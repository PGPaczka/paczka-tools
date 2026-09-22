import type { GraphNode, RealNode } from '../graph/GraphModel'

export interface VennCircle {
  cx: number
  cy: number
  r: number
  color: string
  label: string
  labelX: number
  labelY: number
}

export interface VennNode {
  id: string
  x: number
  y: number
  r: number
  fill: string
  stroke: string
  isMultiSet: boolean
  title: string
}

const PALETTE = ['#58a6ff', '#3fb950', '#bc8cff', '#f0883e']

/**
 * Deterministic hash in [0, 1).
 * Mirrors the prototype: hh=(hh*31+charCode)|0; return ((hh>>>0)%1000)/1000
 */
export function seed(str: string): number {
  let hh = 0
  for (let i = 0; i < str.length; i++) {
    hh = ((hh * 31 + str.charCodeAt(i)) | 0)
  }
  return ((hh >>> 0) % 1000) / 1000
}

/** Circle center positions for 1–4 sets relative to (cx, cy) and radius R. */
function getCenters(
  n: number,
  cx: number,
  cy: number,
  R: number,
): Array<{ x: number; y: number }> {
  switch (n) {
    case 1:
      return [{ x: cx, y: cy }]
    case 2:
      return [
        { x: cx - R * 0.6, y: cy },
        { x: cx + R * 0.6, y: cy },
      ]
    case 3:
      return [
        { x: cx, y: cy - R * 0.62 },
        { x: cx - R * 0.7, y: cy + R * 0.5 },
        { x: cx + R * 0.7, y: cy + R * 0.5 },
      ]
    case 4:
      return [
        { x: cx - R * 0.55, y: cy - R * 0.5 },
        { x: cx + R * 0.55, y: cy - R * 0.5 },
        { x: cx - R * 0.55, y: cy + R * 0.5 },
        { x: cx + R * 0.55, y: cy + R * 0.5 },
      ]
    default:
      return []
  }
}

/**
 * Compute the Venn circle layout for 1–4 sets.
 * Returns circles (with label positions) and the palette slice used.
 */
export function computeVennLayout(
  sets: string[],
  width: number,
  height: number,
): { circles: VennCircle[]; palette: string[] } {
  const n = Math.min(sets.length, 4)
  const cx = width / 2
  const cy = height / 2
  const R = Math.min(width, height) * 0.26
  const centers = getCenters(n, cx, cy, R)
  const palette = PALETTE.slice(0, n)

  const circles: VennCircle[] = sets.slice(0, 4).map((label, i) => {
    const c = centers[i]
    // Place label outside the circle in the outward direction from (cx, cy)
    const dx = c.x - cx
    const dy = c.y - cy
    const dist = Math.sqrt(dx * dx + dy * dy)

    let labelX: number
    let labelY: number
    if (dist < 1) {
      // Single set — label above circle
      labelX = cx
      labelY = cy - R - 16
    } else {
      const nx = dx / dist
      const ny = dy / dist
      labelX = c.x + nx * (R + 18)
      labelY = c.y + ny * (R + 18)
    }

    return { cx: c.x, cy: c.y, r: R, color: palette[i], label, labelX, labelY }
  })

  return { circles, palette }
}

/**
 * Place visible graph nodes inside the Venn diagram using deterministic jitter.
 *
 * @param nodes      All graph nodes (ghosts are skipped)
 * @param sets       1–4 set labels (tags or categories)
 * @param dim        Membership dimension: 'tag' or 'category'
 * @param layout     Output of computeVennLayout
 * @param catColor   Maps category → fill hex
 * @param statusColor Maps status → stroke hex
 */
export function placeVennNodes(
  nodes: GraphNode[],
  sets: string[],
  dim: 'tag' | 'category',
  layout: ReturnType<typeof computeVennLayout>,
  catColor: (cat: string) => string,
  statusColor: (s: string | null) => string,
  width: number,
  height: number,
): VennNode[] {
  const n = Math.min(sets.length, 4)
  const cx = width / 2
  const cy = height / 2
  const R = Math.min(width, height) * 0.26
  const centers = getCenters(n, cx, cy, R)
  const limitedSets = sets.slice(0, 4)

  const result: VennNode[] = []

  for (const node of nodes) {
    if (node.kind !== 'real') continue
    const real = node as RealNode

    // Determine which sets this node belongs to
    const inSets = limitedSets
      .map((s, i) => {
        if (dim === 'tag') return real.tags.includes(s) ? i : -1
        return real.category === s ? i : -1
      })
      .filter((i) => i >= 0)

    if (inSets.length === 0) continue

    let x: number
    let y: number

    if (inSets.length === 1) {
      // Single-set: deterministic jitter strictly within the exclusive zone.
      // Max safe radius ≈ 0.38R — well clear of every neighbour circle
      // regardless of n (the tightest layout is n=4, min separation 1.1R;
      // a node at 0.38R from its own centre is 0.72R from the neighbour
      // centre, safely outside radius 1.0R).
      const c = centers[inSets[0]]
      const ang = seed(node.id + 'a') * Math.PI * 2
      const rr = R * (0.12 + seed(node.id + 'b') * 0.26)
      x = c.x + Math.cos(ang) * rr
      y = c.y + Math.sin(ang) * rr
    } else {
      // Multi-set: near the centroid of all containing circles
      const sumX = inSets.reduce((acc, i) => acc + centers[i].x, 0)
      const sumY = inSets.reduce((acc, i) => acc + centers[i].y, 0)
      x = sumX / inSets.length + (seed(node.id + 'x') - 0.5) * 22
      y = sumY / inSets.length + (seed(node.id + 'y') - 0.5) * 22
    }

    const isMultiSet = inSets.length > 1
    const fill = real.status === 'not-started' ? 'transparent' : catColor(real.category)
    const stroke = statusColor(real.status)

    result.push({
      id: node.id,
      x,
      y,
      r: isMultiSet ? 10 : 8,
      fill,
      stroke,
      isMultiSet,
      title: real.title,
    })
  }

  return result
}
