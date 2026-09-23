import {
  forceSimulation as d3Simulation,
  forceLink,
  forceManyBody,
  forceCollide,
  forceCenter,
  type SimulationNodeDatum,
  type SimulationLinkDatum,
} from 'd3-force'
import { categoryAnchors } from './categoryAnchors'

export interface SimNode extends SimulationNodeDatum {
  id: string
  category: string
  /**
   * Do czego ten węzeł ciąży w układzie.
   *
   * NIE jest to `category`: w paczce kursów kategoria pliku to rodzaj materiału
   * (`egzamin`, `laboratoria`), wspólny dla wszystkich przedmiotów — więc kotwiczenie po
   * niej ściągało egzaminy z dziesięciu różnych przedmiotów w jedno miejsce i graf
   * wyglądał na wymieszany, choć między tymi plikami nie ma ani jednej krawędzi.
   * Właściwą odpowiedzią jest RODZIC w hierarchii (`belongs_to`), a gdy vault jej nie ma —
   * kategoria, tak jak dotąd.
   */
  anchor: string
  level: number | null
}

export interface SimLink extends SimulationLinkDatum<SimNode> {
  source: string
  target: string
}

/**
 * Create a d3-force simulation matching the Synapse prototype physics.
 *
 * Forces applied:
 *  - forceManyBody (repulsion)  strength = -repulsion
 *  - forceLink (springs)        distance = linkDist
 *  - forceCollide               radius scales with node level
 *  - forceCenter                gentle 0.05 strength to prevent drift
 *  - custom anchor pull (0.03; the prototype's 0.0085 loses to repulsion at scale)
 *
 * Alpha decay matches prototype: alpha *= 0.975 per tick → alphaDecay = 0.025
 * Stops at alphaMin = 0.004.
 *
 * @returns control handle — { stop, restart, setNodeFixed, reheat }
 */
/** Above this many nodes a layout is no longer a sketch to watch, but a cost to pay. */
export const LARGE_LAYOUT_NODES = 800

/**
 * How fast the layout cools down.
 *
 * The prototype's 0.025 means ~220 ticks, which is right for a vault of a few dozen
 * notes and wrong for a filtered subject of two and a half thousand: each tick computes
 * repulsion, springs and collisions over all of them, so the canvas stayed busy for the
 * best part of a minute and dragging it felt like glue (zgłoszone z tabletu 2026-09-23).
 * A large layout cools in ~65 ticks instead — by then the anchors have long since decided
 * the arrangement, and what is left is drift nobody can see.
 */
export function alphaDecayFor(nodeCount: number): number {
  return nodeCount > LARGE_LAYOUT_NODES ? 0.08 : 0.025
}

export function createSimulation(
  nodes: SimNode[],
  links: SimLink[],
  vw: number,
  vh: number,
  repulsion: number,
  linkDist: number,
  onTick: (positions: Map<string, { x: number; y: number }>, alpha: number) => void,
  onEnd?: () => void,
  /**
   * Gotowe pozycje kotwic (klucz `SimNode.anchor` → punkt). Gdy ich nie ma, kotwice
   * liczy `categoryAnchors` jak dotąd — czyli vault bez hierarchii zachowuje się jak
   * przedtem. Z hierarchią pozycje muszą przyjść z ZEWNĄTRZ, bo tylko tam wiadomo,
   * że kategoria ma stać przy swoim przedmiocie, a nie w dowolnym wolnym slocie.
   */
  anchorPositions?: Map<string, { x: number; y: number }>,
) {
  // Gather unique categories in encounter order (first-seen determines angle slot)
  const catSet = new Set<string>()
  const catOrder: string[] = []
  for (const node of nodes) {
    if (!catSet.has(node.anchor)) {
      catSet.add(node.anchor)
      catOrder.push(node.anchor)
    }
  }

  // Anchors centred at world-origin (0,0); forceCenter also targets (0,0).
  // The viewport is offset so the canvas centre sits at world (0,0), keeping
  // world-space coordinates small and viewport-independent.
  const anchors = anchorPositions ?? categoryAnchors(catOrder, vw, vh, 0, 0)

  // Use the caller's nodes directly so d3's in-place mutations (x, y, vx, vy, fx, fy)
  // are visible on the same objects the caller holds — essential for drag to work.
  const simNodes = nodes

  // d3-force mutates link.source / link.target from string → node ref after init
  // We pass copies with string ids; the .id() accessor handles the mapping
  const simLinks = links.map((l) => ({ ...l }))

  /**
   * Siła ciągnąca węzeł do jego kotwicy.
   *
   * 0,0085 z prototypu wystarczało dla vaulta o kilkudziesięciu notatkach. Przy
   * siedmiuset plikach w jednej kategorii odpychanie (820) wygrywa z tak słabym
   * ciągiem i skupisko rozdyma się do promienia półtora tysiąca jednostek — czyli
   * kategorie odlatują od swojego przedmiotu, choć kotwice mają dobrze policzone
   * miejsca. Mocniejszy ciąg trzyma je przy kotwicy, a kolizje dalej pilnują, żeby
   * węzły nie siadały sobie na głowie.
   */
  const ANCHOR_PULL = 0.03

  // Custom category-anchor force
  function anchorForce(alpha: number) {
    for (const node of simNodes) {
      // Honour fixed positions (e.g. user-dragged nodes)
      if (node.fx != null) continue
      const anchor = anchors.get(node.anchor)
      if (!anchor) continue
      node.vx = (node.vx ?? 0) + (anchor.x - (node.x ?? 0)) * ANCHOR_PULL * alpha
      node.vy = (node.vy ?? 0) + (anchor.y - (node.y ?? 0)) * ANCHOR_PULL * alpha
    }
  }

  const sim = d3Simulation<SimNode, SimLink>(simNodes)
    .alphaDecay(alphaDecayFor(simNodes.length))
    .alphaMin(0.004) // matches prototype stop threshold
    .force('charge', forceManyBody<SimNode>().strength(-repulsion))
    .force(
      'link',
      forceLink<SimNode, SimLink>(simLinks as SimLink[])
        .id((d) => d.id)
        .distance(linkDist),
    )
    .force(
      'collide',
      // Odstęp 14, nie 30: promień skupiska rośnie jak `odstęp × √liczba`, więc przy
      // siedmiuset plikach trzydziestka robiła z kategorii tarczę o promieniu tysiąca
      // jednostek — i to ona, a nie kotwice, wypychała skupiska daleko od przedmiotu.
      // Węzeł ma promień ~11, więc 25 dalej trzyma je osobno.
      forceCollide<SimNode>().radius((d) => 9 + (d.level ?? 1) * 2.2 + 14),
    )
    .force('center', forceCenter<SimNode>(0, 0).strength(0.05))
    .force('anchors', anchorForce)
    .on('tick', () => {
      const positions = new Map<string, { x: number; y: number }>()
      for (const node of simNodes) {
        positions.set(node.id, { x: node.x ?? 0, y: node.y ?? 0 })
      }
      onTick(positions, sim.alpha())
    })
    .on('end', () => {
      onEnd?.()
    })

  return {
    stop(): void {
      sim.stop()
    },

    restart(): void {
      sim.restart()
    },

    getAlpha(): number {
      return sim.alpha()
    },

    /** Pin or unpin a node.  Pass null to unpin. */
    setNodeFixed(id: string, x: number | null, y: number | null): void {
      const node = simNodes.find((n) => n.id === id)
      if (!node) return
      node.fx = x
      node.fy = y
    },

    /** Reheat the simulation to the given alpha value and restart it. */
    reheat(alpha: number): void {
      sim.alpha(alpha).restart()
    },

    /** Dynamically update physics parameters and reheat. */
    updatePhysics(repulsion: number, linkDist: number): void {
      sim.force('charge', forceManyBody<SimNode>().strength(-repulsion))
      sim.force(
        'link',
        forceLink<SimNode, SimLink>(simLinks as SimLink[])
          .id((d) => d.id)
          .distance(linkDist),
      )
      sim.alpha(0.5).restart()
    },
  }
}
