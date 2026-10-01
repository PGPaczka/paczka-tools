/** Historia decyzji ręcznych: `/api/decisions/history` i cofnięcie jednej z nich. */

import { fetchJson } from './_client';

export interface ManualDecision {
  sha256: string;
  decision_type: string;
  target_relative_path: string | null;
  relation_override: string | null;
  decided_by: string;
  decided_at: string;
  note: string | null;
}

export interface HistoryPage {
  total: number;
  limit: number;
  offset: number;
  decisions: ManualDecision[];
}

export const getHistory = (
  filters: { decided_by?: string; since?: string; limit?: number; offset?: number } = {},
  signal?: AbortSignal,
) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  }
  const query = params.toString();
  return fetchJson<HistoryPage>(query ? `/api/decisions/history?${query}` : '/api/decisions/history', signal);
};

export const deleteDecision = (sha256: string) =>
  fetch(`/api/decisions/${sha256}`, { method: 'DELETE', headers: { accept: 'application/json' } })
    .then(async (r) => {
      if (!r.ok) {
        let detail = `${r.status}`;
        try { const b = await r.json(); if (b?.detail) detail = b.detail; } catch {}
        throw new Error(detail);
      }
      return r.json() as Promise<{ undone: ManualDecision }>;
    });
