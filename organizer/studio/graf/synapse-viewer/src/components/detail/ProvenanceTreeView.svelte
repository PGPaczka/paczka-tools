<script lang="ts">
  import { buildProvenanceTree } from '../../domain/graph/provenanceTree'
  import type { ProvenanceCopy } from '../../domain/graph/GraphModel'
  import ProvenanceBranch from './ProvenanceBranch.svelte'
  import SectionHeading from './SectionHeading.svelte'

  export let copies: ProvenanceCopy[]
  export let total: number

  $: tree = buildProvenanceTree(copies, total)
</script>

<SectionHeading
  title="Prowenancja"
  note="{tree.total} {tree.total === 1 ? 'kopia' : 'kopii'}"
/>

{#if tree.commonName}
  <!-- 92% treści ma tę samą nazwę we wszystkich kopiach — raz na górze, nie w każdym wierszu. -->
  <p class="common">wszystkie jako <code>{tree.commonName}</code></p>
{/if}

<ul class="roots">
  {#each tree.roots as root (root.label)}
    <li>
      <ProvenanceBranch node={root} isPackage={true} />
    </li>
  {/each}
</ul>

{#if tree.hidden > 0}
  <p class="hidden-note">i jeszcze {tree.hidden} — pełna lista w studiu</p>
{/if}

<style>
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
  /* Pierwsza paczka nie potrzebuje odstępu, który oddziela kolejne od poprzedniej. */
  .roots > li:first-child :global(.package) { margin-top: 0; }

  .hidden-note {
    margin: 6px 0 0;
    font-size: 11.5px;
    color: var(--muted-2);
    font-style: italic;
  }
</style>
