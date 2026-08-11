"""Synthèse vocale par PAGE + boucle de correction bornée (phase 3).

Chaque page a son propre audio (garantit la synchro image/son). Pour chaque
page :
1. TTS du script actuel -> mesure de la durée RÉELLE (ffprobe, autorité finale)
2. Calibration du VoiceProfile (débit) à partir de cette mesure
3. Si un budget de mots cible existe ET que l'écart réel/cible dépasse le
   seuil : régénère le texte (même contexte narratif) et resynthétise.

Pour une cible EXPLICITE (`ctx.precise`), la correction est BIDIRECTIONNELLE
et bornée à `_MAX_AUDIO_ATTEMPTS_PRECISE` tentatives -- le texte a déjà
convergé en mots (voir scripting._refine_to_target), ici on absorbe surtout
la variance naturelle du débit réel de la voix. Pour une cible AUTO, la
correction reste UNIQUE et n'agit qu'en cas de dépassement (comportement
historique : aucune promesse explicite à tenir sur une section non configurée).

Sans cible, aucune contrainte : la durée réelle du premier TTS fait foi.
"""

from __future__ import annotations

from pathlib import Path

from ..providers.llm.base import LLMProvider
from ..providers.tts.base import TTSProvider, VoiceProfile
from . import scripting
from .scripting import NarrationContext

_MAX_AUDIO_ATTEMPTS_PRECISE = 3  # 1 synthèse + jusqu'à 2 corrections
_MAX_AUDIO_ATTEMPTS_AUTO = 2     # 1 synthèse + 1 correction max (inchangé)


async def synthesize_slide(
    llm: LLMProvider,
    tts: TTSProvider,
    ctx: NarrationContext,
    voice: VoiceProfile,
    out_dir: Path,
    deviation_threshold: float,
    max_passes: int,
) -> None:
    """Synthétise (et corrige au besoin) l'audio d'une page. Mute la page en place."""
    slide = ctx.slide
    assert slide.script is not None, "Le scripting doit précéder la synthèse."

    out_path = str(out_dir / f"slide_{slide.index:03d}.mp3")
    result = await tts.synthesize(slide.script.text, voice, out_path)
    ctx.warning = result.warning

    slide.script.audio_path = result.audio_path
    slide.script.audio_duration_s = result.duration_s
    slide.actual_duration_s = result.duration_s
    voice.recalibrate(result.word_count, result.duration_s)

    target_words = slide.script.word_count_target
    if target_words is None:
        return  # mode auto sans estimation : pas de contrainte

    # Recalculée à chaque tentative avec le débit fraîchement calibré : plus
    # les pages avancent, plus cette cible en secondes reflète la voix réelle.
    slide_target_s = target_words / voice.speech_rate_wps
    max_attempts = _MAX_AUDIO_ATTEMPTS_PRECISE if ctx.precise else _MAX_AUDIO_ATTEMPTS_AUTO
    attempts = 1

    while attempts < max_attempts:
        gap = (result.duration_s - slide_target_s) / slide_target_s
        if ctx.precise:
            if abs(gap) <= deviation_threshold:
                break
        else:
            # Cible AUTO : comportement historique -- jamais de correction
            # pour un manque, uniquement en cas de dépassement.
            if gap <= deviation_threshold:
                break

        slide.script = await scripting.generate_slide_script(llm, ctx, max_passes)
        result = await tts.synthesize(slide.script.text, voice, out_path)
        ctx.warning = result.warning or ctx.warning
        slide.script.audio_path = result.audio_path
        slide.script.audio_duration_s = result.duration_s
        slide.actual_duration_s = result.duration_s
        voice.recalibrate(result.word_count, result.duration_s)
        slide_target_s = target_words / voice.speech_rate_wps
        attempts += 1

    final_gap = (result.duration_s - slide_target_s) / slide_target_s
    residual = abs(final_gap) > deviation_threshold if ctx.precise else final_gap > deviation_threshold
    if residual:
        section = ctx.section
        direction = "Dépassement" if final_gap > 0 else "Manque"
        section.synthesis_note = (
            f"{section.synthesis_note + ' ' if section.synthesis_note else ''}"
            f"{direction} résiduel de {abs(final_gap):.0%} sur la page "
            f"{slide.source_page} (cible {slide_target_s:.0f}s, réel {result.duration_s:.0f}s)."
        )
