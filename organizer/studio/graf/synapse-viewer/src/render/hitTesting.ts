import { quadtree } from 'd3-quadtree'
import type { NodePosition } from './IGraphRenderer'

/**
 * Build a d3 quadtree over the given node positions.
 * The `nodeRadius` parameter is accepted for API symmetry with hitTest
 * but the quadtree itself stores only positions.
 */
export function buildQuadtree(
  positions: NodePosition[],
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  _nodeRadius: (id: string) => number,
) {
  return quadtree<NodePosition>()
    .x((d) => d.x)
    .y((d) => d.y)
    .addAll(positions)
}

/**
 * Find the node at (worldX, worldY) using the quadtree.
 *
 * A node is "hit" when the distance from its centre to the query point
 * is ≤ its radius.  When multiple nodes overlap the query point,
 * `priorityOrder` breaks the tie — the first id in that list that is
 * also a hit is returned.  Ids not mentioned in priorityOrder are
 * considered last.
 */
export function hitTest(
  qt: ReturnType<typeof buildQuadtree>,
  worldX: number,
  worldY: number,
  nodeRadius: (id: string) => number,
  priorityOrder: string[],
): string | null {
  // Maximum node radius — used to prune quadtree cells that can't possibly hit
  const MAX_RADIUS = 60

  const hits: string[] = []

  qt.visit((node, x0, y0, x1, y1) => {
    // Prune cells whose bounding box doesn't overlap the search area
    if (
      x0 > worldX + MAX_RADIUS ||
      x1 < worldX - MAX_RADIUS ||
      y0 > worldY + MAX_RADIUS ||
      y1 < worldY - MAX_RADIUS
    ) {
      return true // prune
    }

    // Leaf nodes have length === undefined; internal nodes have length === 4
    if (node.length === undefined) {
      // Iterate the linked list of coincident points at this leaf
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let p: any = node
      while (p != null && p.length === undefined) {
        const dx: number = (p.data as NodePosition).x - worldX
        const dy: number = (p.data as NodePosition).y - worldY
        const r = nodeRadius((p.data as NodePosition).id)
        if (dx * dx + dy * dy <= r * r) {
          hits.push((p.data as NodePosition).id)
        }
        p = p.next
      }
    }

    return false // do not prune; continue visiting
  })

  if (hits.length === 0) return null

  // Return the first hit that appears in priorityOrder; fall back to hits[0]
  for (const id of priorityOrder) {
    if (hits.includes(id)) return id
  }

  return hits[0]
}
