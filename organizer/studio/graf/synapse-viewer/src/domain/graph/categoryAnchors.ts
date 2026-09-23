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
/**
 * Powyżej tylu grup okrąg przestaje wystarczać i kotwice idą na tarczę.
 *
 * Dwieście kotwic na jednym okręgu leży kilka pikseli od siebie, więc skupiska, które
 * miały zostać osobno, wracają do siebie i graf znowu wygląda na wymieszany.
 */
const RING_LIMIT = 12
/** Kąt złoty — rozkłada punkty po tarczy równomiernie, bez pierścieni i szprych. */
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5))

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

  if (catCount <= RING_LIMIT) {
    categories.forEach((cat, i) => {
      const angle = (i / catCount) * 2 * Math.PI - Math.PI / 2
      result.set(cat, {
        x: cx + Math.cos(angle) * AR,
        y: cy + Math.sin(angle) * AR,
      })
    })
    return result
  }

  // Słonecznik: promień rośnie jak pierwiastek z numeru, więc gęstość kotwic zostaje
  // stała niezależnie od ich liczby — sto skupisk dostaje tyle samo miejsca co dziesięć.
  const spacing = (AR * 2) / Math.sqrt(RING_LIMIT)
  categories.forEach((cat, i) => {
    const radius = spacing * Math.sqrt(i + 0.5)
    const angle = i * GOLDEN_ANGLE - Math.PI / 2
    result.set(cat, {
      x: cx + Math.cos(angle) * radius,
      y: cy + Math.sin(angle) * radius,
    })
  })
  return result
}
