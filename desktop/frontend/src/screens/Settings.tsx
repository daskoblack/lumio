import { useEffect, useState } from 'react';
import { bridge } from '../api/bridge';
import { VoicePreviewButton } from '../components/VoicePreviewButton';
import { LLM_PROVIDERS, type LlmProvider, type LlmStatus, type UsageStatus, type Voice } from '../types';
import './settings.css';

/** Ce que l'utilisateur doit savoir sur chaque fournisseur, sans jargon. */
const PROVIDER_INFO: Record<LlmProvider, { name: string; url: string; note: string }> = {
  groq: {
    name: 'Groq',
    url: 'https://console.groq.com/keys',
    note: "Le plus rapide. Gratuit, mais sa réserve du jour s'épuise vite sur un long cours.",
  },
  cerebras: {
    name: 'Cerebras',
    url: 'https://cloud.cerebras.ai',
    note: 'Gratuit, avec une réserve quotidienne dix fois plus grande. Recommandé en secours.',
  },
  gemini: {
    name: 'Gemini (Google)',
    url: 'https://aistudio.google.com/apikey',
    note: 'Gratuit, réserve quotidienne confortable.',
  },
  mistral: {
    name: 'Mistral',
    url: 'https://console.mistral.ai/api-keys',
    note: 'Gratuit, français. Dernier filet de sécurité.',
  },
};

export function Settings() {
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [voiceId, setVoiceId] = useState('');
  const [voices, setVoices] = useState<Voice[]>([]);
  const [shown, setShown] = useState<Record<string, boolean>>({});
  const [status, setStatus] = useState<LlmStatus | null>(null);
  const [usage, setUsage] = useState<UsageStatus | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    bridge.getSettings().then((s) => {
      setKeys(Object.fromEntries(
        LLM_PROVIDERS.map((p) => [p, (s as unknown as Record<string, string>)[`${p}_api_key`] ?? '']),
      ));
      setVoiceId(s.voice_id);
    });
    bridge.listVoices().then(setVoices);
    bridge.llmStatus().then(setStatus);
    bridge.usageStatus().then(setUsage).catch(() => setUsage(null));
  }, []);

  async function handleSave() {
    const updates: Record<string, string> = {};
    for (const p of LLM_PROVIDERS) updates[`${p}_api_key`] = keys[p] ?? '';
    await bridge.saveSettings(updates, voiceId);
    setStatus(await bridge.llmStatus());
    setUsage(await bridge.usageStatus().catch(() => null));
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  }

  const activeCount = status?.configured.length ?? 0;

  return (
    <section className="screen-enter">
      <h1 className="hero"><span className="glow-text">Réglages</span></h1>
      <p className="lede">Tu peux changer ces informations à tout moment.</p>

      <div className="settings-grid">
        <div className="card field-card">
          <label>Intelligences artificielles</label>
          <p className="hint">
            Ces codes gratuits permettent à Lumio d'écrire tes cours. Renseignes-en{' '}
            <strong>au moins un</strong>. Si tu en mets plusieurs, Lumio passe
            automatiquement au suivant quand le premier a épuisé sa réserve du jour,
            au lieu de s'arrêter en pleine génération.
          </p>

          {LLM_PROVIDERS.map((provider) => {
            const info = PROVIDER_INFO[provider];
            const field = `${provider}_api_key`;
            return (
              <div className="provider-block" key={provider}>
                <div className="provider-head">
                  <label htmlFor={field}>{info.name}</label>
                  <a className="link" href={info.url} target="_blank" rel="noreferrer">
                    obtenir un code
                  </a>
                </div>
                <p className="provider-note">{info.note}</p>
                <div className="field-input-wrap">
                  <input
                    className="field-input inset"
                    id={field}
                    type={shown[provider] ? 'text' : 'password'}
                    value={keys[provider] ?? ''}
                    placeholder="Colle le code ici (optionnel)"
                    onChange={(e) => setKeys((k) => ({ ...k, [provider]: e.target.value }))}
                  />
                  <button
                    className="reveal-btn"
                    type="button"
                    aria-label={shown[provider] ? 'Cacher le code' : 'Afficher le code'}
                    onClick={() => setShown((s) => ({ ...s, [provider]: !s[provider] }))}
                  >
                    <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  </button>
                </div>
              </div>
            );
          })}

          <div className={`llm-status${activeCount === 0 ? ' empty' : ''}`}>
            {activeCount === 0
              ? "Aucune intelligence artificielle configurée : Lumio ne pourra pas écrire de cours."
              : `${activeCount} option${activeCount > 1 ? 's' : ''} disponible${activeCount > 1 ? 's' : ''} — Lumio bascule tout seul si la réserve du jour s'épuise.`}
          </div>

          {usage && activeCount > 0 && (
            <div className="usage-panel">
              <div className="usage-bar" aria-hidden="true">
                <div
                  className="usage-fill"
                  style={{ width: `${Math.min(100, Math.round((usage.used_today / usage.capacity) * 100))}%` }}
                />
              </div>
              <p className="usage-text">
                Réserve du jour utilisée à environ{' '}
                <strong>{Math.min(100, Math.round((usage.used_today / usage.capacity) * 100))} %</strong>
                {' — '}
                {(() => {
                  const restants = Math.floor((usage.capacity - usage.used_today) / 55_000);
                  if (restants <= 0) return "il n'y a plus de quoi produire un cours entier aujourd'hui.";
                  if (restants === 1) return 'de quoi produire encore environ un cours de 40 pages.';
                  return `de quoi produire encore environ ${restants} cours de 40 pages.`;
                })()}
              </p>
              <p className="usage-hint">
                {activeCount < 4
                  ? `Chaque clé supplémentaire agrandit cette réserve. Il t'en reste ${4 - activeCount} à ajouter, toutes gratuites.`
                  : 'Toutes les clés sont configurées : ta réserve est au maximum.'}
                {' '}Elle repart à zéro chaque jour.
              </p>
            </div>
          )}
        </div>

        <div className="card field-card">
          <label htmlFor="voice-select">Voix</label>
          <p className="hint">La voix qui racontera tes cours.</p>
          <div className="voice-row">
            <div className="select-fake inset">
              <select id="voice-select" value={voiceId} onChange={(e) => setVoiceId(e.target.value)}>
                {voices.map((v) => (
                  <option key={v.id} value={v.id}>{v.id.replace(/^fr-\w+-/, '')} ({v.locale})</option>
                ))}
              </select>
            </div>
            {voiceId && <VoicePreviewButton voiceId={voiceId} />}
          </div>
        </div>

        <div className="save-row">
          <button className="btn-primary" type="button" onClick={handleSave}>Enregistrer</button>
          {saved && (
            <span className="status-chip"><span className="dot" />Enregistré</span>
          )}
        </div>
      </div>
    </section>
  );
}
