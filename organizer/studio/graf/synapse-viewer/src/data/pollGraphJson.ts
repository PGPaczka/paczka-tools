import { conditionalLoad } from './GraphLoader'
import type { KnowledgeGraph } from '../domain/graph/GraphModel'

const GRAPH_URL = '/graph.json'

/**
 * Start polling /graph.json every `intervalMs` milliseconds using
 * conditional GET (ETag / Last-Modified headers).
 *
 * When the server returns a new version the `onUpdate` callback fires.
 * Errors are silently swallowed so polling survives transient network issues.
 *
 * @returns A stop function — call it to cancel polling.
 */
export function startPolling(
  intervalMs: number,
  etag: string | null,
  lastModified: string | null,
  onUpdate: (newGraph: KnowledgeGraph) => void,
): () => void {
  // Track the latest headers so each conditional request uses fresh values
  let currentEtag = etag
  let currentLastModified = lastModified
  let stopped = false

  const tick = async () => {
    if (stopped) return
    try {
      const result = await conditionalLoad(GRAPH_URL, currentEtag, currentLastModified)
      if (result !== null) {
        // New data — update cached headers and notify caller
        currentEtag = result.etag
        currentLastModified = result.lastModified
        onUpdate(result.graph)
      }
    } catch {
      // Swallow errors — polling should survive transient failures
    }
  }

  const id = setInterval(() => {
    void tick()
  }, intervalMs)

  return () => {
    stopped = true
    clearInterval(id)
  }
}
