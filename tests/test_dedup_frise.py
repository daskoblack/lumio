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


# --- Deux fuites qui rendaient la deduplication inoperante ------------------

@pytest.mark.asyncio
async def test_l_apercu_de_la_page_suivante_est_deduplique(tmp_path):
    """L'aperçu de la page suivante remettait TOUTES les étapes déjà traitées
    sous les yeux du modèle, alors même que le contenu de la page courante,
    lui, était bien réduit à sa nouveauté. Le modèle les récapitulait donc
    malgré la consigne de ne pas y revenir."""
    orch, job_id = _frise_course(tmp_path)
    llm: _CapturingLLM = orch.llm  # type: ignore[assignment]

    await orch.run_scripting(job_id)

    for index, prompt in enumerate(llm.prompts[:-1], start=1):
        apercu = prompt.split("Aperçu de la page suivante")[1].split("Contenu de CETTE page")[0]
        for phase in range(1, index + 1):
            assert f"Phase {phase} :" not in apercu, (
                f"page {index} : l'aperçu réaffiche la phase {phase}, déjà traitée"
            )


def test_le_budget_de_mots_n_enfle_pas_avec_le_texte_cumule():
    """Le budget était réparti au prorata du texte AFFICHÉ, qui grossit à
    chaque étape alors que le contenu neuf reste constant : sur un cas réel,
    la dernière page recevait 134 mots à écrire pour 6 mots de nouveauté. Le
    modèle tenait la consigne en meublant avec les étapes précédentes.

    Passe par `build_sections`, comme le vrai pipeline : c'est là que la
    répartition est calculée.
    """
    from lectio.pipeline.sectioning import build_sections

    titre = "Les etapes de la photosynthese"
    etapes = [
        "Etape 1 : absorption de la lumiere par la chlorophylle.",
        "Etape 2 : dissociation des molecules d eau.",
        "Etape 3 : liberation du dioxygene.",
        "Etape 4 : fixation du dioxyde de carbone.",
        "Etape 5 : production de glucose.",
    ]
    slides = [
        Slide(index=i, source_page=i + 1, title="p",
              content_blocks=[ContentBlock(kind="text", text=f"{titre} " + " ".join(etapes[:i + 1]))])
        for i in range(5)
    ]
    structure = {"sections": [{
        "title": "Les etapes", "kind": "concept",
        "source_pages": [1, 2, 3, 4, 5], "estimated_words_per_page": 90,
    }]}
    build_sections(structure, slides, speech_rate_wps=2.3, min_words_per_page=70)

    budgets = [s.estimated_narration_words for s in slides]
    # Pages 2 a 5 : chacune n'apporte qu'une etape. Leur budget doit rester
    # stable, jamais croitre page apres page.
    suivantes = budgets[1:]
    assert max(suivantes) - min(suivantes) <= 15, (
        f"le budget enfle encore d'une page a l'autre : {budgets}"
    )


# --- Structures de diapositives REELLES ------------------------------------
# La version initiale exigeait que la page precedente soit un PREFIXE exact.
# Elle echouait donc sur la plupart des supports reels : un numero de page, un
# pied de page ou un simple changement d'ordre de lecture suffisait a la
# desactiver -- silencieusement.

@pytest.mark.parametrize("nom,precedente,courante", [
    (
        "ajout en fin de page",
        "Titre. Etape 1 : absorption.",
        "Titre. Etape 1 : absorption. Etape 2 : dissociation.",
    ),
    (
        "liste a puces",
        "Titre\n- Etape 1 : absorption",
        "Titre\n- Etape 1 : absorption\n- Etape 2 : dissociation",
    ),
    (
        "numero de page qui change",
        "Titre. Etape 1 : absorption. 1/5",
        "Titre. Etape 1 : absorption. Etape 2 : dissociation. 2/5",
    ),
    (
        "nouvel element en tete de lecture",
        "Titre. Etape 1 : absorption.",
        "Titre. Etape 2 : dissociation. Etape 1 : absorption.",
    ),
    (
        "pied de page repete",
        "Titre. Etape 1. Photosynthese - Lycee",
        "Titre. Etape 1. Etape 2. Photosynthese - Lycee",
    ),
])
def test_deduplication_sur_structures_reelles(nom, precedente, courante):
    from lectio.core.textutil import dedupe_cumulative_source

    resultat = dedupe_cumulative_source(precedente, courante)
    assert "Etape 1" not in resultat, f"{nom} : l'etape deja traitee est encore transmise"
    assert "Etape 2" in resultat, f"{nom} : la nouveaute a ete perdue"


def test_la_deduplication_ne_coupe_jamais_un_mot():
    """L'ancienne decoupe par position tronquait en plein mot des qu'un
    caractere s'intercalait (« pe 2 : dissociation »)."""
    from lectio.core.textutil import dedupe_cumulative_source

    resultat = dedupe_cumulative_source(
        "Titre. Etape 1 : absorption. 1/5",
        "Titre. Etape 1 : absorption. Etape 2 : dissociation. 2/5",
    )
    for mot in resultat.split():
        assert mot.strip(".,;:/") == "" or len(mot) > 1 or mot.isalnum()
    assert "Etape 2 : dissociation." in resultat
