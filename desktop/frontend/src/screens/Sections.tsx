import { useEffect, useState } from 'react';
import { bridge } from '../api/bridge';
import { DurationSlider } from '../components/DurationSlider';
import { ProgressBar } from '../components/ProgressBar';
import { isApiError, type Course, type ProgressEvent, type UsageStatus } from '../types';
import './sections.css';

type GenerationStage = Exclude<ProgressEvent['stage'], 'regenerate'>;

const STAGE_ORDER: GenerationStage[] = ['script', 'synthesize', 'render', 'subtitle'];
const STAGE_LABELS: Record<GenerationStage, string> = {
  script: 'Écriture du script',
  synthesize: 'Enregistrement de la voix',
  render: 'Montage de la vidéo',
  subtitle: 'Sous-titres',
};

/** Part de chaque étape dans le temps total : la barre doit avancer de façon
 *  continue d'un bout à l'autre, sans reculer en changeant d'étape. */
const STAGE_WEIGHTS: Record<GenerationStage, number> = {
  script: 0.40,
  synthesize: 0.35,
  render: 0.20,
  subtitle: 0.05,
};

function overallPercent(event: ProgressEvent | null): number {
  if (!event) return 0;
  // 'regenerate' n'arrive jamais ici (propre à l'écran Lecture) : l'index
  // négatif qui en résulterait est déjà géré juste en dessous.
  const index = STAGE_ORDER.indexOf(event.stage as GenerationStage);
  if (index < 0) return 0;
  const stage = event.stage as GenerationStage;
  const before = STAGE_ORDER.slice(0, index)
    .reduce((sum, s) => sum + STAGE_WEIGHTS[s], 0);
  const within = event.total > 0 ? Math.min(1, event.done / event.total) : 0;
  return (before + STAGE_WEIGHTS[stage] * within) * 100;
}

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
  const [subtitles, setSubtitles] = useState(false);
  const [usage, setUsage] = useState<UsageStatus | null>(null);
  // La progression ne doit jamais reculer, même si un évènement arrive
  // dans le désordre : on ne garde que le maximum atteint.
  const [maxPercent, setMaxPercent] = useState(0);

  useEffect(() => {
    if (!course) return;
    const next: Record<number, number> = {};
    for (const s of course.sections) next[s.index] = s.target_duration_s ?? s.estimated_duration_s;
    setLocalSeconds(next);
    setSubtitles(course.subtitles_enabled);
    // Réserve d'IA : prévenir AVANT une génération de plusieurs minutes vaut
    // mieux que de découvrir la limite à mi-parcours.
    bridge.usageStatus(course.id).then(setUsage).catch(() => setUsage(null));
  }, [course]);

  useEffect(() => {
    setMaxPercent((current) => Math.max(current, overallPercent(progress)));
  }, [progress]);

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

  async function handleSubtitlesChange(enabled: boolean) {
    setSubtitles(enabled);
    const result = await bridge.setSubtitles(course!.id, enabled);
    if (isApiError(result)) { setGenError(result.error); return; }
    onCourseUpdate(result);
  }

  async function handleGenerate() {
    setGenError(null);
    setGenerating(true);
    setMaxPercent(0);
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
    const stageIndex = progress ? STAGE_ORDER.indexOf(progress.stage as GenerationStage) : 0;
    return (
      <section className="screen-enter generating-view">
        <h1 className="hero">Lumio <span className="glow-text">travaille</span>…</h1>
        <p className="lede">Ça peut prendre quelques minutes — tu peux laisser la fenêtre ouverte en arrière-plan.</p>
        <div className="card generating-card">
          <div className="stage-steps">
            {STAGE_ORDER.filter((stage) => stage !== 'subtitle' || subtitles).map((stage) => {
              const i = STAGE_ORDER.indexOf(stage);
              return (
                <div key={stage} className={`stage-step${i < stageIndex ? ' done' : ''}${i === stageIndex ? ' active' : ''}`}>
                  {STAGE_LABELS[stage]}
                </div>
              );
            })}
          </div>
          {progress && (
            <ProgressBar
              label={progress.label}
              percent={maxPercent}
              counter={progress.total > 1 ? `${progress.done}/${progress.total}` : undefined}
            />
          )}
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

      {course.truncated && (
        <p className="warning-banner">
          Ce document est long : pour le découper en parties, Lumio s'est appuyé sur
          un extrait de chaque page. Toutes tes pages sont bien prises en compte, et
          la narration de chacune utilise son contenu complet.
        </p>
      )}

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

      {usage && usage.fits === false && (
        <p className="warning-banner">
          {usage.providers.length <= 1
            ? "Ta réserve d'intelligence artificielle gratuite du jour risque de ne pas suffire "
              + 'pour ce cours. Ajoute une deuxième clé dans Réglages pour doubler ta réserve '
              + '(gratuit), sinon la fin du cours sera de moins bonne qualité.'
            : "Ta réserve d'intelligence artificielle gratuite du jour risque de ne pas suffire "
              + 'pour ce cours. Tu peux réduire les durées, ajouter une clé de plus dans '
              + 'Réglages, ou reprendre demain — la réserve repart à zéro chaque jour.'}
        </p>
      )}

      <div className="card generate-bar">
        <div className="generate-left">
          <div className="total">Durée totale estimée : <strong>{formatDuration(totalSeconds)}</strong></div>
          <label className="subtitle-toggle">
            <input
              type="checkbox"
              checked={subtitles}
              onChange={(e) => handleSubtitlesChange(e.target.checked)}
            />
            <span>Ajouter des sous-titres <em>(plus long à générer)</em></span>
          </label>
        </div>
        <button className="btn-primary" type="button" onClick={handleGenerate}>Générer la vidéo</button>
      </div>
    </section>
  );
}
