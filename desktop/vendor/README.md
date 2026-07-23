# FFmpeg vendorisé (pour l'empaquetage uniquement)

Le dossier `ffmpeg/` doit contenir `ffmpeg.exe` et `ffprobe.exe` avant de
lancer le build PyInstaller — ils sont embarqués dans `Lumio.exe` pour que
l'app fonctionne sans installation préalable de FFmpeg chez l'utilisateur.

Ces binaires (~200 Mo) ne sont **pas** versionnés dans git. Pour les
récupérer :

```bash
curl -L -o ffmpeg-essentials.zip https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
unzip ffmpeg-essentials.zip
mkdir -p desktop/vendor/ffmpeg
cp ffmpeg-*-essentials_build/bin/ffmpeg.exe ffmpeg-*-essentials_build/bin/ffprobe.exe desktop/vendor/ffmpeg/
```

Le build "essentials" (~100 Mo) suffit : il inclut `libx264`, `aac` et
`mov_text`, tout ce dont Lumio a besoin. Le build "full" (~230 Mo par
binaire) fonctionne aussi mais est inutilement volumineux pour ce projet.
