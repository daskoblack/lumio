// Enveloppe typée autour de window.pywebview.api (exposé par desktop/app/api.py).
// pywebview injecte `window.pywebview` un peu après le chargement de la page :
// `ready()` attend cet événement avant le premier appel.

import type { ApiError, Course, LlmStatus, ProgressEvent, Settings, Voice } from '../types';

declare global {
  interface Window {
    pywebview?: { api: PywebviewApi };
    __lumioProgress?: (event: ProgressEvent) => void;
  }
}

// Tout appel qui touche à un job peut renvoyer {error: "..."} côté Python
// (job introuvable, clé API absente, échec FFmpeg...) : jamais juste `Course`.
type CourseResult = Course | ApiError;

type PreviewVoiceResult = { audio: string } | ApiError;

interface PywebviewApi {
  get_settings(): Promise<Settings>;
  save_settings(updates: Record<string, string> | null, voice_id: string | null): Promise<Settings>;
  llm_status(): Promise<LlmStatus>;
  list_voices(): Promise<Voice[]>;
  preview_voice(voice_id: string): Promise<PreviewVoiceResult>;
  pick_pdf_file(): Promise<string | null>;
  analyze(pdf_path: string, voice_id: string | null, title: string | null): Promise<CourseResult>;
  set_durations(job_id: string, section_indices: number[], duration_s: number | null): Promise<CourseResult>;
  set_subtitles(job_id: string, enabled: boolean): Promise<CourseResult>;
  run_script(job_id: string): Promise<CourseResult>;
  run_synthesize(job_id: string): Promise<CourseResult>;
  run_render(job_id: string): Promise<CourseResult>;
  run_subtitle(job_id: string): Promise<CourseResult>;
  run_build(job_id: string): Promise<CourseResult>;
  get_job(job_id: string): Promise<CourseResult>;
  list_jobs(): Promise<Course[]>;
  open_output_folder(job_id: string): Promise<void>;
}

let readyPromise: Promise<void> | null = null;

function ready(): Promise<void> {
  if (window.pywebview) return Promise.resolve();
  if (!readyPromise) {
    readyPromise = new Promise((resolve) => {
      window.addEventListener('pywebviewready', () => resolve(), { once: true });
    });
  }
  return readyPromise;
}

async function api(): Promise<PywebviewApi> {
  await ready();
  return window.pywebview!.api;
}

export const bridge = {
  getSettings: async () => (await api()).get_settings(),
  saveSettings: async (updates: Record<string, string> | null, voiceId: string | null) =>
    (await api()).save_settings(updates, voiceId),
  llmStatus: async () => (await api()).llm_status(),
  listVoices: async () => (await api()).list_voices(),
  previewVoice: async (voiceId: string) => (await api()).preview_voice(voiceId),
  pickPdfFile: async () => (await api()).pick_pdf_file(),
  analyze: async (pdfPath: string, voiceId: string | null, title: string | null) =>
    (await api()).analyze(pdfPath, voiceId, title),
  setDurations: async (jobId: string, sectionIndices: number[], durationS: number | null) =>
    (await api()).set_durations(jobId, sectionIndices, durationS),
  setSubtitles: async (jobId: string, enabled: boolean) =>
    (await api()).set_subtitles(jobId, enabled),
  runScript: async (jobId: string) => (await api()).run_script(jobId),
  runSynthesize: async (jobId: string) => (await api()).run_synthesize(jobId),
  runRender: async (jobId: string) => (await api()).run_render(jobId),
  runSubtitle: async (jobId: string) => (await api()).run_subtitle(jobId),
  runBuild: async (jobId: string) => (await api()).run_build(jobId),
  getJob: async (jobId: string) => (await api()).get_job(jobId),
  listJobs: async () => (await api()).list_jobs(),
  openOutputFolder: async (jobId: string) => (await api()).open_output_folder(jobId),

  /** S'abonne aux événements de progression envoyés depuis Python. */
  onProgress(handler: (event: ProgressEvent) => void): () => void {
    window.__lumioProgress = handler;
    return () => { window.__lumioProgress = undefined; };
  },
};
