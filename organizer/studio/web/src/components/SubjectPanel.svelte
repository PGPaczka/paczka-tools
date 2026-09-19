<script lang="ts">
  import type { ItemsPage, SubjectDetail, SubjectRow } from '../lib/api';
  import { count, percent, stamp } from '../lib/format';
  import Bar from './Bar.svelte';
  import ItemList from './ItemList.svelte';

  let {
    row,
    detail,
    page,
    loading,
    error,
    category = $bindable<string | null>(null),
    onlyReview = $bindable(false),
    onMore,
  }: {
    row: SubjectRow | null;
    detail: SubjectDetail | null;
    page: ItemsPage | null;
    loading: boolean;
    error: string | null;
    category: string | null;
    onlyReview: boolean;
    onMore: () => void;
  } = $props();

  /** Kolory kubełków pewności — te same znaczenia, co w etykietach pozycji. */
  const bucketColors: Record<string, string> = {
    auto: 'var(--green)',
    review: 'var(--amber)',
    unresolved: 'var(--red)',
    brak: 'var(--panel-3)',
  };
</script>

<section>
  {#if !row}
    <div class="blank">
      <h2>Wybierz przedmiot</h2>
      <p>
        Po lewej kolejka: <em>plan do przeglądu</em> to przedmioty, w których coś czeka na
        oko. Klawisze: <kbd>/</kbd> szukaj, <kbd>j</kbd>/<kbd>k</kbd> ruch po liście,
        <kbd>Enter</kbd> otwórz, <kbd>Esc</kbd> wyczyść filtry.
      </p>
    </div>
  {:else}
    <header>
      <div class="title">
        <h2>{row.skrot} · {row.nazwa.replaceAll('_', ' ')}</h2>
        <span class="tag">{row.stage}</span>
      </div>
      <div class="path mono">{row.target_dir}</div>
      <div class="chips">
        <span class="chip">SEM{row.semester}</span>
        <span class="chip">{row.grupa}</span>
        {#each row.forms as form (form)}<span class="chip">{form}</span>{/each}
        {#each row.aliases as alias (alias)}<span class="chip dim">{alias}</span>{/each}
        <span class="when">ostatni plan: {stamp(row.decided_at)}</span>
      </div>
    </header>

    {#if error}
      <p class="error">{error}</p>
    {/if}

    {#if detail}
      <div class="tiles">
        <div class="tile">
          <span class="num">{count(detail.planned)}</span>
          <small>w planie</small>
        </div>
        <div class="tile" class:warn={detail.needs_review > 0}>
          <span class="num">{count(detail.needs_review)}</span>
          <small>do obejrzenia</small>
        </div>
        <div class="tile">
          <span class="num">{count(detail.ground_truth)}</span>
          <small>już w paczce</small>
        </div>
        <div class="tile">
          <span class="num">{count(detail.outdated)}</span>
          <small>nieaktualne</small>
        </div>
      </div>

      <div class="panels">
        <div class="panel">
          <h3>Pewność</h3>
          <Bar
            height={6}
            segments={Object.entries(detail.confidence.buckets).map(([name, value]) => ({
              value,
              color: bucketColors[name] ?? 'var(--gray)',
              label: name,
            }))}
          />
          <ul class="legend">
            {#each Object.entries(detail.confidence.buckets) as [name, value] (name)}
              <li>
                <span class="dot" style="background: {bucketColors[name] ?? 'var(--gray)'}"></span>
                {name}
                <span class="num">{count(value)}</span>
              </li>
            {/each}
          </ul>
          <p class="hint">
            progi z <span class="mono">thresholds.yaml</span>: auto ≥
            {percent(detail.confidence.thresholds.auto_apply)}, review ≥
            {percent(detail.confidence.thresholds.review_min)}
          </p>
        </div>

        <div class="panel">
          <h3>Akcje i metody</h3>
          <ul class="pairs">
            {#each Object.entries(detail.actions) as [name, value] (name)}
              <li><span class="tag {name}">{name}</span><span class="num">{count(value)}</span></li>
            {/each}
            {#each Object.entries(detail.methods) as [name, value] (name)}
              <li><span class="dim">{name}</span><span class="num">{count(value)}</span></li>
            {/each}
          </ul>
        </div>
      </div>

      <div class="panel">
        <h3>Kategorie</h3>
        <ul class="categories">
          <li>
            <button class:active={category === null} onclick={() => (category = null)}>
              <span class="name">wszystkie</span>
              <span class="num">{count(detail.planned)}</span>
            </button>
          </li>
          {#each detail.categories as entry (entry.category)}
            <li>
              <button
                class:active={category === entry.category}
                onclick={() => (category = category === entry.category ? null : entry.category)}
              >
                <span class="name">{entry.category}</span>
                {#if entry.needs_review > 0}
                  <span class="tag review num">{count(entry.needs_review)}</span>
                {/if}
                <span class="num">{count(entry.count)}</span>
              </button>
            </li>
          {/each}
        </ul>
      </div>
    {/if}

    <div class="items-head">
      <h3>
        Pozycje
        {#if page}<span class="num dim">&nbsp;{count(page.total)}</span>{/if}
      </h3>
      <label>
        <input type="checkbox" bind:checked={onlyReview} />
        tylko do obejrzenia
      </label>
    </div>

    <ItemList {page} {loading} {onMore} />
  {/if}
</section>

<style>
  section {
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-height: 0;
    padding: 14px 16px 24px;
    overflow-y: auto;
    background: var(--bg);
  }

  .blank {
    margin: auto;
    max-width: 30rem;
    text-align: center;
    color: var(--muted);
  }
  .blank h2 {
    margin: 0 0 6px;
    font-size: 15px;
    color: var(--text);
  }
  kbd {
    padding: 0 5px;
    border: 1px solid var(--border);
    border-bottom-width: 2px;
    border-radius: 4px;
    background: var(--panel-2);
    font-family: var(--font-mono);
    font-size: 11px;
  }

  header {
    display: flex;
    flex-direction: column;
    gap: 5px;
  }
  .title {
    display: flex;
    align-items: baseline;
    gap: 10px;
  }
  h2 {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
  }
  .path {
    color: var(--muted-2);
  }
  .chips {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
    font-size: 11px;
    color: var(--muted);
  }
  .chip {
    padding: 0 6px;
    border-radius: 4px;
    background: var(--panel-2);
  }
  .chip.dim,
  .dim {
    color: var(--muted-2);
  }
  .when {
    margin-left: auto;
    color: var(--muted-2);
  }

  .tiles {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 8px;
  }
  .tile {
    display: flex;
    flex-direction: column;
    gap: 1px;
    padding: 9px 12px;
    border: 1px solid var(--border-2);
    border-radius: 8px;
    background: var(--panel);
  }
  .tile span {
    font-size: 19px;
    line-height: 1.2;
    font-weight: 600;
  }
  .tile small {
    color: var(--muted);
    font-size: 11px;
  }
  .tile.warn span {
    color: var(--amber);
  }

  .panels {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 10px;
  }
  .panel {
    display: flex;
    flex-direction: column;
    gap: 7px;
    padding: 10px 12px;
    border: 1px solid var(--border-2);
    border-radius: 8px;
    background: var(--panel);
  }
  h3 {
    margin: 0;
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--muted-2);
  }

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    font-size: 11px;
    color: var(--muted);
  }
  .legend li {
    display: flex;
    align-items: center;
    gap: 5px;
  }
  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
  }
  .hint {
    margin: 0;
    font-size: 11px;
    color: var(--muted-2);
  }

  .pairs {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 14px;
  }
  .pairs li {
    display: flex;
    align-items: center;
    gap: 6px;
    color: var(--muted);
  }

  .categories {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
    gap: 2px;
  }
  .categories button {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 3px 8px;
    border-radius: 6px;
    color: var(--muted);
  }
  .categories button:hover {
    background: var(--panel-2);
    color: var(--text);
  }
  .categories button.active {
    background: var(--panel-3);
    color: var(--text);
  }
  .categories button .num:last-child {
    min-width: 3.4em;
    text-align: right;
  }
  .categories .name {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    text-align: left;
  }

  .items-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-top: 2px;
  }
  .items-head label {
    display: flex;
    align-items: center;
    gap: 6px;
    color: var(--muted);
    cursor: pointer;
  }

  .error {
    margin: 0;
    padding: 8px 10px;
    border: 1px solid rgba(248, 81, 73, 0.4);
    border-radius: 7px;
    color: var(--red);
    background: rgba(248, 81, 73, 0.08);
  }
</style>
