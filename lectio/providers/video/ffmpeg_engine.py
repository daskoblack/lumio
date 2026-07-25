"""Implémentation FFmpeg de VideoEngine.

Stratégie en 3 passes (robuste aux durées/format hétérogènes) :
1. Diaporama silencieux depuis les images (concat demuxer, une durée par image).
2. Piste audio unique = concaténation des segments audio par section
   (filtre `concat`, tolère des encodages différents contrairement au concat demuxer).
3. Mux vidéo + audio -> MP4 final.

Aucune connaissance des modèles pédagogiques ici : uniquement des chemins et
des durées (`TimelineEntry`), conformément à la séparation pédagogie/rendu.

Débit d'images CONSTANT (pas VFR) : avec un débit variable, une slide très
longue ne produit qu'une poignée d'images réelles dans le fichier, espacées
irrégulièrement. Un lecteur qui avance/recule dans la vidéo doit alors sauter
à l'image codée la plus proche, souvent lointaine -> l'image affichée se
« fige » puis change en retard sur le son, avec un décalage grandissant qui
ne se résorbe qu'en repassant par une image réellement codée. Un débit
constant + des images-clés régulières garantit un seek précis n'importe où.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from ...core.proc import resolve_binary, run
from .base import TimelineEntry, VideoEngine

# Durée plancher par image pour le concat demuxer (évite une entrée à 0s
# invalide côté FFmpeg si une section ne compte qu'une slide très courte).
_MIN_IMAGE_DURATION_S = 0.05

# Débit de sortie et intervalle entre images-clés. Une image statique n'a pas
# besoin d'un débit élevé (pas de mouvement à restituer) ; ce qui compte pour
# un seek précis est la RÉGULARITÉ des images-clés, pas leur nombre total.
_OUTPUT_FPS = 10
_KEYFRAME_INTERVAL_S = 1


def _escape_concat_path(path: str) -> str:
    return path.replace("'", "'\\''")


class FFmpegVideoEngine(VideoEngine):
    async def assemble(self, timeline: list[TimelineEntry], out_path: str) -> str:
        if not timeline:
            raise ValueError("Timeline vide : rien à assembler.")

        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp_dir = Path(tempfile.mkdtemp(prefix="lectio_render_", dir=out.parent))

        try:
            video_silent = await self._build_silent_video(timeline, tmp_dir)
            audio_full = await self._build_audio_track(timeline, tmp_dir)
            await self._mux(video_silent, audio_full, out)
        finally:
            for f in tmp_dir.glob("*"):
                f.unlink(missing_ok=True)
            tmp_dir.rmdir()

        return str(out)

    async def _build_silent_video(self, timeline: list[TimelineEntry], tmp_dir: Path) -> Path:
        list_path = tmp_dir / "images.txt"
        lines: list[str] = []
        for entry in timeline:
            duration = max(entry.duration_s, _MIN_IMAGE_DURATION_S)
            path = _escape_concat_path(str(Path(entry.image_path).resolve()))
            lines.append(f"file '{path}'")
            lines.append(f"duration {duration:.3f}")
        # Quirk FFmpeg : la dernière `duration` est ignorée sans répétition du fichier.
        last_path = _escape_concat_path(str(Path(timeline[-1].image_path).resolve()))
        lines.append(f"file '{last_path}'")
        list_path.write_text("\n".join(lines), encoding="utf-8")

        out_video = tmp_dir / "video_silent.mp4"
        await run(
            [
                resolve_binary("ffmpeg"), "-y",
                "-f", "concat", "-safe", "0", "-i", str(list_path),
                "-r", str(_OUTPUT_FPS),
                "-g", str(_OUTPUT_FPS * _KEYFRAME_INTERVAL_S),
                "-pix_fmt", "yuv420p",
                "-c:v", "libx264",
                str(out_video),
            ]
        )
        return out_video

    async def _build_audio_track(self, timeline: list[TimelineEntry], tmp_dir: Path) -> Path:
        audio_paths = [e.audio_path for e in timeline if e.audio_path]
        if not audio_paths:
            raise ValueError("Aucun segment audio dans la timeline (synthèse manquante ?).")

        out_audio = tmp_dir / "audio_full.mp3"
        cmd = [resolve_binary("ffmpeg"), "-y"]
        for p in audio_paths:
            cmd += ["-i", p]
        filter_inputs = "".join(f"[{i}:a]" for i in range(len(audio_paths)))
        filter_complex = f"{filter_inputs}concat=n={len(audio_paths)}:v=0:a=1[aout]"
        cmd += ["-filter_complex", filter_complex, "-map", "[aout]", str(out_audio)]
        await run(cmd)
        return out_audio

    async def _mux(self, video_path: Path, audio_path: Path, out_path: Path) -> None:
        await run(
            [
                resolve_binary("ffmpeg"), "-y",
                "-i", str(video_path),
                "-i", str(audio_path),
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy", "-c:a", "aac",
                "-shortest",
                str(out_path),
            ]
        )
