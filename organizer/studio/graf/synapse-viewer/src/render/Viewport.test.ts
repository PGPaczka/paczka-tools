import { describe, it, expect, beforeEach } from 'vitest'
import { Viewport } from './Viewport'

describe('Viewport', () => {
  let vp: Viewport

  beforeEach(() => {
    vp = new Viewport()
    vp.setSize(800, 600)
  })

  describe('toWorld / toScreen', () => {
    it('toWorld inverts toScreen for identity transform', () => {
      const world = vp.toWorld(400, 300)
      expect(world.x).toBeCloseTo(400)
      expect(world.y).toBeCloseTo(300)
    })

    it('toWorld accounts for translation', () => {
      vp.tx = 100
      vp.ty = 50
      const world = vp.toWorld(200, 150)
      // (200 - 100) / 1 = 100, (150 - 50) / 1 = 100
      expect(world.x).toBeCloseTo(100)
      expect(world.y).toBeCloseTo(100)
    })

    it('toWorld accounts for scale', () => {
      vp.scale = 2
      const world = vp.toWorld(200, 100)
      // (200 - 0) / 2 = 100, (100 - 0) / 2 = 50
      expect(world.x).toBeCloseTo(100)
      expect(world.y).toBeCloseTo(50)
    })

    it('toScreen is the inverse of toWorld', () => {
      vp.tx = 40
      vp.ty = -20
      vp.scale = 1.5
      const canvasX = 300
      const canvasY = 200
      const world = vp.toWorld(canvasX, canvasY)
      const screen = vp.toScreen(world.x, world.y)
      expect(screen.x).toBeCloseTo(canvasX)
      expect(screen.y).toBeCloseTo(canvasY)
    })
  })

  describe('applyWheel', () => {
    it('zoom in: deltaY < 0 increases scale', () => {
      const oldScale = vp.scale
      vp.applyWheel(-100, 400, 300)
      expect(vp.scale).toBeGreaterThan(oldScale)
    })

    it('zoom out: deltaY > 0 decreases scale', () => {
      const oldScale = vp.scale
      vp.applyWheel(100, 400, 300)
      expect(vp.scale).toBeLessThan(oldScale)
    })

    it('scale is clamped to max 6', () => {
      // Raised from 2.6 on 2026-09-22: a four-thousand-node vault opens at a scale
      // where one node is a few pixels wide, and on a touch screen the old ceiling
      // left no way to look at it. Page zoom is not a substitute — it blurs the canvas.
      vp.scale = 5.9
      vp.applyWheel(-1, 400, 300) // factor 1.12 → 6.6 → clamped
      expect(vp.scale).toBeLessThanOrEqual(6)
    })

    it('scale is clamped to min 0.35', () => {
      vp.scale = 0.36
      vp.applyWheel(1, 400, 300) // factor 0.89 → 0.32 → clamped
      expect(vp.scale).toBeGreaterThanOrEqual(0.35)
    })

    it('keeps the world point under the mouse fixed', () => {
      const mouseX = 200
      const mouseY = 150
      const worldBefore = vp.toWorld(mouseX, mouseY)
      vp.applyWheel(-100, mouseX, mouseY)
      const worldAfter = vp.toWorld(mouseX, mouseY)
      expect(worldAfter.x).toBeCloseTo(worldBefore.x, 5)
      expect(worldAfter.y).toBeCloseTo(worldBefore.y, 5)
    })
  })

  describe('fitView', () => {
    it('positions the bbox centre in the viewport centre', () => {
      // bbox [100,100] to [300,300] → centre (200, 200)
      vp.fitView(100, 100, 300, 300)
      const screen = vp.toScreen(200, 200)
      expect(screen.x).toBeCloseTo(400) // vw/2
      expect(screen.y).toBeCloseTo(300) // vh/2
    })

    it('scale clamped to max 1.35 for a small bbox', () => {
      // A 10×10 bbox would yield a very large unclamped scale
      vp.fitView(0, 0, 10, 10)
      expect(vp.scale).toBeLessThanOrEqual(1.35)
    })

    it('scale clamped to min 0.4 for a huge bbox', () => {
      // 10000×10000 world vs 800×600 viewport → unclamped << 0.4
      vp.fitView(0, 0, 10000, 10000)
      expect(vp.scale).toBeGreaterThanOrEqual(0.4)
    })

    it('computes correct scale and translation for [100,100]→[300,300], vw=800, vh=600', () => {
      // bw = 200 + 168 = 368, bh = 368
      // sc = clamp(min(800/368, 600/368), 0.4, 1.35)
      //    = clamp(min(2.174, 1.630), 0.4, 1.35)
      //    = clamp(1.630, 0.4, 1.35) = 1.35  (clamped to max)
      // tx = 400 - 200*1.35 = 130
      // ty = 300 - 200*1.35 = 30
      vp.fitView(100, 100, 300, 300)
      expect(vp.scale).toBeCloseTo(1.35, 5)
      expect(vp.tx).toBeCloseTo(130, 5)
      expect(vp.ty).toBeCloseTo(30, 5)
    })
  })

  describe('getTransform', () => {
    it('returns current tx, ty, scale', () => {
      vp.tx = 10
      vp.ty = 20
      vp.scale = 1.5
      expect(vp.getTransform()).toEqual({ tx: 10, ty: 20, scale: 1.5 })
    })
  })
})
