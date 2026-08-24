"""Tests de la chaîne de repli LLM et de la détection de quota épuisé."""

import os

import pytest

from lectio.core.config import Config
from lectio.core.exceptions import LLMError
from lectio.providers.llm.base import LLMProvider
from lectio.providers.llm.chain import LLMChain
from lectio.providers.llm.errors import (
    QuotaExhaustedError,
    is_auth_error,
    is_quota_exhausted,
    retry_delay_s,
)
from lectio.providers.llm.factory import build_llm


# --- Détection : « attends 8s » vs « reviens demain » -------------------------

def test_short_rate_limit_is_not_exhaustion():
    message = "Error code: 429 - Rate limit reached ... Please try again in 8.085s"
    assert retry_delay_s(message) == pytest.approx(8.085)
    assert not is_quota_exhausted(message)


def test_daily_token_limit_is_exhaustion():
    message = (
        "Error code: 429 - Rate limit reached for model `llama-3.3-70b-versatile` "
        "on tokens per day (TPD): Limit 100000, Used 99544. "
        "Please try again in 2m21.696s"
    )
    assert retry_delay_s(message) == pytest.approx(141.696)
    assert is_quota_exhausted(message)


def test_gemini_resource_exhausted_is_exhaustion():
    assert is_quota_exhausted("HTTP 429 : {'status': 'RESOURCE_EXHAUSTED'}")


def test_invalid_key_is_auth_error():
    assert is_auth_error("HTTP 401 : Invalid API key")
    assert not is_auth_error("HTTP 500 : internal error")


# --- Chaîne de repli ----------------------------------------------------------

class _FakeLLM(LLMProvider):
    def __init__(self, name: str, fail_with: Exception | None = None) -> None:
        self.name = name
        self.fail_with = fail_with
        self.calls = 0

    async def complete(self, system, user, *, json_mode=False, temperature=None, max_tokens=None):
        self.calls += 1
        if self.fail_with is not None:
            raise self.fail_with
        return f"réponse de {self.name}"


@pytest.mark.asyncio
async def test_chain_uses_first_available():
    first = _FakeLLM("A")
    second = _FakeLLM("B")
    chain = LLMChain([("A", first), ("B", second)])

    assert await chain.complete("s", "u") == "réponse de A"
    assert second.calls == 0  # le repli n'est pas sollicité inutilement


@pytest.mark.asyncio
async def test_chain_falls_back_when_quota_exhausted():
    first = _FakeLLM("A", fail_with=QuotaExhaustedError("quota du jour épuisé"))
    second = _FakeLLM("B")
    chain = LLMChain([("A", first), ("B", second)])

    assert await chain.complete("s", "u") == "réponse de B"
    assert second.calls == 1


@pytest.mark.asyncio
async def test_exhausted_provider_is_not_retried_on_next_call():
    first = _FakeLLM("A", fail_with=QuotaExhaustedError("quota du jour épuisé"))
    second = _FakeLLM("B")
    chain = LLMChain([("A", first), ("B", second)])

    await chain.complete("s", "u")
    await chain.complete("s", "u")
    await chain.complete("s", "u")

    assert first.calls == 1  # sollicité une seule fois, puis définitivement écarté
    assert second.calls == 3


@pytest.mark.asyncio
async def test_transient_error_tries_next_without_condemning():
    """Une erreur ponctuelle (réseau) ne doit pas écarter définitivement le candidat."""
    flaky = _FakeLLM("A", fail_with=LLMError("réseau instable"))
    backup = _FakeLLM("B")
    chain = LLMChain([("A", flaky), ("B", backup)])

    await chain.complete("s", "u")
    flaky.fail_with = None  # le réseau revient
    await chain.complete("s", "u")

    assert flaky.calls == 2  # re-tenté, contrairement à un quota épuisé


@pytest.mark.asyncio
async def test_all_exhausted_raises_clear_error():
    chain = LLMChain([
        ("A", _FakeLLM("A", fail_with=QuotaExhaustedError("épuisé"))),
        ("B", _FakeLLM("B", fail_with=QuotaExhaustedError("épuisé"))),
    ])
    with pytest.raises(LLMError, match="Tous les fournisseurs"):
        await chain.complete("s", "u")


def test_empty_chain_gives_actionable_message():
    with pytest.raises(LLMError, match="Réglages"):
        LLMChain([])


# --- Fabrique -----------------------------------------------------------------

def test_factory_skips_providers_without_api_key(monkeypatch):
    for var in ("GROQ_API_KEY", "CEREBRAS_API_KEY", "GEMINI_API_KEY", "MISTRAL_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")

    chain = build_llm(Config())
    assert isinstance(chain, LLMChain)
    # Seul Mistral a une clé : c'est le seul maillon retenu.
    assert chain.available_labels == ["mistral/mistral-small-latest"]


def test_factory_builds_full_chain_in_priority_order(monkeypatch):
    for var in ("GROQ_API_KEY", "CEREBRAS_API_KEY", "GEMINI_API_KEY", "MISTRAL_API_KEY"):
        monkeypatch.setenv(var, "test-key")

    chain = build_llm(Config())
    assert chain.available_labels == [
        "groq/openai/gpt-oss-120b",       # principal
        "groq/openai/gpt-oss-20b",        # même compte, modèle plus léger
        "cerebras/gpt-oss-120b",
        "gemini/gemini-2.5-flash-lite",
        "mistral/mistral-small-latest",
    ]


def test_factory_without_any_key_raises_actionable_error(monkeypatch):
    for var in ("GROQ_API_KEY", "CEREBRAS_API_KEY", "GEMINI_API_KEY", "MISTRAL_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(LLMError, match="Réglages"):
        build_llm(Config())
