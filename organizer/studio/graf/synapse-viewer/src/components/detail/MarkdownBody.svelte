<script lang="ts">
  import { createEventDispatcher } from 'svelte'
  import type { GraphEdge } from '../../domain/graph/GraphModel'

  export let html: string
  export let edges: GraphEdge[]

  const dispatch = createEventDispatcher<{ navigate: string }>()

  function handleClick(e: MouseEvent) {
    const a = (e.target as Element).closest('.wikilink')
    if (!a) return
    e.preventDefault()
    const linkText = a.getAttribute('data-linktext')
    if (!linkText) return
    const edge = edges.find((ed) => ed.linkText === linkText)
    if (edge) dispatch('navigate', edge.target)
  }
</script>

<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions a11y_no_noninteractive_element_interactions -->
<div class="markdown-body" role="document" on:click={handleClick}>
  {@html html}
</div>

<style>
  .markdown-body {
    color: var(--text);
    font-size: 13px;
    line-height: 1.6;
  }

  /* Headings */
  .markdown-body :global(h1),
  .markdown-body :global(h2),
  .markdown-body :global(h3),
  .markdown-body :global(h4),
  .markdown-body :global(h5),
  .markdown-body :global(h6) {
    color: var(--text);
    font-weight: 600;
    margin: 1em 0 0.4em;
    line-height: 1.3;
  }
  .markdown-body :global(h1) { font-size: 1.4em; }
  .markdown-body :global(h2) { font-size: 1.2em; }
  .markdown-body :global(h3) { font-size: 1.05em; }

  .markdown-body :global(p) {
    margin: 0 0 0.75em;
  }

  .markdown-body :global(a) {
    color: var(--accent);
    text-decoration: none;
  }
  .markdown-body :global(a:hover) {
    text-decoration: underline;
  }

  /* Wikilinks */
  .markdown-body :global(.wikilink) {
    color: var(--accent);
    background: rgba(88, 166, 255, 0.08);
    border-radius: 3px;
    padding: 0 3px;
    cursor: pointer;
  }
  .markdown-body :global(.wikilink:hover) {
    background: rgba(88, 166, 255, 0.18);
    text-decoration: none;
  }

  /* Code */
  .markdown-body :global(code) {
    font-family: var(--font-mono);
    font-size: 0.88em;
    background: var(--panel-3);
    border: 1px solid var(--border);
    border-radius: 3px;
    padding: 1px 5px;
    color: var(--text);
  }

  .markdown-body :global(pre) {
    background: var(--bg-deep);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 12px 14px;
    overflow-x: auto;
    margin: 0 0 1em;
  }

  .markdown-body :global(pre code) {
    background: none;
    border: none;
    padding: 0;
    font-size: 0.85em;
    line-height: 1.5;
  }

  /* Lists */
  .markdown-body :global(ul),
  .markdown-body :global(ol) {
    margin: 0 0 0.75em;
    padding-left: 1.4em;
  }

  .markdown-body :global(li) {
    margin-bottom: 0.2em;
  }

  /* Blockquotes */
  .markdown-body :global(blockquote) {
    border-left: 3px solid var(--border);
    margin: 0 0 0.75em;
    padding: 0 0 0 12px;
    color: var(--muted);
  }

  /* Horizontal rule */
  .markdown-body :global(hr) {
    border: none;
    border-top: 1px solid var(--border);
    margin: 1em 0;
  }

  /* Tables */
  .markdown-body :global(table) {
    border-collapse: collapse;
    width: 100%;
    margin-bottom: 0.75em;
    font-size: 0.92em;
  }
  .markdown-body :global(th),
  .markdown-body :global(td) {
    border: 1px solid var(--border);
    padding: 5px 10px;
    text-align: left;
  }
  .markdown-body :global(th) {
    background: var(--panel-2);
    font-weight: 600;
  }
</style>
