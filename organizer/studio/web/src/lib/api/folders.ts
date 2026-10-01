/**
 * Katalogi: `/api/folders`, ich ręczne powiązania (Q3) i decyzja hurtowa
 * po katalogu (`/api/decisions/by-folder`) — katalog jest tu kluczem.
 */

import { fetchJson, postJson } from './_client';
import type { DecisionResult } from './decisions';
import type { Item } from './items';

export interface FolderItems {
  folder: string;
  total: number;
  items: Item[];
  /** Katalogi powiązane ręcznie (Q3) — pokazywane ZAWSZE, dokładane tylko na żądanie. */
  linked_folders: string[];
  included_linked: boolean;
}

export interface FolderDecisionResult {
  folder: string;
  count: number;
  decisions: DecisionResult[];
}

export const getItemsByFolder = (folder: string, includeLinked = false, signal?: AbortSignal) =>
  fetchJson<FolderItems>(
    `/api/decisions/by-folder?folder=${encodeURIComponent(folder)}` +
      (includeLinked ? '&include_linked=true' : ''),
    signal,
  );

export const postDecisionByFolder = (folder: string, decisionType: string, extra: Record<string, unknown> = {}) =>
  postJson<FolderDecisionResult>('/api/decisions/by-folder', { folder, decision_type: decisionType, ...extra });

export interface FolderRow {
  folder_path: string;
  source_package: string;
  file_count: number | null;
  total_bytes: number | null;
  /** Automatyczny dedup (równość poddrzewa co do bitu) — co innego niż powiązanie ręczne. */
  duplicate_of: string | null;
  /** Katalogi powiązane RĘCZNIE, z obu stron pary. */
  linked_to: string[];
}

export interface FoldersPage {
  total: number;
  limit: number;
  offset: number;
  folders: FolderRow[];
}

export interface FolderLink {
  folder_a: string;
  folder_b: string;
  kind: 'duplicate' | 'related';
  decided_by: string;
  decided_at: string;
  note: string | null;
}

export const getFolders = (
  filters: { q?: string; package?: string; limit?: number; offset?: number } = {},
  signal?: AbortSignal,
) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  }
  const query = params.toString();
  return fetchJson<FoldersPage>(`/api/folders${query ? `?${query}` : ''}`, signal);
};

export const getFolderLinks = (folder?: string, signal?: AbortSignal) =>
  fetchJson<{ total: number; links: FolderLink[] }>(
    `/api/folders/links${folder ? `?folder=${encodeURIComponent(folder)}` : ''}`,
    signal,
  );

export const linkFolders = (
  folderA: string,
  folderB: string,
  kind: 'duplicate' | 'related' = 'duplicate',
  note?: string,
) => postJson<FolderLink>('/api/folders/links', {
  folder_a: folderA, folder_b: folderB, kind, note,
});

/** DELETE z parametrami w adresie — para jest kluczem, nie treścią żądania. */
export const unlinkFolders = async (folderA: string, folderB: string) => {
  const params = new URLSearchParams({ folder_a: folderA, folder_b: folderB });
  const response = await fetch(`/api/folders/links?${params}`, {
    method: 'DELETE',
    headers: { accept: 'application/json' },
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const data = await response.json();
      if (data && typeof data.detail === 'string') detail = data.detail;
    } catch { /* odpowiedź bez JSON-a */ }
    throw new Error(detail);
  }
  return (await response.json()) as { unlinked: { folder_a: string; folder_b: string } };
};
