import { fromDto, type KnowledgeGraph } from '../domain/graph/GraphModel'

export interface LoadedGraph {
  graph: KnowledgeGraph
  etag: string | null
  lastModified: string | null
}

/**
 * Fetch graph.json, validate schemaVersion === 1, return typed graph.
 * Throws Error('SCHEMA_MISMATCH') if the schema version is wrong.
 */
export async function loadGraph(url = '/graph.json'): Promise<LoadedGraph> {
  const res = await fetch(url)
  if (!res.ok) {
    throw new Error(`Failed to load graph: ${res.status} ${res.statusText}`)
  }

  const dto: unknown = await res.json()
  const graph = fromDto(dto)

  return {
    graph,
    etag: res.headers.get('ETag'),
    lastModified: res.headers.get('Last-Modified'),
  }
}

/**
 * Conditional GET using ETag / Last-Modified headers.
 * Returns null if the server responds with 304 Not Modified.
 */
export async function conditionalLoad(
  url: string,
  etag: string | null,
  lastModified: string | null,
): Promise<LoadedGraph | null> {
  const headers: Record<string, string> = {}
  if (etag) headers['If-None-Match'] = etag
  if (lastModified) headers['If-Modified-Since'] = lastModified

  const res = await fetch(url, { headers })

  if (res.status === 304) return null
  if (!res.ok) {
    throw new Error(`Failed to load graph: ${res.status} ${res.statusText}`)
  }

  const dto: unknown = await res.json()
  const graph = fromDto(dto)

  return {
    graph,
    etag: res.headers.get('ETag'),
    lastModified: res.headers.get('Last-Modified'),
  }
}
