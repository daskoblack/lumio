# Lectio — AI Course Maker

Transforme un PDF pédagogique en vidéo de cours avec un professeur IA (narration
originale, pas une lecture du PDF).

Point clé : **la durée de chaque section est un input utilisateur optionnel** qui
contraint la génération du script (budget de mots ≈ durée × débit), et non une
post-édition de la vidéo. Sans cible, la durée reste calculée automatiquement à
partir de l'audio réel généré.

## État d'avancement — MVP CLI complet (phases 0 à 5)

- **Phase 0** — socle : modèles, config, interfaces `LLMProvider` / `TTSProvider` /
  `VideoEngine` / `STTProvider`, orchestrateur async par job, persistance JSON. ✅
- **Phase 1** — extraction PDF (PyMuPDF) + analyse de structure (LLM) + découpage
  en sections avec durée estimée. ✅
- **Phase 2** — génération des narrations avec durée personnalisable et boucle de
  correction bornée (texte, sans TTS). ✅
- **Phase 3** — synthèse vocale (TTS), mesure de la durée réelle (ffprobe),
  calibration du débit par voix, correction bornée à une itération post-TTS. ✅
- **Phase 4** — rendu des slides (Pillow), construction de la timeline (basée
  uniquement sur la durée réelle), montage FFmpeg -> MP4. ✅
- **Phase 5** — transcription (Whisper), sous-titres SRT, incrustation souple
  dans le MP4 final. ✅

Toutes les phases ont été vérifiées avec de vrais outils (edge-tts, FFmpeg,
Pillow) de bout en bout ; seul l'appel réel à l'API Groq (LLM + Whisper)
nécessite ta clé pour être testé en conditions réelles.

## Décisions techniques notables

- **LLM** : Groq (`llama-3.3-70b-versatile`), gratuit.
- **TTS** : Groq (PlayAI) ne supporte **pas le français** → le fournisseur par
  défaut est **edge-tts** (Microsoft, gratuit, sans clé, voix neurales FR :
  `fr-FR-DeniseNeural` / `fr-FR-HenriNeural`). Interface `TTSProvider`
  inchangée : remplaçable dès qu'un fournisseur payant/français apparaît.
- **STT (sous-titres)** : Groq Whisper (`whisper-large-v3-turbo`), multilingue,
  timestamps mot-à-mot, même clé que le LLM.
- **Rendu des slides** : Pillow plutôt que Playwright — évite l'installation
  d'un navigateur headless pour un rendu titre + texte + image suffisant au MVP.
- **FFmpeg** requis sur la machine (installé ici via `scoop install ffmpeg`).

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows PowerShell
pip install -e ".[dev]"
```

FFmpeg doit être sur le PATH :

```bash
scoop install ffmpeg
```

Clé Groq (LLM + sous-titres) :

```bash
setx GROQ_API_KEY "gsk_..."   # nouvelle session ensuite
```

## Utilisation (CLI)

```bash
# 1. Analyse : découpe le PDF en sections avec durées estimées
lectio analyze cours.pdf

# 2. (Optionnel) Fixe une durée cible sur certaines sections
lectio set-duration <job> --section 2 --duration 60s
lectio set-duration <job> --section 3 --duration auto   # retour au calcul auto

# 3. Génère les narrations (respecte les cibles par ajustement du texte)
lectio script <job>

# 4. Synthèse vocale + calibration + correction bornée si écart trop grand
lectio synthesize <job>

# 5. Rendu des slides + montage vidéo
lectio render <job>

# 6. Sous-titres + incrustation -> vidéo finale
lectio subtitle <job>

# Raccourci : enchaîne 4+5+6 d'un coup
lectio build <job>

# Inspecter
lectio show <job>
lectio show-script <job> --section 2
lectio list
```

## Architecture

Modules séparés et testables indépendamment : la logique pédagogique
(`pipeline/sectioning`, `pipeline/scripting`) ne connaît rien du rendu vidéo
(`pipeline/slides`, `pipeline/timeline`, `providers/video`). Le contrat unique
entre les deux est le schéma de données (`core/models.py`).

```
lectio/
├── core/        modèles, config, timing (logique pure), ffprobe, exceptions
├── providers/   interfaces abstraites LLM / TTS / STT / Video + implémentations
│   ├── llm/     Groq
│   ├── tts/     edge-tts
│   ├── stt/     Groq Whisper
│   └── video/   FFmpeg
├── pipeline/    extraction, analysis, sectioning, scripting, synthesis,
│                slides, timeline, subtitles
├── jobs/        orchestrateur async + persistance de l'état + calibration voix
└── cli/         interface Typer
```

Règle d'or : `pipeline/timeline.py` ne lit QUE `actual_duration_s` (mesurée
post-TTS). Les durées cible/estimée ne servent qu'à contraindre la génération
du texte en amont.

## Limites connues (MVP)

- Une section avec plusieurs slides répartit sa durée réellement mesurée à
  parts égales entre elles (pas de synchronisation fine avec le contenu).
- Rendu de slide minimal (titre + texte + séparateur) ; pas de mise en page
  riche ni d'insertion des images extraites du PDF pour l'instant.
- PDF scannés non supportés (pas d'OCR).

## Tests

```bash
pytest
```

26 tests unitaires couvrent la logique pure (timing, sectioning, scripting,
timeline, sous-titres) avec des fournisseurs simulés — aucun appel réseau.
