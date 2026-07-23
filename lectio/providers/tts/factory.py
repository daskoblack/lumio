"""Fabrique de TTSProvider à partir de la config."""

from __future__ import annotations

from ...core.config import Config
from ...core.exceptions import TTSError
from .base import TTSProvider


def build_tts(config: Config) -> TTSProvider:
    name = config.providers.tts.name.lower()
    if name == "edge":
        from .edge_provider import EdgeTTS

        return EdgeTTS()
    raise TTSError(f"Fournisseur TTS inconnu : {name!r}")
