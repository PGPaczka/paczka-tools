/**
 * Plan i jego wykonanie: `/api/plan/*` wraz z bramką, drzewem, konfliktami
 * oraz uruchamianiem etapów (`/api/plan/{...}/run`, `/api/pipeline/run`).
 */

import { failure, fetchJson, readStageStream } from './_client';

/** Treść walcząca o ścieżkę — tyle, żeby dało się wybrać bez wchodzenia w każdą z osobna. */
export interface ConflictContent {
  sha256: string;
  filename: string | null;
  source_relative_path: string | null;
  size_bytes: number | null;
  confidence: number | null;
  classification_method: string | null;
  category: string | null;
  needs_review: number | null;
}

export interface PlanConflict {
  /** `plan` — dwie zaplanowane treści; `applied` — zderzenie z tym, co leży w paczce. */
  kind: 'plan' | 'applied';
  path: string;
  applied_sha256: string | null;
  contents: ConflictContent[];
}

export interface PlanConflicts {
  total: number;
  conflicts: PlanConflict[];
}

/** Konflikty liczone z bazy, nie z pliku planu — zmiana nazwy gasi je od razu. */
export const getPlanConflicts = (
  filters: { semester?: number; skrot?: string } = {},
  signal?: AbortSignal,
) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  }
  const query = params.toString();
  return fetchJson<PlanConflicts>(`/api/plan/conflicts${query ? `?${query}` : ''}`, signal);
};

export interface PlanFinding {
  level: string;
  code: string;
  message: string;
  source_sha256: string | null;
  target_rel: string | null;
}

export interface PlanOverview {
  subject: { semester: number; skrot: string; nazwa: string; grupa: string; target_dir: string };
  plan: {
    path: string;
    plan_hash: string;
    declared_hash: string;
    created_at: string;
    items: number;
    actions: Record<string, number>;
    needs_review: number;
  } | null;
  validation?: {
    errors: number;
    warnings: number;
    blocking: number;
    findings: PlanFinding[];
    truncated: number;
  };
  diff?: {
    files: number;
    folders: number;
    new: number;
    present: number;
    conflict: number;
    missing_source: number;
    outside: number;
    blockers: Array<{ state: string; target_rel: string; detail: string; sha256: string }>;
  };
  can_apply: boolean;
  reason: string;
}

export interface TreeFile {
  name: string;
  path: string;
  state: 'new' | 'present' | 'conflict' | 'missing_source' | 'outside' | 'ground_truth';
  sha256: string;
  detail: string;
}

export interface PlanTree {
  target_dir: string;
  folders: Array<{ path: string; files: TreeFile[]; states: Record<string, number> }>;
  files: number;
  homeless: Array<{
    sha256: string;
    /** Nazwa pliku — „przenieś tu” składa z niej ścieżkę docelową. */
    filename: string;
    action: string | null;
    category: string | null;
    reason: string | null;
    confidence: number | null;
    needs_review: boolean;
    target_rel: string | null;
  }>;
}

/** Etapy, które studio umie uruchomić jako podproces CLI. */
export type Stage =
  | 'prepare'
  | 'classify'
  | 'ai-resolve'
  | 'relate'
  | 'plan'
  | 'validate'
  | 'review'
  | 'apply-dry'
  | 'apply'
  | 'verify';

/** Etapy całego indeksu — nie znają przedmiotu, więc idą własną trasą. */
export type IndexStage =
  | 'scan'
  | 'hash'
  | 'fold-hash'
  | 'extract'
  | 'scan-target'
  | 'status';

export interface PipelineState {
  stages: Array<{ stage: IndexStage; timeout_s: number }>;
  /** Nazwa trwającego etapu albo `null`. Blokada jest jedna na całe studio. */
  running: string | null;
}

export const getPlan = (semester: number, skrot: string, grupa?: string, signal?: AbortSignal) =>
  fetchJson<PlanOverview>(
    `/api/plan/${semester}/${encodeURIComponent(skrot)}` + (grupa ? `?grupa=${encodeURIComponent(grupa)}` : ''),
    signal,
  );

export const getPlanTree = (semester: number, skrot: string, grupa?: string, signal?: AbortSignal) =>
  fetchJson<PlanTree>(
    `/api/plan/${semester}/${encodeURIComponent(skrot)}/tree` +
      (grupa ? `?grupa=${encodeURIComponent(grupa)}` : ''),
    signal,
  );

export const getPipeline = (signal?: AbortSignal) =>
  fetchJson<PipelineState>('/api/pipeline', signal);

/**
 * Uruchamia etap INDEKSU (scan/hash/extract/status).
 *
 * Osobno od `runStage`, bo te skrypty nie znają `--semester/--skrot` — wspólna
 * funkcja musiałaby udawać, że przedmiot jest opcjonalny.
 */
export async function runIndexStage(
  body: { stage: IndexStage; ocr_images?: boolean },
  onLine: (line: string) => void,
): Promise<number> {
  const response = await fetch('/api/pipeline/run', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw await failure(response);
  return readStageStream(response, onLine);
}

/**
 * Uruchamia etap i oddaje jego wyjście linia po linii, na żywo.
 *
 * Strumień idzie POST-em (EventSource umie tylko GET), a odmowa bramki wraca
 * zwykłym kodem 409 ZANIM cokolwiek wystartuje — widok ma ją pokazać, a nie
 * tłumaczyć „coś poszło nie tak”.
 */

export async function runStage(
  semester: number,
  skrot: string,
  body: { stage: Stage; plan_hash?: string; confirm?: boolean },
  onLine: (line: string) => void,
  grupa?: string,
): Promise<number> {
  const response = await fetch(
    `/api/plan/${semester}/${encodeURIComponent(skrot)}/run` +
      (grupa ? `?grupa=${encodeURIComponent(grupa)}` : ''),
    {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
  if (!response.ok) throw await failure(response);
  return readStageStream(response, onLine);
}
