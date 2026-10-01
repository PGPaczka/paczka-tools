<script lang="ts">
  import {
    getStats,
    getPipeline,
    runIndexStage,
    type LiveStats,
    type IndexStage,
  } from '../../lib/api';
  import { count, percent } from '../../lib/format';

  let stats = $state<LiveStats | null>(null);
  let loading = $state(false);
  let error = $state<string | null>(null);

  /** Etapy CAŁEGO indeksu. Nie należą do żadnego przedmiotu, więc nie mają czego
   *  szukać w zakładce planu — a to jest jedyny widok o indeksie jako całości. */
  const indexStages: Array<{ id: IndexStage; label: string; title: string }> = [
    { id: 'scan', label: 'skanuj źródła', title: 'scan.py — spis plików i katalogów źródeł; niczego nie zmienia w materiałach' },
    { id: 'hash', label: 'hashuj', title: 'hash_files.py — sha256 każdego pliku; identyczne bajty scalają się w jedną treść' },
    { id: 'fold-hash', label: 'dedup katalogów', title: 'fold_hash.py — identyczne poddrzewa wypadają z dalszej pracy' },
    { id: 'extract', label: 'ekstrahuj tekst', title: 'extract_text.py — tekst z PDF/docx; bez tego podobieństwo obrazów liczy się po pikselach' },
    { id: 'scan-target', label: 'wczytaj paczkę', title: 'scan_target.py — ground truth z repo paczki; to on chroni ułożone materiały przed nadpisaniem' },
    { id: 'status', label: 'przelicz STATUS.md', title: 'status_report.py — tabela przedmioty × etapy z indeksu' },
  ];

  let running = $state<IndexStage | null>(null);
  /** Nazwa etapu trwającego GDZIEKOLWIEK w studiu — blokada jest jedna na całość,
   *  więc `apply` przedmiotu też wyszarza te przyciski. */
  let busyElsewhere = $state<string | null>(null);
  let log = $state<string[]>([]);
  let lastCode = $state<number | null>(null);
  let ocrImages = $state(false);
  let console_ = $state<HTMLPreElement | null>(null);

  async function load(): Promise<void> {
    loading = true;
    error = null;
    try {
      const [live, pipeline] = await Promise.all([getStats(), getPipeline()]);
      stats = live;
      busyElsewhere = pipeline.running;
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc);
    } finally {
      loading = false;
    }
  }

  async function runIndex(stage: IndexStage): Promise<void> {
    if (running || busyElsewhere) return;
    running = stage;
    lastCode = null;
    log = [];
    try {
      lastCode = await runIndexStage(
        { stage, ocr_images: stage === 'extract' && ocrImages },
        (line) => {
          log = [...log, line];
          queueMicrotask(() => console_?.scrollTo({ top: console_.scrollHeight }));
        },
      );
    } catch (exc) {
      // Odmowa blokady wraca tu jako wyjątek z treścią z serwera — pokazujemy ją
      // dosłownie, bo to jest powód, dla którego etap nie ruszył.
      log = [...log, exc instanceof Error ? exc.message : String(exc)];
      lastCode = 409;
    } finally {
      running = null;
      await load();
    }
  }

  $effect(() => { load(); });
</script>

<div class="stats-panel">
  <div class="header">
    <h3>Indeks — stan i etapy</h3>
    <button onclick={load}>odśwież</button>
  </div>

  {#if error}
    <div class="msg error">{error}</div>
  {/if}

  <section class="runner">
    <h4>Etapy indeksu</h4>
    <p class="hint">
      Dotyczą <strong>wszystkich źródeł</strong>, nie wybranego przedmiotu. Źródła są
      czytane tylko do odczytu; wynik idzie do bazy roboczej. Etapy przedmiotu są
      w zakładce <strong>plan</strong>.
    </p>

    <div class="stages">
      {#each indexStages as stage (stage.id)}
        <button
          disabled={running !== null || busyElsewhere !== null}
          title={stage.title}
          onclick={() => runIndex(stage.id)}
        >
          {running === stage.id ? '…' : stage.label}
        </button>
      {/each}
      {#if lastCode !== null}
        <span class="code" class:bad={lastCode !== 0}>kod wyjścia {lastCode}</span>
      {/if}
    </div>

    <label class="ocr">
      <input type="checkbox" bind:checked={ocrImages} disabled={running !== null} />
      OCR obrazów przy ekstrakcji
      <span class="dim">— zmierzone 2977 s na tym indeksie, czyli ok. 50 minut</span>
    </label>

    {#if busyElsewhere}
      <!-- Blokada jest jedna na całe studio: wszystkie etapy piszą do tej samej
           bazy, więc `apply` przedmiotu wyklucza `extract` indeksu i odwrotnie. -->
      <p class="msg busy">Trwa inny etap: <strong>{busyElsewhere}</strong>. Poczekaj na jego koniec.</p>
    {/if}

    {#if log.length || running}
      <pre class="console" bind:this={console_}>{log.join('\n')}</pre>
    {/if}
  </section>

  {#if loading}
    <div class="empty">Wczytuję…</div>
  {:else if stats}
    <div class="sections">
      <section>
        <h4>Ogólne</h4>
        <dl>
          <dt>Paczki</dt><dd class="num">{count(stats.totals.packages)}</dd>
          <dt>Katalogi</dt><dd class="num">{count(stats.totals.folders)} <span class="dim">({count(stats.totals.duplicate_folders)} dupl.)</span></dd>
          <dt>Pliki</dt><dd class="num">{count(stats.totals.files)}</dd>
          <dt>Treści</dt><dd class="num">{count(stats.totals.contents)}</dd>
          <dt>Z tekstem</dt><dd class="num">{count(stats.totals.with_text)}</dd>
          <dt>Relacje</dt><dd class="num">{count(stats.totals.relations)}</dd>
          <dt>Pozycje planu</dt><dd class="num">{count(stats.totals.plan_items)}</dd>
          <dt>Applied</dt><dd class="num">{count(stats.totals.applied)}</dd>
          <dt>Przedmioty</dt><dd class="num">{count(stats.totals.subjects)}</dd>
          <dt>Decyzje ręczne</dt><dd class="num">{count(stats.totals.manual_decisions)}</dd>
        </dl>
      </section>

      <section>
        <h4>Etapy przedmiotów</h4>
        <dl>
          {#each Object.entries(stats.stages) as [stage, n]}
            <dt>{stage}</dt><dd class="num">{n}</dd>
          {/each}
        </dl>
      </section>

      <section>
        <h4>Statusy plików</h4>
        <dl>
          {#each Object.entries(stats.totals.files_by_status) as [status, n]}
            <dt>{status}</dt><dd class="num">{count(n)}</dd>
          {/each}
        </dl>
      </section>

      <section>
        <h4>Metody klasyfikacji</h4>
        <dl>
          {#each Object.entries(stats.methods) as [method, n]}
            <dt>{method}</dt><dd class="num">{count(n)}</dd>
          {/each}
        </dl>
      </section>

      <section>
        <h4>Kategorie</h4>
        <dl>
          {#each Object.entries(stats.categories).sort((a, b) => b[1] - a[1]) as [cat, n]}
            <dt>{cat}</dt><dd class="num">{count(n)}</dd>
          {/each}
        </dl>
      </section>

      <section>
        <h4>Akcje</h4>
        <dl>
          {#each Object.entries(stats.actions) as [action, n]}
            <dt>{action}</dt><dd class="num">{count(n)}</dd>
          {/each}
        </dl>
      </section>

      <section>
        <h4>Progi pewności</h4>
        <dl>
          <dt>Auto-apply</dt><dd class="num">≥ {percent(stats.thresholds.auto_apply)}</dd>
          <dt>Review</dt><dd class="num">≥ {percent(stats.thresholds.review_min)}</dd>
        </dl>
      </section>
    </div>
  {/if}
</div>

<style>
  .stats-panel {
    padding: 12px;
    overflow-y: auto;
  }
  .header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 12px;
  }
  .header h3 { margin: 0; font-size: 14px; }
  .header button {
    padding: 2px 10px;
    border: 1px solid var(--border);
    border-radius: 999px;
    font-size: 11px;
    color: var(--muted);
    background: transparent;
    cursor: pointer;
  }
  .header button:hover { color: var(--text); border-color: var(--accent-dim); }
  .sections {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  section {
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px;
  }
  h4 { margin: 0 0 6px; font-size: 12px; color: var(--muted); }
  dl {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 2px 12px;
    margin: 0;
    font-size: 12px;
  }
  dt { color: var(--text); }
  dd { margin: 0; text-align: right; }
  .msg.error {
    padding: 6px 10px; margin-bottom: 8px; border-radius: 4px;
    background: color-mix(in srgb, var(--warn) 15%, transparent); color: var(--warn); font-size: 12px;
  }
  .empty { padding: 24px; text-align: center; color: var(--muted); }

  /* --- etapy indeksu --- */
  .runner { margin-bottom: 14px; }
  .hint {
    margin: 0 0 8px;
    font-size: 11px;
    color: var(--muted);
    line-height: 1.5;
  }
  .stages {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }
  .stages button {
    padding: 3px 12px;
    border: 1px solid var(--border);
    border-radius: 999px;
    font-size: 12px;
    color: var(--muted);
    background: transparent;
    cursor: pointer;
  }
  .stages button:hover:not(:disabled) { color: var(--text); border-color: var(--accent-dim); }
  .stages button:disabled { opacity: 0.45; cursor: default; }
  .code { font-size: 11px; color: var(--green); font-family: var(--font-mono); }
  .code.bad { color: var(--warn); }
  .ocr {
    display: flex;
    align-items: baseline;
    gap: 6px;
    margin-top: 8px;
    font-size: 11px;
    color: var(--text);
  }
  .dim { color: var(--muted); }
  .msg.busy {
    margin: 8px 0 0;
    padding: 6px 10px;
    border-radius: 4px;
    background: color-mix(in srgb, var(--warn) 12%, transparent);
    color: var(--warn);
    font-size: 11px;
  }
  /* Log rośnie w trakcie etapu, więc ma stałą wysokość — inaczej strona skacze
     pod kursorem przy każdej linii. */
  .console {
    margin: 8px 0 0;
    padding: 8px;
    max-height: 220px;
    overflow: auto;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg-deep);
    font-size: 11px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
  }
</style>
