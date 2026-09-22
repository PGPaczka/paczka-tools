import { describe, it, expect } from 'vitest'
import { seed, computeVennLayout, placeVennNodes } from './venn'
import type { GraphNode } from '../graph/GraphModel'

// ── seed ────────────────────────────────────────────────────────────────────

describe('seed', () => {
  it('is deterministic — same input always returns the same value', () => {
    expect(seed('docker-basics')).toBe(seed('docker-basics'))
    expect(seed('linux-fundamentals')).toBe(seed('linux-fundamentals'))
  })

  it('returns a value in [0, 1)', () => {
    const v = seed('docker-basics')
    expect(v).toBeGreaterThanOrEqual(0)
    expect(v).toBeLessThan(1)
  })

  it('different strings produce different values (with high probability)', () => {
    expect(seed('a')).not.toBe(seed('b'))
    expect(seed('docker-basicsa')).not.toBe(seed('docker-basicsb'))
  })

  it('empty string does not throw and returns a value in [0,1)', () => {
    const v = seed('')
    expect(v).toBeGreaterThanOrEqual(0)
    expect(v).toBeLessThan(1)
  })
})

// ── computeVennLayout ────────────────────────────────────────────────────────

const W = 800
const H = 600
const CX = W / 2
const CY = H / 2
const R = Math.min(W, H) * 0.26 // 156

describe('computeVennLayout — 1 set', () => {
  it('single circle at (cx, cy)', () => {
    const { circles } = computeVennLayout(['A'], W, H)
    expect(circles).toHaveLength(1)
    expect(circles[0].cx).toBeCloseTo(CX)
    expect(circles[0].cy).toBeCloseTo(CY)
    expect(circles[0].r).toBeCloseTo(R)
  })
})

describe('computeVennLayout — 2 sets', () => {
  it('centers at cx ± R*0.6, cy', () => {
    const { circles } = computeVennLayout(['A', 'B'], W, H)
    expect(circles[0].cx).toBeCloseTo(CX - R * 0.6)
    expect(circles[0].cy).toBeCloseTo(CY)
    expect(circles[1].cx).toBeCloseTo(CX + R * 0.6)
    expect(circles[1].cy).toBeCloseTo(CY)
  })

  it('palette uses first two entries', () => {
    const { palette } = computeVennLayout(['A', 'B'], W, H)
    expect(palette[0]).toBe('#58a6ff')
    expect(palette[1]).toBe('#3fb950')
  })
})

describe('computeVennLayout — 3 sets', () => {
  it('first circle at cx, cy − R*0.62', () => {
    const { circles } = computeVennLayout(['A', 'B', 'C'], W, H)
    expect(circles[0].cx).toBeCloseTo(CX)
    expect(circles[0].cy).toBeCloseTo(CY - R * 0.62)
  })

  it('bottom-left and bottom-right circles at correct positions', () => {
    const { circles } = computeVennLayout(['A', 'B', 'C'], W, H)
    expect(circles[1].cx).toBeCloseTo(CX - R * 0.7)
    expect(circles[1].cy).toBeCloseTo(CY + R * 0.5)
    expect(circles[2].cx).toBeCloseTo(CX + R * 0.7)
    expect(circles[2].cy).toBeCloseTo(CY + R * 0.5)
  })
})

describe('computeVennLayout — 4 sets', () => {
  it('matches the 2×2 grid formula', () => {
    const { circles } = computeVennLayout(['A', 'B', 'C', 'D'], W, H)
    expect(circles[0].cx).toBeCloseTo(CX - R * 0.55)
    expect(circles[0].cy).toBeCloseTo(CY - R * 0.5)
    expect(circles[1].cx).toBeCloseTo(CX + R * 0.55)
    expect(circles[1].cy).toBeCloseTo(CY - R * 0.5)
    expect(circles[2].cx).toBeCloseTo(CX - R * 0.55)
    expect(circles[2].cy).toBeCloseTo(CY + R * 0.5)
    expect(circles[3].cx).toBeCloseTo(CX + R * 0.55)
    expect(circles[3].cy).toBeCloseTo(CY + R * 0.5)
  })

  it('palette has all four entries', () => {
    const { palette } = computeVennLayout(['A', 'B', 'C', 'D'], W, H)
    expect(palette).toHaveLength(4)
    expect(palette[2]).toBe('#bc8cff')
    expect(palette[3]).toBe('#f0883e')
  })
})

describe('computeVennLayout — labels', () => {
  it('each circle has a label matching its set name', () => {
    const { circles } = computeVennLayout(['Alpha', 'Beta'], W, H)
    expect(circles[0].label).toBe('Alpha')
    expect(circles[1].label).toBe('Beta')
  })

  it('caps at 4 circles even with more sets', () => {
    const { circles } = computeVennLayout(['A', 'B', 'C', 'D', 'E'], W, H)
    expect(circles).toHaveLength(4)
  })
})

// ── placeVennNodes ────────────────────────────────────────────────────────────

const miniNodes: GraphNode[] = [
  {
    id: 'node-containers-only',
    kind: 'real',
    title: 'Containers Only',
    path: 'a.md',
    category: 'DevOps',
    level: 1,
    status: 'completed',
    tags: ['containers'],
    aliases: [],
    modified: '2026-01-01',
    excerpt: '',
    wordCount: 1,
  },
  {
    id: 'node-both-tags',
    kind: 'real',
    title: 'Both Tags',
    path: 'b.md',
    category: 'OS',
    level: 1,
    status: 'in-progress',
    tags: ['containers', 'linux'],
    aliases: [],
    modified: '2026-01-02',
    excerpt: '',
    wordCount: 1,
  },
  {
    id: 'node-no-match',
    kind: 'real',
    title: 'No Match',
    path: 'c.md',
    category: 'Tools',
    level: 1,
    status: null,
    tags: ['editor'],
    aliases: [],
    modified: '2026-01-03',
    excerpt: '',
    wordCount: 1,
  },
]

const ghostNode: GraphNode = {
  id: 'ghost-1',
  kind: 'ghost',
  title: 'Ghost',
  referencedBy: [],
  referenceCount: 0,
}

const catColor = (cat: string): string => (cat === 'DevOps' ? '#aaa111' : '#bbb222')
const statusColor = (s: string | null): string =>
  s === 'completed' ? '#3fb950' : s === 'in-progress' ? '#d29922' : 'transparent'

const sets2 = ['containers', 'linux']
const layout2 = computeVennLayout(sets2, W, H)

describe('placeVennNodes', () => {
  it('ghost nodes are excluded', () => {
    const result = placeVennNodes([ghostNode], sets2, 'tag', layout2, catColor, statusColor, W, H)
    expect(result).toHaveLength(0)
  })

  it('nodes not matching any set are excluded', () => {
    const result = placeVennNodes(
      [miniNodes[2]],
      sets2,
      'tag',
      layout2,
      catColor,
      statusColor,
      W,
      H,
    )
    expect(result).toHaveLength(0)
  })

  it('single-set node is placed within the circle radius', () => {
    const result = placeVennNodes(
      [miniNodes[0]],
      sets2,
      'tag',
      layout2,
      catColor,
      statusColor,
      W,
      H,
    )
    expect(result).toHaveLength(1)
    const vn = result[0]
    // Circle 0 (containers) center:
    const c0x = CX - R * 0.6
    const c0y = CY
    const dist = Math.sqrt((vn.x - c0x) ** 2 + (vn.y - c0y) ** 2)
    // rr ≤ R * (0.45 + 0.32) = R * 0.77 < R
    expect(dist).toBeLessThanOrEqual(R)
    expect(vn.isMultiSet).toBe(false)
    expect(vn.r).toBe(8)
  })

  it('multi-set node is placed near the centroid of its circles', () => {
    const result = placeVennNodes(
      [miniNodes[1]],
      sets2,
      'tag',
      layout2,
      catColor,
      statusColor,
      W,
      H,
    )
    expect(result).toHaveLength(1)
    const vn = result[0]
    expect(vn.isMultiSet).toBe(true)
    expect(vn.r).toBe(10)
    // Centroid of both circle centers (at CX - R*0.6 and CX + R*0.6, both at CY) ≈ (CX, CY)
    expect(Math.abs(vn.x - CX)).toBeLessThan(14)
    expect(Math.abs(vn.y - CY)).toBeLessThan(14)
  })

  it('fill is transparent for not-started nodes', () => {
    const notStarted: GraphNode = {
      ...miniNodes[0],
      id: 'ns-node',
      status: 'not-started',
    } as GraphNode
    const result = placeVennNodes([notStarted], sets2, 'tag', layout2, catColor, statusColor, W, H)
    expect(result[0].fill).toBe('transparent')
  })

  it('fill is catColor for nodes with non-not-started status', () => {
    const result = placeVennNodes(
      [miniNodes[0]],
      sets2,
      'tag',
      layout2,
      catColor,
      statusColor,
      W,
      H,
    )
    // miniNodes[0] is 'completed', category 'DevOps'
    expect(result[0].fill).toBe(catColor('DevOps'))
  })

  it('category dimension uses category membership', () => {
    const catSets = ['DevOps', 'OS']
    const catLayout = computeVennLayout(catSets, W, H)
    const result = placeVennNodes(
      miniNodes.slice(0, 2),
      catSets,
      'category',
      catLayout,
      catColor,
      statusColor,
      W,
      H,
    )
    // node-containers-only is DevOps → set 0 only
    expect(result.find((v) => v.id === 'node-containers-only')?.isMultiSet).toBe(false)
    // node-both-tags is OS → set 1 only
    expect(result.find((v) => v.id === 'node-both-tags')?.isMultiSet).toBe(false)
  })

  it('placement is deterministic across calls', () => {
    const r1 = placeVennNodes([miniNodes[0]], sets2, 'tag', layout2, catColor, statusColor, W, H)
    const r2 = placeVennNodes([miniNodes[0]], sets2, 'tag', layout2, catColor, statusColor, W, H)
    expect(r1[0].x).toBe(r2[0].x)
    expect(r1[0].y).toBe(r2[0].y)
  })
})
