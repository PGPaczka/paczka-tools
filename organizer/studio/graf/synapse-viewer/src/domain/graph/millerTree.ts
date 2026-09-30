import type { GraphEdge, RealNode } from './GraphModel'
import { presentNodeTypes } from './edgeStyle'

/**
 * The containment tree the vault already declares, read as something you can walk.
 *
 * A force layout shows the SHAPE of a vault; it is a poor way to reach one file among
 * thousands. The edges are already a strict tree — `belongs_to` runs from the child to
 * its parent, one per note — so the same data supports column browsing at no cost.
 */
export const BELONGS_TO = 'belongs_to'

export interface MillerTree {
  /** Nodes with no parent inside this tree, in display order. */
  roots: RealNode[]
  childrenOf(id: string): RealNode[]
  parentOf(id: string): string | null
  /** Every descendant, not just direct children — a subject's count must mean its material. */
  descendantCount(id: string): number
  nodeById(id: string): RealNode | undefined
}

/** Comparator for siblings: containers first, then by title the way Polish reads. */
function compareSiblings(order: Map<string, number>) {
  return (a: RealNode, b: RealNode): number => {
    const rank = (n: RealNode) => order.get(n.type ?? '') ?? order.size
    const byType = rank(a) - rank(b)
    if (byType !== 0) return byType
    return a.title.localeCompare(b.title, 'pl')
  }
}

/**
 * Builds the tree over `nodes`, keeping only what `matches` selects — plus every ancestor
 * of a match.
 *
 * That last part is the whole point of the predicate. Filtering by category drops the
 * semester and subject nodes, because THEIR category is `semestr` / `SEM3`, not
 * `kolokwia`; without keeping the road to a match, narrowing the view would flatten it
 * into a list of files with no way to tell where any of them live.
 */
export function buildMillerTree(
  nodes: readonly RealNode[],
  edges: readonly GraphEdge[],
  matches?: (node: RealNode) => boolean,
): MillerTree {
  const byId = new Map(nodes.map((n) => [n.id, n]))

  const parent = new Map<string, string>()
  for (const edge of edges) {
    if (edge.kind !== BELONGS_TO) continue
    // A child declares one parent; a target outside this node set (a ghost) is no parent.
    if (!byId.has(edge.source) || !byId.has(edge.target)) continue
    if (edge.source === edge.target) continue
    if (!parent.has(edge.source)) parent.set(edge.source, edge.target)
  }

  const kept = keptIds(nodes, parent, matches)

  const children = new Map<string, RealNode[]>()
  const roots: RealNode[] = []
  for (const node of nodes) {
    if (!kept.has(node.id)) continue
    const parentId = parent.get(node.id)
    if (parentId === undefined || !kept.has(parentId)) {
      roots.push(node)
      continue
    }
    const bucket = children.get(parentId)
    if (bucket) bucket.push(node)
    else children.set(parentId, [node])
  }

  const order = new Map(
    presentNodeTypes(nodes.map((n) => n.type)).map((type, index) => [type, index]),
  )
  const compare = compareSiblings(order)
  roots.sort(compare)
  for (const bucket of children.values()) bucket.sort(compare)

  const counts = new Map<string, number>()

  return {
    roots,
    childrenOf: (id) => children.get(id) ?? [],
    parentOf: (id) => {
      const parentId = parent.get(id)
      return parentId !== undefined && kept.has(parentId) ? parentId : null
    },
    descendantCount: (id) => descendantCount(id, children, counts),
    nodeById: (id) => (kept.has(id) ? byId.get(id) : undefined),
  }
}

/** Matches plus their ancestors; everything when no predicate was given. */
function keptIds(
  nodes: readonly RealNode[],
  parent: ReadonlyMap<string, string>,
  matches?: (node: RealNode) => boolean,
): Set<string> {
  if (!matches) return new Set(nodes.map((n) => n.id))

  const kept = new Set<string>()
  for (const node of nodes) {
    if (!matches(node)) continue
    let current: string | undefined = node.id
    // Stops on a node already kept, so a deep tree is walked once per branch, and a
    // malformed vault with a cycle stops instead of spinning.
    while (current !== undefined && !kept.has(current)) {
      kept.add(current)
      current = parent.get(current)
    }
  }
  return kept
}

function descendantCount(
  id: string,
  children: ReadonlyMap<string, RealNode[]>,
  memo: Map<string, number>,
  seen: Set<string> = new Set(),
): number {
  const cached = memo.get(id)
  if (cached !== undefined) return cached
  if (seen.has(id)) return 0
  seen.add(id)

  let total = 0
  for (const child of children.get(id) ?? []) {
    total += 1 + descendantCount(child.id, children, memo, seen)
  }

  memo.set(id, total)
  return total
}

/**
 * Columns to draw for an opened path: the roots, then the children of each opened node.
 *
 * A path entry that no longer exists truncates the rest. Paths outlive the graph they
 * were made against — a filter change or a rebuild can take a node away — and a stale
 * id must collapse the view to what is real, not leave an empty column behind.
 */
export function columnsFor(tree: MillerTree, path: readonly string[]): RealNode[][] {
  return [tree.roots, ...visiblePath(tree, path).map((id) => tree.childrenOf(id))]
}

/**
 * The part of a path that still opens a column.
 *
 * Kept separate from `columnsFor` so a view can show breadcrumbs for the same truncation
 * without assigning anything back: doing that inside a reactive block made the columns
 * depend on the state the columns had just corrected, and the build rejected the cycle.
 */
/**
 * The chain that opens itself: from a single root down, as long as each level offers
 * exactly one way on.
 *
 * Narrowing to one subject and one category leaves a tree one row wide all the way to the
 * files. Making the reader click through that chain is asking them to confirm a choice
 * they already made in the view they came from. It stops the moment there are two options,
 * because that is a question, and at a leaf, because there is nothing below it.
 */
export function autoPath(tree: MillerTree): string[] {
  const path: string[] = []
  let level = tree.roots

  // Bounded so a malformed vault cannot spin here; the real hierarchy is five deep.
  while (level.length === 1 && path.length < 16) {
    const only = level[0]
    const children = tree.childrenOf(only.id)
    if (children.length === 0) break
    path.push(only.id)
    level = children
  }

  return path
}

export function visiblePath(tree: MillerTree, path: readonly string[]): string[] {
  const open: string[] = []
  for (const id of path) {
    if (!tree.nodeById(id)) break
    if (tree.childrenOf(id).length === 0) break
    open.push(id)
  }
  return open
}
