<script lang="ts">
  import { settings } from '../../stores/settingsStore'
  import { fitTrigger } from '../../stores/graphControlsStore'
  import Minimap from './Minimap.svelte'
  import GraphLegend from './GraphLegend.svelte'

  $: minimapOn = $settings.minimapOn

  function handleFit() {
    fitTrigger.update((n) => n + 1)
  }
</script>

{#if minimapOn}
  <Minimap />
{/if}

<!-- Legend sits bottom-left, opposite the minimap: without it an edge's kind is a
     colour nobody can decode. -->
<GraphLegend />

<!-- Fit-to-graph button — positioned above minimap when it's visible -->
<button
  class="fit-btn"
  style:bottom={minimapOn ? '140px' : '12px'}
  on:click={handleFit}
  title="Fit all nodes to screen"
  aria-label="Fit all nodes to screen"
>
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path d="M1 5V2a1 1 0 0 1 1-1h3M11 1h3a1 1 0 0 1 1 1v3M15 11v3a1 1 0 0 1-1 1h-3M5 15H2a1 1 0 0 1-1-1v-3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="8" cy="8" r="2" stroke="currentColor" stroke-width="1.3"/>
  </svg>
</button>

<style>
  .fit-btn {
    position: absolute;
    right: 12px;
    width: 30px;
    height: 30px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--panel);
    color: var(--muted);
    cursor: pointer;
    z-index: 20;
    box-shadow: 0 2px 6px var(--shadow);
    transition: background 0.12s, color 0.12s, border-color 0.12s;
  }

  .fit-btn:hover {
    background: var(--panel-2);
    color: var(--text);
    border-color: var(--border-2);
  }

  .fit-btn:active {
    background: var(--panel-3);
  }
</style>
