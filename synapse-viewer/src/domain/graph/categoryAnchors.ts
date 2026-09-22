export interface Point {
  x: number
  y: number
}

/**
 * Computes category anchor positions arranged in a circle.
 *
 * AR = Math.min(vw, vh) * 0.24
 * angle_i = (i / catCount) * 2*Math.PI - Math.PI/2   (starts at 12 o'clock)
 * anchor = { x: cx + cos(angle)*AR, y: cy + sin(angle)*AR }
 *
 * @param categories - Categories in encounter order (first-seen determines angle slot)
 * @param vw - Viewport width in logical pixels
 * @param vh - Viewport height in logical pixels
 */
export function categoryAnchors(
  categories: string[],
  vw: number,
  vh: number,
  cx = 0,
  cy = 0,
): Map<string, Point> {
  const AR = Math.min(vw, vh) * 0.24
  const catCount = categories.length
  const result = new Map<string, Point>()

  categories.forEach((cat, i) => {
    const angle = (i / catCount) * 2 * Math.PI - Math.PI / 2
    result.set(cat, {
      x: cx + Math.cos(angle) * AR,
      y: cy + Math.sin(angle) * AR,
    })
  })

  return result
}
