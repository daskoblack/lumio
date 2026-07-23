"""Fabrique de STTProvider à partir de la config."""

from __future__ import annotations

from ...core.config import Config
from ...core.exceptions import STTError
from .base import STTProvider


def build_stt(config: Config) -> STTProvider:
    name = config.providers.stt.name.lower()
    if name == "groq":
        from .groq_whisper import GroqWhisperSTT

        return GroqWhisperSTT(
            api_key=Config.groq_api_key() or "",
            model=config.providers.stt.model,
            min_interval_s=config.providers.stt.min_interval_s,
        )
    raise STTError(f"Fournisseur STT inconnu : {name!r}")
