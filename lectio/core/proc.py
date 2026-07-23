"""Exécution async de commandes externes (ffmpeg/ffprobe), non bloquante."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from .exceptions import RenderError


def resolve_binary(name: str) -> str:
    """Résout le chemin d'un binaire externe (ffmpeg/ffprobe).

    Dans l'app packagée (PyInstaller), le binaire est fourni à côté du
    bundle (sys._MEIPASS/bin/) : le père de l'utilisateur n'a pas ffmpeg
    installé. En développement (CLI), on compte simplement sur le PATH.
    """
    if getattr(sys, "frozen", False):
        exe_name = f"{name}.exe" if sys.platform == "win32" else name
        bundled = Path(getattr(sys, "_MEIPASS", "")) / "bin" / exe_name
        if bundled.exists():
            return str(bundled)
    return name


async def run(cmd: list[str]) -> str:
    """Exécute une commande et retourne stdout. Lève RenderError si le code != 0."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        detail = stderr.decode(errors="replace").strip()[-2000:]
        raise RenderError(f"Commande échouée ({cmd[0]}) : {detail}")
    return stdout.decode(errors="replace")
