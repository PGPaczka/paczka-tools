<script lang="ts">
  import type { Dashboard, QueueStage } from '../lib/api';
  import { count } from '../lib/format';
  import Bar from './Bar.svelte';

  let {
    dashboard,
    stage,
    onStage,
    onClose,
  }: {
    dashboard: Dashboard;
    stage: string | null;
    onStage: (value: string | null) => void;
    /** Zwinięcie panelu — na telefonie to jedyny sensowny sposób odzyskania ekranu. */
    onClose?: () => void;
  } = $props();

  /** Kolor etapu — ta sama skala, co przy pozycjach: bursztyn = czeka na oko. */
  const colors: Record<string, string> = {
    'plan do przeglądu': 'var(--amber)',
    'plan gotowy': 'var(--green)',
    'tylko ground truth': 'var(--accent-dim)',
    nietknięty: 'var(--muted-2)',
  };

  const segments = $derived(
    dashboard.queue.map((entry: QueueStage) => ({
      value: entry.count,
      color: colors[entry.stage] ?? 'var(--gray)',
      label: entry.stage,
    })),
  );
</script>

<aside class="side-panel queue-panel">
  <div class="panel-head">
    <h2>Kolejka</h2>
    {#if onClose}
      <button class="collapse" onclick={onClose} title="Zwiń panel" aria-label="Zwiń panel">×</button>
    {/if}
  </div>
  <Bar {segments} height={6} />

  <ul>
    {#each dashboard.queue as entry (entry.stage)}
      <li>
        <button
          class:active={stage === entry.stage}
          onclick={() => onStage(stage === entry.stage ? null : entry.stage)}
        >
          <span class="dot" style="background: {colors[entry.stage] ?? 'var(--gray)'}"></span>
          <span class="name">{entry.stage}</span>
          <span class="num">{count(entry.count)}</span>
        </button>
      </li>
    {/each}
  </ul>

  <h2>Pliki</h2>
  <dl>
    {#each Object.entries(dashboard.totals.files_by_status) as [status, value] (status)}
      <div class:error={status === 'error'}>
        <dt>{status}</dt>
        <dd class="num">{count(value)}</dd>
      </div>
    {/each}
  </dl>

  <h2>Indeks</h2>
  <dl>
    <div><dt>paczki</dt><dd class="num">{count(dashboard.totals.packages)}</dd></div>
    <div><dt>katalogi</dt><dd class="num">{count(dashboard.totals.folders)}</dd></div>
    <div><dt>w tym duplikaty</dt><dd class="num">{count(dashboard.totals.duplicate_folders)}</dd></div>
    <div><dt>treści</dt><dd class="num">{count(dashboard.totals.contents)}</dd></div>
    <div><dt>z tekstem</dt><dd class="num">{count(dashboard.totals.with_text)}</dd></div>
    <div><dt>relacje</dt><dd class="num">{count(dashboard.totals.relations)}</dd></div>
    <div><dt>pozycje planu</dt><dd class="num">{count(dashboard.totals.plan_items)}</dd></div>
    <div><dt>w paczce</dt><dd class="num">{count(dashboard.totals.applied)}</dd></div>
  </dl>
</aside>

<style>
  aside {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 14px 12px;
    border-right: 1px solid var(--border);
    background: var(--bg-deep);
    overflow-y: auto;
  }

  .panel-head {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .panel-head h2 {
    margin: 0;
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

  h2 {
    margin: 10px 0 2px;
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--muted-2);
  }
  h2:first-of-type {
    margin-top: 0;
  }

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  li button {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 5px 8px;
    border-radius: 6px;
    text-align: left;
    color: var(--muted);
  }
  li button:hover {
    background: var(--panel);
    color: var(--text);
  }
  li button.active {
    background: var(--panel-2);
    color: var(--text);
    box-shadow: inset 2px 0 0 var(--accent);
  }

  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex: none;
  }
  .name {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  dl {
    margin: 0;
    display: grid;
    gap: 1px;
  }
  dl div {
    display: flex;
    justify-content: space-between;
    padding: 2px 8px;
    color: var(--muted);
  }
  dl div.error dd {
    color: var(--red);
  }
  dt,
  dd {
    margin: 0;
  }
  dd {
    color: var(--text);
  }
</style>
