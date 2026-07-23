"""Interface abstraite du fournisseur de transcription (sous-titres).

Non demandée explicitement dans le brief initial, mais ajoutée par cohérence
avec le principe d'architecture modulaire (LLM/TTS/Video) : le moteur de
sous-titrage doit lui aussi être remplaçable sans toucher au pipeline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class WordTiming(BaseModel):
    """Un mot transcrit avec ses bornes temporelles, relatives au début du fichier audio."""

    word: str
    start_s: float
    end_s: float


class STTProvider(ABC):
    """Fournisseur de transcription avec timestamps mot-à-mot (async)."""

    @abstractmethod
    async def transcribe_words(self, audio_path: str, language: str) -> list[WordTiming]:
        """Transcrit l'audio et retourne les mots avec leurs timestamps."""
        raise NotImplementedError
