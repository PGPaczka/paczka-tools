import type { Point } from './categoryAnchors'

/**
 * Anchor positions that follow the containment tree.
 *
 * The previous version handed every anchor key a slot on one disc, in the order the
 * keys happened to appear. That places a subject in one corner and its own categories
 * in another — which is exactly what a filtered package looked like: clusters flung far
 * from the node they belong to, with their spokes crossing half the graph.
 *
 * Here a container is placed relative to its PARENT: semesters around the origin,
 * subjects around their semester, categories around their subject. The arc each child
 * gets is proportional to how much it has to hold, so a subject with two thousand files
 * is not squeezed next to one with twelve.
 */
export interface AnchorNode {
  id: string
  /** Container this one sits in, or null for a root. */
  parent: string | null
  /** How much this container holds — used for spacing, not for drawing. */
  weight: number
}

/**
 * World units per unit of sqrt(weight).
 *
 * Kept in step with the simulation's collide radius (~25): a cluster of N nodes settles
 * into a disc of roughly `collide × √N`, so this is the radius its parent has to make
 * room for. Too large and every cluster is flung away from the node it belongs to.
 */
export const SPACING = 22

/** Smallest ring radius, so a container with one tiny child is not degenerate. */
const MIN_RADIUS = 120

/** Footprint of a subtree: area grows with content, radius with its square root. */
export function footprint(weight: number): number {
  return SPACING * Math.sqrt(Math.max(weight, 1))
}

export function hierarchyAnchors(nodes: readonly AnchorNode[]): Map<string, Point> {
  const byParent = new Map<string | null, AnchorNode[]>()
  for (const node of nodes) {
    const key = node.parent
    const group = byParent.get(key)
    if (group === undefined) byParent.set(key, [node])
    else group.push(node)
  }

  const result = new Map<string, Point>()
  const known = new Set(nodes.map((n) => n.id))

  // A parent that is not in the set (filtered out) leaves its children rootless —
  // otherwise a filtered view would anchor everything at the origin and pile up.
  const roots = nodes.filter((n) => n.parent === null || !known.has(n.parent))

  const place = (children: AnchorNode[], centre: Point): void => {
    if (children.length === 0) return
    const weights = children.map((child) => footprint(child.weight))
    const total = weights.reduce((sum, value) => sum + value, 0)
    // Circumference two footprints wide per child: neighbours end up a footprint apart.
    const radius = Math.max(MIN_RADIUS, total / Math.PI)

    let angle = -Math.PI / 2
    children.forEach((child, index) => {
      const share = (weights[index] / total) * Math.PI * 2
      const at = angle + share / 2
      angle += share
      const point = children.length === 1
        ? { x: centre.x, y: centre.y }
        : { x: centre.x + Math.cos(at) * radius, y: centre.y + Math.sin(at) * radius }
      result.set(child.id, point)
      place(byParent.get(child.id) ?? [], point)
    })
  }

  place(roots, { x: 0, y: 0 })
  return result
}
