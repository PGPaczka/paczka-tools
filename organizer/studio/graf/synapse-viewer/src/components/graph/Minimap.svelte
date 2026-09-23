<script lang="ts">
  /**
   * Overview of the whole layout, with the current viewport drawn on top.
   *
   * It used to be an SVG with one <circle> per node and one <line> per edge. For a
   * course package that is ~10 000 DOM elements, and the viewport rectangle changes on
   * every single pan frame — so the browser re-painted all of them, continuously. On a
   * phone that cost around half a second per frame while the graph itself drew in 3 ms:
   * the graph was smooth and the minimap was strangling it.
   *
   * Now it is a canvas with two layers. The layout goes into an offscreen bitmap that is
   * only redrawn when the positions or the filters change; a pan just blits that bitmap
   * and strokes one rectangle.
   */
  import { onDestroy } from 'svelte'

  import { graph, visibleNodeIds } from '../../stores/graphStore'
  import { minimapPositions, minimapViewport } from '../../stores/minimapStore'
  import { categoryColor } from '../../domain/color/categoryColor'
  import { settings } from '../../stores/settingsStore'
  import type { RealNode } from '../../domain/graph/GraphModel'

  const W = 172
  const H = 118
  const PAD = 20

  let canvas: HTMLCanvasElement | undefined
  let layer: HTMLCanvasElement | null = null
  let layerDirty = true
  let frame: number | null = null

  $: positions = $minimapPositions
  $: vp = $minimapViewport
  $: graphData = $graph
  $: visIds = $visibleNodeIds
  $: overrides = $settings.catColorOverrides

  // Bounding box of the layout, in world units.
  $: bbox = (() => {
    if (positions.size === 0) return { minX: 0, minY: 0, maxX: W, maxY: H }
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
    for (const { x, y } of positions.values()) {
      if (x < minX) minX = x
      if (y < minY) minY = y
      if (x > maxX) maxX = x
      if (y > maxY) maxY = y
    }
    return { minX: minX - PAD, minY: minY - PAD, maxX: maxX + PAD, maxY: maxY + PAD }
  })()

  $: scaleX = W / ((bbox.maxX - bbox.minX) || W)
  $: scaleY = H / ((bbox.maxY - bbox.minY) || H)

  // Anything that changes the PICTURE invalidates the cached layer; the viewport alone
  // does not, which is the whole point.
  $: {
    void positions
    void graphData
    void visIds
    void overrides
    void bbox
    layerDirty = true
    schedule()
  }

  // The viewport rectangle moves with every pan — it only ever costs one blit + one rect.
  $: {
    void vp
    schedule()
  }

  function schedule(): void {
    if (typeof window === 'undefined' || frame !== null) return
    frame = requestAnimationFrame(() => {
      frame = null
      paint()
    })
  }

  function buildLayer(): void {
    if (typeof document === 'undefined') return
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    if (layer === null) layer = document.createElement('canvas')
    layer.width = Math.round(W * dpr)
    layer.height = Math.round(H * dpr)
    const ctx = layer.getContext('2d')
    if (!ctx || !graphData) return

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, W, H)

    // Edges first, as one path: at this size they are a texture, not individual lines.
    ctx.strokeStyle = 'rgba(48, 54, 61, 0.5)'
    ctx.lineWidth = 0.6
    ctx.beginPath()
    for (const edge of graphData.edges) {
      const src = positions.get(edge.source)
      const tgt = positions.get(edge.target)
      if (!src || !tgt) continue
      ctx.moveTo((src.x - bbox.minX) * scaleX, (src.y - bbox.minY) * scaleY)
      ctx.lineTo((tgt.x - bbox.minX) * scaleX, (tgt.y - bbox.minY) * scaleY)
    }
    ctx.stroke()

    // Nodes grouped by colour, so a few thousand dots cost a few fills.
    const byColor = new Map<string, number[]>()
    for (const node of graphData.nodes) {
      const p = positions.get(node.id)
      if (!p) continue
      const fill = node.kind === 'real'
        ? categoryColor((node as RealNode).category, overrides)
        : '#30363d'
      const key = visIds.has(node.id) ? fill : `${fill}|dim`
      let bucket = byColor.get(key)
      if (bucket === undefined) {
        bucket = []
        byColor.set(key, bucket)
      }
      bucket.push((p.x - bbox.minX) * scaleX, (p.y - bbox.minY) * scaleY)
    }
    for (const [key, bucket] of byColor) {
      const [color, dim] = key.split('|')
      ctx.globalAlpha = dim ? 0.4 : 1
      ctx.fillStyle = color
      ctx.beginPath()
      for (let i = 0; i < bucket.length; i += 2) {
        ctx.moveTo(bucket[i] + 2.4, bucket[i + 1])
        ctx.arc(bucket[i], bucket[i + 1], 2.4, 0, Math.PI * 2)
      }
      ctx.fill()
    }
    ctx.globalAlpha = 1
    layerDirty = false
  }

  function paint(): void {
    if (!canvas) return
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    if (canvas.width !== Math.round(W * dpr)) {
      canvas.width = Math.round(W * dpr)
      canvas.height = Math.round(H * dpr)
      layerDirty = true
    }
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    if (layerDirty) buildLayer()

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, W, H)
    ctx.fillStyle = '#161b22'
    ctx.fillRect(0, 0, W, H)
    if (layer) {
      ctx.drawImage(layer, 0, 0, W, H)
    }

    // Viewport rectangle: world → minimap.
    const x = ((0 - vp.tx) / vp.scale - bbox.minX) * scaleX
    const y = ((0 - vp.ty) / vp.scale - bbox.minY) * scaleY
    const w = (vp.vw / vp.scale) * scaleX
    const h = (vp.vh / vp.scale) * scaleY
    ctx.strokeStyle = '#58a6ff'
    ctx.globalAlpha = 0.8
    ctx.lineWidth = 1.2
    ctx.strokeRect(x, y, w, h)
    ctx.globalAlpha = 1

    ctx.strokeStyle = '#30363d'
    ctx.lineWidth = 1
    ctx.strokeRect(0.5, 0.5, W - 1, H - 1)
  }

  onDestroy(() => {
    if (frame !== null && typeof window !== 'undefined') cancelAnimationFrame(frame)
  })
</script>

<div class="minimap" aria-label="Graph minimap">
  <canvas
    bind:this={canvas}
    style="width:{W}px;height:{H}px;display:block"
    aria-label="Minimap overview"
  ></canvas>
</div>

<style>
  .minimap {
    position: absolute;
    bottom: 12px;
    right: 12px;
    border-radius: 6px;
    overflow: hidden;
    box-shadow: 0 4px 12px var(--shadow);
    pointer-events: none;
    z-index: 20;
  }
</style>
