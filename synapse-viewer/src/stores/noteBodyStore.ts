import { writable, get } from 'svelte/store'

// Cache: path → markdown body (frontmatter stripped)
const cache = new Map<string, string>()
// In-flight: path → Promise (deduplicate concurrent requests)
const inflight = new Map<string, Promise<string | null>>()

// Reactive store — components can subscribe to know when a fetch completes
export const noteBodyVersion = writable(0)

function stripFrontmatter(raw: string): string {
  if (!raw.startsWith('---')) return raw
  const afterOpen = raw.indexOf('\n')
  if (afterOpen === -1) return raw
  const closePos = raw.indexOf('\n---', afterOpen)
  if (closePos === -1) return raw.slice(afterOpen + 1)
  const bodyStart = raw.indexOf('\n', closePos + 1)
  return bodyStart === -1 ? '' : raw.slice(bodyStart + 1)
}

export async function fetchBody(path: string): Promise<string | null> {
  if (cache.has(path)) return cache.get(path)!

  if (inflight.has(path)) return inflight.get(path)!

  const promise = (async () => {
    try {
      const r = await fetch(`/vault/${path}`)
      if (!r.ok) return null
      const raw = await r.text()
      const body = stripFrontmatter(raw)
      cache.set(path, body)
      noteBodyVersion.update((v) => v + 1)
      return body
    } catch {
      return null
    } finally {
      inflight.delete(path)
    }
  })()

  inflight.set(path, promise)
  return promise
}

export function getCachedBody(path: string): string | null {
  return cache.get(path) ?? null
}
