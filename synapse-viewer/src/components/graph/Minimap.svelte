<script lang="ts">
  import { graph, visibleNodeIds } from '../../stores/graphStore'
  import { minimapPositions, minimapViewport } from '../../stores/minimapStore'
  import { categoryColor } from '../../domain/color/categoryColor'
  import { settings } from '../../stores/settingsStore'
  import type { RealNode } from '../../domain/graph/GraphModel'

  const W = 172
  const H = 118

  // Map world coordinates to minimap coordinates
  function worldToMinimap(
    wx: number,
    wy: number,
    minX: number,
    minY: number,
    scaleX: number,
    scaleY: number,
  ): { x: number; y: number } {
    return {
      x: (wx - minX) * scaleX,
      y: (wy - minY) * scaleY,
    }
  }

  $: positions = $minimapPositions
  $: vp = $minimapViewport
  $: graphData = $graph
  $: visIds = $visibleNodeIds
  $: overrides = $settings.catColorOverrides

  // Find bounding box of all node positions
  $: bbox = (() => {
    if (positions.size === 0) return { minX: 0, minY: 0, maxX: W, maxY: H }
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
    for (const { x, y } of positions.values()) {
      if (x < minX) minX = x
      if (y < minY) minY = y
      if (x > maxX) maxX = x
      if (y > maxY) maxY = y
    }
    // Add padding
    const pad = 20
    return { minX: minX - pad, minY: minY - pad, maxX: maxX + pad, maxY: maxY + pad }
  })()

  $: bboxW = bbox.maxX - bbox.minX || W
  $: bboxH = bbox.maxY - bbox.minY || H
  $: scaleX = W / bboxW
  $: scaleY = H / bboxH

  // Compute the viewport rect in minimap coords
  // The canvas transform is: screen = world * scale + (tx, ty)
  // So world = (screen - translation) / scale
  $: vpRect = (() => {
    // Map the four corners of the canvas viewport to world, then to minimap coords
    const worldTL = {
      x: (0 - vp.tx) / vp.scale,
      y: (0 - vp.ty) / vp.scale,
    }
    const worldBR = {
      x: (vp.vw - vp.tx) / vp.scale,
      y: (vp.vh - vp.ty) / vp.scale,
    }
    const mmTL = worldToMinimap(worldTL.x, worldTL.y, bbox.minX, bbox.minY, scaleX, scaleY)
    const mmBR = worldToMinimap(worldBR.x, worldBR.y, bbox.minX, bbox.minY, scaleX, scaleY)
    return {
      x: mmTL.x,
      y: mmTL.y,
      w: mmBR.x - mmTL.x,
      h: mmBR.y - mmTL.y,
    }
  })()

  // Build edge lines and node circles for rendering
  $: edges = (() => {
    if (!graphData) return []
    return graphData.edges.map((e) => {
      const src = positions.get(e.source)
      const tgt = positions.get(e.target)
      if (!src || !tgt) return null
      const s = worldToMinimap(src.x, src.y, bbox.minX, bbox.minY, scaleX, scaleY)
      const t = worldToMinimap(tgt.x, tgt.y, bbox.minX, bbox.minY, scaleX, scaleY)
      return { x1: s.x, y1: s.y, x2: t.x, y2: t.y }
    }).filter(Boolean) as Array<{ x1: number; y1: number; x2: number; y2: number }>
  })()

  $: nodes = (() => {
    if (!graphData) return []
    return graphData.nodes.map((n) => {
      const p = positions.get(n.id)
      if (!p) return null
      const mm = worldToMinimap(p.x, p.y, bbox.minX, bbox.minY, scaleX, scaleY)
      const isVisible = visIds.has(n.id)
      const fill =
        n.kind === 'real'
          ? categoryColor((n as RealNode).category, overrides)
          : 'var(--border)'
      return { id: n.id, x: mm.x, y: mm.y, fill, isVisible }
    }).filter(Boolean) as Array<{ id: string; x: number; y: number; fill: string; isVisible: boolean }>
  })()
</script>

<div class="minimap" aria-label="Graph minimap">
  <svg
    width={W}
    height={H}
    viewBox="0 0 {W} {H}"
    role="img"
    aria-label="Minimap overview"
  >
    <!-- Background -->
    <rect x="0" y="0" width={W} height={H} fill="var(--panel)" rx="4" />

    <!-- Edges -->
    {#each edges as e}
      <line
        x1={e.x1} y1={e.y1}
        x2={e.x2} y2={e.y2}
        stroke="var(--border)"
        stroke-width="0.6"
        opacity="0.5"
      />
    {/each}

    <!-- Nodes -->
    {#each nodes as n (n.id)}
      <circle
        cx={n.x}
        cy={n.y}
        r="2.4"
        fill={n.fill}
        opacity={n.isVisible ? 1 : 0.4}
      />
    {/each}

    <!-- Viewport rect -->
    <rect
      x={vpRect.x}
      y={vpRect.y}
      width={vpRect.w}
      height={vpRect.h}
      fill="none"
      stroke="var(--accent)"
      stroke-width="1.2"
      opacity="0.8"
      rx="2"
    />

    <!-- Border -->
    <rect
      x="0.5"
      y="0.5"
      width={W - 1}
      height={H - 1}
      fill="none"
      stroke="var(--border)"
      stroke-width="1"
      rx="4"
    />
  </svg>
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

  svg {
    display: block;
  }
</style>
