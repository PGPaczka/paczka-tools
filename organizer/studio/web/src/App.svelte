<script lang="ts">
  import {
    getDashboard,
    getHealth,
    getItems,
    getSubject,
    type Dashboard,
    type Health,
    type ItemsPage,
    type SubjectDetail,
    type SubjectRow,
  } from './lib/api';
  import { count } from './lib/format';
  import QueuePanel from './components/QueuePanel.svelte';
  import SubjectList from './components/SubjectList.svelte';
  import SubjectPanel from './components/SubjectPanel.svelte';
  import DecisionPanel from './components/DecisionPanel.svelte';
  import ClusterPanel from './components/ClusterPanel.svelte';
  import HistoryPanel from './components/HistoryPanel.svelte';
  import StatsPanel from './components/StatsPanel.svelte';

  type Mode = 'browse' | 'decide' | 'clusters' | 'history' | 'stats';

  /** Ile pozycji dokłada „Pokaż więcej”. */
  const PAGE = 30;

  let dashboard = $state<Dashboard | null>(null);
  let health = $state<Health | null>(null);
  let fatal = $state<string | null>(null);

  let stage = $state<string | null>(null);
  let query = $state('');
  let semester = $state<number | null>(null);

  let selected = $state<SubjectRow | null>(null);
  let detail = $state<SubjectDetail | null>(null);
  let detailError = $state<string | null>(null);
  let category = $state<string | null>(null);
  let onlyReview = $state(false);
  let limit = $state(PAGE);
  let page = $state<ItemsPage | null>(null);
  let loadingItems = $state(false);

  let mode = $state<Mode>('browse');
  let list: SubjectList | undefined = $state();

  const semesters = $derived(
    dashboard ? [...new Set(dashboard.subjects.map((row) => row.semester))].sort((a, b) => a - b) : [],
  );

  const filtered = $derived.by(() => {
    const rows = dashboard?.subjects ?? [];
    const needle = query.trim().toLocaleLowerCase('pl');
    return rows.filter((row) => {
      if (stage && row.stage !== stage) return false;
      if (semester !== null && row.semester !== semester) return false;
      if (!needle) return true;
      const haystack = [row.skrot, row.nazwa, row.grupa, ...row.aliases]
        .join(' ')
        .toLocaleLowerCase('pl');
      return haystack.includes(needle);
    });
  });

  async function loadDashboard(): Promise<void> {
    try {
      [dashboard, health] = await Promise.all([getDashboard(), getHealth()]);
      fatal = null;
    } catch (exc) {
      fatal = exc instanceof Error ? exc.message : String(exc);
    }
  }

  function select(row: SubjectRow): void {
    selected = row;
    category = null;
    limit = PAGE;
    detail = null;
    page = null;
  }

  function move(delta: number): void {
    const rows = filtered;
    if (!rows.length) return;
    const index = selected ? rows.findIndex((row) => row.skrot === selected!.skrot && row.semester === selected!.semester) : -1;
    const next = rows[Math.min(Math.max(index + delta, 0), rows.length - 1)] ?? rows[0];
    select(next);
    queueMicrotask(() => {
      document
        .querySelector(`[data-subject="${next.semester}/${next.grupa}/${next.skrot}"]`)
        ?.scrollIntoView({ block: 'nearest' });
    });
  }

  function onKey(event: KeyboardEvent): void {
    const target = event.target as HTMLElement | null;
    const typing = target?.tagName === 'INPUT' || target?.tagName === 'TEXTAREA';
    if (event.key === 'Escape') {
      (target as HTMLInputElement | null)?.blur();
      query = '';
      stage = null;
      semester = null;
      return;
    }
    if (typing || event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.key === 'd' && mode === 'browse') {
      event.preventDefault();
      mode = 'decide';
      return;
    }
    if (event.key === 'c' && mode === 'browse') {
      event.preventDefault();
      mode = 'clusters';
      return;
    }
    if (event.key === 'h' && mode === 'browse') {
      event.preventDefault();
      mode = 'history';
      return;
    }
    if (event.key === 'b' && mode !== 'browse') {
      event.preventDefault();
      mode = 'browse';
      return;
    }
    if (mode !== 'browse') return;
    if (event.key === '/') {
      event.preventDefault();
      list?.focusSearch();
    } else if (event.key === 'j' || event.key === 'ArrowDown') {
      event.preventDefault();
      move(1);
    } else if (event.key === 'k' || event.key === 'ArrowUp') {
      event.preventDefault();
      move(-1);
    }
  }

  $effect(() => {
    loadDashboard();
  });

  $effect(() => {
    const row = selected;
    if (!row) return;
    const controller = new AbortController();
    getSubject(row.semester, row.skrot, row.grupa, controller.signal)
      .then((value) => {
        detail = value;
        detailError = null;
      })
      .catch((exc: unknown) => {
        if (controller.signal.aborted) return;
        detailError = exc instanceof Error ? exc.message : String(exc);
      });
    return () => controller.abort();
  });

  $effect(() => {
    const row = selected;
    const filters = { category, onlyReview, limit };
    if (!row) return;
    const controller = new AbortController();
    loadingItems = true;
    getItems(
      {
        semester: row.semester,
        skrot: row.skrot,
        category: filters.category ?? undefined,
        needs_review: filters.onlyReview ? true : undefined,
        limit: filters.limit,
      },
      controller.signal,
    )
      .then((value) => {
        page = value;
        detailError = null;
      })
      .catch((exc: unknown) => {
        if (controller.signal.aborted) return;
        detailError = exc instanceof Error ? exc.message : String(exc);
      })
      .finally(() => {
        if (!controller.signal.aborted) loadingItems = false;
      });
    return () => controller.abort();
  });
</script>

<svelte:window onkeydown={onKey} />

<div class="app">
  <header>
    <div class="brand">
      <strong>Paczka Studio</strong>
      <span class="phase">{
        mode === 'browse' ? 'S0 · przeglądarka' :
        mode === 'decide' ? 'S1 · decyzje' :
        mode === 'clusters' ? 'S2 · klastry' :
        mode === 'history' ? 'S4 · historia' :
        'S4 · statystyki'
      }</span>
    </div>

    {#if dashboard}
      <div class="totals num">
        <span><b>{count(dashboard.totals.subjects)}</b> przedmiotów</span>
        <span><b>{count(dashboard.totals.contents)}</b> treści</span>
        <span><b>{count(dashboard.totals.files)}</b> plików</span>
        <span><b>{count(dashboard.totals.plan_items)}</b> w planie</span>
      </div>
    {/if}

    <div class="right mono">
      {#if health}
        <span title={health.db}>{health.db.split('/').slice(-2).join('/')}</span>
        <span class="dim">schema v{health.schema_version}</span>
      {/if}
      <button onclick={loadDashboard} title="Przeładuj liczby z bazy">odśwież</button>
        <button
          class="mode-toggle"
          class:active={mode === 'decide'}
          onclick={() => (mode = mode === 'decide' ? 'browse' : 'decide')}
          title="d / b — tryb decyzji"
        >
          decyzje
        </button>
        <button
          class="mode-toggle"
          class:active={mode === 'clusters'}
          onclick={() => (mode = mode === 'clusters' ? 'browse' : 'clusters')}
          title="c / b — klastry"
        >
          klastry
        </button>
        <button
          class="mode-toggle"
          class:active={mode === 'history'}
          onclick={() => (mode = mode === 'history' ? 'browse' : 'history')}
          title="h / b — historia"
        >
          historia
        </button>
        <button
          class="mode-toggle"
          class:active={mode === 'stats'}
          onclick={() => (mode = mode === 'stats' ? 'browse' : 'stats')}
          title="statystyki"
        >
          statystyki
        </button>
    </div>
  </header>

  {#if fatal}
    <div class="fatal">
      <p>Backend nie odpowiada: {fatal}</p>
      <p class="mono">just studio</p>
    </div>
  {:else if !dashboard}
    <div class="fatal"><p>Wczytuję indeks…</p></div>
  {:else}
    <main>
      <QueuePanel {dashboard} {stage} onStage={(value) => (stage = value)} />
      <SubjectList
        bind:this={list}
        subjects={filtered}
        {selected}
        onSelect={select}
        bind:query
        bind:semester
        {semesters}
      />
      {#if mode === 'decide'}
        <DecisionPanel
          semester={selected?.semester}
          skrot={selected?.skrot}
          onDecided={loadDashboard}
        />
      {:else if mode === 'clusters'}
        <ClusterPanel
          semester={selected?.semester}
          skrot={selected?.skrot}
          onResolved={loadDashboard}
        />
      {:else if mode === 'history'}
        <HistoryPanel onChanged={loadDashboard} />
      {:else if mode === 'stats'}
        <StatsPanel />
      {:else}
        <SubjectPanel
          row={selected}
          {detail}
          {page}
          loading={loadingItems}
          error={detailError}
          bind:category
          bind:onlyReview
          onMore={() => (limit += PAGE)}
        />
      {/if}
    </main>
  {/if}
</div>

<style>
  .app {
    display: grid;
    grid-template-rows: auto minmax(0, 1fr);
    height: 100%;
  }

  header {
    display: flex;
    align-items: center;
    gap: 18px;
    padding: 0 14px;
    height: 44px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-deep);
  }
  .brand {
    display: flex;
    align-items: baseline;
    gap: 8px;
  }
  .brand strong {
    font-size: 14px;
    letter-spacing: 0.01em;
  }
  .phase {
    font-size: 10.5px;
    color: var(--muted-2);
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 0 7px;
  }

  .totals {
    display: flex;
    gap: 16px;
    color: var(--muted);
  }
  .totals b {
    color: var(--text);
    font-weight: 600;
  }

  .right {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-left: auto;
    color: var(--muted-2);
  }
  .right button {
    padding: 2px 10px;
    border: 1px solid var(--border);
    border-radius: 999px;
    color: var(--muted);
  }
  .right button:hover {
    color: var(--text);
    border-color: var(--accent-dim);
  }
  .mode-toggle.active {
    background: var(--accent-dim);
    border-color: var(--accent);
    color: var(--text);
  }
  .dim {
    color: var(--muted-2);
  }

  main {
    display: grid;
    grid-template-columns: 220px minmax(320px, 0.9fr) minmax(0, 1.3fr);
    min-height: 0;
  }

  .fatal {
    display: flex;
    flex-direction: column;
    gap: 6px;
    align-items: center;
    justify-content: center;
    color: var(--muted);
  }
  .fatal p {
    margin: 0;
  }

  /* Na wąskim ekranie znika kolejka (jest powtórzona jako filtr etapu),
     a nie panel przedmiotu — to on jest treścią tego widoku. */
  @media (max-width: 1100px) {
    main {
      grid-template-columns: minmax(240px, 0.85fr) minmax(0, 1.15fr);
    }
    main > :global(aside) {
      display: none;
    }
  }
</style>
