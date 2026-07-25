"""Pont entre l'interface web (React) et le pipeline Python existant (lectio).

Chaque méthode publique est appelable depuis JS via `window.pywebview.api.<methode>(...)`.
Les opérations longues (script/synthesize/render/subtitle/build) poussent leur
avancement à l'interface via `window.evaluate_js` (callback JS `__lumioProgress`).

Aucune connaissance de React ici : ce module ne fait que traduire entre le
pipeline Python (synchrone du point de vue de pywebview) et du JSON simple.
"""

from __future__ import annotations

import asyncio
import json
import threading

import webview

from lectio.core.config import Config
from lectio.core.exceptions import LectioError
from lectio.jobs.orchestrator import Orchestrator

from . import paths
from . import settings as settings_store


def _course_dict(course) -> dict:
    return course.model_dump(mode="json")


def _error_dict(exc: Exception) -> dict:
    return {"error": str(exc)}


class Api:
    def __init__(self) -> None:
        # Sérialise les opérations qui mutent un job (évite deux écritures
        # concurrentes du même job.json si l'UI déclenche deux actions vite).
        self._lock = threading.Lock()
        self._window: webview.Window | None = None
        self._config = Config.load()
        self._config.paths.workspace = str(paths.default_workspace_dir("Lumio"))
        settings_store.apply_to_environment(settings_store.load_settings())

        # Boucle asyncio UNIQUE, persistante pour toute la vie de l'app : le
        # client Groq (httpx.AsyncClient) reste attaché à cette même boucle au
        # lieu d'être recréé puis abandonné à chaque appel (ce qui laissait
        # des connexions orphelines se fermer sur une boucle déjà détruite —
        # inoffensif, mais du gaspillage et du bruit inutile dans les logs).
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._loop_thread.start()

        # Un seul Orchestrator réutilisé : ses fournisseurs (LLM/TTS/STT) ne
        # sont donc construits qu'une fois, pas à chaque clic.
        self._orchestrator_instance = Orchestrator(self._config)

    def set_window(self, window: webview.Window) -> None:
        self._window = window

    def _orchestrator(self) -> Orchestrator:
        return self._orchestrator_instance

    def _run(self, coro):
        with self._lock:
            future = asyncio.run_coroutine_threadsafe(coro, self._loop)
            return future.result()

    def _progress_emitter(self, stage: str):
        def emit(label: str, done: int, total: int) -> None:
            if self._window is None:
                return
            payload = json.dumps({"stage": stage, "label": label, "done": done, "total": total})
            try:
                self._window.evaluate_js(
                    f"window.__lumioProgress && window.__lumioProgress({payload})"
                )
            except Exception:  # noqa: BLE001 - la fenêtre a pu se fermer entre-temps
                pass
        return emit

    # --- Réglages (clé API + voix), modifiables à tout moment ---
    def get_settings(self) -> dict:
        return settings_store.load_settings()

    def save_settings(self, groq_api_key: str | None, voice_id: str | None) -> dict:
        updated = settings_store.save_settings(groq_api_key=groq_api_key, voice_id=voice_id)
        settings_store.apply_to_environment(updated)
        if voice_id:
            self._config.providers.tts.voice = voice_id
        return updated

    def list_voices(self) -> list[dict]:
        import edge_tts

        async def _list():
            all_voices = await edge_tts.list_voices()
            return [
                {"id": v["ShortName"], "gender": v["Gender"], "locale": v["Locale"]}
                for v in all_voices if v["Locale"].startswith("fr-")
            ]
        return sorted(self._run(_list()), key=lambda v: v["locale"])

    def preview_voice(self, voice_id: str) -> dict:
        """Synthétise une phrase de démonstration et la renvoie en base64
        (pas de fichier à gérer côté JS : lu directement par un <audio>)."""
        import base64
        import tempfile
        from pathlib import Path

        import edge_tts

        async def _synthesize() -> str:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                tmp_path = f.name
            try:
                communicate = edge_tts.Communicate(
                    "Bonjour, voici un aperçu de cette voix.", voice=voice_id
                )
                await communicate.save(tmp_path)
                data = Path(tmp_path).read_bytes()
                return "data:audio/mpeg;base64," + base64.b64encode(data).decode("ascii")
            finally:
                Path(tmp_path).unlink(missing_ok=True)

        try:
            return {"audio": self._run(_synthesize())}
        except Exception as exc:  # noqa: BLE001
            return _error_dict(exc)

    # --- Sélection de fichier natif ---
    def pick_pdf_file(self) -> str | None:
        if self._window is None:
            return None
        result = self._window.create_file_dialog(
            webview.FileDialog.OPEN, file_types=("Fichiers PDF (*.pdf)",)
        )
        return result[0] if result else None

    # --- Étape 1 : analyse ---
    def analyze(self, pdf_path: str, voice_id: str | None = None, title: str | None = None) -> dict:
        orch = self._orchestrator()
        try:
            course = self._run(orch.create_and_analyze(pdf_path, title, voice_id))
        except LectioError as exc:
            return _error_dict(exc)
        return _course_dict(course)

    # --- Durées cibles (une ou plusieurs sections) ---
    def set_durations(self, job_id: str, section_indices: list[int], duration_s: float | None) -> dict:
        orch = self._orchestrator()
        try:
            with self._lock:
                orch.set_target_durations(job_id, section_indices, duration_s)
                course = orch.store.load(job_id)
        except LectioError as exc:
            return _error_dict(exc)
        return _course_dict(course)

    # --- Étapes individuelles (utiles pour ré-essayer une étape précise) ---
    def run_script(self, job_id: str) -> dict:
        orch = self._orchestrator()
        try:
            course = self._run(orch.run_scripting(job_id, self._progress_emitter("script")))
        except LectioError as exc:
            return _error_dict(exc)
        return _course_dict(course)

    def run_synthesize(self, job_id: str) -> dict:
        orch = self._orchestrator()
        try:
            course = self._run(orch.run_synthesis(job_id, self._progress_emitter("synthesize")))
        except LectioError as exc:
            return _error_dict(exc)
        return _course_dict(course)

    def run_render(self, job_id: str) -> dict:
        orch = self._orchestrator()
        try:
            course = self._run(orch.run_rendering(job_id, self._progress_emitter("render")))
        except LectioError as exc:
            return _error_dict(exc)
        return _course_dict(course)

    def run_subtitle(self, job_id: str) -> dict:
        orch = self._orchestrator()
        try:
            course = self._run(orch.run_subtitles(job_id, self._progress_emitter("subtitle")))
        except LectioError as exc:
            return _error_dict(exc)
        return _course_dict(course)

    # --- Raccourci : enchaîne synthesize + render + subtitle ---
    def run_build(self, job_id: str) -> dict:
        orch = self._orchestrator()

        async def _pipeline():
            await orch.run_synthesis(job_id, self._progress_emitter("synthesize"))
            await orch.run_rendering(job_id, self._progress_emitter("render"))
            return await orch.run_subtitles(job_id, self._progress_emitter("subtitle"))

        try:
            course = self._run(_pipeline())
        except LectioError as exc:
            return _error_dict(exc)
        return _course_dict(course)

    # --- Consultation ---
    def get_job(self, job_id: str) -> dict:
        orch = self._orchestrator()
        try:
            course = orch.store.load(job_id)
        except LectioError as exc:
            return _error_dict(exc)
        return _course_dict(course)

    def list_jobs(self) -> list[dict]:
        orch = self._orchestrator()
        return [_course_dict(c) for c in orch.store.list_jobs()]

    def open_output_folder(self, job_id: str) -> None:
        import subprocess

        orch = self._orchestrator()
        folder = orch.store.job_dir(job_id) / "output"
        if folder.exists():
            subprocess.Popen(["explorer", str(folder)])  # noqa: S603, S607
