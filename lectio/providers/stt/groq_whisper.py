"""Implémentation STTProvider via l'API Whisper de Groq (whisper-large-v3-turbo).

Utilise le même client/clé que le LLM (GROQ_API_KEY) : aucune dépendance
supplémentaire. `response_format="verbose_json"` + `timestamp_granularities=
["word"]` donnent les timestamps mot-à-mot nécessaires aux sous-titres.
"""

from __future__ import annotations

from pathlib import Path

from ...core.exceptions import STTError
from .base import STTProvider, WordTiming


class GroqWhisperSTT(STTProvider):
    def __init__(self, api_key: str, model: str) -> None:
        try:
            from groq import AsyncGroq
        except ImportError as exc:  # pragma: no cover
            raise STTError("Le paquet 'groq' est requis (pip install groq).") from exc

        if not api_key:
            raise STTError("Clé API Groq absente. Définis la variable GROQ_API_KEY.")

        self._client = AsyncGroq(api_key=api_key)
        self._model = model

    async def transcribe_words(self, audio_path: str, language: str) -> list[WordTiming]:
        path = Path(audio_path)
        try:
            with path.open("rb") as f:
                resp = await self._client.audio.transcriptions.create(
                    model=self._model,
                    file=(path.name, f.read()),
                    language=language,
                    response_format="verbose_json",
                    timestamp_granularities=["word"],
                )
        except Exception as exc:  # noqa: BLE001
            raise STTError(f"Transcription Groq échouée : {exc}") from exc

        words = getattr(resp, "words", None) or []
        return [
            WordTiming(word=str(w["word"]), start_s=float(w["start"]), end_s=float(w["end"]))
            for w in words
        ]
