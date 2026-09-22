<script lang="ts">
  import { graph } from '../../stores/graphStore'
  import { settings } from '../../stores/settingsStore'
  import { selectedId } from '../../stores/selectionStore'
  import { categoryColor } from '../../domain/color/categoryColor'
  import { orphanIds } from '../../domain/graph/selectors'
  import { buildHeatmapCells } from '../../domain/dashboard/heatmap'
  import type { RealNode } from '../../domain/graph/GraphModel'
  import StatCard from './StatCard.svelte'
  import Donut from './Donut.svelte'
  import Heatmap from './Heatmap.svelte'

  // ── Derived data from graph store ─────────────────────────────────────────

  $: realNodes = ($graph?.nodes.filter((n) => n.kind === 'real') ?? []) as RealNode[]
  $: ghostNodes = $graph?.nodes.filter((n) => n.kind === 'ghost') ?? []
  $: totalNotes = realNodes.length
  $: completed = realNodes.filter((n) => n.status === 'completed').length
  $: inProgress = realNodes.filter((n) => n.status === 'in-progress').length
  $: notStarted = realNodes.filter((n) => n.status === 'not-started').length
  $: orphans = $graph ? orphanIds($graph).size : 0

  // ── Category breakdown for donut ──────────────────────────────────────────

  $: catCounts = (() => {
    const m: Record<string, number> = {}
    for (const n of realNodes) {
      m[n.category] = (m[n.category] ?? 0) + 1
    }
    return m
  })()

  $: overrides = $settings.catColorOverrides

  $: categories = Object.entries(catCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([name, count]) => ({
      name,
      count,
      color: categoryColor(name, overrides),
    }))

  // ── Status progress ────────────────────────────────────────────────────────

  $: statusRows = [
    { label: 'Completed', count: completed, color: 'var(--green)' },
    { label: 'In progress', count: inProgress, color: 'var(--amber)' },
    { label: 'Not started', count: notStarted, color: 'var(--muted-2)' },
  ]

  // ── Heatmap ───────────────────────────────────────────────────────────────

  $: allHistoryDates = realNodes.flatMap((n) => n.history ?? [])
  $: heatmapCells = buildHeatmapCells(allHistoryDates, new Date())
  $: heatmapMax = Math.max(1, ...heatmapCells.map((c) => c.count))

  $: heatmapStats = (() => {
    const totalEdits = allHistoryDates.length
    const activeDays = heatmapCells.filter((c) => c.count > 0).length

    const activeSorted = heatmapCells
      .filter((c) => c.count > 0)
      .map((c) => c.date)
      .sort()

    let longestStreak = activeSorted.length > 0 ? 1 : 0
    let curStreak = longestStreak
    for (let i = 1; i < activeSorted.length; i++) {
      const prev = new Date(activeSorted[i - 1] + 'T00:00:00Z')
      const curr = new Date(activeSorted[i] + 'T00:00:00Z')
      const diff = (curr.getTime() - prev.getTime()) / 86400000
      if (diff === 1) {
        curStreak++
        if (curStreak > longestStreak) longestStreak = curStreak
      } else {
        curStreak = 1
      }
    }

    return { totalEdits, maxPerDay: heatmapMax, activeDays, longestStreak }
  })()

  // ── "What's next" — up to 3 actionable notes ─────────────────────────────
  // Strategy: pick in-progress first, then not-started, sorted by level asc

  // Donut hover sync — tracks which segment the user is hovering in the chart
  let hoveredSeg: string | null = null

  $: whatsNext = (() => {
    const actionable = realNodes
      .filter((n) => n.status === 'in-progress' || n.status === 'not-started')
      .sort((a, b) => {
        // in-progress before not-started
        if (a.status !== b.status) {
          return a.status === 'in-progress' ? -1 : 1
        }
        return (a.level ?? 0) - (b.level ?? 0)
      })
    return actionable.slice(0, 3)
  })()
</script>

<div class="dashboard">
  <!-- Stat cards row -->
  <section class="stat-row">
    <StatCard label="Total notes" value={totalNotes} color="var(--text)" />
    <StatCard
      label="Completed"
      value={completed}
      sub="{totalNotes > 0 ? Math.round((completed / totalNotes) * 100) : 0}%"
      color="var(--green)"
    />
    <StatCard label="In progress" value={inProgress} color="var(--amber)" />
    <StatCard label="Orphans" value={orphans} color="var(--muted-2)" sub="no links" />
    <StatCard label="Ghost nodes" value={ghostNodes.length} color="var(--muted-2)" sub="unresolved" />
  </section>

  <!-- Main grid: donut + progress + heatmap + what's next -->
  <div class="dash-grid">

    <!-- Donut + legend -->
    <section class="card donut-card">
      <h3 class="card-title">By category</h3>
      <div class="donut-row">
        <Donut {categories} bind:hoveredSeg />
        <ul class="legend" class:legend--two-col={categories.length > 5}>
          {#each categories as cat (cat.name)}
            <li
              class="legend-item"
              class:legend-item--hovered={hoveredSeg === cat.name}
              class:legend-item--dimmed={hoveredSeg !== null && hoveredSeg !== cat.name}
            >
              <span class="legend-dot" style="background:{cat.color}"></span>
              <span class="legend-name">{cat.name}</span>
              <span class="legend-count">{cat.count}</span>
            </li>
          {/each}
          {#if categories.length === 0}
            <li class="legend-empty">No notes yet</li>
          {/if}
        </ul>
      </div>
    </section>

    <!-- Status progress -->
    <section class="card status-card">
      <h3 class="card-title">Status</h3>
      <div class="status-list">
        {#each statusRows as row (row.label)}
          <div class="status-row">
            <span class="status-label">{row.label}</span>
            <div class="progress-track">
              <div
                class="progress-fill"
                style="width:{totalNotes > 0 ? (row.count / totalNotes) * 100 : 0}%; background:{row.color}"
              ></div>
            </div>
            <span class="status-count" style="color:{row.color}">{row.count}</span>
          </div>
        {/each}
      </div>
    </section>

    <!-- Heatmap -->
    <section class="card heatmap-card">
      <h3 class="card-title">Activity — last 26 weeks</h3>
      <div class="heatmap-body">
        <div class="heatmap-wrap">
          <Heatmap cells={heatmapCells} max={heatmapMax} />
        </div>
        <div class="heatmap-stats">
          <div class="hs-stat">
            <span class="hs-val">{heatmapStats.totalEdits}</span>
            <span class="hs-label">total edits</span>
          </div>
          <div class="hs-stat">
            <span class="hs-val">{heatmapStats.maxPerDay}</span>
            <span class="hs-label">max / day</span>
          </div>
          <div class="hs-stat">
            <span class="hs-val">{heatmapStats.longestStreak}</span>
            <span class="hs-label">best streak</span>
          </div>
          <div class="hs-stat">
            <span class="hs-val">{heatmapStats.activeDays}</span>
            <span class="hs-label">active days</span>
          </div>
        </div>
      </div>
    </section>

    <!-- What's next -->
    <section class="card next-card">
      <h3 class="card-title">What's next</h3>
      {#if whatsNext.length === 0}
        <p class="next-empty">All notes completed 🎉</p>
      {:else}
        <ul class="next-list">
          {#each whatsNext as note (note.id)}
            <li>
              <button class="next-item" on:click={() => selectedId.set(note.id)}>
                <span
                  class="next-status-dot"
                  style="background:{note.status === 'in-progress' ? 'var(--amber)' : 'var(--border)'}"
                ></span>
                <div class="next-info">
                  <span class="next-title">{note.title}</span>
                  <span class="next-meta">
                    <span class="next-status-label" style="color:{note.status === 'in-progress' ? 'var(--amber)' : 'var(--muted-2)'}">
                      {note.status === 'in-progress' ? 'In progress' : 'Not started'}
                    </span>
                    · {note.category}{note.level != null ? ' · L' + note.level : ''}
                  </span>
                </div>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </section>
  </div>
</div>

<style>
  .dashboard {
    width: 100%;
    height: 100%;
    overflow-y: auto;
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    box-sizing: border-box;
  }

  /* ── Stat row ──────────────────────────────────────────── */
  .stat-row {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
  }

  /* ── Dashboard grid ────────────────────────────────────── */
  .dash-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    grid-template-rows: auto auto;
    gap: 12px;
  }

  .heatmap-card {
    min-width: 0;
  }

  /* ── Card base ─────────────────────────────────────────── */
  .card {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .card-title {
    margin: 0;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted-2);
  }

  /* ── Donut card ────────────────────────────────────────── */
  .donut-row {
    display: flex;
    gap: 16px;
    align-items: center;
  }

  .legend {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
    flex: 1;
    overflow: hidden;
  }

  .legend--two-col {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 4px 10px;
    align-content: start;
  }

  .legend-item {
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: 12px;
    transition: opacity 0.15s ease;
  }

  .legend-item--dimmed {
    opacity: 0.3;
  }

  .legend-item--hovered .legend-name {
    color: var(--accent);
    font-weight: 600;
  }

  .legend-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .legend-name {
    flex: 1;
    color: var(--text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .legend-count {
    color: var(--muted);
    font-variant-numeric: tabular-nums;
    font-size: 11px;
  }

  .legend-empty {
    color: var(--muted-2);
    font-size: 12px;
  }

  /* ── Status card ───────────────────────────────────────── */
  .status-list {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .status-row {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .status-label {
    font-size: 12px;
    color: var(--muted);
    width: 88px;
    flex-shrink: 0;
  }

  .progress-track {
    flex: 1;
    height: 6px;
    background: var(--panel-3);
    border-radius: 3px;
    overflow: hidden;
  }

  .progress-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 0.3s ease;
  }

  .status-count {
    font-size: 12px;
    font-variant-numeric: tabular-nums;
    width: 28px;
    text-align: right;
    flex-shrink: 0;
  }

  /* ── Heatmap card ──────────────────────────────────────── */
  .heatmap-body {
    display: flex;
    align-items: flex-start;
    gap: 20px;
  }

  .heatmap-wrap {
    overflow-x: auto;
    padding-bottom: 4px;
    flex-shrink: 0;
  }

  .heatmap-stats {
    flex: 1;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px 8px;
    align-content: start;
    padding-top: 10px;
  }

  .hs-stat {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }

  .hs-val {
    font-size: 22px;
    font-weight: 600;
    color: var(--text);
    font-variant-numeric: tabular-nums;
    line-height: 1;
  }

  .hs-label {
    font-size: 10px;
    color: var(--muted-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  /* ── What's next card ──────────────────────────────────── */
  .next-empty {
    font-size: 12px;
    color: var(--muted-2);
    margin: 0;
  }

  .next-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .next-item {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    width: 100%;
    background: none;
    border: none;
    padding: 4px 6px;
    margin: -4px -6px;
    border-radius: 5px;
    cursor: pointer;
    text-align: left;
    transition: background 0.1s;
  }
  .next-item:hover {
    background: var(--panel-2);
  }
  .next-item:hover .next-title {
    color: var(--accent);
  }

  .next-status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
    margin-top: 3px;
  }

  .next-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .next-title {
    font-size: 12px;
    color: var(--text);
  }

  .next-meta {
    font-size: 11px;
    color: var(--muted-2);
    display: flex;
    flex-wrap: wrap;
    gap: 2px;
    align-items: center;
  }

  .next-status-label {
    font-weight: 600;
    font-size: 10px;
  }
</style>
