"""Tests du découpage : mapping pages->slides et calcul de durée estimée."""

from lectio.core.models import ContentBlock, Slide
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


def test_word_budget_distributed_proportionally_across_slides():
    short_text = "un deux trois"  # 3 mots
    long_text = " ".join(["mot"] * 27)  # 27 mots -> poids 9x le premier
    slides = [
        Slide(index=0, source_page=1, title="P1", content_blocks=[ContentBlock(kind="text", text=short_text)]),
        Slide(index=1, source_page=2, title="P2", content_blocks=[ContentBlock(kind="text", text=long_text)]),
    ]
    structure = {
        "sections": [
            {
                "title": "Concept", "kind": "concept", "source_pages": [1, 2],
                "estimated_narration_words": 300,
            }
        ]
    }
    build_sections(structure, slides, speech_rate_wps=2.3)

    # 3 mots vs 27 mots -> poids 1/10 et 9/10 du budget de 300.
    assert slides[0].estimated_narration_words == 30
    assert slides[1].estimated_narration_words == 270
    # La somme des slides doit reconstituer exactement le budget de la section.
    assert slides[0].estimated_narration_words + slides[1].estimated_narration_words == 300
