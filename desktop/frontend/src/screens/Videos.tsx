import { useEffect, useState } from 'react';
import { bridge } from '../api/bridge';
import { isApiError, type Course, type CourseStatus } from '../types';
import './videos.css';

const STATUS_LABELS: Record<CourseStatus, string> = {
  created: 'À configurer',
  extracted: 'À configurer',
  analyzed: 'Durées à régler',
  scripted: 'Script prêt',
  synthesized: 'Voix enregistrée',
  rendered: 'Sous-titres en attente',
  done: 'Terminé',
  failed: 'Erreur',
};

function VideoTitle({ job, onRenamed }: { job: Course; onRenamed: (c: Course) => void }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(job.title);

  useEffect(() => { setValue(job.title); }, [job.title]);

  async function commit() {
    setEditing(false);
    const trimmed = value.trim();
    if (!trimmed || trimmed === job.title) { setValue(job.title); return; }
    const result = await bridge.renameCourse(job.id, trimmed);
    if (isApiError(result)) { setValue(job.title); return; }
    onRenamed(result);
  }

  if (editing) {
    return (
      <input
        className="video-title-input"
        value={value}
        autoFocus
        onFocus={(e) => e.currentTarget.select()}
        onChange={(e) => setValue(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') (e.currentTarget as HTMLInputElement).blur();
          if (e.key === 'Escape') { setValue(job.title); setEditing(false); }
        }}
      />
    );
  }

  return (
    <h3 className="video-title" onClick={() => setEditing(true)} title="Cliquer pour renommer">
      {job.title}
      <span className="video-title-edit-hint" aria-hidden="true">✎</span>
    </h3>
  );
}

export function Videos({
  onResume, onWatch,
}: {
  onResume: (course: Course) => void;
  onWatch: (course: Course) => void;
}) {
  const [jobs, setJobs] = useState<Course[] | null>(null);

  useEffect(() => {
    bridge.listJobs().then((list) => setJobs([...list].reverse()));
  }, []);

  function updateJob(updated: Course) {
    setJobs((prev) => prev?.map((j) => (j.id === updated.id ? updated : j)) ?? prev);
  }

  return (
    <section className="screen-enter">
      <h1 className="hero">Tes <span className="glow-text">vidéos</span></h1>
      <p className="lede">Retrouve ici tous les cours que tu as commencés ou terminés.</p>

      {jobs === null && <p className="lede">Chargement…</p>}
      {jobs && jobs.length === 0 && (
        <div className="card empty-card">Aucun cours pour l'instant — dépose un PDF depuis l'accueil.</div>
      )}

      <div className="video-list">
        {jobs?.map((job) => (
          <div className="card video-card" key={job.id}>
            <div className="video-info">
              <VideoTitle job={job} onRenamed={updateJob} />
              <span className={`status-pill${job.status === 'done' ? ' done' : ''}`}>
                {STATUS_LABELS[job.status]}
              </span>
              {job.degraded_pages.length > 0 && (
                <ul className="degraded-list">
                  {job.degraded_pages.slice(0, 3).map((msg, i) => (
                    <li key={i}>⚠ {msg}</li>
                  ))}
                  {job.degraded_pages.length > 3 && (
                    <li>+ {job.degraded_pages.length - 3} autre(s) avertissement(s)</li>
                  )}
                </ul>
              )}
            </div>
            {job.status === 'done' ? (
              <div className="video-actions">
                <button className="btn-ghost" type="button" onClick={() => onWatch(job)}>
                  Voir / Modifier
                </button>
                <button className="btn-primary" type="button" onClick={() => bridge.openOutputFolder(job.id)}>
                  Ouvrir le dossier
                </button>
              </div>
            ) : (
              <button className="btn-ghost" type="button" onClick={() => onResume(job)}>
                Reprendre
              </button>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
