"""Tests du découpage : mapping pages->slides et calcul de durée estimée."""

from lectio.core.models import Slide
from lectio.core.timing import words_to_duration
from lectio.pipeline.sectioning import build_sections


def test_build_sections_maps_slides_and_durations():
    slides = [
        Slide(index=0, source_page=1, title="P1"),
        Slide(index=1, source_page=2, title="P2"),
    ]
    structure = {
        "sections": [
            {
                "title": "Intro",
                "kind": "intro",
                "summary": "présentation",
                "source_pages": [1],
                "estimated_narration_words": 92,
            },
            {
                "title": "Concept",
                "kind": "concept",
                "summary": "le cœur",
                "source_pages": [2],
                "estimated_narration_words": 230,
            },
        ]
    }
    sections = build_sections(structure, slides, speech_rate_wps=2.3)

    assert len(sections) == 2
    assert sections[0].kind.value == "intro"
    assert sections[0].slide_ids == [slides[0].id]
    assert sections[1].estimated_duration_s == words_to_duration(230, 2.3)
    # Pas de durée cible tant que l'utilisateur n'en fixe pas.
    assert all(s.target_duration_s is None for s in sections)


def test_unknown_kind_falls_back_to_other():
    slides = [Slide(index=0, source_page=1, title="P1")]
    structure = {"sections": [{"title": "X", "kind": "bizarre", "source_pages": [1]}]}
    sections = build_sections(structure, slides, 2.3)
    assert sections[0].kind.value == "other"
