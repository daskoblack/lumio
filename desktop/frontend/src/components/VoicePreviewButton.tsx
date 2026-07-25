import { useRef, useState } from 'react';
import { bridge } from '../api/bridge';
import { isApiError } from '../types';
import './voice-preview-button.css';

export function VoicePreviewButton({ voiceId }: { voiceId: string }) {
  const [state, setState] = useState<'idle' | 'loading' | 'playing'>('idle');
  const audioRef = useRef<HTMLAudioElement | null>(null);

  async function handleClick() {
    if (state === 'loading') return;
    if (state === 'playing') {
      audioRef.current?.pause();
      setState('idle');
      return;
    }
    setState('loading');
    const result = await bridge.previewVoice(voiceId);
    if (isApiError(result)) {
      setState('idle');
      return;
    }
    const audio = new Audio(result.audio);
    audioRef.current = audio;
    audio.onended = () => setState('idle');
    audio.play();
    setState('playing');
  }

  return (
    <button
      type="button"
      className="voice-preview-btn"
      onClick={handleClick}
      disabled={state === 'loading'}
      aria-label={state === 'playing' ? 'Arrêter' : 'Tester la voix'}
      title={state === 'playing' ? 'Arrêter' : 'Tester la voix'}
    >
      {state === 'loading' ? (
        <span className="voice-preview-spinner" />
      ) : state === 'playing' ? (
        <svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="5" width="4" height="14" rx="1" /><rect x="14" y="5" width="4" height="14" rx="1" /></svg>
      ) : (
        <svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7Z" /></svg>
      )}
    </button>
  );
}
