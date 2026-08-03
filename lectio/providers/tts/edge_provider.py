"""Implémentation TTSProvider via edge-tts (gratuit, sans clé, voix FR neurales).

Groq (PlayAI) ne propose pas de voix française à ce jour : edge-tts est donc
le fournisseur par défaut. Interface identique, changeable via la config sans
toucher au reste du pipeline.

Trois pièges d'edge-tts vérifiés en conditions réelles, gardés ici — tous
remontent le même message inexploitable (« No audio was received ») :
- un texte sans lettre ni chiffre (« ... ») ;
- une voix qui n'existe pas / plus dans le catalogue Microsoft ;
- un texte vide, qui ne lève AUCUNE erreur mais écrit un fichier de 0 octet,
  dont l'échec ne se manifeste que bien plus loin, à la mesure de durée.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from ...core.exceptions import TTSError
from ...core.ffprobe import measure_duration_s
from ...core.textutil import is_pronounceable
from ...core.timing import count_words
from .base import TTSProvider, TTSResult, VoiceProfile

# Voix de repli si celle demandée n'existe plus dans le catalogue.
_DEFAULT_VOICE = "fr-FR-DeniseNeural"


class EdgeTTS(TTSProvider):
    def __init__(self) -> None:
        self._known_voices: set[str] | None = None
        self._voices_lock = asyncio.Lock()

    async def _catalogue(self) -> set[str] | None:
        """Noms de voix disponibles, chargés une seule fois.

        None si le catalogue est inaccessible (hors ligne) : on tente alors la
        voix demandée telle quelle plutôt que de bloquer inutilement.
        """
        if self._known_voices is not None:
            return self._known_voices
        async with self._voices_lock:
            if self._known_voices is None:
                try:
                    import edge_tts

                    voices = await edge_tts.list_voices()
                    self._known_voices = {v["ShortName"] for v in voices}
                except Exception:  # noqa: BLE001 - hors ligne : on n'empêche rien
                    return None
        return self._known_voices

    async def _resolve_voice(self, requested: str) -> tuple[str, str | None]:
        """Retourne (voix_utilisable, avertissement)."""
        catalogue = await self._catalogue()
        if catalogue is None or requested in catalogue:
            return requested, None

        # Même langue de préférence, sinon la voix française par défaut.
        prefix = requested.split("-")[0] if "-" in requested else "fr"
        same_language = sorted(v for v in catalogue if v.startswith(f"{prefix}-"))
        replacement = same_language[0] if same_language else _DEFAULT_VOICE
        return replacement, (
            f"La voix « {requested} » n'existe plus dans le catalogue : "
            f"« {replacement} » a été utilisée à la place. "
            "Choisis une nouvelle voix dans les Réglages."
        )

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

        voice_id, warning = await self._resolve_voice(voice.voice_id)

        try:
            communicate = edge_tts.Communicate(text, voice=voice_id)
            await communicate.save(out_path)
        except Exception as exc:  # noqa: BLE001
            detail = f" ({warning})" if warning else ""
            raise TTSError(
                f"Synthèse vocale échouée avec la voix {voice_id}{detail} : {exc}"
            ) from exc

        produced = Path(out_path)
        if not produced.exists() or produced.stat().st_size == 0:
            raise TTSError(
                f"La voix {voice_id} n'a produit aucun son. "
                "Vérifie ta connexion internet, ou change de voix dans les Réglages."
            )

        duration = await measure_duration_s(out_path)
        return TTSResult(
            audio_path=out_path,
            duration_s=duration,
            word_count=count_words(text),
            warning=warning,
        )
