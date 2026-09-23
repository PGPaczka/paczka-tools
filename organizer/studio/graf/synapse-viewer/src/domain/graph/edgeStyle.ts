import type { GraphEdge } from './GraphModel'
import { EDGE_KIND_LINK } from './GraphModel'

/**
 * How an edge of a given kind is drawn, and what to call it in the legend.
 *
 * A vault defines its own relation vocabulary, so this is a lookup with a fallback,
 * never a closed enum: an unknown kind still gets drawn (neutral colour, dashed) and
 * still appears in the legend under its raw name. Better a visible unknown relation
 * than a silently invisible one.
 */
export interface EdgeStyle {
  color: string
  /** Canvas line dash pattern; empty means solid. */
  dash: number[]
  width: number
  /** Draw a head at the target end — only for genuinely directed kinds. */
  arrow: boolean
  label: string
}

export const EDGE_STYLES: Record<string, EdgeStyle> = {
  // A plain [[wikilink]] — the quietest line, it is structure, not meaning.
  [EDGE_KIND_LINK]: { color: '#30363d', dash: [], width: 1, arrow: false, label: 'wikilink' },
  // Containment. Stored child → parent, because a container may have thousands of
  // children and one relation per note keeps every note's frontmatter small.
  belongs_to: { color: '#3d444d', dash: [], width: 1.2, arrow: true, label: 'belongs to' },
  // Same material in another wrapper.
  near_duplicate: { color: '#d29922', dash: [4, 3], width: 1.4, arrow: false, label: 'near duplicate' },
  // Directed: source is the older one.
  older_version: { color: '#58a6ff', dash: [], width: 1.6, arrow: true, label: 'older version' },
  related: { color: '#bc8cff', dash: [1, 3], width: 1.2, arrow: false, label: 'related' },
}

const UNKNOWN_STYLE: EdgeStyle = {
  color: '#8b949e',
  dash: [2, 2],
  width: 1.2,
  arrow: false,
  label: 'other',
}

export function edgeStyle(kind: string | undefined): EdgeStyle {
  if (!kind) return EDGE_STYLES[EDGE_KIND_LINK]
  return EDGE_STYLES[kind] ?? { ...UNKNOWN_STYLE, label: kind }
}

/**
 * Line width for one edge: the declared style, widened with confidence when the vault
 * provided one. A 0.5-confidence guess should not look like a certainty.
 */
export function edgeWidth(edge: GraphEdge): number {
  const base = edgeStyle(edge.kind).width
  if (typeof edge.confidence !== 'number') return base
  return base * (0.6 + 0.8 * Math.min(Math.max(edge.confidence, 0), 1))
}

/** Distinct kinds actually present in the graph, ordered for a stable legend. */
export function presentEdgeKinds(edges: readonly GraphEdge[]): string[] {
  const known = Object.keys(EDGE_STYLES)
  const present = new Set(edges.map((e) => e.kind ?? EDGE_KIND_LINK))
  const ordered = known.filter((k) => present.has(k))
  const extra = [...present].filter((k) => !known.includes(k)).sort()
  return [...ordered, ...extra]
}

/** Distinct node types actually present, ordered coarsest-first when recognised. */
export function presentNodeTypes(types: readonly (string | null | undefined)[]): string[] {
  // `category` sits between a subject and its files: a course package puts its material
  // into kolokwia / laboratoria / wykład, and without that level a subject is a star with
  // thousands of spokes — unreadable, and expensive to draw.
  const preferred = ['semester', 'subject', 'category', 'file']
  const present = new Set(types.filter((t): t is string => typeof t === 'string' && t.length > 0))
  const ordered = preferred.filter((t) => present.has(t))
  const extra = [...present].filter((t) => !preferred.includes(t)).sort()
  return [...ordered, ...extra]
}

/** Relative node size by type: the containment spine should dominate the graph. */
export function nodeTypeScale(type: string | null | undefined): number {
  switch (type) {
    case 'semester':
      return 2.2
    case 'subject':
      return 1.7
    case 'category':
      return 1.3
    default:
      return 1
  }
}

/**
 * Is this a CONTAINER — a note whose job is to hold others (semester, subject, category)?
 *
 * The containers and the links between them are the skeleton of a vault: a handful of
 * nodes carrying most of the meaning. They are drawn on top, always labelled and never
 * culled by the rules that keep a crowd of files affordable — those rules exist because
 * files are many, and the skeleton is not.
 */
export function isContainerType(type: string | null | undefined): boolean {
  return nodeTypeScale(type) > 1
}
