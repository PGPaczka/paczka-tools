<script lang="ts">
  /** Pasek złożony z segmentów. Nic nie liczy — dostaje gotowe wartości z API. */
  interface Segment {
    value: number;
    color: string;
    label: string;
  }
  let { segments, height = 4 }: { segments: Segment[]; height?: number } = $props();

  const total = $derived(segments.reduce((sum, segment) => sum + Math.max(segment.value, 0), 0));
</script>

<div class="bar" style="height: {height}px" title={segments.map((s) => `${s.label}: ${s.value}`).join(' · ')}>
  {#if total > 0}
    {#each segments as segment (segment.label)}
      {#if segment.value > 0}
        <span style="width: {(segment.value / total) * 100}%; background: {segment.color}"></span>
      {/if}
    {/each}
  {/if}
</div>

<style>
  .bar {
    display: flex;
    width: 100%;
    border-radius: 999px;
    overflow: hidden;
    background: var(--panel-3);
  }
  .bar span {
    display: block;
    height: 100%;
  }
</style>
