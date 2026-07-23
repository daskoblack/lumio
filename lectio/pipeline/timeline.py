"""Construction de la timeline vidéo — logique PURE, aucune I/O (testable seule).

Règle d'or : ne lit QUE `actual_duration_s` (mesurée post-TTS). Les durées
cible/estimée n'ont servi qu'à contraindre la génération du texte en amont ;
elles n'apparaissent jamais ici.

Si une section a plusieurs slides, sa durée réelle est répartie également
entre elles (limite MVP documentée : pas de synchronisation fine avec le
contenu de la narration).
"""

from __future__ import annotations

from ..core.exceptions import InvalidStateError
from ..core.models import Course
from ..providers.video.base import TimelineEntry


def build_timeline(course: Course) -> list[TimelineEntry]:
    entries: list[TimelineEntry] = []
    cursor = 0.0

    for section in sorted(course.sections, key=lambda s: s.index):
        if section.actual_duration_s is None:
            raise InvalidStateError(
                f"Section {section.index} sans durée réelle : "
                "lance 'synthesize' avant de construire la timeline."
            )
        slide_ids = section.slide_ids or [None]  # section sans slide -> un segment virtuel
        n = len(slide_ids)
        per_slide = section.actual_duration_s / n

        for i, slide_id in enumerate(slide_ids):
            slide = course.slide_by_id(slide_id) if slide_id else None
            if slide is None or not slide.rendered_path:
                raise InvalidStateError(
                    f"Slide {slide_id!r} (section {section.index}) non rendue : "
                    "lance le rendu des slides avant la timeline."
                )
            start = cursor
            end = cursor + per_slide
            entries.append(
                TimelineEntry(
                    section_id=section.id,
                    slide_id=slide.id,
                    image_path=slide.rendered_path,
                    audio_path=section.script.audio_path if i == 0 else None,
                    start_s=start,
                    end_s=end,
                )
            )
            cursor = end

    return entries
