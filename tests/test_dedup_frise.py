"""Vérifie que la génération, mise bout à bout, ne redemande pas au modèle
de raconter une frise progressive depuis le début à chaque page (cause
identifiée : le texte extrait d'une page PDF de type 'build' PowerPoint
cumule tout ce qui a déjà été révélé)."""

import pytest

from lectio.core.config import Config
from lectio.core.models import ContentBlock, Course, CourseStatus, Section, SectionKind, Slide
from lectio.jobs.orchestrator import Orchestrator
from lectio.providers.llm.base import LLMProvider


class _CapturingLLM(LLMProvider):
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def complete(self, system, user, *, json_mode=False, temperature=None, max_tokens=None):
        self.prompts.append(user)
        return f"Narration de la page {len(self.prompts)}, avec du contenu original."


def _frise_course(tmp_path) -> tuple[Orchestrator, str]:
    """5 pages d'une même section, texte cumulatif comme un export PowerPoint
    en construction progressive (page N = pages 1..N-1 + une phase de plus)."""
    config = Config.load()
    config.paths.workspace = str(tmp_path / "workspace")

    phases = [
        "Phase 1 : origines du mouvement.",
        "Phase 2 : premiers développements.",
        "Phase 3 : expansion rapide.",
        "Phase 4 : consolidation.",
        "Phase 5 : bilan et héritage.",
    ]
    slides = []
    cumul = ""
    for i, phase in enumerate(phases):
        cumul = f"{cumul} {phase}".strip()
        slides.append(Slide(
            index=i, source_page=i + 1, title=f"Frise - étape {i + 1}",
            content_blocks=[ContentBlock(kind="text", text=cumul)],
        ))

    section = Section(
        index=0, kind=SectionKind.CONCEPT, title="La frise",
        context="Cette partie présente les 5 phases historiques, une par page.",
        slide_ids=[s.id for s in slides],
    )
    course = Course(title="Cours", source_pdf="x.pdf", status=CourseStatus.ANALYZED,
                     slides=slides, sections=[section])

    llm = _CapturingLLM()
    orch = Orchestrator(config, llm=llm)
    orch.store.save(course)
    return orch, course.id


@pytest.mark.asyncio
async def test_chaque_page_ne_recoit_que_sa_phase_nouvelle(tmp_path):
    orch, job_id = _frise_course(tmp_path)
    llm: _CapturingLLM = orch.llm  # type: ignore[assignment]

    await orch.run_scripting(job_id)

    assert len(llm.prompts) == 5
    for i, prompt in enumerate(llm.prompts):
        bloc = prompt.split("Contenu de CETTE page à expliquer :")[1]
        # La page reçoit sa PROPRE phase...
        assert f"Phase {i + 1} " in bloc or f"Phase {i + 1}." in bloc
        # ...mais plus les phases précédentes déjà cumulées dans le PDF.
        for j in range(1, i + 1):
            assert f"Phase {j} :" not in bloc, (
                f"page {i + 1} : la phase {j} n'aurait pas dû être répétée dans le prompt"
            )


@pytest.mark.asyncio
async def test_premiere_page_de_section_non_touchee(tmp_path):
    """Rien à dédupliquer pour la toute première page (pas de page précédente
    dans la même section) : le texte source doit rester intact."""
    orch, job_id = _frise_course(tmp_path)
    llm: _CapturingLLM = orch.llm  # type: ignore[assignment]

    await orch.run_scripting(job_id)

    premier_bloc = llm.prompts[0].split("Contenu de CETTE page à expliquer :")[1]
    assert "Phase 1 :" in premier_bloc
