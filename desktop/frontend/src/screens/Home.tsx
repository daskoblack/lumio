import { useEffect, useState } from 'react';
import { bridge } from '../api/bridge';
import { VoicePreviewButton } from '../components/VoicePreviewButton';
import { isApiError, type Course, type Voice } from '../types';
import { friendlyError } from '../friendlyError';
import './home.css';

export function Home({ onCourseReady }: { onCourseReady: (course: Course) => void }) {
  const [voices, setVoices] = useState<Voice[]>([]);
  const [voiceId, setVoiceId] = useState<string>('');
  const [recentJob, setRecentJob] = useState<Course | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    bridge.getSettings().then((s) => setVoiceId(s.voice_id));
    bridge.listVoices().then(setVoices);
    bridge.listJobs().then((jobs) => {
      if (jobs.length) setRecentJob(jobs[0]);  // le plus récent en tête
    });
  }, []);

  async function handleVoiceChange(id: string) {
    setVoiceId(id);
    await bridge.saveSettings(null, id);
  }

  async function handlePickFile() {
    setError(null);
    const path = await bridge.pickPdfFile();
    if (!path) return;
    setBusy(true);
    try {
      const result = await bridge.analyze(path, voiceId || null, null);
      if (isApiError(result)) {
        setError(friendlyError(result.error));
        return;
      }
      onCourseReady(result);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="screen-enter">
      <h1 className="hero">
        Transforme un cours en <span className="glow-text">vidéo</span>,<br />en trois clics.
      </h1>
      <p className="lede">
        Dépose ton support de cours en PDF. Lumio écrit une narration, l'enregistre avec
        une voix, et assemble la vidéo pour toi.
      </p>

      <div className="card dropzone" onClick={handlePickFile} role="button" tabIndex={0}
        onKeyDown={(e) => e.key === 'Enter' && handlePickFile()}>
        <div className="dropzone-icon">
          <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 16V4M12 4l-4 4M12 4l4 4" />
            <path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
          </svg>
        </div>
        <h2>{busy ? 'Analyse en cours…' : 'Dépose ton PDF ici'}</h2>
        <p>{busy ? "Lumio lit le document, ça ne prend qu'un instant" : 'ou clique pour choisir un fichier sur ton ordinateur'}</p>
        <button className="btn-primary" type="button" disabled={busy} onClick={(e) => { e.stopPropagation(); handlePickFile(); }}>
          {busy ? 'Patiente…' : 'Choisir un fichier'}
        </button>
      </div>

      {error && <p className="home-error">{error}</p>}

      <div className="row-cards">
        <div className="card mini-card">
          <div className="label">Voix du professeur</div>
          <div className="voice-row">
            <div className="select-fake inset">
              <select value={voiceId} onChange={(e) => handleVoiceChange(e.target.value)}>
                {voices.map((v) => (
                  <option key={v.id} value={v.id}>{v.id.replace(/^fr-\w+-/, '')} ({v.locale})</option>
                ))}
              </select>
            </div>
            {voiceId && <VoicePreviewButton voiceId={voiceId} />}
          </div>
        </div>
        {recentJob && (
          <div className="card mini-card">
            <div className="label">Dernier cours ouvert</div>
            <button
              type="button"
              className="select-fake inset recent-btn"
              onClick={() => onCourseReady(recentJob)}
            >
              <span>{recentJob.title}</span>
              <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 6l6 6-6 6" />
              </svg>
            </button>
          </div>
        )}
      </div>
    </section>
  );
}

