"""Exceptions métier de Lectio (permettent un traitement d'erreur explicite par job)."""


class LectioError(Exception):
    """Erreur de base de l'application."""


class ExtractionError(LectioError):
    """Le PDF n'a pas pu être exploité (scanné, vide, corrompu...)."""


class LLMError(LectioError):
    """Échec d'appel ou réponse invalide du fournisseur LLM."""


class JobNotFoundError(LectioError):
    """Aucun job ne correspond à l'identifiant fourni."""


class InvalidStateError(LectioError):
    """Opération demandée incompatible avec l'état courant du job."""


class TTSError(LectioError):
    """Échec de synthèse vocale."""


class RenderError(LectioError):
    """Échec de rendu des slides ou de montage vidéo (FFmpeg)."""


class STTError(LectioError):
    """Échec de transcription (sous-titres)."""
