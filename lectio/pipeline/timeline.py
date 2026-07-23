"""Construction de la timeline vidéo — logique PURE, aucune I/O (testable seule).

Règle d'or : ne lit QUE `actual_duration_s` (mesurée post-TTS). Les durées
cible/estimée n'ont servi qu'à contraindre la génération du texte en amont ;
elles n'apparaissent jamais ici.

Chaque slide a désormais son propre audio (phase 3) : la timeline est une
simple concaténation 1:1, sans découpage artificiel du temps au sein d'une
section — la synchro image/narration est garantie par construction.
"""

from __future__ import annotations

from ..core.exceptions import InvalidStateError
from ..core.models import Course
from ..providers.video.base import TimelineEntry


def build_timeline(course: Course) -> list[TimelineEntry]:
    entries: list[TimelineEntry] = []
    cursor = 0.0

    for section in sorted(course.sections, key=lambda s: s.index):
        for slide in course.section_slides(section):
            if slide.actual_duration_s is None:
                raise InvalidStateError(
                    f"Page {slide.source_page} (section {section.index}) sans durée réelle : "
                    "lance 'synthesize' avant de construire la timeline."
                )
            if not slide.rendered_path:
                raise InvalidStateError(
                    f"Page {slide.source_page} non rendue : lance le rendu des slides "
                    "avant la timeline."
                )
            if not slide.script or not slide.script.audio_path:
                raise InvalidStateError(
                    f"Page {slide.source_page} sans audio : lance 'synthesize' avant "
                    "la timeline."
                )

            start = cursor
            end = cursor + slide.actual_duration_s
            entries.append(
                TimelineEntry(
                    section_id=section.id,
                    slide_id=slide.id,
                    image_path=slide.rendered_path,
                    audio_path=slide.script.audio_path,
                    start_s=start,
                    end_s=end,
                )
            )
            cursor = end

    return entries
