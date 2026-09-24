<script lang="ts">
  /**
   * Filters as a drawer on small screens.
   *
   * The filter panel is a fixed 220px column. On a 412px phone that left the canvas
   * ~190px wide, so an embedded graph looked like "only the sidebar loaded" (reported
   * from a phone and a tablet). Below 820px it floats above the canvas instead.
   */
  let filtersOpen = false
  import { createEventDispatcher } from 'svelte'

  export let view: 'graph' | 'cards' | 'dash' | 'venn' = 'graph'
  export let vaultName: string = 'Synapse'

  const dispatch = createEventDispatcher<{
    switchView: 'graph' | 'cards' | 'dash' | 'venn'
    openSettings: void
    openPalette: void
  }>()

  const SETTINGS_ICON = `<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 16 16" fill="currentColor">
    <path d="M6.5 1h3l.45 1.8a5.2 5.2 0 011.3.75l1.75-.6 1.5 2.6-1.4 1.1a5.2 5.2 0 010 1.7l1.4 1.1-1.5 2.6-1.75-.6a5.2 5.2 0 01-1.3.75L9.5 14h-3l-.45-1.75A5.2 5.2 0 014.75 11.5l-1.75.6-1.5-2.6 1.4-1.1a5.2 5.2 0 010-1.7L1.5 5.55l1.5-2.6 1.75.6A5.2 5.2 0 016.05 2.8L6.5 1zm1.5 9a2 2 0 100-4 2 2 0 000 4z"/>
  </svg>`

  const views: Array<{ id: 'graph' | 'cards' | 'dash' | 'venn'; label: string }> = [
    { id: 'graph', label: 'Graph' },
    { id: 'venn', label: 'Venn' },
    { id: 'cards', label: 'Cards' },
    { id: 'dash', label: 'Dash' },
  ]
</script>

<div class="classic-shell">
  <!-- Top bar -->
  <header class="topbar">
    <!-- Left: logo + vault name -->
    <div class="topbar-left">
      <div class="logo">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20">
          <defs>
            <radialGradient id="lg" cx="40%" cy="35%">
              <stop offset="0%" stop-color="#58a6ff"/>
              <stop offset="100%" stop-color="#1f6feb"/>
            </radialGradient>
          </defs>
          <circle cx="10" cy="10" r="9" fill="url(#lg)"/>
          <circle cx="10" cy="10" r="2.5" fill="white" fill-opacity=".9"/>
          <line x1="10" y1="4" x2="10" y2="7" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
          <line x1="10" y1="13" x2="10" y2="16" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
          <line x1="4" y1="10" x2="7" y2="10" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
          <line x1="13" y1="10" x2="16" y2="10" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
      </div>
      <span class="vault-name">{vaultName}</span>
    </div>

    <!-- Center: palette trigger -->
    <button class="palette-trigger" on:click={() => dispatch('openPalette')}>
      <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="7" cy="7" r="5"/>
        <line x1="11" y1="11" x2="15" y2="15"/>
      </svg>
      <span class="trigger-label">Search or run a command…</span>
      <kbd class="trigger-kbd">⌘K</kbd>
    </button>

    <!-- Right: tabs + layout + settings -->
    <div class="topbar-right">
      <nav class="view-tabs">
        {#each views as v}
          <button
            class="tab-btn"
            class:active={view === v.id}
            on:click={() => dispatch('switchView', v.id)}
          >
            {v.label}
          </button>
        {/each}
      </nav>

      <!-- Na telefonie cztery zakładki nie mieszczą się obok wyszukiwarki i uciekały
           poza ekran. Lista rozwijana zajmuje tyle co jeden przycisk. -->
      <select
        class="view-select"
        aria-label="View"
        value={view}
        on:change={(event) =>
          dispatch('switchView', event.currentTarget.value as (typeof views)[number]['id'])}
      >
        {#each views as v}
          <option value={v.id}>{v.label}</option>
        {/each}
      </select>

      <button class="icon-btn settings-btn" title="Settings" on:click={() => dispatch('openSettings')}>
        {@html SETTINGS_ICON}
      </button>
    </div>
  </header>

  <!-- Content row -->
  <button
    class="filters-toggle"
    class:open={filtersOpen}
    aria-label={filtersOpen ? 'Hide filters' : 'Show filters'}
    on:click={() => (filtersOpen = !filtersOpen)}
  >{filtersOpen ? '×' : '☰'}</button>

  <div class="content-row" class:filters-open={filtersOpen}>
    <!-- Left sidebar: filter panel slot -->
    <slot name="filters" />

    <!-- Main area -->
    <main class="main-area">
      <slot name="main" />
    </main>

    <!-- Right: detail panel slot -->
    <slot name="detail" />
  </div>
</div>

<style>
  .classic-shell {
    width: 100vw;
    height: 100vh;
    /* `dvh` liczy się do PASKA ADRESU telefonu, a `vh` do całego ekranu — stąd legenda
       i minimapa lądowały pod krawędzią i trzeba było przewijać, żeby je zobaczyć. */
    height: 100dvh;
    display: flex;
    flex-direction: column;
    background: var(--bg);
    overflow: hidden;
  }

  .topbar {
    height: 44px;
    background: var(--panel);
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0 12px;
    flex-shrink: 0;
    z-index: 10;
  }

  .topbar-left {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
  }

  .logo {
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .vault-name {
    font-size: 13px;
    font-weight: 600;
    color: var(--text);
    white-space: nowrap;
  }

  .palette-trigger {
    flex: 1;
    max-width: 360px;
    margin: 0 auto;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 12px;
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--muted-2);
    cursor: pointer;
    font-size: 12px;
    font-family: var(--font-ui);
    transition: all 0.12s;
  }
  .palette-trigger:hover {
    background: var(--panel-3);
    border-color: var(--accent-dim);
    color: var(--muted);
  }

  .trigger-label {
    flex: 1;
    text-align: left;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .trigger-kbd {
    font-size: 10px;
    background: var(--panel-3);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 1px 5px;
    color: var(--muted-2);
    font-family: var(--font-ui);
    flex-shrink: 0;
  }

  .topbar-right {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
    margin-left: auto;
  }

  .view-select {
    display: none;
    max-width: 104px;
    padding: 4px 6px;
    background: var(--panel-2);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 12px;
  }

  .view-tabs {
    display: flex;
    gap: 2px;
  }

  .tab-btn {
    padding: 4px 10px;
    border-radius: 5px;
    border: 1px solid transparent;
    background: transparent;
    color: var(--muted);
    font-size: 12px;
    font-family: var(--font-ui);
    cursor: pointer;
    transition: all 0.1s;
    white-space: nowrap;
  }
  .tab-btn:hover {
    background: var(--panel-2);
    color: var(--text);
  }
  .tab-btn.active {
    background: var(--panel-2);
    border-color: var(--border);
    color: var(--text);
  }

  .icon-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border-radius: 5px;
    border: none;
    background: transparent;
    color: var(--muted);
    cursor: pointer;
    transition: all 0.1s;
  }
  .icon-btn:hover {
    background: var(--panel-2);
    color: var(--text);
  }

  .content-row {
    flex: 1;
    display: flex;
    overflow: hidden;
  }

  .main-area {
    flex: 1;
    overflow: hidden;
    position: relative;
  }

  /* Na szerokim ekranie kolumna filtrów jest zawsze — przycisk byłby zbędny. */
  .filters-toggle {
    display: none;
  }

  @media (max-width: 820px) {
    .filters-toggle {
      display: block;
      position: absolute;
      left: 8px;
      top: 60px;
      z-index: 30;
      width: 38px;
      height: 38px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--panel);
      color: var(--text);
      font-size: 17px;
      line-height: 1;
      cursor: pointer;
    }

    .content-row > :global(.filter-panel) {
      position: absolute;
      top: 48px;
      bottom: 0;
      left: 0;
      z-index: 25;
      transform: translateX(-102%);
      transition: transform 0.16s ease-out;
      box-shadow: 0 0 24px rgba(1, 4, 9, 0.6);
    }
    .content-row.filters-open > :global(.filter-panel) {
      transform: translateX(0);
    }

    /* Otwarta szuflada: przycisk przenosi się na JEJ prawą krawędź. W rogu zasłaniał
       tytuł panelu filtrów, a po zamknięciu wchodził na panel notatki. */
    .filters-toggle.open {
      left: auto;
      right: 8px;
    }

    /* Panel notatki jest wtedy arkuszem na całą szerokość, nie trzecią kolumną. */
    .content-row > :global(.detail-panel) {
      position: absolute;
      top: 48px;
      bottom: 0;
      left: 0;
      right: 0;
      z-index: 26;
      width: auto !important;
      max-width: none;
    }
  }

  /* Wąski ekran: zakładki chowają się w listę. Cztery przyciski obok wyszukiwarki
     nie mieszczą się na telefonie i uciekały poza krawędź. */
  @media (max-width: 720px) {
    .view-tabs {
      display: none;
    }
    .view-select {
      display: block;
    }

    /* Pasek ma się MIEŚCIĆ: nazwa vaulta schodzi, wyszukiwarka oddaje szerokość,
       a koło zębate przestaje wystawać poza krawędź (zgłoszone 2026-09-24). */
    .topbar {
      padding: 0 6px;
      gap: 6px;
    }
    .vault-name,
    .trigger-kbd {
      display: none;
    }
    .palette-trigger {
      min-width: 0;
      flex: 1 1 auto;
    }
    .topbar-right {
      gap: 4px;
      min-width: 0;
    }
  }
</style>
