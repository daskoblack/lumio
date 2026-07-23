"""Découpage : transforme la structure LLM en objets Section + calcule les durées.

Transformation pure (pas d'I/O réseau) : associe les pages aux slides, mappe
les `kind`, et calcule les durées. Aucune durée arbitraire : tout vient de
l'estimation LLM et du débit configuré.

L'estimation LLM ne porte que sur la SECTION entière (pas de découpage par
page côté LLM, pour ne pas complexifier l'analyse). On répartit donc ce
budget entre les slides de la section au prorata de la longueur de leur
texte source respectif : c'est une approximation raisonnable de "combien il y
a à dire" sur chaque page, qui sert de point de départ à la génération
page par page (phase 2).
"""

from __future__ import annotations

from ..core.models import Section, SectionKind, Slide
from ..core.timing import count_words, words_to_duration

_VALID_KINDS = {k.value for k in SectionKind}


def build_sections(
    structure: dict, slides: list[Slide], speech_rate_wps: float
) -> list[Section]:
    """Construit les sections à partir de la sortie d'analyse."""
    # Index page -> id de slide (les slides sont générées une par page).
    page_to_slide = {slide.source_page: slide.id for slide in slides}
    slide_by_id = {slide.id: slide for slide in slides}

    sections: list[Section] = []
    for index, raw in enumerate(structure.get("sections", [])):
        kind_value = str(raw.get("kind", "other")).lower()
        kind = SectionKind(kind_value) if kind_value in _VALID_KINDS else SectionKind.OTHER

        slide_ids = [
            page_to_slide[p]
            for p in raw.get("source_pages", [])
            if p in page_to_slide
        ]

        section_words = int(raw.get("estimated_narration_words", 0) or 0)
        section_duration = words_to_duration(section_words, speech_rate_wps) if section_words else 0.0

        _distribute_words_across_slides(
            [slide_by_id[sid] for sid in slide_ids], section_words, speech_rate_wps
        )

        sections.append(
            Section(
                index=index,
                kind=kind,
                title=str(raw.get("title", f"Section {index + 1}")),
                summary=str(raw.get("summary", "")),
                slide_ids=slide_ids,
                estimated_narration_words=section_words,
                estimated_duration_s=section_duration,
            )
        )
    return sections


def _distribute_words_across_slides(
    slides: list[Slide], total_words: int, speech_rate_wps: float
) -> None:
    """Répartit le budget de mots d'une section entre ses slides (prorata du texte source)."""
    if not slides:
        return

    weights = [max(1, count_words(s.source_text())) for s in slides]
    total_weight = sum(weights)

    remaining = total_words
    for i, (slide, weight) in enumerate(zip(slides, weights)):
        if i == len(slides) - 1:
            share = remaining  # dernière slide : absorbe l'arrondi
        else:
            share = round(total_words * weight / total_weight)
            remaining -= share
        slide.estimated_narration_words = max(0, share)
        slide.estimated_duration_s = words_to_duration(slide.estimated_narration_words, speech_rate_wps) \
            if slide.estimated_narration_words else 0.0
