"""Tests de set_target_durations : fixation de durée cible sur plusieurs sections à la fois."""

import pytest

from lectio.core.config import Config
from lectio.core.exceptions import InvalidStateError
from lectio.core.models import Course, CourseStatus, Section, SectionKind
from lectio.jobs.orchestrator import Orchestrator


def _make_job(tmp_path) -> tuple[Orchestrator, str]:
    config = Config.load()
    config.paths.workspace = str(tmp_path / "workspace")
    orch = Orchestrator(config)

    course = Course(
        title="T", source_pdf="x.pdf", status=CourseStatus.ANALYZED,
        sections=[
            Section(index=0, kind=SectionKind.INTRO, title="A"),
            Section(index=1, kind=SectionKind.CONCEPT, title="B"),
            Section(index=2, kind=SectionKind.CONCEPT, title="C"),
        ],
    )
    orch.store.save(course)
    return orch, course.id


def test_set_target_durations_applies_to_all_listed_sections(tmp_path):
    orch, job_id = _make_job(tmp_path)
    sections = orch.set_target_durations(job_id, [0, 2], 90.0)

    assert {s.index for s in sections} == {0, 2}
    reloaded = orch.store.load(job_id)
    assert reloaded.section_by_index(0).target_duration_s == 90.0
    assert reloaded.section_by_index(1).target_duration_s is None  # non listée : inchangée
    assert reloaded.section_by_index(2).target_duration_s == 90.0


def test_set_target_durations_none_resets_to_auto(tmp_path):
    orch, job_id = _make_job(tmp_path)
    orch.set_target_durations(job_id, [1], 60.0)
    orch.set_target_durations(job_id, [1], None)

    reloaded = orch.store.load(job_id)
    assert reloaded.section_by_index(1).target_duration_s is None


def test_set_target_durations_rejects_unknown_index_without_partial_write(tmp_path):
    orch, job_id = _make_job(tmp_path)
    with pytest.raises(InvalidStateError):
        orch.set_target_durations(job_id, [0, 99], 45.0)

    # La section 0 (valide) ne doit PAS avoir été modifiée : validation atomique.
    reloaded = orch.store.load(job_id)
    assert reloaded.section_by_index(0).target_duration_s is None
