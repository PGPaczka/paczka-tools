<script lang="ts">
  import { onMount } from 'svelte'
  import type { FileInfo } from '../../domain/graph/GraphModel'
  import { humanSize } from '../../domain/format/size'

  export let preview: NonNullable<FileInfo['preview']>
  export let contentKind: string | undefined = undefined
  export let sizeBytes: number | undefined = undefined

  let page = 1
  $: pages = preview.pages ?? 1
  $: imageUrl = preview.imageUrl
    ? preview.imageUrl + (pages > 1 ? `&page=${page}` : '')
    : undefined
  // A new note must not keep the previous one's page number.
  $: if (preview) page = 1

  let failed = false
  $: if (imageUrl) failed = false

  // highlight.js is a quarter of the bundle, so it arrives only when there is code to
  // colour — and never at all for a vault whose notes are pictures.
  let highlighted: string | null = null
  let mounted = false
  onMount(() => (mounted = true))

  $: if (mounted && preview.kind === 'text' && preview.language && preview.text) {
    void colour(preview.text, preview.language)
  } else {
    highlighted = null
  }

  async function colour(text: string, language: string) {
    try {
      const hljs = (await import('highlight.js/lib/common')).default
      highlighted = hljs.getLanguage(language)
        ? hljs.highlight(text, { language, ignoreIllegals: true }).value
        : null
    } catch {
      highlighted = null
    }
  }

  const MISSING_REASON: Record<string, string> = {
    format: 'tego formatu nie umiemy pokazać',
    'no-copy': 'żadna kopia nie leży dziś na dysku',
  }
</script>

<div class="preview">
  {#if (preview.kind === 'image' || preview.kind === 'page') && imageUrl && !failed}
    <img src={imageUrl} alt="" loading="lazy" on:error={() => (failed = true)} />
    {#if pages > 1}
      <div class="pager">
        <button on:click={() => (page = Math.max(1, page - 1))} disabled={page === 1}>←</button>
        <span>strona {page} z {pages}</span>
        <button on:click={() => (page = Math.min(pages, page + 1))} disabled={page === pages}>→</button>
      </div>
    {/if}
  {:else if preview.kind === 'text' && preview.text}
    <pre class="text"><code>{#if highlighted}{@html highlighted}{:else}{preview.text}{/if}</code></pre>
    {#if preview.truncated}
      <p class="note">… to tylko początek pliku</p>
    {/if}
  {:else if preview.kind === 'listing' && preview.entries}
    <p class="note">Archiwum · {preview.entriesTotal} plików</p>
    <ul class="entries">
      {#each preview.entries as entry}
        <li title={entry}>{entry}</li>
      {/each}
    </ul>
    {#if preview.truncated}
      <p class="note">…</p>
    {/if}
  {:else}
    <!-- Uczciwa kafelka: mówi, czym plik jest i DLACZEGO nie ma podglądu. Dwie przyczyny
         są różne — formatu nie umiemy pokazać albo nie mamy kopii na dysku. -->
    <div class="tile">
      <span class="tile-kind">{contentKind ?? 'plik'}</span>
      <span class="tile-why">
        {failed ? 'podglądu nie udało się wczytać' : MISSING_REASON[preview.missing ?? ''] ?? 'bez podglądu'}
        {#if humanSize(sizeBytes)} · {humanSize(sizeBytes)}{/if}
      </span>
    </div>
  {/if}
</div>

<style>
  .preview { margin: 0 0 12px; }

  img {
    display: block;
    max-width: 100%;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--bg-deep);
  }

  .pager {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 6px;
    font-size: 11.5px;
    color: var(--muted-2);
  }
  .pager button {
    border: 1px solid var(--border);
    background: var(--panel-2);
    color: var(--text);
    border-radius: 4px;
    cursor: pointer;
    padding: 1px 7px;
  }
  .pager button:disabled { opacity: 0.4; cursor: default; }

  .text {
    margin: 0;
    padding: 9px 11px;
    max-height: 190px;
    overflow: auto;
    background: var(--bg-deep);
    border: 1px solid var(--border);
    border-radius: 6px;
    font-family: var(--font-mono);
    font-size: 11px;
    line-height: 1.5;
    color: var(--text);
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  .entries {
    margin: 0;
    padding: 6px 11px 6px 26px;
    max-height: 170px;
    overflow: auto;
    background: var(--bg-deep);
    border: 1px solid var(--border);
    border-radius: 6px;
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--muted);
  }
  .entries li { overflow-wrap: anywhere; }

  .note {
    margin: 5px 0 0;
    font-size: 11px;
    color: var(--muted-2);
    font-style: italic;
  }

  .tile {
    display: flex;
    flex-direction: column;
    gap: 3px;
    padding: 14px;
    border: 1px dashed var(--border-2);
    border-radius: 6px;
    background: var(--panel-2);
  }
  .tile-kind {
    font-family: var(--font-mono);
    font-size: 13px;
    color: var(--text);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  .tile-why { font-size: 11.5px; color: var(--muted-2); }
</style>
