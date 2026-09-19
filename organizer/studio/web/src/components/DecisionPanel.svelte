<script lang="ts">
  import {
    postDecision,
    postUndo,
    getItems,
    type Item,
    type ItemsPage,
    type DecisionRequest,
  } from '../lib/api';
  import { basename, bytes, percent, dirname } from '../lib/format';

  interface Props {
    semester?: number | null;
    skrot?: string | null;
    onDecided?: () => void;
  }

  let { semester = null, skrot = null, onDecided }: Props = $props();

  let current = $state<Item | null>(null);
  let remaining = $state(0);
  let loading = $state(false);
  let error = $state<string | null>(null);
  let success = $state<string | null>(null);
  let history = $state<string[]>([]);

  async function loadNext(): Promise<void> {
    loading = true;
    error = null;
    try {
      const filters: Record<string, unknown> = { needs_review: true, limit: 1 };
      if (semester) filters.semester = semester;
      if (skrot) filters.skrot = skrot;
      const page: ItemsPage = await getItems(filters as any);
      current = page.items[0] ?? null;
      remaining = page.total;
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc);
    } finally {
      loading = false;
    }
  }

  async function decide(action: string, category?: string): Promise<void> {
    if (!current) return;
    const item = current;
    error = null;
    success = null;

    const decision: DecisionRequest = {
      sha256: item.sha256,
      decision_type: action === 'skip' || action === 'quarantine' ? action : 'classify',
      semester: item.semester ?? semester ?? undefined,
      subject_key: item.subject_key ?? skrot ?? undefined,
      category: category ?? item.category ?? undefined,
      action: action === 'quarantine' ? 'quarantine' : action === 'skip' ? undefined : action,
    };

    try {
      await postDecision(decision);
      history = [item.sha256, ...history.slice(0, 49)];
      success = `${item.sha256.slice(0, 12)}… → ${action}`;
      onDecided?.();
      await loadNext();
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc);
    }
  }

  async function undo(): Promise<void> {
    if (!history.length) return;
    error = null;
    try {
      await postUndo();
      history = history.slice(1);
      success = 'cofnięto';
      onDecided?.();
      await loadNext();
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc);
    }
  }

  function onKey(event: KeyboardEvent): void {
    const target = event.target as HTMLElement | null;
    if (target?.tagName === 'INPUT' || target?.tagName === 'TEXTAREA') return;
    if (!current) return;

    switch (event.key) {
      case 'Enter':
        event.preventDefault();
        decide('copy');
        break;
      case 's':
        event.preventDefault();
        decide('skip');
        break;
      case 'q':
        event.preventDefault();
        decide('quarantine');
        break;
      case 'u':
        event.preventDefault();
        undo();
        break;
      case 'm':
        event.preventDefault();
        decide('media');
        break;
    }
  }

  $effect(() => {
    const _deps = [semester, skrot];
    loadNext();
  });
</script>

<svelte:window onkeydown={onKey} />

<div class="decision-panel">
  <div class="header">
    <h3>Kolejka decyzji</h3>
    <span class="remaining num">{remaining} do przeglądu</span>
  </div>

  {#if error}
    <div class="error">{error}</div>
  {/if}
  {#if success}
    <div class="success">{success}</div>
  {/if}

  {#if loading}
    <div class="empty">Wczytuję…</div>
  {:else if !current}
    <div class="empty">Brak pozycji do przeglądu</div>
  {:else}
    <div class="item-card">
      <div class="item-header">
        <span class="sha mono">{current.sha256.slice(0, 16)}…</span>
        <span class="kind tag">{current.content_kind ?? '?'}</span>
        {#if current.copies > 1}
          <span class="copies tag">{current.copies} kopii</span>
        {/if}
      </div>

      <div class="item-meta">
        {#if current.filename}
          <div class="filename">{current.filename}</div>
        {/if}
        {#if current.source_relative_path}
          <div class="path mono dim">{dirname(current.source_relative_path)}</div>
        {/if}
        {#if current.size_bytes}
          <div class="size">{bytes(current.size_bytes)}</div>
        {/if}
      </div>

      <div class="proposal">
        <div class="label dim">Propozycja:</div>
        <div class="proposal-row">
          <span class="tag cat">{current.category ?? '—'}</span>
          <span class="tag action">{current.action ?? '—'}</span>
          <span class="confidence num" class:low={current.confidence !== null && current.confidence < 0.7}>
            {current.confidence !== null ? percent(current.confidence) : '—'}
          </span>
          <span class="method dim">{current.classification_method ?? ''}</span>
        </div>
        {#if current.reason}
          <div class="reason dim">{current.reason}</div>
        {/if}
        {#if current.target_relative_path}
          <div class="target mono dim">{current.target_relative_path}</div>
        {/if}
      </div>

      <div class="actions">
        <button class="action-btn accept" onclick={() => decide('copy')} title="Enter">
          Akceptuj (copy)
        </button>
        <button class="action-btn skip" onclick={() => decide('skip')} title="s">
          Pomiń
        </button>
        <button class="action-btn quarantine" onclick={() => decide('quarantine')} title="q">
          Kwarantanna
        </button>
        <button class="action-btn media" onclick={() => decide('media')} title="m">
          Media
        </button>
        <button class="action-btn undo" onclick={undo} disabled={!history.length} title="u">
          Cofnij ({history.length})
        </button>
      </div>

      <div class="shortcuts dim">
        <kbd>Enter</kbd> akceptuj &nbsp;
        <kbd>s</kbd> pomiń &nbsp;
        <kbd>q</kbd> kwarantanna &nbsp;
        <kbd>m</kbd> media &nbsp;
        <kbd>u</kbd> cofnij
      </div>
    </div>
  {/if}
</div>

<style>
  .decision-panel {
    padding: 12px;
    overflow-y: auto;
  }
  .header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 12px;
  }
  .header h3 {
    margin: 0;
    font-size: 14px;
  }
  .remaining {
    color: var(--muted);
    font-size: 12px;
  }
  .item-card {
    display: flex;
    flex-direction: column;
    gap: 10px;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 14px;
    background: var(--bg-deep);
  }
  .item-header {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .sha {
    font-size: 11px;
    color: var(--muted-2);
  }
  .item-meta {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .filename {
    font-weight: 600;
    font-size: 13px;
  }
  .path {
    font-size: 11px;
  }
  .size {
    font-size: 11px;
    color: var(--muted);
  }
  .proposal {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px;
    border-radius: 4px;
    background: var(--bg);
  }
  .proposal-row {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .confidence.low {
    color: var(--warn);
  }
  .reason, .target {
    font-size: 11px;
  }
  .actions {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }
  .action-btn {
    padding: 5px 12px;
    border: 1px solid var(--border);
    border-radius: 4px;
    font-size: 12px;
    cursor: pointer;
    color: var(--text);
    background: transparent;
  }
  .action-btn:hover {
    border-color: var(--accent-dim);
  }
  .action-btn.accept {
    border-color: var(--tag-ok);
    color: var(--tag-ok);
  }
  .action-btn.accept:hover {
    background: color-mix(in srgb, var(--tag-ok) 15%, transparent);
  }
  .action-btn.skip {
    color: var(--muted);
  }
  .action-btn.quarantine {
    color: var(--warn);
  }
  .action-btn.undo {
    margin-left: auto;
    color: var(--muted-2);
  }
  .action-btn:disabled {
    opacity: 0.3;
    cursor: default;
  }
  .shortcuts {
    font-size: 10px;
    text-align: center;
  }
  .shortcuts kbd {
    padding: 1px 4px;
    border: 1px solid var(--border);
    border-radius: 3px;
    font-size: 10px;
    background: var(--bg-deep);
  }
  .error {
    padding: 6px 10px;
    margin-bottom: 8px;
    border-radius: 4px;
    background: color-mix(in srgb, var(--warn) 15%, transparent);
    color: var(--warn);
    font-size: 12px;
  }
  .success {
    padding: 6px 10px;
    margin-bottom: 8px;
    border-radius: 4px;
    background: color-mix(in srgb, var(--tag-ok) 15%, transparent);
    color: var(--tag-ok);
    font-size: 12px;
  }
  .empty {
    padding: 24px;
    text-align: center;
    color: var(--muted);
  }
  .label {
    font-size: 11px;
  }
  .tag {
    padding: 1px 6px;
    border-radius: 3px;
    font-size: 11px;
    background: var(--tag-bg, color-mix(in srgb, var(--border) 50%, transparent));
  }
</style>
