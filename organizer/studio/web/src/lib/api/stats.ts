/** Liczby na żywo: `/api/stats`. */

import { fetchJson } from './_client';
import type { Thresholds, Totals } from './dashboard';

export interface LiveStats {
  thresholds: Thresholds;
  totals: Totals & { manual_decisions: number };
  stages: Record<string, number>;
  methods: Record<string, number>;
  categories: Record<string, number>;
  actions: Record<string, number>;
}

export const getStats = (signal?: AbortSignal) =>
  fetchJson<LiveStats>('/api/stats', signal);
