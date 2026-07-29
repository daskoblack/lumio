"""Implémentation Google Gemini de LLMProvider (REST direct via httpx).

Comme pour Mistral : appel REST natif plutôt qu'un SDK, pour ne pas alourdir
le paquet distribué. Gemini a sa propre forme de requête (systemInstruction /
contents / generationConfig), d'où un provider distinct des fournisseurs
compatibles OpenAI.
"""

from __future__ import annotations

import httpx

from ...core.exceptions import LLMError
from ...core.rate_limiter import RateLimiter
from ._retry import call_with_retry
from .base import LLMProvider

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiLLM(LLMProvider):
    """Fournisseur LLM basé sur Google Gemini (tier gratuit via Google AI Studio)."""

    label = "Gemini"

    def __init__(
        self, api_key: str, model: str, temperature: float = 0.4, min_interval_s: float = 2.0
    ) -> None:
        if not api_key:
            raise LLMError("Clé API Gemini absente. Définis la variable GEMINI_API_KEY.")

        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._rate_limiter = RateLimiter(min_interval_s)
        self._client = httpx.AsyncClient(timeout=120.0)

    async def complete(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        generation_config: dict = {
            "temperature": self._temperature if temperature is None else temperature,
        }
        if json_mode:
            generation_config["responseMimeType"] = "application/json"
        if max_tokens is not None:
            generation_config["maxOutputTokens"] = max_tokens

        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": generation_config,
        }

        async def _call() -> dict:
            resp = await self._client.post(
                f"{_BASE}/{self._model}:generateContent",
                headers={"x-goog-api-key": self._api_key},
                json=payload,
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code} : {resp.text[:500]}")
            return resp.json()

        data = await call_with_retry(
            _call, self._rate_limiter, f"{self.label} ({self._model})"
        )

        try:
            parts = data["candidates"][0]["content"]["parts"]  # type: ignore[index]
            content = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Réponse Gemini inattendue : {data}") from exc
        if not content:
            raise LLMError("Réponse vide du modèle Gemini.")
        return content
