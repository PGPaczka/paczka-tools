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
  import {
    loadPrefs,
    savePrefs,
    shaFromUrl,
    type Prefs,
    defaultPanels,
    NARROW,
  } from './lib/prefs';
  import QueuePanel from './components/QueuePanel.svelte';
  import SubjectList from './components/SubjectList.svelte';
  import SubjectPanel from './components/SubjectPanel.svelte';
  import DecisionPanel from './components/DecisionPanel.svelte';
  import ClusterPanel from './components/ClusterPanel.svelte';
  import HistoryPanel from './components/HistoryPanel.svelte';
  import FolderLinkPanel from './components/FolderLinkPanel.svelte';
  import StatsPanel from './components/StatsPanel.svelte';
  import GraphPanel from './components/GraphPanel.svelte';
  import PlanPanel from './components/PlanPanel.svelte';
  import SearchPanel from './components/SearchPanel.svelte';

  type Mode = 'browse' | 'decide' | 'clusters' | 'history' | 'stats' | 'graph' | 'plan' | 'search' | 'folders';

  /** Tryby widoku w jednym miejscu: pasek przycisków i lista na telefonie czytają stąd. */
  const MODES: { id: Mode; label: string; title: string }[] = [
    { id: 'browse', label: 'przegląd', title: 'b — przegląd przedmiotu' },
    { id: 'decide', label: 'decyzje', title: 'd / b — tryb decyzji' },
    { id: 'clusters', label: 'klastry', title: 'c / b — klastry' },
    { id: 'history', label: 'historia', title: 'h / b — historia' },
    { id: 'search', label: 'szukaj', title: 'w / b — wyszukiwanie w całej paczce' },
    { id: 'plan', label: 'plan', title: 'p / b — plan, bramka i apply' },
    { id: 'graph', label: 'graf', title: 'g / b — graf jako soczewka' },
    { id: 'folders', label: 'katalogi', title: 'ręczne powiązania katalogów między paczkami' },
    { id: 'stats', label: 'statystyki', title: 'statystyki' },
  ];

  /** Ile pozycji dokłada „Pokaż więcej”. */
  const PAGE = 30;

  /** Zapamiętany wybór z poprzedniej wizyty; odczyt jest bezpieczny nawet bez pamięci. */
  const saved: Prefs = loadPrefs();

  let dashboard = $state<Dashboard | null>(null);
  let health = $state<Health | null>(null);
  let fatal = $state<string | null>(null);

  let stage = $state<string | null>(saved.stage ?? null);
  let query = $state('');
  /** Zapytanie wyszukiwarki; z adresu wchodzi tu sha wskazanej treści. */
  let searchQuery = $state(fromUrlSha());

  function fromUrlSha(): string {
    if (typeof window === 'undefined') return '';
    return shaFromUrl(window.location.search) ?? '';
  }
  let semester = $state<number | null>(saved.semester ?? null);

  let selected = $state<SubjectRow | null>(null);
  let detail = $state<SubjectDetail | null>(null);
  let detailError = $state<string | null>(null);
  let category = $state<string | null>(null);
  let onlyReview = $state(false);
  let limit = $state(PAGE);
  let page = $state<ItemsPage | null>(null);
  let loadingItems = $state(false);

  /** Wejście z grafu: `/?sha=<sha256>` otwiera wyszukiwanie na tej jednej treści. */
  const fromUrl = typeof window === 'undefined' ? null : shaFromUrl(window.location.search);
  let mode = $state<Mode>(fromUrl ? 'search' : ((saved.mode as Mode) ?? 'browse'));
  /** Strumień/katedra — drugi poziom wyboru dla SEM5–7. */
  let grupa = $state<string | null>(saved.grupa ?? null);
  /** Czy ekran jest na tyle wąski, że panele muszą być nakładką, a nie kolumną. */
  const startsNarrow =
    typeof window !== 'undefined' && window.matchMedia(`(max-width: ${NARROW}px)`).matches;
  let narrow = $state(startsNarrow);

  /** Boczne panele: na tablecie oddają miejsce panelowi roboczemu, na telefonie
   *  startują zwinięte — inaczej pierwszy ekran to sama lista, a nie praca. */
  const panels = defaultPanels(typeof window === 'undefined' ? 1440 : window.innerWidth);
  let queueOpen = $state<boolean>(saved.queueOpen ?? panels.queueOpen);
  let listOpen = $state<boolean>(saved.listOpen ?? panels.listOpen);
  let list: SubjectList | undefined = $state();

  /** Grupy (strumień/katedra) dostępne w wybranym semestrze — drugi poziom wyboru.
   *  Pokazujemy je tylko wtedy, gdy naprawdę rozdzielają przedmioty. */
  const grupy = $derived.by(() => {
    // Dopiero po wybraniu semestru: bez niego „grupa” zlewa strumienie SEM5/6
    // z katedrami SEM7 w jedną listę, która niczego nie zawęża.
    if (semester === null) return [];
    const rows = (dashboard?.subjects ?? []).filter((row) => row.semester === semester);
    const names = [...new Set(rows.map((row) => row.grupa))].sort();
    return names.length > 1 ? names : [];
  });

  const semesters = $derived(
    dashboard ? [...new Set(dashboard.subjects.map((row) => row.semester))].sort((a, b) => a - b) : [],
  );

  const filtered = $derived.by(() => {
    const rows = dashboard?.subjects ?? [];
    const needle = query.trim().toLocaleLowerCase('pl');
    return rows.filter((row) => {
      if (stage && row.stage !== stage) return false;
      if (semester !== null && row.semester !== semester) return false;
      if (grupa !== null && row.grupa !== grupa) return false;
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

  /** Powrót z grafu: zaznacz przedmiot tej treści i wróć do przeglądarki. */
  function openSubjectFromGraph(semesterValue: number, skrotValue: string): void {
    const row = (dashboard?.subjects ?? []).find(
      (item) => item.semester === semesterValue && item.skrot === skrotValue,
    );
    if (!row) return;
    select(row);
    mode = 'browse';
    queueMicrotask(() => {
      document
        .querySelector(`[data-subject="${row.semester}/${row.grupa}/${row.skrot}"]`)
        ?.scrollIntoView({ block: 'nearest' });
    });
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
    if (event.key === 'g' && mode === 'browse') {
      event.preventDefault();
      mode = 'graph';
      return;
    }
    if (event.key === 'w' && mode === 'browse') {
      event.preventDefault();
      mode = 'search';
      return;
    }
    if (event.key === 'p' && mode === 'browse') {
      event.preventDefault();
      mode = 'plan';
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
    if (typeof window === 'undefined') return;
    const query = window.matchMedia(`(max-width: ${NARROW}px)`);
    const update = () => (narrow = query.matches);
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  });

  $effect(() => {
    loadDashboard();
  });

  // Zapamiętujemy wybór, żeby odświeżenie strony (albo powrót na tablecie)
  // wracało tam, gdzie się skończyło.
  $effect(() => {
    savePrefs({
      mode,
      semester,
      grupa,
      skrot: selected?.skrot ?? null,
      stage,
      queueOpen,
      listOpen,
    });
  });

  /** Odtworzenie wybranego przedmiotu — dopiero gdy przyjdzie lista z serwera. */
  let restored = false;
  $effect(() => {
    if (restored || !dashboard || !saved.skrot) return;
    restored = true;
    const row = dashboard.subjects.find(
      (item) =>
        item.skrot === saved.skrot &&
        (saved.semester == null || item.semester === saved.semester) &&
        (saved.grupa == null || item.grupa === saved.grupa),
    );
    if (row) selected = row;
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
        mode === 'graph' ? 'S4 · graf' :
        mode === 'plan' ? 'S3 · plan' :
        mode === 'search' ? 'S4 · szukaj' :
        mode === 'folders' ? 'Q3 · katalogi' :
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
        <span class="db" title={health.db}>{health.db.split('/').slice(-2).join('/')}</span>
        <span class="db dim">schema v{health.schema_version}</span>
      {/if}
      <button
        class="panel-toggle"
        class:off={!queueOpen}
        onclick={() => (queueOpen = !queueOpen)}
        title="Zwiń/rozwiń kolejkę etapów"
      >⟨kolejka⟩</button>
      <button
        class="panel-toggle"
        class:off={!listOpen}
        onclick={() => (listOpen = !listOpen)}
        title="Zwiń/rozwiń listę przedmiotów"
      >⟨lista⟩</button>
      <button onclick={loadDashboard} title="Przeładuj liczby z bazy">odśwież</button>
      {#each MODES.filter((m) => m.id !== 'browse') as entry}
        <button
          class="mode-toggle"
          class:active={mode === entry.id}
          onclick={() => (mode = mode === entry.id ? 'browse' : entry.id)}
          title={entry.title}
        >
          {entry.label}
        </button>
      {/each}
      <!-- Na telefonie osiem zakładek nie mieści się w pasku i uciekały poza ekran. -->
      <select
        class="mode-select mono"
        aria-label="Widok"
        bind:value={mode}
        title="Widok"
      >
        {#each MODES as entry}
          <option value={entry.id}>{entry.label}</option>
        {/each}
      </select>
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
    <main
      class:narrow
      class:lens={mode === 'graph'}
      class:queue-hidden={!queueOpen}
      class:list-hidden={!listOpen || mode === 'graph'}
    >
      <!-- Panele boczne zwijają się do pionowej zakładki: na tablecie cała szerokość
           idzie wtedy do panelu roboczego, a wybór wraca jednym kliknięciem. -->
      {#if queueOpen}
        <QueuePanel
          {dashboard}
          {stage}
          onStage={(value) => {
            stage = value;
            if (narrow) queueOpen = false;
          }}
          onClose={() => (queueOpen = false)}
        />
      {:else}
        <button class="rail" onclick={() => (queueOpen = true)} title="Pokaż kolejkę etapów">
          <span>kolejka</span>
        </button>
      {/if}

      {#if mode !== 'graph'}
        {#if listOpen}
          <SubjectList
            bind:this={list}
            subjects={filtered}
            {selected}
            onSelect={(row) => {
              select(row);
              // Na telefonie lista zasłania panel roboczy — po wyborze schodzi z drogi.
              if (narrow) listOpen = false;
            }}
            bind:query
            bind:semester
            bind:grupa
            {grupy}
            {semesters}
            onClose={() => (listOpen = false)}
          />
        {:else}
          <button class="rail" onclick={() => (listOpen = true)} title="Pokaż listę przedmiotów">
            <span>{selected ? selected.skrot : 'przedmioty'}</span>
          </button>
        {/if}
      {/if}
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
      {:else if mode === 'search'}
        <SearchPanel onOpenSubject={openSubjectFromGraph} initialQuery={searchQuery} />
      {:else if mode === 'plan'}
        <PlanPanel
          semester={selected?.semester}
          skrot={selected?.skrot}
          grupa={selected?.grupa}
          onChanged={loadDashboard}
        />
      {:else if mode === 'graph'}
        <GraphPanel
          semester={selected?.semester}
          skrot={selected?.skrot}
          grupa={selected?.grupa}
          onOpenSubject={openSubjectFromGraph}
        />
      {:else if mode === 'folders'}
        <FolderLinkPanel />
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
    /* Bez tego pasek zakładek rozpychał CAŁĄ stronę: na telefonie `main` robił się
       szerszy od ekranu (zmierzone 769 px przy 412 px widoku), więc panel roboczy
       — w tym graf — dostawał ułamek szerokości i wyglądał na zepsuty. */
    max-width: 100vw;
    overflow-x: hidden;
  }

  header {
    display: flex;
    align-items: center;
    gap: 12px;
    max-width: 100%;
    min-width: 0;
    padding: 4px 10px;
    min-height: 44px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-deep);
  }
  .brand {
    display: flex;
    align-items: baseline;
    gap: 8px;
    flex: none;
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
    gap: 8px;
    margin-left: auto;
    color: var(--muted-2);
    /* Zakładki MUSZĄ być dosięgalne na każdym ekranie. Na wąskim nagłówek nie
       zawija ich poza widok, tylko przewija się w poziomie — wcześniej na telefonie
       `plan`, `graf` i `statystyki` były po prostu nieklikalne. */
    overflow-x: auto;
    scrollbar-width: none;
    max-width: 100%;
    min-width: 0;
    flex: 1 1 auto;
  }
  .right::-webkit-scrollbar {
    display: none;
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
    min-width: 0;
    max-width: 100vw;
  }
  main.queue-hidden {
    grid-template-columns: 28px minmax(320px, 0.9fr) minmax(0, 1.3fr);
  }
  main.list-hidden {
    grid-template-columns: 220px 28px minmax(0, 1fr);
  }
  main.queue-hidden.list-hidden {
    grid-template-columns: 28px 28px minmax(0, 1fr);
  }

  /* Zwinięty panel jako pionowa zakładka przy krawędzi. */
  .rail {
    display: flex;
    align-items: center;
    justify-content: center;
    border-right: 1px solid var(--border);
    background: var(--bg-deep);
    color: var(--muted);
    padding: 0;
  }
  .rail:hover {
    color: var(--text);
    background: var(--panel);
  }
  .rail span {
    writing-mode: vertical-rl;
    transform: rotate(180deg);
    font-size: 11px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    white-space: nowrap;
  }

  /* Telefon: jedna kolumna na pracę, panele wjeżdżają NAD nią.
     Wcześniej układ trzymał siatkę kolumn także przy 412 px, więc graf dostawał
     sto kilkadziesiąt pikseli i wyglądał na zepsuty. */
  main.narrow,
  main.narrow.lens,
  main.narrow.queue-hidden,
  main.narrow.list-hidden,
  main.narrow.lens.queue-hidden,
  main.narrow.queue-hidden.list-hidden,
  main.narrow.lens.queue-hidden.list-hidden {
    grid-template-columns: minmax(0, 1fr);
    position: relative;
  }
  main.narrow > :global(.side-panel) {
    position: absolute;
    top: 0;
    bottom: 0;
    left: 0;
    z-index: 20;
    width: min(86vw, 340px);
    box-shadow: 0 0 28px rgba(1, 4, 9, 0.6);
  }
  /* Zwinięty panel na telefonie to wąska zakładka przyklejona do krawędzi. */
  main.narrow .rail {
    position: absolute;
    top: 0;
    bottom: 0;
    left: 0;
    z-index: 19;
    width: 30px;
    border-right: 1px solid var(--border);
  }
  main.narrow.queue-hidden .rail:nth-of-type(2),
  main.narrow .rail + .rail {
    left: 30px;
  }
  /* Zakładka stoi NAD panelem roboczym, więc bez tego zjadała mu lewą krawędź:
     na telefonie ginął nagłówek grafu i podpis pod nim. Panel zaczyna się za szynami. */
  main.narrow:has(.rail) > :global(:not(.rail):not(.side-panel)) {
    margin-left: 30px;
  }
  main.narrow:has(.rail + .rail) > :global(:not(.rail):not(.side-panel)) {
    margin-left: 60px;
  }

  .mode-select {
    display: none;
    max-width: 128px;
    padding: 3px 6px;
    background: var(--panel-2);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 999px;
    font-size: 11px;
  }

  .panel-toggle {
    padding: 2px 8px;
    border: 1px solid var(--border);
    border-radius: 999px;
    color: var(--muted);
    font-size: 11px;
  }
  .panel-toggle.off {
    opacity: 0.45;
  }
  .panel-toggle:hover {
    color: var(--text);
    border-color: var(--accent-dim);
  }

  /* Graf to soczewka na całą paczkę: viewer ma własne trzy panele, więc w wąskiej
     kolumnie zostawał mu pasek na sam rysunek. Lista przedmiotów wraca klawiszem `b`. */
  main.lens {
    grid-template-columns: 220px minmax(0, 1fr);
  }
  main.lens.queue-hidden {
    grid-template-columns: 28px minmax(0, 1fr);
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
  /* Poniżej tej szerokości liczniki i ścieżka bazy ustępują miejsca zakładkom:
     te same liczby są w zakładce „statystyki", a zakładki muszą być klikalne. */
  @media (max-width: 1100px) {
    /* Przyciski trybów ustępują liście: w pasku mieści się ich najwyżej kilka,
       a jest ich osiem (zgłoszone 2026-09-24). */
    .mode-toggle {
      display: none;
    }
    .mode-select {
      display: block;
    }
    .totals {
      display: none;
    }
    .right .db {
      display: none;
    }
    .brand .phase {
      display: none;
    }
  }
  @media (max-width: 700px) {
    header {
      flex-wrap: wrap;
    }
    .right {
      width: 100%;
      margin-left: 0;
      justify-content: flex-start;
    }
  }

  /* Nie ma tu reguły chowającej panele na wąskim ekranie. Była i szkodziła:
     `main > aside { display: none }` poniżej 1100 px gasiło panel niezależnie od tego,
     czy jest rozwinięty, więc na telefonie przycisk „rozwiń" nic nie pokazywał.
     O tym, co widać, decyduje stan aplikacji (`defaultPanels`), a CSS go rysuje. */
</style>
