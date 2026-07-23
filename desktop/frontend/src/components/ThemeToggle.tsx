import { useEffect, useState } from 'react';

function currentIsDark(): boolean {
  const attr = document.documentElement.getAttribute('data-theme');
  if (attr === 'dark') return true;
  if (attr === 'light') return false;
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

export function ThemeToggle() {
  const [isDark, setIsDark] = useState(currentIsDark);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
  }, [isDark]);

  return (
    <button type="button" className="btn-ghost" onClick={() => setIsDark((v) => !v)}>
      {isDark ? 'Mode clair' : 'Mode sombre'}
    </button>
  );
}
