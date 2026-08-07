"""Tests du budget de mots, de la correction ASYMÉTRIQUE (jamais d'invention),
de la répartition du budget entre pages et du contexte anti-répétition (LLM
simulé)."""

import pytest

from lectio.core.models import ContentBlock, Section, SectionKind, Slide
from lectio.pipeline.scripting import (
    NarrationContext,
    distribute_target_words,
    generate_slide_script,
)
from lectio.providers.llm.base import LLMProvider


class FakeLLM(LLMProvider):
    """Renvoie des textes d'un nombre de mots contrôlé, tour à tour."""

    def __init__(self, word_counts: list[int]) -> None:
        self._word_counts = word_counts
        self.calls = 0

    async def complete(self, system, user, *, json_mode=False, temperature=None, max_tokens=None):
        n = self._word_counts[self.calls]
        self.calls += 1
        return " ".join(["mot"] * n)


def _section(titre="T"):
    return Section(index=0, kind=SectionKind.CONCEPT, title=titre)


def _slide(text="source"):
    return Slide(index=0, source_page=1, title="P1", content_blocks=[ContentBlock(kind="text", text=text)])


def _ctx(**kwargs) -> NarrationContext:
    defaults = dict(section=_section(), slide=_slide(), position=1, total=1, tolerance=0.10)
    return NarrationContext(**{**defaults, **kwargs})


@pytest.mark.asyncio
async def test_no_target_generates_once_without_budget():
    llm = FakeLLM([50])
    script = await generate_slide_script(llm, _ctx(), max_passes=2)
    assert script.word_count_target is None
    assert script.generation_pass == 1
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_target_within_tolerance_no_correction():
    # cible 120 mots ; on génère 118 -> dans ±10%, pas de correction
    llm = FakeLLM([118])
    script = await generate_slide_script(llm, _ctx(target_words=120), max_passes=2)
    assert script.word_count_target == 120
    assert script.generation_pass == 1
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_depassement_declenche_une_correction():
    llm = FakeLLM([200, 122])  # 200 mots pour une cible de 120 : net dépassement
    script = await generate_slide_script(llm, _ctx(target_words=120), max_passes=2)
    assert script.generation_pass == 2
    assert script.word_count_actual == 122
    assert llm.calls == 2


@pytest.mark.asyncio
async def test_manque_de_mots_n_est_JAMAIS_corrige():
    """Le cœur du correctif anti-invention : un texte trop COURT est accepté
    tel quel, jamais renvoyé au modèle pour être "complété"."""
    llm = FakeLLM([40])  # bien en dessous de la cible de 120
    script = await generate_slide_script(llm, _ctx(target_words=120), max_passes=2)
    assert script.generation_pass == 1
    assert script.word_count_actual == 40
    assert llm.calls == 1  # aucun second appel : pas de tentative de "compléter"


@pytest.mark.asyncio
async def test_correction_is_bounded_to_one_pass():
    llm = FakeLLM([200, 190])  # la correction dépasse encore : acceptée telle quelle
    script = await generate_slide_script(llm, _ctx(target_words=120), max_passes=2)
    assert script.generation_pass == 2
    assert llm.calls == 2  # jamais 3


class _CapturingLLM(LLMProvider):
    def __init__(self) -> None:
        self.prompt = ""

    async def complete(self, system, user, *, json_mode=False, temperature=None, max_tokens=None):
        self.prompt = user
        return "bla bla"


@pytest.mark.asyncio
async def test_previous_and_next_context_passed_to_prompt():
    llm = _CapturingLLM()
    await generate_slide_script(
        llm,
        _ctx(
            position=2, total=3,
            previous_text="Nous avons vu l'introduction",
            next_slide=_slide("contenu de la page suivante"),
        ),
        max_passes=2,
    )
    assert "Nous avons vu l'introduction" in llm.prompt
    assert "contenu de la page suivante" in llm.prompt


# --- Anti-répétition ------------------------------------------------------

@pytest.mark.asyncio
async def test_seule_la_toute_premiere_page_introduit_le_cours():
    llm = _CapturingLLM()
    await generate_slide_script(llm, _ctx(position=1, total=5), max_passes=2)
    assert "TOUTE PREMIÈRE page" in llm.prompt


@pytest.mark.asyncio
async def test_une_nouvelle_section_n_introduit_pas_le_cours():
    """Le cas qui provoquait les répétitions : chaque section repartait de zéro."""
    llm = _CapturingLLM()
    await generate_slide_script(
        llm,
        _ctx(position=4, total=9, starts_new_section=True, previous_text="déjà dit"),
        max_passes=2,
    )
    assert "TOUTE PREMIÈRE page" not in llm.prompt
    assert "SANS réintroduire" in llm.prompt


@pytest.mark.asyncio
async def test_les_pages_deja_traitees_sont_rappelees_au_modele():
    llm = _CapturingLLM()
    await generate_slide_script(
        llm,
        _ctx(
            position=3, total=5,
            previous_text="texte de la page 2",
            previous_summaries=["résumé page 1", "résumé page 2"],
        ),
        max_passes=2,
    )
    assert "NE REVIENS PAS dessus" in llm.prompt
    assert "résumé page 1" in llm.prompt
    assert "résumé page 2" in llm.prompt


# --- Répartition du budget -------------------------------------------------

def test_distribute_target_words_proportional():
    slides = [_slide(), _slide(), _slide()]
    slides[0].estimated_narration_words = 10
    slides[1].estimated_narration_words = 30
    slides[2].estimated_narration_words = 60

    shares = distribute_target_words(_section(), slides, target_words=100)
    assert sum(shares) == 100
    assert shares[0] < shares[1] < shares[2]


def test_distribute_target_words_falls_back_to_even_split_without_estimates():
    slides = [_slide(), _slide()]
    shares = distribute_target_words(_section(), slides, target_words=50)
    assert sum(shares) == 50
    assert shares[0] == shares[1]
