<script lang="ts">
  import { getHistory, deleteDecision, type HistoryPage, type ManualDecision } from '../lib/api';
  import { stamp } from '../lib/format';

  interface Props {
    onChanged?: () => void;
  }

  let { onChanged }: Props = $props();

  let page = $state<HistoryPage | null>(null);
  let loading = $state(false);
  let error = $state<string | null>(null);
  let success = $state<string | null>(null);
  let sinceFilter = $state('');

  async function load(): Promise<void> {
    loading = true;
    error = null;
    try {
      const filters: Record<string, string> = {};
      if (sinceFilter) filters.since = sinceFilter;
      page = await getHistory(filters);
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc);
    } finally {
      loading = false;
    }
  }

  async function undoOne(sha: string): Promise<void> {
    error = null;
    success = null;
    try {
      await deleteDecision(sha);
      success = `Cofnięto decyzję ${sha.slice(0, 12)}…`;
      onChanged?.();
      await load();
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc);
    }
  }

  function typeLabel(t: string): string {
    switch (t) {
      case 'classify': return 'klasyfikacja';
      case 'skip': return 'pomiń';
      case 'quarantine': return 'kwarantanna';
      case 'outdated': return 'outdated';
      case 'relation': return 'relacja';
      default: return t;
    }
  }

  $effect(() => { load(); });
</script>

<div class="history-panel">
  <div class="header">
    <h3>Historia decyzji</h3>
    <span class="total num">{page?.total ?? 0} decyzji</span>
  </div>

  <div class="filter-row">
    <input
      type="date"
      bind:value={sinceFilter}
      onchange={load}
      title="Pokaż od daty"
    />
    <button onclick={() => { sinceFilter = ''; load(); }}>wszystkie</button>
    <button onclick={load}>odśwież</button>
  </div>

  {#if error}
    <div class="msg error">{error}</div>
  {/if}
  {#if success}
    <div class="msg success">{success}</div>
  {/if}

  {#if loading}
    <div class="empty">Wczytuję…</div>
  {:else if !page || page.total === 0}
    <div class="empty">Brak decyzji</div>
  {:else}
    <div class="history-list">
      {#each page.decisions as decision}
        <div class="history-row">
          <div class="row-main">
            <span class="sha mono">{decision.sha256.slice(0, 12)}…</span>
            <span class="tag type">{typeLabel(decision.decision_type)}</span>
            <span class="dim by">{decision.decided_by}</span>
            <span class="dim date">{stamp(decision.decided_at)}</span>
          </div>
          {#if decision.note}
            <div class="note dim">{decision.note}</div>
          {/if}
          <button class="undo-btn" onclick={() => undoOne(decision.sha256)} title="Cofnij tę decyzję">
            cofnij
          </button>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .history-panel {
    padding: 12px;
    overflow-y: auto;
  }
  .header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 8px;
  }
  .header h3 { margin: 0; font-size: 14px; }
  .total { color: var(--muted); font-size: 12px; }
  .filter-row {
    display: flex;
    gap: 6px;
    margin-bottom: 10px;
  }
  .filter-row input {
    padding: 4px 8px;
    border: 1px solid var(--border);
    border-radius: 4px;
    font-size: 12px;
    background: var(--bg-deep);
    color: var(--text);
  }
  .filter-row button {
    padding: 4px 10px;
    border: 1px solid var(--border);
    border-radius: 4px;
    font-size: 12px;
    color: var(--muted);
    background: transparent;
    cursor: pointer;
  }
  .filter-row button:hover { border-color: var(--accent-dim); color: var(--text); }
  .history-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .history-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 10px;
    border: 1px solid var(--border);
    border-radius: 4px;
    font-size: 12px;
  }
  .row-main {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
    min-width: 0;
  }
  .sha { font-size: 10px; color: var(--muted-2); }
  .tag {
    padding: 1px 6px; border-radius: 3px; font-size: 10px;
    background: color-mix(in srgb, var(--border) 50%, transparent);
  }
  .by { font-size: 11px; }
  .date { font-size: 11px; }
  .note { font-size: 10px; margin-left: auto; }
  .undo-btn {
    padding: 2px 8px;
    border: 1px solid var(--border);
    border-radius: 3px;
    font-size: 10px;
    color: var(--muted);
    background: transparent;
    cursor: pointer;
    flex-shrink: 0;
  }
  .undo-btn:hover { color: var(--warn); border-color: var(--warn); }
  .msg { padding: 6px 10px; margin-bottom: 8px; border-radius: 4px; font-size: 12px; }
  .msg.error { background: color-mix(in srgb, var(--warn) 15%, transparent); color: var(--warn); }
  .msg.success { background: color-mix(in srgb, var(--tag-ok) 15%, transparent); color: var(--tag-ok); }
  .empty { padding: 24px; text-align: center; color: var(--muted); }
</style>
