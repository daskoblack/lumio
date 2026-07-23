"""Persistance de l'état d'un job (Course) en JSON.

Permet l'arrêt entre étapes (ex. après l'analyse pour la revue utilisateur)
puis la reprise. Un job = un dossier workspace/{id}/.
"""

from __future__ import annotations

from pathlib import Path

from ..core.exceptions import JobNotFoundError
from ..core.models import Course


class JobStore:
    """Stockage fichier des jobs sous workspace/."""

    def __init__(self, workspace: Path) -> None:
        self._workspace = Path(workspace)
        self._workspace.mkdir(parents=True, exist_ok=True)

    def job_dir(self, job_id: str) -> Path:
        return self._workspace / job_id

    def _job_file(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "job.json"

    def images_dir(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "extracted" / "images"

    def save(self, course: Course) -> None:
        self.job_dir(course.id).mkdir(parents=True, exist_ok=True)
        self._job_file(course.id).write_text(
            course.model_dump_json(indent=2), encoding="utf-8"
        )

    def load(self, job_id: str) -> Course:
        path = self._job_file(job_id)
        if not path.exists():
            raise JobNotFoundError(f"Job introuvable : {job_id}")
        return Course.model_validate_json(path.read_text(encoding="utf-8"))

    def list_jobs(self) -> list[Course]:
        jobs: list[Course] = []
        for child in sorted(self._workspace.iterdir() if self._workspace.exists() else []):
            if (child / "job.json").exists():
                try:
                    jobs.append(self.load(child.name))
                except Exception:  # noqa: BLE001 - job corrompu ignoré dans la liste
                    continue
        return jobs
