"""Synthèse vocale par section + boucle de correction bornée (phase 3).

Pour chaque section :
1. TTS du script actuel -> mesure de la durée RÉELLE (ffprobe, autorité finale)
2. Calibration du VoiceProfile (débit) à partir de cette mesure
3. Si une cible est fixée ET l'écart réel/cible dépasse le seuil :
   UNE seule régénération du texte (budget recalculé avec le débit mesuré)
   + un seul nouveau TTS. Le résultat est accepté quel que soit l'écart
   résiduel (pas de 2e correction : coût maîtrisé), avec une note d'écart.

Sans cible utilisateur, aucune contrainte ni correction : la durée réelle
du premier TTS devient simplement `actual_duration_s`.
"""

from __future__ import annotations

from pathlib import Path

from ..core.models import Section
from ..core.timing import deviation, duration_to_words
from ..providers.llm.base import LLMProvider
from ..providers.tts.base import TTSProvider, VoiceProfile
from . import scripting


async def synthesize_section(
    llm: LLMProvider,
    tts: TTSProvider,
    section: Section,
    source_text: str,
    voice: VoiceProfile,
    out_dir: Path,
    tolerance: float,
    deviation_threshold: float,
    scripting_max_passes: int,
) -> None:
    """Synthétise (et corrige au besoin) l'audio d'une section. Mute `section` en place."""
    assert section.script is not None, "Le scripting doit précéder la synthèse."

    out_path = str(out_dir / f"section_{section.index:03d}.mp3")
    result = await tts.synthesize(section.script.text, voice, out_path)

    section.script.audio_path = result.audio_path
    section.script.audio_duration_s = result.duration_s
    section.actual_duration_s = result.duration_s
    voice.recalibrate(result.word_count, result.duration_s)

    if section.target_duration_s is None:
        return  # mode auto : pas de contrainte, la durée réelle fait foi telle quelle

    dev = deviation(result.duration_s, section.target_duration_s)
    section.duration_deviation = dev

    if dev <= deviation_threshold:
        return

    # Correction UNIQUE : régénère le texte avec le débit fraîchement calibré.
    new_target_words = duration_to_words(section.target_duration_s, voice.speech_rate_wps)
    section.script = await scripting.generate_script(
        llm, section, source_text, voice.speech_rate_wps, tolerance, scripting_max_passes
    )
    section.script.word_count_target = new_target_words

    result2 = await tts.synthesize(section.script.text, voice, out_path)
    section.script.audio_path = result2.audio_path
    section.script.audio_duration_s = result2.duration_s
    section.actual_duration_s = result2.duration_s
    voice.recalibrate(result2.word_count, result2.duration_s)

    dev2 = deviation(result2.duration_s, section.target_duration_s)
    section.duration_deviation = dev2
    if dev2 > deviation_threshold:
        section.synthesis_note = (
            f"Écart résiduel de {dev2:.0%} après correction unique "
            f"(cible {section.target_duration_s:.0f}s, réel {result2.duration_s:.0f}s)."
        )
