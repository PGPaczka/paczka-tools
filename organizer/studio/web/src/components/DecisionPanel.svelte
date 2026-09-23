<script lang="ts">
  import TextPreview from './TextPreview.svelte';
  import Lightbox from './Lightbox.svelte';
  import {
    postDecision,
    postUndo,
    postDecisionBatch,
    getItems,
    getPreview,
    getItemsByFolder,
    postDecisionByFolder,
    previewImageUrl,
    type Item,
    type ItemsPage,
    type DecisionRequest,
    type Preview,
  } from '../lib/api';
  import { basename, bytes, percent, dirname } from '../lib/format';

  const CATEGORIES = [
    'egzamin', 'kolokwia', 'laboratoria', 'cwiczenia', 'projekt',
    'seminarium', 'wyklad', 'opracowania', 'inne',
  ] as const;

  interface Props {
    semester?: number | null;
    skrot?: string | null;
    onDecided?: () => void;
  }

  let { semester = null, skrot = null, onDecided }: Props = $props();

  let current = $state<Item | null>(null);
  let remaining = $state(0);
  let loading = $state(false);
  let error = $state<string | null>(null);
  let success = $state<string | null>(null);
  let history = $state<string[]>([]);
  let showHelp = $state(false);

  // Podgląd: bez niego decyzja zapada po samej nazwie pliku, czyli dokładnie tak,
  // jak w konsoli — a po to studio nie powstało (PLAN.md: „podgląd po lewej,
  // propozycja po prawej").
  /** Podgląd na cały ekran — miniatura mówi „co to”, pełny ekran mówi „czym się różni”. */
  let zoomed = $state(false);

  /** Decyzja hurtem po katalogu (S1.6): najpierw pokaż, czego dotknie, potem zapisz. */
  let bulk = $state<{ folder: string; total: number; names: string[] } | null>(null);
  let bulkBusy = $state(false);

  /** Zmiana ścieżki docelowej (klawisz `t`) — bez niej jedyną drogą byłoby
   *  „przenieś tu” w zakładce plan, czyli wyjście z kolejki. */
  let editingTarget = $state(false);
  let targetDraft = $state('');

  let preview = $state<Preview | null>(null);
  let previewError = $state<string | null>(null);
  let page = $state(1);

  /** Szerokość renderu dopasowana do ekranu: tablet nie potrzebuje wersji jak monitor,
   *  a przez sieć każdy zbędny piksel to czekanie. Sufit 1200 px, bo wyżej i tak
   *  nie widać różnicy na podglądzie. */
  function previewWidth(): number {
    const css = typeof window === 'undefined' ? 1000 : window.innerWidth;
    const dpr = typeof window === 'undefined' ? 1 : Math.min(window.devicePixelRatio || 1, 2);
    return Math.max(480, Math.min(1200, Math.round(css * 0.55 * dpr)));
  }

  const imageUrl = $derived(
    current && preview?.has_image ? previewImageUrl(current.sha256, page, previewWidth()) : null,
  );

  async function loadNext(): Promise<void> {
    loading = true;
    error = null;
    try {
      const filters: Record<string, unknown> = { needs_review: true, limit: 1 };
      if (semester) filters.semester = semester;
      if (skrot) filters.skrot = skrot;
      const page: ItemsPage = await getItems(filters as any);
      current = page.items[0] ?? null;
      remaining = page.total;
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc);
    } finally {
      loading = false;
    }
  }

  async function decide(action: string, category?: string): Promise<void> {
    if (!current) return;
    const item = current;
    error = null;
    success = null;

    const dtype = (action === 'skip' || action === 'quarantine')
      ? action
      : action === 'outdated' ? 'outdated' : 'classify';

    const decision: DecisionRequest = {
      sha256: item.sha256,
      decision_type: dtype,
      semester: item.semester ?? semester ?? undefined,
      subject_key: item.subject_key ?? skrot ?? undefined,
      category: category ?? item.category ?? undefined,
      action: dtype === 'classify' ? action : dtype === 'quarantine' ? 'quarantine' : undefined,
    };

    try {
      await postDecision(decision);
      history = [item.sha256, ...history.slice(0, 49)];
      success = `${item.sha256.slice(0, 12)}… → ${action}`;
      onDecided?.();
      await loadNext();
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc);
    }
  }

  async function openBulk(): Promise<void> {
    const folder = current?.folder_path;
    if (!folder) return;
    error = null;
    try {
      const preview = await getItemsByFolder(folder);
      bulk = {
        folder,
        total: preview.total,
        names: preview.items.slice(0, 8).map((item) => item.filename ?? item.sha256.slice(0, 12)),
      };
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc);
    }
  }

  async function applyBulk(decisionType: string, extra: Record<string, unknown> = {}): Promise<void> {
    if (!bulk || bulkBusy) return;
    bulkBusy = true;
    error = null;
    try {
      const result = await postDecisionByFolder(bulk.folder, decisionType, extra);
      success = `katalog ${bulk.folder}: ${result.count} decyzji`;
      bulk = null;
      onDecided?.();
      await loadNext();
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc);
    } finally {
      bulkBusy = false;
    }
  }

  async function saveTarget(): Promise<void> {
    if (!current || !targetDraft.trim()) return;
    error = null;
    try {
      await postDecision({
        sha256: current.sha256,
        decision_type: 'classify',
        semester: current.semester ?? semester ?? undefined,
        subject_key: current.subject_key ?? skrot ?? undefined,
        category: current.category ?? undefined,
        target_relative_path: targetDraft.trim(),
        action: 'copy',
      });
      editingTarget = false;
      success = 'ścieżka docelowa zapisana';
      onDecided?.();
      await loadNext();
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc);
    }
  }

  async function undo(): Promise<void> {
    if (!history.length) return;
    error = null;
    try {
      await postUndo();
      history = history.slice(1);
      success = 'cofnięto';
      onDecided?.();
      await loadNext();
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc);
    }
  }

  function onKey(event: KeyboardEvent): void {
    const target = event.target as HTMLElement | null;
    if (target?.tagName === 'INPUT' || target?.tagName === 'TEXTAREA') return;

    if (event.key === '?') {
      event.preventDefault();
      showHelp = !showHelp;
      return;
    }

    if (!current) return;

    const digit = parseInt(event.key, 10);
    if (digit >= 1 && digit <= 9 && digit <= CATEGORIES.length) {
      event.preventDefault();
      decide('copy', CATEGORIES[digit - 1]);
      return;
    }

    switch (event.key) {
      case 'Enter':
        event.preventDefault();
        decide('copy');
        break;
      case 's':
        event.preventDefault();
        decide('skip');
        break;
      case 'q':
        event.preventDefault();
        decide('quarantine');
        break;
      case 'u':
        event.preventDefault();
        undo();
        break;
      case 'm':
        event.preventDefault();
        decide('media');
        break;
      case 'o':
        event.preventDefault();
        decide('outdated');
        break;
      case 't':
        event.preventDefault();
        targetDraft = current.target_relative_path ?? '';
        editingTarget = true;
        break;
      case 'f':
        event.preventDefault();
        openBulk();
        break;
      case 'ArrowRight':
        if (preview?.pages && page < preview.pages) {
          event.preventDefault();
          page += 1;
        }
        break;
      case 'ArrowLeft':
        if (page > 1) {
          event.preventDefault();
          page -= 1;
        }
        break;
    }
  }

  $effect(() => {
    const _deps = [semester, skrot];
    loadNext();
  });

  $effect(() => {
    const sha = current?.sha256;
    preview = null;
    previewError = null;
    page = 1;
    if (!sha) return;
    const controller = new AbortController();
    getPreview(sha, controller.signal)
      .then((value) => {
        preview = value;
      })
      .catch((exc: unknown) => {
        if (controller.signal.aborted) return;
        previewError = exc instanceof Error ? exc.message : String(exc);
      });
    return () => controller.abort();
  });
</script>

<svelte:window onkeydown={onKey} />

<div class="decision-panel">
  <div class="header">
    <h3>Kolejka decyzji</h3>
    <span class="remaining num">{remaining} do przeglądu</span>
  </div>

  {#if error}
    <div class="error">{error}</div>
  {/if}
  {#if success}
    <div class="success">{success}</div>
  {/if}

  {#if loading}
    <div class="empty">Wczytuję…</div>
  {:else if !current}
    <div class="empty">Brak pozycji do przeglądu</div>
  {:else}
    <div class="item-card">
      <figure class="preview">
        {#if imageUrl}
          <button class="zoom-wrap" onclick={() => (zoomed = true)} title="Pokaż na cały ekran">
            <img src={imageUrl} alt="Podgląd: {current.filename ?? current.sha256}" />
            <span class="zoom-badge" aria-hidden="true">⤢</span>
          </button>
          {#if preview?.pages && preview.pages > 1}
            <figcaption class="pager">
              <button onclick={() => (page = Math.max(1, page - 1))} disabled={page <= 1}>‹</button>
              <span class="num">strona {page} / {preview.pages}</span>
              <button
                onclick={() => (page = Math.min(preview!.pages!, page + 1))}
                disabled={page >= preview.pages}>›</button
              >
            </figcaption>
          {/if}
        {:else if preview?.text_head}
          <TextPreview
            text={preview.text_head}
            language={preview.text_language}
            label={current.filename ?? preview.content_kind}
          />
        {:else if preview && preview.preview_kind === 'none'}
          <div class="no-preview">
            <p>Bez podglądu</p>
            <p class="dim">
              {preview.content_kind ?? 'nieznany rodzaj'} · żadna kopia tej treści nie leży
              dziś na dysku albo format nie ma podglądu
            </p>
          </div>
        {:else if previewError}
          <div class="no-preview"><p>Podgląd niedostępny</p><p class="dim">{previewError}</p></div>
        {:else}
          <div class="no-preview dim"><p>Wczytuję podgląd…</p></div>
        {/if}

        {#if preview?.text_head && imageUrl}
          <details class="text-toggle">
            <summary>głowa tekstu</summary>
            <TextPreview text={preview.text_head} language={preview.text_language} />
          </details>
        {/if}
      </figure>

      {#if zoomed && current}
        <Lightbox
          src={previewImageUrl(current.sha256, page, 1800)}
          alt={current.filename ?? current.sha256}
          caption={current.source_relative_path}
          original={previewImageUrl(current.sha256, page, 2000)}
          onClose={() => (zoomed = false)}
        />
      {/if}

      <div class="decision">
      <div class="item-header">
        <span class="sha mono">{current.sha256.slice(0, 16)}…</span>
        <span class="kind tag">{current.content_kind ?? '?'}</span>
        {#if current.copies > 1}
          <span class="copies tag">{current.copies} kopii</span>
        {/if}
      </div>

      <div class="item-meta">
        {#if current.filename}
          <div class="filename">{current.filename}</div>
        {/if}
        {#if current.source_relative_path}
          <div class="path mono dim">{dirname(current.source_relative_path)}</div>
        {/if}
        {#if current.size_bytes}
          <div class="size">{bytes(current.size_bytes)}</div>
        {/if}
      </div>

      <div class="proposal">
        <div class="label dim">Propozycja:</div>
        <div class="proposal-row">
          <span class="tag cat">{current.category ?? '—'}</span>
          <span class="tag action">{current.action ?? '—'}</span>
          <span class="confidence num" class:low={current.confidence !== null && current.confidence < 0.7}>
            {current.confidence !== null ? percent(current.confidence) : '—'}
          </span>
          <span class="method dim">{current.classification_method ?? ''}</span>
        </div>
        {#if current.reason}
          <div class="reason dim">{current.reason}</div>
        {/if}
        {#if current.target_relative_path}
          <div class="target mono dim">{current.target_relative_path}</div>
        {/if}
      </div>

      <div class="categories">
        <div class="label dim">Kategoria (1-9):</div>
        <div class="cat-buttons">
          {#each CATEGORIES as cat, i}
            <button
              class="cat-btn"
              class:current={current.category === cat}
              onclick={() => decide('copy', cat)}
              title={String(i + 1)}
            >
              <kbd>{i + 1}</kbd> {cat}
            </button>
          {/each}
        </div>
      </div>

      <div class="actions">
        <button class="action-btn accept" onclick={() => decide('copy')} title="Enter">
          Akceptuj (copy)
        </button>
        <button class="action-btn skip" onclick={() => decide('skip')} title="s">
          Pomiń
        </button>
        <button class="action-btn quarantine" onclick={() => decide('quarantine')} title="q">
          Kwarantanna
        </button>
        <button class="action-btn media" onclick={() => decide('media')} title="m">
          Media
        </button>
        <button class="action-btn outdated" onclick={() => decide('outdated')} title="o">
          Outdated
        </button>
        <button class="action-btn undo" onclick={undo} disabled={!history.length} title="u">
          Cofnij ({history.length})
        </button>
      </div>

      {#if editingTarget}
        <div class="target-edit">
          <label for="target-path">ścieżka docelowa:</label>
          <input
            id="target-path"
            bind:value={targetDraft}
            spellcheck="false"
            onkeydown={(e) => {
              if (e.key === 'Enter') { e.preventDefault(); saveTarget(); }
              if (e.key === 'Escape') { e.preventDefault(); editingTarget = false; }
            }}
          />
          <button onclick={saveTarget}>zapisz</button>
          <button class="ghost" onclick={() => (editingTarget = false)}>anuluj</button>
        </div>
      {/if}

      {#if bulk}
        <div class="bulk">
          <div class="bulk-head">
            <strong>cały katalog</strong>
            <span class="mono dim">{bulk.folder}</span>
            <span class="num">{bulk.total} pozycji</span>
          </div>
          <!-- Pokazujemy, czego decyzja dotknie, ZANIM cokolwiek zapiszemy. -->
          <div class="bulk-names mono dim">
            {bulk.names.join(' · ')}{bulk.total > bulk.names.length ? ' · …' : ''}
          </div>
          <div class="bulk-actions">
            <button disabled={bulkBusy} onclick={() => applyBulk('skip')}>pomiń wszystko</button>
            <button
              disabled={bulkBusy}
              onclick={() =>
                applyBulk('classify', {
                  semester: current?.semester ?? semester,
                  subject_key: current?.subject_key ?? skrot,
                  category: current?.category,
                  action: 'copy',
                })}
            >
              akceptuj wszystko ({current?.category ?? 'bez kategorii'})
            </button>
            <button class="ghost" disabled={bulkBusy} onclick={() => (bulk = null)}>anuluj</button>
          </div>
          <p class="dim">Pozycje z ground truth zostaną pominięte — nie nadpisujemy paczki.</p>
        </div>
      {/if}

      <div class="shortcuts dim">
        <kbd>←</kbd><kbd>→</kbd> strona &nbsp;
        <kbd>Enter</kbd> akceptuj &nbsp;
        <kbd>1-9</kbd> kategoria &nbsp;
        <kbd>s</kbd> pomiń &nbsp;
        <kbd>q</kbd> kwarantanna &nbsp;
        <kbd>m</kbd> media &nbsp;
        <kbd>o</kbd> outdated &nbsp;
        <kbd>t</kbd> ścieżka &nbsp;
        <kbd>f</kbd> katalog &nbsp;
        <kbd>u</kbd> cofnij &nbsp;
        <kbd>?</kbd> pomoc
      </div>
      </div>
    </div>
  {/if}

  {#if showHelp}
    <div class="help-panel">
      <h4>Skróty klawiszowe</h4>
      <table>
        <tbody>
          <tr><td><kbd>Enter</kbd></td><td>Akceptuj z bieżącą kategorią (copy)</td></tr>
          <tr><td><kbd>1</kbd>–<kbd>9</kbd></td><td>Akceptuj z wybraną kategorią</td></tr>
          <tr><td><kbd>s</kbd></td><td>Pomiń (skip)</td></tr>
          <tr><td><kbd>q</kbd></td><td>Kwarantanna</td></tr>
          <tr><td><kbd>m</kbd></td><td>Media</td></tr>
          <tr><td><kbd>o</kbd></td><td>Oznacz jako outdated</td></tr>
          <tr><td><kbd>t</kbd></td><td>Zmień ścieżkę docelową tej pozycji</td></tr>
          <tr><td><kbd>f</kbd></td><td>Decyzja dla całego katalogu źródłowego</td></tr>
          <tr><td><kbd>u</kbd></td><td>Cofnij ostatnią decyzję</td></tr>
          <tr><td><kbd>?</kbd></td><td>Pokaż/ukryj tę pomoc</td></tr>
        </tbody>
      </table>
      <h4>Kategorie</h4>
      <table>
        <tbody>
          {#each CATEGORIES as cat, i}
            <tr><td><kbd>{i + 1}</kbd></td><td>{cat}</td></tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

<style>
  .preview {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin: 0;
    padding: 10px;
    min-height: 240px;
    border: 1px solid var(--border-2);
    border-radius: 8px;
    background: var(--bg-deep);
  }
  .zoom-wrap {
    position: relative;
    display: block;
    width: 100%;
    padding: 0;
    cursor: zoom-in;
  }
  .zoom-badge {
    position: absolute;
    right: 8px;
    bottom: 8px;
    padding: 2px 8px;
    border-radius: 6px;
    background: rgba(1, 4, 9, 0.72);
    border: 1px solid var(--border);
    color: var(--text);
    font-size: 14px;
    line-height: 20px;
  }
  .preview img {
    width: 100%;
    /* Sufit dobrany tak, żeby przy układzie jednokolumnowym propozycja
       i przyciski decyzji zostały widoczne bez przewijania. */
    max-height: 44vh;
    object-fit: contain;
    border-radius: 4px;
    background: #fff;
  }
  .pager {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    color: var(--muted);
    font-size: 11px;
  }
  .pager button {
    padding: 0 8px;
    border: 1px solid var(--border);
    border-radius: 999px;
    color: var(--muted);
  }
  .pager button:disabled {
    opacity: 0.35;
    cursor: default;
  }
  .text-toggle summary {
    cursor: pointer;
    color: var(--muted);
    font-size: 11px;
  }
  .no-preview {
    margin: auto;
    text-align: center;
    color: var(--muted);
  }
  .no-preview p {
    margin: 2px 0;
  }

  .decision {
    display: flex;
    flex-direction: column;
    gap: 10px;
    min-width: 0;
  }

  .decision-panel {
    padding: 12px;
    overflow-y: auto;
    container-type: inline-size;
    container-name: decision;
  }
  .header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 12px;
  }
  .header h3 {
    margin: 0;
    font-size: 14px;
  }
  .remaining {
    color: var(--muted);
    font-size: 12px;
  }
  .item-card {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 12px;
    align-items: start;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 14px;
    background: var(--bg-deep);
  }

  /* Podgląd po lewej, decyzja po prawej — ale dopiero gdy panel ma na to miejsce.
     Zapytanie kontenerowe, nie medialne: o układ karty decyduje szerokość PANELU
     (trzeciej kolumny aplikacji), a nie szerokość okna. */
  @container decision (min-width: 900px) {
    .item-card {
      grid-template-columns: minmax(0, 1.1fr) minmax(330px, 0.9fr);
    }
  }
  .item-header {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .sha {
    font-size: 11px;
    color: var(--muted-2);
  }
  .item-meta {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .filename {
    font-weight: 600;
    font-size: 13px;
  }
  .path {
    font-size: 11px;
  }
  .size {
    font-size: 11px;
    color: var(--muted);
  }
  .proposal {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px;
    border-radius: 4px;
    background: var(--bg);
  }
  .proposal-row {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .confidence.low {
    color: var(--warn);
  }
  .reason, .target {
    font-size: 11px;
  }
  .actions {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }
  .action-btn {
    padding: 5px 12px;
    border: 1px solid var(--border);
    border-radius: 4px;
    font-size: 12px;
    cursor: pointer;
    color: var(--text);
    background: transparent;
  }
  .action-btn:hover {
    border-color: var(--accent-dim);
  }
  .action-btn.accept {
    border-color: var(--tag-ok);
    color: var(--tag-ok);
  }
  .action-btn.accept:hover {
    background: color-mix(in srgb, var(--tag-ok) 15%, transparent);
  }
  .action-btn.skip {
    color: var(--muted);
  }
  .action-btn.quarantine {
    color: var(--warn);
  }
  .action-btn.undo {
    margin-left: auto;
    color: var(--muted-2);
  }
  .action-btn:disabled {
    opacity: 0.3;
    cursor: default;
  }
  .target-edit {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    padding: 8px 10px;
    border: 1px solid var(--accent-dim);
    border-radius: 7px;
    background: var(--panel);
  }
  .target-edit input {
    flex: 1;
    min-width: 16rem;
    padding: 4px 8px;
    border: 1px solid var(--border);
    border-radius: 5px;
    background: var(--bg-deep);
    font-family: var(--font-mono);
    font-size: 11px;
  }
  .target-edit button,
  .bulk-actions button {
    padding: 3px 12px;
    border: 1px solid var(--border);
    border-radius: 999px;
    color: var(--muted);
  }
  .target-edit button:hover,
  .bulk-actions button:hover:not(:disabled) {
    color: var(--text);
    border-color: var(--accent-dim);
  }
  .ghost {
    border-color: transparent !important;
  }

  .bulk {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 8px 10px;
    border: 1px solid var(--amber);
    border-radius: 7px;
    background: rgba(210, 153, 34, 0.06);
  }
  .bulk-head {
    display: flex;
    align-items: baseline;
    gap: 10px;
    flex-wrap: wrap;
  }
  .bulk-names {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 11px;
  }
  .bulk-actions {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }
  .bulk p {
    margin: 0;
    font-size: 11px;
  }

  .shortcuts {
    font-size: 10px;
    text-align: center;
  }
  .shortcuts kbd {
    padding: 1px 4px;
    border: 1px solid var(--border);
    border-radius: 3px;
    font-size: 10px;
    background: var(--bg-deep);
  }
  .error {
    padding: 6px 10px;
    margin-bottom: 8px;
    border-radius: 4px;
    background: color-mix(in srgb, var(--warn) 15%, transparent);
    color: var(--warn);
    font-size: 12px;
  }
  .success {
    padding: 6px 10px;
    margin-bottom: 8px;
    border-radius: 4px;
    background: color-mix(in srgb, var(--tag-ok) 15%, transparent);
    color: var(--tag-ok);
    font-size: 12px;
  }
  .empty {
    padding: 24px;
    text-align: center;
    color: var(--muted);
  }
  .label {
    font-size: 11px;
  }
  .tag {
    padding: 1px 6px;
    border-radius: 3px;
    font-size: 11px;
    background: var(--tag-bg, color-mix(in srgb, var(--border) 50%, transparent));
  }
  .categories {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .cat-buttons {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .cat-btn {
    padding: 3px 8px;
    border: 1px solid var(--border);
    border-radius: 4px;
    font-size: 11px;
    cursor: pointer;
    color: var(--text);
    background: transparent;
  }
  .cat-btn:hover {
    border-color: var(--accent-dim);
  }
  .cat-btn.current {
    border-color: var(--accent);
    background: color-mix(in srgb, var(--accent) 12%, transparent);
  }
  .cat-btn kbd {
    padding: 0 3px;
    border: 1px solid var(--border);
    border-radius: 2px;
    font-size: 10px;
    background: var(--bg-deep);
  }
  .action-btn.outdated {
    color: var(--muted-2);
  }
  .help-panel {
    margin-top: 8px;
    padding: 12px;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--bg-deep);
    font-size: 12px;
  }
  .help-panel h4 {
    margin: 0 0 6px;
    font-size: 12px;
  }
  .help-panel table {
    width: 100%;
    border-collapse: collapse;
  }
  .help-panel td {
    padding: 2px 6px;
    font-size: 11px;
  }
  .help-panel td:first-child {
    width: 60px;
    text-align: center;
  }
  .help-panel kbd {
    padding: 1px 4px;
    border: 1px solid var(--border);
    border-radius: 3px;
    font-size: 10px;
    background: var(--bg);
  }
</style>
