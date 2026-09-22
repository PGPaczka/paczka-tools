<script lang="ts">
  import { createEventDispatcher, tick } from 'svelte'
  import { graph } from '../../stores/graphStore'
  import { selectedId } from '../../stores/selectionStore'
  import { searchPalette } from '../../domain/commandPalette/search'
  import { buildActionsRegistry } from '../../domain/commandPalette/actionsRegistry'
  import { categoryColor } from '../../domain/color/categoryColor'
  import { ensureIndexLoaded, searchContent, indexState } from '../../stores/searchStore'
  import type { PaletteResult } from '../../domain/commandPalette/search'

  export let open: boolean = false

  const dispatch = createEventDispatcher<{
    close: void
    switchView: string
    switchLayout: string
    openSettings: void
  }>()

  let query = ''
  let activeIndex = 0
  let inputEl: HTMLInputElement

  const actions = buildActionsRegistry({
    switchViewGraph: () => { dispatch('switchView', 'graph'); close() },
    switchViewCards: () => { dispatch('switchView', 'cards'); close() },
    switchViewDash: () => { dispatch('switchView', 'dash'); close() },
    switchLayoutClassic: () => { dispatch('switchLayout', 'classic'); close() },
    switchLayoutRail: () => { dispatch('switchLayout', 'rail'); close() },
    switchLayoutCommand: () => { dispatch('switchLayout', 'command'); close() },
    openSettings: () => { dispatch('openSettings'); close() },
  })

  function close() {
    open = false
    query = ''
    activeIndex = 0
    dispatch('close')
  }

  function selectNote(id: string) {
    selectedId.set(id)
    close()
  }

  $: nodes = $graph?.nodes ?? []
  $: results = searchPalette(query, actions, nodes, categoryColor, selectNote)

  // Reset active index on query change
  $: query, (activeIndex = 0)

  // Groups
  $: actionResults = results.filter((r) => r.type === 'action')
  $: noteResults = results.filter((r) => r.type === 'note')

  // Full-text content search — deduplicated against title/tag results
  $: noteIds = new Set(noteResults.map((r) => r.id).filter((id): id is string => !!id))
  $: contentItems = ($indexState === 'ready' && query.length > 1)
      ? searchContent(query, noteIds)
      : []
  $: contentResults = contentItems.map((r): PaletteResult => ({
      type: 'content',
      id: r.id,
      label: r.title,
      hint: 'In content',
      run: () => { selectedId.set(r.id); close() },
    }))

  // Flat list for keyboard navigation (actions → notes → content)
  $: allResults = [...actionResults, ...noteResults, ...contentResults]

  async function handleOpenChange(isOpen: boolean) {
    if (isOpen) {
      await tick()
      inputEl?.focus()
      // Start loading the full-text index in the background (no-op if already loaded)
      ensureIndexLoaded()
    }
  }

  $: handleOpenChange(open)

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      close()
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      activeIndex = Math.min(activeIndex + 1, allResults.length - 1)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      activeIndex = Math.max(activeIndex - 1, 0)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      allResults[activeIndex]?.run()
    }
  }

  function runResult(r: PaletteResult) {
    r.run()
  }

  $: statusVar = (s: string | null | undefined) => {
    switch (s) {
      case 'completed': return 'var(--green)'
      case 'in-progress': return 'var(--amber)'
      case 'not-started': return 'var(--gray)'
      default: return 'var(--muted)'
    }
  }
</script>

{#if open}
  <!-- Backdrop -->
  <div class="palette-backdrop" on:click={close} on:keydown={() => {}} role="presentation"></div>

  <!-- Palette container -->
  <div class="palette-container" role="dialog" aria-modal="true" aria-label="Command palette">
    <div class="palette-input-row">
      <svg class="search-icon" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="7" cy="7" r="5"/>
        <line x1="11" y1="11" x2="15" y2="15"/>
      </svg>
      <input
        bind:this={inputEl}
        bind:value={query}
        class="palette-input"
        type="text"
        placeholder="Search notes and actions…"
        autocomplete="off"
        spellcheck="false"
        on:keydown={handleKeydown}
      />
      <kbd class="esc-hint">Esc</kbd>
    </div>

    <div class="palette-results" role="listbox">
      {#if allResults.length === 0}
        {#if query.length > 0}
          <div class="empty-state">No results for "{query}"</div>
        {/if}
      {:else}
        {#if actionResults.length > 0}
          <div class="results-group-label">Actions</div>
          {#each actionResults as result, i}
            {@const globalIdx = i}
            <button
              class="result-item"
              class:active={globalIdx === activeIndex}
              role="option"
              aria-selected={globalIdx === activeIndex}
              on:click={() => runResult(result)}
              on:mouseenter={() => (activeIndex = globalIdx)}
            >
              <span class="result-label">{result.label}</span>
              {#if result.hint}
                <span class="result-hint">{result.hint}</span>
              {/if}
            </button>
          {/each}
        {/if}

        {#if noteResults.length > 0}
          <div class="results-group-label">Notes</div>
          {#each noteResults as result, i}
            {@const globalIdx = actionResults.length + i}
            <button
              class="result-item"
              class:active={globalIdx === activeIndex}
              role="option"
              aria-selected={globalIdx === activeIndex}
              on:click={() => runResult(result)}
              on:mouseenter={() => (activeIndex = globalIdx)}
            >
              <span class="status-dot" style="background:{statusVar(result.status)}"></span>
              {#if result.color}
                <span class="cat-dot" style="background:{result.color}"></span>
              {/if}
              <span class="result-label">{result.label}</span>
              {#if result.hint}
                <span class="result-hint">{result.hint}</span>
              {/if}
            </button>
          {/each}
        {/if}

        {#if contentResults.length > 0}
          <div class="results-group-label">
            In content
            {#if $indexState === 'loading'}
              <span class="index-hint">indexing…</span>
            {/if}
          </div>
          {#each contentResults as result, i}
            {@const globalIdx = actionResults.length + noteResults.length + i}
            <button
              class="result-item"
              class:active={globalIdx === activeIndex}
              role="option"
              aria-selected={globalIdx === activeIndex}
              on:click={() => runResult(result)}
              on:mouseenter={() => (activeIndex = globalIdx)}
            >
              <span class="content-icon">
                <svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5">
                  <rect x="1" y="1" width="10" height="10" rx="1.5"/>
                  <line x1="3" y1="4" x2="9" y2="4"/>
                  <line x1="3" y1="6.5" x2="9" y2="6.5"/>
                  <line x1="3" y1="9" x2="6" y2="9"/>
                </svg>
              </span>
              <span class="result-label">{result.label}</span>
              <span class="result-hint">{result.hint}</span>
            </button>
          {/each}
        {:else if $indexState === 'loading' && query.length > 1}
          <div class="index-loading">Building search index…</div>
        {:else if $indexState === 'error'}
          <div class="index-error">Content search unavailable — run the generator to create search-index.json</div>
        {/if}
      {/if}
    </div>
  </div>
{/if}

<style>
  .palette-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(1, 4, 9, 0.6);
    z-index: 100;
  }

  .palette-container {
    position: fixed;
    top: 80px;
    left: 50%;
    transform: translateX(-50%);
    width: min(640px, calc(100vw - 32px));
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 10px;
    box-shadow: 0 20px 60px var(--shadow), 0 4px 16px rgba(0,0,0,.3);
    z-index: 101;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    max-height: calc(100vh - 160px);
  }

  .palette-input-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 14px;
    border-bottom: 1px solid var(--border-2);
  }

  .search-icon {
    color: var(--muted);
    flex-shrink: 0;
  }

  .palette-input {
    flex: 1;
    background: transparent;
    border: none;
    outline: none;
    color: var(--text);
    font-size: 14px;
    font-family: var(--font-ui);
    caret-color: var(--accent);
  }

  .palette-input::placeholder {
    color: var(--muted-2);
  }

  .esc-hint {
    font-size: 10px;
    color: var(--muted-2);
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 2px 6px;
    font-family: var(--font-ui);
    cursor: pointer;
    flex-shrink: 0;
  }

  .palette-results {
    overflow-y: auto;
    padding: 6px 0;
  }

  .results-group-label {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--muted-2);
    padding: 6px 14px 3px;
  }

  .result-item {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 8px 14px;
    border: none;
    background: transparent;
    color: var(--muted);
    cursor: pointer;
    text-align: left;
    font-size: 13px;
    font-family: var(--font-ui);
    transition: all 0.08s;
  }

  .result-item.active,
  .result-item:hover {
    background: var(--panel-2);
    color: var(--text);
  }

  .result-item.active {
    background: rgba(88, 166, 255, 0.08);
    color: var(--text);
  }

  .result-label {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .result-hint {
    font-size: 11px;
    color: var(--muted-2);
    white-space: nowrap;
    flex-shrink: 0;
  }

  .status-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .cat-dot {
    width: 7px;
    height: 7px;
    border-radius: 2px;
    flex-shrink: 0;
  }

  .content-icon {
    display: flex;
    align-items: center;
    color: var(--muted-2);
    flex-shrink: 0;
  }

  .index-hint {
    font-size: 9px;
    color: var(--muted-2);
    font-weight: 400;
    letter-spacing: 0;
    text-transform: none;
    margin-left: 6px;
  }

  .index-loading {
    padding: 10px 14px;
    color: var(--muted-2);
    font-size: 12px;
    font-style: italic;
  }

  .index-error {
    padding: 10px 14px;
    color: var(--muted-2);
    font-size: 11px;
    border-top: 1px solid var(--border-2);
    margin-top: 4px;
  }

  .empty-state {
    padding: 16px 14px;
    color: var(--muted-2);
    font-size: 13px;
    text-align: center;
  }
</style>
