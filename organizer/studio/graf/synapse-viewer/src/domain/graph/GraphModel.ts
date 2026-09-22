export type NodeKind = 'real' | 'ghost'

/**
 * Schema contract version. The generator writes it, the viewer refuses anything else —
 * there is no migration machinery by design, regenerating the graph takes seconds.
 */
export const SCHEMA_VERSION = 2

/**
 * `kind` on an edge says WHY two notes are connected. `link` is a plain [[wikilink]];
 * anything else comes from a typed relation declared in the vault's frontmatter.
 * Deliberately a bare string: a vault defines its own vocabulary and the viewer styles
 * whatever it finds, falling back to a neutral look for unknown kinds.
 */
export const EDGE_KIND_LINK = 'link'

export interface RealNode {
  id: string
  kind: 'real'
  title: string
  path: string
  category: string
  level: number | null
  status: 'not-started' | 'in-progress' | 'completed' | null
  tags: string[]
  aliases: string[]
  modified: string
  excerpt: string
  wordCount: number
  history?: string[]
  /** What the note IS in the vault's taxonomy (e.g. 'semester' | 'subject' | 'file'). */
  type?: string | null
}

export interface GhostNode {
  id: string
  kind: 'ghost'
  title: string
  referencedBy: string[]
  referenceCount: number
}

export type GraphNode = RealNode | GhostNode

export interface GraphEdge {
  source: string
  target: string
  linkText: string
  /** Relation kind; 'link' for a plain wikilink. */
  kind: string
  /** Optional strength of a typed relation, 0..1. */
  confidence?: number
}

export interface VaultMeta {
  name: string
  notesCount: number
  ghostCount: number
  orphanCount: number
}

export interface KnowledgeGraph {
  schemaVersion: number
  generatedAt: string
  vault: VaultMeta
  nodes: GraphNode[]
  edges: GraphEdge[]
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function fromDto(dto: any): KnowledgeGraph {
  if (dto == null || typeof dto !== 'object') {
    throw new Error('SCHEMA_MISMATCH')
  }
  if (dto.schemaVersion !== SCHEMA_VERSION) {
    throw new Error('SCHEMA_MISMATCH')
  }
  return dto as KnowledgeGraph
}
