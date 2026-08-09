"""Tests de la régénération ciblée d'une section (filet de sécurité
complémentaire au plancher de mots / filtre anti-folie) : seules les pages de
la section visée sont réécrites, les autres restent intactes."""

from pathlib import Path

import pytest

from lectio.core.config import Config
from lectio.core.exceptions import InvalidStateError, LLMError
from lectio.core.models import (
    ContentBlock, Course, CourseStatus, Script, Section, SectionKind, Slide,
)
from lectio.jobs.orchestrator import Orchestrator
from lectio.providers.llm.base import LLMProvider
from lectio.providers.tts.base import TTSProvider, TTSResult, VoiceProfile
from lectio.providers.video.base import TimelineEntry, VideoEngine


class _RecordingLLM(LLMProvider):
    """Renvoie un texte fixe qui trahit s'il a vu la consigne utilisateur."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def complete(self, system, user, *, json_mode=False, temperature=None, max_tokens=None):
        self.prompts.append(user)
        marker = "AVEC-CONSIGNE" if "Consigne spécifique" in user else "SANS-CONSIGNE"
        return f"Narration régénérée {marker}, avec assez de mots pour être valable ici."


class _RecordingTTS(TTSProvider):
    def __init__(self) -> None:
        self.calls = 0

    async def synthesize(self, text, voice, out_path):
        self.calls += 1
        return TTSResult(audio_path=out_path, duration_s=5.0, word_count=len(text.split()))


class _RecordingVideo(VideoEngine):
    def __init__(self) -> None:
        self.assembled_entries: list[TimelineEntry] | None = None

    async def assemble(self, timeline, out_path):
        self.assembled_entries = timeline
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"fake-mp4")  # un vrai VideoEngine produirait ce fichier
        return out_path


def _slide(index, page, text="Contenu source de la page.") -> Slide:
    return Slide(
        index=index, source_page=page, title=f"P{page}",
        content_blocks=[ContentBlock(kind="text", text=text)],
        rendered_path=f"/slides/p{page}.png",
        actual_duration_s=4.0,
        script=Script(
            slide_id="", text=f"Narration originale de la page {page}.",
            word_count_actual=6, generation_pass=1,
            audio_path=f"/audio/p{page}.mp3", audio_duration_s=4.0,
        ),
    )


def _make_course(tmp_path) -> tuple[Orchestrator, str, Course]:
    config = Config.load()
    config.paths.workspace = str(tmp_path / "workspace")

    slides = [_slide(0, 1), _slide(1, 2), _slide(2, 3), _slide(3, 4)]
    for s in slides:
        s.script.slide_id = s.id  # lie le script à sa slide (id généré après coup)

    section_a = Section(index=0, kind=SectionKind.INTRO, title="Intro", slide_ids=[slides[0].id])
    section_b = Section(
        index=1, kind=SectionKind.CONCEPT, title="Les fractions",
        slide_ids=[slides[1].id, slides[2].id, slides[3].id],
    )

    course = Course(
        title="Cours", source_pdf="x.pdf", status=CourseStatus.DONE,
        slides=slides, sections=[section_a, section_b], subtitles_enabled=False,
    )

    llm, tts, video = _RecordingLLM(), _RecordingTTS(), _RecordingVideo()
    orch = Orchestrator(config, llm=llm, tts=tts, video=video)
    orch.store.save(course)
    return orch, course.id, course


@pytest.mark.asyncio
async def test_seules_les_pages_de_la_section_visee_sont_regenerees(tmp_path):
    orch, job_id, course = _make_course(tmp_path)
    tts: _RecordingTTS = orch.tts  # type: ignore[assignment]

    result = await orch.regenerate_section(job_id, 1, "Utilise un exemple avec des fruits.")

    section_b = result.section_by_index(1)
    slides_b = result.section_slides(section_b)
    assert all("AVEC-CONSIGNE" in s.script.text for s in slides_b)
    assert all("Narration régénérée" in s.script.text for s in slides_b)

    section_a = result.section_by_index(0)
    slides_a = result.section_slides(section_a)
    assert all(s.script.text == "Narration originale de la page 1." for s in slides_a)

    # Seules les 3 pages de la section 1 ont déclenché une synthèse vocale.
    assert tts.calls == 3


@pytest.mark.asyncio
async def test_consigne_atteint_bien_le_prompt_des_pages_visees(tmp_path):
    orch, job_id, _ = _make_course(tmp_path)
    llm: _RecordingLLM = orch.llm  # type: ignore[assignment]

    await orch.regenerate_section(job_id, 1, "Utilise un exemple avec des fruits.")

    assert len(llm.prompts) == 3  # les 3 pages de la section 1, pas plus
    assert all("Utilise un exemple avec des fruits." in p for p in llm.prompts)


@pytest.mark.asyncio
async def test_video_reassemblee_apres_regeneration(tmp_path):
    orch, job_id, _ = _make_course(tmp_path)
    video: _RecordingVideo = orch.video  # type: ignore[assignment]

    await orch.regenerate_section(job_id, 1, "Sois plus concis.")

    assert video.assembled_entries is not None
    assert len(video.assembled_entries) == 4  # les 4 pages du cours, dans l'ordre


@pytest.mark.asyncio
async def test_statut_final_done_sans_sous_titres(tmp_path):
    orch, job_id, _ = _make_course(tmp_path)
    result = await orch.regenerate_section(job_id, 1, "Sois plus concis.")
    assert result.status == CourseStatus.DONE


@pytest.mark.asyncio
async def test_section_inexistante_leve_une_erreur(tmp_path):
    orch, job_id, _ = _make_course(tmp_path)
    with pytest.raises(InvalidStateError):
        await orch.regenerate_section(job_id, 99, "Sois plus concis.")


@pytest.mark.asyncio
async def test_consigne_vide_est_rejetee(tmp_path):
    orch, job_id, _ = _make_course(tmp_path)
    with pytest.raises(InvalidStateError):
        await orch.regenerate_section(job_id, 1, "   ")


@pytest.mark.asyncio
async def test_etat_trop_precoce_est_rejete(tmp_path):
    config = Config.load()
    config.paths.workspace = str(tmp_path / "workspace")
    course = Course(
        title="C", source_pdf="x.pdf", status=CourseStatus.ANALYZED,
        sections=[Section(index=0, kind=SectionKind.INTRO, title="A")],
    )
    orch = Orchestrator(config, llm=_RecordingLLM(), tts=_RecordingTTS(), video=_RecordingVideo())
    orch.store.save(course)
    with pytest.raises(InvalidStateError):
        await orch.regenerate_section(course.id, 0, "Consigne.")


@pytest.mark.asyncio
async def test_echec_llm_sur_une_page_visee_remonte_l_erreur(tmp_path):
    """Contrairement à la génération initiale (qui bascule sur un secours pour
    ne pas perdre tout le travail), une régénération ciblée qui échoue doit le
    dire clairement : l'utilisateur attend un résultat immédiat, pas un secours
    silencieux qui ignorerait sa consigne."""
    class _EchecLLM(LLMProvider):
        async def complete(self, system, user, *, json_mode=False, temperature=None, max_tokens=None):
            raise LLMError("Fournisseur indisponible.")

    config = Config.load()
    config.paths.workspace = str(tmp_path / "workspace")
    slides = [_slide(0, 1)]
    slides[0].script.slide_id = slides[0].id
    section = Section(index=0, kind=SectionKind.INTRO, title="A", slide_ids=[slides[0].id])
    course = Course(
        title="C", source_pdf="x.pdf", status=CourseStatus.DONE,
        slides=slides, sections=[section],
    )
    orch = Orchestrator(config, llm=_EchecLLM(), tts=_RecordingTTS(), video=_RecordingVideo())
    orch.store.save(course)

    with pytest.raises(LLMError):
        await orch.regenerate_section(course.id, 0, "Consigne.")
