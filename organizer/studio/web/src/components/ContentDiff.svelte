<script lang="ts">
  /**
   * Porównanie dwóch treści. Backend (`/api/clusters/diff`) nigdy nie wymagał, żeby
   * należały do jednego klastra — ograniczał to wyłącznie widok. Komponent jest więc
   * wspólny dla klastrów i dla zestawiania dowolnych dwóch pozycji.
   *
   * Obie strony rysuje jedna pętla: wcześniej był to ten sam kod wklejony dwa razy,
   * przez co poprawka trafiała raz w lewą, raz w obie.
   */
  import { previewImageUrl, type ClusterDiff, type Item } from '../lib/api';
  import { bytes, percent } from '../lib/format';

  interface Props {
    diff: ClusterDiff | null;
    loading?: boolean;
    onClose?: () => void;
    onZoom?: (sha256: string, name: string) => void;
  }

  let { diff, loading = false, onClose, onZoom }: Props = $props();

  /** Treści, dla których podgląd zwraca obrazek (PDF renderuje pierwszą stronę). */
  const SHOWABLE = new Set(['image', 'pdf']);
  const showsPicture = (kind: string | null | undefined) => SHOWABLE.has(String(kind ?? ''));

  const sides = $derived<Array<{ item: Item; text: string | null }>>(
    diff ? [
      { item: diff.left, text: diff.left_text },
      { item: diff.right, text: diff.right_text },
    ] : [],
  );
</script>

{#if loading}
  <div class="diff-panel"><div class="empty">Wczytuję porównanie…</div></div>
{:else if diff}
  <div class="diff-panel">
    <div class="diff-header">
      <span class="tag">{diff.diff_type === 'text' ? 'diff tekstu' : 'porównanie metadanych'}</span>
      {#if diff.relation}
        <span class="dim">{diff.relation.reason}</span>
      {/if}
      {#if onClose}
        <button class="close-diff" onclick={onClose}>zamknij</button>
      {/if}
    </div>

    <div class="diff-sides">
      {#each sides as side (side.item.sha256)}
        <div class="diff-side">
          <div class="diff-side-header">
            <span class="mono">{side.item.sha256.slice(0, 12)}…</span>
            {#if side.item.filename}
              <span class="diff-filename">{side.item.filename}</span>
            {/if}
          </div>

          {#if showsPicture(side.item.content_kind)}
            <button
              class="picture-btn"
              title="Pokaż na cały ekran"
              onclick={() => onZoom?.(side.item.sha256, side.item.filename ?? side.item.sha256)}
            >
              <img
                class="diff-picture"
                src={previewImageUrl(side.item.sha256, 1, 700)}
                alt="Podgląd: {side.item.filename ?? ''}"
              />
            </button>
          {/if}

          <div class="diff-meta">
            {#if side.item.content_kind}<span class="tag">{side.item.content_kind}</span>{/if}
            {#if side.item.size_bytes}<span class="dim">{bytes(side.item.size_bytes)}</span>{/if}
            {#if side.item.category}<span>kat: {side.item.category}</span>{/if}
            {#if side.item.action}<span>→ {side.item.action}</span>{/if}
            {#if side.item.confidence !== null && side.item.confidence !== undefined}
              <span class="num">{percent(side.item.confidence)}</span>
            {/if}
          </div>

          {#if side.item.target_relative_path}
            <div class="mono dim diff-target" title={side.item.target_relative_path}>
              → {side.item.target_relative_path}
            </div>
          {/if}

          {#if side.text}
            <pre class="diff-text">{side.text}</pre>
          {:else}
            <div class="no-text dim">brak wyekstrahowanego tekstu</div>
          {/if}
        </div>
      {/each}
    </div>
  </div>
{/if}

<style>
  .diff-panel {
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px;
    background: var(--bg);
  }
  .diff-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 10px;
  }
  .close-diff {
    margin-left: auto;
    padding: 2px 8px;
    border: 1px solid var(--border);
    border-radius: 3px;
    font-size: 10px;
    background: transparent;
    color: var(--muted);
    cursor: pointer;
  }
  .close-diff:hover {
    color: var(--text);
  }
  .diff-sides {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }
  /* Na telefonie dwie kolumny znaczą dwa nieczytelne paski. Porównanie ma sens
     również jedno pod drugim — przewinięcie jest tańsze niż zgadywanie z 15 znaków. */
  @media (max-width: 700px) {
    .diff-sides {
      grid-template-columns: 1fr;
    }
  }
  .diff-side {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }
  .diff-side-header {
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
    font-size: 11px;
  }
  /* Nazwy w tej paczce bywają bardzo długie („…_2015_cz2_ODP.docx(1).docx”) i bez
     przycięcia wychodziły poza swoją kolumnę, nachodząc na drugą stronę diffa. */
  .diff-filename {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 600;
    font-size: 12px;
  }
  .picture-btn {
    display: block;
    width: 100%;
    padding: 0;
    border: none;
    background: none;
    cursor: zoom-in;
  }
  /* Porównanie dwóch obrazów: `contain`, bo tu liczy się CAŁY kadr, nie ładne kafelki. */
  .diff-picture {
    width: 100%;
    max-height: 40vh;
    object-fit: contain;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg-deep);
  }
  .diff-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    font-size: 11px;
  }
  .diff-target {
    font-size: 10px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .diff-text {
    margin: 0;
    padding: 8px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg-deep);
    font-size: 11px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 300px;
    overflow-y: auto;
  }
  .no-text {
    font-size: 11px;
    font-style: italic;
  }
  .empty {
    padding: 12px;
    text-align: center;
    font-size: 11px;
    color: var(--muted);
  }
</style>
