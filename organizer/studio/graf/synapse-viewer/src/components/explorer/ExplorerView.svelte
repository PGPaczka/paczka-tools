<script lang="ts">
  import { onMount } from 'svelte'
  import { graph, filters } from '../../stores/graphStore'
  import { selectedId } from '../../stores/selectionStore'
  import { categoryColor } from '../../domain/color/categoryColor'
  import { settings } from '../../stores/settingsStore'
  import { realNodesIgnoringNodeType } from '../../domain/graph/selectors'
  import {
    autoPath, buildMillerTree, columnsFor, visiblePath,
  } from '../../domain/graph/millerTree'
  import { nextFocus, focusedNode, type FocusState } from '../../domain/graph/millerKeyboard'
  import { humanSize } from '../../domain/format/size'
  import type { RealNode } from '../../domain/graph/GraphModel'

  // Walking the containment tree, not the force layout: the vault already declares
  // `semester → subject → category → group → file`, and that is how you reach one file
  // out of thousands. Filters apply EXCEPT the node-type dimension — see the selector.
  $: allNodes = ($graph?.nodes ?? []).filter((n): n is RealNode => n.kind === 'real')
  $: matching = new Set(
    ($graph ? realNodesIgnoringNodeType($graph, $filters) : []).map((n) => n.id),
  )
  // The tree is built over EVERY note, with the filter as a predicate, so the road to a
  // match survives it. Building it over the filtered list instead loses the containers —
  // narrowing by category drops the subject and semester, whose own category is `SEM3` —
  // and the view then opens on a lone category with no way to tell where it lives.
  $: tree = buildMillerTree(
    allNodes,
    $graph?.edges ?? [],
    matching.size === allNodes.length ? undefined : (n) => matching.has(n.id),
  )

  // Arriving from a narrowing elsewhere (a cell of the matrix) leaves a tree one row wide;
  // opening it is repeating a choice already made. Recomputed per tree, not stored, so it
  // follows the filters instead of fighting the path the reader walks by hand.
  $: auto = autoPath(tree)

  let state: FocusState = { path: [], cursor: 0 }

  // The path outlives the graph it was made against — filters change, the graph is
  // rebuilt — so anything it points at may be gone. It is truncated on the way OUT,
  // never written back: correcting the state from a value derived from that same state
  // is a reactive cycle, and the build refuses it.
  $: open = state.path.length > 0 ? visiblePath(tree, state.path) : auto
  $: live = { path: open, cursor: state.cursor }
  $: columns = columnsFor(tree, open)
  $: openable = new Set(
    columns.flat().filter((n) => tree.childrenOf(n.id).length > 0).map((n) => n.id),
  )
  $: focused = focusedNode(live, columns)

  $: breadcrumbs = open
    .map((id) => tree.nodeById(id))
    .filter((n): n is RealNode => n !== undefined)

  function openNote(id: string) {
    history.pushState({ noteId: id }, '', '#' + id)
    selectedId.set(id)
  }

  /** A row click: descend into a container, select a leaf. Both also move the cursor. */
  function activate(columnIndex: number, node: RealNode) {
    const path = open.slice(0, columnIndex)
    if (tree.childrenOf(node.id).length > 0) {
      state = { path: [...path, node.id], cursor: 0 }
    } else {
      const column = columnsFor(tree, path)[columnIndex] ?? []
      state = { path, cursor: Math.max(column.findIndex((n) => n.id === node.id), 0) }
    }
    openNote(node.id)
  }

  function jumpTo(depth: number) {
    state = { path: open.slice(0, depth), cursor: 0 }
  }

  function onKeydown(event: KeyboardEvent) {
    const target = event.target as HTMLElement | null
    if (target && (target.tagName === 'INPUT' || target.tagName === 'SELECT')) return
    if (event.metaKey || event.ctrlKey || event.altKey) return

    const next = nextFocus(live, event.key, columns, openable)
    if (next === live) return

    event.preventDefault()
    state = next
    const node = focusedNode(next, columnsFor(tree, next.path))
    if (node) openNote(node.id)
  }

  onMount(() => {
    window.addEventListener('keydown', onKeydown)
    return () => window.removeEventListener('keydown', onKeydown)
  })

  // A narrowing made elsewhere (a cell of the matrix) is a new question, so the walk made
  // against the old one is dropped and the view opens itself again. Done as a subscription
  // rather than a reactive block: assigning state from something the columns also derive
  // from is how the reactive cycle happened the first time.
  onMount(() => filters.subscribe(() => { state = { path: [], cursor: 0 } }))

  // ── Virtual rows ───────────────────────────────────────────
  // One category of AKO holds 2563 files, so a column renders its window, not its list.
  // Rows are uniform height by construction (one line + one meta line, both clamped).
  const ROW_H = 38
  const OVERSCAN = 6

  let scrollTops: number[] = []
  let columnHeight = 600
  let wrapEl: HTMLElement

  function onColumnScroll(index: number, event: Event) {
    const next = scrollTops.slice()
    next[index] = (event.currentTarget as HTMLElement).scrollTop
    scrollTops = next
  }

  function windowOf(index: number, length: number): { start: number; end: number } {
    const top = scrollTops[index] ?? 0
    const start = Math.max(0, Math.floor(top / ROW_H) - OVERSCAN)
    const end = Math.min(length, Math.ceil((top + columnHeight) / ROW_H) + OVERSCAN)
    return { start, end }
  }

  onMount(() => {
    const ro = new ResizeObserver(([entry]) => {
      columnHeight = entry.contentRect.height
    })
    ro.observe(wrapEl)
    return () => ro.disconnect()
  })

  // Below this width only the deepest column fits; breadcrumbs carry the way back.
  const NARROW = 720
  let width = 1200
  $: narrow = width <= NARROW
  $: shown = narrow ? [columns.length - 1] : columns.map((_, i) => i)

  function label(node: RealNode): string {
    const kind = node.contentKind ? node.contentKind : null
    const size = humanSize(node.sizeBytes)
    const count = tree.descendantCount(node.id)
    if (count > 0) return `${count}`
    return [kind, size].filter(Boolean).join(' · ')
  }

  function levelTitle(level: number | null): string {
    if (level === 1) return 'w paczce'
    if (level === 2) return 'zaplanowane'
    if (level === 3) return 'do przeglądu'
    return ''
  }
</script>

<svelte:window bind:innerWidth={width} />

<div class="explorer">
  <div class="bar">
    <button class="crumb" class:active={open.length === 0} on:click={() => jumpTo(0)}>
      vault
    </button>
    {#each breadcrumbs as node, depth}
      <span class="sep">›</span>
      <button
        class="crumb"
        class:active={depth === breadcrumbs.length - 1}
        on:click={() => jumpTo(depth + 1)}
      >{node.title}</button>
    {/each}
    <span class="flex-1"></span>
    {#if focused}
      <span class="hint">{focused.title}</span>
    {/if}
  </div>

  <div class="columns" bind:this={wrapEl}>
    {#each shown as index (index)}
      {@const column = columns[index] ?? []}
      {@const win = windowOf(index, column.length)}
      {@const selectedHere = open[index]}
      <div class="column" on:scroll={(e) => onColumnScroll(index, e)}>
        <div class="spacer" style="height:{column.length * ROW_H}px">
          <div class="rows" style="top:{win.start * ROW_H}px">
            {#each column.slice(win.start, win.end) as node (node.id)}
              {@const isOpen = node.id === selectedHere}
              {@const isFocused = focused?.id === node.id && index === columns.length - 1}
              <!-- svelte-ignore a11y-click-events-have-key-events -->
              <div
                class="row"
                class:open={isOpen}
                class:focused={isFocused}
                style="height:{ROW_H}px"
                role="button"
                tabindex="-1"
                on:click={() => activate(index, node)}
                title={node.title}
              >
                <span
                  class="dot"
                  style="background:{categoryColor(node.category, $settings.catColorOverrides)}"
                ></span>
                <span class="name">{node.title}</span>
                {#if node.level !== null}
                  <span class="level l{node.level}" title={levelTitle(node.level)}>
                    L{node.level}
                  </span>
                {/if}
                <span class="meta">{label(node)}</span>
                {#if tree.childrenOf(node.id).length > 0}
                  <span class="chevron">›</span>
                {/if}
              </div>
            {/each}
          </div>
        </div>
      </div>
    {/each}
  </div>

  {#if focused}
    <div class="footer">
      <span class="ftitle">{focused.title}</span>
      {#if focused.contentKind}<span class="fmeta">{focused.contentKind}</span>{/if}
      {#if humanSize(focused.sizeBytes)}<span class="fmeta">{humanSize(focused.sizeBytes)}</span>{/if}
      <span class="flex-1"></span>
      {#if focused.sha256}
        <!-- Absolute on purpose: studio serves the viewer under /graf/, and this leaves it. -->
        <a class="studio" href={`/?sha=${focused.sha256}`}>Otwórz w studiu ↗</a>
      {/if}
    </div>
  {/if}
</div>

<style>
  .explorer {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .bar, .footer {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 12px;
    background: var(--panel);
    flex-shrink: 0;
    font-size: 12px;
    overflow-x: auto;
    white-space: nowrap;
  }
  .bar { border-bottom: 1px solid var(--border); }
  .footer { border-top: 1px solid var(--border); }

  .crumb {
    background: none;
    border: none;
    color: var(--muted);
    font-family: var(--font-ui);
    font-size: 12px;
    cursor: pointer;
    padding: 2px 4px;
    border-radius: 4px;
  }
  .crumb:hover { color: var(--text); background: var(--panel-2); }
  .crumb.active { color: var(--text); }
  .sep { color: var(--muted-2); }
  .hint, .fmeta { color: var(--muted-2); font-size: 11.5px; }
  .ftitle { color: var(--text); }
  .flex-1 { flex: 1; }

  .studio {
    color: var(--accent, #58a6ff);
    text-decoration: none;
    font-size: 11.5px;
  }
  .studio:hover { text-decoration: underline; }

  .columns {
    flex: 1;
    display: flex;
    overflow-x: auto;
    overflow-y: hidden;
  }

  .column {
    flex: 0 0 280px;
    height: 100%;
    overflow-y: auto;
    border-right: 1px solid var(--border);
  }
  .column:last-child { flex: 1 1 280px; }

  .spacer { position: relative; }
  .rows { position: absolute; left: 0; right: 0; }

  .row {
    display: flex;
    align-items: center;
    gap: 7px;
    padding: 0 10px;
    cursor: pointer;
    box-sizing: border-box;
  }
  .row:hover { background: var(--panel-2); }
  .row.open { background: var(--panel-2); }
  .row.focused { outline: 1px solid var(--accent, #58a6ff); outline-offset: -1px; }

  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .name {
    flex: 1;
    color: var(--text);
    font-size: 12.5px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .meta { color: var(--muted-2); font-size: 11px; white-space: nowrap; }
  .chevron { color: var(--muted-2); }

  .level {
    font-size: 10px;
    padding: 1px 4px;
    border-radius: 3px;
    color: var(--muted);
    background: var(--panel-2);
  }
  /* w paczce / zaplanowane / do przeglądu — te same trzy stany co w macierzy */
  .level.l1 { color: #3fb950; background: #3fb95022; }
  .level.l2 { color: #d29922; background: #d2992222; }
  .level.l3 { color: #f85149; background: #f8514922; }

  @media (max-width: 720px) {
    .column { flex: 1 1 100%; border-right: none; }
  }

  /* Poniżej 820px powłoka wystawia pływający przycisk szuflady filtrów w lewym górnym
     rogu obszaru roboczego (left 8px, top 68px, 36×36). Pasek ustępuje mu miejsca w obu
     osiach: wcięcie z lewej odsłania treść, a wysokość sprawia, że przycisk siada NA
     pasku zamiast na pierwszym wierszu listy, który jest celem kliknięcia. */
  @media (max-width: 820px) {
    .bar { padding-left: 52px; min-height: 60px; }
  }
</style>
