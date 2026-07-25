"""Fabrique de LLMProvider à partir de la config (permet de router vers un autre
fournisseur sans changer le code appelant)."""

from __future__ import annotations

from ...core.config import Config
from ...core.exceptions import LLMError
from .base import LLMProvider


def build_llm(config: Config) -> LLMProvider:
    name = config.providers.llm.name.lower()
    if name == "groq":
        from .groq_provider import GroqLLM

        return GroqLLM(
            api_key=Config.groq_api_key() or "",
            model=config.providers.llm.model,
            temperature=config.providers.llm.temperature,
            min_interval_s=config.providers.llm.min_interval_s,
        )
    if name == "cerebras":
        from .cerebras_provider import CerebrasLLM

        return CerebrasLLM(
            api_key=Config.cerebras_api_key() or "",
            model=config.providers.llm.model,
            temperature=config.providers.llm.temperature,
            min_interval_s=config.providers.llm.min_interval_s,
        )
    raise LLMError(f"Fournisseur LLM inconnu : {name!r}")
