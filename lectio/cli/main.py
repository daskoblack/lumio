"""Interface CLI de Lectio (Typer).

Flux MVP :
  lectio voices                    -> liste les voix FR disponibles (edge-tts)
  lectio analyze cours.pdf --voice fr-FR-HenriNeural
                                    -> crée le job, affiche le plan de sections
  lectio set-duration <job> -s 2 -d 60s        -> fixe une durée cible (optionnel)
  lectio set-duration <job> -s 1,2,19 -d 120s  -> ou sur plusieurs sections d'un coup
  lectio script <job>              -> génère les narrations (page par page, durées contraintes)
  lectio synthesize <job>          -> TTS + durée réelle + calibration + correction
  lectio render <job>              -> vraies pages du PDF + timeline + montage FFmpeg -> MP4
  lectio subtitle <job>            -> sous-titres (Whisper) incrustés -> MP4 final
  lectio build <job>               -> enchaîne synthesize + render + subtitle
  lectio show <job>                -> réaffiche l'état
  lectio show-script <job> -s 2    -> affiche la narration de chaque page d'une section
  lectio list                      -> liste les jobs
"""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table

from ..core.config import Config
from ..core.exceptions import LectioError
from ..core.models import Course
from ..core.timing import format_duration, parse_duration
from ..jobs.orchestrator import Orchestrator

app = typer.Typer(help="Lectio — transforme un PDF de cours en vidéo (professeur IA).")
console = Console()


def _orchestrator() -> Orchestrator:
    return Orchestrator(Config.load())


def _fail(message: str) -> None:
    console.print(f"[bold red]Erreur :[/] {message}")
    raise typer.Exit(code=1)


def _print_plan(course: Course) -> None:
    """Affiche le plan de sections avec durées estimée / cible."""
    console.print(
        f"\n[bold]{course.title}[/]  "
        f"[dim](job {course.id} · état {course.status.value} · voix {course.voice_profile_id})[/]"
    )
    if course.truncated:
        console.print(
            "[yellow]⚠ Document tronqué pour l'analyse (voir max_document_chars).[/]"
        )

    table = Table(show_lines=False)
    table.add_column("#", justify="right")
    table.add_column("Type")
    table.add_column("Titre")
    table.add_column("Slides", justify="right")
    table.add_column("Estimée", justify="right")
    table.add_column("Cible", justify="right")
    table.add_column("Réelle", justify="right")
    table.add_column("Mots", justify="right")

    total_est = 0.0
    total_actual = 0.0
    any_corrected = False
    for s in course.sections:
        total_est += s.estimated_duration_s or 0.0
        total_actual += s.actual_duration_s or 0.0
        slides = course.section_slides(s)
        words = sum(sl.script.word_count_actual for sl in slides if sl.script)
        corrected = any(sl.script and sl.script.generation_pass == 2 for sl in slides)
        any_corrected = any_corrected or corrected
        table.add_row(
            str(s.index),
            s.kind.value,
            s.title,
            str(len(s.slide_ids)),
            format_duration(s.estimated_duration_s),
            format_duration(s.target_duration_s) if s.target_duration_s else "[dim]auto[/]",
            format_duration(s.actual_duration_s),
            f"{words} *" if corrected else (str(words) if words else ""),
        )

    console.print(table)
    console.print(f"[dim]Durée estimée totale : {format_duration(total_est)}[/]")
    if total_actual:
        console.print(f"[dim]Durée réelle totale (audio) : {format_duration(total_actual)}[/]")
    if any_corrected:
        console.print("[dim]* au moins une page ajustée en 2e passe pour tenir la cible.[/]")
    for s in course.sections:
        if s.synthesis_note:
            console.print(f"[yellow]⚠ Section {s.index} : {s.synthesis_note}[/]")


@app.command()
def voices() -> None:
    """Liste les voix françaises disponibles (edge-tts, gratuit)."""
    import edge_tts

    async def _list() -> list[dict]:
        all_voices = await edge_tts.list_voices()
        return [v for v in all_voices if v["Locale"].startswith("fr-")]

    fr_voices = asyncio.run(_list())
    table = Table()
    table.add_column("Voix (--voice)")
    table.add_column("Genre")
    table.add_column("Locale")
    for v in sorted(fr_voices, key=lambda v: v["Locale"]):
        table.add_row(v["ShortName"], v["Gender"], v["Locale"])
    console.print(table)
    console.print(f"[dim]Défaut actuel : {Config.load().providers.tts.voice}[/]")


@app.command()
def analyze(
    pdf: str = typer.Argument(..., help="Chemin du PDF de cours."),
    title: str = typer.Option(None, "--title", "-t", help="Titre du cours (optionnel)."),
    voice: str = typer.Option(
        None, "--voice", help="Voix TTS à utiliser (voir 'lectio voices'). Défaut : config."
    ),
) -> None:
    """Extrait le PDF, analyse la structure et propose un plan de sections."""
    orch = _orchestrator()
    try:
        course = asyncio.run(orch.create_and_analyze(pdf, title, voice))
    except LectioError as exc:
        _fail(str(exc))
    _print_plan(course)
    console.print(
        f"\nProchaine étape : "
        f"[cyan]lectio set-duration {course.id} -s <n> -d <durée>[/] "
        f"puis [cyan]lectio script {course.id}[/]."
    )


@app.command("set-duration")
def set_duration(
    job: str = typer.Argument(..., help="Identifiant du job."),
    section: str = typer.Option(
        ..., "--section", "-s",
        help="Index de section, ou plusieurs séparés par des virgules (ex. 1,2,19,39).",
    ),
    duration: str = typer.Option(
        ..., "--duration", "-d",
        help="Durée cible (ex. 90, 90s, 2m, 1m30s) ou 'auto' pour repasser en automatique.",
    ),
) -> None:
    """Fixe (ou annule) la durée cible d'une ou plusieurs sections à la fois."""
    orch = _orchestrator()
    try:
        indices = [int(tok.strip()) for tok in section.split(",") if tok.strip()]
    except ValueError:
        _fail(f"Index de section invalide : {section!r} (attendu : des entiers séparés par des virgules).")

    try:
        value = None if duration.strip().lower() == "auto" else parse_duration(duration)
        secs = orch.set_target_durations(job, indices, value)
    except (LectioError, ValueError) as exc:
        _fail(str(exc))

    label = ", ".join(str(i) for i in indices)
    if value is None:
        console.print(f"Section(s) {label} : durée remise en [cyan]auto[/].")
    else:
        for sec in secs:
            console.print(
                f"Section {sec.index} « {sec.title} » : cible fixée à "
                f"[cyan]{format_duration(value)}[/] "
                f"(estimation actuelle {format_duration(sec.estimated_duration_s)})."
            )


@app.command()
def script(job: str = typer.Argument(..., help="Identifiant du job.")) -> None:
    """Génère les narrations 'professeur' page par page (durées contraintes)."""
    orch = _orchestrator()
    console.print("[dim]Génération des scripts (page par page, avec contexte)…[/]")
    try:
        course = asyncio.run(orch.run_scripting(job))
    except LectioError as exc:
        _fail(str(exc))
    _print_plan(course)


@app.command()
def synthesize(job: str = typer.Argument(..., help="Identifiant du job.")) -> None:
    """Synthétise l'audio (TTS) par page, mesure la durée réelle, calibre et corrige si besoin."""
    orch = _orchestrator()
    console.print("[dim]Synthèse vocale…[/]")
    try:
        course = asyncio.run(orch.run_synthesis(job))
    except LectioError as exc:
        _fail(str(exc))
    _print_plan(course)


@app.command()
def render(job: str = typer.Argument(..., help="Identifiant du job.")) -> None:
    """Rend les vraies pages du PDF, construit la timeline et assemble la vidéo (FFmpeg)."""
    orch = _orchestrator()
    console.print("[dim]Rendu des pages et montage vidéo…[/]")
    try:
        course = asyncio.run(orch.run_rendering(job))
    except LectioError as exc:
        _fail(str(exc))
    out = orch.store.job_dir(job) / "output" / "video.mp4"
    console.print(f"[green]Vidéo produite :[/] {out}")


@app.command()
def subtitle(job: str = typer.Argument(..., help="Identifiant du job.")) -> None:
    """Transcrit l'audio (Whisper) et incruste les sous-titres dans le MP4 final."""
    orch = _orchestrator()
    console.print("[dim]Transcription et sous-titrage…[/]")
    try:
        asyncio.run(orch.run_subtitles(job))
    except LectioError as exc:
        _fail(str(exc))
    out = orch.store.job_dir(job) / "output" / "video_final.mp4"
    console.print(f"[green]Vidéo finale (avec sous-titres) :[/] {out}")


@app.command()
def build(job: str = typer.Argument(..., help="Identifiant du job.")) -> None:
    """Enchaîne synthesize + render + subtitle jusqu'à la vidéo finale."""
    orch = _orchestrator()

    async def _run() -> None:
        console.print("[dim]1/3 Synthèse vocale…[/]")
        await orch.run_synthesis(job)
        console.print("[dim]2/3 Rendu et montage…[/]")
        await orch.run_rendering(job)
        console.print("[dim]3/3 Sous-titres…[/]")
        await orch.run_subtitles(job)

    try:
        asyncio.run(_run())
    except LectioError as exc:
        _fail(str(exc))

    course = orch.store.load(job)
    _print_plan(course)
    out = orch.store.job_dir(job) / "output" / "video_final.mp4"
    console.print(f"[green]Vidéo finale :[/] {out}")


@app.command()
def show(job: str = typer.Argument(..., help="Identifiant du job.")) -> None:
    """Réaffiche l'état d'un job."""
    orch = _orchestrator()
    try:
        course = orch.store.load(job)
    except LectioError as exc:
        _fail(str(exc))
    _print_plan(course)


@app.command("show-script")
def show_script(
    job: str = typer.Argument(..., help="Identifiant du job."),
    section: int = typer.Option(..., "--section", "-s", help="Index de la section."),
) -> None:
    """Affiche la narration générée pour chaque page (slide) d'une section."""
    orch = _orchestrator()
    try:
        course = orch.store.load(job)
    except LectioError as exc:
        _fail(str(exc))
    sec = course.section_by_index(section)
    if sec is None:
        _fail(f"Section {section} inexistante.")
    slides = course.section_slides(sec)
    if not slides or not any(sl.script for sl in slides):
        _fail("Aucun script pour cette section (as-tu lancé 'script' ?).")

    console.print(f"[bold]{sec.title}[/]\n")
    for sl in slides:
        if not sl.script:
            continue
        console.print(f"[cyan]— Page {sl.source_page}[/] ({sl.script.word_count_actual} mots)")
        console.print(sl.script.text)
        console.print()


@app.command("list")
def list_jobs() -> None:
    """Liste les jobs existants."""
    orch = _orchestrator()
    jobs = orch.store.list_jobs()
    if not jobs:
        console.print("[dim]Aucun job.[/]")
        return
    table = Table()
    table.add_column("Job")
    table.add_column("Titre")
    table.add_column("État")
    table.add_column("Sections", justify="right")
    for c in jobs:
        table.add_row(c.id, c.title, c.status.value, str(len(c.sections)))
    console.print(table)


if __name__ == "__main__":
    app()
