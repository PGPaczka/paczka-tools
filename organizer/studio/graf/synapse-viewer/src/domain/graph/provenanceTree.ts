import type { ProvenanceCopy } from './GraphModel'

/**
 * Where a content's copies came from, as something you can read.
 *
 * A flat list repeats itself: most contents carry the same file name in every copy and
 * share the tail of their path, so the part that actually distinguishes one copy from
 * another is buried in the middle of a wrapped line. The tree keeps the shared parts in
 * one place and spends vertical space only where the copies genuinely diverge.
 */
export interface ProvenanceNode {
  /** One or more path segments; a chain with no choice in it is joined with `/`. */
  label: string
  children: ProvenanceNode[]
  /** Set when a copy ends here — the whole path, ready to copy to the clipboard. */
  fullPath?: string
}

export interface ProvenanceTree {
  /** File name shared by every copy, or null when they differ. Shown once. */
  commonName: string | null
  /** One root per source package. */
  roots: ProvenanceNode[]
  shown: number
  total: number
  /** Copies that exist but did not travel in the graph — never pretend they are not there. */
  hidden: number
}

interface Building {
  label: string
  children: Map<string, Building>
  fullPath?: string
  count: number
}

function fileNameOf(path: string): string {
  const segments = path.split('/')
  return segments[segments.length - 1] ?? ''
}

export function buildProvenanceTree(
  copies: readonly ProvenanceCopy[],
  total: number,
): ProvenanceTree {
  const names = new Set(copies.map((c) => fileNameOf(c.path)))
  const commonName = copies.length > 0 && names.size === 1 ? [...names][0] : null

  const roots = new Map<string, Building>()

  for (const copy of copies) {
    const segments = copy.path.split('/').filter((s) => s.length > 0)
    // The shared name is printed once above the tree, so it does not repeat in every
    // leaf. When the names differ it stays where it belongs: on its own copy.
    const trail = commonName !== null ? segments.slice(0, -1) : segments
    const fullPath = `${copy.package}/${copy.path}`

    let node = roots.get(copy.package)
    if (!node) {
      node = { label: copy.package, children: new Map(), count: 0 }
      roots.set(copy.package, node)
    }
    node.count += 1

    for (const segment of trail) {
      let child = node.children.get(segment)
      if (!child) {
        child = { label: segment, children: new Map(), count: 0 }
        node.children.set(segment, child)
      }
      child.count += 1
      node = child
    }
    node.fullPath = fullPath
  }

  return {
    commonName,
    roots: [...roots.values()].sort(byWeight).map((root) => finish(root, false)),
    shown: copies.length,
    total,
    hidden: Math.max(total - copies.length, 0),
  }
}

/** Packages first by how much came from them, then by name the way Polish reads. */
function byWeight(a: Building, b: Building): number {
  return b.count - a.count || a.label.localeCompare(b.label, 'pl')
}

/**
 * Collapses chains with nothing to choose in them, the way an editor shows nested
 * folders as `a/b/c`. A node that is itself a copy is never merged away: it has
 * something to say.
 */
function finish(node: Building, mergeable: boolean): ProvenanceNode {
  let current = node
  let label = node.label

  while (mergeable && current.fullPath === undefined && current.children.size === 1) {
    const [only] = current.children.values()
    label = `${label}/${only.label}`
    current = only
  }

  const children = [...current.children.values()]
    .sort(byWeight)
    .map((child) => finish(child, true))

  const out: ProvenanceNode = { label, children }
  if (current.fullPath !== undefined) out.fullPath = current.fullPath
  return out
}
