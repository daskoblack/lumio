"""Mesure de la durée réelle d'un fichier audio/vidéo via ffprobe.

C'est l'autorité finale de durée dans tout le pipeline : la timeline (phase 4)
ne se fie qu'à cette mesure, jamais aux estimations pré-TTS.
"""

from __future__ import annotations

import json

from .proc import run


async def measure_duration_s(media_path: str) -> float:
    """Retourne la durée réelle du média en secondes (précision ffprobe)."""
    stdout = await run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            media_path,
        ]
    )
    data = json.loads(stdout)
    return float(data["format"]["duration"])
