"""Implémentation TTSProvider via edge-tts (gratuit, sans clé, voix FR neurales).

Groq (PlayAI) ne propose pas de voix française à ce jour : edge-tts est donc
le fournisseur par défaut. Interface identique, changeable via la config sans
toucher au reste du pipeline.

Deux pièges d'edge-tts vérifiés en conditions réelles, gardés ici :
- un texte sans lettre ni chiffre (« ... ») échoue avec « No audio was
  received », message qui n'aide en rien à comprendre la cause ;
- un texte vide ne lève AUCUNE erreur mais écrit un fichier de 0 octet, dont
  l'échec ne se manifeste que bien plus loin, à la mesure de durée (« Failed
  to find two consecutive MPEG audio frames »).
"""

from __future__ import annotations

from pathlib import Path

from ...core.exceptions import TTSError
from ...core.ffprobe import measure_duration_s
from ...core.textutil import is_pronounceable
from ...core.timing import count_words
from .base import TTSProvider, TTSResult, VoiceProfile


class EdgeTTS(TTSProvider):
    async def synthesize(self, text: str, voice: VoiceProfile, out_path: str) -> TTSResult:
        try:
            import edge_tts
        except ImportError as exc:  # pragma: no cover
            raise TTSError("Le paquet 'edge-tts' est requis (pip install edge-tts).") from exc

        if not is_pronounceable(text):
            raise TTSError(
                "Rien à prononcer sur cette page : le texte à lire ne contient "
                f"ni lettre ni chiffre ({text.strip()[:40]!r})."
            )

        try:
            communicate = edge_tts.Communicate(text, voice=voice.voice_id)
            await communicate.save(out_path)
        except Exception as exc:  # noqa: BLE001
            raise TTSError(
                f"Synthèse vocale échouée avec la voix {voice.voice_id} : {exc}"
            ) from exc

        produced = Path(out_path)
        if not produced.exists() or produced.stat().st_size == 0:
            raise TTSError(
                f"La voix {voice.voice_id} n'a produit aucun son. "
                "Vérifie ta connexion internet, ou change de voix dans les Réglages."
            )

        duration = await measure_duration_s(out_path)
        return TTSResult(audio_path=out_path, duration_s=duration, word_count=count_words(text))
