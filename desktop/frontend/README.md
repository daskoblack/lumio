# Lumio — frontend

Interface React + TypeScript de l'app desktop Lumio, chargée par pywebview
(`desktop/app/main.py`). Communique avec le pipeline Python via
`window.pywebview.api` (voir `src/api/bridge.ts` et `desktop/app/api.py`).

## Développement

```bash
npm install
npm run dev          # serveur Vite sur http://localhost:5173
```

Puis, dans un autre terminal (depuis la racine du dépôt), avec `LUMIO_DEV=1` :

```bash
LUMIO_DEV=1 python -m desktop.app.main
```

⚠️ Toujours lancer avec `-m` (pas `python desktop/app/main.py`) : `main.py` utilise des
imports relatifs (`from .api import Api`), qui ne fonctionnent que si le fichier est
exécuté comme faisant partie du package `desktop.app`, pas comme un script isolé.

pywebview charge alors le serveur Vite (rechargement à chaud) au lieu du build statique.

## Production

```bash
npm run build         # génère dist/, chargé par pywebview en production
```

## Structure

```
src/
├── api/bridge.ts        pont typé vers window.pywebview.api
├── components/          Rail, DurationSlider, ProgressBar, Wordmark, ThemeToggle
├── screens/              Home, Sections, Videos, Settings
├── styles/               tokens.css (design system) + global.css
└── types.ts              types miroir des modèles Pydantic (lectio/core/models.py)
```
