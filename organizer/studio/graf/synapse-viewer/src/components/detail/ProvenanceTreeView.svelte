<script lang="ts">
  import { buildProvenanceTree } from '../../domain/graph/provenanceTree'
  import type { ProvenanceCopy } from '../../domain/graph/GraphModel'
  import ProvenanceBranch from './ProvenanceBranch.svelte'

  export let copies: ProvenanceCopy[]
  export let total: number

  $: tree = buildProvenanceTree(copies, total)
</script>

<section class="prov">
  <h3>
    Prowenancja
    <span class="count">{tree.total} {tree.total === 1 ? 'kopia' : 'kopii'}</span>
  </h3>

  {#if tree.commonName}
    <!-- 92% treści ma tę samą nazwę we wszystkich kopiach — raz na górze, nie w każdym wierszu. -->
    <p class="common">wszystkie jako <code>{tree.commonName}</code></p>
  {/if}

  <ul class="roots">
    {#each tree.roots as root (root.label)}
      <li>
        <ProvenanceBranch node={root} depth={0} isPackage={true} />
      </li>
    {/each}
  </ul>

  {#if tree.hidden > 0}
    <p class="hidden-note">i jeszcze {tree.hidden} — pełna lista w studiu</p>
  {/if}
</section>

<style>
  .prov { margin: 0 0 14px; }

  h3 {
    display: flex;
    align-items: baseline;
    gap: 8px;
    margin: 0 0 6px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--muted-2);
  }
  .count { text-transform: none; letter-spacing: 0; font-weight: 400; }

  .common {
    margin: 0 0 8px;
    font-size: 11.5px;
    color: var(--muted);
  }
  .common code {
    font-family: var(--font-mono);
    font-size: 0.95em;
    color: var(--text);
    overflow-wrap: anywhere;
  }

  .roots { list-style: none; margin: 0; padding: 0; }

  .hidden-note {
    margin: 6px 0 0;
    font-size: 11.5px;
    color: var(--muted-2);
    font-style: italic;
  }
</style>
