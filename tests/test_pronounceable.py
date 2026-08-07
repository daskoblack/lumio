"""Garde-fous contre le texte imprononçable (qui faisait échouer la synthèse
vocale avec « No audio was received », reproduit en conditions réelles) et
contre les ruptures de personnage (« Je m'appelle [Votre Nom] »)."""

import pytest

from lectio.core.exceptions import TTSError
from lectio.core.models import ContentBlock, Section, SectionKind, Slide
from lectio.core.textutil import has_suspicious_pattern, is_pronounceable
from lectio.pipeline.scripting import NarrationContext, generate_slide_script
from lectio.providers.llm.base import LLMProvider
from lectio.providers.tts.base import VoiceProfile
from lectio.providers.tts.edge_provider import EdgeTTS


# --- Détection : prononçabilité -------------------------------------------

@pytest.mark.parametrize("texte", ["...", "---", '""', "  ", "", "!?", "«»"])
def test_texte_sans_lettre_est_rejete(texte):
    assert not is_pronounceable(texte)


@pytest.mark.parametrize("texte", ["Bonjour", "a", "1", "... et voilà", "3 points"])
def test_texte_avec_lettre_ou_chiffre_est_accepte(texte):
    assert is_pronounceable(texte)


# --- Détection : rupture de personnage -------------------------------------

@pytest.mark.parametrize("texte", [
    "Bonjour, je m'appelle [Votre Nom] et je suis ravi de vous accompagner.",
    "En tant qu'assistant, je ne peux pas répondre à cette question.",
    "En tant qu'IA, je n'ai pas d'opinion personnelle sur ce sujet.",
    "Je suis un modèle de langage entraîné par OpenAI.",
    "Voici un exemple : [insérer ici un exemple concret].",
])
def test_texte_avec_rupture_de_personnage_est_detecte(texte):
    assert has_suspicious_pattern(texte)


@pytest.mark.parametrize("texte", [
    "Aujourd'hui, nous allons étudier les fractions et leurs propriétés.",
    "Prenons un exemple concret pour illustrer cette idée.",
    "On appelle cette figure un triangle rectangle.",
    "[Ce texte entre crochets fait 45 caractères et plus]",  # trop long -> pas un gabarit
])
def test_texte_de_cours_legitime_n_est_pas_signale(texte):
    assert not has_suspicious_pattern(texte)


# --- Garde côté TTS (dernier recours) ------------------------------------

@pytest.mark.asyncio
async def test_tts_refuse_le_texte_imprononcable_avec_message_clair(tmp_path):
    """Le message doit dire ce qui ne va pas, pas « No audio was received »."""
    with pytest.raises(TTSError, match="ni lettre ni chiffre"):
        await EdgeTTS().synthesize("...", VoiceProfile(), str(tmp_path / "a.mp3"))


@pytest.mark.asyncio
async def test_tts_detecte_un_audio_vide(tmp_path, monkeypatch):
    """Un fichier de 0 octet ne doit pas filer en aval : ffprobe y échouerait
    avec un message incompréhensible."""
    out = tmp_path / "vide.mp3"

    class _FakeCommunicate:
        def __init__(self, *a, **kw):
            pass

        async def save(self, path):
            open(path, "wb").close()  # ce que fait edge-tts sur un texte vide

    import edge_tts
    monkeypatch.setattr(edge_tts, "Communicate", _FakeCommunicate)

    with pytest.raises(TTSError, match="aucun son"):
        await EdgeTTS().synthesize("Bonjour", VoiceProfile(), str(out))


# --- Garde côté génération de script -------------------------------------

class _LLMScripted(LLMProvider):
    """Renvoie les réponses fournies, dans l'ordre."""

    def __init__(self, reponses: list[str]) -> None:
        self.reponses = reponses
        self.appels = 0

    async def complete(self, system, user, *, json_mode=False, temperature=None, max_tokens=None):
        reponse = self.reponses[min(self.appels, len(self.reponses) - 1)]
        self.appels += 1
        return reponse


def _slide(texte_source="Contenu réel de la page sur les fractions."):
    return Slide(
        index=0, source_page=1, title="Les fractions",
        content_blocks=[ContentBlock(kind="text", text=texte_source)],
    )


def _section(titre="Partie 1"):
    return Section(index=0, kind=SectionKind.CONCEPT, title=titre)


def _ctx(section=None, slide=None, **kwargs) -> NarrationContext:
    defaults = dict(
        section=section or _section(),
        slide=slide if slide is not None else _slide(),
        position=1, total=1, tolerance=0.10,
    )
    return NarrationContext(**{**defaults, **kwargs})


@pytest.mark.asyncio
async def test_reponse_imprononcable_declenche_une_seconde_tentative():
    llm = _LLMScripted(["...", "Voici une vraie narration."])
    script = await generate_slide_script(llm, _ctx(), max_passes=2)
    assert script.text == "Voici une vraie narration."
    assert script.fallback_used is False
    assert llm.appels == 2


@pytest.mark.asyncio
async def test_rupture_de_personnage_declenche_une_seconde_tentative():
    """Le cas réel signalé : « Je m'appelle [Votre Nom] » est textuellement
    valide (contient des lettres) mais doit être rattrapé comme le texte
    imprononçable, avant de partir à la synthèse vocale."""
    llm = _LLMScripted([
        "Bonjour, je m'appelle [Votre Nom] et je suis ravi de vous accompagner.",
        "Reprenons où nous en étions sur les fractions.",
    ])
    script = await generate_slide_script(llm, _ctx(), max_passes=2)
    assert script.text == "Reprenons où nous en étions sur les fractions."
    assert script.fallback_used is False
    assert llm.appels == 2


@pytest.mark.asyncio
async def test_secours_bati_sur_la_page_si_l_ia_echoue_deux_fois():
    llm = _LLMScripted(["...", "---"])
    script = await generate_slide_script(llm, _ctx(), max_passes=2)
    assert script.fallback_used is True
    assert is_pronounceable(script.text)
    assert "fractions" in script.text  # secours tiré du contenu réel de la page


@pytest.mark.asyncio
async def test_secours_si_rupture_de_personnage_persiste():
    llm = _LLMScripted([
        "Je suis un modèle de langage entraîné par OpenAI.",
        "En tant qu'IA, je ne peux pas donner mon avis.",
    ])
    script = await generate_slide_script(llm, _ctx(), max_passes=2)
    assert script.fallback_used is True
    assert not has_suspicious_pattern(script.text)
    assert "fractions" in script.text


@pytest.mark.asyncio
async def test_secours_ultime_si_la_page_est_vide():
    slide = Slide(index=0, source_page=1, title="...", content_blocks=[])
    section = Section(index=0, kind=SectionKind.OTHER, title="   ")
    llm = _LLMScripted(["...", "..."])
    script = await generate_slide_script(llm, _ctx(section=section, slide=slide), max_passes=2)
    assert is_pronounceable(script.text)  # jamais de texte impossible à prononcer


@pytest.mark.asyncio
async def test_correction_de_depassement_invalide_est_ignoree():
    """La passe de correction (dépassement de durée) ne doit pas remplacer un
    texte valide par une rupture de personnage."""
    llm = _LLMScripted([
        " ".join(["mot"] * 200),  # net dépassement de la cible de 120
        "Je suis un modèle de langage entraîné par OpenAI.",  # correction invalide
    ])
    script = await generate_slide_script(llm, _ctx(target_words=120), max_passes=2)
    assert script.word_count_actual == 200  # correction rejetée, original conservé
    assert script.generation_pass == 1
