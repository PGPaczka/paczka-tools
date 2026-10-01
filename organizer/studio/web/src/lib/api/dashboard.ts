/**
 * Pulpit i przedmioty: `/api/health` i `/api/subjects`. Tu leżą typy, na których
 * stoi reszta klienta — progi, sumy i wiersz przedmiotu.
 */

import { fetchJson } from './_client';

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

/** Adres jednego przedmiotu; `grupa` rozstrzyga kolizje skrótu w semestrze. */
export function subjectUrl(semester: number, skrot: string, grupa?: string): string {
  const base = `/api/subjects/${semester}/${encodeURIComponent(skrot)}`;
  return grupa ? `${base}?grupa=${encodeURIComponent(grupa)}` : base;
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
