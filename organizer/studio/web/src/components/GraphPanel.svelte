<script lang="ts">
  import {
    getGraphContent,
    getGraphStatus,
    getGraphSubject,
    graphUrl,
    rebuildGraph,
    type GraphContentRef,
    type GraphStatus,
  } from '../lib/api';
  import { bytes, percent } from '../lib/format';

  interface Props {
    semester?: number | null;
    skrot?: string | null;
    grupa?: string | null;
    /** Treść, na której graf ma się otworzyć (kierunek: studio → graf). */
    focusNode?: string | null;
    /** „Otwórz przedmiot” — powrót z grafu do listy studia. */
    onOpenSubject?: (semester: number, skrot: string) => void;
  }

  let { semester = null, skrot = null, grupa = null, focusNode = null, onOpenSubject }: Props =
    $props();

  let status = $state<GraphStatus | null>(null);
  let error = $state<string | null>(null);
  let frame = $state<HTMLIFrameElement | undefined>();
  let src = $state<string | null>(null);
  let picked = $state<GraphContentRef | null>(null);
  let pickError = $state<string | null>(null);

  /** Ostatni adres, jaki sami ustawiliśmy — żeby nie przeładowywać ramki w kółko. */
  let applied = '';

  /** Przebudowa danych grafu — graf jest migawką, więc decyzje widać dopiero po niej. */
  let rebuilding = $state(false);
  let log = $state<string[]>([]);
  let rebuildError = $state<string | null>(null);
  let rebuiltAt = $state<string | null>(null);

  async function rebuild(): Promise<void> {
    if (rebuilding) return;
    rebuilding = true;
    rebuildError = null;
    log = [];
    try {
      const code = await rebuildGraph((line) => {
        // Trzymamy ogon logu: generator wypisuje kilkaset linii, a liczy się koniec.
        log = [...log, line].slice(-14);
      });
      if (code !== 0) {
        rebuildError = `przebudowa zakończyła się kodem ${code}`;
        return;
      }
      status = await getGraphStatus();
      rebuiltAt = new Date().toLocaleTimeString('pl-PL');
      // Viewer czyta `graph.json` przy starcie, więc świeże dane widać dopiero po
      // przeładowaniu ramki. Samo podmienienie `src` nie wystarcza (ten sam adres).
      frame?.contentWindow?.location.reload();
    } catch (exc) {
      rebuildError = exc instanceof Error ? exc.message : String(exc);
    } finally {
      rebuilding = false;
    }
  }

  /**
   * Viewer czyta zaznaczony węzeł z fragmentu URL-a, ale TYLKO przy montowaniu.
   * Sama podmiana `#` w atrybucie `src` nie nawiguje istniejącej ramki (sprawdzone:
   * atrybut się zmieniał, `location.hash` w ramce zostawał pusty), więc pierwszy
   * adres ustawiamy przed utworzeniem ramki, a każdy kolejny przez `location.replace`.
   */
  function goTo(next: string): void {
    if (next === applied) return;
    applied = next;
    const view = frame?.contentWindow;
    if (view && src !== null) {
      view.location.replace(next);
    } else {
      src = next;
    }
  }

  /** Węzeł pliku kończy się skrótem sha; semestr i przedmiot — nie. */
  const FILE_NODE = /-[0-9a-f]{8}$/;

  async function resolve(node: string): Promise<void> {
    pickError = null;
    if (!FILE_NODE.test(node)) {
      // Węzeł semestru albo przedmiotu nie wskazuje pojedynczej treści. To nie błąd,
      // tylko inny poziom grafu — nie strasz komunikatem o 404.
      picked = null;
      pickError = 'to węzeł przedmiotu albo semestru — kliknij plik, żeby wrócić do treści';
      return;
    }
    try {
      picked = await getGraphContent(node);
    } catch (exc) {
      picked = null;
      pickError = exc instanceof Error ? exc.message : String(exc);
    }
  }

  /** Viewer trzyma zaznaczenie w fragmencie URL-a, a ramka jest tego samego
   *  pochodzenia co studio — stąd powrót działa bez zmian w cudzym repo. */
  function watchFrame(): void {
    const view = frame?.contentWindow;
    if (!view) return;
    const read = () => {
      const node = view.location.hash.replace(/^#/, '');
      if (node) resolve(node);
    };
    read();
    view.addEventListener('hashchange', read);
    // Viewer dopasowuje widok do swojego rozmiaru przy starcie; w ramce ten rozmiar
    // ustala się po jego montowaniu, więc bez tego trącenia graf zostaje odsunięty
    // i widać same pyłki zamiast węzłów.
    setTimeout(() => view.dispatchEvent(new Event('resize')), 300);
  }

  $effect(() => {
    const controller = new AbortController();
    getGraphStatus(controller.signal)
      .then((value) => {
        status = value;
        error = null;
      })
      .catch((exc: unknown) => {
        if (!controller.signal.aborted) error = exc instanceof Error ? exc.message : String(exc);
      });
    return () => controller.abort();
  });

  $effect(() => {
    const sem = semester;
    const key = skrot;
    const node = focusNode;
    if (!status?.viewer_built) return;
    const controller = new AbortController();
    if (node) {
      goTo(graphUrl(node));
      return;
    }
    if (sem && key) {
      getGraphSubject(sem, key, grupa ?? undefined, controller.signal)
        .then((value) => goTo(graphUrl(value.node)))
        .catch(() => goTo(graphUrl()));
    } else {
      goTo(graphUrl());
    }
    return () => controller.abort();
  });
</script>

<section class="graph-panel">
  <header>
    <h3>Graf</h3>
    {#if status}
      <span class="dim num">{status.notes} notatek</span>
    {/if}
    {#if rebuiltAt}
      <span class="dim num">odświeżony {rebuiltAt}</span>
    {/if}
    <button class="rebuild" onclick={rebuild} disabled={rebuilding}
      title="Przelicz dane grafu z bazy — decyzje podjęte w studiu stają się widoczne">
      {rebuilding ? 'przebudowuję…' : 'przebuduj'}
    </button>
    <a class="external" href={src} target="_blank" rel="noreferrer">otwórz osobno ↗</a>
  </header>

  {#if rebuilding || rebuildError || log.length > 0}
    <div class="rebuild-log" class:failed={rebuildError !== null}>
      {#if rebuildError}<p class="error">{rebuildError}</p>{/if}
      <pre>{log.join('\n') || 'start…'}</pre>
    </div>
  {/if}

  {#if error}
    <p class="error">{error}</p>
  {:else if status && !status.viewer_built}
    <div class="missing">
      <p><strong>Graf nie jest zbudowany.</strong></p>
      <p class="dim">
        Studio osadza zbudowany viewer synapse z <code>vendor/synapse</code> — katalog jest
        poza gitem, więc w świeżym klonie go nie ma.
      </p>
      <pre>{status.hint}</pre>
    </div>
  {:else if status && src !== null}
    <iframe bind:this={frame} title="Graf paczki" {src} onload={watchFrame}></iframe>

    <footer>
      {#if picked?.item}
        <div class="picked">
          <span class="name">{picked.item.filename ?? picked.sha256?.slice(0, 12)}</span>
          {#if picked.item.category}<span class="tag">{picked.item.category}</span>{/if}
          {#if picked.item.action}<span class="tag {picked.item.action}">{picked.item.action}</span>{/if}
          <span class="dim num">{percent(picked.item.confidence)} · {bytes(picked.item.size_bytes)}</span>
          {#if picked.item.semester && picked.item.subject_key}
            <button
              onclick={() => onOpenSubject?.(picked!.item!.semester!, picked!.item!.subject_key!)}
            >
              otwórz przedmiot ({picked.item.subject_key})
            </button>
          {/if}
        </div>
        {#if picked.item.target_relative_path}
          <div class="mono dim target">→ {picked.item.target_relative_path}</div>
        {/if}
      {:else if picked && picked.candidates.length > 1}
        <p class="dim">
          Węzeł pasuje do {picked.candidates.length} treści — skrót sha jest wieloznaczny,
          wybierz ręcznie: {picked.candidates.map((c) => c.slice(0, 12)).join(', ')}
        </p>
      {:else}
        <p class="dim">
          {#if pickError}{pickError}{:else}Kliknij węzeł w grafie — pokażę, jaka treść za
            nim stoi i pozwolę wrócić do przedmiotu.{/if}
        </p>
      {/if}
    </footer>
  {/if}
</section>

<style>
  .rebuild {
    padding: 2px 10px;
    border: 1px solid var(--border);
    border-radius: 999px;
    color: var(--text);
    font-size: 11px;
  }
  .rebuild:hover:not(:disabled) {
    border-color: var(--accent-dim);
  }
  .rebuild:disabled {
    opacity: 0.55;
    cursor: default;
  }

  .rebuild-log {
    max-height: 168px;
    overflow: auto;
    padding: 6px 10px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-deep);
  }
  .rebuild-log.failed {
    border-left: 2px solid var(--red);
  }
  .rebuild-log pre {
    margin: 0;
    font-family: var(--font-mono);
    font-size: 11px;
    line-height: 1.5;
    color: var(--muted);
    white-space: pre-wrap;
    word-break: break-word;
  }

  .graph-panel {
    display: flex;
    flex-direction: column;
    min-height: 0;
    height: 100%;
    background: var(--bg);
  }

  header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    border-bottom: 1px solid var(--border);
  }
  h3 {
    margin: 0;
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--muted-2);
  }
  .external {
    margin-left: auto;
    color: var(--muted);
    text-decoration: none;
    font-size: 11px;
  }
  .external:hover {
    color: var(--accent);
  }

  iframe {
    flex: 1;
    width: 100%;
    border: 0;
    min-height: 0;
    background: var(--bg-deep);
  }

  footer {
    padding: 8px 12px;
    border-top: 1px solid var(--border);
    background: var(--panel);
  }
  .picked {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .picked .name {
    font-weight: 600;
  }
  .picked button {
    margin-left: auto;
    padding: 2px 10px;
    border: 1px solid var(--border);
    border-radius: 999px;
    color: var(--muted);
  }
  .picked button:hover {
    color: var(--text);
    border-color: var(--accent-dim);
  }
  .target {
    margin-top: 3px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .missing {
    margin: auto;
    max-width: 30rem;
    text-align: center;
    color: var(--muted);
  }
  .missing pre {
    display: inline-block;
    padding: 6px 12px;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--panel);
    font-family: var(--font-mono);
  }

  .dim {
    color: var(--muted-2);
  }
  .quiet {
    opacity: 0.7;
  }
  .error {
    margin: 12px;
    padding: 8px 10px;
    border: 1px solid rgba(248, 81, 73, 0.4);
    border-radius: 7px;
    color: var(--red);
    background: rgba(248, 81, 73, 0.08);
  }
</style>
