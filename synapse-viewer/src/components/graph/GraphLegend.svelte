<script lang="ts">
  import { graph } from '../../stores/graphStore'
  import {
    EDGE_STYLES,
    edgeStyle,
    presentEdgeKinds,
    presentNodeTypes,
    nodeTypeScale,
  } from '../../domain/graph/edgeStyle'

  /**
   * Legend for the graph canvas. The viewer had none: every edge looked the same, so a
   * relation's kind was invisible even when the data carried it. Only kinds and types
   * actually present in this vault are listed — a legend for things that are not there
   * is noise.
   */
  export let collapsed = false

  $: edges = $graph?.edges ?? []
  $: nodes = $graph?.nodes ?? []
  $: kinds = presentEdgeKinds(edges)
  $: types = presentNodeTypes(
    nodes.map((n) => (n.kind === 'real' ? n.type : undefined)),
  )
  $: counts = kinds.reduce<Record<string, number>>((acc, kind) => {
    acc[kind] = edges.filter((e) => (e.kind ?? 'link') === kind).length
    return acc
  }, {})

  function dashArray(dash: number[]): string {
    return dash.length > 0 ? dash.join(' ') : 'none'
  }
</script>

{#if kinds.length > 1 || types.length > 0}
  <div class="legend" class:collapsed>
    <button class="toggle" on:click={() => (collapsed = !collapsed)} title="Toggle legend">
      {collapsed ? 'Legend' : 'Legend ▾'}
    </button>

    {#if !collapsed}
      {#if types.length > 0}
        <div class="group">
          <div class="heading">nodes</div>
          {#each types as type}
            <div class="row">
              <svg width="22" height="12" aria-hidden="true">
                <circle cx="11" cy="6" r={Math.min(5, 2.6 * nodeTypeScale(type))} fill="#8b949e" />
              </svg>
              <span>{type}</span>
            </div>
          {/each}
        </div>
      {/if}

      <div class="group">
        <div class="heading">relations</div>
        {#each kinds as kind}
          <div class="row">
            <svg width="22" height="12" aria-hidden="true">
              <line
                x1="1"
                y1="6"
                x2="21"
                y2="6"
                stroke={edgeStyle(kind).color}
                stroke-width={Math.max(1.5, edgeStyle(kind).width)}
                stroke-dasharray={dashArray(edgeStyle(kind).dash)}
              />
              {#if edgeStyle(kind).arrow}
                <polygon points="21,6 16,3.5 16,8.5" fill={edgeStyle(kind).color} />
              {/if}
            </svg>
            <span>{EDGE_STYLES[kind]?.label ?? kind}</span>
            <span class="count">{counts[kind]}</span>
          </div>
        {/each}
      </div>
    {/if}
  </div>
{/if}

<style>
  .legend {
    position: absolute;
    left: 12px;
    bottom: 12px;
    background: var(--panel, #161b22);
    border: 1px solid var(--border, #30363d);
    border-radius: 8px;
    padding: 8px 10px;
    font-size: 11.5px;
    color: var(--muted, #8b949e);
    pointer-events: auto;
    max-width: 220px;
  }
  .legend.collapsed {
    padding: 4px 8px;
  }
  .toggle {
    background: none;
    border: none;
    color: var(--muted-2, #6e7681);
    font-size: 10.5px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    cursor: pointer;
    padding: 0 0 4px;
  }
  .group + .group {
    margin-top: 6px;
  }
  .heading {
    font-size: 10px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--muted-2, #6e7681);
    margin-bottom: 2px;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 6px;
    line-height: 1.5;
  }
  .count {
    margin-left: auto;
    color: var(--muted-2, #6e7681);
    font-variant-numeric: tabular-nums;
  }
</style>
