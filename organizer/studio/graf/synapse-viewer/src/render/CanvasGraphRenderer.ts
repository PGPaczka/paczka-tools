import { Viewport } from './Viewport'
import { buildQuadtree, hitTest } from './hitTesting'
import { categoryColor } from '../domain/color/categoryColor'
import { edgeStyle, edgeWidth, isContainerType, nodeTypeScale } from '../domain/graph/edgeStyle'
import {
  DOT_RADIUS_PX,
  adaptRenderScale,
  containerRadius,
  detailLevel,
  discInBounds,
  maxEdgePx,
  placeLabels,
  renderScale,
  segmentOffscreen,
  shouldLabel,
  visibleWorldBounds,
} from './lod'
import type { IGraphRenderer, RendererOptions, NodePosition, RenderStats } from './IGraphRenderer'
import type { GraphNode, KnowledgeGraph } from '../domain/graph/GraphModel'

const BG_COLOR = '#0d1117'
const EDGE_COLOR = '#30363d'
const GHOST_STROKE = '#6e7681'
const SELECTED_COLOR = '#58a6ff'
const AMBER = '#d29922'
const GREEN = '#3fb950'
const GRAY = '#7d8590'
const LABEL_BG = 'rgba(13,17,23,0.82)'
const LABEL_COLOR = '#e6edf3'
const LABEL_COLOR_DIM = '#6e7681'
/** Largest radius any node can take — the zoom test for detail is made against it. */
const MAX_NODE_RADIUS = (9 + 3 * 2.2) * 1.9

/** Edges that look alike are stroked as one path; this is one such group. */
interface EdgeBatch {
  color: string
  width: number
  dash: number[]
  alpha: number
  /** Flat x1,y1,x2,y2 quadruples — a flat array keeps this off the allocator's back. */
  segments: number[]
}

/**
 * Display radius. The level term is the prototype's formula; the type term makes a
 * three-level vault readable — a semester has to look like a container, not like one
 * more file among four thousand.
 */
function nodeRadius(level: number | null, type?: string | null): number {
  return (9 + (level ?? 1) * 2.2) * nodeTypeScale(type)
}

/** Arrow head at the target end, for directed edge kinds. */
function drawArrowHead(
  ctx: CanvasRenderingContext2D,
  from: { x: number; y: number },
  to: { x: number; y: number },
  radius: number,
  color: string,
): void {
  const dx = to.x - from.x
  const dy = to.y - from.y
  const len = Math.hypot(dx, dy)
  if (len < radius + 4) return

  const ux = dx / len
  const uy = dy / len
  // Stop at the node's edge, not its centre.
  const tipX = to.x - ux * radius
  const tipY = to.y - uy * radius
  const size = 6

  ctx.fillStyle = color
  ctx.beginPath()
  ctx.moveTo(tipX, tipY)
  ctx.lineTo(tipX - ux * size - uy * size * 0.5, tipY - uy * size + ux * size * 0.5)
  ctx.lineTo(tipX - ux * size + uy * size * 0.5, tipY - uy * size - ux * size * 0.5)
  ctx.closePath()
  ctx.fill()
}

export class CanvasGraphRenderer implements IGraphRenderer {
  private viewport = new Viewport()
  private options: RendererOptions | null = null
  private canvas: HTMLCanvasElement | null = null
  private ctx: CanvasRenderingContext2D | null = null
  private rafId: number | null = null
  private renderScheduled = false

  /**
   * Node lookup, rebuilt only when the graph itself changes.
   *
   * It replaces a `graph.nodes.find()` inside the edge loop: with four thousand nodes
   * and as many directed edges that was eleven million comparisons PER FRAME, which is
   * most of what made a filtered subject drag while panning.
   */
  private nodeIndex: Map<string, GraphNode> = new Map()
  private nodeIndexFor: KnowledgeGraph | null = null

  /** Koszt ostatnich klatek — mierzony zawsze, pokazywany tylko w `?diag=1`. */
  private stats: RenderStats = {
    drawMs: 0, fps: 0, nodesDrawn: 0, edgesDrawn: 0, renderDpr: 1, deviceDpr: 1, scale: 1,
  }
  private frameTimes: number[] = []
  private lastFrameAt = 0
  /** Bieżąca gęstość rysowania — dostrajana do tego, co urządzenie wyrabia. */
  private currentDpr = 0
  /** Jedno dodatkowe rysowanie po uspokojeniu, żeby obraz wrócił do pełnej ostrości. */
  private sharpenTimer: ReturnType<typeof setTimeout> | null = null

  getStats(): RenderStats {
    return { ...this.stats }
  }

  /** Hit-testing quadtree, kept until the positions it was built from change. */
  private quadtree: ReturnType<typeof buildQuadtree> | null = null
  private quadtreeVersion = -1

  // Fit animation state
  private animating = false
  private animStart = 0
  private animDuration = 420
  private animFromTx = 0
  private animFromTy = 0
  private animFromScale = 1
  private animToTx = 0
  private animToTy = 0
  private animToScale = 1

  // Pan state
  // Touch state. The canvas previously listened to mouse events only, so on a
  // tablet the graph could be neither panned nor zoomed — the browser just scaled
  // the whole page, which blurs an already-rasterised canvas.
  private touchMode: 'none' | 'pan' | 'pinch' = 'none'
  private touchStartX = 0
  private touchStartY = 0
  private touchStartTx = 0
  private touchStartTy = 0
  private pinchStartDistance = 0

  private isPanning = false
  private panStartX = 0
  private panStartY = 0
  private panStartTx = 0
  private panStartTy = 0

  // Drag state
  private isDragging = false
  private dragNodeId: string | null = null
  private dragStartCanvasX = 0
  private dragStartCanvasY = 0
  private dragMoved = false

  // ---------- public API ----------

  mount(options: RendererOptions): void {
    this.options = options
    this.canvas = options.canvas
    // Kontekst zostaje PRZEZROCZYSTY. `alpha: false` wygląda na darmową oszczędność
    // (kompozytor nie musi mieszać warstw), ale zmierzone było dwa i pół raza wolniejsze:
    // 4 przerysowania na sekundę zamiast 11. Zgadywanie o wydajności bywa odwrotne
    // od prawdy — stąd pomiar przed i po każdej takiej zmianie.
    this.ctx = this.canvas.getContext('2d')

    this.viewport.setSize(this.canvas.clientWidth, this.canvas.clientHeight)
    // World (0,0) maps to canvas centre on first paint.
    // forceSimulation centres forces at world (0,0), so this ensures nodes
    // are visible before fitToNodes() is called.
    this.viewport.tx = this.canvas.clientWidth / 2
    this.viewport.ty = this.canvas.clientHeight / 2

    this.canvas.addEventListener('mousemove', this.onCanvasMouseMove)
    this.canvas.addEventListener('mousedown', this.onCanvasMouseDown)
    this.canvas.addEventListener('mouseup', this.onCanvasMouseUp)
    this.canvas.addEventListener('wheel', this.onWheel, { passive: false })
    this.canvas.addEventListener('mouseleave', this.onMouseLeave)
    this.canvas.addEventListener('touchstart', this.onTouchStart, { passive: false })
    this.canvas.addEventListener('touchmove', this.onTouchMove, { passive: false })
    this.canvas.addEventListener('touchend', this.onTouchEnd)
    this.canvas.addEventListener('touchcancel', this.onTouchEnd)
    // Without this the browser claims the gesture and zooms the page instead.
    this.canvas.style.touchAction = 'none'

    this.scheduleRender()
  }

  scheduleRender(): void {
    if (this.renderScheduled) return
    this.renderScheduled = true
    this.rafId = requestAnimationFrame(() => {
      this.renderScheduled = false
      this.draw()
    })
  }

  destroy(): void {
    if (this.rafId !== null) {
      cancelAnimationFrame(this.rafId)
      this.rafId = null
    }
    if (this.canvas) {
      this.canvas.removeEventListener('mousemove', this.onCanvasMouseMove)
      this.canvas.removeEventListener('mousedown', this.onCanvasMouseDown)
      this.canvas.removeEventListener('mouseup', this.onCanvasMouseUp)
      this.canvas.removeEventListener('wheel', this.onWheel)
      this.canvas.removeEventListener('mouseleave', this.onMouseLeave)
      this.canvas.removeEventListener('touchstart', this.onTouchStart)
      this.canvas.removeEventListener('touchmove', this.onTouchMove)
      this.canvas.removeEventListener('touchend', this.onTouchEnd)
      this.canvas.removeEventListener('touchcancel', this.onTouchEnd)
    }
    if (this.sharpenTimer !== null) {
      clearTimeout(this.sharpenTimer)
      this.sharpenTimer = null
    }
    this.options = null
    this.canvas = null
    this.ctx = null
  }

  fitToNodes(duration = 420): void {
    if (!this.options || !this.canvas) return
    if (this.canvas.clientWidth === 0 || this.canvas.clientHeight === 0) return
    const all = this.options.getPositions()
    if (all.length === 0) return

    // Fit to what the reader can actually SEE. The simulation keeps positions for every
    // node, including those hidden by filters, so fitting to all of them zooms out far
    // enough to show a filtered handful as dust — which is what a large, filtered vault
    // looked like before this.
    const visibleIds = this.options.getVisibleIds()
    const visible = visibleIds.size > 0 ? all.filter((p) => visibleIds.has(p.id)) : all
    const positions = visible.length > 0 ? visible : all

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
    for (const p of positions) {
      if (p.x < minX) minX = p.x
      if (p.y < minY) minY = p.y
      if (p.x > maxX) maxX = p.x
      if (p.y > maxY) maxY = p.y
    }

    this.viewport.setSize(this.canvas.clientWidth, this.canvas.clientHeight)
    const target = this.viewport.computeFitView(minX, minY, maxX, maxY)

    // Start from current viewport (which may already be mid-animation)
    this.animFromTx    = this.viewport.tx
    this.animFromTy    = this.viewport.ty
    this.animFromScale = this.viewport.scale
    this.animToTx      = target.tx
    this.animToTy      = target.ty
    this.animToScale   = target.scale
    this.animStart     = performance.now()
    this.animDuration  = duration
    this.animating     = true

    this.scheduleRender()
  }

  handleWindowMouseMove(clientX: number, clientY: number): void {
    if (!this.canvas) return
    const rect = this.canvas.getBoundingClientRect()
    const canvasX = clientX - rect.left
    const canvasY = clientY - rect.top

    if (this.isDragging && this.dragNodeId && this.options) {
      const dx = Math.abs(canvasX - this.dragStartCanvasX)
      const dy = Math.abs(canvasY - this.dragStartCanvasY)
      if (dx > 3 || dy > 3) this.dragMoved = true
      const world = this.viewport.toWorld(canvasX, canvasY)
      this.options.onNodeDrag?.(this.dragNodeId, world.x, world.y)
      this.scheduleRender()
      return
    }

    if (this.isPanning) {
      this.animating = false  // user takes control — cancel any ongoing fit animation
      const rawTx = this.panStartTx + (canvasX - this.panStartX)
      const rawTy = this.panStartTy + (canvasY - this.panStartY)
      const [tx, ty] = this.clampPan(rawTx, rawTy)
      this.viewport.tx = tx
      this.viewport.ty = ty
      this.options?.onUserMove?.()
      this.scheduleRender()
    }
  }

  handleWindowMouseUp(): void {
    if (this.isDragging && this.dragNodeId) {
      this.options?.onNodeDragEnd?.(this.dragNodeId)
      if (!this.dragMoved) {
        this.options?.onNodeClick(this.dragNodeId)
      }
      this.isDragging = false
      this.dragNodeId = null
      if (this.canvas) this.canvas.style.cursor = 'default'
    }
    this.isPanning = false
  }

  // ---------- private helpers ----------

  private canvasPoint(e: MouseEvent): { x: number; y: number } {
    const rect = this.canvas!.getBoundingClientRect()
    return { x: e.clientX - rect.left, y: e.clientY - rect.top }
  }

  private getRadius = (id: string): number => {
    if (!this.options) return 9
    // Through the index, not `nodes.find`: hit testing asks for the radius of every
    // candidate under the cursor, and a linear scan of four thousand nodes per ask
    // turned hovering into work.
    const node = this.nodeIndexOf(this.options.getGraph()).get(id)
    if (!node || node.kind === 'ghost') return 7
    // Must stay in step with the drawn radius, or the outer ring of a big node
    // (semester, subject) would not be clickable.
    return nodeRadius(node.level, node.type)
  }

  /** Czy ten węzeł trzyma inne (semestr, przedmiot, kategoria)? Ghost nigdy nie trzyma. */
  private isContainer(id: string): boolean {
    const node = this.nodeIndex.get(id)
    return node !== undefined && node.kind === 'real' && isContainerType(node.type ?? null)
  }

  /** Node lookup for this graph, rebuilt only when the graph itself changes. */
  private nodeIndexOf(graph: KnowledgeGraph): Map<string, GraphNode> {
    if (this.nodeIndexFor !== graph) {
      this.nodeIndex = new Map(graph.nodes.map((node) => [node.id, node]))
      this.nodeIndexFor = graph
    }
    return this.nodeIndex
  }

  private hitAtCanvas(canvasX: number, canvasY: number): string | null {
    if (!this.options) return null
    // The quadtree is rebuilt when the layout moves, not when the pointer does.
    const version = this.options.getPositionsVersion?.() ?? -1
    if (this.quadtree === null || version !== this.quadtreeVersion || version === -1) {
      this.quadtree = buildQuadtree(this.options.getPositions(), this.getRadius)
      this.quadtreeVersion = version
    }
    const qt = this.quadtree
    const world = this.viewport.toWorld(canvasX, canvasY)
    const selected = this.options.getSelected()
    const hovered = this.options.getHovered()
    const priority = [selected, hovered].filter((id): id is string => id != null)
    return hitTest(qt, world.x, world.y, this.getRadius, priority)
  }

  // ---------- event handlers ----------

  private readonly onCanvasMouseMove = (e: MouseEvent): void => {
    if (!this.options) return
    // Drag and pan are handled by the window-level listener (handleWindowMouseMove),
    // which also fires for movements outside the canvas. Skip here to avoid double-calling.
    if (this.isDragging || this.isPanning) return

    const { x, y } = this.canvasPoint(e)
    const hit = this.hitAtCanvas(x, y)
    this.options.onNodeHover(hit)
    this.canvas!.style.cursor = hit ? 'pointer' : 'default'
    this.scheduleRender()
  }

  private readonly onCanvasMouseDown = (e: MouseEvent): void => {
    if (e.button !== 0) return
    const { x, y } = this.canvasPoint(e)
    const hit = this.hitAtCanvas(x, y)

    if (hit) {
      this.isDragging = true
      this.dragNodeId = hit
      this.dragStartCanvasX = x
      this.dragStartCanvasY = y
      this.dragMoved = false
      const world = this.viewport.toWorld(x, y)
      this.options?.onNodeDragStart?.(hit, world.x, world.y)
      this.canvas!.style.cursor = 'grabbing'
    } else {
      this.isPanning = true
      this.panStartX = x
      this.panStartY = y
      this.panStartTx = this.viewport.tx
      this.panStartTy = this.viewport.ty
      this.canvas!.style.cursor = 'grabbing'
    }
  }

  private readonly onCanvasMouseUp = (_e: MouseEvent): void => {
    if (this.isDragging && this.dragNodeId) {
      this.options?.onNodeDragEnd?.(this.dragNodeId)
      if (!this.dragMoved) {
        this.options?.onNodeClick(this.dragNodeId)
      }
      this.isDragging = false
      this.dragNodeId = null
      this.canvas!.style.cursor = 'default'
    } else if (this.isPanning) {
      this.isPanning = false
      this.canvas!.style.cursor = 'default'
    }
  }

  private readonly onWheel = (e: WheelEvent): void => {
    if (!this.canvas) return
    e.preventDefault()
    this.animating = false  // user zooms — cancel fit animation immediately
    const { x, y } = this.canvasPoint(e)
    this.viewport.applyWheel(e.deltaY, x, y)
    this.options?.onUserMove?.()
    this.scheduleRender()
  }

  // ---------- touch ----------

  private touchPoint(t: Touch): { x: number; y: number } {
    const rect = this.canvas!.getBoundingClientRect()
    return { x: t.clientX - rect.left, y: t.clientY - rect.top }
  }

  private static distance(a: Touch, b: Touch): number {
    return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY)
  }

  private readonly onTouchStart = (e: TouchEvent): void => {
    if (!this.canvas) return
    this.animating = false
    this.touchStartTx = this.viewport.tx
    this.touchStartTy = this.viewport.ty
    if (e.touches.length === 1) {
      const { x, y } = this.touchPoint(e.touches[0])
      this.touchMode = 'pan'
      this.touchStartX = x
      this.touchStartY = y
    } else if (e.touches.length >= 2) {
      this.touchMode = 'pinch'
      this.pinchStartDistance = CanvasGraphRenderer.distance(e.touches[0], e.touches[1])
    }
  }

  private readonly onTouchMove = (e: TouchEvent): void => {
    if (!this.canvas || this.touchMode === 'none') return
    e.preventDefault()

    if (this.touchMode === 'pan' && e.touches.length === 1) {
      const { x, y } = this.touchPoint(e.touches[0])
      const [tx, ty] = this.clampPan(
        this.touchStartTx + (x - this.touchStartX),
        this.touchStartTy + (y - this.touchStartY),
      )
      this.viewport.tx = tx
      this.viewport.ty = ty
    } else if (e.touches.length >= 2) {
      const distance = CanvasGraphRenderer.distance(e.touches[0], e.touches[1])
      if (this.pinchStartDistance > 0) {
        // Anchor the zoom at the midpoint between the fingers, the way a map does.
        const a = this.touchPoint(e.touches[0])
        const b = this.touchPoint(e.touches[1])
        this.viewport.zoomBy(distance / this.pinchStartDistance, (a.x + b.x) / 2, (a.y + b.y) / 2)
      }
      this.pinchStartDistance = distance
      this.touchMode = 'pinch'
    }

    this.options?.onUserMove?.()
    this.scheduleRender()
  }

  private readonly onTouchEnd = (): void => {
    this.touchMode = 'none'
    this.pinchStartDistance = 0
  }

  private readonly onMouseLeave = (): void => {
    if (this.options) this.options.onNodeHover(null)
  }

  // ---------- rendering ----------

  /**
   * Clamp a candidate (tx, ty) so the user can't pan all nodes off screen.
   * Guarantees at least `margin` CSS pixels of graph content remain visible
   * on each edge of the canvas.
   */
  private clampPan(tx: number, ty: number): [number, number] {
    if (!this.options || !this.canvas) return [tx, ty]
    const positions = this.options.getPositions()
    if (positions.length === 0) return [tx, ty]

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
    for (const p of positions) {
      if (p.x < minX) minX = p.x
      if (p.y < minY) minY = p.y
      if (p.x > maxX) maxX = p.x
      if (p.y > maxY) maxY = p.y
    }

    const margin = 100  // minimum screen-px of graph content to keep visible
    const sc = this.viewport.scale
    const vw = this.canvas.clientWidth
    const vh = this.canvas.clientHeight

    // screen_x = world_x * sc + tx
    // rightmost node must stay >= margin from left:  maxX * sc + tx >= margin
    // leftmost  node must stay <= vw-margin from left: minX * sc + tx <= vw - margin
    const clampedTx = Math.max(margin - maxX * sc, Math.min(vw - margin - minX * sc, tx))
    const clampedTy = Math.max(margin - maxY * sc, Math.min(vh - margin - minY * sc, ty))
    return [clampedTx, clampedTy]
  }

  private draw(): void {
    if (!this.ctx || !this.canvas || !this.options) return
    const drawStartedAt = performance.now()

    const canvas = this.canvas
    const ctx = this.ctx
    const deviceDpr = window.devicePixelRatio || 1
    if (this.currentDpr === 0) this.currentDpr = renderScale(deviceDpr)
    const gaps0 = [...this.frameTimes].sort((a, b) => a - b)
    const medianGap = gaps0.length >= 6 ? gaps0[Math.floor(gaps0.length / 2)] : 0
    // „Cisza" = od ostatniej klatki minęło więcej niż pół sekundy, czyli nikt nie rusza
    // grafem; wtedy wolno wrócić do pełnej ostrości bez ryzyka szarpnięcia.
    const idle = this.lastFrameAt > 0 && performance.now() - this.lastFrameAt > 500
    this.currentDpr = adaptRenderScale(
      this.currentDpr, medianGap || 0, deviceDpr, idle || medianGap === 0,
    )
    const dpr = this.currentDpr

    const cssW = canvas.clientWidth
    const cssH = canvas.clientHeight
    // Canvas is hidden (display:none) — skip entirely to avoid corrupting viewport state
    if (cssW === 0 || cssH === 0) return
    if (canvas.width !== Math.round(cssW * dpr) || canvas.height !== Math.round(cssH * dpr)) {
      canvas.width = Math.round(cssW * dpr)
      canvas.height = Math.round(cssH * dpr)
      this.viewport.setSize(cssW, cssH)
    }

    // Animate viewport toward fit target (ease-out cubic)
    if (this.animating) {
      const elapsed = performance.now() - this.animStart
      const t = Math.min(elapsed / this.animDuration, 1)
      const e = 1 - Math.pow(1 - t, 3)  // ease-out cubic
      this.viewport.tx    = this.animFromTx    + (this.animToTx    - this.animFromTx)    * e
      this.viewport.ty    = this.animFromTy    + (this.animToTy    - this.animFromTy)    * e
      this.viewport.scale = this.animFromScale + (this.animToScale - this.animFromScale) * e
      if (t < 1) {
        this.scheduleRender()  // keep the loop alive until done
      } else {
        this.animating = false
      }
    }

    // Nieprzezroczysty kontekst trzeba zamalować, a nie wyczyścić do przezroczystości.
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    const { tx, ty, scale } = this.viewport.getTransform()
    ctx.setTransform(scale * dpr, 0, 0, scale * dpr, tx * dpr, ty * dpr)

    const positions = this.options.getPositions()
    const graph = this.options.getGraph()
    this.nodeIndexOf(graph)
    const selected = this.options.getSelected()
    const hovered = this.options.getHovered()
    const visibleIds = this.options.getVisibleIds()

    const posMap = new Map<string, NodePosition>()
    for (const p of positions) posMap.set(p.id, p)

    const overrides = this.options.getCatColorOverrides()
    const colorPriority = this.options.getColorPriority()
    const secondaryOn = this.options.getSecondaryColorEnabled()

    // Determine focus state: when something is hovered or selected, dim others
    const hasFocus = hovered !== null || selected !== null

    // Build adjacency for dimming.
    // Selection takes priority over hover: when a node is selected, its neighbourhood
    // stays visible even while hovering elsewhere. Hover only controls adjacency when
    // nothing is selected (lightweight exploration mode).
    const dimFocusId = selected ?? hovered  // null when nothing is focused
    const adjacent = new Set<string>()
    if (dimFocusId) {
      adjacent.add(dimFocusId)
      for (const edge of graph.edges) {
        if (edge.source === dimFocusId) adjacent.add(edge.target)
        if (edge.target === dimFocusId) adjacent.add(edge.source)
      }
    }

    // Only what is on screen gets drawn, and only in the detail the zoom can show.
    const bounds = visibleWorldBounds(tx, ty, scale, cssW, cssH)
    const detail = detailLevel(scale, MAX_NODE_RADIUS)

    // Ile węzłów jest NA EKRANIE — nie ile przepuścił filtr. Po tej liczbie idą dwie
    // decyzje: czy rysować krawędzie uciekające poza ekran i czy starczy miejsca na
    // etykiety. Licząc po filtrze, przedmiot z 2,5 tys. plików był „gęsty" zawsze,
    // także wtedy, gdy na ekranie widać trzysta węzłów z nazwami do przeczytania.
    const onScreen = new Set<string>()
    for (const p of positions) {
      if (visibleIds.has(p.id) && discInBounds(bounds, p.x, p.y, MAX_NODE_RADIUS)) {
        onScreen.add(p.id)
      }
    }
    const edgeLimitPx = maxEdgePx(detail.richNodes, cssW, cssH)

    // --- Draw edges ---
    // Batched by appearance: one path per (colour, dash, width) instead of one path,
    // one state change and one stroke per edge. At subject scope that is ~2500 strokes
    // collapsed into a handful.
    const visibleKinds = this.options.getVisibleEdgeKinds?.() ?? new Set<string>()
    const batches = new Map<string, EdgeBatch>()
    let edgesDrawn = 0
    const arrows: { src: NodePosition; tgt: NodePosition; radius: number; color: string }[] = []
    ctx.save()
    for (const edge of graph.edges) {
      if (visibleKinds.size > 0 && !visibleKinds.has(edge.kind ?? 'link')) continue

      // Filtered-out edges are not drawn at all. Keeping them at a low alpha left a
      // grey haze around the filtered subgraph, which is exactly what made a filtered
      // view look like dust instead of an answer.
      if (!visibleIds.has(edge.source) || !visibleIds.has(edge.target)) continue

      const src = posMap.get(edge.source)
      const tgt = posMap.get(edge.target)
      if (!src || !tgt) continue
      if (segmentOffscreen(bounds, src.x, src.y, tgt.x, tgt.y)) continue
      // Kręgosłup hierarchii — połączenia między kontenerami (przedmiot → kategorie,
      // semestr → przedmioty) — zostaje ZAWSZE. Jest ich kilkanaście, a to one pokazują,
      // z czego składa się to, na co patrzysz; reguła długości chroni przed tłumem
      // plików, nie przed nimi.
      const spine = this.isContainer(edge.source) && this.isContainer(edge.target)
      if (!spine && Math.hypot(tgt.x - src.x, tgt.y - src.y) * scale > edgeLimitPx) continue

      // Highlight only edges where the focused node is a direct endpoint.
      // Cross-edges between neighbours would misleadingly look like those neighbours are also focused.
      const isHighlighted = hasFocus && (edge.source === dimFocusId || edge.target === dimFocusId)
      const alpha = hasFocus ? (isHighlighted ? 0.9 : 0.08) : 0.85

      // The KIND of relation is the point of the graph, so it survives focus dimming:
      // a highlighted edge brightens, it does not lose its identity.
      const style = edgeStyle(edge.kind)
      const color = isHighlighted && hasFocus ? SELECTED_COLOR : style.color
      const width = isHighlighted && hasFocus ? edgeWidth(edge) * 1.6 : edgeWidth(edge)

      // Grubość jest w jednostkach świata, więc przy oddaleniu linia potrafi zejść
      // poniżej piksela i zniknąć. Kręgosłup ma być widoczny przy każdym przybliżeniu.
      const drawWidth = spine ? Math.max(width, 1.6 / scale) : width
      const key = `${color}|${drawWidth}|${style.dash.join(',')}|${alpha}`
      let batch = batches.get(key)
      if (batch === undefined) {
        batch = { color, width: drawWidth, dash: style.dash, alpha, segments: [] }
        batches.set(key, batch)
      }
      batch.segments.push(src.x, src.y, tgt.x, tgt.y)
      edgesDrawn++

      if (style.arrow && detail.arrows) {
        const targetNode = this.nodeIndex.get(edge.target)
        const targetRadius =
          targetNode && targetNode.kind === 'real'
            ? nodeRadius(targetNode.level, targetNode.type)
            : 7
        arrows.push({ src, tgt, radius: targetRadius, color })
      }
    }
    for (const batch of batches.values()) {
      ctx.globalAlpha = batch.alpha
      ctx.strokeStyle = batch.color
      ctx.lineWidth = batch.width
      ctx.setLineDash(batch.dash)
      ctx.beginPath()
      for (let i = 0; i < batch.segments.length; i += 4) {
        ctx.moveTo(batch.segments[i], batch.segments[i + 1])
        ctx.lineTo(batch.segments[i + 2], batch.segments[i + 3])
      }
      ctx.stroke()
    }
    ctx.setLineDash([])
    // Arrow heads carry direction, so they keep their own pass — but only at a zoom
    // where a six-pixel head is not bigger than the node it points at.
    for (const arrow of arrows) {
      drawArrowHead(ctx, arrow.src, arrow.tgt, arrow.radius, arrow.color)
    }
    ctx.restore()

    // Render nodes: selected/hovered on top. Sorting four thousand nodes on every frame
    // cost a copy and a sort for the sake of at most two of them, so the two are simply
    // drawn last.
    const onTop: GraphNode[] = []
    const drawOrder: GraphNode[] = []
    for (const node of graph.nodes) {
      // Kontenery idą na wierzch razem z zaznaczonym: w gęstwinie plików węzeł
      // przedmiotu ginął pod nimi, choć to on jest punktem odniesienia.
      if (node.id === selected || node.id === hovered || this.isContainer(node.id)) {
        onTop.push(node)
      } else drawOrder.push(node)
    }

    // --- Draw nodes ---
    // At a zoom where a node is a couple of pixels wide, its ring, inner dot and
    // secondary stroke all land on the same pixel — so nodes are collected by colour
    // and drawn as one path each. Two and a half thousand fills become a handful.
    const dots = new Map<string, number[]>()
    interface LabelDraw {
      /** Pozycja węzła w świecie — na ekran przeliczamy ją dopiero przy rysowaniu. */
      x: number; y: number
      /** Odstęp pod węzłem, już w pikselach ekranu. */
      offset: number
      text: string; focused: boolean; bold: boolean; dimmed: boolean
      /** Im grubszy poziom, tym wyżej w kolejce po miejsce na podpis. */
      priority: number
      /** Promień NATURALNY na ekranie — bez podniesienia do minimalnej widoczności. */
      radiusPx: number
    }
    const labels: LabelDraw[] = []
    const containerLabels: LabelDraw[] = []
    let nodesDrawn = 0

    for (const node of drawOrder.concat(onTop)) {
      const pos = posMap.get(node.id)
      if (!pos) continue
      if (!discInBounds(bounds, pos.x, pos.y, MAX_NODE_RADIUS)) continue

      const isVisible = visibleIds.has(node.id)
      if (isVisible) nodesDrawn++
      // A node excluded by a filter disappears. It used to be drawn at alpha 0.08,
      // so a filtered graph still showed every one of four thousand nodes as a speck —
      // and since the view fits to the VISIBLE ones, the result looked like the filter
      // had done nothing.
      if (!isVisible) continue
      const isSelected = node.id === selected
      const isHovered = node.id === hovered
      const isDim = hasFocus && !adjacent.has(node.id)
      const alpha = isDim ? 0.22 : 1

      // Próg liczony dla TEGO węzła: plik przy skali, w której semestr jest jeszcze
      // czytelnym kółkiem, ma już półtora piksela i cały jego rysunek ląduje na jednym.
      const container = node.kind === 'real' && isContainerType(node.type ?? null)
      const baseRadius = node.kind === 'ghost' ? 7 : nodeRadius(node.level, node.type)
      const radius = container ? containerRadius(baseRadius, scale) : baseRadius
      if (radius * scale < DOT_RADIUS_PX && !isSelected && !isHovered && !container) {
        // Kolor niesie znaczenie także przy oddaleniu (to po nim widać skupiska
        // semestrów), więc grupujemy PO KOLORZE, a nie rysujemy wszystkiego na szaro.
        const color =
          node.kind === 'ghost'
            ? GHOST_STROKE
            : colorPriority === 'status'
              ? node.status === 'in-progress'
                ? AMBER
                : node.status === 'completed'
                  ? GREEN
                  : GRAY
              : categoryColor(node.category, overrides)
        const key = isDim ? `${color}|dim` : color
        let bucket = dots.get(key)
        if (bucket === undefined) {
          bucket = []
          dots.set(key, bucket)
        }
        // Poniżej piksela kropka znika w zaokrągleniu — trzymamy minimum widoczności.
        bucket.push(pos.x, pos.y, Math.max(radius, 1.2 / scale))
        continue
      }

      ctx.save()
      ctx.globalAlpha = alpha

      if (node.kind === 'ghost') {
        const r = 7
        ctx.setLineDash([4, 3])
        ctx.strokeStyle = GHOST_STROKE
        ctx.lineWidth = 1.5
        ctx.beginPath()
        ctx.arc(pos.x, pos.y, r, 0, Math.PI * 2)
        ctx.stroke()
        ctx.setLineDash([])
      } else {
        const r = radius
        const catColor = categoryColor(node.category, overrides)
        const statusColor = node.status === 'in-progress' ? AMBER : node.status === 'completed' ? GREEN : GRAY

        // Poświata wokół kontenera: przedmiot i kategorie mają się wyróżniać z tłumu
        // plików bez powiększania ich do rozmiaru, przy którym zasłaniają sąsiadów.
        if (container && !isHovered && !isSelected) {
          ctx.globalAlpha = alpha * 0.14
          ctx.fillStyle = catColor
          ctx.beginPath()
          ctx.arc(pos.x, pos.y, r + Math.max(6, r * 0.5), 0, Math.PI * 2)
          ctx.fill()
          ctx.globalAlpha = alpha
        }

        // Glow ring for hovered/selected (always category colour)
        if (isHovered || isSelected) {
          ctx.globalAlpha = alpha * 0.18
          ctx.fillStyle = catColor
          ctx.beginPath()
          ctx.arc(pos.x, pos.y, r + 7, 0, Math.PI * 2)
          ctx.fill()
          ctx.globalAlpha = alpha
        }

        // colorPriority: 'category' → cat fill + status stroke (default)
        //                'status'   → status fill + cat stroke
        const mainFill = colorPriority === 'status' ? statusColor : catColor
        const mainStroke = colorPriority === 'status' ? catColor : statusColor

        // Node fill & stroke
        if (node.status === 'not-started') {
          // Hollow ring + tiny inner dot
          ctx.beginPath()
          ctx.arc(pos.x, pos.y, r, 0, Math.PI * 2)
          ctx.fillStyle = BG_COLOR
          ctx.fill()
          ctx.strokeStyle = colorPriority === 'status' ? GRAY : catColor
          ctx.lineWidth = 2.2
          ctx.stroke()
          ctx.fillStyle = colorPriority === 'status' ? GRAY : catColor
          ctx.globalAlpha = alpha * 0.85
          ctx.beginPath()
          ctx.arc(pos.x, pos.y, Math.max(2, r * 0.34), 0, Math.PI * 2)
          ctx.fill()
          ctx.globalAlpha = alpha
        } else if (node.status === 'in-progress') {
          // Hollow ring + large inner fill (minimal gap) — same colour logic as other
          // nodes so colorPriority is respected (e.g. category=white stays white).
          ctx.beginPath()
          ctx.arc(pos.x, pos.y, r, 0, Math.PI * 2)
          ctx.fillStyle = BG_COLOR
          ctx.fill()
          ctx.strokeStyle = mainFill
          ctx.lineWidth = 2.2
          ctx.stroke()
          ctx.fillStyle = mainFill
          ctx.beginPath()
          ctx.arc(pos.x, pos.y, Math.max(3, r - 3.5), 0, Math.PI * 2)
          ctx.fill()
        } else {
          // completed / other — solid fill
          ctx.beginPath()
          ctx.arc(pos.x, pos.y, r, 0, Math.PI * 2)
          ctx.fillStyle = mainFill
          ctx.fill()
          if (secondaryOn) {
            ctx.strokeStyle = mainStroke
            ctx.lineWidth = 2.4
            ctx.stroke()
          }
        }

        // Selection ring
        if (isSelected) {
          ctx.beginPath()
          ctx.arc(pos.x, pos.y, r + 3.5, 0, Math.PI * 2)
          ctx.strokeStyle = SELECTED_COLOR
          ctx.lineWidth = 1.8
          ctx.stroke()
        }
      }

      ctx.restore()

      // --- Labels ---
      // Zbierane, nie rysowane od razu: ustawienie `ctx.font` jest jedną z droższych
      // operacji kontekstu, a tak wystarczy raz na klatkę zamiast raz na etykietę.
      // Przy okazji żadna etykieta nie chowa się pod węzłem narysowanym później.
      if (
        node.kind === 'real' && isVisible &&
        shouldLabel(radius * scale, onScreen.size, isHovered || isSelected, container)
      ) {
        const draw: LabelDraw = {
          x: pos.x,
          y: pos.y,
          offset: radius * scale + 5,
          text: node.title,
          focused: isHovered || isSelected || container,
          bold: isSelected || container,
          dimmed: hasFocus && !adjacent.has(node.id),
          // Wskazany palcem albo wybrany węzeł wygrywa z całą hierarchią: to jego
          // nazwy człowiek w tej chwili szuka.
          priority: (isHovered || isSelected ? 10 : 0) +
            nodeTypeScale(node.kind === 'real' ? node.type : null),
          radiusPx: baseRadius * scale,
        }
        if (container && !isHovered && !isSelected) containerLabels.push(draw)
        else labels.push(draw)
      }
    }

    for (const [key, bucket] of dots) {
      const [color, dim] = key.split('|')
      ctx.globalAlpha = dim ? 0.22 : 1
      ctx.fillStyle = color
      ctx.beginPath()
      for (let i = 0; i < bucket.length; i += 3) {
        const x = bucket[i]
        const y = bucket[i + 1]
        const r = bucket[i + 2]
        ctx.moveTo(x + r, y)
        ctx.arc(x, y, r, 0, Math.PI * 2)
      }
      ctx.fill()
    }
    ctx.globalAlpha = 1

    // Kontenery dorzucamy bez filtrowania: o tym, ile z nich da się podpisać, rozstrzyga
    // układanie prostokątów niżej — czyli to, czy nazwy na siebie NACHODZĄ.
    for (const label of containerLabels) labels.push(label)

    // --- Labels, in one pass, in SCREEN space ---
    // Tekst rysowany w jednostkach świata kurczy się razem z grafem: przy widoku całej
    // paczki (skala 0,05) dwunastopunktowa etykieta miała pół piksela, więc podpisy
    // semestrów i przedmiotów po prostu znikały. W przestrzeni ekranu są zawsze czytelne
    // i przy okazji ostre, bo nie przechodzą przez skalowanie.
    if (labels.length > 0) {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.textAlign = 'center'
      ctx.textBaseline = 'top'
      const padH = 5
      const padV = 3

      // Najpierw zmierz, potem rozstrzygnij, co się mieści, a dopiero na końcu rysuj.
      // Bez tego kroku nazwy kategorii skupionych wokół jednego przedmiotu zlepiały się
      // w plamę — a żaden próg przybliżenia tego nie rozróżni od siedmiu kategorii
      // rozrzuconych daleko od siebie, gdzie wszystkie da się przeczytać.
      let font = ''
      const boxes = labels.map((label) => {
        const fontSize = label.focused ? 12 : 10.5
        const wanted = `${label.bold ? 700 : 500} ${fontSize}px Inter, system-ui, sans-serif`
        if (wanted !== font) {
          ctx.font = wanted
          font = wanted
        }
        const sx = label.x * scale + tx
        const sy = label.y * scale + ty + label.offset
        const w = ctx.measureText(label.text).width + padH * 2
        const h = fontSize + padV * 2
        return { label, fontSize, x: sx - w / 2, y: sy, w, h, priority: label.priority }
      })

      font = ''
      for (const box of placeLabels(boxes)) {
        const wanted =
          `${box.label.bold ? 700 : 500} ${box.fontSize}px Inter, system-ui, sans-serif`
        if (wanted !== font) {
          ctx.font = wanted
          font = wanted
        }

        ctx.globalAlpha = box.label.dimmed ? 0 : 0.82
        ctx.fillStyle = LABEL_BG
        ctx.beginPath()
        ctx.roundRect(box.x, box.y, box.w, box.h, 4)
        ctx.fill()

        ctx.globalAlpha = box.label.dimmed ? 0.3 : 1
        ctx.fillStyle = box.label.dimmed ? LABEL_COLOR_DIM : LABEL_COLOR
        ctx.fillText(box.label.text, box.x + box.w / 2, box.y + padV)
      }
      ctx.globalAlpha = 1
    }

    ctx.setTransform(1, 0, 0, 1, 0, 0)

    // Pomiar jest tani (dwa odczyty zegara) i dzięki niemu „laguje" da się zamienić
    // na liczbę z konkretnego urządzenia, zamiast zgadywać po opisie.
    const finishedAt = performance.now()
    const gap = finishedAt - this.lastFrameAt
    // Przerwy dłuższe niż pół sekundy to bezczynność (graf rysuje się na żądanie),
    // a nie wolna klatka — wliczone, zaniżałyby odczyt akurat wtedy, gdy nic nie boli.
    if (this.lastFrameAt > 0 && gap < 500) {
      this.frameTimes.push(gap)
      if (this.frameTimes.length > 30) this.frameTimes.shift()
    }
    this.lastFrameAt = finishedAt
    const gaps = [...this.frameTimes].sort((a, b) => a - b)
    this.stats = {
      drawMs: Math.round((finishedAt - drawStartedAt) * 10) / 10,
      fps: gaps.length > 0 ? Math.round(1000 / gaps[Math.floor(gaps.length / 2)]) : 0,
      nodesDrawn,
      edgesDrawn,
      renderDpr: dpr,
      deviceDpr,
      scale: Math.round(scale * 1000) / 1000,
    }

    // Obniżona gęstość to cena za ruch, nie trwałe pogorszenie: gdy ruch ustanie,
    // rysujemy jeszcze raz w pełnej ostrości. Bez tego obraz zostawał rozmyty, bo po
    // puszczeniu palca nic już nie zleca kolejnej klatki.
    if (this.sharpenTimer !== null) clearTimeout(this.sharpenTimer)
    if (dpr < renderScale(deviceDpr)) {
      this.sharpenTimer = setTimeout(() => {
        this.sharpenTimer = null
        this.scheduleRender()
      }, 650)
    }

    this.options.onViewportChange?.({
      tx: this.viewport.tx,
      ty: this.viewport.ty,
      scale: this.viewport.scale,
      vw: canvas.clientWidth,
      vh: canvas.clientHeight,
    })
  }
}
