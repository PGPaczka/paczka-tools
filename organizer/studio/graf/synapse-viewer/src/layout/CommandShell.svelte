<script lang="ts">
  import { createEventDispatcher } from 'svelte'

  export let view: 'graph' | 'cards' | 'dash' | 'venn' = 'graph'

  const dispatch = createEventDispatcher<{
    switchView: 'graph' | 'cards' | 'dash' | 'venn'
    openSettings: void
    openPalette: void
  }>()

  const SETTINGS_ICON = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
    <path d="M6.5 1h3l.45 1.8a5.2 5.2 0 011.3.75l1.75-.6 1.5 2.6-1.4 1.1a5.2 5.2 0 010 1.7l1.4 1.1-1.5 2.6-1.75-.6a5.2 5.2 0 01-1.3.75L9.5 14h-3l-.45-1.75A5.2 5.2 0 014.75 11.5l-1.75.6-1.5-2.6 1.4-1.1a5.2 5.2 0 010-1.7L1.5 5.55l1.5-2.6 1.75.6A5.2 5.2 0 016.05 2.8L6.5 1zm1.5 9a2 2 0 100-4 2 2 0 000 4z"/>
  </svg>`

  /**
   * Filters as a drawer on small screens.
   *
   * The panel is a fixed 220px column. On a phone (412px) that left the canvas
   * ~190px wide, so the graph looked like "only the sidebar loaded" — reported from
   * a tablet and a phone. Below 820px the panel floats above the canvas instead and
   * is toggled from the command bar, so the drawing always gets the full width.
   */
  let filtersOpen = false

  const views: Array<{ id: 'graph' | 'cards' | 'dash' | 'venn'; label: string }> = [
    { id: 'graph', label: 'Graph' },
    { id: 'venn', label: 'Venn' },
    { id: 'cards', label: 'Cards' },
    { id: 'dash', label: 'Dash' },
  ]
</script>

<div class="command-shell">
  <!-- Floating command bar -->
  <div class="command-bar">
    <!-- Logo -->
    <div class="bar-logo">
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 20 20">
        <defs>
          <radialGradient id="lg-cmd" cx="40%" cy="35%">
            <stop offset="0%" stop-color="#58a6ff"/>
            <stop offset="100%" stop-color="#1f6feb"/>
          </radialGradient>
        </defs>
        <circle cx="10" cy="10" r="9" fill="url(#lg-cmd)"/>
        <circle cx="10" cy="10" r="2.5" fill="white" fill-opacity=".9"/>
        <line x1="10" y1="4" x2="10" y2="7" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
        <line x1="10" y1="13" x2="10" y2="16" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
        <line x1="4" y1="10" x2="7" y2="10" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
        <line x1="13" y1="10" x2="16" y2="10" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
    </div>

    <!-- Palette trigger (expanded search bar) -->
    <button class="bar-search" on:click={() => dispatch('openPalette')}>
      <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="7" cy="7" r="5"/>
        <line x1="11" y1="11" x2="15" y2="15"/>
      </svg>
      <span class="bar-search-text">Search or run…</span>
      <kbd>⌘K</kbd>
    </button>

    <div class="bar-divider"></div>

    <!-- View tabs -->
    <nav class="bar-views">
      {#each views as v}
        <button
          class="bar-tab"
          class:active={view === v.id}
          on:click={() => dispatch('switchView', v.id)}
        >
          {v.label}
        </button>
      {/each}
    </nav>

    <!-- Settings -->
    <button class="bar-icon-btn" title="Settings" on:click={() => dispatch('openSettings')}>
      {@html SETTINGS_ICON}
    </button>
  </div>

  <!-- Content row sits below the floating command bar -->
  <button
    class="filters-toggle"
    aria-label={filtersOpen ? 'Hide filters' : 'Show filters'}
    on:click={() => (filtersOpen = !filtersOpen)}
  >{filtersOpen ? '×' : '☰'}</button>

  <div class="content-zone" class:filters-open={filtersOpen}>
    <slot name="filters" />
    <div class="main-area">
      <slot name="main" />
    </div>
    <slot name="detail" />
  </div>
</div>

<style>
  .command-shell {
    width: 100vw;
    height: 100vh;
    background: var(--bg);
    overflow: hidden;
    position: relative;
  }

  .command-bar {
    position: absolute;
    top: 12px;
    left: 50%;
    transform: translateX(-50%);
    width: min(700px, calc(100vw - 32px));
    height: 40px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 10px;
    box-shadow: 0 4px 20px var(--shadow);
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 0 10px;
    z-index: 20;
  }

  .bar-logo {
    display: flex;
    align-items: center;
    flex-shrink: 0;
  }

  .bar-search {
    display: flex;
    align-items: center;
    gap: 7px;
    flex: 1;
    min-width: 0;
    padding: 5px 8px;
    background: var(--panel-2);
    border: 1px solid var(--border-2);
    border-radius: 6px;
    color: var(--muted-2);
    cursor: pointer;
    font-size: 12px;
    font-family: var(--font-ui);
    transition: all 0.12s;
  }
  .bar-search:hover {
    background: var(--panel-3);
    color: var(--muted);
  }

  .bar-search-text {
    flex: 1;
    text-align: left;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .bar-search kbd {
    font-size: 9px;
    background: var(--panel-3);
    border: 1px solid var(--border);
    border-radius: 3px;
    padding: 1px 4px;
    color: var(--muted-2);
    font-family: var(--font-ui);
    flex-shrink: 0;
  }

  .bar-divider {
    width: 1px;
    height: 20px;
    background: var(--border-2);
    flex-shrink: 0;
    margin: 0 2px;
  }

  .bar-views {
    display: flex;
    gap: 1px;
    flex-shrink: 0;
  }

  .bar-tab {
    padding: 3px 9px;
    border-radius: 4px;
    border: 1px solid transparent;
    background: transparent;
    color: var(--muted);
    font-size: 11px;
    font-family: var(--font-ui);
    cursor: pointer;
    transition: all 0.1s;
    white-space: nowrap;
  }
  .bar-tab:hover {
    background: var(--panel-2);
    color: var(--text);
  }
  .bar-tab.active {
    background: var(--panel-2);
    border-color: var(--border);
    color: var(--text);
  }

  .bar-icon-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 26px;
    height: 26px;
    border-radius: 5px;
    border: none;
    background: transparent;
    color: var(--muted);
    cursor: pointer;
    flex-shrink: 0;
    transition: all 0.1s;
  }
  .bar-icon-btn:hover {
    background: var(--panel-2);
    color: var(--text);
  }

  /* Content row: filter sidebar fills full height, main area pushed below command bar */
  .content-zone {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    display: flex;
  }

  .main-area {
    flex: 1;
    overflow: hidden;
    position: relative;
    padding-top: 64px;
  }

  /* On a wide screen the drawer button is pointless — the column is always there. */
  .filters-toggle {
    display: none;
  }

  @media (max-width: 820px) {
    .filters-toggle {
      display: block;
      position: absolute;
      left: 8px;
      top: 68px;
      z-index: 30;
      width: 36px;
      height: 36px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--panel);
      color: var(--text);
      font-size: 16px;
      line-height: 1;
      cursor: pointer;
    }

    /* Filters float above the canvas instead of taking a column from it. */
    .content-zone > :global(.filter-panel) {
      position: absolute;
      top: 0;
      bottom: 0;
      left: 0;
      z-index: 25;
      transform: translateX(-102%);
      transition: transform 0.16s ease-out;
      box-shadow: 0 0 24px rgba(1, 4, 9, 0.6);
    }
    .content-zone.filters-open > :global(.filter-panel) {
      transform: translateX(0);
    }

    /* Same for the note panel: on a phone it is a sheet, not a third column. */
    .content-zone > :global(.detail-panel) {
      position: absolute;
      top: 56px;
      bottom: 0;
      left: 0;
      right: 0;
      z-index: 26;
      /* `!important`, bo panel niesie szerokość w atrybucie style (suwak szerokości). */
      width: auto !important;
      max-width: none;
    }
  }
</style>
