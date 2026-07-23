"""Tests de la timeline : logique pure, ne doit lire que actual_duration_s.

Chaque slide porte désormais son propre script/audio (synchro 1:1)."""

import pytest

from lectio.core.exceptions import InvalidStateError
from lectio.core.models import Course, Script, Section, SectionKind, Slide
from lectio.pipeline.timeline import build_timeline


def _slide(index, page, audio, duration, rendered=True):
    return Slide(
        index=index, source_page=page, title=f"P{page}",
        rendered_path=f"p{page}.png" if rendered else None,
        actual_duration_s=duration,
        script=Script(slide_id="", audio_path=audio, audio_duration_s=duration),
    )


def _course_with_one_slide_sections() -> Course:
    slides = [_slide(0, 1, "a0.mp3", 10.0), _slide(1, 2, "a1.mp3", 20.0)]
    sections = [
        Section(index=0, kind=SectionKind.INTRO, title="Intro", slide_ids=[slides[0].id]),
        Section(index=1, kind=SectionKind.CONCEPT, title="Concept", slide_ids=[slides[1].id]),
    ]
    return Course(title="T", source_pdf="x.pdf", slides=slides, sections=sections)


def test_build_timeline_cumulative_offsets():
    course = _course_with_one_slide_sections()
    entries = build_timeline(course)

    assert len(entries) == 2
    assert entries[0].start_s == 0.0
    assert entries[0].end_s == 10.0
    assert entries[1].start_s == 10.0
    assert entries[1].end_s == 30.0
    assert entries[0].audio_path == "a0.mp3"
    assert entries[1].audio_path == "a1.mp3"


def test_build_timeline_one_audio_per_slide_no_even_split():
    """Contrairement à l'ancien découpage égal : chaque slide garde SA durée réelle propre."""
    slides = [_slide(0, 1, "a0.mp3", 7.0), _slide(1, 2, "a1.mp3", 42.0)]
    section = Section(index=0, kind=SectionKind.CONCEPT, title="C", slide_ids=[slides[0].id, slides[1].id])
    course = Course(title="T", source_pdf="x.pdf", slides=slides, sections=[section])

    entries = build_timeline(course)
    assert len(entries) == 2
    assert entries[0].duration_s == pytest.approx(7.0)
    assert entries[1].duration_s == pytest.approx(42.0)
    assert entries[0].audio_path == "a0.mp3"
    assert entries[1].audio_path == "a1.mp3"  # chaque slide a bien SON propre audio


def test_build_timeline_requires_actual_duration():
    course = _course_with_one_slide_sections()
    course.slides[0].actual_duration_s = None
    with pytest.raises(InvalidStateError):
        build_timeline(course)


def test_build_timeline_requires_rendered_slide():
    course = _course_with_one_slide_sections()
    course.slides[0].rendered_path = None
    with pytest.raises(InvalidStateError):
        build_timeline(course)


def test_build_timeline_requires_audio():
    course = _course_with_one_slide_sections()
    course.slides[0].script.audio_path = None
    with pytest.raises(InvalidStateError):
        build_timeline(course)
