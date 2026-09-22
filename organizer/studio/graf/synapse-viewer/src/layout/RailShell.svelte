<script lang="ts">
  import { createEventDispatcher } from 'svelte'

  export let view: 'graph' | 'cards' | 'dash' | 'venn' = 'graph'
  export let vaultName: string = 'Synapse'

  const dispatch = createEventDispatcher<{
    switchView: 'graph' | 'cards' | 'dash' | 'venn'
    openSettings: void
    openPalette: void
  }>()

  const ICONS = {
    graph: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 16 16" fill="none">
      <circle cx="3" cy="8" r="2" fill="currentColor"/>
      <circle cx="13" cy="3" r="2" fill="currentColor"/>
      <circle cx="13" cy="13" r="2" fill="currentColor"/>
      <line x1="5" y1="7.2" x2="11" y2="4" stroke="currentColor" stroke-width="1.5"/>
      <line x1="5" y1="8.8" x2="11" y2="12" stroke="currentColor" stroke-width="1.5"/>
    </svg>`,
    cards: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 16 16" fill="currentColor">
      <rect x="1" y="1" width="6" height="6" rx="1"/>
      <rect x="9" y="1" width="6" height="6" rx="1"/>
      <rect x="1" y="9" width="6" height="6" rx="1"/>
      <rect x="9" y="9" width="6" height="6" rx="1"/>
    </svg>`,
    dash: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 16 16" fill="currentColor">
      <rect x="1" y="1" width="14" height="4" rx="1"/>
      <rect x="1" y="7" width="6" height="8" rx="1"/>
      <rect x="9" y="7" width="6" height="8" rx="1"/>
    </svg>`,
    venn: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 18 18" fill="currentColor">
      <circle cx="6.5" cy="9" r="5" fill-opacity=".55"/>
      <circle cx="11.5" cy="9" r="5" fill-opacity=".55"/>
    </svg>`,
    search: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8">
      <circle cx="7" cy="7" r="5"/>
      <line x1="11" y1="11" x2="15" y2="15"/>
    </svg>`,
    settings: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 16 16" fill="currentColor">
      <path d="M6.5 1h3l.45 1.8a5.2 5.2 0 011.3.75l1.75-.6 1.5 2.6-1.4 1.1a5.2 5.2 0 010 1.7l1.4 1.1-1.5 2.6-1.75-.6a5.2 5.2 0 01-1.3.75L9.5 14h-3l-.45-1.75A5.2 5.2 0 014.75 11.5l-1.75.6-1.5-2.6 1.4-1.1a5.2 5.2 0 010-1.7L1.5 5.55l1.5-2.6 1.75.6A5.2 5.2 0 016.05 2.8L6.5 1zm1.5 9a2 2 0 100-4 2 2 0 000 4z"/>
    </svg>`,
  }

  const views: Array<{ id: 'graph' | 'cards' | 'dash' | 'venn'; icon: string; label: string }> = [
    { id: 'graph', icon: ICONS.graph, label: 'Graph' },
    { id: 'venn', icon: ICONS.venn, label: 'Venn' },
    { id: 'cards', icon: ICONS.cards, label: 'Cards' },
    { id: 'dash', icon: ICONS.dash, label: 'Dashboard' },
  ]
</script>

<div class="rail-shell">
  <!-- Left rail -->
  <nav class="rail" aria-label="Navigation rail">
    <!-- Logo -->
    <div class="rail-logo" title={vaultName}>
      <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 20 20">
        <defs>
          <radialGradient id="lg-rail" cx="40%" cy="35%">
            <stop offset="0%" stop-color="#58a6ff"/>
            <stop offset="100%" stop-color="#1f6feb"/>
          </radialGradient>
        </defs>
        <circle cx="10" cy="10" r="9" fill="url(#lg-rail)"/>
        <circle cx="10" cy="10" r="2.5" fill="white" fill-opacity=".9"/>
        <line x1="10" y1="4" x2="10" y2="7" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
        <line x1="10" y1="13" x2="10" y2="16" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
        <line x1="4" y1="10" x2="7" y2="10" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
        <line x1="13" y1="10" x2="16" y2="10" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
    </div>

    <!-- Search -->
    <button class="rail-btn" title="Search (⌘K)" on:click={() => dispatch('openPalette')}>
      {@html ICONS.search}
    </button>

    <div class="rail-divider"></div>

    <!-- View buttons -->
    {#each views as v}
      <button
        class="rail-btn"
        class:active={view === v.id}
        title={v.label}
        on:click={() => dispatch('switchView', v.id)}
      >
        {@html v.icon}
      </button>
    {/each}

    <div class="rail-spacer"></div>

    <div class="rail-divider"></div>

    <!-- Settings -->
    <button class="rail-btn" title="Settings" on:click={() => dispatch('openSettings')}>
      {@html ICONS.settings}
    </button>
  </nav>

  <!-- Content area -->
  <div class="rail-content">
    <!-- Filter sidebar -->
    <slot name="filters" />

    <!-- Main area -->
    <main class="main-area">
      <slot name="main" />
    </main>

    <!-- Detail panel -->
    <slot name="detail" />
  </div>
</div>

<style>
  .rail-shell {
    width: 100vw;
    height: 100vh;
    display: flex;
    background: var(--bg);
    overflow: hidden;
  }

  .rail {
    width: 54px;
    flex-shrink: 0;
    background: var(--panel);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 8px 0;
    gap: 2px;
    z-index: 10;
  }

  .rail-logo {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    margin-bottom: 4px;
  }

  .rail-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 34px;
    border-radius: 6px;
    border: none;
    background: transparent;
    color: var(--muted);
    cursor: pointer;
    transition: all 0.1s;
  }
  .rail-btn:hover {
    background: var(--panel-2);
    color: var(--text);
  }
  .rail-btn.active {
    background: rgba(88, 166, 255, 0.1);
    color: var(--accent);
  }

  .rail-divider {
    width: 28px;
    height: 1px;
    background: var(--border-2);
    margin: 4px 0;
  }

  .rail-spacer {
    flex: 1;
  }

  .rail-content {
    flex: 1;
    display: flex;
    overflow: hidden;
  }

  .main-area {
    flex: 1;
    overflow: hidden;
    position: relative;
  }
</style>
