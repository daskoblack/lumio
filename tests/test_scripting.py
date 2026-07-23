"""Tests du budget de mots et de la boucle de correction (LLM simulé)."""

import pytest

from lectio.core.models import Section, SectionKind
from lectio.pipeline.scripting import generate_script
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


def _section(target=None):
    return Section(index=0, kind=SectionKind.CONCEPT, title="T", target_duration_s=target)


@pytest.mark.asyncio
async def test_no_target_generates_once_without_budget():
    llm = FakeLLM([50])
    script = await generate_script(llm, _section(), "source", 2.0, 0.10, 2)
    assert script.word_count_target is None
    assert script.generation_pass == 1
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_target_within_tolerance_no_correction():
    # cible 60s * 2 wps = 120 mots ; on génère 118 -> dans ±10%, pas de correction
    llm = FakeLLM([118])
    script = await generate_script(llm, _section(target=60), "source", 2.0, 0.10, 2)
    assert script.word_count_target == 120
    assert script.generation_pass == 1
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_target_out_of_tolerance_triggers_single_correction():
    # cible 120 mots ; 1re passe 60 mots (hors ±10%) -> correction unique -> 122 mots
    llm = FakeLLM([60, 122])
    script = await generate_script(llm, _section(target=60), "source", 2.0, 0.10, 2)
    assert script.generation_pass == 2
    assert script.word_count_actual == 122
    assert llm.calls == 2


@pytest.mark.asyncio
async def test_correction_is_bounded_to_one_pass():
    # même si la 2e passe reste hors cible, on ne relance pas (boucle bornée)
    llm = FakeLLM([60, 70])
    script = await generate_script(llm, _section(target=60), "source", 2.0, 0.10, 2)
    assert script.generation_pass == 2
    assert llm.calls == 2  # jamais 3
