"""Garde-fous contre le texte imprononçable, qui faisait échouer la synthèse
vocale avec « No audio was received » (reproduit en conditions réelles)."""

import pytest

from lectio.core.exceptions import TTSError
from lectio.core.models import ContentBlock, Section, SectionKind, Slide
from lectio.core.textutil import is_pronounceable
from lectio.pipeline.scripting import NarrationContext, generate_slide_script
from lectio.providers.llm.base import LLMProvider
from lectio.providers.tts.base import VoiceProfile
from lectio.providers.tts.edge_provider import EdgeTTS


# --- Détection -----------------------------------------------------------

@pytest.mark.parametrize("texte", ["...", "---", '""', "  ", "", "!?", "«»"])
def test_texte_sans_lettre_est_rejete(texte):
    assert not is_pronounceable(texte)


@pytest.mark.parametrize("texte", ["Bonjour", "a", "1", "... et voilà", "3 points"])
def test_texte_avec_lettre_ou_chiffre_est_accepte(texte):
    assert is_pronounceable(texte)


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
        position=1, total=1,
    )
    return NarrationContext(**{**defaults, **kwargs})


@pytest.mark.asyncio
async def test_reponse_imprononcable_declenche_une_seconde_tentative():
    llm = _LLMScripted(["...", "Voici une vraie narration."])
    script = await generate_slide_script(
        llm, _ctx(), tolerance=0.10, max_passes=2
    )
    assert script.text == "Voici une vraie narration."
    assert script.fallback_used is False
    assert llm.appels == 2


@pytest.mark.asyncio
async def test_secours_bati_sur_la_page_si_l_ia_echoue_deux_fois():
    llm = _LLMScripted(["...", "---"])
    script = await generate_slide_script(
        llm, _ctx(), tolerance=0.10, max_passes=2
    )
    assert script.fallback_used is True
    assert is_pronounceable(script.text)
    assert "fractions" in script.text  # secours tiré du contenu réel de la page


@pytest.mark.asyncio
async def test_secours_ultime_si_la_page_est_vide():
    slide = Slide(index=0, source_page=1, title="...", content_blocks=[])
    section = Section(index=0, kind=SectionKind.OTHER, title="   ")
    llm = _LLMScripted(["...", "..."])
    script = await generate_slide_script(
        llm, _ctx(section=section, slide=slide), tolerance=0.10, max_passes=2
    )
    assert is_pronounceable(script.text)  # jamais de texte impossible à prononcer


@pytest.mark.asyncio
async def test_correction_imprononcable_est_ignoree():
    """La 2e passe (ajustement de durée) ne doit pas casser un texte valide."""
    llm = _LLMScripted(["Un texte correct mais trop court.", "..."])
    script = await generate_slide_script(
        llm, _ctx(target_words=200), tolerance=0.10, max_passes=2
    )
    assert script.text == "Un texte correct mais trop court."
    assert script.generation_pass == 1  # la correction inutilisable a été écartée
