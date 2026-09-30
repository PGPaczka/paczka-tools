<script lang="ts">
  import type { ProvenanceNode } from '../../domain/graph/provenanceTree'
  import CopyButton from './CopyButton.svelte'

  export let node: ProvenanceNode
  /** The package name is the one thing here that is not a directory, so it reads differently. */
  export let isPackage = false
  export let depth = 0
</script>

<div class="row" class:package={isPackage} style="padding-left:{depth * 12}px">
  {#if !isPackage}<span class="tick">└</span>{/if}
  <span class="label" title={node.fullPath ?? node.label}>{node.label}</span>
  {#if node.fullPath}
    <CopyButton value={node.fullPath} label="Copy source path" />
  {/if}
</div>

{#if node.children.length > 0}
  <div class="children">
    {#each node.children as child (child.label)}
      <svelte:self node={child} depth={depth + 1} />
    {/each}
  </div>
{/if}

<style>
  .row {
    display: flex;
    align-items: center;
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
    margin-top: 4px;
  }

  .tick { color: var(--border-2); flex-shrink: 0; }
  .label { min-width: 0; }
</style>
