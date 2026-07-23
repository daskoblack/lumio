# -*- mode: python ; coding: utf-8 -*-
"""Spec PyInstaller pour Lumio.

Produit un dossier dist/Lumio/ contenant Lumio.exe + toutes ses dépendances
(Python, FFmpeg vendorisé, frontend buildé). Nécessite au préalable :
  - desktop/frontend/dist/  (npm run build côté frontend)
  - desktop/vendor/ffmpeg/ffmpeg.exe + ffprobe.exe (voir desktop/vendor/README.md)

Lancer avec : pyinstaller lumio.spec
"""

from pathlib import Path

root = Path(SPECPATH)  # noqa: F821 - injecté par PyInstaller

datas = [
    (str(root / "desktop" / "frontend" / "dist"), "frontend/dist"),
    (str(root / "desktop" / "frontend" / "lumio_icon.ico"), "frontend"),
    (str(root / "config" / "default.yaml"), "config"),
]

binaries = [
    (str(root / "desktop" / "vendor" / "ffmpeg" / "ffmpeg.exe"), "bin"),
    (str(root / "desktop" / "vendor" / "ffmpeg" / "ffprobe.exe"), "bin"),
]

a = Analysis(  # noqa: F821
    [str(root / "desktop" / "lumio_launcher.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Lumio",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(root / "desktop" / "frontend" / "lumio_icon.ico"),
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="Lumio",
)
