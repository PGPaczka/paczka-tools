import { describe, it, expect } from 'vitest'
import { categoryAnchors } from './categoryAnchors'

const VW = 800
const VH = 600
// AR = min(800, 600) * 0.24 = 144
const AR = Math.min(VW, VH) * 0.24
const CX = VW / 2
const CY = VH / 2

describe('categoryAnchors', () => {
  it('N=1: single anchor at top center (angle = -π/2)', () => {
    const map = categoryAnchors(['A'], VW, VH)
    const p = map.get('A')!
    // cos(-π/2) ≈ 0, sin(-π/2) = -1
    expect(p.x).toBeCloseTo(CX, 5)
    expect(p.y).toBeCloseTo(CY - AR, 5)
  })

  it('N=2: first at -π/2 (top), second at π/2 (bottom)', () => {
    const map = categoryAnchors(['A', 'B'], VW, VH)
    const a = map.get('A')!
    const b = map.get('B')!
    // A: i=0, angle = -π/2
    expect(a.x).toBeCloseTo(CX, 5)
    expect(a.y).toBeCloseTo(CY - AR, 5)
    // B: i=1, angle = (1/2)*2π - π/2 = π - π/2 = π/2
    expect(b.x).toBeCloseTo(CX, 5)
    expect(b.y).toBeCloseTo(CY + AR, 5)
  })

  it('N=4: four anchors evenly spaced, first at 12 oclock', () => {
    const map = categoryAnchors(['A', 'B', 'C', 'D'], VW, VH)
    const a = map.get('A')! // angle = -π/2 → top
    const b = map.get('B')! // angle = 0 → right
    const c = map.get('C')! // angle = π/2 → bottom
    const d = map.get('D')! // angle = π → left

    expect(a.x).toBeCloseTo(CX, 5)
    expect(a.y).toBeCloseTo(CY - AR, 5)

    expect(b.x).toBeCloseTo(CX + AR, 5)
    expect(b.y).toBeCloseTo(CY, 5)

    expect(c.x).toBeCloseTo(CX, 5)
    expect(c.y).toBeCloseTo(CY + AR, 5)

    expect(d.x).toBeCloseTo(CX - AR, 5)
    expect(d.y).toBeCloseTo(CY, 5)
  })

  it('returns a map with the correct number of entries', () => {
    const cats = ['X', 'Y', 'Z']
    const map = categoryAnchors(cats, VW, VH)
    expect(map.size).toBe(3)
    for (const cat of cats) {
      expect(map.has(cat)).toBe(true)
    }
  })
})
