/**
 * Klastry powtórzeń: `/api/clusters`, porównanie dwóch treści, podpowiedź
 * „chyba jedna sesja” (Q8) oraz scalanie (`/api/decisions/merge`).
 */

import { fetchJson, postJson } from './_client';
import type { DecisionResult } from './decisions';
import type { Item } from './items';

export interface ClusterRelation {
  source_sha256: string;
  target_sha256: string;
  relation_type: string;
  confidence: number;
  detection_method: string;
  reason: string;
}

export interface Cluster {
  members: Item[];
  relations: ClusterRelation[];
  size: number;
  strength: number;
  has_older_version: boolean;
}

export interface ClustersPage {
  total: number;
  clusters: Cluster[];
}

export interface ResolveResult {
  canonical: string;
  skipped: number;
  decisions: DecisionResult[];
}

export const getClusters = (
  filters: { semester?: number; skrot?: string; noise?: string } = {},
  signal?: AbortSignal,
) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  }
  const query = params.toString();
  return fetchJson<ClustersPage>(query ? `/api/clusters?${query}` : '/api/clusters', signal);
};

export interface ClusterDiff {
  left: Item;
  right: Item;
  left_text: string | null;
  right_text: string | null;
  diff_type: 'text' | 'meta';
  relation: ClusterRelation | null;
}

export const getClusterDiff = (leftSha: string, rightSha: string, signal?: AbortSignal) =>
  fetchJson<ClusterDiff>(`/api/clusters/diff?left=${leftSha}&right=${rightSha}`, signal);

/** Treść w podpowiedzi „chyba jedna sesja" (Q8). */
export interface SessionContent {
  sha256: string;
  filename: string | null;
  source_relative_path: string | null;
  size_bytes: number | null;
  category: string | null;
  semester: number | null;
  subject_key: string | null;
  confidence: number | null;
  action: string | null;
  needs_review: number | null;
}

export interface SessionGroup {
  folder: string;
  day: string;
  contents: SessionContent[];
}

/**
 * Treści z jednego katalogu i jednego dnia. Podpowiedź pokazuje się TYLKO tam, gdzie data
 * naprawdę rozdziela katalog — w większości katalogów jest to data skopiowania paczki.
 */
export const getSameDayGroups = (
  filters: { semester?: number; skrot?: string; max_size?: number } = {},
  signal?: AbortSignal,
) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  }
  const query = params.toString();
  return fetchJson<{ total: number; limit: number; groups: SessionGroup[] }>(
    `/api/clusters/same-day${query ? `?${query}` : ''}`,
    signal,
  );
};

export const resolveCluster = (canonicalSha256: string, members: string[], decidedBy = 'studio') =>
  postJson<ResolveResult>('/api/clusters/resolve', {
    canonical_sha256: canonicalSha256,
    members,
    decided_by: decidedBy,
  });

/** Rodzaj scalenia: „ten sam materiał" albo „to jest starsza wersja tamtego". */
export type MergeRelation = 'near_duplicate' | 'older_version';

export interface MergeResult {
  canonical: string;
  merged: number;
  relation: MergeRelation;
}

/**
 * Scala treści w jedną kanoniczną: wchłonięte dostają `skip`, a powiązanie ląduje
 * w `relations` — czyli tam, gdzie widzi je graf i raporty, nie tylko w notatce.
 */
export const mergeContents = (
  canonicalSha256: string,
  absorbed: string[],
  relation: MergeRelation = 'near_duplicate',
  decidedBy = 'studio',
) =>
  postJson<MergeResult>('/api/decisions/merge', {
    canonical_sha256: canonicalSha256,
    absorbed,
    relation,
    decided_by: decidedBy,
  });
