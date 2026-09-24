<script lang="ts">
  import {
    getPlan,
    getPlanConflicts,
    getPlanTree,
    postDecision,
    renameTarget,
    runStage,
    type PlanConflicts,
    type PlanOverview,
    type PlanTree,
    type Stage,
  } from '../lib/api';
  import { basename, bytes, count, percent } from '../lib/format';
  import { collisionAt, moveTarget } from '../lib/plan';

  interface Props {
    semester?: number | null;
    skrot?: string | null;
    grupa?: string | null;
    onChanged?: () => void;
  }

  let { semester = null, skrot = null, grupa = null, onChanged }: Props = $props();

  let plan = $state<PlanOverview | null>(null);
  let tree = $state<PlanTree | null>(null);
  let error = $state<string | null>(null);

  let log = $state<string[]>([]);
  let running = $state<Stage | null>(null);
  let lastCode = $state<number | null>(null);
  let console_: HTMLElement | undefined = $state();

  /** „Przenieś tu”: wybrana pozycja bez miejsca + wybrany katalog drzewa. */
  let pickedItem = $state<string | null>(null);
  let pickedFolder = $state<string | null>(null);
  let moveNote = $state<string | null>(null);

  /** Konflikty ścieżek docelowych. Liczone z bazy, nie z pliku planu, więc naprawa
   *  widać od razu — bez ponownego budowania planu. */
  let conflicts = $state<PlanConflicts | null>(null);
  /** sha treści, której nazwę właśnie poprawiamy, i brudnopis nazwy. */
  let renaming = $state<string | null>(null);
  let renameDraft = $state('');

  /** Katalogi rozwinięte ręcznie. Domyślnie zwinięte: przedmiot ma ich sto
   *  kilkadziesiąt i po rozwinięciu wszystkich drzewo przestaje być drzewem. */
  let expanded = $state<Record<string, boolean>>({});

  const stages: Array<{ id: Stage; label: string; title: string }> = [
    { id: 'plan', label: 'zbuduj plan', title: 'build_plan.py — scala decyzje w jeden plan' },
    { id: 'validate', label: 'waliduj', title: 'validate_plan.py — bramka; kod 2 = nie wykonuj' },
    { id: 'review', label: 'review.html', title: 'review_report.py — strona do obejrzenia' },
    { id: 'apply-dry', label: 'apply (dry-run)', title: 'apply.py bez --yes — niczego nie kopiuje' },
    { id: 'verify', label: 'verify', title: 'verify.py — hash po kopii wobec planu' },
  ];

  const homelessItem = $derived(
    (tree?.homeless ?? []).find((item) => item.sha256 === pickedItem) ?? null,
  );

  /** Ścieżka docelowa i ewentualna kolizja — liczone w `lib/plan.ts`, z testami. */
  const target = $derived(moveTarget(pickedFolder, homelessItem?.filename ?? null));
  const collision = $derived(collisionAt(tree, target));

  async function load(): Promise<void> {
    if (!semester || !skrot) return;
    try {
      [plan, tree, conflicts] = await Promise.all([
        getPlan(semester, skrot, grupa ?? undefined),
        getPlanTree(semester, skrot, grupa ?? undefined),
        getPlanConflicts({ semester, skrot }),
      ]);
      error = null;
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc);
    }
  }

  function startRename(sha: string, path: string): void {
    renaming = sha;
    renameDraft = basename(path);
  }

  /** Kursor w nazwie, zaznaczony rdzeń: poprawia się nazwę, nie rozszerzenie. */
  function focusName(node: HTMLInputElement): void {
    node.focus();
    const dot = node.value.lastIndexOf('.');
    node.setSelectionRange(0, dot > 0 ? dot : node.value.length);
  }

  async function saveRename(sha: string): Promise<void> {
    if (!renameDraft.trim()) return;
    error = null;
    try {
      await renameTarget(sha, renameDraft.trim());
      renaming = null;
      onChanged?.();
      await load();
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc);
    }
  }

  async function run(stage: Stage, confirm = false): Promise<void> {
    if (!semester || !skrot || running) return;
    running = stage;
    lastCode = null;
    log = [];
    try {
      lastCode = await runStage(
        semester,
        skrot,
        { stage, confirm, plan_hash: plan?.plan?.plan_hash },
        (line) => {
          log = [...log, line];
          queueMicrotask(() => console_?.scrollTo({ top: console_.scrollHeight }));
        },
        grupa ?? undefined,
      );
    } catch (exc) {
      // Odmowa bramki wraca tutaj jako wyjątek z treścią z serwera — pokazujemy ją
      // dosłownie, bo to jest powód, dla którego etap nie ruszył.
      log = [...log, exc instanceof Error ? exc.message : String(exc)];
      lastCode = 409;
    } finally {
      running = null;
      await load();
      onChanged?.();
    }
  }

  async function applyNow(): Promise<void> {
    if (!plan?.plan) return;
    const question =
      `Wykonać plan ${plan.plan.plan_hash.slice(0, 12)}…?\n\n` +
      `Do paczki dojdzie ${plan.diff?.new ?? 0} plików w ${plan.diff?.folders ?? 0} katalogach.\n` +
      'Materiały zostaną skopiowane do repo; commit robisz sam po verify.';
    if (!globalThis.confirm(question)) return;
    await run('apply', true);
  }

  async function moveHere(): Promise<void> {
    if (!homelessItem || !target || collision || !semester || !skrot) return;
    moveNote = null;
    try {
      await postDecision({
        sha256: homelessItem.sha256,
        decision_type: 'classify',
        semester,
        subject_key: skrot,
        category: pickedFolder?.split('/').pop() ?? undefined,
        target_relative_path: target,
        action: 'copy',
      });
      pickedItem = null;
      moveNote = 'Decyzja zapisana. Żeby weszła do drzewa, zbuduj plan na nowo.';
      await load();
      onChanged?.();
    } catch (exc) {
      moveNote = exc instanceof Error ? exc.message : String(exc);
    }
  }

  $effect(() => {
    const _deps = [semester, skrot, grupa];
    plan = null;
    tree = null;
    load();
  });
</script>

<section class="plan-panel">
  {#if !semester || !skrot}
    <p class="empty">Wybierz przedmiot, żeby zobaczyć jego plan.</p>
  {:else if error}
    <p class="error">{error}</p>
  {:else if plan}
    <header>
      <div class="title">
        <h3>Plan · {plan.subject.skrot}</h3>
        {#if plan.plan}
          <span class="mono dim">{plan.plan.plan_hash.slice(0, 12)}…</span>
          <span class="dim">{count(plan.plan.items)} pozycji</span>
          {#each Object.entries(plan.plan.actions) as [name, value] (name)}
            <span class="tag {name}">{name} {count(value)}</span>
          {/each}
        {:else}
          <span class="dim">{plan.reason}</span>
        {/if}
      </div>
      <div class="mono dim path">{plan.subject.target_dir}</div>
    </header>

    <!-- Bramka. Kolor mówi to samo, co kod wyjścia validate_plan. -->
    <div class="gate" class:ok={plan.can_apply} class:bad={!plan.can_apply}>
      {#if plan.validation}
        <span><b>{count(plan.validation.errors)}</b> błędów</span>
        <span><b>{count(plan.validation.warnings)}</b> ostrzeżeń</span>
      {/if}
      {#if plan.diff}
        <span class="sep">·</span>
        <span>dojdzie <b>{count(plan.diff.new)}</b> plików w {count(plan.diff.folders)} katalogach</span>
        <span>już jest <b>{count(plan.diff.present)}</b></span>
        {#if plan.diff.conflict}<span class="bad-text">kolizje <b>{count(plan.diff.conflict)}</b></span>{/if}
        {#if plan.diff.missing_source}
          <span class="bad-text">bez źródła <b>{count(plan.diff.missing_source)}</b></span>
        {/if}
      {/if}
      <span class="verdict">{plan.can_apply ? 'plan przechodzi bramkę' : plan.reason}</span>
    </div>

    {#if conflicts && conflicts.total}
      <!-- Bramka mówi „kolizja_celu" dopiero przy validate i tylko tekstem. Tu widać,
           KTO się bije o ścieżkę, i da się to rozstrzygnąć bez wychodzenia z widoku. -->
      <div class="conflicts">
        <div class="conflicts-head">
          <strong>Konflikty ścieżek</strong>
          <span class="num">{count(conflicts.total)}</span>
          <span class="dim">dwie treści w jednym pliku — zmień nazwę jednej z nich</span>
        </div>
        {#each conflicts.conflicts as conflict (conflict.path)}
          <div class="conflict">
            <div class="conflict-path mono">
              {conflict.path}
              {#if conflict.kind === 'applied'}
                <span class="tag applied">leży już w paczce</span>
              {/if}
            </div>
            {#each conflict.contents as item (item.sha256)}
              <div class="rival">
                <span class="mono">{item.filename ?? item.sha256.slice(0, 12)}</span>
                {#if item.size_bytes}<span class="dim">{bytes(item.size_bytes)}</span>{/if}
                {#if item.confidence !== null}
                  <span class="dim">{percent(item.confidence)}</span>
                {/if}
                <span class="mono dim src" title={item.source_relative_path ?? ''}>
                  {item.source_relative_path ?? ''}
                </span>
                {#if renaming === item.sha256}
                  <input
                    class="mono rename-input"
                    bind:value={renameDraft}
                    spellcheck="false"
                    use:focusName
                    onkeydown={(e) => {
                      if (e.key === 'Enter') { e.preventDefault(); saveRename(item.sha256); }
                      if (e.key === 'Escape') { e.preventDefault(); renaming = null; }
                    }}
                  />
                  <button onclick={() => saveRename(item.sha256)}>zapisz</button>
                {:else}
                  <button onclick={() => startRename(item.sha256, conflict.path)}>zmień nazwę</button>
                {/if}
              </div>
            {/each}
          </div>
        {/each}
      </div>
    {/if}

    <div class="stages">
      {#each stages as stage (stage.id)}
        <button disabled={running !== null} title={stage.title} onclick={() => run(stage.id)}>
          {running === stage.id ? '…' : stage.label}
        </button>
      {/each}
      <button
        class="apply"
        disabled={running !== null || !plan.can_apply}
        title={plan.can_apply
          ? 'apply.py --yes — kopiuje materiały do repo paczki'
          : `nie do wykonania: ${plan.reason}`}
        onclick={applyNow}
      >
        {running === 'apply' ? 'kopiuję…' : 'APPLY'}
      </button>
      {#if lastCode !== null}
        <span class="code" class:bad={lastCode !== 0}>kod wyjścia {lastCode}</span>
      {/if}
    </div>

    <div class="columns">
      <div class="tree">
        <h4>Drzewo docelowe {#if tree}<span class="dim num">{count(tree.files)}</span>{/if}</h4>
        {#each tree?.folders ?? [] as folder (folder.path)}
          <div class="folder" class:picked={pickedFolder === folder.path}>
            <div class="folder-row">
              <button
                class="folder-head"
                onclick={() => (expanded = { ...expanded, [folder.path]: !expanded[folder.path] })}
              >
                <span class="caret">{expanded[folder.path] ? '▾' : '▸'}</span>
                <span class="mono">{folder.path.replace(plan.subject.target_dir + '/', '')}</span>
                <span class="dim num">{folder.files.length}</span>
              </button>
              {#if pickedItem}
                <button
                  class="here"
                  class:active={pickedFolder === folder.path}
                  title="przenieś tu wybraną pozycję"
                  onclick={() => (pickedFolder = folder.path)}
                >
                  tu
                </button>
              {/if}
            </div>
            <ul class:hidden={!expanded[folder.path]}>
              {#each folder.files.slice(0, 40) as file (file.path)}
                <li class={file.state} title={file.detail || file.state}>
                  <span class="mark">{file.state === 'new' ? '+' : file.state === 'ground_truth' ? '·' : file.state === 'present' ? '=' : '!'}</span>
                  {file.name}
                </li>
              {/each}
              {#if folder.files.length > 40}
                <li class="dim">… i {count(folder.files.length - 40)} więcej</li>
              {/if}
            </ul>
          </div>
        {/each}
      </div>

      <div class="console">
        <h4>Etap</h4>
        <pre bind:this={console_}>{log.join('\n') || 'Uruchom etap — zobaczysz jego wyjście na żywo.'}</pre>
      </div>
    </div>

    <div class="homeless">
      <h4>
        Bez miejsca w drzewie
        {#if tree}<span class="dim num">{count(tree.homeless.length)}</span>{/if}
      </h4>
      {#if pickedItem}
        <div class="move" class:bad={collision !== null}>
          <span class="mono">{homelessItem?.filename}</span>
          →
          <span class="mono">{target ?? 'wybierz katalog w drzewie'}</span>
          {#if collision}
            <span class="bad-text">kolizja: pod tą nazwą już coś stoi ({collision.state})</span>
          {/if}
          <button disabled={!target || collision !== null} onclick={moveHere}>przenieś tu</button>
          <button class="ghost" onclick={() => (pickedItem = null)}>anuluj</button>
        </div>
      {/if}
      {#if moveNote}<p class="note">{moveNote}</p>{/if}
      <ul class="items">
        {#each (tree?.homeless ?? []).slice(0, 60) as item (item.sha256)}
          <li>
            <button class:active={pickedItem === item.sha256} onclick={() => (pickedItem = item.sha256)}>
              <span class="name">{item.filename}</span>
              {#if item.action}<span class="tag {item.action}">{item.action}</span>{/if}
              {#if item.needs_review}<span class="tag review">do obejrzenia</span>{/if}
              <span class="dim num">{percent(item.confidence)}</span>
              <span class="dim reason">{item.reason ?? ''}</span>
            </button>
          </li>
        {/each}
      </ul>
      {#if (tree?.homeless.length ?? 0) > 60}
        <p class="dim">… i {count((tree?.homeless.length ?? 0) - 60)} więcej — rozstrzygnij je w kolejce decyzji</p>
      {/if}
    </div>
  {/if}
</section>

<style>
  .plan-panel {
    display: flex;
    flex-direction: column;
    gap: 10px;
    min-height: 0;
    padding: 12px 14px 20px;
    overflow-y: auto;
  }

  header {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .title {
    display: flex;
    align-items: baseline;
    gap: 10px;
    flex-wrap: wrap;
  }
  h3 {
    margin: 0;
    font-size: 14px;
    font-weight: 600;
  }
  h4 {
    margin: 0 0 6px;
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--muted-2);
  }
  .path {
    color: var(--muted-2);
  }

  .gate {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    padding: 8px 12px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--panel);
    color: var(--muted);
  }
  .gate b {
    color: var(--text);
  }
  .gate.ok {
    border-color: rgba(63, 185, 80, 0.45);
  }
  .gate.bad {
    border-color: rgba(248, 81, 73, 0.45);
    background: rgba(248, 81, 73, 0.06);
  }
  .gate .verdict {
    margin-left: auto;
    font-weight: 600;
    color: var(--text);
  }
  .gate.bad .verdict {
    color: var(--red);
  }
  .bad-text {
    color: var(--red);
  }
  .sep {
    color: var(--border);
  }

  .conflicts {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 8px 10px;
    border: 1px solid var(--amber);
    border-radius: 7px;
    background: rgba(210, 153, 34, 0.06);
  }
  .conflicts-head {
    display: flex;
    align-items: baseline;
    gap: 10px;
    flex-wrap: wrap;
  }
  .conflict {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .conflict-path {
    font-size: 11px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .conflict-path .tag.applied {
    margin-left: 6px;
    padding: 0 6px;
    border-radius: 999px;
    background: var(--amber);
    color: var(--bg-deep);
    font-size: 10px;
  }
  .rival {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    padding-left: 12px;
    font-size: 11px;
  }
  /* Ścieżka źródłowa ustępuje miejsca: to ona mówi, która kopia jest która,
     ale nie może zepchnąć przycisku poza ekran telefonu. */
  .rival .src {
    flex: 1 1 8rem;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .rival button,
  .conflicts button {
    padding: 2px 10px;
    border: 1px solid var(--border);
    border-radius: 999px;
    color: var(--muted);
    font-size: 10px;
  }
  .rival button:hover {
    color: var(--text);
    border-color: var(--accent-dim);
  }
  .rename-input {
    flex: 1 1 10rem;
    min-width: 8rem;
    padding: 2px 6px;
    border: 1px solid var(--border);
    border-radius: 5px;
    background: var(--bg-deep);
    color: var(--text);
    font-size: 11px;
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
    color: var(--muted);
  }
  .stages button:hover:not(:disabled) {
    color: var(--text);
    border-color: var(--accent-dim);
  }
  .stages button:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .stages .apply {
    margin-left: auto;
    border-color: rgba(63, 185, 80, 0.5);
    color: var(--green);
    font-weight: 600;
  }
  .stages .apply:disabled {
    border-color: var(--border);
    color: var(--muted-2);
  }
  .code {
    color: var(--green);
    font-family: var(--font-mono);
    font-size: 11px;
  }
  .code.bad {
    color: var(--red);
  }

  .columns {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 10px;
    min-height: 260px;
  }
  .tree,
  .console {
    padding: 10px 12px;
    border: 1px solid var(--border-2);
    border-radius: 8px;
    background: var(--panel);
    overflow: auto;
    max-height: 46vh;
  }

  .folder {
    margin-bottom: 4px;
  }
  .folder-row {
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .caret {
    width: 10px;
    color: var(--muted-2);
  }
  .here {
    padding: 0 8px;
    border: 1px solid var(--accent-dim);
    border-radius: 999px;
    font-size: 10.5px;
    color: var(--accent);
  }
  .here.active {
    background: var(--accent-dim);
    color: var(--text);
  }
  ul.hidden {
    display: none;
  }
  .folder-head {
    display: flex;
    gap: 8px;
    width: 100%;
    padding: 2px 6px;
    border-radius: 5px;
    color: var(--muted);
    text-align: left;
  }
  .folder-head:hover {
    background: var(--panel-2);
    color: var(--text);
  }
  .folder.picked .folder-head {
    background: var(--panel-3);
    color: var(--text);
    box-shadow: inset 2px 0 0 var(--accent);
  }
  .folder-head .num {
    margin-left: auto;
  }
  .folder ul {
    margin: 0;
    padding: 0 0 0 16px;
    list-style: none;
    font-size: 11px;
  }
  .folder li {
    color: var(--muted-2);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .folder li.new {
    color: var(--green);
  }
  .folder li.ground_truth {
    color: var(--accent);
    opacity: 0.8;
  }
  .folder li.conflict,
  .folder li.missing_source,
  .folder li.outside {
    color: var(--red);
  }
  .mark {
    display: inline-block;
    width: 10px;
    font-family: var(--font-mono);
  }

  .console pre {
    margin: 0;
    white-space: pre-wrap;
    word-break: break-word;
    font-family: var(--font-mono);
    font-size: 11px;
    line-height: 1.5;
    color: var(--text);
  }

  .homeless .items {
    margin: 0;
    padding: 0;
    list-style: none;
    max-height: 30vh;
    overflow-y: auto;
  }
  .homeless li button {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 3px 8px;
    border-radius: 6px;
    text-align: left;
    color: var(--muted);
  }
  .homeless li button:hover {
    background: var(--panel);
    color: var(--text);
  }
  .homeless li button.active {
    background: var(--panel-2);
    box-shadow: inset 2px 0 0 var(--accent);
    color: var(--text);
  }
  .homeless .name {
    min-width: 12rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .homeless .reason {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .move {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin-bottom: 6px;
    padding: 6px 10px;
    border: 1px solid var(--accent-dim);
    border-radius: 7px;
    background: var(--panel);
  }
  .move.bad {
    border-color: rgba(248, 81, 73, 0.5);
  }
  .move button {
    padding: 2px 10px;
    border: 1px solid var(--border);
    border-radius: 999px;
    color: var(--muted);
  }
  .move button:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .move .ghost {
    border-color: transparent;
  }
  .note {
    margin: 0 0 6px;
    color: var(--amber);
    font-size: 11px;
  }

  .dim {
    color: var(--muted-2);
  }
  .empty,
  .error {
    margin: auto;
    color: var(--muted);
  }
  .error {
    padding: 8px 10px;
    border: 1px solid rgba(248, 81, 73, 0.4);
    border-radius: 7px;
    color: var(--red);
  }
</style>
