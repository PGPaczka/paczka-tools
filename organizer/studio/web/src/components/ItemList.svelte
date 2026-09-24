<script lang="ts">
  import type { Item, ItemsPage } from '../lib/api';
  import { bytes, count, dirname, percent, basename } from '../lib/format';

  let {
    page,
    loading,
    onMore,
    compared = [],
    onCompare,
  }: {
    page: ItemsPage | null;
    loading: boolean;
    onMore: () => void;
    /** sha treści odłożonych do porównania — podświetlamy je na liście. */
    compared?: string[];
    onCompare?: (sha256: string) => void;
  } = $props();

  const shown = $derived(page ? page.items.length : 0);
  const remaining = $derived(page ? Math.max(page.total - shown, 0) : 0);

  /** Nazwa pozycji: plik źródłowy, a gdy go brak — sama treść po sha. */
  function title(item: Item): string {
    return item.filename ?? basename(item.source_relative_path) ?? item.sha256.slice(0, 12);
  }
</script>

<div class="items">
  {#if page && page.items.length === 0 && !loading}
    <p class="empty">Żadna pozycja nie pasuje do tych filtrów.</p>
  {/if}

  {#each page?.items ?? [] as item (item.sha256)}
    <article class:compared={compared.includes(item.sha256)}>
      <div class="top">
        <span class="name" title={item.source_relative_path ?? item.sha256}>{title(item)}</span>
        {#if onCompare}
          <button
            class="compare-btn"
            class:on={compared.includes(item.sha256)}
            title="Zestaw tę treść z inną"
            onclick={() => onCompare(item.sha256)}
          >
            {compared.includes(item.sha256) ? 'odłożone' : 'porównaj'}
          </button>
        {/if}
        {#if item.action}<span class="tag {item.action}">{item.action}</span>{/if}
        {#if item.needs_review}<span class="tag review">do obejrzenia</span>{/if}
        <span class="tag {item.confidence_bucket} num">{percent(item.confidence)}</span>
      </div>

      <div class="where mono">
        <span class="dim">{item.source_package}/{dirname(item.source_relative_path)}</span>
      </div>

      {#if item.target_relative_path}
        <div class="where mono target" title={item.target_relative_path}>
          → {item.target_relative_path}
        </div>
      {/if}

      <div class="facts">
        <span>{item.content_kind ?? '—'}</span>
        <span class="num">{bytes(item.size_bytes)}</span>
        {#if item.copies > 1}<span class="num">{count(item.copies)} kopie</span>{/if}
        {#if item.category}<span>{item.category}</span>{/if}
        {#if item.classification_method}<span class="dim">{item.classification_method}</span>{/if}
        {#if !item.has_text}<span class="dim">bez tekstu</span>{/if}
      </div>

      {#if item.reason}
        <p class="reason">{item.reason}</p>
      {/if}
    </article>
  {/each}

  {#if loading}
    <p class="empty">Wczytuję…</p>
  {:else if remaining > 0}
    <button class="more" onclick={onMore}>Pokaż więcej ({count(remaining)})</button>
  {/if}
</div>

<style>
  article.compared {
    border-color: var(--accent-dim);
  }
  .compare-btn {
    padding: 1px 8px;
    border: 1px solid var(--border);
    border-radius: 999px;
    background: transparent;
    color: var(--muted);
    font-size: 10px;
    cursor: pointer;
  }
  .compare-btn:hover {
    color: var(--text);
    border-color: var(--accent-dim);
  }
  .compare-btn.on {
    border-color: var(--accent-dim);
    color: var(--text);
  }

  .items {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  article {
    display: flex;
    flex-direction: column;
    gap: 3px;
    padding: 8px 10px;
    border: 1px solid var(--border-2);
    border-radius: 7px;
    background: var(--panel);
  }

  .top {
    display: flex;
    align-items: center;
    gap: 7px;
    min-width: 0;
  }
  .name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .where {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--muted-2);
  }
  .where.target {
    color: var(--accent);
    opacity: 0.85;
  }

  .facts {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    font-size: 11px;
    color: var(--muted);
  }
  .dim {
    color: var(--muted-2);
  }

  .reason {
    margin: 2px 0 0;
    font-size: 11px;
    color: var(--muted);
    border-left: 2px solid var(--border);
    padding-left: 7px;
  }

  .more {
    align-self: center;
    margin: 4px 0 2px;
    padding: 4px 14px;
    border: 1px solid var(--border);
    border-radius: 999px;
    color: var(--muted);
  }
  .more:hover {
    color: var(--text);
    border-color: var(--accent-dim);
  }

  .empty {
    margin: 10px 0;
    text-align: center;
    color: var(--muted-2);
  }
</style>
