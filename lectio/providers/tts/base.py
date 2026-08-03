"""Interface abstraite du fournisseur TTS + profil de voix.

Défini dès la phase 0 pour figer le contrat. L'implémentation (Groq PlayAI,
ElevenLabs, OpenAI...) arrive en phase 3. Le VoiceProfile porte le débit
calibré : c'est lui qui relie mots <-> durée de façon fiable dans le temps.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class VoiceProfile(BaseModel):
    """Profil de voix avec débit calibré (mots/s) mis à jour après chaque TTS.

    `id` identifie le profil pour la persistance (calibration inter-jobs) ;
    `voice_id` est l'identifiant spécifique au fournisseur TTS (ex. le nom de
    voix edge-tts "fr-FR-DeniseNeural").
    """

    id: str = "default"
    voice_id: str = "fr-FR-DeniseNeural"
    speech_rate_wps: float = 2.3
    calibration_samples: int = 0  # nb de mesures ayant servi à la calibration

    def recalibrate(self, words: int, duration_s: float) -> None:
        """Met à jour le débit par moyenne glissante à partir d'une mesure réelle."""
        if duration_s <= 0:
            return
        observed = words / duration_s
        n = self.calibration_samples
        self.speech_rate_wps = (self.speech_rate_wps * n + observed) / (n + 1)
        self.calibration_samples = n + 1


class TTSResult(BaseModel):
    audio_path: str
    duration_s: float
    word_count: int
    # Message à remonter à l'utilisateur sans faire échouer la synthèse
    # (ex. voix demandée absente du catalogue, remplacée automatiquement).
    warning: str | None = None


class TTSProvider(ABC):
    """Fournisseur de synthèse vocale (async)."""

    @abstractmethod
    async def synthesize(self, text: str, voice: VoiceProfile, out_path: str) -> TTSResult:
        """Synthétise `text` vers un fichier audio et retourne sa durée réelle."""
        raise NotImplementedError
