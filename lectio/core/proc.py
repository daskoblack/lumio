"""Exécution async de commandes externes (ffmpeg/ffprobe), non bloquante."""

from __future__ import annotations

import asyncio

from .exceptions import RenderError


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
