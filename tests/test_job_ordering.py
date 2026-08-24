"""Classement chronologique des cours.

Le tri portait sur le nom du dossier, c'est-à-dire un identifiant ALÉATOIRE :
l'ordre de la liste des vidéos n'avait aucun sens, et le « dernier cours » de
l'accueil désignait un cours au hasard.
"""

import os
import time
from datetime import datetime, timedelta

from lectio.core.models import Course, CourseStatus
from lectio.jobs.store import JobStore


def _course(store: JobStore, titre: str, quand: datetime | None) -> Course:
    course = Course(title=titre, source_pdf="x.pdf", created_at=quand,
                     status=CourseStatus.DONE)
    store.save(course)
    return course


def test_les_cours_sont_du_plus_recent_au_plus_ancien(tmp_path):
    store = JobStore(tmp_path / "ws")
    base = datetime(2026, 1, 1, 12, 0, 0)
    _course(store, "ancien", base)
    _course(store, "recent", base + timedelta(days=5))
    _course(store, "intermediaire", base + timedelta(days=2))

    assert [c.title for c in store.list_jobs()] == ["recent", "intermediaire", "ancien"]


def test_l_ordre_ne_depend_pas_de_l_identifiant(tmp_path):
    """Le cœur du correctif : l'identifiant est aléatoire, il ne doit jouer
    aucun rôle dans le classement."""
    store = JobStore(tmp_path / "ws")
    base = datetime(2026, 1, 1, 12, 0, 0)
    for i in range(12):
        _course(store, f"cours-{i:02d}", base + timedelta(hours=i))

    titres = [c.title for c in store.list_jobs()]
    attendu = [f"cours-{i:02d}" for i in reversed(range(12))]
    assert titres == attendu


def test_un_cours_sans_date_utilise_la_date_de_son_fichier(tmp_path):
    """Les cours créés avant l'ajout du champ ne doivent pas être relégués
    au hasard : leur fichier porte une date exploitable."""
    store = JobStore(tmp_path / "ws")
    ancien = _course(store, "sans-date", None)

    # Vieillit artificiellement le fichier du cours sans date.
    chemin = tmp_path / "ws" / ancien.id / "job.json"
    vieux = time.time() - 86_400
    os.utime(chemin, (vieux, vieux))

    _course(store, "avec-date", datetime.now())

    assert [c.title for c in store.list_jobs()] == ["avec-date", "sans-date"]


def test_un_job_corrompu_est_ignore_sans_casser_la_liste(tmp_path):
    store = JobStore(tmp_path / "ws")
    _course(store, "valide", datetime.now())

    casse = tmp_path / "ws" / "abcdef123456"
    casse.mkdir(parents=True)
    (casse / "job.json").write_text("{ pas du JSON", encoding="utf-8")

    assert [c.title for c in store.list_jobs()] == ["valide"]


def test_espace_de_travail_vide(tmp_path):
    assert JobStore(tmp_path / "ws").list_jobs() == []


def test_la_date_est_conservee_apres_relecture(tmp_path):
    """Une relecture ne doit pas redater le cours à « maintenant », sinon le
    classement se dégraderait à chaque ouverture de l'application."""
    store = JobStore(tmp_path / "ws")
    quand = datetime(2026, 1, 1, 12, 0, 0)
    course = _course(store, "cours", quand)

    for _ in range(3):
        relu = store.load(course.id)
        store.save(relu)

    assert store.load(course.id).created_at == quand
