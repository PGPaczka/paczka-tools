<script lang="ts">
  import { onDestroy } from 'svelte'
  import { copyText } from '../../lib/clipboard'

  export let value: string
  export let label = 'Copy'

  let done = false
  let cancel: (() => void) | undefined

  function copy(event: MouseEvent) {
    event.stopPropagation()
    cancel?.()
    cancel = copyText(value, (state) => (done = state))
  }

  onDestroy(() => cancel?.())
</script>

<button
  class="copy-btn"
  class:copy-btn--ok={done}
  on:click={copy}
  title={done ? 'Copied' : label}
  aria-label={label}
>
  {#if done}
    <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 16 16"
         fill="none" stroke="currentColor" stroke-width="2">
      <path d="M2.5 8.5l4 4 7-8" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
  {:else}
    <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 16 16"
         fill="none" stroke="currentColor" stroke-width="1.5">
      <rect x="5" y="5" width="9" height="9" rx="1.5"/>
      <path d="M11 2.5H3A1.5 1.5 0 001.5 4v8" stroke-linecap="round"/>
    </svg>
  {/if}
</button>

<style>
  .copy-btn {
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    padding: 0;
    border: none;
    border-radius: 4px;
    background: none;
    color: var(--muted-2);
    cursor: pointer;
  }
  .copy-btn:hover { background: var(--panel-3); color: var(--text); }
  .copy-btn--ok, .copy-btn--ok:hover { color: var(--green); }
</style>
