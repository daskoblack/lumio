import { useId, useRef, type ChangeEvent } from 'react';
import './duration-slider.css';

function formatDuration(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = Math.round(totalSeconds % 60);
  return m > 0 ? `${m}m ${String(s).padStart(2, '0')}` : `${s}s`;
}

export function DurationSlider({
  label,
  seconds,
  isAuto,
  min = 15,
  max = 1800,  // 30 minutes
  onChange,
  onCommit,
}: {
  label: string;
  seconds: number;
  isAuto: boolean;
  min?: number;
  max?: number;
  /** Appelé à chaque déplacement (retour visuel immédiat, pas d'écriture disque). */
  onChange: (seconds: number) => void;
  /** Appelé au relâchement du curseur : c'est là qu'on persiste vraiment la valeur. */
  onCommit: (seconds: number) => void;
}) {
  const id = useId();
  // La valeur courante à committer au relâchement (évite un rendu React entre-temps).
  const pendingRef = useRef(seconds);
  pendingRef.current = seconds;

  // Le curseur doit pouvoir représenter une valeur au-delà de son maximum par défaut
  // (ex. estimation automatique très longue) sans se couper.
  const effectiveMax = Math.max(max, Math.ceil(seconds / 15) * 15);

  function handleInput(e: ChangeEvent<HTMLInputElement>) {
    const value = Number(e.target.value);
    pendingRef.current = value;
    onChange(value);
  }

  function commit() {
    onCommit(pendingRef.current);
  }

  return (
    <div className="duration-control">
      <div className="duration-top">
        <span className="duration-value">{formatDuration(seconds)}</span>
        <span className={`mode-pill${isAuto ? ' auto' : ''}`}>
          {isAuto ? 'Automatique' : 'Choisie'}
        </span>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={effectiveMax}
        step={5}
        value={Math.round(seconds)}
        aria-label={label}
        onChange={handleInput}
        onMouseUp={commit}
        onTouchEnd={commit}
        onKeyUp={commit}
      />
    </div>
  );
}
