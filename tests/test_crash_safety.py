"""Filet de sécurité contre les plantages muets au démarrage.

L'app packagée n'a pas de console : sans ce filet, une exception au démarrage
fait disparaître le processus sans le moindre message, ce qui est
indéfendable pour un utilisateur non technique.

NOTE : `crash.show_dialog` n'est JAMAIS appelée ici. Sur Windows elle ouvre
une vraie boîte de dialogue modale, qui bloquerait la suite de tests. Toutes
les vérifications passent par une notification injectée.
"""

import pytest

from desktop.app import crash


class _Notify:
    """Remplace la boîte de dialogue native : capture ce qui serait affiché."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def __call__(self, message: str) -> None:
        self.messages.append(message)


@pytest.fixture
def journal(tmp_path, monkeypatch):
    """Redirige le journal d'erreur vers un fichier temporaire."""
    destination = tmp_path / "lumio-erreur.log"
    monkeypatch.setattr(crash, "log_path", lambda: destination)
    return destination


# --- Journal ---------------------------------------------------------------

def test_le_rapport_contient_la_trace_complete(journal):
    try:
        raise ValueError("clé API introuvable")
    except ValueError as exc:
        chemin = crash.write_report(exc)

    assert chemin == journal
    contenu = journal.read_text(encoding="utf-8")
    assert "ValueError" in contenu
    assert "clé API introuvable" in contenu
    assert "Traceback" in contenu


def test_les_incidents_successifs_sont_conserves(journal):
    """Un problème intermittent doit laisser tout son historique."""
    for message in ("premier incident", "second incident"):
        try:
            raise RuntimeError(message)
        except RuntimeError as exc:
            crash.write_report(exc)

    contenu = journal.read_text(encoding="utf-8")
    assert "premier incident" in contenu
    assert "second incident" in contenu


def test_un_journal_inaccessible_ne_fait_pas_planter(tmp_path, monkeypatch):
    """Disque plein, droits manquants : on ne doit pas planter DANS le
    gestionnaire de plantage."""
    # Un chemin dont le parent est un FICHIER : mkdir échouera.
    obstacle = tmp_path / "fichier"
    obstacle.write_text("x", encoding="utf-8")
    monkeypatch.setattr(crash, "log_path", lambda: obstacle / "sous" / "erreur.log")

    chemin = crash.write_report(ValueError("peu importe"))
    assert chemin is None


def test_le_chemin_du_journal_a_un_repli(monkeypatch):
    """Si le dossier de réglages est inaccessible, on retombe sur le temporaire."""
    import desktop.app.paths as paths

    def _casse(_):
        raise OSError("profil Windows cassé")

    monkeypatch.setattr(paths, "app_data_dir", _casse)
    assert crash.log_path().name == "lumio-erreur.log"


# --- Message affiché -------------------------------------------------------

def test_le_message_indique_le_probleme_et_le_rapport(journal):
    notify = _Notify()
    crash.report_fatal(ValueError("clé API introuvable"), notify)

    assert len(notify.messages) == 1
    message = notify.messages[0]
    assert "n'a pas pu s'ouvrir" in message
    assert "clé API introuvable" in message
    assert str(journal) in message  # l'utilisateur sait où trouver le détail


def test_le_message_reste_utile_sans_rapport(monkeypatch):
    monkeypatch.setattr(crash, "write_report", lambda exc: None)
    notify = _Notify()
    crash.report_fatal(ValueError("souci"), notify)
    assert "n'a pas pu être enregistré" in notify.messages[0]


# --- Garde du point d'entrée ----------------------------------------------

def test_un_demarrage_normal_passe_sans_message(journal):
    notify = _Notify()
    appels = []
    crash.guard(lambda: appels.append("demarre"), notify)

    assert appels == ["demarre"]
    assert notify.messages == []
    assert not journal.exists()


def test_une_exception_au_demarrage_est_signalee(journal):
    notify = _Notify()

    def _demarrage_casse():
        raise RuntimeError("pywebview introuvable")

    with pytest.raises(SystemExit) as sortie:
        crash.guard(_demarrage_casse, notify)

    assert sortie.value.code == 1
    assert "pywebview introuvable" in notify.messages[0]
    assert "pywebview introuvable" in journal.read_text(encoding="utf-8")


def test_une_fermeture_normale_n_affiche_aucune_erreur(journal):
    """Quitter l'application ne doit pas ressembler à un plantage."""
    notify = _Notify()

    def _fermeture():
        raise SystemExit(0)

    with pytest.raises(SystemExit) as sortie:
        crash.guard(_fermeture, notify)

    assert sortie.value.code == 0
    assert notify.messages == []
    assert not journal.exists()


def test_un_ctrl_c_n_affiche_aucune_erreur(journal):
    notify = _Notify()

    def _interruption():
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        crash.guard(_interruption, notify)

    assert notify.messages == []
