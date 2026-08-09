"""Le serveur local qui sert la vidéo au lecteur intégré (voir la note dans
media_server.py sur pourquoi pas un simple file://)."""

import urllib.request

from desktop.app import media_server


def test_sert_un_fichier_du_dossier_racine(tmp_path):
    job_dir = tmp_path / "abc123" / "output"
    job_dir.mkdir(parents=True)
    (job_dir / "video_final.mp4").write_bytes(b"contenu-video-factice")

    port = media_server.start(tmp_path)
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/abc123/output/video_final.mp4") as resp:
        assert resp.read() == b"contenu-video-factice"


def test_repond_404_hors_du_dossier_racine(tmp_path):
    (tmp_path / "reel.mp4").write_bytes(b"x")

    port = media_server.start(tmp_path)
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/inexistant.mp4")
        assert False, "devrait lever une erreur 404"
    except urllib.error.HTTPError as exc:
        assert exc.code == 404
