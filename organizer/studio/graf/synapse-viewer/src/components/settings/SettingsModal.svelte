<script lang="ts">
  import { createEventDispatcher } from 'svelte'
  import { settings } from '../../stores/settingsStore'
  import { graph } from '../../stores/graphStore'
  import { categoryColor } from '../../domain/color/categoryColor'
  import { layouts } from '../../layout/layoutRegistry'
  import type { RealNode } from '../../domain/graph/GraphModel'
  import type { LayoutId } from '../../layout/layoutRegistry'

  const LAYOUT_ICONS: Record<LayoutId, string> = {
    classic: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="20" viewBox="0 0 24 20" fill="currentColor">
      <rect x="1" y="1" width="22" height="5" rx="1.5"/>
      <rect x="1" y="8" width="22" height="11" rx="1.5" fill-opacity=".35"/>
    </svg>`,
    rail: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="20" viewBox="0 0 24 20" fill="currentColor">
      <rect x="1" y="1" width="5" height="18" rx="1.5"/>
      <rect x="8" y="1" width="15" height="18" rx="1.5" fill-opacity=".35"/>
    </svg>`,
    command: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="20" viewBox="0 0 24 20" fill="currentColor">
      <rect x="5" y="1" width="14" height="5" rx="2"/>
      <rect x="1" y="8" width="22" height="11" rx="1.5" fill-opacity=".35"/>
    </svg>`,
  }

  const dispatch = createEventDispatcher<{ close: void }>()

  function close() {
    dispatch('close')
  }

  function onBackdropClick(e: MouseEvent) {
    if (e.target === e.currentTarget) close()
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') close()
  }

  $: realNodes = ($graph?.nodes.filter((n) => n.kind === 'real') ?? []) as RealNode[]
  $: categories = [...new Set(realNodes.map((n) => n.category))].sort()

  function setCatColor(cat: string, color: string) {
    settings.update((s) => ({
      ...s,
      catColorOverrides: { ...s.catColorOverrides, [cat]: color },
    }))
  }

  function getCatColor(cat: string): string {
    return $settings.catColorOverrides[cat] ?? categoryColor(cat)
  }
</script>

<svelte:window on:keydown={onKeydown} />

<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
<div class="backdrop" on:click={onBackdropClick}>
  <div class="modal" role="dialog" aria-modal="true" aria-label="Settings">
    <!-- Header -->
    <div class="modal-header">
      <span class="modal-title">Settings</span>
      <button class="close-btn" on:click={close} aria-label="Close settings">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 14 14" fill="none">
          <path d="M2 2l10 10M12 2L2 12" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
        </svg>
      </button>
    </div>

    <div class="modal-body">

      <!-- LAYOUT -->
      <div class="section-label">Layout</div>
      <div class="layout-picker">
        {#each layouts as l}
          <button
            class="layout-option"
            class:active={$settings.layout === l.id}
            on:click={() => settings.update((s) => ({ ...s, layout: l.id }))}
            title={l.label}
          >
            <span class="layout-option-icon">{@html LAYOUT_ICONS[l.id]}</span>
            <span class="layout-option-label">{l.label}</span>
          </button>
        {/each}
      </div>

      <div class="divider"></div>

      <!-- APPEARANCE -->
      <div class="section-label">Appearance</div>

      <div class="row">
        <div class="row-info">
          <div class="row-name">Minimap</div>
          <div class="row-desc">Overview navigator in graph view</div>
        </div>
        <button
          class="toggle"
          class:toggle--on={$settings.minimapOn}
          on:click={() => settings.update((s) => ({ ...s, minimapOn: !s.minimapOn }))}
          aria-label="Toggle minimap"
        >
          <span class="toggle-knob"></span>
        </button>
      </div>

      <div class="divider"></div>

      <!-- GRAPH PHYSICS -->
      <div class="section-label">Graph Physics</div>

      <div class="slider-row">
        <div class="slider-info">
          <span class="slider-name">Repulsion force</span>
          <span class="slider-val">{$settings.repulsion}</span>
        </div>
        <input
          type="range"
          min="200"
          max="2400"
          step="50"
          value={$settings.repulsion}
          on:input={(e) => settings.update((s) => ({ ...s, repulsion: +e.currentTarget.value }))}
          class="slider"
        />
      </div>

      <div class="slider-row">
        <div class="slider-info">
          <span class="slider-name">Link distance</span>
          <span class="slider-val">{$settings.linkDist}</span>
        </div>
        <input
          type="range"
          min="40"
          max="200"
          step="5"
          value={$settings.linkDist}
          on:input={(e) => settings.update((s) => ({ ...s, linkDist: +e.currentTarget.value }))}
          class="slider"
        />
      </div>

      <div class="divider"></div>

      <!-- NODE COLORING -->
      <div class="section-label">Node Coloring</div>
      <div class="row">
        <div class="row-info">
          <div class="row-name">Color priority</div>
          <div class="row-desc">Which attribute determines the fill color</div>
        </div>
        <div class="seg-ctrl">
          <button
            class="seg-btn"
            class:active={$settings.colorPriority === 'category'}
            on:click={() => settings.update((s) => ({ ...s, colorPriority: 'category' }))}
          >Category</button>
          <button
            class="seg-btn"
            class:active={$settings.colorPriority === 'status'}
            on:click={() => settings.update((s) => ({ ...s, colorPriority: 'status' }))}
          >Status</button>
        </div>
      </div>

      <div class="row">
        <div class="row-info">
          <div class="row-name">Secondary color</div>
          <div class="row-desc">Show status/category ring on filled nodes</div>
        </div>
        <button
          class="toggle"
          class:toggle--on={$settings.secondaryColorEnabled}
          on:click={() => settings.update((s) => ({ ...s, secondaryColorEnabled: !s.secondaryColorEnabled }))}
          aria-label="Toggle secondary color ring"
        >
          <span class="toggle-knob"></span>
        </button>
      </div>

      <div class="divider"></div>

      <!-- CATEGORY COLORS -->
      {#if categories.length > 0}
        <div class="section-label">Category Colors</div>
        <div class="color-grid">
          {#each categories as cat}
            <div class="color-row">
              <input
                type="color"
                value={getCatColor(cat)}
                on:input={(e) => setCatColor(cat, e.currentTarget.value)}
                class="color-swatch"
                title="Pick color for {cat}"
              />
              <span class="color-label">{cat}</span>
              <span class="color-hex">{getCatColor(cat)}</span>
            </div>
          {/each}
        </div>
      {/if}

    </div>
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 200;
    background: rgba(1, 4, 9, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .modal {
    width: 540px;
    max-width: 94vw;
    max-height: 84vh;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    box-shadow: 0 24px 64px rgba(1, 4, 9, 0.7);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 18px;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }

  .modal-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--text);
  }

  .close-btn {
    width: 26px;
    height: 26px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: transparent;
    color: var(--muted);
    cursor: pointer;
    transition: all 0.1s;
  }
  .close-btn:hover {
    background: var(--panel-2);
    color: var(--text);
  }

  .modal-body {
    flex: 1;
    overflow-y: auto;
    padding: 18px;
    display: flex;
    flex-direction: column;
    gap: 0;
  }

  .section-label {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--muted-2);
    margin-bottom: 12px;
  }

  /* Layout picker */
  .layout-picker {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    margin-bottom: 4px;
  }

  .layout-option {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    padding: 12px 8px;
    border-radius: 8px;
    border: 1.5px solid var(--border);
    background: var(--panel-2);
    color: var(--muted);
    cursor: pointer;
    transition: all 0.12s;
  }
  .layout-option:hover {
    border-color: var(--border-2);
    color: var(--text);
    background: var(--panel-3);
  }
  .layout-option.active {
    border-color: var(--accent);
    color: var(--accent);
    background: rgba(88, 166, 255, 0.08);
  }

  .layout-option-icon {
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .layout-option-label {
    font-size: 11px;
    font-family: var(--font-ui);
    font-weight: 500;
  }

  .divider {
    height: 1px;
    background: var(--border);
    margin: 16px 0;
  }

  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 12px;
  }

  .row-info {
    flex: 1;
  }

  .row-name {
    font-size: 13px;
    font-weight: 500;
    color: var(--text);
  }

  .row-desc {
    font-size: 11px;
    color: var(--muted);
    margin-top: 2px;
  }

  /* Toggle */
  .toggle {
    width: 38px;
    height: 20px;
    border-radius: 10px;
    border: none;
    cursor: pointer;
    position: relative;
    background: var(--border);
    transition: background 0.15s;
    flex-shrink: 0;
  }
  .toggle--on {
    background: var(--accent);
  }
  .toggle-knob {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: #fff;
    transition: left 0.15s;
  }
  .toggle--on .toggle-knob {
    left: 20px;
  }

  /* Sliders */
  .slider-row {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-bottom: 14px;
  }

  .slider-info {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .slider-name {
    font-size: 12px;
    color: var(--muted);
  }

  .slider-val {
    font-size: 11px;
    font-family: var(--font-mono);
    color: var(--accent);
  }

  .slider {
    width: 100%;
    accent-color: var(--accent);
    cursor: pointer;
  }

  /* Segment control */
  .seg-ctrl {
    display: flex;
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 2px;
    gap: 1px;
    flex-shrink: 0;
  }

  .seg-btn {
    padding: 4px 10px;
    border-radius: 4px;
    border: none;
    background: transparent;
    color: var(--muted);
    font-size: 12px;
    font-family: var(--font-ui);
    cursor: pointer;
    transition: all 0.1s;
    white-space: nowrap;
  }
  .seg-btn.active {
    background: var(--panel-3);
    color: var(--text);
  }

  /* Category colors */
  .color-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-bottom: 4px;
  }

  .color-row {
    display: flex;
    align-items: center;
    gap: 8px;
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px 9px;
  }

  .color-swatch {
    width: 22px;
    height: 22px;
    border: none;
    border-radius: 4px;
    background: none;
    cursor: pointer;
    padding: 0;
    flex-shrink: 0;
  }

  .color-label {
    flex: 1;
    font-size: 11.5px;
    color: var(--text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .color-hex {
    font-size: 10px;
    color: var(--muted-2);
    font-family: var(--font-mono);
    flex-shrink: 0;
  }
</style>
