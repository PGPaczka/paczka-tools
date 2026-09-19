/**
 * Klient API studia. Typy odpowiadają kształtowi z `studio/api/queries.py`;
 * widok niczego nie dolicza — jeśli jakiejś liczby tu nie ma, ma ją dodać backend
 * (studio/AGENTS.md, reguła 1).
 */

export interface Thresholds {
  auto_apply: number;
  review_min: number;
}

export interface Totals {
  packages: number;
  folders: number;
  duplicate_folders: number;
  files: number;
  files_by_status: Record<string, number>;
  contents: number;
  with_text: number;
  relations: number;
  plan_items: number;
  applied: number;
  subjects: number;
}

export interface SubjectRow {
  semester: number;
  skrot: string;
  nazwa: string;
  grupa: string;
  target_dir: string;
  forms: string[];
  aliases: string[];
  stage: string;
  ground_truth: number;
  planned: number;
  needs_review: number;
  actions: Record<string, number>;
  decided_at: string | null;
  run_id: string | null;
}

export interface QueueStage {
  stage: string;
  count: number;
  subjects: Array<Pick<SubjectRow, 'semester' | 'skrot' | 'nazwa' | 'grupa' | 'needs_review' | 'planned' | 'ground_truth'>>;
}

export interface Dashboard {
  thresholds: Thresholds;
  totals: Totals;
  subjects: SubjectRow[];
  queue: QueueStage[];
}

export interface CategoryRow {
  category: string;
  count: number;
  needs_review: number;
  min_confidence: number | null;
}

export interface SubjectDetail {
  subject: Pick<SubjectRow, 'semester' | 'skrot' | 'nazwa' | 'grupa' | 'target_dir' | 'forms' | 'aliases'>;
  stage: string;
  ground_truth: number;
  planned: number;
  needs_review: number;
  actions: Record<string, number>;
  decided_at: string | null;
  run_id: string | null;
  outdated: number;
  categories: CategoryRow[];
  methods: Record<string, number>;
  confidence: { thresholds: Thresholds; buckets: Record<string, number> };
  ground_truth_categories: Record<string, number>;
}

export interface Item {
  sha256: string;
  content_kind: string | null;
  has_text: number;
  ocr_done: number;
  semester: number | null;
  subject_key: string | null;
  category: string | null;
  slot: string | null;
  target_relative_path: string | null;
  action: string | null;
  reason: string | null;
  confidence: number | null;
  confidence_bucket: string;
  classification_method: string | null;
  needs_review: number | null;
  is_outdated: number | null;
  run_id: string | null;
  decided_at: string | null;
  file_id: number | null;
  source_package: string | null;
  source_relative_path: string | null;
  filename: string | null;
  extension: string | null;
  size_bytes: number | null;
  modified_date: string | null;
  file_status: string | null;
  copies: number;
}

export interface ItemsPage {
  total: number;
  limit: number;
  offset: number;
  thresholds: Thresholds;
  items: Item[];
}

export interface ItemFilters {
  semester?: number;
  skrot?: string;
  category?: string;
  action?: string;
  status?: string;
  kind?: string;
  needs_review?: boolean;
  classified?: boolean;
  confidence_min?: number;
  confidence_max?: number;
  include_ground_truth?: boolean;
  limit?: number;
  offset?: number;
}

/**
 * Buduje adres listy pozycji. Puste i nieustawione filtry NIE trafiają do URL-a:
 * pusty parametr znaczyłby dla backendu „kategoria równa pustemu napisowi”,
 * czyli cicho zerową listę zamiast braku filtru.
 */
export function itemsUrl(filters: ItemFilters = {}): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === null || value === '') continue;
    params.set(key, typeof value === 'boolean' ? String(value) : String(value));
  }
  const query = params.toString();
  return query ? `/api/items?${query}` : '/api/items';
}

/** Adres jednego przedmiotu; `grupa` rozstrzyga kolizje skrótu w semestrze. */
export function subjectUrl(semester: number, skrot: string, grupa?: string): string {
  const base = `/api/subjects/${semester}/${encodeURIComponent(skrot)}`;
  return grupa ? `${base}?grupa=${encodeURIComponent(grupa)}` : base;
}

async function fetchJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal, headers: { accept: 'application/json' } });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body && typeof body.detail === 'string') detail = body.detail;
    } catch {
      /* odpowiedź bez JSON-a — zostaje sam status */
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export interface Health {
  status: string;
  db: string;
  schema_version: number | null;
  read_only: boolean;
  subjects: number;
}

export const getHealth = (signal?: AbortSignal) => fetchJson<Health>('/api/health', signal);

export const getDashboard = (signal?: AbortSignal) =>
  fetchJson<Dashboard>('/api/subjects', signal);

export const getSubject = (semester: number, skrot: string, grupa?: string, signal?: AbortSignal) =>
  fetchJson<SubjectDetail>(subjectUrl(semester, skrot, grupa), signal);

export const getItems = (filters: ItemFilters, signal?: AbortSignal) =>
  fetchJson<ItemsPage>(itemsUrl(filters), signal);
