# Lectio — AI Course Maker

Transforme un PDF pédagogique en vidéo de cours avec un professeur IA (narration
originale, pas une lecture du PDF).

Points clés :
- **La durée de chaque section est un input utilisateur optionnel** qui
  contraint la génération du script (budget de mots ≈ durée × débit), et non
  une post-édition de la vidéo. Sans cible, la durée reste calculée
  automatiquement à partir de l'audio réel généré.
- **La vidéo affiche les vraies pages du PDF**, telles quelles (pas de
  redessin par l'IA), et chaque page a son propre audio : la synchro entre ce
  que dit le professeur et la page affichée est garantie par construction.
- **La narration reste fluide malgré le découpage page par page** : chaque
  page est générée avec le contexte de ce qui vient d'être dit (page
  précédente) et un aperçu de ce qui arrive (page suivante), pour permettre
  des enchaînements et transitions naturels ("Nous allons maintenant voir...")
  sans jamais répéter une introduction déjà faite.

## État d'avancement — MVP CLI complet (phases 0 à 5)

- **Phase 0** — socle : modèles, config, interfaces `LLMProvider` / `TTSProvider` /
  `VideoEngine` / `STTProvider`, orchestrateur async par job, persistance JSON. ✅
- **Phase 1** — extraction PDF (PyMuPDF) + analyse de structure (LLM) + découpage
  en sections avec durée estimée, répartie ensuite entre les pages. ✅
- **Phase 2** — génération des narrations PAGE PAR PAGE avec contexte narratif
  (page précédente/suivante), durée personnalisable et boucle de correction
  bornée (texte, sans TTS). ✅
- **Phase 3** — synthèse vocale par page (TTS), mesure de la durée réelle
  (ffprobe), calibration du débit par voix, correction bornée à une itération
  post-TTS. ✅
- **Phase 4** — rendu des VRAIES pages du PDF (rasterisation, pas de dessin
  IA), timeline 1 page = 1 audio (synchro garantie), montage FFmpeg -> MP4. ✅
- **Phase 5** — transcription (Whisper), sous-titres SRT, incrustation souple
  dans le MP4 final. ✅

Toutes les phases ont été vérifiées avec de vrais outils (edge-tts, FFmpeg,
PyMuPDF/Pillow) de bout en bout ; seul l'appel réel à l'API Groq (LLM +
Whisper) nécessite ta clé pour être testé en conditions réelles.

## Décisions techniques notables

- **LLM** : Groq (`llama-3.3-70b-versatile`), gratuit.
- **TTS** : Groq (PlayAI) ne supporte **pas le français** → le fournisseur par
  défaut est **edge-tts** (Microsoft, gratuit, sans clé, plusieurs voix
  neurales FR). Voix choisissable par cours (`lectio voices`,
  `lectio analyze --voice ...`) ; la calibration du débit est propre à chaque
  voix. Interface `TTSProvider` inchangée : remplaçable dès qu'un fournisseur
  payant/français apparaît (ex. ElevenLabs, si le budget le permet un jour).
- **STT (sous-titres)** : Groq Whisper (`whisper-large-v3-turbo`), multilingue,
  timestamps mot-à-mot, même clé que le LLM.
- **Rendu des slides** : rasterisation directe des pages du PDF (PyMuPDF +
  Pillow pour le letterboxing), PAS un redessin par l'IA — fidélité totale au
  support original.
- **Synchro narration/page** : approche hybride. Chaque page a son propre
  audio (fiabilité de la synchro garantie par construction, pas par mesure
  dans l'audio), mais la génération du texte se fait en séquence au sein
  d'une section, avec mémoire du texte déjà dit et aperçu de la page
  suivante — pour un rendu de cours fluide plutôt que haché page par page.
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

Clé Groq (LLM + sous-titres), rendue permanente :

```bash
setx GROQ_API_KEY "gsk_..."   # nouvelle session de terminal ensuite
```

## Utilisation (CLI)

```bash
# 0. (Optionnel) Lister les voix FR disponibles
lectio voices

# 1. Analyse : découpe le PDF en sections avec durées estimées
lectio analyze cours.pdf --voice fr-FR-HenriNeural

# 2. (Optionnel) Fixe une durée cible sur certaines sections
lectio set-duration <job> --section 2 --duration 60s
lectio set-duration <job> --section 3 --duration auto   # retour au calcul auto

# 3. Génère les narrations page par page (respecte les cibles par ajustement du texte)
lectio script <job>
lectio show-script <job> --section 2   # relit le texte généré, page par page

# 4. Synthèse vocale + calibration + correction bornée si écart trop grand
lectio synthesize <job>

# 5. Rendu des vraies pages du PDF + montage vidéo
lectio render <job>

# 6. Sous-titres + incrustation -> vidéo finale
lectio subtitle <job>

# Raccourci : enchaîne 4+5+6 d'un coup
lectio build <job>

# Inspecter
lectio show <job>
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
post-TTS) de chaque SLIDE. Les durées cible/estimée ne servent qu'à
contraindre la génération du texte en amont ; le rendu vidéo ne connaît
jamais ces notions.

Le `Script` (narration) vit sur `Slide`, pas sur `Section` : chaque page a sa
propre narration, son propre audio, sa propre durée réelle. La `Section`
reste le regroupement pédagogique où l'utilisateur fixe une durée cible
globale, répartie entre ses pages au prorata de leur poids de contenu.

## Limites connues (MVP)

- La continuité narrative (page précédente/suivante) ne s'étend pas au-delà
  d'une section : la première page d'une nouvelle section réintroduit
  normalement son sujet (pas de transition inter-sections).
- L'aperçu donné au LLM pour teaser la page suivante est un extrait brut du
  texte source (pas un résumé) : pour des pages très denses, la teaser peut
  être moins naturel.
- PDF scannés non supportés (pas d'OCR).
- Pas de support natif `.pptx` : exporter en PDF au préalable.

## Tests

```bash
pytest
```

31 tests unitaires couvrent la logique pure (timing, sectioning, scripting
avec contexte, timeline, sous-titres) avec des fournisseurs simulés — aucun
appel réseau.
