<script lang="ts">
  import { onMount } from 'svelte'
  import { graph, visibleNodeIds } from '../../stores/graphStore'
  import { selectedId } from '../../stores/selectionStore'
  import { categoryColor } from '../../domain/color/categoryColor'
  import { settings } from '../../stores/settingsStore'
  import type { RealNode } from '../../domain/graph/GraphModel'

  type SortKey = 'default' | 'date' | 'category' | 'level' | 'status'

  let search = ''
  let sortKey: SortKey = 'default'

  $: realNodes = ($graph?.nodes.filter((n) => n.kind === 'real') ?? []) as RealNode[]

  $: filtered = realNodes.filter((n) => {
    if (!$visibleNodeIds.has(n.id)) return false
    if (!search) return true
    const q = search.toLowerCase()
    return (
      n.title.toLowerCase().includes(q) ||
      n.excerpt?.toLowerCase().includes(q) ||
      n.tags.some((t) => t.includes(q)) ||
      n.category.toLowerCase().includes(q)
    )
  })

  const STATUS_ORDER: Record<string, number> = {
    'not-started': 0,
    'in-progress': 1,
    completed: 2,
  }

  $: sorted = [...filtered].sort((a, b) => {
    switch (sortKey) {
      case 'date':     return b.modified.localeCompare(a.modified)
      case 'category': return a.category.localeCompare(b.category)
      case 'level':    return (a.level ?? 0) - (b.level ?? 0)
      case 'status':   return (STATUS_ORDER[a.status ?? ''] ?? 0) - (STATUS_ORDER[b.status ?? ''] ?? 0)
      default:         return 0
    }
  })

  // Reset scroll to top when search or sort changes
  $: if (search || sortKey) scrollEl?.scrollTop && (scrollEl.scrollTop = 0)

  function statusColor(s: string | null): string {
    if (s === 'completed') return 'var(--green)'
    if (s === 'in-progress') return 'var(--amber)'
    return 'var(--gray)'
  }

  function statusLabel(s: string | null): string {
    if (s === 'completed') return 'Done'
    if (s === 'in-progress') return 'In progress'
    if (s === 'not-started') return 'Not started'
    return ''
  }

  function excerptText(n: RealNode): string {
    return (n.excerpt ?? '')
      .replace(/```[\s\S]*?```/g, '')
      .replace(/[#>*`\[\]_~]/g, '')
      .replace(/\n+/g, ' ')
      .trim()
      .slice(0, 110) + '…'
  }

  function openNote(id: string) {
    history.pushState({ noteId: id }, '', '#' + id)
    selectedId.set(id)
  }

  // ── Virtual grid ───────────────────────────────────────────
  // Cards are uniform-height (excerpt is clamped to 3 lines) so a fixed
  // row-height estimate is reliable. This avoids the need to measure actual
  // DOM heights while still keeping the scrollbar accurate.
  const GAP = 12          // matches CSS gap
  const PAD = 14          // grid padding (top/bottom/left/right)
  const MIN_COL_W = 240   // matches minmax(240px, 1fr)
  const ROW_H = 218       // measured estimate for a clamped card
  const OVERSCAN = 3      // extra rows to render above/below viewport

  let scrollEl: HTMLElement
  let viewW = 800
  let viewH = 600
  let scrollTop = 0

  // Column count derived from container width, matching the CSS minmax rule
  $: cols = Math.max(1, Math.floor((viewW - PAD * 2 + GAP) / (MIN_COL_W + GAP)))
  $: totalRows = Math.ceil(sorted.length / cols)
  // Total scrollable height: padding top + rows + gaps + padding bottom
  $: totalH = PAD + totalRows * (ROW_H + GAP) - (totalRows > 0 ? GAP : 0) + PAD

  // Visible row window
  $: startRow = Math.max(0, Math.floor((scrollTop - PAD) / (ROW_H + GAP)) - OVERSCAN)
  $: endRow   = Math.min(totalRows - 1, Math.ceil((scrollTop + viewH - PAD) / (ROW_H + GAP)) + OVERSCAN)
  // Absolute top position of the rendered grid window inside the total-height container
  $: gridTop = PAD + startRow * (ROW_H + GAP)
  $: visibleItems = sorted.slice(startRow * cols, (endRow + 1) * cols)

  function onScroll(e: Event) {
    scrollTop = (e.currentTarget as HTMLElement).scrollTop
  }

  onMount(() => {
    const ro = new ResizeObserver(([entry]) => {
      viewW = entry.contentRect.width
      viewH = entry.contentRect.height
    })
    ro.observe(scrollEl)
    return () => ro.disconnect()
  })
</script>

<div class="cards-view">
  <!-- Toolbar -->
  <div class="toolbar">
    <span class="note-count">{sorted.length} notes</span>
    <div class="search-wrap">
      <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" class="search-icon">
        <circle cx="7" cy="7" r="5"/>
        <line x1="11" y1="11" x2="15" y2="15"/>
      </svg>
      <input
        class="search-input"
        bind:value={search}
        placeholder="Search title, tags, content…"
        aria-label="Search notes"
      />
    </div>
    <select class="sort-select" bind:value={sortKey} aria-label="Sort notes">
      <option value="default">Default order</option>
      <option value="date">Date modified</option>
      <option value="category">Category</option>
      <option value="level">Level</option>
      <option value="status">Status</option>
    </select>
  </div>

  <!-- Virtual scroll container -->
  <div class="virtual-scroll" bind:this={scrollEl} on:scroll={onScroll}>
    <!-- Sized to total content height so the scrollbar is correct -->
    <div class="virtual-total" style="height:{totalH}px">

      {#if sorted.length === 0}
        <div class="empty">No notes match your search or filters.</div>
      {:else}
        <!-- Only the visible window of cards is rendered -->
        <div
          class="grid"
          style="top:{gridTop}px; grid-template-columns:repeat({cols},1fr)"
        >
          {#each visibleItems as note (note.id)}
            {@const isSelected = $selectedId === note.id}
            <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
            <div
              class="card"
              class:card--selected={isSelected}
              on:click={() => openNote(note.id)}
              role="button"
              tabindex="0"
              on:keydown={(e) => e.key === 'Enter' && openNote(note.id)}
              aria-label="Open {note.title}"
            >
              <!-- Top row: dot + category + status badge -->
              <div class="card-top">
                <span class="cat-dot" style="background:{categoryColor(note.category, $settings.catColorOverrides)}"></span>
                <span class="cat-label">{note.category}</span>
                <span class="flex-1"></span>
                <span class="status-badge" style="color:{statusColor(note.status)};background:{statusColor(note.status)}22">
                  {statusLabel(note.status)}
                </span>
              </div>

              <!-- Title -->
              <div class="card-title">{note.title}</div>

              <!-- Excerpt -->
              <div class="card-excerpt">{excerptText(note)}</div>

              <!-- Tags -->
              {#if note.tags.length > 0}
                <div class="tag-row">
                  {#each note.tags.slice(0, 3) as tag}
                    <span class="tag">#{tag}</span>
                  {/each}
                </div>
              {/if}

              <!-- Footer: level + links + date -->
              <div class="card-footer">
                {#if note.level !== null}
                  <span class="meta">L{note.level}</span>
                {/if}
                <span class="meta">↳ {note.tags.length} tags</span>
                <span class="flex-1"></span>
                <span class="meta">{note.modified.slice(5)}</span>
              </div>
            </div>
          {/each}
        </div>
      {/if}

    </div>
  </div>
</div>

<style>
  .cards-view {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  /* Toolbar */
  .toolbar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    border-bottom: 1px solid var(--border);
    background: var(--panel);
    flex-shrink: 0;
  }

  .note-count {
    font-size: 12px;
    color: var(--muted);
    white-space: nowrap;
  }

  .search-wrap {
    flex: 1;
    max-width: 340px;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0 10px;
    height: 30px;
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 6px;
  }

  .search-icon {
    color: var(--muted-2);
    flex-shrink: 0;
  }

  .search-input {
    flex: 1;
    background: none;
    border: none;
    color: var(--text);
    font-size: 12px;
    font-family: var(--font-ui);
    outline: none;
  }
  .search-input::placeholder {
    color: var(--muted-2);
  }

  .sort-select {
    height: 30px;
    padding: 0 28px 0 10px;
    background-color: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text);
    font-size: 11.5px;
    font-family: var(--font-ui);
    cursor: pointer;
    appearance: none;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path d='M1 1l4 4 4-4' stroke='%238b949e' stroke-width='1.4' fill='none' stroke-linecap='round'/></svg>");
    background-repeat: no-repeat;
    background-position: right 9px center;
  }

  /* Virtual scroll */
  .virtual-scroll {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
  }

  .virtual-total {
    position: relative;
    /* height set by inline style = total content height */
  }

  /* Grid: absolutely positioned within virtual-total, only renders visible rows */
  .grid {
    position: absolute;
    left: 14px;
    right: 14px;
    /* top set by inline style = gridTop */
    display: grid;
    /* grid-template-columns set by inline style = repeat(cols, 1fr) */
    gap: 12px;
  }

  .empty {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    font-size: 13px;
    color: var(--muted-2);
  }

  .card {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 13px;
    cursor: pointer;
    transition: border-color 0.12s, box-shadow 0.12s;
    display: flex;
    flex-direction: column;
    gap: 7px;
  }
  .card:hover {
    border-color: var(--accent-dim);
    box-shadow: 0 4px 16px var(--shadow);
  }
  .card--selected {
    border-color: var(--accent);
    box-shadow: 0 0 0 1px var(--accent);
  }

  .card-top {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .cat-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .cat-label {
    font-size: 10px;
    color: var(--muted);
    font-weight: 500;
  }

  .flex-1 {
    flex: 1;
  }

  .status-badge {
    font-size: 9px;
    font-weight: 600;
    padding: 2px 6px;
    border-radius: 4px;
    white-space: nowrap;
  }

  .card-title {
    font-size: 13.5px;
    font-weight: 600;
    color: var(--text);
    line-height: 1.3;
    letter-spacing: -0.01em;
  }

  .card-excerpt {
    font-size: 11px;
    color: var(--muted);
    line-height: 1.5;
    flex: 1;
    min-height: 32px;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
  }

  .tag-row {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }

  .tag {
    font-size: 9.5px;
    color: var(--muted-2);
    background: var(--panel-3);
    border: 1px solid var(--border);
    border-radius: 3px;
    padding: 1px 5px;
    font-family: var(--font-mono);
  }

  .card-footer {
    display: flex;
    align-items: center;
    gap: 8px;
    padding-top: 7px;
    border-top: 1px solid var(--border-2);
  }

  .meta {
    font-size: 9.5px;
    color: var(--muted-2);
    font-family: var(--font-mono);
  }
</style>
