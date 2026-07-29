"""Implémentation Mistral de LLMProvider (REST direct via httpx).

Pas de SDK dédié : l'API Mistral est compatible OpenAI et httpx est déjà une
dépendance transitive. Ça évite d'alourdir le paquet distribué (l'app est
déjà à ~90 Mo compressés) pour trois appels HTTP.
"""

from __future__ import annotations

import httpx

from ...core.exceptions import LLMError
from ...core.rate_limiter import RateLimiter
from ._retry import call_with_retry
from .base import LLMProvider

_ENDPOINT = "https://api.mistral.ai/v1/chat/completions"


class MistralLLM(LLMProvider):
    """Fournisseur LLM basé sur Mistral (tier gratuit « Experiment »)."""

    label = "Mistral"

    def __init__(
        self, api_key: str, model: str, temperature: float = 0.4, min_interval_s: float = 2.0
    ) -> None:
        if not api_key:
            raise LLMError("Clé API Mistral absente. Définis la variable MISTRAL_API_KEY.")

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
        payload: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self._temperature if temperature is None else temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        async def _call() -> dict:
            resp = await self._client.post(
                _ENDPOINT,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
            if resp.status_code >= 400:
                # Le code ET le corps doivent apparaître dans le message : c'est
                # ce texte qu'inspecte `errors.is_quota_exhausted`.
                raise RuntimeError(f"HTTP {resp.status_code} : {resp.text[:500]}")
            return resp.json()

        data = await call_with_retry(
            _call, self._rate_limiter, f"{self.label} ({self._model})"
        )

        try:
            content = data["choices"][0]["message"]["content"]  # type: ignore[index]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Réponse Mistral inattendue : {data}") from exc
        if not content:
            raise LLMError("Réponse vide du modèle Mistral.")
        return content
