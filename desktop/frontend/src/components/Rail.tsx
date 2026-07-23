import type { ReactElement } from 'react';
import './rail.css';

export type ScreenId = 'home' | 'sections' | 'videos' | 'settings';

const ICONS: Record<ScreenId, ReactElement> = {
  home: (
    <path d="M3 11.5 12 4l9 7.5M5 10v9a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1v-9" />
  ),
  sections: (
    <>
      <rect x="4" y="5" width="16" height="14" rx="2" />
      <path d="M4 10h16M9 10v9" />
    </>
  ),
  videos: (
    <>
      <rect x="3" y="6" width="13" height="12" rx="2" />
      <path d="M16 10l5-3v10l-5-3" />
    </>
  ),
  settings: (
    <>
      <circle cx="12" cy="12" r="3.2" />
      <path d="M19.4 13.9a7.6 7.6 0 0 0 0-3.8l2-1.5-2-3.4-2.3.9a7.6 7.6 0 0 0-3.3-1.9L13.4 2h-2.8l-.4 2.2a7.6 7.6 0 0 0-3.3 1.9l-2.3-.9-2 3.4 2 1.5a7.6 7.6 0 0 0 0 3.8l-2 1.5 2 3.4 2.3-.9a7.6 7.6 0 0 0 3.3 1.9l.4 2.2h2.8l.4-2.2a7.6 7.6 0 0 0 3.3-1.9l2.3.9 2-3.4-2-1.5Z" />
    </>
  ),
};

const LABELS: Record<ScreenId, string> = {
  home: 'Accueil',
  sections: 'Sections',
  videos: 'Vidéos',
  settings: 'Réglages',
};

export function Rail({ active, onNavigate }: { active: ScreenId; onNavigate: (s: ScreenId) => void }) {
  return (
    <nav className="rail" aria-label="Navigation principale">
      <div className="rail-mark" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none">
          <path
            d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"
            stroke="#14131c" strokeWidth="2" strokeLinecap="round"
          />
          <circle cx="12" cy="12" r="4.5" fill="#14131c" />
        </svg>
      </div>

      {(['home', 'sections'] as ScreenId[]).map((id) => (
        <RailButton key={id} id={id} active={active === id} onNavigate={onNavigate} />
      ))}
      <RailButton id="videos" active={active === 'videos'} onNavigate={onNavigate} />
      <div className="rail-spacer" />
      <RailButton id="settings" active={active === 'settings'} onNavigate={onNavigate} />
    </nav>
  );
}

function RailButton({
  id, active, onNavigate,
}: { id: ScreenId; active: boolean; onNavigate: (s: ScreenId) => void }) {
  return (
    <button
      type="button"
      className="rail-btn"
      aria-current={active ? 'page' : undefined}
      onClick={() => onNavigate(id)}
    >
      <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        {ICONS[id]}
      </svg>
      <span className="rail-label">{LABELS[id]}</span>
    </button>
  );
}
