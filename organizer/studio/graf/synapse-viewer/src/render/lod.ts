/**
 * What is worth drawing at the current zoom, and what is off screen.
 *
 * A filtered course package draws two and a half thousand nodes and as many edges on
 * every pan frame. Most of that work is invisible: nodes outside the viewport, arrow
 * heads six pixels wide rendered at a scale where a whole node is two pixels, rings and
 * inner dots that land on the same pixel as the fill. The rules live here, apart from
 * the canvas, so they can be tested without one.
 */

export interface WorldBounds {
  minX: number
  minY: number
  maxX: number
  maxY: number
}

/** The world rectangle currently on screen, grown by `margin` screen pixels. */
export function visibleWorldBounds(
  tx: number, ty: number, scale: number, vw: number, vh: number, margin = 120,
): WorldBounds {
  const m = margin / scale
  return {
    minX: (0 - tx) / scale - m,
    minY: (0 - ty) / scale - m,
    maxX: (vw - tx) / scale + m,
    maxY: (vh - ty) / scale + m,
  }
}

/** Is a disc of radius `r` around (x, y) at least partly inside the bounds? */
export function discInBounds(b: WorldBounds, x: number, y: number, r = 0): boolean {
  return x + r >= b.minX && x - r <= b.maxX && y + r >= b.minY && y - r <= b.maxY
}

/**
 * Can this segment be skipped? Only when its whole bounding box misses the viewport —
 * a cheap, conservative test: a long edge crossing the screen diagonally is kept even
 * when both ends are outside, because dropping it would tear the picture.
 */
export function segmentOffscreen(
  b: WorldBounds, x1: number, y1: number, x2: number, y2: number,
): boolean {
  return (
    (x1 < b.minX && x2 < b.minX) ||
    (x1 > b.maxX && x2 > b.maxX) ||
    (y1 < b.minY && y2 < b.minY) ||
    (y1 > b.maxY && y2 > b.maxY)
  )
}

/** Below this on-screen radius a node is a dot: rings and inner dots land on one pixel. */
export const DOT_RADIUS_PX = 4
/** Below this on-screen length an arrow head is smaller than the line it decorates. */
export const ARROW_MIN_PX = 14

export interface DetailLevel {
  /** Draw arrow heads (a fill + three lines per directed edge). */
  arrows: boolean
  /**
   * Draw full nodes: ring, inner dot, secondary stroke. The renderer applies this per
   * node against its own radius; the graph-wide answer here is what decides the cheap
   * bits that have no radius of their own.
   */
  richNodes: boolean
}

/**
 * How much detail the current zoom can actually show.
 *
 * `radius` is the largest node radius in world units; at the package's opening scale a
 * file node is under two pixels wide, so everything but its colour is wasted work.
 */
export function detailLevel(scale: number, radius: number): DetailLevel {
  return {
    arrows: scale * radius >= ARROW_MIN_PX,
    richNodes: scale * radius >= DOT_RADIUS_PX,
  }
}

/**
 * Ile pikseli fizycznych naprawdę warto malować na jeden piksel CSS.
 *
 * Telefon potrafi mieć `devicePixelRatio` 3, czyli DZIEWIĘĆ razy więcej pikseli do
 * wymazania i pomalowania na każdej klatce niż ekran zwykłego laptopa. Przy grafie
 * złożonym z kropek i włosowatych linii nikt tej różnicy nie zobaczy, a różnica w
 * płynności jest widoczna od razu. Etykiety i tak są rysowane tekstem, więc zostają
 * ostre na tyle, na ile pozwala ten limit.
 */
export const MAX_RENDER_DPR = 2

export function renderScale(devicePixelRatio: number): number {
  return Math.min(devicePixelRatio || 1, MAX_RENDER_DPR)
}

/** Najniższa gęstość, do jakiej wolno zejść — poniżej graf zaczyna wyglądać na zepsuty. */
export const MIN_RENDER_DPR = 1
/** Powyżej tego czasu klatki (ok. 30 kl./s) rysunek jest za drogi dla tego urządzenia. */
export const SLOW_FRAME_MS = 33

/**
 * Gęstość rysowania dostosowana do tego, co urządzenie NAPRAWDĘ wyrabia.
 *
 * Nie da się z góry wiedzieć, ile pikseli uciągnie cudzy telefon: ten sam graf chodzi
 * płynnie na laptopie i dławi się na ekranie o trzykrotnej gęstości. Więc zamiast
 * zgadywać — mierzymy: wolne klatki obniżają gęstość o pół kroku, cisza (czyli nikt nic
 * nie robi) przywraca pełną. Dzięki temu ostrość spada tylko wtedy, gdy alternatywą
 * jest szarpanie.
 */
export function adaptRenderScale(
  current: number, medianFrameMs: number, deviceDpr: number, idle: boolean,
): number {
  const ceiling = renderScale(deviceDpr)
  if (idle) return ceiling
  if (medianFrameMs > SLOW_FRAME_MS) return Math.max(MIN_RENDER_DPR, current - 0.5)
  return Math.min(ceiling, current)
}

/**
 * Ile etykiet naraz ma sens.
 *
 * Liczone po węzłach NA EKRANIE, nie po wszystkich, które przepuścił filtr — to była
 * realna wada: przy przedmiocie z 2,5 tys. plików próg „gęsto" włączał się na zawsze,
 * więc po przybliżeniu do pojedynczych plików żaden z nich nie miał nazwy, choć na
 * ekranie było ich trzysta (zgłoszone z telefonu 2026-09-23).
 */
export const LABEL_BUDGET = 400
/** Poniżej tylu pikseli promienia etykieta jest większa od węzła, który opisuje. */
export const LABEL_MIN_RADIUS_PX = 4.5

export function shouldLabel(
  radiusPx: number, onScreenCount: number, focused: boolean, container = false,
): boolean {
  // Kontenery (semestr, przedmiot, kategoria) mają podpis zawsze: jest ich garstka,
  // a to one mówią, na co się właśnie patrzy. Reszta reguł dotyczy tłumu plików.
  if (focused || container) return true
  if (onScreenCount > LABEL_BUDGET) return radiusPx >= 14
  return radiusPx >= LABEL_MIN_RADIUS_PX
}

/** Ile ekranów może mieć krawędź, zanim przestanie cokolwiek mówić. */
export const MAX_EDGE_SCREENS = 1.5

/**
 * Najdłuższa krawędź, jaką warto narysować przy obecnym przybliżeniu (w pikselach).
 *
 * Przy oddaleniu bez ograniczeń: długie linie są wtedy kształtem całości i o to chodzi.
 * Po przybliżeniu układ jest gwiazdą — każdy plik ma szprychę do węzła przedmiotu — więc
 * na ekranie z trzystoma węzłami rysowało się dwa i pół tysiąca linii długich na kilka
 * ekranów. Kosztowała ich RASTERYZACJA (miliony pikseli), nie liczba. Linia, której
 * drugiego końca i tak nie widać, nie niesie żadnej informacji; bliska relacja między
 * dwoma sąsiednimi plikami — owszem, i ta zostaje.
 */
export function maxEdgePx(richNodes: boolean, vw: number, vh: number): number {
  if (!richNodes) return Number.POSITIVE_INFINITY
  return Math.hypot(vw, vh) * MAX_EDGE_SCREENS
}

/**
 * Najmniejszy promień kontenera NA EKRANIE.
 *
 * Semestr, przedmiot i kategoria mają być widoczne przy każdym przybliżeniu — przy
 * oddaleniu do całej paczki węzeł przedmiotu schodził do jednego piksela i ginął wśród
 * plików, choć to on jest punktem odniesienia dla całej reszty.
 */
export const MIN_CONTAINER_PX = 6

export function containerRadius(radius: number, scale: number): number {
  return Math.max(radius, MIN_CONTAINER_PX / scale)
}

/**
 * Kontener ma podpis zawsze, gdy tylko jest dla niego MIEJSCE — o tym rozstrzyga
 * `placeLabels` niżej. Progi rozmiaru i budżety, które stały tu wcześniej, były
 * przybliżeniem tego samego pytania i myliły się w obie strony: przy jednym przedmiocie
 * gasiły siedem nazw, które spokojnie by się zmieściły, a w gęstwinie przepuszczały
 * dziesięć, które i tak zlepiały się w plamę.
 */

export interface LabelBox {
  /** Lewy górny róg i rozmiar prostokąta podpisu, w pikselach EKRANU. */
  x: number
  y: number
  w: number
  h: number
  /** Im wyżej, tym wcześniej dostaje miejsce: semestr > przedmiot > kategoria > plik. */
  priority: number
}

/**
 * Które podpisy naprawdę się mieszczą.
 *
 * Progi rozmiaru i budżety były przybliżeniem tego, o co naprawdę chodzi: czy nazwy
 * NACHODZĄ NA SIEBIE. Przy jednym przedmiocie siedem kategorii leży daleko od siebie
 * i wszystkie nazwy da się przeczytać nawet z daleka; w gęstwinie dziesięć kategorii
 * skupionych wokół jednego węzła zlepia się w nieczytelną plamę przy tym samym
 * przybliżeniu. Żaden próg zoomu tego nie rozróżni, a zwykłe sprawdzenie prostokątów —
 * tak, i przy okazji samo się reguluje: im więcej miejsca, tym więcej nazw.
 *
 * Kolejność ma znaczenie: pierwszeństwo dostaje to, co grubsze w hierarchii (i to, co
 * człowiek właśnie wskazał), więc w tłoku zostaje szkielet, a nie przypadkowy plik.
 */
export function placeLabels<T extends LabelBox>(items: T[], gap = 2): T[] {
  const placed: T[] = []
  for (const item of [...items].sort((a, b) => b.priority - a.priority)) {
    const collides = placed.some(
      (other) =>
        item.x < other.x + other.w + gap &&
        item.x + item.w + gap > other.x &&
        item.y < other.y + other.h + gap &&
        item.y + item.h + gap > other.y,
    )
    if (!collides) placed.push(item)
  }
  return placed
}
