<script lang="ts">
  /**
   * Donut SVG chart — 112×112 px, R=44, stroke-width=15.
   * Ports donutSvg() from the prototype exactly.
   */
  export let categories: Array<{ name: string; count: number; color: string }>

  const W = 112
  const R = 44
  const SW = 15
  const C = 2 * Math.PI * R // circumference ≈ 276.46

  $: total = categories.reduce((s, c) => s + c.count, 0)

  interface Segment {
    name: string
    color: string
    count: number
    len: number
    offset: number
  }

  $: segments = (() => {
    let acc = 0
    return categories.map((cat): Segment => {
      const frac = total > 0 ? cat.count / total : 0
      const len = frac * C
      const seg: Segment = { name: cat.name, color: cat.color, count: cat.count, len, offset: acc }
      acc += len
      return seg
    })
  })()

  export let hoveredSeg: string | null = null
</script>

<svg
  width={W}
  height={W}
  viewBox="0 0 {W} {W}"
  aria-label="Category breakdown donut chart"
  role="img"
>
  <!-- Background ring -->
  <circle
    cx="56"
    cy="56"
    r={R}
    fill="none"
    stroke="var(--panel-3)"
    stroke-width={SW}
  />

  <!-- Category segments -->
  {#each segments as seg, i (seg.name)}
    {#if seg.len > 0}
      <circle
        class="segment"
        class:dimmed={hoveredSeg !== null && hoveredSeg !== seg.name}
        cx="56"
        cy="56"
        r={R}
        fill="none"
        stroke={seg.color}
        stroke-dasharray="{seg.len} {C - seg.len}"
        stroke-dashoffset={-seg.offset}
        transform="rotate(-90 56 56)"
        style="--sw: {hoveredSeg === seg.name ? SW + 5 : SW}; animation-delay: {i * 65}ms"
        aria-label="{seg.name}: {seg.count} notes"
        on:mouseenter={() => { hoveredSeg = seg.name }}
        on:mouseleave={() => { hoveredSeg = null }}
      >
        <title>{seg.name}: {seg.count} notes</title>
      </circle>
    {/if}
  {/each}

  <!-- Center: total count -->
  <text
    x="56"
    y="52"
    text-anchor="middle"
    dominant-baseline="middle"
    font-family="var(--font-mono)"
    font-size="20"
    font-weight="600"
    fill="var(--text)"
  >{total}</text>

  <!-- Center: "notes" label -->
  <text
    x="56"
    y="67"
    text-anchor="middle"
    dominant-baseline="middle"
    font-size="9"
    fill="var(--muted-2)"
    letter-spacing="0.06em"
  >notes</text>
</svg>

<style>
  svg {
    display: block;
    flex-shrink: 0;
  }

  @keyframes donut-in {
    from { opacity: 0; }
  }

  .segment {
    stroke-width: var(--sw, 15);
    animation: donut-in 0.4s ease-out both;
    transition: stroke-width 0.15s ease, filter 0.15s ease;
    cursor: pointer;
  }

  .segment.dimmed {
    filter: brightness(0.3);
  }
</style>
