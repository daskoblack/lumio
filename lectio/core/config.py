"""Chargement de la configuration (YAML) et résolution des secrets (env).

La clé API n'est JAMAIS stockée dans un fichier : elle est lue depuis
l'environnement (GROQ_API_KEY) au moment de l'instanciation du provider.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


def _default_config_path() -> Path:
    """Chemin de config/default.yaml.

    Dans l'app packagée (PyInstaller), `__file__` ne pointe pas vers une
    arborescence source réelle : le fichier est alors cherché à côté du
    bundle (sys._MEIPASS), où il est inclus explicitement (voir lumio.spec).
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", "")) / "config" / "default.yaml"
    return Path(__file__).resolve().parents[2] / "config" / "default.yaml"


_DEFAULT_CONFIG_PATH = _default_config_path()


# Les clés API ne sont JAMAIS lues depuis un fichier de config : uniquement
# depuis l'environnement (l'app desktop les y injecte depuis ses réglages).
LLM_ENV_KEYS = {
    "groq": "GROQ_API_KEY",
    "cerebras": "CEREBRAS_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "mistral": "MISTRAL_API_KEY",
}


class LLMCandidate(BaseModel):
    """Un maillon de la chaîne de repli : un fournisseur + un modèle précis."""

    name: str                    # groq | cerebras | gemini | mistral
    model: str
    min_interval_s: float = 2.0  # espacement propre au fournisseur (limites RPM ≠)


def _default_fallbacks() -> list[LLMCandidate]:
    """Repli par défaut : du plus capable au plus modeste.

    Chaque maillon est tenté seulement si le précédent est épuisé, et
    seulement si sa clé API est renseignée. Sans aucune clé de repli,
    le comportement reste identique à avant (un seul fournisseur).
    """
    return [
        # Même fournisseur, modèle plus léger : consomme bien moins de tokens.
        LLMCandidate(name="groq", model="llama-3.1-8b-instant"),
        # Puis d'autres comptes gratuits, avec leurs propres quotas quotidiens.
        LLMCandidate(name="cerebras", model="gpt-oss-120b"),
        # Gemini gratuit est limité à ~10 requêtes/min : espacement plus large.
        LLMCandidate(name="gemini", model="gemini-2.5-flash-lite", min_interval_s=6.5),
        LLMCandidate(name="mistral", model="mistral-small-latest"),
    ]


class LLMConfig(BaseModel):
    name: str = "groq"
    model: str = "llama-3.3-70b-versatile"
    temperature: float = 0.4
    max_document_chars: int = 24000
    min_interval_s: float = 2.0  # espacement minimal entre appels (évite les 429 Groq)
    fallbacks: list[LLMCandidate] = Field(default_factory=_default_fallbacks)


class TTSConfig(BaseModel):
    name: str = "edge"
    voice: str = "fr-FR-DeniseNeural"


class STTConfig(BaseModel):
    name: str = "groq"
    model: str = "whisper-large-v3-turbo"
    min_interval_s: float = 2.0  # même compte Groq que le LLM : même précaution


class ProvidersConfig(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    stt: STTConfig = Field(default_factory=STTConfig)


class VoiceConfig(BaseModel):
    default_speech_rate_wps: float = 2.3


class ScriptingConfig(BaseModel):
    word_budget_tolerance: float = 0.10
    max_generation_passes: int = 2


class SynthesisConfig(BaseModel):
    deviation_threshold: float = 0.12


class SlidesConfig(BaseModel):
    width: int = 1920
    height: int = 1080


class SubtitlesConfig(BaseModel):
    max_chars_per_line: int = 42
    max_lines: int = 2
    max_words_per_caption: int = 14


class PathsConfig(BaseModel):
    workspace: str = "workspace"


class Config(BaseModel):
    language: str = "fr"
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    scripting: ScriptingConfig = Field(default_factory=ScriptingConfig)
    synthesis: SynthesisConfig = Field(default_factory=SynthesisConfig)
    slides: SlidesConfig = Field(default_factory=SlidesConfig)
    subtitles: SubtitlesConfig = Field(default_factory=SubtitlesConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        """Charge la config depuis un YAML (défaut : config/default.yaml)."""
        config_path = Path(path) if path else _DEFAULT_CONFIG_PATH
        if config_path.exists():
            data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        else:
            data = {}
        return cls.model_validate(data)

    @property
    def workspace_path(self) -> Path:
        return Path(self.paths.workspace)

    @staticmethod
    def api_key_for(provider_name: str) -> str | None:
        """Clé API d'un fournisseur, depuis l'environnement."""
        env_var = LLM_ENV_KEYS.get(provider_name.lower())
        return os.environ.get(env_var) if env_var else None

    @staticmethod
    def groq_api_key() -> str | None:
        """Clé API Groq depuis l'environnement (jamais depuis un fichier)."""
        return os.environ.get("GROQ_API_KEY")

    @staticmethod
    def cerebras_api_key() -> str | None:
        """Clé API Cerebras depuis l'environnement (jamais depuis un fichier)."""
        return os.environ.get("CEREBRAS_API_KEY")
