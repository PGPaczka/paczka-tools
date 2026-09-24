<script lang="ts">
  import { onMount, onDestroy } from 'svelte'
  import { get } from 'svelte/store'
  import { loadGraph } from './data/GraphLoader'
  import { startPolling } from './data/pollGraphJson'
  import { graph, loadError, filters } from './stores/graphStore'
  import { defaultFiltersFor } from './domain/graph/selectors'
  import {
    narrowsAnything,
    readStoredFilters,
    sanitizeFilters,
    writeStoredFilters,
    type FilterVocabulary,
  } from './stores/filterPersistence'
  import type { KnowledgeGraph } from './domain/graph/GraphModel'

  /** Co w TYM grafie w ogóle istnieje — po tym przycinamy zapamiętany wybór. */
  function vocabularyOf(loaded: KnowledgeGraph): FilterVocabulary {
    const real = loaded.nodes.filter((n) => n.kind === 'real')
    return {
      categories: new Set(real.map((n) => n.category)),
      statuses: new Set(real.map((n) => String(n.status))),
      levels: new Set(real.map((n) => n.level)),
      tags: new Set(real.flatMap((n) => n.tags)),
      nodeTypes: new Set(real.map((n) => n.type ?? '')),
      relationKinds: new Set(loaded.edges.map((e) => e.kind ?? 'link')),
    }
  }
  import { selectedId } from './stores/selectionStore'
  import { settings } from './stores/settingsStore'
  import type { LayoutId } from './layout/layoutRegistry'

  import GraphCanvas from './components/graph/GraphCanvas.svelte'
  import GraphOverlay from './components/graph/GraphOverlay.svelte'
  import FilterPanel from './components/filters/FilterPanel.svelte'
  import DetailPanel from './components/detail/DetailPanel.svelte'
  import CommandPalette from './components/palette/CommandPalette.svelte'
  import DashboardView from './components/dashboard/DashboardView.svelte'
  import VennView from './components/venn/VennView.svelte'
  import CardsView from './components/cards/CardsView.svelte'
  import SettingsModal from './components/settings/SettingsModal.svelte'
  import ClassicShell from './layout/ClassicShell.svelte'
  import RailShell from './layout/RailShell.svelte'
  import CommandShell from './layout/CommandShell.svelte'

  // ── App state ──────────────────────────────────────────────
  let loading = true
  let view: 'graph' | 'cards' | 'dash' | 'venn' = 'graph'
  let paletteOpen = false
  let settingsOpen = false

  // ETag polling state
  let stopPolling: (() => void) | null = null

  // History navigation: track whether a selectedId change came from popstate
  // so we don't push a new history entry on popstate-driven updates.
  let historyDriven = false

  // ── Graph load + polling ───────────────────────────────────
  onMount(async () => {
    let etag: string | null = null
    let lastModified: string | null = null

    try {
      const loaded = await loadGraph('/graph.json')
      graph.set(loaded.graph)
      // Open a large, typed vault at its coarse level instead of as a cloud of files —
      // chyba że poprzednim razem zawężono widok. Wybór przeżywa odświeżenie, ale
      // przycinamy go do tego, co W TYM grafie nadal istnieje.
      const zapisane = sanitizeFilters(readStoredFilters(), vocabularyOf(loaded.graph))
      filters.set(
        zapisane && narrowsAnything(zapisane) ? zapisane : defaultFiltersFor(loaded.graph),
      )
      filters.subscribe(writeStoredFilters)
      etag = loaded.etag
      lastModified = loaded.lastModified
    } catch (e) {
      loadError.set(e instanceof Error ? e.message : String(e))
    } finally {
      loading = false
    }

    // Restore selected note from URL hash on first load
    const hash = window.location.hash.slice(1)
    if (hash) {
      selectedId.set(hash)
    }

    // Start 30-second ETag polling after initial load
    stopPolling = startPolling(30_000, etag, lastModified, (newGraph) => {
      graph.set(newGraph)
    })

    // ⌘K / Ctrl+K global shortcut
    function onKeydown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        paletteOpen = true
      }
      if (e.key === 'Escape' && settingsOpen) {
        settingsOpen = false
      }
    }
    window.addEventListener('keydown', onKeydown)

    // Browser back/forward navigation
    function onPopstate(e: PopStateEvent) {
      historyDriven = true
      const noteId = (e.state as { noteId?: string | null } | null)?.noteId ?? null
      selectedId.set(noteId)
      historyDriven = false
    }
    window.addEventListener('popstate', onPopstate)

    return () => {
      window.removeEventListener('keydown', onKeydown)
      window.removeEventListener('popstate', onPopstate)
    }
  })

  onDestroy(() => {
    stopPolling?.()
  })

  // Push browser history when selectedId changes (except when driven by popstate).
  //
  // The store fires once at subscribe time with its initial value. That first
  // emission is state, not navigation: acting on it rewrote the URL to ' ' during
  // component init, wiping the '#note-id' deep link *before* onMount could read it.
  // Opening a link to a specific note therefore selected nothing — reproduced with
  // a fresh load of '/#<id>'. Skip the initial emission and the deep link survives.
  let historyPrimed = false
  selectedId.subscribe((id) => {
    if (historyDriven) return
    if (!historyPrimed) {
      historyPrimed = true
      return
    }
    if (id) {
      history.pushState({ noteId: id }, '', '#' + id)
    } else {
      history.replaceState({ noteId: null }, '', ' ')
    }
  })

  // ── Action handlers ────────────────────────────────────────
  function handleSwitchView(e: CustomEvent<string>) {
    view = e.detail as 'graph' | 'cards' | 'dash' | 'venn'
  }

  function handleSwitchLayout(e: CustomEvent<string>) {
    settings.update((s) => ({ ...s, layout: e.detail as LayoutId }))
  }

  function handleOpenSettings() {
    settingsOpen = true
  }

  function handleOpenPalette() {
    paletteOpen = true
  }

  function handlePaletteClose() {
    paletteOpen = false
  }

  function handlePaletteSwitchView(e: CustomEvent<string>) {
    view = e.detail as 'graph' | 'cards' | 'dash' | 'venn'
  }

  function handlePaletteSwitchLayout(e: CustomEvent<string>) {
    settings.update((s) => ({ ...s, layout: e.detail as LayoutId }))
  }

  $: layout = $settings.layout
  $: vaultName = $graph?.vault?.name ?? 'Synapse'
</script>

<!-- Settings modal -->
{#if settingsOpen}
  <SettingsModal on:close={() => (settingsOpen = false)} />
{/if}

<!-- Loading / error states -->
{#if loading}
  <div class="full-state loading-state">Loading graph…</div>
{:else if $loadError}
  <div class="full-state error-state">
    {#if $loadError.includes('SCHEMA_MISMATCH')}
      <strong>Schema mismatch</strong> — graph.json format is not compatible with this viewer.
    {:else}
      Failed to load graph: {$loadError}
    {/if}
  </div>
{:else}
  <!-- Command palette (rendered outside shell so it overlays everything) -->
  <CommandPalette
    bind:open={paletteOpen}
    on:close={handlePaletteClose}
    on:switchView={handlePaletteSwitchView}
    on:switchLayout={handlePaletteSwitchLayout}
    on:openSettings={handleOpenSettings}
  />

  <!-- Layout shells -->
  {#if layout === 'rail'}
    <RailShell
      {view}
      {vaultName}
      on:switchView={handleSwitchView}
      on:openSettings={handleOpenSettings}
      on:openPalette={handleOpenPalette}
    >
      <svelte:fragment slot="filters">
        <FilterPanel />
      </svelte:fragment>
      <svelte:fragment slot="main">
        <!-- GraphCanvas is always mounted so the simulation state (node positions,
             physics) survives view switches. CSS display:none hides it without
             destroying it. draw() guards against 0×0 to avoid corrupting viewport. -->
        <div class="graph-wrapper" style:display={view === 'graph' ? '' : 'none'}>
          <GraphCanvas />
          <GraphOverlay />
        </div>
        {#if view === 'venn'}
          <VennView />
        {:else if view === 'cards'}
          <CardsView />
        {:else if view === 'dash'}
          <DashboardView />
        {/if}
      </svelte:fragment>
      <svelte:fragment slot="detail">
        {#if $selectedId}
          <DetailPanel />
        {/if}
      </svelte:fragment>
    </RailShell>

  {:else if layout === 'command'}
    <CommandShell
      {view}
      on:switchView={handleSwitchView}
      on:openSettings={handleOpenSettings}
      on:openPalette={handleOpenPalette}
    >
      <svelte:fragment slot="main">
        <div class="graph-wrapper" style:display={view === 'graph' ? '' : 'none'}>
          <GraphCanvas />
          <GraphOverlay />
        </div>
        {#if view === 'venn'}
          <VennView />
        {:else if view === 'cards'}
          <CardsView />
        {:else if view === 'dash'}
          <DashboardView />
        {/if}
      </svelte:fragment>
      <svelte:fragment slot="filters">
        <FilterPanel />
      </svelte:fragment>
      <svelte:fragment slot="detail">
        {#if $selectedId}
          <DetailPanel />
        {/if}
      </svelte:fragment>
    </CommandShell>

  {:else}
    <!-- Classic (default) -->
    <ClassicShell
      {view}
      {vaultName}
      on:switchView={handleSwitchView}
      on:openSettings={handleOpenSettings}
      on:openPalette={handleOpenPalette}
    >
      <svelte:fragment slot="filters">
        <FilterPanel />
      </svelte:fragment>
      <svelte:fragment slot="main">
        <div class="graph-wrapper" style:display={view === 'graph' ? '' : 'none'}>
          <GraphCanvas />
          <GraphOverlay />
        </div>
        {#if view === 'venn'}
          <VennView />
        {:else if view === 'cards'}
          <CardsView />
        {:else if view === 'dash'}
          <DashboardView />
        {/if}
      </svelte:fragment>
      <svelte:fragment slot="detail">
        {#if $selectedId}
          <DetailPanel />
        {/if}
      </svelte:fragment>
    </ClassicShell>
  {/if}
{/if}

<style>
  .full-state {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100vw;
    height: 100vh;
    /* `dvh` liczy się do PASKA ADRESU telefonu, a `vh` do całego ekranu — stąd legenda
       i minimapa lądowały pod krawędzią i trzeba było przewijać, żeby je zobaczyć. */
    height: 100dvh;
    font-family: var(--font-ui);
    font-size: 14px;
  }

  .loading-state {
    color: var(--muted);
  }

  .error-state {
    color: var(--red);
    text-align: center;
    padding: 24px;
    max-width: 480px;
    margin: auto;
  }

  .graph-wrapper {
    position: relative;
    width: 100%;
    height: 100%;
    overflow: hidden;
  }
</style>
