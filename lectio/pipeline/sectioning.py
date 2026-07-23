"""Découpage : transforme la structure LLM en objets Section + calcule les durées.

Transformation pure (pas d'I/O réseau) : associe les pages aux slides, mappe
les `kind`, et calcule `estimated_duration_s = mots estimés / débit`.
Aucune durée arbitraire : tout vient de l'estimation LLM et du débit configuré.
"""

from __future__ import annotations

from ..core.models import Section, SectionKind, Slide
from ..core.timing import words_to_duration

_VALID_KINDS = {k.value for k in SectionKind}


def build_sections(
    structure: dict, slides: list[Slide], speech_rate_wps: float
) -> list[Section]:
    """Construit les sections à partir de la sortie d'analyse."""
    # Index page -> id de slide (les slides sont générées une par page).
    page_to_slide = {slide.source_page: slide.id for slide in slides}

    sections: list[Section] = []
    for index, raw in enumerate(structure.get("sections", [])):
        kind_value = str(raw.get("kind", "other")).lower()
        kind = SectionKind(kind_value) if kind_value in _VALID_KINDS else SectionKind.OTHER

        slide_ids = [
            page_to_slide[p]
            for p in raw.get("source_pages", [])
            if p in page_to_slide
        ]

        words = int(raw.get("estimated_narration_words", 0) or 0)
        estimated_duration = words_to_duration(words, speech_rate_wps) if words else 0.0

        sections.append(
            Section(
                index=index,
                kind=kind,
                title=str(raw.get("title", f"Section {index + 1}")),
                summary=str(raw.get("summary", "")),
                slide_ids=slide_ids,
                estimated_narration_words=words,
                estimated_duration_s=estimated_duration,
            )
        )
    return sections
