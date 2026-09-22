<script lang="ts">
  import {
    getClusters,
    getClusterDiff,
    resolveCluster,
    type Cluster,
    type ClusterDiff,
    type ClustersPage,
    type Item,
  } from '../lib/api';
  import { basename, bytes, percent } from '../lib/format';
  import { previewImageUrl } from '../lib/api';
  import Lightbox from './Lightbox.svelte';

  interface Props {
    semester?: number | null;
    skrot?: string | null;
    onResolved?: () => void;
  }

  let { semester = null, skrot = null, onResolved }: Props = $props();

  let page = $state<ClustersPage | null>(null);
  let loading = $state(false);
  let error = $state<string | null>(null);
  let success = $state<string | null>(null);
  let noiseFilter = $state('');

  /** Treść oglądana na cały ekran: {sha, nazwa} albo nic. */
  let zoomed = $state<{ sha256: string; name: string } | null>(null);

  /** Treści, dla których podgląd zwraca obrazek (PDF renderuje stronę). */
  const SHOWABLE = new Set(['image', 'pdf']);
  const showsPicture = (kind: string | null | undefined) => SHOWABLE.has(String(kind ?? ''));

  let expandedIndex = $state<number | null>(null);
  /** Ile miniatur rozwiniętego klastra już doszło — widać, że się doczytują,
   *  zamiast patrzeć na puste kafelki i zgadywać, czy coś się dzieje. */
  let thumbsLoaded = $state(0);
  const thumbsExpected = $derived(
    expandedIndex === null
      ? 0
      : (page?.clusters[expandedIndex]?.members ?? []).filter((member) =>
          showsPicture(member.content_kind),
        ).length,
  );
  let selectedCanonical = $state<string | null>(null);

  let diff = $state<ClusterDiff | null>(null);
  let diffLoading = $state(false);
  let diffPair = $state<[string, string] | null>(null);

  async function load(): Promise<void> {
    loading = true;
    error = null;
    try {
      const filters: Record<string, unknown> = {};
      if (semester) filters.semester = semester;
      if (skrot) filters.skrot = skrot;
      if (noiseFilter.trim()) filters.noise = noiseFilter.trim();
      page = await getClusters(filters as any);
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc);
    } finally {
      loading = false;
    }
  }

  function toggle(index: number): void {
    thumbsLoaded = 0;
    if (expandedIndex === index) {
      expandedIndex = null;
      selectedCanonical = null;
      diff = null;
      diffPair = null;
    } else {
      expandedIndex = index;
      selectedCanonical = null;
      diff = null;
      diffPair = null;
    }
  }

  function selectCanonical(sha: string): void {
    selectedCanonical = sha;
  }

  async function loadDiff(leftSha: string, rightSha: string): Promise<void> {
    if (diffPair && diffPair[0] === leftSha && diffPair[1] === rightSha) {
      diff = null;
      diffPair = null;
      return;
    }
    diffLoading = true;
    diff = null;
    diffPair = [leftSha, rightSha];
    try {
      diff = await getClusterDiff(leftSha, rightSha);
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc);
      diffPair = null;
    } finally {
      diffLoading = false;
    }
  }

  async function resolve(cluster: Cluster): Promise<void> {
    if (!selectedCanonical) return;
    error = null;
    success = null;
    const members = cluster.members.map((m) => m.sha256);
    try {
      const result = await resolveCluster(selectedCanonical, members);
      success = `Klaster rozstrzygnięty: ${result.skipped} oznaczonych jako skip`;
      expandedIndex = null;
      selectedCanonical = null;
      diff = null;
      diffPair = null;
      onResolved?.();
      await load();
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc);
    }
  }

  function relationLabel(type: string): string {
    switch (type) {
      case 'near_duplicate': return 'near-dupe';
      case 'older_version': return 'starsza wersja';
      case 'related': return 'powiązany';
      default: return type;
    }
  }

  $effect(() => {
    const _deps = [semester, skrot];
    load();
  });
</script>

<div class="cluster-panel">
  <div class="header">
    <h3>Klastry near-dupe</h3>
    <span class="total num">{page?.total ?? 0} klastrów</span>
  </div>

  <div class="noise-row">
    <input
      type="text"
      bind:value={noiseFilter}
      placeholder="Dodatkowy filtr szumu (fnmatch, domyślne w config)"
      onchange={load}
    />
    <button onclick={load} title="Przeładuj klastry">odśwież</button>
  </div>

  {#if error}
    <div class="msg error">{error}</div>
  {/if}
  {#if success}
    <div class="msg success">{success}</div>
  {/if}

  {#if loading}
    <div class="empty">Wczytuję klastry…</div>
  {:else if !page || page.total === 0}
    <div class="empty">Brak klastrów</div>
  {:else}
    <div class="cluster-list">
      {#each page.clusters as cluster, i}
        <div class="cluster-card" class:expanded={expandedIndex === i}>
          <button class="cluster-header" onclick={() => toggle(i)}>
            <span class="size num">{cluster.size} treści</span>
            <span class="tag" class:older={cluster.has_older_version}>
              {cluster.has_older_version ? 'wersje' : 'duplikaty'}
            </span>
            <span class="strength num">{percent(cluster.strength)}</span>
            <span class="arrow">{expandedIndex === i ? '▾' : '▸'}</span>
          </button>

          {#if expandedIndex === i}
            <div class="cluster-body">
              {#if thumbsExpected > 0 && thumbsLoaded < thumbsExpected}
                <div class="thumbs-progress">
                  podglądy: {thumbsLoaded} / {thumbsExpected}
                  <span class="bar"><span style="width: {(thumbsLoaded / thumbsExpected) * 100}%"></span></span>
                </div>
              {/if}
              <div class="members-grid">
                {#each cluster.members as member}
                  <button
                    class="member-card"
                    class:canonical={selectedCanonical === member.sha256}
                    onclick={() => selectCanonical(member.sha256)}
                    title="Kliknij, żeby oznaczyć jako kanoniczną"
                  >
                    {#if showsPicture(member.content_kind)}
                      <span class="thumb-wrap">
                        <img
                          class="member-thumb"
                          loading="lazy"
                          onload={() => (thumbsLoaded += 1)}
                          onerror={() => (thumbsLoaded += 1)}
                          src={previewImageUrl(member.sha256, 1, 240)}
                          alt="Podgląd: {member.filename ?? member.sha256.slice(0, 12)}"
                        />
                        <!-- Osobna lupka, bo klik w kartę wybiera wersję kanoniczną. -->
                        <span
                          class="zoom-badge"
                          role="button"
                          tabindex="0"
                          title="Pokaż na cały ekran"
                          onclick={(e) => { e.stopPropagation();
                            zoomed = { sha256: member.sha256, name: member.filename ?? member.sha256 }; }}
                          onkeydown={(e) => { if (e.key === 'Enter') { e.stopPropagation();
                            zoomed = { sha256: member.sha256, name: member.filename ?? member.sha256 }; } }}
                        >⤢</span>
                      </span>
                    {/if}
                    <div class="member-sha mono">{member.sha256.slice(0, 12)}…</div>
                    {#if member.filename}
                      <div class="member-name">{member.filename}</div>
                    {/if}
                    {#if member.content_kind}
                      <span class="tag kind">{member.content_kind}</span>
                    {/if}
                    {#if member.size_bytes}
                      <span class="member-size dim">{bytes(member.size_bytes)}</span>
                    {/if}
                    {#if member.confidence !== undefined && member.confidence !== null}
                      <span class="member-conf num">{percent(member.confidence)}</span>
                    {/if}
                    {#if member.action}
                      <span class="tag action-tag">{member.action}</span>
                    {/if}
                    {#if selectedCanonical === member.sha256}
                      <div class="canonical-badge">kanoniczna</div>
                    {/if}
                  </button>
                {/each}
              </div>

              <div class="relations-section">
                <div class="label dim">Relacje:</div>
                {#each cluster.relations as rel}
                  <div class="relation-row">
                    <span class="mono dim">{rel.source_sha256.slice(0, 8)}…</span>
                    <button class="diff-btn" onclick={() => loadDiff(rel.source_sha256, rel.target_sha256)}
                      title="Pokaż porównanie">
                      {relationLabel(rel.relation_type)}
                    </button>
                    <span class="mono dim">{rel.target_sha256.slice(0, 8)}…</span>
                    <span class="num">{percent(rel.confidence)}</span>
                    {#if rel.reason}
                      <span class="dim reason">{rel.reason}</span>
                    {/if}
                  </div>
                {/each}
              </div>

              {#if diffLoading}
                <div class="diff-panel">
                  <div class="empty">Wczytuję porównanie…</div>
                </div>
              {:else if diff}
                <div class="diff-panel">
                  <div class="diff-header">
                    <span class="tag">{diff.diff_type === 'text' ? 'diff tekstu' : 'porównanie metadanych'}</span>
                    {#if diff.relation}
                      <span class="dim">{diff.relation.reason}</span>
                    {/if}
                    <button class="close-diff" onclick={() => { diff = null; diffPair = null; }}>zamknij</button>
                  </div>

                  <div class="diff-sides">
                    <div class="diff-side">
                      <div class="diff-side-header">
                        <span class="mono">{diff.left.sha256.slice(0, 12)}…</span>
                        {#if diff.left.filename}
                          <span class="diff-filename">{diff.left.filename}</span>
                        {/if}
                      </div>
                      {#if showsPicture(diff.left.content_kind)}
                        <button
                          class="picture-btn"
                          title="Pokaż na cały ekran"
                          onclick={() => (zoomed = { sha256: diff!.left.sha256,
                            name: diff!.left.filename ?? diff!.left.sha256 })}
                        >
                          <img
                            class="diff-picture"
                            src={previewImageUrl(diff.left.sha256, 1, 700)}
                            alt="Podgląd: {diff.left.filename ?? ''}"
                          />
                        </button>
                      {/if}
                      <div class="diff-meta">
                        {#if diff.left.content_kind}<span class="tag">{diff.left.content_kind}</span>{/if}
                        {#if diff.left.size_bytes}<span class="dim">{bytes(diff.left.size_bytes)}</span>{/if}
                        {#if diff.left.category}<span>kat: {diff.left.category}</span>{/if}
                        {#if diff.left.action}<span>→ {diff.left.action}</span>{/if}
                        {#if diff.left.confidence !== null && diff.left.confidence !== undefined}
                          <span class="num">{percent(diff.left.confidence)}</span>
                        {/if}
                      </div>
                      {#if diff.left_text}
                        <pre class="diff-text">{diff.left_text}</pre>
                      {:else}
                        <div class="no-text dim">brak wyekstrahowanego tekstu</div>
                      {/if}
                    </div>

                    <div class="diff-side">
                      <div class="diff-side-header">
                        <span class="mono">{diff.right.sha256.slice(0, 12)}…</span>
                        {#if diff.right.filename}
                          <span class="diff-filename">{diff.right.filename}</span>
                        {/if}
                      </div>
                      {#if showsPicture(diff.right.content_kind)}
                        <button
                          class="picture-btn"
                          title="Pokaż na cały ekran"
                          onclick={() => (zoomed = { sha256: diff!.right.sha256,
                            name: diff!.right.filename ?? diff!.right.sha256 })}
                        >
                          <img
                            class="diff-picture"
                            src={previewImageUrl(diff.right.sha256, 1, 700)}
                            alt="Podgląd: {diff.right.filename ?? ''}"
                          />
                        </button>
                      {/if}
                      <div class="diff-meta">
                        {#if diff.right.content_kind}<span class="tag">{diff.right.content_kind}</span>{/if}
                        {#if diff.right.size_bytes}<span class="dim">{bytes(diff.right.size_bytes)}</span>{/if}
                        {#if diff.right.category}<span>kat: {diff.right.category}</span>{/if}
                        {#if diff.right.action}<span>→ {diff.right.action}</span>{/if}
                        {#if diff.right.confidence !== null && diff.right.confidence !== undefined}
                          <span class="num">{percent(diff.right.confidence)}</span>
                        {/if}
                      </div>
                      {#if diff.right_text}
                        <pre class="diff-text">{diff.right_text}</pre>
                      {:else}
                        <div class="no-text dim">brak wyekstrahowanego tekstu</div>
                      {/if}
                    </div>
                  </div>
                </div>
              {/if}

              <div class="resolve-actions">
                <button
                  class="resolve-btn"
                  disabled={!selectedCanonical}
                  onclick={() => resolve(cluster)}
                >
                  Rozstrzygnij → reszta skip
                </button>
                {#if !selectedCanonical}
                  <span class="dim hint">Kliknij kartę, żeby wybrać wersję kanoniczną</span>
                {/if}
              </div>
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>

{#if zoomed}
  <Lightbox
    src={previewImageUrl(zoomed.sha256, 1, 1800)}
    alt={zoomed.name}
    caption={zoomed.name}
    original={previewImageUrl(zoomed.sha256, 1, 2000)}
    onClose={() => (zoomed = null)}
  />
{/if}

<style>
  .cluster-panel {
    padding: 12px;
    overflow-y: auto;
  }
  .header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 8px;
  }
  .header h3 {
    margin: 0;
    font-size: 14px;
  }
  .total {
    color: var(--muted);
    font-size: 12px;
  }
  .noise-row {
    display: flex;
    gap: 6px;
    margin-bottom: 10px;
  }
  .noise-row input {
    flex: 1;
    padding: 4px 8px;
    border: 1px solid var(--border);
    border-radius: 4px;
    font-size: 12px;
    background: var(--bg-deep);
    color: var(--text);
  }
  .noise-row button {
    padding: 4px 10px;
    border: 1px solid var(--border);
    border-radius: 4px;
    font-size: 12px;
    color: var(--muted);
    background: transparent;
    cursor: pointer;
  }
  .noise-row button:hover {
    border-color: var(--accent-dim);
    color: var(--text);
  }
  .cluster-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .cluster-card {
    border: 1px solid var(--border);
    border-radius: 6px;
    overflow: hidden;
  }
  .cluster-card.expanded {
    border-color: var(--accent-dim);
  }
  .cluster-header {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 8px 12px;
    border: none;
    background: var(--bg-deep);
    color: var(--text);
    cursor: pointer;
    font-size: 12px;
    text-align: left;
  }
  .cluster-header:hover {
    background: var(--bg);
  }
  .arrow {
    margin-left: auto;
    color: var(--muted-2);
  }
  .cluster-body {
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .members-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 8px;
  }
  .member-card {
    display: flex;
    flex-direction: column;
    gap: 3px;
    padding: 10px;
    border: 2px solid var(--border);
    border-radius: 6px;
    background: var(--bg-deep);
    cursor: pointer;
    text-align: left;
    color: var(--text);
    font-size: 12px;
    transition: border-color 0.15s;
  }
  .member-card:hover {
    border-color: var(--accent-dim);
  }
  .member-card.canonical {
    border-color: var(--tag-ok);
    background: color-mix(in srgb, var(--tag-ok) 8%, var(--bg-deep));
  }
  .member-sha {
    font-size: 10px;
    color: var(--muted-2);
  }
  .member-name {
    font-weight: 600;
    font-size: 12px;
    word-break: break-all;
  }
  .member-size {
    font-size: 11px;
  }
  .member-conf {
    font-size: 11px;
  }
  .canonical-badge {
    margin-top: 4px;
    padding: 1px 6px;
    border-radius: 3px;
    font-size: 10px;
    background: var(--tag-ok);
    color: var(--bg);
    text-align: center;
    font-weight: 600;
  }
  .relations-section {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .relation-row {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
  }
  .diff-btn {
    padding: 1px 6px;
    border: 1px solid var(--border);
    border-radius: 3px;
    font-size: 10px;
    background: transparent;
    color: var(--text);
    cursor: pointer;
  }
  .diff-btn:hover {
    border-color: var(--accent-dim);
    background: var(--bg-deep);
  }
  .reason {
    font-size: 10px;
  }
  .diff-panel {
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px;
    background: var(--bg);
  }
  .diff-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 10px;
  }
  .close-diff {
    margin-left: auto;
    padding: 2px 8px;
    border: 1px solid var(--border);
    border-radius: 3px;
    font-size: 10px;
    background: transparent;
    color: var(--muted);
    cursor: pointer;
  }
  .close-diff:hover {
    color: var(--text);
  }
  .diff-sides {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }
  .diff-side {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }
  /* Miniatura w karcie: „czy to zdjęcie jest duplikatem" rozstrzyga oko, nie hash. */
  .thumbs-progress {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
    color: var(--muted-2);
    font-size: 11px;
  }
  .thumbs-progress .bar {
    flex: 1;
    max-width: 160px;
    height: 3px;
    border-radius: 999px;
    background: var(--panel-3);
    overflow: hidden;
  }
  .thumbs-progress .bar span {
    display: block;
    height: 100%;
    background: var(--accent-dim);
    transition: width 0.15s;
  }
  .thumb-wrap {
    position: relative;
    display: block;
  }
  .zoom-badge {
    position: absolute;
    right: 4px;
    bottom: 8px;
    padding: 0 6px;
    border-radius: 5px;
    background: rgba(1, 4, 9, 0.72);
    border: 1px solid var(--border);
    color: var(--text);
    font-size: 12px;
    line-height: 18px;
    cursor: zoom-in;
  }
  .picture-btn {
    display: block;
    width: 100%;
    padding: 0;
    cursor: zoom-in;
  }
  .member-thumb {
    width: 100%;
    height: 96px;
    object-fit: cover;
    border-radius: 4px;
    background: var(--bg-deep);
    margin-bottom: 4px;
  }
  /* Porównanie dwóch obrazów: `contain`, bo tu liczy się CAŁY kadr, nie ładne kafelki. */
  .diff-picture {
    width: 100%;
    max-height: 40vh;
    object-fit: contain;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg-deep);
  }

  .diff-side-header {
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
    font-size: 11px;
  }
  /* Nazwy w tej paczce bywają bardzo długie („…_2015_cz2_ODP.docx(1).docx”) i bez
     przycięcia wychodziły poza swoją kolumnę, nachodząc na drugą stronę diffa. */
  .diff-filename {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 600;
    font-size: 12px;
  }
  .diff-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    font-size: 11px;
  }
  .diff-text {
    margin: 0;
    padding: 8px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg-deep);
    font-size: 11px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 300px;
    overflow-y: auto;
  }
  .no-text {
    padding: 12px;
    text-align: center;
    font-size: 11px;
  }
  .resolve-actions {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .resolve-btn {
    padding: 6px 14px;
    border: 1px solid var(--tag-ok);
    border-radius: 4px;
    background: transparent;
    color: var(--tag-ok);
    font-size: 12px;
    cursor: pointer;
  }
  .resolve-btn:hover:not(:disabled) {
    background: color-mix(in srgb, var(--tag-ok) 15%, transparent);
  }
  .resolve-btn:disabled {
    opacity: 0.3;
    cursor: default;
  }
  .hint {
    font-size: 11px;
  }
  .tag {
    padding: 1px 6px;
    border-radius: 3px;
    font-size: 10px;
    background: color-mix(in srgb, var(--border) 50%, transparent);
  }
  .tag.older {
    color: var(--warn);
  }
  .msg {
    padding: 6px 10px;
    margin-bottom: 8px;
    border-radius: 4px;
    font-size: 12px;
  }
  .msg.error {
    background: color-mix(in srgb, var(--warn) 15%, transparent);
    color: var(--warn);
  }
  .msg.success {
    background: color-mix(in srgb, var(--tag-ok) 15%, transparent);
    color: var(--tag-ok);
  }
  .empty {
    padding: 24px;
    text-align: center;
    color: var(--muted);
  }
  .label {
    font-size: 11px;
  }
</style>
