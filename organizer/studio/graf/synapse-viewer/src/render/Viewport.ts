function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}

/**
 * Dolna i górna granica przybliżenia.
 *
 * Dół jest niższy niż podłoga `computeFitView` (0.06) celowo: paczka na cztery
 * tysiące węzłów otwiera się właśnie tam, a kółko zatrzymywało się na 0.35 —
 * po pierwszym przybliżeniu nie dało się wrócić do widoku całości i przesuwanie
 * między semestrami stawało się zgadywanką (zgłoszone z tabletu 2026-09-23).
 */
export const MIN_SCALE = 0.04
export const MAX_SCALE = 6

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
   * Zoom by an arbitrary factor, keeping the world point under (x, y) fixed.
   *
   * Shared by the wheel and by pinch gestures, so both obey the same clamp and
   * the same anchoring rule.
   *
   * The upper bound is 6, not 2.6: with four thousand nodes a vault opens at a
   * scale where a node is a few pixels wide, and on a tablet the old ceiling left
   * no way to actually look at one. Browser page zoom is not a substitute — it
   * scales an already-rasterised canvas, so it only blurs.
   */
  zoomBy(factor: number, x: number, y: number): void {
    const ns = clamp(this.scale * factor, MIN_SCALE, MAX_SCALE)

    // Keep the world point under the pointer fixed
    const wx = (x - this.tx) / this.scale
    const wy = (y - this.ty) / this.scale

    this.scale = ns
    this.tx = x - wx * ns
    this.ty = y - wy * ns
  }

  /** Zoom toward the mouse position (wheel step). */
  applyWheel(deltaY: number, mouseX: number, mouseY: number): void {
    this.zoomBy(deltaY < 0 ? 1.12 : 0.89, mouseX, mouseY)
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

    // Dolna granica ta sama co dla kółka (`MIN_SCALE`): przedmiot z dwoma tysiącami
    // plików nie mieścił się na ekranie telefonu przy 0,06, więc „dopasuj widok"
    // pokazywało wycinek i wyglądało na zepsute.
    const sc = clamp(Math.min(this.vw / bw, this.vh / bh), MIN_SCALE, 1.35)
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
