"""Fabrique de LLMProvider : assemble la chaîne de repli à partir de la config.

Le reste de l'app ne voit qu'un seul `LLMProvider` ; qu'il y ait un ou quatre
fournisseurs derrière est un détail d'implémentation de cette fabrique.
"""

from __future__ import annotations

from ...core.config import Config, LLMCandidate
from ...core.exceptions import LLMError
from .base import LLMProvider
from .chain import LLMChain


def _build_one(name: str, model: str, temperature: float, min_interval_s: float) -> LLMProvider:
    """Construit un fournisseur unique. Lève LLMError si clé absente/inconnue."""
    key = Config.api_key_for(name) or ""
    lowered = name.lower()

    if lowered == "groq":
        from .groq_provider import GroqLLM

        return GroqLLM(key, model, temperature, min_interval_s)
    if lowered == "cerebras":
        from .cerebras_provider import CerebrasLLM

        return CerebrasLLM(key, model, temperature, min_interval_s)
    if lowered == "gemini":
        from .gemini_provider import GeminiLLM

        return GeminiLLM(key, model, temperature, min_interval_s)
    if lowered == "mistral":
        from .mistral_provider import MistralLLM

        return MistralLLM(key, model, temperature, min_interval_s)
    raise LLMError(f"Fournisseur LLM inconnu : {name!r}")


def build_llm(config: Config) -> LLMProvider:
    """Chaîne : fournisseur principal, puis replis dont la clé est renseignée.

    Un candidat sans clé API est simplement ignoré (pas d'erreur) : l'utilisateur
    n'a pas à créer quatre comptes pour que l'app fonctionne. S'il n'en renseigne
    qu'une seule, le comportement est identique à avant.
    """
    llm_config = config.providers.llm
    wanted: list[LLMCandidate] = [
        LLMCandidate(
            name=llm_config.name,
            model=llm_config.model,
            min_interval_s=llm_config.min_interval_s,
        ),
        *llm_config.fallbacks,
    ]

    candidates: list[tuple[str, LLMProvider]] = []
    seen: set[tuple[str, str]] = set()
    for candidate in wanted:
        signature = (candidate.name.lower(), candidate.model)
        if signature in seen:
            continue
        seen.add(signature)
        if not Config.api_key_for(candidate.name):
            continue  # pas de clé pour ce fournisseur : maillon simplement absent
        try:
            provider = _build_one(
                candidate.name, candidate.model, llm_config.temperature, candidate.min_interval_s
            )
        except LLMError:
            continue  # paquet manquant ou fournisseur inconnu : on ignore ce maillon
        candidates.append((f"{candidate.name}/{candidate.model}", provider))

    return LLMChain(candidates)
