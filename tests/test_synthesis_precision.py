"""Tests de la boucle de correction audio : bidirectionnelle et bornée pour
une cible EXPLICITE (`ctx.precise`), inchangée (asymétrique, une passe) pour
une cible AUTO."""

from pathlib import Path

import pytest

from lectio.core.models import ContentBlock, Script, Section, SectionKind, Slide
from lectio.pipeline.scripting import NarrationContext
from lectio.pipeline.synthesis import synthesize_slide
from lectio.providers.llm.base import LLMProvider
from lectio.providers.tts.base import TTSProvider, TTSResult, VoiceProfile


class _FixedLLM(LLMProvider):
    """Renvoie toujours le même texte : isole la boucle AUDIO de la boucle mots."""

    def __init__(self, words: int = 50) -> None:
        self.words = words
        self.calls = 0

    async def complete(self, system, user, *, json_mode=False, temperature=None, max_tokens=None):
        self.calls += 1
        return " ".join(["mot"] * self.words)


class _ScriptedTTS(TTSProvider):
    """Renvoie une durée prédéfinie à chaque appel (simule la convergence)."""

    def __init__(self, durations: list[float]) -> None:
        self.durations = durations
        self.calls = 0

    async def synthesize(self, text, voice, out_path):
        d = self.durations[min(self.calls, len(self.durations) - 1)]
        self.calls += 1
        return TTSResult(audio_path=out_path, duration_s=d, word_count=len(text.split()))


def _ctx(tmp_path, precise: bool) -> NarrationContext:
    section = Section(index=0, kind=SectionKind.CONCEPT, title="T")
    slide = Slide(
        index=0, source_page=1, title="P1",
        content_blocks=[ContentBlock(kind="text", text="Contenu source.")],
        script=Script(slide_id="", text="Narration initiale.", word_count_target=100,
                       word_count_actual=50, generation_pass=1),
    )
    return NarrationContext(
        section=section, slide=slide, position=1, total=1,
        target_words=100, tolerance=0.99, precise=precise,
    )


# Débit verrouillé (calibration_samples énorme) : la cible en secondes reste
# stable d'une tentative à l'autre, l'arithmétique du test reste prévisible.
def _voice() -> VoiceProfile:
    return VoiceProfile(speech_rate_wps=2.0, calibration_samples=100_000)


@pytest.mark.asyncio
async def test_auto_manque_n_est_jamais_corrige(tmp_path):
    ctx = _ctx(tmp_path, precise=False)
    tts = _ScriptedTTS([20.0])  # très en dessous de la cible (50s), jamais corrigé en mode auto
    await synthesize_slide(_FixedLLM(), tts, ctx, _voice(), tmp_path, deviation_threshold=0.08, max_passes=2)
    assert tts.calls == 1


@pytest.mark.asyncio
async def test_auto_depassement_est_corrige_une_fois(tmp_path):
    ctx = _ctx(tmp_path, precise=False)
    tts = _ScriptedTTS([70.0, 52.0])  # dépasse puis rentre dans la marge après correction
    await synthesize_slide(_FixedLLM(), tts, ctx, _voice(), tmp_path, deviation_threshold=0.08, max_passes=2)
    assert tts.calls == 2


@pytest.mark.asyncio
async def test_precise_manque_est_corrige(tmp_path):
    """Le coeur du changement demandé : une cible EXPLICITE corrige aussi un manque."""
    ctx = _ctx(tmp_path, precise=True)
    tts = _ScriptedTTS([30.0, 48.0])  # 30s (cible 50s) puis 48s (dans la marge 46-54)
    await synthesize_slide(_FixedLLM(), tts, ctx, _voice(), tmp_path, deviation_threshold=0.08, max_passes=4)
    assert tts.calls == 2
    assert ctx.slide.actual_duration_s == 48.0


@pytest.mark.asyncio
async def test_precise_est_borne_et_ne_boucle_pas_indefiniment(tmp_path):
    ctx = _ctx(tmp_path, precise=True)
    tts = _ScriptedTTS([10.0])  # ne convergera jamais (toujours très en dessous)
    await synthesize_slide(_FixedLLM(), tts, ctx, _voice(), tmp_path, deviation_threshold=0.08, max_passes=4)
    assert tts.calls == 3  # _MAX_AUDIO_ATTEMPTS_PRECISE : jamais plus


@pytest.mark.asyncio
async def test_precise_ecart_residuel_est_signale(tmp_path):
    ctx = _ctx(tmp_path, precise=True)
    tts = _ScriptedTTS([10.0])
    await synthesize_slide(_FixedLLM(), tts, ctx, _voice(), tmp_path, deviation_threshold=0.08, max_passes=4)
    assert ctx.section.synthesis_note is not None
    assert "Manque résiduel" in ctx.section.synthesis_note


@pytest.mark.asyncio
async def test_precise_dans_la_marge_ne_declenche_rien(tmp_path):
    ctx = _ctx(tmp_path, precise=True)
    tts = _ScriptedTTS([49.0])  # déjà dans la marge (46-54) : pas de correction
    await synthesize_slide(_FixedLLM(), tts, ctx, _voice(), tmp_path, deviation_threshold=0.08, max_passes=4)
    assert tts.calls == 1
    assert ctx.section.synthesis_note is None
