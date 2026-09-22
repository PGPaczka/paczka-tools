<script lang="ts">
  import { graph, visibleNodeIds } from '../../stores/graphStore'
  import { selectedId } from '../../stores/selectionStore'
  import { settings } from '../../stores/settingsStore'
  import { categoryColor } from '../../domain/color/categoryColor'
  import { computeVennLayout, placeVennNodes } from '../../domain/sets/venn'
  import type { RealNode } from '../../domain/graph/GraphModel'

  // ── Dimension picker ───────────────────────────────────────────────────────

  let dim: 'tag' | 'category' = 'tag'

  // ── Available set options (tags or categories from real nodes) ─────────────

  $: realNodes = ($graph?.nodes.filter((n) => n.kind === 'real') ?? []) as RealNode[]

  $: availableOptions = (() => {
    if (dim === 'tag') {
      const tags = new Set<string>()
      for (const n of realNodes) n.tags.forEach((t) => tags.add(t))
      return [...tags].sort()
    } else {
      const cats = new Set<string>()
      for (const n of realNodes) cats.add(n.category)
      return [...cats].sort()
    }
  })()

  // ── Selected sets (1–4) ────────────────────────────────────────────────────

  let selectedSets: string[] = []

  // Reset selection when dimension changes or available options change
  $: {
    void dim
    selectedSets = []
  }

  function toggleSet(s: string) {
    if (selectedSets.includes(s)) {
      selectedSets = selectedSets.filter((x) => x !== s)
    } else if (selectedSets.length < 4) {
      selectedSets = [...selectedSets, s]
    }
  }

  // ── Container dimensions (for SVG sizing) ─────────────────────────────────

  let containerEl: HTMLDivElement
  let containerW = 800
  let containerH = 500

  // ── Venn layout ────────────────────────────────────────────────────────────

  $: layout = computeVennLayout(selectedSets, containerW, containerH)

  // Color helpers
  $: overrides = $settings.catColorOverrides

  function catColorFn(cat: string): string {
    return categoryColor(cat, overrides)
  }

  function statusColorFn(s: string | null): string {
    if (s === 'completed') return '#3fb950'
    if (s === 'in-progress') return '#d29922'
    return 'transparent'
  }

  $: vennNodes =
    selectedSets.length >= 1
      ? placeVennNodes(
          realNodes,
          selectedSets,
          dim,
          layout,
          catColorFn,
          statusColorFn,
          containerW,
          containerH,
        )
      : []

  function handleNodeClick(id: string) {
    selectedId.set(id)
  }
</script>

<div class="venn-view">
  <!-- Controls bar -->
  <div class="controls">
    <!-- Dimension segment control -->
    <div class="segment-control" role="group" aria-label="Venn dimension">
      <button
        class="seg-btn"
        class:active={dim === 'tag'}
        on:click={() => (dim = 'tag')}
      >By tag</button>
      <button
        class="seg-btn"
        class:active={dim === 'category'}
        on:click={() => (dim = 'category')}
      >By category</button>
    </div>

    <!-- Set chips -->
    <div class="chip-row" role="group" aria-label="Select sets">
      {#each availableOptions as opt (opt)}
        <button
          class="chip"
          class:selected={selectedSets.includes(opt)}
          class:disabled={!selectedSets.includes(opt) && selectedSets.length >= 4}
          on:click={() => toggleSet(opt)}
          disabled={!selectedSets.includes(opt) && selectedSets.length >= 4}
          aria-pressed={selectedSets.includes(opt)}
        >{opt}</button>
      {/each}
    </div>
  </div>

  <!-- Venn SVG area -->
  <div
    class="venn-area"
    bind:this={containerEl}
    bind:clientWidth={containerW}
    bind:clientHeight={containerH}
  >
    {#if selectedSets.length < 2}
      <div class="hint">Select 2–4 sets to compare</div>
    {:else}
      <svg
        width={containerW}
        height={containerH}
        viewBox="0 0 {containerW} {containerH}"
        aria-label="Venn diagram comparing {selectedSets.join(', ')}"
        role="img"
      >
        <!-- Circles -->
        {#each layout.circles as circle, i (circle.label)}
          <circle
            cx={circle.cx}
            cy={circle.cy}
            r={circle.r}
            fill={circle.color}
            fill-opacity="0.10"
            stroke={circle.color}
            stroke-opacity="0.6"
            stroke-width="1.5"
          />
          <!-- Set label -->
          <text
            x={circle.labelX}
            y={circle.labelY}
            text-anchor="middle"
            dominant-baseline="middle"
            font-size="13"
            font-weight="500"
            fill={circle.color}
            font-family="var(--font-ui)"
          >{circle.label}</text>
        {/each}

        <!-- Nodes -->
        {#each vennNodes as vn (vn.id)}
          {@const isVisible = $visibleNodeIds.has(vn.id)}
          {@const isSelected = $selectedId === vn.id}
          <g
            class="venn-node"
            role="button"
            tabindex="0"
            aria-label={vn.title}
            on:click={() => handleNodeClick(vn.id)}
            on:keydown={(e) => e.key === 'Enter' && handleNodeClick(vn.id)}
            opacity={isVisible ? 1 : 0.35}
          >
            {#if isSelected}
              <circle
                cx={vn.x}
                cy={vn.y}
                r={vn.r + 4}
                fill="var(--accent)"
                fill-opacity="0.3"
              />
            {/if}
            <circle
              cx={vn.x}
              cy={vn.y}
              r={vn.r}
              fill={vn.fill}
              stroke={vn.stroke !== 'transparent' ? vn.stroke : 'var(--border)'}
              stroke-width={vn.fill === 'transparent' ? 1.5 : 1}
            />
            {#if isSelected}
              <circle
                cx={vn.x}
                cy={vn.y}
                r={vn.r + 2}
                fill="none"
                stroke="var(--accent)"
                stroke-width="1.5"
              />
            {/if}
            <title>{vn.title}</title>
          </g>
        {/each}
      </svg>
    {/if}
  </div>
</div>

<style>
  .venn-view {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  /* ── Controls ──────────────────────────────────────────── */
  .controls {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 14px;
    border-bottom: 1px solid var(--border);
    background: var(--panel);
    flex-shrink: 0;
    flex-wrap: wrap;
  }

  .segment-control {
    display: flex;
    gap: 1px;
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 2px;
    flex-shrink: 0;
  }

  .seg-btn {
    padding: 4px 12px;
    border-radius: 4px;
    border: none;
    background: transparent;
    color: var(--muted);
    font-size: 12px;
    font-family: var(--font-ui);
    cursor: pointer;
    transition: all 0.1s;
  }
  .seg-btn.active {
    background: var(--panel-3);
    color: var(--text);
  }

  .chip-row {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }

  .chip {
    padding: 3px 10px;
    border-radius: 12px;
    border: 1px solid var(--border);
    background: var(--panel-2);
    color: var(--muted);
    font-size: 11px;
    font-family: var(--font-ui);
    cursor: pointer;
    transition: all 0.1s;
  }
  .chip:hover:not(:disabled) {
    border-color: var(--accent-dim);
    color: var(--text);
  }
  .chip.selected {
    background: var(--accent-dim);
    border-color: var(--accent);
    color: var(--text);
  }
  .chip.disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  /* ── Venn area ─────────────────────────────────────────── */
  .venn-area {
    flex: 1;
    position: relative;
    overflow: hidden;
  }

  .hint {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 13px;
    color: var(--muted-2);
  }

  svg {
    display: block;
    width: 100%;
    height: 100%;
  }

  .venn-node {
    cursor: pointer;
  }
</style>
