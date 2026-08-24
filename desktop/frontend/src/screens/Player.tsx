import { useEffect, useRef, useState } from 'react';
import { bridge } from '../api/bridge';
import { ProgressBar } from '../components/ProgressBar';
import { isApiError, type Course, type ProgressEvent } from '../types';
import { friendlyError } from '../friendlyError';
import './player.css';

function formatDuration(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = Math.round(totalSeconds % 60);
  return m > 0 ? `${m}m ${String(s).padStart(2, '0')}` : `${s}s`;
}

export function Player({
  course, onCourseUpdate, onBack,
}: {
  course: Course | null;
  onCourseUpdate: (c: Course) => void;
  onBack: () => void;
}) {
  const [videoSrc, setVideoSrc] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [instructions, setInstructions] = useState<Record<number, string>>({});
  const [regenerating, setRegenerating] = useState<number | null>(null);
  const [progress, setProgress] = useState<ProgressEvent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (!course) return;
    bridge.videoUrl(course.id).then(setVideoSrc);
  }, [course?.id]);

  if (!course) {
    return (
      <section className="screen-enter">
        <h1 className="hero">Aucune vidéo à afficher</h1>
        <p className="lede">Retourne à l'accueil ou à tes vidéos pour en choisir une.</p>
      </section>
    );
  }

  // Capturé après le garde ci-dessus : TypeScript ne rétrécit pas `course`
  // (potentiellement null) à l'intérieur des fonctions imbriquées définies
  // plus bas, même si elles ne sont créées qu'après ce point.
  const courseId = course.id;

  const starts: number[] = [];
  let cursor = 0;
  for (const s of course.sections) {
    starts.push(cursor);
    cursor += s.actual_duration_s ?? 0;
  }

  function seekTo(seconds: number) {
    if (videoRef.current) videoRef.current.currentTime = seconds;
  }

  async function handleRegenerate(sectionIndex: number) {
    const instruction = (instructions[sectionIndex] ?? '').trim();
    if (!instruction) {
      setError('Décris ce que tu veux changer pour cette partie avant de régénérer.');
      return;
    }
    setError(null);
    setRegenerating(sectionIndex);
    const unsubscribe = bridge.onProgress((e) => {
      if (e.stage === 'regenerate') setProgress(e);
    });
    try {
      const result = await bridge.regenerateSection(courseId, sectionIndex, instruction);
      if (isApiError(result)) { setError(friendlyError(result.error)); return; }
      onCourseUpdate(result);
      const url = await bridge.videoUrl(courseId);
      setVideoSrc(url);
      setRefreshKey((k) => k + 1);  // casse le cache : même nom de fichier, nouveau contenu
      setInstructions((prev) => ({ ...prev, [sectionIndex]: '' }));
    } catch (e) {
      setError(friendlyError(String(e)));
    } finally {
      unsubscribe();
      setRegenerating(null);
      setProgress(null);
    }
  }

  return (
    <section className="screen-enter player-view">
      <button type="button" className="btn-ghost player-back" onClick={onBack}>← Retour</button>
      <h1 className="hero">{course.title}</h1>

      <div className="card player-video-card">
        {videoSrc ? (
          <video
            ref={videoRef}
            key={refreshKey}
            src={`${videoSrc}?v=${refreshKey}`}
            controls
            className="player-video"
          />
        ) : (
          <p className="lede">Vidéo en cours de chargement…</p>
        )}
      </div>

      {error && <p className="home-error">{error}</p>}

      <p className="lede player-sections-lede">
        Une partie ne te convient pas ? Décris ce que tu veux changer, uniquement pour cette partie.
      </p>

      <div className="section-list">
        {course.sections.map((s, i) => {
          const isRegeneratingThis = regenerating === i;
          const isBusy = regenerating !== null;
          return (
            <div className="card player-sec-card" key={s.id}>
              <div className="sec-info">
                <button type="button" className="player-timestamp" onClick={() => seekTo(starts[i])}>
                  {formatDuration(starts[i])}
                </button>
                <h3>{s.title}</h3>
                <div className="meta">
                  {s.slide_ids.length} page{s.slide_ids.length > 1 ? 's' : ''} · {formatDuration(s.actual_duration_s ?? 0)}
                </div>
              </div>
              <div className="player-regen">
                <textarea
                  className="player-instruction"
                  placeholder="Ex. : sois plus concis, utilise un exemple avec des fruits…"
                  value={instructions[i] ?? ''}
                  onChange={(e) => setInstructions((prev) => ({ ...prev, [i]: e.target.value }))}
                  disabled={isBusy}
                  rows={2}
                />
                <button
                  type="button"
                  className="btn-ghost"
                  onClick={() => handleRegenerate(i)}
                  disabled={isBusy}
                >
                  {isRegeneratingThis ? 'Régénération…' : 'Régénérer cette partie'}
                </button>
                {isRegeneratingThis && progress && (
                  <ProgressBar
                    label={progress.label}
                    percent={progress.total > 0 ? (progress.done / progress.total) * 100 : 0}
                    counter={`${progress.done}/${progress.total}`}
                  />
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
