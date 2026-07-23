"""Persistance des profils de voix (débit calibré), partagée entre jobs.

La calibration s'améliore au fil des générations : elle vit donc au niveau
`workspace/voices/{id}.json`, indépendamment d'un job particulier.
"""

from __future__ import annotations

from pathlib import Path

from ..providers.tts.base import VoiceProfile


class VoiceProfileStore:
    def __init__(self, workspace: Path) -> None:
        self._dir = Path(workspace) / "voices"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, profile_id: str) -> Path:
        return self._dir / f"{profile_id}.json"

    def load(self, profile_id: str, default_voice_id: str, default_rate_wps: float) -> VoiceProfile:
        path = self._path(profile_id)
        if path.exists():
            return VoiceProfile.model_validate_json(path.read_text(encoding="utf-8"))
        return VoiceProfile(
            id=profile_id, voice_id=default_voice_id, speech_rate_wps=default_rate_wps
        )

    def save(self, profile: VoiceProfile) -> None:
        self._path(profile.id).write_text(profile.model_dump_json(indent=2), encoding="utf-8")
