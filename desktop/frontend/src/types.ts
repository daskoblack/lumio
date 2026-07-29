// Reflète lectio/core/models.py (sérialisé en JSON par Course.model_dump(mode="json")).

export type CourseStatus =
  | 'created' | 'extracted' | 'analyzed' | 'scripted'
  | 'synthesized' | 'rendered' | 'done' | 'failed';

export type SectionKind = 'intro' | 'concept' | 'example' | 'exercise' | 'summary' | 'other';

export interface Script {
  slide_id: string;
  text: string;
  word_count_target: number | null;
  word_count_actual: number;
  generation_pass: number;
  audio_path: string | null;
  audio_duration_s: number | null;
}

export interface Slide {
  id: string;
  index: number;
  source_page: number;
  title: string;
  rendered_path: string | null;
  estimated_narration_words: number;
  estimated_duration_s: number;
  actual_duration_s: number | null;
  script: Script | null;
}

export interface Section {
  id: string;
  index: number;
  kind: SectionKind;
  title: string;
  summary: string;
  slide_ids: string[];
  estimated_narration_words: number;
  target_duration_s: number | null;
  estimated_duration_s: number;
  actual_duration_s: number | null;
  duration_deviation: number | null;
  synthesis_note: string | null;
}

export interface Course {
  id: string;
  title: string;
  source_pdf: string;
  language: string;
  voice_profile_id: string;
  status: CourseStatus;
  truncated: boolean;
  slides: Slide[];
  sections: Section[];
}

export interface Voice {
  id: string;
  gender: string;
  locale: string;
}

/** Identifiants des fournisseurs d'IA, dans l'ordre de la chaîne de repli. */
export const LLM_PROVIDERS = ['groq', 'cerebras', 'gemini', 'mistral'] as const;
export type LlmProvider = (typeof LLM_PROVIDERS)[number];

export interface Settings {
  groq_api_key: string;
  cerebras_api_key: string;
  gemini_api_key: string;
  mistral_api_key: string;
  voice_id: string;
}

export interface LlmStatus {
  /** Étiquettes « fournisseur/modèle » réellement utilisables. */
  configured: string[];
  error: string | null;
}

export interface ProgressEvent {
  stage: 'script' | 'synthesize' | 'render' | 'subtitle';
  label: string;
  done: number;
  total: number;
}

export interface ApiError {
  error: string;
}

export function isApiError(x: unknown): x is ApiError {
  return typeof x === 'object' && x !== null && 'error' in x;
}
