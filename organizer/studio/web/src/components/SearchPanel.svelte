<script lang="ts">
  import { searchItems, previewImageUrl, type Item } from '../lib/api';
  import { bytes, percent } from '../lib/format';
  import Lightbox from './Lightbox.svelte';

  interface Props {
    /** Otwórz przedmiot znalezionej pozycji (powrót do zwykłej pracy). */
    onOpenSubject?: (semester: number, skrot: string) => void;
  }

  let { onOpenSubject }: Props = $props();

  let query = $state('');
  let items = $state<Item[]>([]);
  let total = $state(0);
  let loading = $state(false);
  let error = $state<string | null>(null);
  let searched = $state(false);
  let zoomed = $state<Item | null>(null);
  let box: HTMLInputElement | undefined = $state();

  const SHOWABLE = new Set(['image', 'pdf']);
  const showsPicture = (kind: string | null | undefined) => SHOWABLE.has(String(kind ?? ''));

  /** Szukamy dopiero po chwili bez pisania: przy 19 tysiącach treści zapytanie
   *  na każdą literę obciąża bazę bez pożytku dla człowieka. */
  let timer: ReturnType<typeof setTimeout> | null = null;

  function schedule(): void {
    if (timer) clearTimeout(timer);
    if (query.trim().length < 2) {
      items = [];
      total = 0;
      searched = false;
      return;
    }
    timer = setTimeout(run, 350);
  }

  async function run(): Promise<void> {
    const q = query.trim();
    if (q.length < 2) return;
    loading = true;
    error = null;
    try {
      const page = await searchItems(q, 60);
      items = page.items;
      total = page.total;
      searched = true;
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc);
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    box?.focus();
  });
</script>

<section class="search-panel">
  <header>
    <input
      bind:this={box}
      bind:value={query}
      oninput={schedule}
      onkeydown={(e) => e.key === 'Enter' && run()}
      type="search"
      placeholder="Szukaj w całej paczce: nazwa, ścieżka, kategoria, sha…"
      aria-label="Szukaj treści"
    />
    {#if searched}
      <span class="dim num">{total} trafień{total > items.length ? ` (pokazuję ${items.length})` : ''}</span>
    {/if}
  </header>

  {#if error}
    <p class="error">{error}</p>
  {:else if loading}
    <p class="hint">Szukam…</p>
  {:else if !searched}
    <p class="hint">
      Wpisz co najmniej dwa znaki. Szukanie idzie po całym indeksie, nie tylko po
      wybranym przedmiocie — od tego jest ta zakładka.
    </p>
  {:else if items.length === 0}
    <p class="hint">Nic nie pasuje do „{query}”.</p>
  {:else}
    <ul>
      {#each items as item (item.sha256)}
        <li>
          {#if showsPicture(item.content_kind)}
            <button class="thumb" title="Pokaż na cały ekran" onclick={() => (zoomed = item)}>
              <img loading="lazy" src={previewImageUrl(item.sha256, 1, 160)} alt="" />
            </button>
          {:else}
            <span class="thumb placeholder">{item.content_kind ?? '?'}</span>
          {/if}

          <div class="meta">
            <div class="line">
              <span class="name">{item.filename ?? item.sha256.slice(0, 16)}</span>
              {#if item.subject_key}
                <span class="tag">SEM{item.semester} {item.subject_key}</span>
              {/if}
              {#if item.category}<span class="tag">{item.category}</span>{/if}
              {#if item.action}<span class="tag {item.action}">{item.action}</span>{/if}
              <span class="dim num">{percent(item.confidence)} · {bytes(item.size_bytes)}</span>
            </div>
            <div class="mono dim path">{item.source_package}/{item.source_relative_path}</div>
          </div>

          {#if item.semester && item.subject_key}
            <button
              class="open"
              onclick={() => onOpenSubject?.(item.semester!, item.subject_key!)}
              title="Otwórz przedmiot tej treści"
            >otwórz</button>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
</section>

{#if zoomed}
  <Lightbox
    src={previewImageUrl(zoomed.sha256, 1, 1800)}
    alt={zoomed.filename ?? zoomed.sha256}
    caption={`${zoomed.source_package}/${zoomed.source_relative_path}`}
    onClose={() => (zoomed = null)}
  />
{/if}

<style>
  .search-panel {
    display: flex;
    flex-direction: column;
    gap: 10px;
    min-height: 0;
    padding: 12px 14px 20px;
    overflow-y: auto;
  }
  header {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  input {
    flex: 1;
    padding: 7px 12px;
    border: 1px solid var(--border);
    border-radius: 7px;
    background: var(--panel);
  }
  input:focus {
    outline: none;
    border-color: var(--accent-dim);
  }

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  li {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 8px;
    border: 1px solid var(--border-2);
    border-radius: 7px;
    background: var(--panel);
  }
  .thumb {
    width: 64px;
    height: 48px;
    flex: none;
    padding: 0;
    border-radius: 4px;
    overflow: hidden;
    background: var(--bg-deep);
    cursor: zoom-in;
  }
  .thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .thumb.placeholder {
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--muted-2);
    font-size: 10px;
    cursor: default;
  }
  .meta {
    flex: 1;
    min-width: 0;
  }
  .line {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .name {
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 22rem;
  }
  .path {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 11px;
  }
  .open {
    flex: none;
    padding: 3px 12px;
    border: 1px solid var(--border);
    border-radius: 999px;
    color: var(--muted);
  }
  .open:hover {
    color: var(--text);
    border-color: var(--accent-dim);
  }
  .dim {
    color: var(--muted-2);
  }
  .hint {
    margin: 12px 2px;
    color: var(--muted);
    max-width: 40rem;
  }
  .error {
    margin: 12px 0;
    padding: 8px 10px;
    border: 1px solid rgba(248, 81, 73, 0.4);
    border-radius: 7px;
    color: var(--red);
  }
</style>
