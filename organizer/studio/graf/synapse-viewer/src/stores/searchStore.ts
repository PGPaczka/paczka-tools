import MiniSearch from 'minisearch'
import { writable } from 'svelte/store'

interface SearchEntry {
  id: string
  title: string
  body: string
}

export interface ContentResult {
  id: string
  title: string
}

export type IndexState = 'idle' | 'loading' | 'ready' | 'error'

export const indexState = writable<IndexState>('idle')

let ms: MiniSearch<SearchEntry> | null = null
let loadPromise: Promise<void> | null = null

/**
 * Starts loading search-index.json and building the MiniSearch index.
 * Safe to call multiple times — subsequent calls return the same promise.
 */
export function ensureIndexLoaded(): Promise<void> {
  if (loadPromise) return loadPromise

  indexState.set('loading')
  loadPromise = (async () => {
    try {
      const res = await fetch('/search-index.json')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const entries: SearchEntry[] = await res.json()

      ms = new MiniSearch<SearchEntry>({
        idField: 'id',
        fields: ['title', 'body'],
        storeFields: ['id', 'title'],
      })
      ms.addAll(entries)
      indexState.set('ready')
    } catch {
      indexState.set('error')
    }
  })()

  return loadPromise
}

/**
 * Search the full-text index. Returns results not already covered by
 * the title/tag search (pass those IDs as `excludeIds`).
 */
export function searchContent(
  query: string,
  excludeIds: Set<string>,
  limit = 6,
): ContentResult[] {
  if (!ms || !query.trim()) return []

  return ms
    .search(query, {
      boost: { title: 3 },
      fuzzy: query.length > 3 ? 0.15 : false,
      prefix: true,
      combineWith: 'OR',
    })
    .filter((r) => !excludeIds.has(r.id))
    .slice(0, limit)
    .map((r) => ({ id: r.id, title: r.title as string }))
}
