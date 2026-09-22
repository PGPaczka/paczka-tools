<script lang="ts">
  import type { HeatmapCell } from '../../domain/dashboard/heatmap'

  export let cells: HeatmapCell[]
  /** Maximum count in the dataset (used for display context, e.g. legends). */
  export let max: number = 1

  const CELL = 13
  const GAP = 2
  const STEP = CELL + GAP // 15

  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

  // Total SVG dimensions (26 weeks × 15px wide, 7 days × 15px tall + 14px for labels)
  const SVG_W = 26 * STEP  // 390
  const SVG_H = 7 * STEP + 14  // 119

  // Tooltip state
  let tooltipCell: HeatmapCell | null = null
  let tooltipX = 0
  let tooltipY = 0

  function fillFor(cell: HeatmapCell): string {
    if (cell.count === 0) return 'var(--bg)'
    const pct = 25 + Math.round(cell.level * 65)
    return `color-mix(in srgb, var(--green) ${pct}%, var(--bg))`
  }

  function monthLabel(cell: HeatmapCell): string | null {
    if (cell.row !== 0) return null
    const d = new Date(cell.date + 'T00:00:00Z')
    if (d.getUTCDate() <= 7) return MONTHS[d.getUTCMonth()]
    return null
  }

  function onEnter(e: MouseEvent, cell: HeatmapCell) {
    tooltipCell = cell
    tooltipX = e.clientX + 12
    tooltipY = e.clientY - 36
  }

  function onMove(e: MouseEvent) {
    if (tooltipCell) {
      tooltipX = e.clientX + 12
      tooltipY = e.clientY - 36
    }
  }

  function onLeave() {
    tooltipCell = null
  }
</script>

<svg
  width={SVG_W}
  height={SVG_H}
  viewBox="0 0 {SVG_W} {SVG_H}"
  aria-label="Activity heatmap — {max} max edits in a day"
  role="img"
  class="heatmap"
>
  <!-- Month labels (14px band above the grid) -->
  {#each cells as cell (cell.col + '-' + cell.row)}
    {#if monthLabel(cell) !== null}
      <text
        x={cell.col * STEP}
        y="10"
        font-size="9"
        fill="var(--muted-2)"
        font-family="var(--font-ui)"
      >{monthLabel(cell)}</text>
    {/if}
  {/each}

  <!-- Cells -->
  {#each cells as cell (cell.col + '-' + cell.row)}
    <rect
      x={cell.col * STEP}
      y={14 + cell.row * STEP}
      width={CELL}
      height={CELL}
      rx="2"
      fill={fillFor(cell)}
      stroke="var(--border)"
      stroke-width="0.6"
      on:mouseenter={(e) => onEnter(e, cell)}
      on:mousemove={onMove}
      on:mouseleave={onLeave}
    />
  {/each}
</svg>

{#if tooltipCell}
  <div
    class="heatmap-tooltip"
    style="left:{tooltipX}px; top:{tooltipY}px"
    role="tooltip"
  >
    <span class="tt-date">{tooltipCell.date}</span>
    <span class="tt-count">{tooltipCell.count} edit{tooltipCell.count !== 1 ? 's' : ''}</span>
  </div>
{/if}

<style>
  .heatmap {
    display: block;
    overflow: visible;
  }

  rect {
    transition: transform 0.12s ease, filter 0.12s ease;
    transform-box: fill-box;
    transform-origin: center;
  }
  rect:hover {
    transform: scale(1.45);
    filter: brightness(1.4);
    cursor: default;
  }

  .heatmap-tooltip {
    position: fixed;
    z-index: 999;
    pointer-events: none;
    background: var(--panel-3);
    border: 1px solid var(--border);
    border-radius: 5px;
    padding: 5px 9px;
    display: flex;
    flex-direction: column;
    gap: 1px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.25);
  }

  .tt-date {
    font-size: 11px;
    color: var(--muted-2);
    font-family: var(--font-mono);
  }

  .tt-count {
    font-size: 12px;
    font-weight: 600;
    color: var(--text);
  }
</style>
