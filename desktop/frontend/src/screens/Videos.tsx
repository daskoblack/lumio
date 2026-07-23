import { useEffect, useState } from 'react';
import { bridge } from '../api/bridge';
import type { Course, CourseStatus } from '../types';
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

export function Videos({ onResume }: { onResume: (course: Course) => void }) {
  const [jobs, setJobs] = useState<Course[] | null>(null);

  useEffect(() => {
    bridge.listJobs().then((list) => setJobs([...list].reverse()));
  }, []);

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
              <h3>{job.title}</h3>
              <span className={`status-pill${job.status === 'done' ? ' done' : ''}`}>
                {STATUS_LABELS[job.status]}
              </span>
            </div>
            {job.status === 'done' ? (
              <button className="btn-primary" type="button" onClick={() => bridge.openOutputFolder(job.id)}>
                Ouvrir le dossier
              </button>
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
