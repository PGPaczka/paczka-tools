<script lang="ts">
  import { getStats, type LiveStats } from '../lib/api';
  import { count, percent } from '../lib/format';

  let stats = $state<LiveStats | null>(null);
  let loading = $state(false);
  let error = $state<string | null>(null);

  async function load(): Promise<void> {
    loading = true;
    error = null;
    try {
      stats = await getStats();
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc);
    } finally {
      loading = false;
    }
  }

  $effect(() => { load(); });
</script>

<div class="stats-panel">
  <div class="header">
    <h3>Statystyki na żywo</h3>
    <button onclick={load}>odśwież</button>
  </div>

  {#if error}
    <div class="msg error">{error}</div>
  {/if}

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
</style>
