"""Implémentation Groq de LLMProvider (API compatible OpenAI, client async)."""

from __future__ import annotations

from ...core.exceptions import LLMError
from .base import LLMProvider


class GroqLLM(LLMProvider):
    """Fournisseur LLM basé sur Groq (gratuit, rapide)."""

    def __init__(self, api_key: str, model: str, temperature: float = 0.4) -> None:
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

        try:
            resp = await self._client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 - on remonte une erreur métier claire
            raise LLMError(f"Appel Groq échoué : {exc}") from exc

        content = resp.choices[0].message.content
        if not content:
            raise LLMError("Réponse vide du modèle Groq.")
        return content
