import { describe, it, expect } from 'vitest'
import { buildQuadtree, hitTest } from './hitTesting'
import type { NodePosition } from './IGraphRenderer'

// All nodes have radius 10 in these tests
const radius = (_id: string): number => 10

describe('buildQuadtree + hitTest', () => {
  it('exact center hit returns that node id', () => {
    const positions: NodePosition[] = [{ id: 'a', x: 100, y: 200 }]
    const qt = buildQuadtree(positions, radius)
    expect(hitTest(qt, 100, 200, radius, [])).toBe('a')
  })

  it('hit within radius returns the node id', () => {
    const positions: NodePosition[] = [{ id: 'a', x: 100, y: 200 }]
    const qt = buildQuadtree(positions, radius)
    // 8 pixels away — inside radius 10
    expect(hitTest(qt, 108, 200, radius, [])).toBe('a')
  })

  it('miss returns null when point is outside all radii', () => {
    const positions: NodePosition[] = [{ id: 'a', x: 100, y: 200 }]
    const qt = buildQuadtree(positions, radius)
    expect(hitTest(qt, 1000, 1000, radius, [])).toBeNull()
  })

  it('just outside radius returns null', () => {
    const positions: NodePosition[] = [{ id: 'a', x: 100, y: 200 }]
    const qt = buildQuadtree(positions, radius)
    // radius 10 → point at distance ~14.14 misses
    expect(hitTest(qt, 111, 200, radius, [])).toBeNull()
  })

  it('overlapping nodes: priorityOrder determines winner', () => {
    // Both nodes at the same location — both are hits
    const positions: NodePosition[] = [
      { id: 'selected', x: 50, y: 50 },
      { id: 'normal', x: 52, y: 52 }, // within radius of each other and query
    ]
    const qt = buildQuadtree(positions, radius)
    // selected appears first in priorityOrder → wins
    const result = hitTest(qt, 51, 51, radius, ['selected', 'normal'])
    expect(result).toBe('selected')
  })

  it('overlapping nodes: second in priorityOrder wins if first is absent', () => {
    const positions: NodePosition[] = [{ id: 'normal', x: 50, y: 50 }]
    const qt = buildQuadtree(positions, radius)
    // 'missing' is in priorityOrder but not a hit
    const result = hitTest(qt, 50, 50, radius, ['missing', 'normal'])
    expect(result).toBe('normal')
  })

  it('empty quadtree returns null', () => {
    const qt = buildQuadtree([], radius)
    expect(hitTest(qt, 0, 0, radius, [])).toBeNull()
  })

  it('multiple nodes in separate locations — only the closest is hit', () => {
    const positions: NodePosition[] = [
      { id: 'far', x: 0, y: 0 },
      { id: 'near', x: 200, y: 200 },
    ]
    const qt = buildQuadtree(positions, radius)
    // query at (200, 200) → hits 'near', not 'far'
    expect(hitTest(qt, 200, 200, radius, [])).toBe('near')
    expect(hitTest(qt, 0, 0, radius, [])).toBe('far')
  })
})
