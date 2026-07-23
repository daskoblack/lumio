"""Implémentation Groq de LLMProvider (API compatible OpenAI, client async).

Un `RateLimiter` espace les appels (défaut 2s) pour éviter les 429 de rate
limit Groq (le tier gratuit a un plafond de tokens/minute assez bas). En
filet de sécurité, un 429 déclenche UNE nouvelle tentative après le délai
indiqué par l'API (« Please try again in Xs »), pas de boucle infinie.
"""

from __future__ import annotations

import asyncio
import re

from ...core.exceptions import LLMError
from ...core.rate_limiter import RateLimiter
from .base import LLMProvider

_RETRY_AFTER_RE = re.compile(r"try again in (\d+(?:\.\d+)?)s", re.IGNORECASE)


class GroqLLM(LLMProvider):
    """Fournisseur LLM basé sur Groq (gratuit, rapide)."""

    def __init__(
        self, api_key: str, model: str, temperature: float = 0.4, min_interval_s: float = 2.0
    ) -> None:
        try:
            from groq import AsyncGroq
        except ImportError as exc:  # pragma: no cover
            raise LLMError(
                "Le paquet 'groq' est requis (pip install groq)."
            ) from exc

        if not api_key:
            raise LLMError(
                "Clé API Groq absente. Définis la variable GROQ_API_KEY."
            )

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

        await self._rate_limiter.acquire()
        try:
            resp = await self._client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            retry_after = _RETRY_AFTER_RE.search(str(exc))
            if "429" not in str(exc) or not retry_after:
                raise LLMError(f"Appel Groq échoué : {exc}") from exc
            # Retry unique, après le délai indiqué par l'API.
            await asyncio.sleep(float(retry_after.group(1)) + 0.5)
            await self._rate_limiter.acquire()
            try:
                resp = await self._client.chat.completions.create(**kwargs)
            except Exception as exc2:  # noqa: BLE001
                raise LLMError(f"Appel Groq échoué (après retry) : {exc2}") from exc2

        content = resp.choices[0].message.content
        if not content:
            raise LLMError("Réponse vide du modèle Groq.")
        return content
