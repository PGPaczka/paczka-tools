<script lang="ts">
  import type { ProvenanceNode } from '../../domain/graph/provenanceTree'
  import CopyButton from './CopyButton.svelte'

  export let node: ProvenanceNode
  /** The package name is the one thing here that is not a directory, so it reads differently. */
  export let isPackage = false
  /** Last sibling: its guide line stops at the elbow instead of running past it. */
  export let isLast = false
</script>

<div class="branch" class:nested={!isPackage} class:tail={isLast}>
  <div class="row" class:package={isPackage}>
    <span class="label" title={node.fullPath ?? node.label}>{node.label}</span>
    {#if node.fullPath}
      <CopyButton value={node.fullPath} label="Copy source path" />
    {/if}
  </div>

  {#if node.children.length > 0}
    <div class="children">
      {#each node.children as child, i (child.label)}
        <svelte:self node={child} isLast={i === node.children.length - 1} />
      {/each}
    </div>
  {/if}
</div>

<style>
  .branch { position: relative; }

  /* Zamiast pojedynczego „└" na wiersz: każdy potomek rysuje własny odcinek pionowego
     prowadnika, więc ułożone jeden pod drugim dają ciągłą linię, a ostatni urywa ją na
     łokciu. Znak w tekście gubił się przy zawijaniu długich ścieżek (2026-09-30). */
  .nested { padding-left: 15px; }
  .nested::before {
    content: '';
    position: absolute;
    left: 3px;
    top: 0;
    bottom: 0;
    width: 1px;
    background: var(--border-3);
  }
  .nested.tail::before { bottom: auto; height: 11px; }
  .nested::after {
    content: '';
    position: absolute;
    left: 3px;
    top: 11px;
    width: 9px;
    height: 1px;
    background: var(--border-3);
  }

  .row {
    display: flex;
    /* Przy zawiniętej ścieżce guzik kopiowania wisiał na środku bloku, daleko od łokcia
       drzewa, do którego należy — trzyma się więc pierwszej linijki. */
    align-items: flex-start;
    gap: 5px;
    min-height: 22px;
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--muted);
    overflow-wrap: anywhere;
  }
  .row:hover { color: var(--text); }

  /* Paczka źródłowa to inne pytanie niż katalog, więc i inna waga. */
  .package {
    font-family: var(--font-ui);
    font-size: 12px;
    color: var(--text);
    margin-top: 8px;
  }

  .label { min-width: 0; }
</style>
