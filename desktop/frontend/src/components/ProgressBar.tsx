import './progress-bar.css';

export function ProgressBar({
  label, done, total,
}: { label: string; done: number; total: number }) {
  const pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
  return (
    <div className="progress-wrap">
      <div className="progress-label">
        <span>{label}</span>
        <span className="progress-count">{done}/{total}</span>
      </div>
      <div className="progress-track">
        <div className="progress-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
