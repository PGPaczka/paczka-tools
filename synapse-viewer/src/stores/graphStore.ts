import { writable, derived } from 'svelte/store'
import type { KnowledgeGraph } from '../domain/graph/GraphModel'
import type { GraphFilters } from '../domain/graph/selectors'
import { visibleNodes } from '../domain/graph/selectors'

export const graph = writable<KnowledgeGraph | null>(null)
export const loadError = writable<string | null>(null)

export const filters = writable<GraphFilters>({
  categories: [],
  statuses: [],
  levels: [],
  tags: [],
  nodeTypes: [],
  relationKinds: [],
  tagMode: 'all',
})

/** Derived set of visible node IDs based on the current graph and filters. */
export const visibleNodeIds = derived([graph, filters], ([$graph, $filters]) => {
  if (!$graph) return new Set<string>()
  return new Set(visibleNodes($graph, $filters).map((n) => n.id))
})
