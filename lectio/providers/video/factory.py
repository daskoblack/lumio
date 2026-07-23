"""Fabrique de VideoEngine (un seul fournisseur pour l'instant : FFmpeg)."""

from __future__ import annotations

from .base import VideoEngine


def build_video_engine() -> VideoEngine:
    from .ffmpeg_engine import FFmpegVideoEngine

    return FFmpegVideoEngine()
