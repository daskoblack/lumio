import './progress-bar.css';

export function ProgressBar({
  label, percent, counter,
}: {
  label: string;
  /** Avancement global 0-100. Ne doit jamais reculer d'une étape à l'autre. */
  percent: number;
  /** Détail facultatif affiché à droite (ex. « page 12 / 20 »). */
  counter?: string;
}) {
  const clamped = Math.max(0, Math.min(100, Math.round(percent)));
  return (
    <div className="progress-wrap">
      <div className="progress-label">
        <span>{label}</span>
        <span className="progress-count">{counter ?? `${clamped} %`}</span>
      </div>
      <div
        className="progress-track"
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="progress-fill" style={{ width: `${clamped}%` }} />
      </div>
    </div>
  );
}
