<script lang="ts">
  /** Label shown above the value. */
  export let label: string
  /** Main numeric value. */
  export let value: number | string
  /** Optional subtitle / supporting text. */
  export let sub: string = ''
  /** Accent color for the value text (CSS color string). */
  export let color: string = 'var(--text)'
</script>

<div class="stat-card">
  <span class="stat-label">{label}</span>
  <span class="stat-value" style="color:{color}">{value}</span>
  {#if sub}
    <span class="stat-sub">{sub}</span>
  {/if}
</div>

<style>
  .stat-card {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 14px 16px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    min-width: 100px;
    flex: 1;
  }

  .stat-label {
    font-size: 11px;
    color: var(--muted-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-weight: 500;
  }

  .stat-value {
    font-size: 28px;
    font-weight: 600;
    font-family: var(--font-mono);
    line-height: 1;
  }

  .stat-sub {
    font-size: 11px;
    color: var(--muted);
  }
</style>
