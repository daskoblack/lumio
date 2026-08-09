"""Tests du renommage d'un cours (titre affiché dans l'app)."""

import pytest

from lectio.core.config import Config
from lectio.core.exceptions import InvalidStateError
from lectio.core.models import Course, CourseStatus
from lectio.jobs.orchestrator import Orchestrator


def _make_job(tmp_path) -> tuple[Orchestrator, str]:
    config = Config.load()
    config.paths.workspace = str(tmp_path / "workspace")
    orch = Orchestrator(config)

    course = Course(title="mon_pdf_export_final_v2", source_pdf="x.pdf", status=CourseStatus.DONE)
    orch.store.save(course)
    return orch, course.id


def test_rename_course_change_le_titre(tmp_path):
    orch, job_id = _make_job(tmp_path)
    result = orch.rename_course(job_id, "Les fractions - CM2")

    assert result.title == "Les fractions - CM2"
    reloaded = orch.store.load(job_id)
    assert reloaded.title == "Les fractions - CM2"


def test_rename_course_retire_les_espaces_superflus(tmp_path):
    orch, job_id = _make_job(tmp_path)
    result = orch.rename_course(job_id, "  Titre avec espaces  ")
    assert result.title == "Titre avec espaces"


def test_rename_course_refuse_un_titre_vide(tmp_path):
    orch, job_id = _make_job(tmp_path)
    with pytest.raises(InvalidStateError):
        orch.rename_course(job_id, "   ")

    # Le titre d'origine ne doit pas avoir été effacé.
    reloaded = orch.store.load(job_id)
    assert reloaded.title == "mon_pdf_export_final_v2"


def test_rename_course_job_inexistant(tmp_path):
    config = Config.load()
    config.paths.workspace = str(tmp_path / "workspace")
    orch = Orchestrator(config)
    with pytest.raises(Exception):  # JobNotFoundError (LectioError)
        orch.rename_course("inconnu", "Nouveau titre")
