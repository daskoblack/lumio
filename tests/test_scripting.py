"""Tests du budget de mots, de la boucle de correction et de la répartition
du budget entre slides (LLM simulé)."""

import pytest

from lectio.core.models import ContentBlock, Section, SectionKind, Slide
from lectio.pipeline.scripting import distribute_target_words, generate_slide_script
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


def _section():
    return Section(index=0, kind=SectionKind.CONCEPT, title="T")


def _slide(text="source"):
    return Slide(index=0, source_page=1, title="P1", content_blocks=[ContentBlock(kind="text", text=text)])


@pytest.mark.asyncio
async def test_no_target_generates_once_without_budget():
    llm = FakeLLM([50])
    script = await generate_slide_script(
        llm, _section(), _slide(), 1, 1, None, None, target_words=None, tolerance=0.10, max_passes=2
    )
    assert script.word_count_target is None
    assert script.generation_pass == 1
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_target_within_tolerance_no_correction():
    # cible 120 mots ; on génère 118 -> dans ±10%, pas de correction
    llm = FakeLLM([118])
    script = await generate_slide_script(
        llm, _section(), _slide(), 1, 1, None, None, target_words=120, tolerance=0.10, max_passes=2
    )
    assert script.word_count_target == 120
    assert script.generation_pass == 1
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_target_out_of_tolerance_triggers_single_correction():
    llm = FakeLLM([60, 122])
    script = await generate_slide_script(
        llm, _section(), _slide(), 1, 1, None, None, target_words=120, tolerance=0.10, max_passes=2
    )
    assert script.generation_pass == 2
    assert script.word_count_actual == 122
    assert llm.calls == 2


@pytest.mark.asyncio
async def test_correction_is_bounded_to_one_pass():
    llm = FakeLLM([60, 70])
    script = await generate_slide_script(
        llm, _section(), _slide(), 1, 1, None, None, target_words=120, tolerance=0.10, max_passes=2
    )
    assert script.generation_pass == 2
    assert llm.calls == 2  # jamais 3


@pytest.mark.asyncio
async def test_previous_and_next_context_passed_to_prompt():
    """Le prompt doit porter la trace du contexte narratif (page précédente/suivante)."""
    captured = {}

    class CapturingLLM(LLMProvider):
        async def complete(self, system, user, *, json_mode=False, temperature=None, max_tokens=None):
            captured["user"] = user
            return "bla bla"

    next_slide = _slide("contenu de la page suivante")
    await generate_slide_script(
        CapturingLLM(), _section(), _slide(), 2, 3,
        previous_text="Nous avons vu l'introduction",
        next_slide=next_slide,
        target_words=None, tolerance=0.10, max_passes=2,
    )
    assert "Nous avons vu l'introduction" in captured["user"]
    assert "contenu de la page suivante" in captured["user"]


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
