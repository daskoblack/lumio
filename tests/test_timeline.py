"""Tests de la timeline : logique pure, ne doit lire que actual_duration_s."""

import pytest

from lectio.core.exceptions import InvalidStateError
from lectio.core.models import Course, Script, Section, SectionKind, Slide
from lectio.pipeline.timeline import build_timeline


def _course_with_one_slide_sections() -> Course:
    slides = [
        Slide(index=0, source_page=1, title="P1", rendered_path="p1.png"),
        Slide(index=1, source_page=2, title="P2", rendered_path="p2.png"),
    ]
    sections = [
        Section(
            index=0, kind=SectionKind.INTRO, title="Intro", slide_ids=[slides[0].id],
            actual_duration_s=10.0, script=Script(section_id="", audio_path="a0.mp3"),
        ),
        Section(
            index=1, kind=SectionKind.CONCEPT, title="Concept", slide_ids=[slides[1].id],
            actual_duration_s=20.0, script=Script(section_id="", audio_path="a1.mp3"),
        ),
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
    # audio_path set on first entry of each section
    assert entries[0].audio_path == "a0.mp3"
    assert entries[1].audio_path == "a1.mp3"


def test_build_timeline_splits_duration_across_multiple_slides():
    slides = [
        Slide(index=0, source_page=1, title="P1", rendered_path="p1.png"),
        Slide(index=1, source_page=2, title="P2", rendered_path="p2.png"),
    ]
    section = Section(
        index=0, kind=SectionKind.CONCEPT, title="C",
        slide_ids=[slides[0].id, slides[1].id],
        actual_duration_s=10.0, script=Script(section_id="", audio_path="a0.mp3"),
    )
    course = Course(title="T", source_pdf="x.pdf", slides=slides, sections=[section])

    entries = build_timeline(course)
    assert len(entries) == 2
    assert entries[0].duration_s == pytest.approx(5.0)
    assert entries[1].duration_s == pytest.approx(5.0)
    # only the first slide of the section carries the audio_path
    assert entries[0].audio_path == "a0.mp3"
    assert entries[1].audio_path is None


def test_build_timeline_requires_actual_duration():
    course = _course_with_one_slide_sections()
    course.sections[0].actual_duration_s = None
    with pytest.raises(InvalidStateError):
        build_timeline(course)


def test_build_timeline_requires_rendered_slide():
    course = _course_with_one_slide_sections()
    course.slides[0].rendered_path = None
    with pytest.raises(InvalidStateError):
        build_timeline(course)
