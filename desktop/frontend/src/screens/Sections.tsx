import { useEffect, useState } from 'react';
import { bridge } from '../api/bridge';
import { DurationSlider } from '../components/DurationSlider';
import { ProgressBar } from '../components/ProgressBar';
import { isApiError, type Course, type ProgressEvent } from '../types';
import './sections.css';

const STAGE_ORDER: ProgressEvent['stage'][] = ['script', 'synthesize', 'render', 'subtitle'];
const STAGE_LABELS: Record<ProgressEvent['stage'], string> = {
  script: 'Écriture du script',
  synthesize: 'Enregistrement de la voix',
  render: 'Montage de la vidéo',
  subtitle: 'Sous-titres',
};

function formatDuration(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = Math.round(totalSeconds % 60);
  return m > 0 ? `${m}m ${String(s).padStart(2, '0')}` : `${s}s`;
}

export function Sections({
  course, onCourseUpdate, onFinished,
}: {
  course: Course | null;
  onCourseUpdate: (c: Course) => void;
  onFinished: () => void;
}) {
  const [localSeconds, setLocalSeconds] = useState<Record<number, number>>({});
  const [generating, setGenerating] = useState(false);
  const [progress, setProgress] = useState<ProgressEvent | null>(null);
  const [genError, setGenError] = useState<string | null>(null);

  useEffect(() => {
    if (!course) return;
    const next: Record<number, number> = {};
    for (const s of course.sections) next[s.index] = s.target_duration_s ?? s.estimated_duration_s;
    setLocalSeconds(next);
  }, [course]);

  if (!course) {
    return (
      <section className="screen-enter">
        <h1 className="hero">Aucun cours pour l'instant</h1>
        <p className="lede">Retourne à l'accueil pour déposer un PDF.</p>
      </section>
    );
  }

  async function commitDuration(sectionIndex: number, seconds: number | null) {
    const result = await bridge.setDurations(course!.id, [sectionIndex], seconds);
    if (isApiError(result)) { setGenError(result.error); return; }
    onCourseUpdate(result);
  }

  async function handleGenerate() {
    setGenError(null);
    setGenerating(true);
    setProgress({ stage: 'script', label: 'Préparation…', done: 0, total: 1 });
    const unsubscribe = bridge.onProgress(setProgress);
    try {
      let current = course!;
      if (current.status === 'analyzed') {
        const scripted = await bridge.runScript(current.id);
        if (isApiError(scripted)) { setGenError(scripted.error); return; }
        current = scripted;
        onCourseUpdate(current);
      }
      const built = await bridge.runBuild(current.id);
      if (isApiError(built)) { setGenError(built.error); return; }
      onCourseUpdate(built);
      onFinished();
    } finally {
      unsubscribe();
      setGenerating(false);
    }
  }

  const totalSeconds = course.sections.reduce(
    (sum, s) => sum + (localSeconds[s.index] ?? s.estimated_duration_s), 0,
  );

  if (generating) {
    const stageIndex = progress ? STAGE_ORDER.indexOf(progress.stage) : 0;
    return (
      <section className="screen-enter generating-view">
        <h1 className="hero">Lumio <span className="glow-text">travaille</span>…</h1>
        <p className="lede">Ça peut prendre quelques minutes — tu peux laisser la fenêtre ouverte en arrière-plan.</p>
        <div className="card generating-card">
          <div className="stage-steps">
            {STAGE_ORDER.map((stage, i) => (
              <div key={stage} className={`stage-step${i < stageIndex ? ' done' : ''}${i === stageIndex ? ' active' : ''}`}>
                {STAGE_LABELS[stage]}
              </div>
            ))}
          </div>
          {progress && <ProgressBar label={progress.label} done={progress.done} total={progress.total} />}
        </div>
      </section>
    );
  }

  return (
    <section className="screen-enter">
      <h1 className="hero">Combien de <span className="glow-text">temps</span> pour chaque partie ?</h1>
      <p className="lede">
        Laisse « Automatique » si tu ne sais pas encore, ou glisse le curseur pour choisir
        une durée précise : Lumio adapte le texte pour la respecter.
      </p>

      <div className="section-list">
        {course.sections.map((s) => {
          const seconds = localSeconds[s.index] ?? s.estimated_duration_s;
          const isAuto = s.target_duration_s === null;
          return (
            <div className="card sec-card" key={s.id}>
              <div className="sec-info">
                <div className="seq">Partie {s.index + 1} sur {course.sections.length}</div>
                <h3>{s.title}</h3>
                <div className="meta">
                  {s.slide_ids.length} page{s.slide_ids.length > 1 ? 's' : ''} · environ {formatDuration(s.estimated_duration_s)}
                </div>
                {s.synthesis_note && <div className="note">⚠ {s.synthesis_note}</div>}
              </div>
              <div className="sec-duration">
                <DurationSlider
                  label={`Durée de la partie ${s.index + 1}`}
                  seconds={seconds}
                  isAuto={isAuto}
                  onChange={(v) => setLocalSeconds((prev) => ({ ...prev, [s.index]: v }))}
                  onCommit={(v) => commitDuration(s.index, v)}
                />
                {!isAuto && (
                  <button type="button" className="reset-auto" onClick={() => commitDuration(s.index, null)}>
                    Repasser en automatique
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {genError && <p className="home-error">{genError}</p>}

      <div className="card generate-bar">
        <div className="total">Durée totale estimée : <strong>{formatDuration(totalSeconds)}</strong></div>
        <button className="btn-primary" type="button" onClick={handleGenerate}>Générer la vidéo</button>
      </div>
    </section>
  );
}
