"""Aucune méthode exposée à l'interface ne doit laisser fuir une exception.

Une exception non rattrapée traverse pywebview, la promesse JavaScript est
rejetée, et l'écran reste MUET : l'utilisateur clique, attend, et rien ne se
passe. Reproduit dans le navigateur avant correction.
"""

import inspect

import pytest

from desktop.app import api as api_module
from desktop.app.api import Api, _guarded, _safe
from lectio.core.exceptions import LLMError


@pytest.fixture(autouse=True)
def journal(tmp_path, monkeypatch):
    """Redirige le journal d'erreur : aucun test ne doit écrire dans
    le vrai dossier de l'utilisateur."""
    destination = tmp_path / "lumio-erreur.log"
    monkeypatch.setattr(api_module.crash, "log_path", lambda: destination)
    return destination


class _Faux:
    """Objet minimal portant des méthodes décorées, sans démarrer l'app."""

    @_guarded
    def metier(self):
        raise LLMError("plus de quota")

    @_guarded
    def inattendu(self):
        raise OSError(28, "No space left on device")

    @_guarded
    def ok(self):
        return {"resultat": 1}

    @_safe(list)
    def liste_qui_casse(self):
        raise RuntimeError("panne")

    @_safe(None)
    def rien_qui_casse(self):
        raise RuntimeError("panne")

    @_safe(list)
    def liste_ok(self):
        return [1, 2]


# --- Erreurs métier : message tel quel ------------------------------------

def test_une_erreur_metier_reste_lisible():
    assert _Faux().metier() == {"error": "plus de quota"}


def test_un_appel_normal_n_est_pas_altere():
    assert _Faux().ok() == {"resultat": 1}
    assert _Faux().liste_ok() == [1, 2]


# --- Erreurs inattendues : plus jamais muettes -----------------------------

def test_une_erreur_inattendue_devient_un_message(journal):
    resultat = _Faux().inattendu()
    assert "error" in resultat
    assert "OSError" in resultat["error"]
    assert "No space left" in resultat["error"]


def test_une_erreur_inattendue_indique_le_rapport(journal):
    resultat = _Faux().inattendu()
    assert str(journal) in resultat["error"]  # l'utilisateur sait quoi transmettre


def test_une_erreur_inattendue_est_tracee(journal):
    _Faux().inattendu()
    contenu = journal.read_text(encoding="utf-8")
    assert "Traceback" in contenu
    assert "No space left" in contenu


# --- Contrats sans erreur : valeur neutre, jamais un dictionnaire ----------

def test_une_liste_reste_une_liste_meme_en_cas_d_echec(journal):
    """Renvoyer {"error": ...} là où l'interface attend une liste la
    casserait : elle itérerait sur les clés du dictionnaire."""
    assert _Faux().liste_qui_casse() == []
    assert "panne" in journal.read_text(encoding="utf-8")


def test_une_valeur_nulle_est_renvoyee_sans_planter(journal):
    assert _Faux().rien_qui_casse() is None


# --- Couverture : aucune méthode publique oubliée --------------------------

def test_toutes_les_methodes_exposees_sont_protegees():
    """Un ajout futur non décoré redeviendrait silencieux : ce test le
    signalera."""
    oubliees = [
        nom
        for nom, methode in inspect.getmembers(Api, inspect.isfunction)
        if not nom.startswith("_")
        and nom != "set_window"  # ne fait qu'affecter un attribut
        and not hasattr(methode, "__wrapped__")
    ]
    assert oubliees == [], f"méthodes exposées sans garde : {oubliees}"
