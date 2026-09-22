import { Viewport } from './Viewport'
import { buildQuadtree, hitTest } from './hitTesting'
import { categoryColor } from '../domain/color/categoryColor'
import { edgeStyle, edgeWidth, nodeTypeScale } from '../domain/graph/edgeStyle'
import type { IGraphRenderer, RendererOptions, NodePosition } from './IGraphRenderer'

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
/** Above this many visible nodes, only big or pointed-at nodes keep their label. */
const LABEL_DENSITY_LIMIT = 400

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
    const graph = this.options.getGraph()
    const node = graph.nodes.find((n) => n.id === id)
    if (!node || node.kind === 'ghost') return 7
    // Must stay in step with the drawn radius, or the outer ring of a big node
    // (semester, subject) would not be clickable.
    return nodeRadius(node.level, node.type)
  }

  private hitAtCanvas(canvasX: number, canvasY: number): string | null {
    if (!this.options) return null
    const positions = this.options.getPositions()
    const qt = buildQuadtree(positions, this.getRadius)
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

    const canvas = this.canvas
    const ctx = this.ctx
    const dpr = window.devicePixelRatio || 1

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

    ctx.clearRect(0, 0, canvas.width, canvas.height)

    const { tx, ty, scale } = this.viewport.getTransform()
    ctx.setTransform(scale * dpr, 0, 0, scale * dpr, tx * dpr, ty * dpr)

    const positions = this.options.getPositions()
    const graph = this.options.getGraph()
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

    // --- Draw edges ---
    const visibleKinds = this.options.getVisibleEdgeKinds?.() ?? new Set<string>()
    ctx.save()
    for (const edge of graph.edges) {
      if (visibleKinds.size > 0 && !visibleKinds.has(edge.kind ?? 'link')) continue

      const src = posMap.get(edge.source)
      const tgt = posMap.get(edge.target)
      if (!src || !tgt) continue

      const bothVisible = visibleIds.has(edge.source) && visibleIds.has(edge.target)
      // Highlight only edges where the focused node is a direct endpoint.
      // Cross-edges between neighbours would misleadingly look like those neighbours are also focused.
      const isHighlighted = hasFocus && (edge.source === dimFocusId || edge.target === dimFocusId)

      let alpha: number
      if (!bothVisible) {
        alpha = 0.04
      } else if (hasFocus) {
        alpha = isHighlighted ? 0.9 : 0.08
      } else {
        alpha = 0.85
      }

      // The KIND of relation is the point of the graph, so it survives focus dimming:
      // a highlighted edge brightens, it does not lose its identity.
      const style = edgeStyle(edge.kind)
      const width = edgeWidth(edge)

      ctx.globalAlpha = alpha
      ctx.strokeStyle = isHighlighted && hasFocus ? SELECTED_COLOR : style.color
      ctx.lineWidth = isHighlighted && hasFocus ? width * 1.6 : width
      ctx.setLineDash(style.dash)
      ctx.beginPath()
      ctx.moveTo(src.x, src.y)
      ctx.lineTo(tgt.x, tgt.y)
      ctx.stroke()
      ctx.setLineDash([])

      if (style.arrow && bothVisible) {
        const targetNode = graph.nodes.find((n) => n.id === edge.target)
        const targetRadius =
          targetNode && targetNode.kind === 'real'
            ? nodeRadius(targetNode.level, targetNode.type)
            : 7
        drawArrowHead(
          ctx,
          src,
          tgt,
          targetRadius,
          isHighlighted && hasFocus ? SELECTED_COLOR : style.color,
        )
      }
    }
    ctx.restore()

    // Render nodes: selected/hovered on top
    const sortedNodes = [...graph.nodes].sort((a, b) => {
      const pa = a.id === selected ? 2 : a.id === hovered ? 1 : 0
      const pb = b.id === selected ? 2 : b.id === hovered ? 1 : 0
      return pa - pb
    })

    // --- Draw nodes ---
    for (const node of sortedNodes) {
      const pos = posMap.get(node.id)
      if (!pos) continue

      const isVisible = visibleIds.has(node.id)
      const isSelected = node.id === selected
      const isHovered = node.id === hovered
      const isDim = hasFocus && !adjacent.has(node.id)
      const alpha = isVisible ? (isDim ? 0.22 : 1) : 0.08

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
        const r = nodeRadius(node.level, node.type)
        const catColor = categoryColor(node.category, overrides)
        const statusColor = node.status === 'in-progress' ? AMBER : node.status === 'completed' ? GREEN : GRAY

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
      if (node.kind === 'real' && isVisible) {
        const r = nodeRadius(node.level, node.type)
        // Prototype rule: show label when r>11 OR hovered OR selected OR nothing focused
        // Level of detail: with thousands of visible nodes, labels turn into a grey mat
        // and cost a text measurement each. Keep them for the big nodes (the skeleton)
        // and for whatever the reader is pointing at.
        const dense = visibleIds.size > LABEL_DENSITY_LIMIT
        const showLabel = dense
          ? r > 14 || isHovered || isSelected
          : r > 11 || isHovered || isSelected || !hasFocus
        if (!showLabel) continue

        const isDimmed = hasFocus && !adjacent.has(node.id)
        const fontSize = isHovered || isSelected ? 12 : 10.5
        const label = node.title

        ctx.save()
        ctx.font = `${isSelected ? 700 : 500} ${fontSize}px Inter, system-ui, sans-serif`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'top'

        const textW = ctx.measureText(label).width
        const padH = 5
        const padV = 3
        const boxW = textW + padH * 2
        const boxH = fontSize + padV * 2
        const bx = pos.x - boxW / 2
        const by = pos.y + r + 5

        // Background pill
        ctx.globalAlpha = isDimmed ? 0 : 0.82
        ctx.fillStyle = LABEL_BG
        ctx.beginPath()
        ctx.roundRect(bx, by, boxW, boxH, 4)
        ctx.fill()

        // Label text
        ctx.globalAlpha = isDimmed ? 0.3 : 1
        ctx.fillStyle = isDimmed ? LABEL_COLOR_DIM : LABEL_COLOR
        ctx.fillText(label, pos.x, by + padV)
        ctx.restore()
      }
    }

    ctx.setTransform(1, 0, 0, 1, 0, 0)

    this.options.onViewportChange?.({
      tx: this.viewport.tx,
      ty: this.viewport.ty,
      scale: this.viewport.scale,
      vw: canvas.clientWidth,
      vh: canvas.clientHeight,
    })
  }
}
