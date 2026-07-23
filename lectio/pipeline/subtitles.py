"""Génération des sous-titres (SRT) à partir de la transcription Whisper.

On transcrit l'audio de chaque SLIDE (déjà généré en phase 3, une page = un
audio), puis on décale les timestamps par le décalage cumulé dans la vidéo
finale (même ordre que la timeline, qui repose sur `actual_duration_s`).
Les mots sont regroupés en captions selon des conventions standard de
sous-titrage (nombre de mots / caractères par ligne), configurables mais
sans lien avec la durée pédagogique des sections.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from ..core.config import SubtitlesConfig
from ..core.models import Course
from ..core.proc import resolve_binary, run
from ..providers.stt.base import STTProvider, WordTiming


def _format_timestamp(seconds: float) -> str:
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _group_into_captions(
    words: list[WordTiming], config: SubtitlesConfig
) -> list[tuple[float, float, str]]:
    """Regroupe les mots en captions (start_s, end_s, texte)."""
    captions: list[tuple[float, float, str]] = []
    max_chars = config.max_chars_per_line * config.max_lines

    current: list[WordTiming] = []
    for w in words:
        candidate_text = " ".join(x.word for x in current + [w])
        would_overflow = (
            len(current) >= config.max_words_per_caption or len(candidate_text) > max_chars
        )
        if would_overflow and current:
            captions.append((current[0].start_s, current[-1].end_s, " ".join(x.word for x in current)))
            current = [w]
        else:
            current.append(w)
    if current:
        captions.append((current[0].start_s, current[-1].end_s, " ".join(x.word for x in current)))
    return captions


async def generate_srt(
    stt: STTProvider, course: Course, config: SubtitlesConfig, out_path: Path
) -> str:
    """Transcrit chaque slide, construit le SRT complet, l'écrit sur disque."""
    entries: list[str] = []
    index = 1
    cursor = 0.0

    for section in sorted(course.sections, key=lambda s: s.index):
        for slide in course.section_slides(section):
            if slide.actual_duration_s is None or not slide.script or not slide.script.audio_path:
                continue

            words = await stt.transcribe_words(slide.script.audio_path, course.language)
            for start, end, text in _group_into_captions(words, config):
                wrapped = "\n".join(
                    textwrap.wrap(text, width=config.max_chars_per_line)[: config.max_lines]
                )
                entries.append(
                    f"{index}\n"
                    f"{_format_timestamp(cursor + start)} --> {_format_timestamp(cursor + end)}\n"
                    f"{wrapped}\n"
                )
                index += 1

            cursor += slide.actual_duration_s

    srt_content = "\n".join(entries)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(srt_content, encoding="utf-8")
    return str(out_path)


async def mux_subtitles(video_path: str, srt_path: str, out_path: str) -> str:
    """Incruste les sous-titres en piste souple (mov_text) : pas de ré-encodage vidéo."""
    await run(
        [
            resolve_binary("ffmpeg"), "-y",
            "-i", video_path,
            "-i", srt_path,
            "-map", "0", "-map", "1",
            "-c", "copy", "-c:s", "mov_text",
            out_path,
        ]
    )
    return out_path
