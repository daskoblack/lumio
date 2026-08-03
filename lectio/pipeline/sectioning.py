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


def _repair_page_assignment(
    raw_sections: list[dict], known_pages: list[int]
) -> list[list[int]]:
    """Garantit que CHAQUE page du PDF apparaît exactement une fois, dans l'ordre.

    Le découpage vient d'un LLM : il lui arrive d'oublier une page, de la
    citer deux fois, ou d'inventer un numéro hors du document. Sans
    réparation, une page oubliée disparaît purement et simplement de la
    vidéo — silencieusement. On répare donc de façon déterministe :
    - numéros inconnus ou déjà pris : ignorés ;
    - pages jamais citées : rattachées à la section dont la plage encadre le
      mieux leur position (à défaut, la dernière section), puis remises en
      ordre croissant.
    """
    valid_pages = set(known_pages)
    assigned: list[list[int]] = []
    seen: set[int] = set()

    for raw in raw_sections:
        pages: list[int] = []
        for value in raw.get("source_pages", []) or []:
            try:
                page = int(value)
            except (TypeError, ValueError):
                continue
            if page in valid_pages and page not in seen:
                seen.add(page)
                pages.append(page)
        assigned.append(sorted(pages))

    if not assigned:  # aucune section exploitable : tout dans une seule
        return [sorted(valid_pages)]

    # Pages oubliées par le LLM : on les rattache à la section la plus plausible.
    for page in sorted(valid_pages - seen):
        target = len(assigned) - 1  # par défaut la dernière
        for index, pages in enumerate(assigned):
            if pages and page < pages[0]:
                # La page précède cette section : elle appartient à la
                # précédente non vide, sinon à celle-ci.
                target = next(
                    (i for i in range(index - 1, -1, -1) if assigned[i]), index
                )
                break
            if pages and pages[0] <= page <= pages[-1]:
                target = index
                break
            if pages:
                target = index
        assigned[target].append(page)

    return [sorted(pages) for pages in assigned]


def build_sections(
    structure: dict, slides: list[Slide], speech_rate_wps: float
) -> list[Section]:
    """Construit les sections à partir de la sortie d'analyse."""
    # Index page -> id de slide (les slides sont générées une par page).
    page_to_slide = {slide.source_page: slide.id for slide in slides}
    slide_by_id = {slide.id: slide for slide in slides}

    raw_sections = list(structure.get("sections", []) or [])
    pages_by_section = _repair_page_assignment(
        raw_sections, [slide.source_page for slide in slides]
    )
    if not raw_sections:  # secours : une section unique couvrant tout le document
        raw_sections = [{"title": "Cours", "kind": "other", "summary": ""}]

    sections: list[Section] = []
    for index, raw in enumerate(raw_sections):
        kind_value = str(raw.get("kind", "other")).lower()
        kind = SectionKind(kind_value) if kind_value in _VALID_KINDS else SectionKind.OTHER

        slide_ids = [page_to_slide[p] for p in pages_by_section[index]]

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
