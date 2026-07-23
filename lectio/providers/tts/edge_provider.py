"""Implémentation TTSProvider via edge-tts (gratuit, sans clé, voix FR neurales).

Groq (PlayAI) ne propose pas de voix française à ce jour : edge-tts est donc
le fournisseur par défaut. Interface identique, changeable via la config sans
toucher au reste du pipeline.
"""

from __future__ import annotations

from ...core.exceptions import TTSError
from ...core.ffprobe import measure_duration_s
from ...core.timing import count_words
from .base import TTSProvider, TTSResult, VoiceProfile


class EdgeTTS(TTSProvider):
    async def synthesize(self, text: str, voice: VoiceProfile, out_path: str) -> TTSResult:
        try:
            import edge_tts
        except ImportError as exc:  # pragma: no cover
            raise TTSError("Le paquet 'edge-tts' est requis (pip install edge-tts).") from exc

        try:
            communicate = edge_tts.Communicate(text, voice=voice.voice_id)
            await communicate.save(out_path)
        except Exception as exc:  # noqa: BLE001
            raise TTSError(f"Synthèse edge-tts échouée : {exc}") from exc

        duration = await measure_duration_s(out_path)
        return TTSResult(audio_path=out_path, duration_s=duration, word_count=count_words(text))
