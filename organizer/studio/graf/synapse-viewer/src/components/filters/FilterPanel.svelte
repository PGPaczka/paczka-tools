<script lang="ts">
  import { graph, filters } from '../../stores/graphStore'
  import { visibleNodeIds } from '../../stores/graphStore'
  import { categoryColor } from '../../domain/color/categoryColor'
  import { settings } from '../../stores/settingsStore'
  import type { GraphFilters } from '../../domain/graph/selectors'
  import type { RealNode } from '../../domain/graph/GraphModel'
  import {
    EDGE_STYLES,
    edgeStyle,
    presentEdgeKinds,
    presentNodeTypes,
  } from '../../domain/graph/edgeStyle'

  // Derived data from graph
  $: realNodes = ($graph?.nodes ?? []).filter((n): n is RealNode => n.kind === 'real')
  $: totalCount = $graph?.nodes.length ?? 0
  $: visibleCount = $visibleNodeIds.size

  // Status options
  const statuses = [
    { value: 'not-started', label: 'Not started', cssVar: '--gray' },
    { value: 'in-progress', label: 'In progress', cssVar: '--amber' },
    { value: 'completed', label: 'Completed', cssVar: '--green' },
  ]

  $: statusCounts = statuses.reduce(
    (acc, s) => {
      acc[s.value] = realNodes.filter((n) => n.status === s.value).length
      return acc
    },
    {} as Record<string, number>,
  )

  // Categories
  $: categories = [...new Set(realNodes.map((n) => n.category))].sort()
  $: categoryCounts = categories.reduce(
    (acc, c) => {
      acc[c] = realNodes.filter((n) => n.category === c).length
      return acc
    },
    {} as Record<string, number>,
  )

  // Node types (e.g. semester / subject / file) — only those present in this vault.
  $: nodeTypes = presentNodeTypes(realNodes.map((n) => n.type))
  $: nodeTypeCounts = nodeTypes.reduce(
    (acc, t) => {
      acc[t] = realNodes.filter((n) => n.type === t).length
      return acc
    },
    {} as Record<string, number>,
  )

  // Relation kinds — filters EDGES, not nodes.
  $: relationKinds = presentEdgeKinds($graph?.edges ?? [])
  $: relationCounts = relationKinds.reduce(
    (acc, k) => {
      acc[k] = ($graph?.edges ?? []).filter((e) => (e.kind ?? 'link') === k).length
      return acc
    },
    {} as Record<string, number>,
  )

  // Levels — derived from the data, not a fixed [1,2,3]: a vault decides what its
  // levels mean and how many there are.
  $: levels = [...new Set(realNodes.map((n) => n.level))]
    .filter((l): l is number => typeof l === 'number')
    .sort((a, b) => a - b)
  $: levelCounts = levels.reduce(
    (acc, l) => {
      acc[l] = realNodes.filter((n) => n.level === l).length
      return acc
    },
    {} as Record<number, number>,
  )

  // Tags
  $: allTags = [...new Set(realNodes.flatMap((n) => n.tags))].sort()

  // Active state helpers
  $: hasFilters =
    $filters.categories.length > 0 ||
    $filters.statuses.length > 0 ||
    $filters.levels.length > 0 ||
    $filters.tags.length > 0 ||
    $filters.nodeTypes.length > 0 ||
    $filters.relationKinds.length > 0 ||
    Boolean($filters.connectedOnly)

  function toggleStatus(val: string) {
    filters.update((f: GraphFilters) => {
      const active = f.statuses.includes(val)
      return {
        ...f,
        statuses: active ? f.statuses.filter((s) => s !== val) : [...f.statuses, val],
      }
    })
  }

  function toggleCategory(cat: string) {
    filters.update((f: GraphFilters) => {
      const active = f.categories.includes(cat)
      return {
        ...f,
        categories: active ? f.categories.filter((c) => c !== cat) : [...f.categories, cat],
      }
    })
  }

  function toggleLevel(level: number) {
    filters.update((f: GraphFilters) => {
      const active = f.levels.includes(level)
      return {
        ...f,
        levels: active ? f.levels.filter((l) => l !== level) : [...f.levels, level],
      }
    })
  }

  function toggleTag(tag: string) {
    filters.update((f: GraphFilters) => {
      const active = f.tags.includes(tag)
      return {
        ...f,
        tags: active ? f.tags.filter((t) => t !== tag) : [...f.tags, tag],
      }
    })
  }

  function toggleNodeType(type: string) {
    filters.update((f: GraphFilters) => {
      const active = f.nodeTypes.includes(type)
      return {
        ...f,
        nodeTypes: active ? f.nodeTypes.filter((t) => t !== type) : [...f.nodeTypes, type],
      }
    })
  }

  function toggleRelationKind(kind: string) {
    filters.update((f: GraphFilters) => {
      const active = f.relationKinds.includes(kind)
      return {
        ...f,
        relationKinds: active
          ? f.relationKinds.filter((k) => k !== kind)
          : [...f.relationKinds, kind],
      }
    })
  }

  function toggleConnectedOnly() {
    filters.update((f: GraphFilters) => ({ ...f, connectedOnly: !f.connectedOnly }))
  }

  function setTagMode(mode: 'any' | 'all') {
    filters.update((f: GraphFilters) => ({ ...f, tagMode: mode }))
  }

  function clearFilters() {
    filters.set({
      categories: [],
      statuses: [],
      levels: [],
      tags: [],
      nodeTypes: [],
      relationKinds: [],
      tagMode: $filters.tagMode ?? 'all',
      connectedOnly: false,
    })
  }
</script>

<aside class="filter-panel">
  <div class="panel-header">
    <span class="panel-title">Filters</span>
    <span class="visible-count">{visibleCount} / {totalCount}</span>
  </div>

  <button
    class="clear-btn"
    class:clear-btn--hidden={!hasFilters}
    on:click={clearFilters}
    tabindex={hasFilters ? 0 : -1}
    aria-hidden={!hasFilters}
  >Clear filters</button>

  <!-- Node type — only shown when the vault types its notes -->
  {#if nodeTypes.length > 0}
    <section class="filter-section">
      <div class="section-label">Node type</div>
      <div class="chip-row">
        {#each nodeTypes as t}
          <button
            class="chip"
            class:active={$filters.nodeTypes.includes(t)}
            on:click={() => toggleNodeType(t)}
          >
            {t}
            <span class="count">{nodeTypeCounts[t] ?? 0}</span>
          </button>
        {/each}
      </div>
    </section>
  {/if}

  <!-- Relation kind — hides connections, never notes -->
  {#if relationKinds.length > 1}
    <section class="filter-section">
      <div class="section-label">Relation</div>
      <div class="chip-row">
        {#each relationKinds as k}
          <button
            class="chip"
            class:active={$filters.relationKinds.includes(k)}
            on:click={() => toggleRelationKind(k)}
          >
            <span class="dash" style="border-top-color:{edgeStyle(k).color};
              border-top-style:{edgeStyle(k).dash.length ? 'dashed' : 'solid'}"></span>
            {EDGE_STYLES[k]?.label ?? k}
            <span class="count">{relationCounts[k] ?? 0}</span>
          </button>
        {/each}
      </div>
      <button
        class="chip wide"
        class:active={$filters.connectedOnly}
        title="Hide notes left without a single visible connection"
        on:click={toggleConnectedOnly}
      >
        only connected
      </button>
    </section>
  {/if}

  <!-- Status -->
  <section class="filter-section">
    <div class="section-label">Status</div>
    <div class="chip-row">
      {#each statuses as s}
        <button
          class="chip status-chip"
          class:active={$filters.statuses.includes(s.value)}
          on:click={() => toggleStatus(s.value)}
        >
          <span class="dot" style="background:var({s.cssVar})"></span>
          {s.label}
          <span class="count">{statusCounts[s.value] ?? 0}</span>
        </button>
      {/each}
    </div>
  </section>

  <!-- Category -->
  {#if categories.length > 0}
    <section class="filter-section">
      <div class="section-label">Category</div>
      <div class="chip-row wrap">
        {#each categories as cat}
          <button
            class="chip cat-chip"
            class:active={$filters.categories.includes(cat)}
            on:click={() => toggleCategory(cat)}
          >
            <span class="dot" style="background:{categoryColor(cat, $settings.catColorOverrides)}"></span>
            {cat}
            <span class="count">{categoryCounts[cat] ?? 0}</span>
          </button>
        {/each}
      </div>
    </section>
  {/if}

  <!-- Level -->
  <section class="filter-section">
    <div class="section-label">Level</div>
    <div class="chip-row">
      {#each levels as l}
        <button
          class="chip level-chip"
          class:active={$filters.levels.includes(l)}
          on:click={() => toggleLevel(l)}
        >
          L{l}
          <span class="count">{levelCounts[l] ?? 0}</span>
        </button>
      {/each}
    </div>
  </section>

  <!-- Tags -->
  {#if allTags.length > 0}
    <section class="filter-section">
      <div class="section-label">
        Tags
        <span class="tag-mode">
          <button
            class="mode"
            class:active={($filters.tagMode ?? 'all') === 'all'}
            title="Show notes carrying ALL selected tags"
            on:click={() => setTagMode('all')}>all</button
          ><button
            class="mode"
            class:active={($filters.tagMode ?? 'all') === 'any'}
            title="Show notes carrying ANY selected tag"
            on:click={() => setTagMode('any')}>any</button
          >
        </span>
      </div>
      <div class="chip-row wrap">
        {#each allTags as tag}
          <button
            class="chip tag-chip"
            class:active={$filters.tags.includes(tag)}
            on:click={() => toggleTag(tag)}
          >
            #{tag}
          </button>
        {/each}
      </div>
    </section>
  {/if}
</aside>

<style>
  .dash {
    display: inline-block;
    width: 14px;
    border-top-width: 2px;
    margin-right: 2px;
  }

  .filter-panel {
    width: 220px;
    min-width: 180px;
    background: var(--panel);
    border-right: 1px solid var(--border);
    padding: 12px 0;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 0;
    flex-shrink: 0;
  }

  .panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 12px 8px;
    border-bottom: 1px solid var(--border-2);
    margin-bottom: 8px;
  }

  .panel-title {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
  }

  .visible-count {
    font-size: 11px;
    color: var(--muted-2);
    font-variant-numeric: tabular-nums;
  }

  .clear-btn {
    margin: 0 12px 8px;
    padding: 4px 10px;
    font-size: 11px;
    border-radius: 4px;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--accent);
    cursor: pointer;
    width: calc(100% - 24px);
    text-align: center;
    transition: background 0.15s;
  }
  .clear-btn:hover {
    background: var(--panel-2);
  }
  .clear-btn--hidden {
    visibility: hidden;
    pointer-events: none;
  }

  .filter-section {
    padding: 8px 12px;
    border-bottom: 1px solid var(--border-2);
  }

  .tag-mode {
    float: right;
    display: inline-flex;
    border: 1px solid var(--border);
    border-radius: 5px;
    overflow: hidden;
  }
  .tag-mode .mode {
    background: none;
    border: none;
    color: var(--muted-2);
    font-size: 9.5px;
    letter-spacing: 0.04em;
    padding: 1px 5px;
    cursor: pointer;
  }
  .tag-mode .mode.active {
    background: color-mix(in srgb, var(--accent) 22%, transparent);
    color: var(--text);
  }
  .chip.wide {
    margin-top: 6px;
    width: 100%;
    justify-content: center;
  }
  .section-label {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--muted-2);
    margin-bottom: 6px;
  }

  .chip-row {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .chip-row.wrap {
    flex-direction: row;
    flex-wrap: wrap;
  }

  .chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 8px;
    border-radius: 4px;
    border: 1px solid var(--border);
    background: var(--panel-2);
    color: var(--muted);
    font-size: 12px;
    cursor: pointer;
    transition: all 0.12s;
    text-align: left;
    white-space: nowrap;
  }

  .chip:hover {
    background: var(--panel-3);
    color: var(--text);
  }

  .chip.active {
    border-color: var(--accent);
    background: rgba(88, 166, 255, 0.1);
    color: var(--text);
  }

  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .count {
    margin-left: auto;
    font-size: 10px;
    color: var(--muted-2);
    min-width: 16px;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  :global(.tag-chip .count) {
    display: none;
  }
</style>
