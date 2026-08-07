"""Orchestrateur : enchaîne les étapes de façon asynchrone, par job.

Chaque étape lit/écrit l'état persisté. Le job s'arrête après l'analyse pour
laisser l'utilisateur fixer les durées, puis reprend au scripting.
Pas de script monolithique : chaque étape est indépendante et rejouable.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

from ..core import proc
from ..core.config import Config
from ..core.exceptions import InvalidStateError, LectioError
from ..core.models import Course, CourseStatus, Section
from ..core.timing import deviation, duration_to_words, words_to_duration
from ..pipeline import analysis, extraction, scripting, sectioning, slides as slides_pipeline
from ..pipeline import subtitles as subtitles_pipeline
from ..pipeline import synthesis, timeline as timeline_pipeline
from ..providers.llm.base import LLMProvider
from ..providers.llm.factory import build_llm
from ..providers.stt.base import STTProvider
from ..providers.stt.factory import build_stt
from ..providers.tts.base import TTSProvider, VoiceProfile
from ..providers.tts.factory import build_tts
from ..providers.video.base import VideoEngine
from ..providers.video.factory import build_video_engine
from .store import JobStore
from .voice_store import VoiceProfileStore

# Signature : on_progress(label, terminés, total) — appelé au fil de l'avancement.
# None par défaut : le CLI n'en a pas besoin, seule l'app desktop s'en sert.
ProgressCallback = Callable[[str, int, int], None]

# Durée du silence inséré quand la voix échoue sur une page : assez pour que
# la page reste visible, assez court pour ne pas gêner.
_SILENT_PLACEHOLDER_S = 2.0


class _ProgressTracker:
    """Compteur d'avancement d'une étape."""

    def __init__(self, stage: str, total: int, on_progress: ProgressCallback | None) -> None:
        self._total = total
        self._done = 0
        self._on_progress = on_progress
        if on_progress:
            on_progress(f"{stage}…", 0, max(total, 1))

    def tick(self, label: str) -> None:
        self._done += 1
        if self._on_progress:
            self._on_progress(label, self._done, max(self._total, 1))


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
    async def create_and_analyze(
        self, pdf_path: str, title: str | None = None, voice_id: str | None = None
    ) -> Course:
        course = Course(
            title=title or Path(pdf_path).stem,
            source_pdf=str(Path(pdf_path).resolve()),
            language=self._config.language,
            # Le profil de voix EST l'identifiant de la voix : la calibration du
            # débit reste ainsi propre à chaque voix (des voix différentes ont
            # des débits différents), pas partagée sous un profil "default" générique.
            voice_profile_id=voice_id or self._config.providers.tts.voice,
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

    # --- Réglage utilisateur : durée cible d'une ou plusieurs sections (optionnelle) ---
    def set_target_durations(
        self, job_id: str, section_indices: list[int], duration_s: float | None
    ) -> list[Section]:
        course = self._store.load(job_id)
        sections: list[Section] = []
        for index in section_indices:
            section = course.section_by_index(index)
            if section is None:
                raise InvalidStateError(f"Section {index} inexistante.")
            sections.append(section)

        for section in sections:  # tout validé avant de rien muter (pas d'écriture partielle)
            section.target_duration_s = duration_s  # None = retour au mode auto
        self._store.save(course)
        return sections

    # --- Étape 2 : génération des scripts, PAGE PAR PAGE avec contexte (-> SCRIPTED) ---
    async def run_scripting(self, job_id: str, on_progress: ProgressCallback | None = None) -> Course:
        course = self._store.load(job_id)
        if course.status not in (CourseStatus.ANALYZED, CourseStatus.SCRIPTED):
            raise InvalidStateError(
                f"Scripting impossible depuis l'état {course.status.value}."
            )

        rate = self._config.voice.default_speech_rate_wps
        max_passes = self._config.scripting.max_generation_passes

        plan = self._build_narration_plan(course, rate)
        progress = _ProgressTracker("Écriture du script", len(plan), on_progress)

        # SÉQUENTIEL sur tout le cours : chaque page doit connaître ce qui a
        # réellement été dit avant elle. Générer les sections en parallèle
        # privait chaque début de section de tout contexte -> le professeur
        # réintroduisait le sujet à chaque partie (répétitions signalées).
        # Aucun coût de vitesse : le RateLimiter sérialise déjà les appels.
        previous_text: str | None = None
        summaries: list[str] = []
        failures: list[str] = []
        degradation_reported = False
        initial_llm_label = getattr(self.llm, "active_label", None)

        for ctx in plan:
            ctx.previous_text = previous_text
            ctx.previous_summaries = list(summaries[-scripting._MAX_SUMMARIES:])
            try:
                ctx.slide.script = await scripting.generate_slide_script(
                    self.llm, ctx, max_passes
                )
            except LectioError as exc:
                # Une page qui échoue ne doit pas emporter tout le cours :
                # narration de secours bâtie sur la page, et on continue.
                ctx.slide.script = scripting.emergency_script(ctx)
                failures.append(f"page {ctx.slide.source_page} ({exc})")

            # Le fournisseur d'IA principal peut s'épuiser en cours de route et
            # basculer vers un modèle plus faible (chaîne de repli) : signalé
            # une seule fois, à l'endroit où la qualité a pu changer.
            if not degradation_reported:
                current_label = getattr(self.llm, "active_label", None)
                if current_label is not None and current_label != initial_llm_label:
                    failures.append(
                        f"page {ctx.slide.source_page} : bascule vers un modèle d'IA de "
                        f"repli ({current_label}) après épuisement de {initial_llm_label} — "
                        "la qualité de narration peut être réduite à partir d'ici."
                    )
                    degradation_reported = True

            ctx.slide.estimated_duration_s = words_to_duration(
                ctx.slide.script.word_count_actual, rate
            )
            previous_text = ctx.slide.script.text
            summaries.append(scripting.summarize_for_context(ctx.slide.script.text))
            progress.tick(f"Page {ctx.slide.source_page} : {ctx.section.title}")
            self._store.save(course)  # reprise possible si l'app s'arrête en cours

        for section in course.sections:
            slides = course.section_slides(section)
            section.estimated_duration_s = sum(s.estimated_duration_s for s in slides)
            if section.target_duration_s:
                section.duration_deviation = deviation(
                    section.estimated_duration_s, section.target_duration_s
                )

        if course.truncated:
            failures.insert(
                0,
                "document long : l'analyse initiale n'a vu qu'une partie du texte, "
                "les estimations de durée peuvent être moins précises en fin de cours.",
            )
        course.degraded_pages = failures
        course.status = CourseStatus.SCRIPTED
        self._store.save(course)
        return course

    def _build_narration_plan(
        self, course: Course, rate: float
    ) -> list[scripting.NarrationContext]:
        """Ordonne toutes les pages du cours et prépare leur contexte fixe."""
        ordered: list[tuple[Section, Slide, bool]] = []
        for section in sorted(course.sections, key=lambda s: s.index):
            slides = course.section_slides(section)
            for position_in_section, slide in enumerate(slides):
                ordered.append((section, slide, position_in_section == 0))

        # Budget de mots par page, calculé section par section. Une cible EST
        # TOUJOURS posée, y compris en mode Automatique (via l'estimation faite
        # à l'analyse) : la laisser totalement libre ("écris ce qui te semble
        # naturel") laissait un modèle bavard produire un texte 2 à 3 fois plus
        # long que prévu sur les sections que l'utilisateur n'avait pas touchées
        # — la cause du "20 minutes demandées, 1 heure obtenue".
        targets: dict[str, int | None] = {}
        tolerances: dict[str, float] = {}
        explicit_tol = self._config.scripting.word_budget_tolerance
        auto_tol = self._config.scripting.auto_overshoot_tolerance
        for section in course.sections:
            slides = course.section_slides(section)
            if section.target_duration_s is None:
                for s in slides:
                    # Cas rarissime (LLM n'a fourni aucune estimation) : sans
                    # aucun ancrage possible, on laisse vraiment libre.
                    targets[s.id] = s.estimated_narration_words or None
                    tolerances[s.id] = auto_tol
                continue
            shares = scripting.distribute_target_words(
                section, slides, duration_to_words(section.target_duration_s, rate)
            )
            for s, share in zip(slides, shares):
                targets[s.id] = share
                tolerances[s.id] = explicit_tol

        total = len(ordered)
        return [
            scripting.NarrationContext(
                section=section,
                slide=slide,
                position=index + 1,
                total=total,
                starts_new_section=starts_new and index > 0,
                next_slide=ordered[index + 1][1] if index + 1 < total else None,
                target_words=targets.get(slide.id),
                tolerance=tolerances.get(slide.id, explicit_tol),
            )
            for index, (section, slide, starts_new) in enumerate(ordered)
        ]

    # --- Étape 3 : synthèse vocale par slide + calibration + correction bornée (-> SYNTHESIZED) ---
    async def run_synthesis(self, job_id: str, on_progress: ProgressCallback | None = None) -> Course:
        course = self._store.load(job_id)
        if course.status not in (CourseStatus.SCRIPTED, CourseStatus.SYNTHESIZED):
            raise InvalidStateError(
                f"Synthèse impossible depuis l'état {course.status.value}."
            )

        audio_dir = self._store.job_dir(job_id) / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        voice = self._voice_store.load(
            course.voice_profile_id,
            course.voice_profile_id,
            self._config.voice.default_speech_rate_wps,
        )
        max_passes = self._config.scripting.max_generation_passes
        threshold = self._config.synthesis.deviation_threshold

        plan = self._build_narration_plan(course, self._config.voice.default_speech_rate_wps)
        progress = _ProgressTracker("Enregistrement de la voix", len(plan), on_progress)

        failures: list[str] = []
        warnings: list[str] = []
        previous_text: str | None = None
        for ctx in plan:
            ctx.previous_text = previous_text
            try:
                await synthesis.synthesize_slide(
                    self.llm, self.tts, ctx, voice, audio_dir, threshold, max_passes
                )
            except LectioError as exc:
                # Une page muette ne doit pas emporter la vidéo entière : on
                # met un court silence à la place et on poursuit.
                await self._silent_placeholder(ctx, audio_dir)
                failures.append(f"page {ctx.slide.source_page} ({exc})")

            if ctx.warning and ctx.warning not in warnings:
                warnings.append(ctx.warning)
            previous_text = ctx.slide.script.text if ctx.slide.script else None
            progress.tick(f"Page {ctx.slide.source_page} : {ctx.section.title}")
            self._store.save(course)  # reprise possible si l'app s'arrête en cours

        for section in course.sections:
            slides = course.section_slides(section)
            section.actual_duration_s = sum(s.actual_duration_s or 0.0 for s in slides)
            if section.target_duration_s:
                section.duration_deviation = deviation(
                    section.actual_duration_s, section.target_duration_s
                )

        course.degraded_pages = [*course.degraded_pages, *failures, *warnings]
        self._voice_store.save(voice)
        course.status = CourseStatus.SYNTHESIZED
        self._store.save(course)
        return course

    async def _silent_placeholder(
        self, ctx: "scripting.NarrationContext", audio_dir: Path
    ) -> None:
        """Court silence à la place d'une page dont la voix a échoué.

        Sans cela, la page n'aurait aucune durée réelle et la construction de
        la timeline refuserait de produire la vidéo — tout le travail déjà
        fait serait perdu à cause d'une seule page.
        """
        slide = ctx.slide
        out_path = audio_dir / f"slide_{slide.index:03d}.mp3"
        await proc.run([
            proc.resolve_binary("ffmpeg"), "-y",
            "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
            "-t", f"{_SILENT_PLACEHOLDER_S}",
            str(out_path),
        ])
        if slide.script is not None:
            slide.script.audio_path = str(out_path)
            slide.script.audio_duration_s = _SILENT_PLACEHOLDER_S
        slide.actual_duration_s = _SILENT_PLACEHOLDER_S

    # --- Étape 4 : rendu des slides + timeline + montage FFmpeg (-> RENDERED) ---
    async def run_rendering(self, job_id: str, on_progress: ProgressCallback | None = None) -> Course:
        course = self._store.load(job_id)
        if course.status not in (CourseStatus.SYNTHESIZED, CourseStatus.RENDERED):
            raise InvalidStateError(
                f"Rendu impossible depuis l'état {course.status.value}."
            )

        job_dir = self._store.job_dir(job_id)
        slides_dir = job_dir / "slides"
        output_dir = job_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        if on_progress:
            on_progress("Mise en page des pages du PDF…", 0, 2)
        slides_pipeline.render_all(
            course.source_pdf, course.slides, slides_dir,
            self._config.slides.width, self._config.slides.height,
        )

        if on_progress:
            on_progress("Montage de la vidéo…", 1, 2)
        entries = timeline_pipeline.build_timeline(course)
        video_path = str(output_dir / "video.mp4")
        await self.video.assemble(entries, video_path)
        if on_progress:
            on_progress("Montage terminé", 2, 2)

        course.status = CourseStatus.RENDERED
        self._store.save(course)
        return course

    # --- Étape 5 : sous-titres (Whisper) + incrustation souple (-> DONE) ---
    async def run_subtitles(self, job_id: str, on_progress: ProgressCallback | None = None) -> Course:
        course = self._store.load(job_id)
        if course.status not in (CourseStatus.RENDERED, CourseStatus.DONE):
            raise InvalidStateError(
                f"Sous-titrage impossible depuis l'état {course.status.value}."
            )

        output_dir = self._store.job_dir(job_id) / "output"
        video_path = output_dir / "video.mp4"
        srt_path = output_dir / "subtitles.srt"
        final_path = output_dir / "video_final.mp4"

        # Sous-titres désactivés par défaut : la vidéo finale est alors
        # simplement la vidéo montée, sans passe de transcription.
        if not course.subtitles_enabled:
            shutil.copyfile(video_path, final_path)
            if on_progress:
                on_progress("Terminé", 1, 1)
            course.status = CourseStatus.DONE
            self._store.save(course)
            return course

        if on_progress:
            on_progress("Transcription des sous-titres…", 0, 2)
        try:
            await subtitles_pipeline.generate_srt(
                self.stt, course, self._config.subtitles, srt_path
            )
            if on_progress:
                on_progress("Incrustation dans la vidéo…", 1, 2)
            await subtitles_pipeline.mux_subtitles(
                str(video_path), str(srt_path), str(final_path)
            )
        except LectioError as exc:
            # Les sous-titres sont un supplément : leur échec ne doit pas
            # priver l'utilisateur de la vidéo qu'il vient d'attendre.
            shutil.copyfile(video_path, final_path)
            course.degraded_pages = [
                *course.degraded_pages,
                f"sous-titres non générés ({exc})",
            ]
        if on_progress:
            on_progress("Terminé", 2, 2)

        course.status = CourseStatus.DONE
        self._store.save(course)
        return course

    def set_subtitles_enabled(self, job_id: str, enabled: bool) -> Course:
        """Active ou non les sous-titres pour ce cours (décidé au planning)."""
        course = self._store.load(job_id)
        course.subtitles_enabled = enabled
        self._store.save(course)
        return course
