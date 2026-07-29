"""Implémentation Groq de LLMProvider (API compatible OpenAI, client async).

Tier gratuit : 100 000 tokens/JOUR (plafond vite atteint sur un cours long).
Quand ce plafond tombe, `_retry.call_with_retry` lève QuotaExhaustedError et
la `LLMChain` bascule vers le fournisseur suivant, au lieu de faire échouer
toute la génération de la vidéo.
"""

from __future__ import annotations

from ...core.exceptions import LLMError
from ...core.rate_limiter import RateLimiter
from ._retry import call_with_retry
from .base import LLMProvider


class GroqLLM(LLMProvider):
    """Fournisseur LLM basé sur Groq (gratuit, très rapide)."""

    label = "Groq"

    def __init__(
        self, api_key: str, model: str, temperature: float = 0.4, min_interval_s: float = 2.0
    ) -> None:
        try:
            from groq import AsyncGroq
        except ImportError as exc:  # pragma: no cover
            raise LLMError("Le paquet 'groq' est requis (pip install groq).") from exc

        if not api_key:
            raise LLMError("Clé API Groq absente. Définis la variable GROQ_API_KEY.")

        self._client = AsyncGroq(api_key=api_key)
        self._model = model
        self._temperature = temperature
        self._rate_limiter = RateLimiter(min_interval_s)

    async def complete(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        kwargs: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self._temperature if temperature is None else temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        resp = await call_with_retry(
            lambda: self._client.chat.completions.create(**kwargs),
            self._rate_limiter,
            f"{self.label} ({self._model})",
        )

        content = resp.choices[0].message.content  # type: ignore[union-attr]
        if not content:
            raise LLMError("Réponse vide du modèle Groq.")
        return content
