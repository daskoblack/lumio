"""Orchestrateur : enchaîne les étapes de façon asynchrone, par job.

Chaque étape lit/écrit l'état persisté. Le job s'arrête après l'analyse pour
laisser l'utilisateur fixer les durées, puis reprend au scripting.
Pas de script monolithique : chaque étape est indépendante et rejouable.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from ..core.config import Config
from ..core.exceptions import InvalidStateError
from ..core.models import Course, CourseStatus, Section
from ..core.timing import deviation, words_to_duration
from ..pipeline import analysis, extraction, scripting, sectioning, slides as slides_pipeline
from ..pipeline import subtitles as subtitles_pipeline
from ..pipeline import synthesis, timeline as timeline_pipeline
from ..providers.llm.base import LLMProvider
from ..providers.llm.factory import build_llm
from ..providers.stt.base import STTProvider
from ..providers.stt.factory import build_stt
from ..providers.tts.base import TTSProvider
from ..providers.tts.factory import build_tts
from ..providers.video.base import VideoEngine
from ..providers.video.factory import build_video_engine
from .store import JobStore
from .voice_store import VoiceProfileStore


class Orchestrator:
    def __init__(
        self,
        config: Config,
        llm: LLMProvider | None = None,
        tts: TTSProvider | None = None,
        video: VideoEngine | None = None,
        stt: STTProvider | None = None,
    ) -> None:
        self._config = config
        self._store = JobStore(config.workspace_path)
        self._voice_store = VoiceProfileStore(config.workspace_path)
        # Providers injectables (tests). Sinon construits PARESSEUSEMENT : les
        # commandes qui n'en ont pas besoin (list, show, set-duration) ne
        # réclament pas de clé / de dépendance réseau.
        self._llm = llm
        self._tts = tts
        self._video = video
        self._stt = stt

    @property
    def store(self) -> JobStore:
        return self._store

    @property
    def llm(self) -> LLMProvider:
        if self._llm is None:
            self._llm = build_llm(self._config)
        return self._llm

    @property
    def tts(self) -> TTSProvider:
        if self._tts is None:
            self._tts = build_tts(self._config)
        return self._tts

    @property
    def video(self) -> VideoEngine:
        if self._video is None:
            self._video = build_video_engine()
        return self._video

    @property
    def stt(self) -> STTProvider:
        if self._stt is None:
            self._stt = build_stt(self._config)
        return self._stt

    # --- Étape 1 : extraction + analyse + découpage (-> ANALYZED) ---
    async def create_and_analyze(self, pdf_path: str, title: str | None = None) -> Course:
        course = Course(
            title=title or Path(pdf_path).stem,
            source_pdf=str(Path(pdf_path).resolve()),
            language=self._config.language,
        )
        self._store.save(course)  # crée le dossier du job tôt

        slides, document_text = extraction.extract(
            pdf_path, self._store.images_dir(course.id)
        )
        course.slides = slides
        course.status = CourseStatus.EXTRACTED
        self._store.save(course)

        structure, truncated = await analysis.analyze_structure(
            self.llm, document_text, self._config.providers.llm.max_document_chars
        )
        course.truncated = truncated
        if structure.get("course_title") and not title:
            course.title = str(structure["course_title"])

        course.sections = sectioning.build_sections(
            structure, slides, self._config.voice.default_speech_rate_wps
        )
        course.status = CourseStatus.ANALYZED
        self._store.save(course)
        return course

    # --- Réglage utilisateur : durée cible d'une section (optionnelle) ---
    def set_target_duration(
        self, job_id: str, section_index: int, duration_s: float | None
    ) -> Section:
        course = self._store.load(job_id)
        section = course.section_by_index(section_index)
        if section is None:
            raise InvalidStateError(f"Section {section_index} inexistante.")
        section.target_duration_s = duration_s  # None = retour au mode auto
        self._store.save(course)
        return section

    # --- Étape 2 : génération des scripts (-> SCRIPTED) ---
    async def run_scripting(self, job_id: str) -> Course:
        course = self._store.load(job_id)
        if course.status not in (CourseStatus.ANALYZED, CourseStatus.SCRIPTED):
            raise InvalidStateError(
                f"Scripting impossible depuis l'état {course.status.value}."
            )

        rate = self._config.voice.default_speech_rate_wps
        tol = self._config.scripting.word_budget_tolerance
        max_passes = self._config.scripting.max_generation_passes

        # Génération concurrente des sections (async).
        results = await asyncio.gather(
            *(
                scripting.generate_script(
                    self.llm, section, self._section_source(course, section), rate, tol, max_passes
                )
                for section in course.sections
            )
        )

        for section, script in zip(course.sections, results):
            section.script = script
            # Estimation de durée AVANT TTS, affinée par le nb de mots réellement généré.
            section.estimated_duration_s = words_to_duration(
                script.word_count_actual, rate
            )
            # Écart estimé/cible (indicatif ; l'écart réel sera calculé post-TTS).
            if section.target_duration_s:
                section.duration_deviation = deviation(
                    section.estimated_duration_s, section.target_duration_s
                )

        course.status = CourseStatus.SCRIPTED
        self._store.save(course)
        return course

    # --- Étape 3 : synthèse vocale + calibration + correction bornée (-> SYNTHESIZED) ---
    async def run_synthesis(self, job_id: str) -> Course:
        course = self._store.load(job_id)
        if course.status not in (CourseStatus.SCRIPTED, CourseStatus.SYNTHESIZED):
            raise InvalidStateError(
                f"Synthèse impossible depuis l'état {course.status.value}."
            )

        audio_dir = self._store.job_dir(job_id) / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        voice = self._voice_store.load(
            course.voice_profile_id,
            self._config.providers.tts.voice,
            self._config.voice.default_speech_rate_wps,
        )
        tol = self._config.scripting.word_budget_tolerance
        max_passes = self._config.scripting.max_generation_passes
        threshold = self._config.synthesis.deviation_threshold

        await asyncio.gather(
            *(
                synthesis.synthesize_section(
                    self.llm,
                    self.tts,
                    section,
                    self._section_source(course, section),
                    voice,
                    audio_dir,
                    tol,
                    threshold,
                    max_passes,
                )
                for section in course.sections
            )
        )

        self._voice_store.save(voice)
        course.status = CourseStatus.SYNTHESIZED
        self._store.save(course)
        return course

    # --- Étape 4 : rendu des slides + timeline + montage FFmpeg (-> RENDERED) ---
    async def run_rendering(self, job_id: str) -> Course:
        course = self._store.load(job_id)
        if course.status not in (CourseStatus.SYNTHESIZED, CourseStatus.RENDERED):
            raise InvalidStateError(
                f"Rendu impossible depuis l'état {course.status.value}."
            )

        job_dir = self._store.job_dir(job_id)
        slides_dir = job_dir / "slides"
        output_dir = job_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        slides_pipeline.render_all(
            course.slides, slides_dir, self._config.slides.width, self._config.slides.height
        )

        entries = timeline_pipeline.build_timeline(course)
        video_path = str(output_dir / "video.mp4")
        await self.video.assemble(entries, video_path)

        course.status = CourseStatus.RENDERED
        self._store.save(course)
        return course

    # --- Étape 5 : sous-titres (Whisper) + incrustation souple (-> DONE) ---
    async def run_subtitles(self, job_id: str) -> Course:
        course = self._store.load(job_id)
        if course.status not in (CourseStatus.RENDERED, CourseStatus.DONE):
            raise InvalidStateError(
                f"Sous-titrage impossible depuis l'état {course.status.value}."
            )

        output_dir = self._store.job_dir(job_id) / "output"
        video_path = output_dir / "video.mp4"
        srt_path = output_dir / "subtitles.srt"
        final_path = output_dir / "video_final.mp4"

        await subtitles_pipeline.generate_srt(
            self.stt, course, self._config.subtitles, srt_path
        )
        await subtitles_pipeline.mux_subtitles(str(video_path), str(srt_path), str(final_path))

        course.status = CourseStatus.DONE
        self._store.save(course)
        return course

    def _section_source(self, course: Course, section: Section) -> str:
        """Texte source des slides associées à la section (contexte de génération)."""
        parts = [
            slide.source_text()
            for sid in section.slide_ids
            if (slide := course.slide_by_id(sid))
        ]
        return "\n\n".join(p for p in parts if p)
