/**
 * Pozycje: `/api/items`, `/api/queue` i `/api/search`. Jeden kształt `Item`
 * obsługuje listę, kolejkę i wyszukiwanie — backend oddaje wszędzie ten sam wiersz.
 */

import { fetchJson } from './_client';
import type { Thresholds } from './dashboard';

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
  /** Katalog źródłowy tej kopii — podstawa decyzji hurtowej (S1.6). */
  folder_path: string | null;
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

export const getItems = (filters: ItemFilters, signal?: AbortSignal) =>
  fetchJson<ItemsPage>(itemsUrl(filters), signal);

/** Szczegóły jednej treści — wszystkie kopie, relacje i nazwy, pod którymi leży (Q7). */
export interface ItemDetail {
  item: Item;
  files: Array<{ filename: string | null; source_relative_path: string | null; size_bytes: number | null }>;
  relations: Array<Record<string, unknown>>;
  /** Wszystkie nazwy tej treści, posortowane. Jedna treść bywa pod kilkunastoma. */
  names: string[];
  /** Najbardziej mówiąca z nich albo `null`, gdy nazwa jest tylko jedna. */
  suggested_name: string | null;
}

export const getItemDetail = (sha256: string, signal?: AbortSignal) =>
  fetchJson<ItemDetail>(`/api/items/${sha256}`, signal);

export const getQueue = (
  filters: { semester?: number; skrot?: string; category?: string; limit?: number } = {},
  signal?: AbortSignal,
) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null) params.set(key, String(value));
  }
  const query = params.toString();
  return fetchJson<ItemsPage>(query ? `/api/queue?${query}` : '/api/queue', signal);
};

export interface SearchResult {
  query: string;
  total: number;
  items: Item[];
}

export const searchItems = (q: string, limit = 50, signal?: AbortSignal) =>
  fetchJson<SearchResult>(`/api/search?q=${encodeURIComponent(q)}&limit=${limit}`, signal);
