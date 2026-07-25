import { useEffect, useState } from 'react';
import { bridge } from '../api/bridge';
import { VoicePreviewButton } from '../components/VoicePreviewButton';
import type { Voice } from '../types';
import './settings.css';

export function Settings() {
  const [apiKey, setApiKey] = useState('');
  const [voiceId, setVoiceId] = useState('');
  const [voices, setVoices] = useState<Voice[]>([]);
  const [showKey, setShowKey] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    bridge.getSettings().then((s) => { setApiKey(s.groq_api_key); setVoiceId(s.voice_id); });
    bridge.listVoices().then(setVoices);
  }, []);

  async function handleSave() {
    await bridge.saveSettings(apiKey, voiceId);
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  }

  return (
    <section className="screen-enter">
      <h1 className="hero"><span className="glow-text">Réglages</span></h1>
      <p className="lede">Tu peux changer ces informations à tout moment.</p>

      <div className="settings-grid">
        <div className="card field-card">
          <label htmlFor="api-key">Clé Groq (gratuite)</label>
          <p className="hint">
            Récupère-la sur{' '}
            <a className="link" href="https://console.groq.com/keys" target="_blank" rel="noreferrer">
              console.groq.com
            </a>
            , puis colle-la ici.
          </p>
          <div className="field-input-wrap">
            <input
              className="field-input inset"
              id="api-key"
              type={showKey ? 'text' : 'password'}
              value={apiKey}
              placeholder="Colle ta clé ici"
              onChange={(e) => setApiKey(e.target.value)}
            />
            <button
              className="reveal-btn"
              type="button"
              aria-label={showKey ? 'Cacher la clé' : 'Afficher la clé'}
              onClick={() => setShowKey((v) => !v)}
            >
              <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" />
                <circle cx="12" cy="12" r="3" />
              </svg>
            </button>
          </div>
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
