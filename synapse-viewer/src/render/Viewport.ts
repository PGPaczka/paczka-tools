function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}

export class Viewport {
  tx = 0
  ty = 0
  scale = 1

  private vw = 0
  private vh = 0

  setSize(vw: number, vh: number): void {
    this.vw = vw
    this.vh = vh
  }

  /** Convert a canvas (CSS / logical) coordinate to world space. */
  toWorld(canvasX: number, canvasY: number): { x: number; y: number } {
    return {
      x: (canvasX - this.tx) / this.scale,
      y: (canvasY - this.ty) / this.scale,
    }
  }

  /** Convert a world coordinate to canvas (CSS / logical) space. */
  toScreen(worldX: number, worldY: number): { x: number; y: number } {
    return {
      x: worldX * this.scale + this.tx,
      y: worldY * this.scale + this.ty,
    }
  }

  /**
   * Zoom toward the mouse position.
   * factor = deltaY < 0 ? 1.12 : 0.89
   * scale clamped to [0.35, 2.6]
   */
  applyWheel(deltaY: number, mouseX: number, mouseY: number): void {
    const factor = deltaY < 0 ? 1.12 : 0.89
    const ns = clamp(this.scale * factor, 0.35, 2.6)

    // Keep the world point under the mouse fixed
    const wx = (mouseX - this.tx) / this.scale
    const wy = (mouseY - this.ty) / this.scale

    this.scale = ns
    this.tx = mouseX - wx * ns
    this.ty = mouseY - wy * ns
  }

  /**
   * Compute the target tx/ty/scale to fit the bounding box — without applying it.
   * Used by the renderer to start an animated transition.
   */
  computeFitView(
    minX: number, minY: number, maxX: number, maxY: number,
  ): { tx: number; ty: number; scale: number } {
    const bw0 = (maxX - minX) || 1
    const bh0 = (maxY - minY) || 1

    const roughSc = clamp(Math.min(this.vw / bw0, this.vh / bh0), 0.22, 1.35)
    const pad = Math.max(60, 80 / roughSc)

    const bw = bw0 + pad * 2
    const bh = bh0 + pad * 2

    const sc = clamp(Math.min(this.vw / bw, this.vh / bh), 0.06, 1.35)
    const centerX = (minX + maxX) / 2
    const centerY = (minY + maxY) / 2

    return {
      scale: sc,
      tx: this.vw / 2 - centerX * sc,
      ty: this.vh / 2 - centerY * sc,
    }
  }

  /**
   * Fit the given world bounding box into the viewport (instant, no animation).
   */
  fitView(minX: number, minY: number, maxX: number, maxY: number): void {
    const target = this.computeFitView(minX, minY, maxX, maxY)
    this.scale = target.scale
    this.tx = target.tx
    this.ty = target.ty
  }

  getTransform(): { tx: number; ty: number; scale: number } {
    return { tx: this.tx, ty: this.ty, scale: this.scale }
  }
}
