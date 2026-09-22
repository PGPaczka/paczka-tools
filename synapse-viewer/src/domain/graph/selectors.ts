import type { KnowledgeGraph, GraphNode, GraphEdge } from './GraphModel'
import { presentNodeTypes } from './edgeStyle'

/**
 * Above this many real notes a force graph stops being readable and starts being a cloud.
 * A vault that also declares node types can be opened at its coarse level instead.
 */
export const LARGE_VAULT_NODES = 600

export interface GraphFilters {
  categories: string[]
  statuses: string[]
  levels: (number | null)[]
  tags: string[]
  /** Node types (e.g. 'semester' | 'subject' | 'file'); empty = all. */
  nodeTypes: string[]
  /** Relation kinds to DRAW; empty = all. Filters edges, never nodes. */
  relationKinds: string[]
  /**
   * How several selected tags combine. 'any' (default) is the classic note-taking
   * behaviour; 'all' is what makes a large vault searchable — "this subject AND needs
   * review" is a question you cannot ask with a union.
   */
  tagMode?: 'any' | 'all'
  /**
   * Drop notes left with nothing to show. Filtering relation kinds hides edges but keeps
   * every note, so "show me the duplicates" in a vault of thousands answers with a field
   * of dust around the few hundred that have one. Off by default: the vault must never
   * shrink behind the reader's back.
   */
  connectedOnly?: boolean
}

/**
 * Filters to open a vault with.
 *
 * Small vault, or one without node types: no filter at all — the whole point is to see
 * everything. Large AND typed: preselect every type except the most granular one, so a
 * package of thousands of files opens as its readable skeleton (semesters and subjects)
 * and the files appear when the reader asks for them. This is a starting view, not a
 * restriction: the panel shows the filter as active and one click clears it.
 */
export function defaultFiltersFor(graph: KnowledgeGraph): GraphFilters {
  const empty: GraphFilters = {
    categories: [],
    statuses: [],
    levels: [],
    tags: [],
    nodeTypes: [],
    relationKinds: [],
    tagMode: 'all',
    connectedOnly: false,
  }

  const realNodes = graph.nodes.filter((n) => n.kind === 'real')
  if (realNodes.length <= LARGE_VAULT_NODES) return empty

  const types = presentNodeTypes(
    realNodes.map((n) => (n.kind === 'real' ? n.type : undefined)),
  )
  if (types.length < 2) return empty

  return { ...empty, nodeTypes: types.slice(0, -1) }
}

/**
 * Returns nodes that pass all active filters.
 * An empty array for a dimension means "no filter" (all pass).
 *
 * Ghost nodes pass every filter they cannot answer — they have no category, status or
 * level. The one exception is an explicit NODE TYPE filter: a ghost has no type either,
 * so asking for "semesters and subjects" must not hand back hundreds of untyped ghosts.
 * Without that exception the skeleton of a large vault is buried in the loose ends of
 * the level below it.
 */
export function visibleNodes(graph: KnowledgeGraph, filters: GraphFilters): GraphNode[] {
  const passes = graph.nodes.filter((node) => {
    if (node.kind === 'ghost') return (filters.nodeTypes ?? []).length === 0

    if (filters.categories.length > 0 && !filters.categories.includes(node.category)) {
      return false
    }
    if (filters.statuses.length > 0 && !filters.statuses.includes(node.status as string)) {
      return false
    }
    if (filters.levels.length > 0 && !filters.levels.includes(node.level)) {
      return false
    }
    if (filters.tags.length > 0) {
      const matches = filters.tagMode === 'all'
        ? filters.tags.every((t) => node.tags.includes(t))
        : filters.tags.some((t) => node.tags.includes(t))
      if (!matches) return false
    }
    if ((filters.nodeTypes ?? []).length > 0 && !filters.nodeTypes.includes(node.type ?? '')) {
      return false
    }

    return true
  })

  if (!filters.connectedOnly) return passes

  // Connectedness is judged against the edges actually being DRAWN, and both ends must
  // survive the node filters — otherwise a note is kept for a line nobody can see.
  const shown = new Set(passes.map((n) => n.id))
  const linked = new Set<string>()
  for (const edge of visibleEdges(graph, filters)) {
    if (shown.has(edge.source) && shown.has(edge.target)) {
      linked.add(edge.source)
      linked.add(edge.target)
    }
  }
  return passes.filter((n) => linked.has(n.id))
}

/**
 * Edges to draw. Filtering a relation kind hides the CONNECTION, not the notes —
 * hiding nodes would silently shrink the vault and make the graph lie about what exists.
 */
export function visibleEdges(graph: KnowledgeGraph, filters: GraphFilters): GraphEdge[] {
  if ((filters.relationKinds ?? []).length === 0) return graph.edges
  return graph.edges.filter((edge) => filters.relationKinds.includes(edge.kind ?? 'link'))
}

/** Returns the set of node IDs that have no edges in or out. */
export function orphanIds(graph: KnowledgeGraph): Set<string> {
  const connected = new Set<string>()
  for (const edge of graph.edges) {
    connected.add(edge.source)
    connected.add(edge.target)
  }
  const orphans = new Set<string>()
  for (const node of graph.nodes) {
    if (!connected.has(node.id)) {
      orphans.add(node.id)
    }
  }
  return orphans
}

/** Returns all edges whose target is the given id. */
export function backlinks(graph: KnowledgeGraph, id: string): GraphEdge[] {
  return graph.edges.filter((edge) => edge.target === id)
}

/** Returns all edges whose source is the given id. */
export function outgoing(graph: KnowledgeGraph, id: string): GraphEdge[] {
  return graph.edges.filter((edge) => edge.source === id)
}
