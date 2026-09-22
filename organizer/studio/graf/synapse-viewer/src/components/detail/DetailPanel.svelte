<script lang="ts">
  import { graph } from '../../stores/graphStore'
  import { selectedId } from '../../stores/selectionStore'
  import { filters } from '../../stores/graphStore'
  import { backlinks, outgoing } from '../../domain/graph/selectors'
  import { EDGE_STYLES, edgeStyle, presentEdgeKinds } from '../../domain/graph/edgeStyle'
  import type { GraphEdge } from '../../domain/graph/GraphModel'
  import { categoryColor } from '../../domain/color/categoryColor'
  import { settings } from '../../stores/settingsStore'
  import { createRenderer, renderMarkdown } from '../../markdown/renderer'
  import { wikilinkPlugin } from '../../markdown/wikilinkPlugin'
  import { fetchBody, getCachedBody, noteBodyVersion } from '../../stores/noteBodyStore'
  import MarkdownBody from './MarkdownBody.svelte'
  import type { RealNode, GhostNode, GraphNode } from '../../domain/graph/GraphModel'

  export let canEdit: boolean = false

  // ── Panel resize ───────────────────────────────────────────
  let panelWidth = 320
  let isResizing = false
  let resizeStartX = 0
  let resizeStartWidth = 0

  function onHandleMouseDown(e: MouseEvent) {
    isResizing = true
    resizeStartX = e.clientX
    resizeStartWidth = panelWidth
    document.body.classList.add('resizing-panel')
    window.addEventListener('mousemove', onResizeMouseMove)
    window.addEventListener('mouseup', onResizeMouseUp)
    e.preventDefault()
  }

  function onResizeMouseMove(e: MouseEvent) {
    // Dragging left (smaller x) makes the panel wider
    const dx = resizeStartX - e.clientX
    panelWidth = Math.max(240, Math.min(640, resizeStartWidth + dx))
  }

  function onResizeMouseUp() {
    isResizing = false
    document.body.classList.remove('resizing-panel')
    window.removeEventListener('mousemove', onResizeMouseMove)
    window.removeEventListener('mouseup', onResizeMouseUp)
  }

  const md = createRenderer()
  md.use(wikilinkPlugin)

  $: node = $graph?.nodes.find((n) => n.id === $selectedId) ?? null
  $: realNode = node?.kind === 'real' ? (node as RealNode) : null
  $: ghostNode = node?.kind === 'ghost' ? (node as GhostNode) : null

  $: backlinkEdges = $graph && $selectedId ? backlinks($graph, $selectedId) : []
  $: outgoingEdges = $graph && $selectedId ? outgoing($graph, $selectedId) : []

  // Grouped by relation kind: "linked to 23 notes" says nothing, "near duplicate of 3,
  // older version of 1" is the thing a person actually decides on.
  $: outgoingByKind = groupByKind(outgoingEdges)
  $: backlinksByKind = groupByKind(backlinkEdges)

  function groupByKind(edges: GraphEdge[]) {
    return presentEdgeKinds(edges).map((kind) => ({
      kind,
      label: EDGE_STYLES[kind]?.label ?? kind,
      style: edgeStyle(kind),
      edges: edges.filter((e) => (e.kind ?? 'link') === kind),
    }))
  }

  function confidenceLabel(value: number | undefined): string {
    return typeof value === 'number' ? value.toFixed(2) : ''
  }

  $: allEdges = $graph?.edges ?? []

  // Lazy-load body from /vault/{path}; fall back to excerpt while loading
  let bodyLoading = false

  $: if (realNode?.path) {
    const cached = getCachedBody(realNode.path)
    if (!cached) {
      bodyLoading = true
      fetchBody(realNode.path).then(() => { bodyLoading = false })
    }
  }

  // Re-read from cache whenever noteBodyVersion bumps or selection changes
  $: markdownSource = (() => {
    void $noteBodyVersion  // reactive dependency
    return realNode ? (getCachedBody(realNode.path) ?? realNode.excerpt) : ''
  })()

  $: renderedBody = markdownSource ? renderMarkdown(markdownSource, md) : ''
  // Must depend on the same version counter as markdownSource: without it the notice
  // is computed once, before the body arrives, and then keeps claiming the body is
  // unavailable while the body is rendered right underneath it.
  $: bodyIsExcerpt = (() => {
    void $noteBodyVersion
    return realNode ? getCachedBody(realNode.path) === null : false
  })()

  $: activeTagFilters = $filters.tags

  // ── Obsidian URI ───────────────────────────────────────────
  $: vaultName = $graph?.vault.name ?? null
  $: obsidianUri = realNode && vaultName
    ? `obsidian://open?vault=${encodeURIComponent(vaultName)}&file=${encodeURIComponent(realNode.path.replace(/\.md$/i, ''))}`
    : null

  let pathCopied = false
  let copyTimeout: ReturnType<typeof setTimeout> | null = null

  function copyPath() {
    if (!realNode?.path) return
    navigator.clipboard.writeText(realNode.path).then(() => {
      pathCopied = true
      if (copyTimeout) clearTimeout(copyTimeout)
      copyTimeout = setTimeout(() => { pathCopied = false }, 1500)
    })
  }

  function close() {
    selectedId.set(null)
  }

  function navigateTo(id: string) {
    // Push to browser history so Back button works
    history.pushState({ noteId: id }, '', '#' + id)
    selectedId.set(id)
  }

  function toggleTagFilter(tag: string) {
    filters.update((f) => {
      if (f.tags.includes(tag)) {
        return { ...f, tags: f.tags.filter((t) => t !== tag) }
      }
      return { ...f, tags: [...f.tags, tag] }
    })
  }

  function nodeById(id: string): GraphNode | undefined {
    return $graph?.nodes.find((n) => n.id === id)
  }

  $: statusLabel = (s: string | null) => {
    switch (s) {
      case 'completed': return 'Completed'
      case 'in-progress': return 'In Progress'
      case 'not-started': return 'Not Started'
      default: return 'Unknown'
    }
  }

  $: statusVar = (s: string | null) => {
    switch (s) {
      case 'completed': return '--green'
      case 'in-progress': return '--amber'
      case 'not-started': return '--gray'
      default: return '--muted'
    }
  }
</script>

{#if node}
  <aside class="detail-panel" style="width: {panelWidth}px">
    <!-- Drag handle on the left edge -->
    <!-- svelte-ignore a11y-no-static-element-interactions -->
    <div
      class="resize-handle"
      class:resizing={isResizing}
      on:mousedown={onHandleMouseDown}
    ></div>
    <!-- Header -->
    <div class="panel-header">
      <div class="header-meta">
        {#if realNode}
          <span
            class="badge category-badge"
            style="background:{categoryColor(realNode.category, $settings.catColorOverrides)}22;color:{categoryColor(realNode.category, $settings.catColorOverrides)};border-color:{categoryColor(realNode.category, $settings.catColorOverrides)}44"
          >
            {realNode.category}
          </span>
          {#if realNode.level !== null}
            <span class="badge level-badge">L{realNode.level}</span>
          {/if}
          <span
            class="badge status-badge"
            style="color:var({statusVar(realNode.status)})"
          >
            {statusLabel(realNode.status)}
          </span>
        {:else}
          <span class="badge ghost-badge">Ghost</span>
        {/if}
      </div>
      <button class="close-btn" on:click={close} aria-label="Close detail panel">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
          <path d="M2 2l10 10M12 2L2 12" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" fill="none"/>
        </svg>
      </button>
    </div>

    <!-- Title -->
    <h2 class="note-title">{node.title}</h2>

    <!-- Tags (real nodes only) -->
    {#if realNode && realNode.tags.length > 0}
      <div class="tag-row">
        {#each realNode.tags as tag}
          <button
            class="tag-chip"
            class:tag-chip--active={activeTagFilters.includes(tag)}
            on:click={() => toggleTagFilter(tag)}
            title={activeTagFilters.includes(tag) ? 'Remove filter' : 'Filter by tag'}
          >#{tag}</button>
        {/each}
      </div>
    {/if}

    <!-- Location bar (real nodes only) -->
    {#if realNode}
      <div class="location-bar">
        <svg class="folder-icon" width="12" height="12" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <path d="M1 3.5A1.5 1.5 0 0 1 2.5 2h3.379a1.5 1.5 0 0 1 1.06.44l.83.83A1.5 1.5 0 0 0 8.83 3.75H13.5A1.5 1.5 0 0 1 15 5.25v7.25A1.5 1.5 0 0 1 13.5 14h-11A1.5 1.5 0 0 1 1 12.5V3.5Z" stroke="currentColor" stroke-width="1.4"/>
        </svg>
        <span class="location-path" title={realNode.path}>{realNode.path}</span>
        <button
          class="copy-btn"
          class:copy-btn--ok={pathCopied}
          on:click={copyPath}
          title="Copy vault-relative path"
          aria-label="Copy path"
        >
          {#if pathCopied}
            <svg width="11" height="11" viewBox="0 0 12 12" fill="none" aria-hidden="true"><path d="M2 6l3 3 5-5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
          {:else}
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none" aria-hidden="true"><rect x="5" y="5" width="9" height="9" rx="1.5" stroke="currentColor" stroke-width="1.4"/><path d="M5 11H3a1.5 1.5 0 0 1-1.5-1.5V3A1.5 1.5 0 0 1 3 1.5h7A1.5 1.5 0 0 1 11.5 3v2" stroke="currentColor" stroke-width="1.4"/></svg>
          {/if}
        </button>
        {#if obsidianUri}
          <a
            class="obsidian-btn"
            href={obsidianUri}
            rel="noopener noreferrer"
            title="Open this note in Obsidian"
          >
            Open in Obsidian
            <svg width="10" height="10" viewBox="0 0 12 12" fill="none" aria-hidden="true"><path d="M2 10 10 2M5.5 2H10v4.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </a>
        {/if}
      </div>
    {/if}

    <!-- Body -->
    {#if realNode}
      {#if bodyLoading && !getCachedBody(realNode.path)}
        <div class="body-loading">
          <span class="loading-dot"></span>
          <span class="loading-dot"></span>
          <span class="loading-dot"></span>
        </div>
      {:else if renderedBody}
        <div class="body-section">
          {#if bodyIsExcerpt}
            <div class="excerpt-notice">Excerpt — body unavailable</div>
          {/if}
          <MarkdownBody
            html={renderedBody}
            edges={allEdges}
            on:navigate={(e) => navigateTo(e.detail)}
          />
        </div>
      {/if}

      {#if canEdit}<!-- slot: edit panel -->{/if}

      <!-- Outgoing links, grouped by relation kind -->
      {#if outgoingEdges.length > 0}
        <div class="links-section">
          <div class="links-label">Links to</div>
          {#each outgoingByKind as group}
          <div class="kind-label">
            <span
              class="kind-dash"
              style="border-top-color:{group.style.color};
                border-top-style:{group.style.dash.length ? 'dashed' : 'solid'}"
            ></span>
            {group.label}
            <span class="kind-count">{group.edges.length}</span>
          </div>
          <ul class="link-list">
            {#each group.edges as edge}
              {@const target = nodeById(edge.target)}
              {#if target}
                <li>
                  <button class="link-item" on:click={() => navigateTo(edge.target)}>
                    <span
                      class="link-dot"
                      style="background:{target.kind === 'real' ? categoryColor(target.category, $settings.catColorOverrides) : 'var(--muted-2)'}"
                    ></span>
                    <span class="link-title">{target.title}</span>
                    {#if target.kind === 'ghost'}
                      <span class="ghost-label">ghost</span>
                    {/if}
                    {#if edge.confidence !== undefined}
                      <span class="confidence" title="relation confidence"
                        >{confidenceLabel(edge.confidence)}</span
                      >
                    {/if}
                  </button>
                </li>
              {/if}
            {/each}
          </ul>
          {/each}
        </div>
      {/if}

      <!-- Backlinks, grouped by relation kind -->
      {#if backlinkEdges.length > 0}
        <div class="links-section">
          <div class="links-label">Referenced by</div>
          {#each backlinksByKind as group}
          <div class="kind-label">
            <span
              class="kind-dash"
              style="border-top-color:{group.style.color};
                border-top-style:{group.style.dash.length ? 'dashed' : 'solid'}"
            ></span>
            {group.label}
            <span class="kind-count">{group.edges.length}</span>
          </div>
          <ul class="link-list">
            {#each group.edges as edge}
              {@const source = nodeById(edge.source)}
              {#if source}
                <li>
                  <button class="link-item" on:click={() => navigateTo(edge.source)}>
                    <span
                      class="link-dot"
                      style="background:{source.kind === 'real' ? categoryColor(source.category, $settings.catColorOverrides) : 'var(--muted-2)'}"
                    ></span>
                    <span class="link-title">{source.title}</span>
                    {#if edge.confidence !== undefined}
                      <span class="confidence" title="relation confidence"
                        >{confidenceLabel(edge.confidence)}</span
                      >
                    {/if}
                  </button>
                </li>
              {/if}
            {/each}
          </ul>
          {/each}
        </div>
      {/if}
    {:else if ghostNode}
      <div class="ghost-body">
        <div class="ghost-message">This note hasn't been written yet.</div>
        {#if ghostNode.referencedBy.length > 0}
          <div class="links-section">
            <div class="links-label">Referenced by</div>
            <ul class="link-list">
              {#each ghostNode.referencedBy as sourceId}
                {@const source = nodeById(sourceId)}
                {#if source}
                  <li>
                    <button class="link-item" on:click={() => navigateTo(sourceId)}>
                      <span
                        class="link-dot"
                        style="background:{source.kind === 'real' ? categoryColor(source.category, $settings.catColorOverrides) : 'var(--muted-2)'}"
                      ></span>
                      <span class="link-title">{source.title}</span>
                    </button>
                  </li>
                {/if}
              {/each}
            </ul>
          </div>
        {/if}
      </div>
    {/if}

    <!-- Meta footer (real nodes) -->
    {#if realNode}
      <div class="meta-footer">
        {#if realNode.wordCount}
          <span class="meta-item">{realNode.wordCount} words</span>
        {/if}
        {#if realNode.modified}
          <span class="meta-item">Modified {realNode.modified.slice(0, 10)}</span>
        {/if}
      </div>
    {/if}
  </aside>
{/if}

<style>
  .kind-label {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 10.5px;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--muted-2);
    margin: 8px 0 2px;
  }
  .kind-dash {
    display: inline-block;
    width: 14px;
    border-top-width: 2px;
  }
  .kind-count {
    margin-left: auto;
    font-variant-numeric: tabular-nums;
  }
  .confidence {
    margin-left: auto;
    font-size: 10.5px;
    color: var(--muted-2);
    font-variant-numeric: tabular-nums;
  }

  .detail-panel {
    /* width controlled by inline style (resize handle) */
    min-width: 240px;
    max-width: 640px;
    background: var(--panel);
    border-left: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    overflow-y: auto;
    flex-shrink: 0;
    position: relative;
  }

  .resize-handle {
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 5px;
    cursor: col-resize;
    z-index: 5;
    transition: background 0.15s;
  }
  .resize-handle:hover,
  .resize-handle.resizing {
    background: rgba(88, 166, 255, 0.25);
  }

  /* Prevent text selection while dragging */
  :global(body.resizing-panel) {
    user-select: none;
    cursor: col-resize;
  }

  .panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 12px 8px;
    border-bottom: 1px solid var(--border-2);
    gap: 8px;
  }

  .header-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
    flex: 1;
    min-width: 0;
  }

  .badge {
    font-size: 10px;
    padding: 2px 7px;
    border-radius: 10px;
    font-weight: 500;
    white-space: nowrap;
  }

  .category-badge {
    border: 1px solid transparent;
  }

  .level-badge {
    background: var(--panel-3);
    color: var(--muted);
    border: 1px solid var(--border);
  }

  .status-badge {
    background: transparent;
  }

  .ghost-badge {
    background: var(--panel-2);
    color: var(--muted-2);
    border: 1px solid var(--border);
  }

  .close-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    border-radius: 4px;
    border: none;
    background: transparent;
    color: var(--muted);
    cursor: pointer;
    flex-shrink: 0;
    transition: all 0.12s;
  }
  .close-btn:hover {
    background: var(--panel-2);
    color: var(--text);
  }

  .note-title {
    font-size: 15px;
    font-weight: 600;
    color: var(--text);
    margin: 0;
    padding: 10px 14px 6px;
    line-height: 1.3;
  }

  .tag-row {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    padding: 4px 14px 8px;
  }

  .tag-chip {
    font-size: 11px;
    color: var(--accent);
    background: rgba(88, 166, 255, 0.08);
    border: 1px solid rgba(88, 166, 255, 0.2);
    border-radius: 3px;
    padding: 2px 7px;
    cursor: pointer;
    transition: background 0.12s, border-color 0.12s;
  }
  .tag-chip:hover {
    background: rgba(88, 166, 255, 0.16);
  }
  .tag-chip--active {
    background: rgba(88, 166, 255, 0.22);
    border-color: rgba(88, 166, 255, 0.55);
    color: var(--text);
  }

  /* ── Location bar ─────────────────────────────────────────── */
  .location-bar {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 5px 14px 7px;
    border-bottom: 1px solid var(--border-2);
    min-width: 0;
  }

  .folder-icon {
    color: var(--muted-2);
    flex-shrink: 0;
  }

  .location-path {
    font-size: 11px;
    font-family: var(--font-mono);
    color: var(--muted);
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .copy-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    padding: 0;
    border: none;
    border-radius: 3px;
    background: transparent;
    color: var(--muted-2);
    cursor: pointer;
    flex-shrink: 0;
    transition: color 0.1s, background 0.1s;
  }
  .copy-btn:hover {
    background: var(--panel-2);
    color: var(--text);
  }
  .copy-btn--ok {
    color: var(--green);
  }

  .obsidian-btn {
    display: flex;
    align-items: center;
    gap: 4px;
    flex-shrink: 0;
    font-size: 11px;
    font-weight: 500;
    color: var(--accent);
    text-decoration: none;
    padding: 3px 7px;
    border-radius: 4px;
    border: 1px solid rgba(88, 166, 255, 0.25);
    background: rgba(88, 166, 255, 0.07);
    transition: background 0.12s, border-color 0.12s;
    white-space: nowrap;
  }
  .obsidian-btn:hover {
    background: rgba(88, 166, 255, 0.15);
    border-color: rgba(88, 166, 255, 0.5);
  }

  .body-loading {
    display: flex;
    gap: 5px;
    padding: 16px 14px;
    align-items: center;
  }

  .loading-dot {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: var(--muted-2);
    animation: pulse 1.2s ease-in-out infinite;
  }
  .loading-dot:nth-child(2) { animation-delay: 0.2s; }
  .loading-dot:nth-child(3) { animation-delay: 0.4s; }

  @keyframes pulse {
    0%, 100% { opacity: 0.3; }
    50% { opacity: 1; }
  }

  .excerpt-notice {
    font-size: 10px;
    color: var(--muted-2);
    margin-bottom: 6px;
    font-style: italic;
  }

  .body-section {
    padding: 0 14px 8px;
    border-bottom: 1px solid var(--border-2);
  }

  .ghost-body {
    padding: 12px 14px;
  }

  .ghost-message {
    color: var(--muted);
    font-size: 13px;
    font-style: italic;
    margin-bottom: 12px;
  }

  .links-section {
    padding: 8px 12px;
    border-top: 1px solid var(--border-2);
  }

  .links-label {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--muted-2);
    margin-bottom: 6px;
  }

  .link-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .link-item {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 5px 7px;
    border: none;
    border-radius: 4px;
    background: transparent;
    color: var(--muted);
    cursor: pointer;
    text-align: left;
    font-size: 12px;
    transition: all 0.1s;
  }
  .link-item:hover {
    background: var(--panel-2);
    color: var(--text);
  }

  .link-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .link-title {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .ghost-label {
    font-size: 10px;
    color: var(--muted-2);
    border: 1px solid var(--border);
    border-radius: 3px;
    padding: 1px 4px;
  }

  .meta-footer {
    margin-top: auto;
    padding: 8px 14px;
    border-top: 1px solid var(--border-2);
    display: flex;
    gap: 12px;
  }

  .meta-item {
    font-size: 11px;
    color: var(--muted-2);
  }
</style>
