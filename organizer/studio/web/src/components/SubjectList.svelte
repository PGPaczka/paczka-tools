<script lang="ts">
  import type { SubjectRow } from '../lib/api';
  import { count, stamp } from '../lib/format';
  import Bar from './Bar.svelte';

  let {
    subjects,
    selected,
    onSelect,
    query = $bindable(''),
    semester = $bindable<number | null>(null),
    semesters,
    grupa = $bindable<string | null>(null),
    grupy = [],
    onClose,
  }: {
    subjects: SubjectRow[];
    selected: SubjectRow | null;
    onSelect: (row: SubjectRow) => void;
    query: string;
    semester: number | null;
    semesters: number[];
    grupa: string | null;
    /** Strumienie/katedry w wybranym semestrze; pusto = ten semestr ich nie ma. */
    grupy: string[];
    /** Zwinięcie panelu (przycisk w nagłówku listy). */
    onClose?: () => void;
  } = $props();

  let search: HTMLInputElement | undefined = $state();

  function onEnter(event: KeyboardEvent): void {
    if (event.key !== 'Enter' || !subjects.length) return;
    event.preventDefault();
    onSelect(subjects[0]);
    search?.blur();
  }

  export function focusSearch(): void {
    search?.focus();
    search?.select();
  }

  const key = (row: SubjectRow) => `${row.semester}/${row.grupa}/${row.skrot}`;
</script>

<section class="side-panel subject-list">
  <header>
    <div class="head-row">
      <span class="label">Przedmioty</span>
      {#if onClose}
        <button class="collapse" onclick={onClose} title="Zwiń listę" aria-label="Zwiń listę">×</button>
      {/if}
    </div>
    <input
      bind:this={search}
      bind:value={query}
      type="search"
      onkeydown={onEnter}
      placeholder="Szukaj przedmiotu  ( / )"
      aria-label="Szukaj przedmiotu"
    />
    <div class="semesters">
      <button class:active={semester === null} onclick={() => { semester = null; grupa = null; }}>
        wszystkie
      </button>
      {#each semesters as value (value)}
        <button class:active={semester === value} onclick={() => { semester = value; grupa = null; }}>
          {value}
        </button>
      {/each}
    </div>

    <!-- Drugi poziom wyboru: strumień (SEM5/6) albo katedra (SEM7). Pokazuje się
         tylko wtedy, gdy w tym semestrze naprawdę rozdziela przedmioty. -->
    {#if grupy.length}
      <div class="semesters grupy">
        <button class:active={grupa === null} onclick={() => (grupa = null)}>wszystkie grupy</button>
        {#each grupy as name (name)}
          <button class:active={grupa === name} onclick={() => (grupa = name)} title={name}>
            {name.replaceAll('_', ' ')}
          </button>
        {/each}
      </div>
    {/if}
  </header>

  <ol>
    {#each subjects as row (key(row))}
      <li>
        <button
          class:active={selected && key(selected) === key(row)}
          onclick={() => onSelect(row)}
          data-subject={key(row)}
        >
          <div class="line">
            <span class="sem">SEM{row.semester}</span>
            <span class="skrot">{row.skrot}</span>
            <span class="nazwa">{row.nazwa.replaceAll('_', ' ')}</span>
            {#if row.needs_review > 0}
              <span class="tag review num">{count(row.needs_review)} do obejrzenia</span>
            {/if}
          </div>
          <div class="line meta">
            <!-- Pasek to postęp PLANU tego przedmiotu. Ground truth jest obok liczbą:
                 wliczony w pasek dawał pełny pasek przy zerowym planie, czyli
                 „zrobione” tam, gdzie nikt jeszcze nic nie zaplanował. -->
            <Bar
              segments={[
                { value: row.planned - row.needs_review, color: 'var(--green)', label: 'zdecydowane' },
                { value: row.needs_review, color: 'var(--amber)', label: 'do obejrzenia' },
              ]}
            />
            <span class="num nums">
              {count(row.planned)} plan · {count(row.ground_truth)} w paczce
            </span>
            <span class="when">{stamp(row.decided_at)}</span>
          </div>
        </button>
      </li>
    {:else}
      <li class="empty">Nic nie pasuje do tego filtru.</li>
    {/each}
  </ol>
</section>

<style>
  section {
    display: flex;
    flex-direction: column;
    min-height: 0;
    border-right: 1px solid var(--border);
    background: var(--bg);
  }

  header {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-deep);
  }

  .head-row {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .head-row .label {
    font-size: 10.5px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--muted-2);
  }
  .collapse {
    margin-left: auto;
    width: 30px;
    height: 30px;
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--muted);
    font-size: 16px;
    line-height: 1;
  }
  .collapse:hover {
    color: var(--text);
    border-color: var(--accent-dim);
  }

  input {
    width: 100%;
    padding: 6px 10px;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--panel);
  }
  input:focus {
    outline: none;
    border-color: var(--accent-dim);
  }

  .semesters {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .semesters button {
    padding: 1px 9px;
    border-radius: 999px;
    border: 1px solid var(--border);
    font-size: 11px;
    color: var(--muted);
  }
  .semesters button:hover {
    color: var(--text);
  }
  .grupy button {
    max-width: 14rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .semesters button.active {
    background: var(--panel-3);
    border-color: var(--accent-dim);
    color: var(--text);
  }

  ol {
    flex: 1;
    margin: 0;
    padding: 6px;
    list-style: none;
    overflow-y: auto;
  }

  li button {
    display: flex;
    flex-direction: column;
    gap: 5px;
    width: 100%;
    padding: 7px 9px;
    border-radius: 7px;
    text-align: left;
  }
  li button:hover {
    background: var(--panel);
  }
  li button.active {
    background: var(--panel-2);
    box-shadow: inset 2px 0 0 var(--accent);
  }

  .line {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }
  .sem {
    font-size: 10.5px;
    color: var(--muted-2);
    letter-spacing: 0.04em;
  }
  .skrot {
    font-weight: 600;
  }
  .nazwa {
    flex: 1;
    color: var(--muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .meta {
    color: var(--muted-2);
    font-size: 11px;
  }
  .meta :global(.bar) {
    flex: 1;
    max-width: 120px;
  }
  .nums {
    white-space: nowrap;
  }
  .when {
    margin-left: auto;
    white-space: nowrap;
  }

  .empty {
    padding: 18px 10px;
    color: var(--muted-2);
    text-align: center;
  }
</style>
