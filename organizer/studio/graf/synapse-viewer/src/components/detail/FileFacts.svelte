<script lang="ts">
  import type { FileInfo, RealNode } from '../../domain/graph/GraphModel'
  import { categoryColor } from '../../domain/color/categoryColor'
  import { settings } from '../../stores/settingsStore'
  import { humanSize } from '../../domain/format/size'
  import CopyButton from './CopyButton.svelte'
  import FilePreview from './FilePreview.svelte'
  import ProvenanceTreeView from './ProvenanceTreeView.svelte'
  import SectionHeading from './SectionHeading.svelte'

  export let node: RealNode
  export let file: FileInfo

  $: decision = file.decision
  $: target = decision?.target ?? ''
  $: folder = target.slice(0, target.lastIndexOf('/') + 1)
  $: name = target.slice(target.lastIndexOf('/') + 1)

  /** Below this a classification is a question, not an answer (`thresholds.yaml`). */
  const SURE = 0.9
  const LIKELY = 0.7

  function confidenceVar(value: number): string {
    if (value >= SURE) return 'var(--green)'
    return value >= LIKELY ? 'var(--amber)' : 'var(--red)'
  }
</script>

<!-- Trzy pytania, trzy sekcje: czym ten plik jest, gdzie trafi, skąd się wziął.
     Bez nagłówków i linii działowych wszystko zlewało się w jedną kolumnę drobnego
     tekstu i nie dało się przeskoczyć wzrokiem do właściwego miejsca (2026-09-30). -->
{#if file.preview || node.sha256 || node.contentKind || node.sizeBytes}
  <section class="block">
    <SectionHeading title="Zawartość" />

    {#if file.preview}
      <FilePreview
        preview={file.preview}
        contentKind={node.contentKind}
        sizeBytes={node.sizeBytes}
      />
    {/if}

    <div class="ids">
      {#if node.sha256}
        <span class="sha" title={node.sha256}>{node.sha256.slice(0, 12)}…</span>
        <CopyButton value={node.sha256} label="Copy sha256" />
      {/if}
      {#if node.contentKind}<span class="chip">{node.contentKind}</span>{/if}
      {#if humanSize(node.sizeBytes)}<span class="chip">{humanSize(node.sizeBytes)}</span>{/if}
      <span class="grow"></span>
      {#if file.studioUrl}
        <!-- Absolute on purpose: studio serves the viewer under /graf/, and this leaves it. -->
        <a class="studio" href={file.studioUrl}>Otwórz w studiu ↗</a>
      {/if}
    </div>
  </section>
{/if}

{#if target || decision}
  <section class="block">
    <SectionHeading title={decision?.inPackage ? 'Leży w paczce' : 'Trafi do paczki'} />

    {#if target}
      <div class="path-row">
        <span class="path" title={target}><span class="dir">{folder}</span>{name}</span>
        <CopyButton value={target} label="Copy target path" />
      </div>
    {/if}

    {#if decision}
      <div class="facts">
        {#if decision.action}
          <span class="badge action">{decision.action}</span>
        {/if}
        {#if decision.category}
          <span
            class="badge cat"
            style="color:{categoryColor(decision.category, $settings.catColorOverrides)}"
          >{decision.category}</span>
        {/if}
        {#if decision.confidence !== undefined}
          <span class="confidence" style="color:{confidenceVar(decision.confidence)}">
            {decision.confidence.toFixed(2)}
          </span>
        {/if}
        {#if decision.method}<span class="method">{decision.method}</span>{/if}
        {#if decision.needsReview}<span class="badge review">do przeglądu</span>{/if}
      </div>
      {#if decision.reason}
        <p class="reason">{decision.reason}</p>
      {/if}
    {/if}
  </section>
{/if}

{#if file.provenance}
  <section class="block">
    <ProvenanceTreeView copies={file.provenance.copies} total={file.provenance.total} />
  </section>
{/if}

<style>
  /* Linia działowa niesie oddzielenie sekcji; nagłówek mówi, o co w niej chodzi. */
  .block + .block {
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid var(--border);
  }

  .path-row { display: flex; align-items: flex-start; gap: 6px; margin: 0 0 8px; }
  .path {
    font-family: var(--font-mono);
    font-size: 11.5px;
    color: var(--text);
    overflow-wrap: anywhere;
    min-width: 0;
  }
  /* Katalog jest kontekstem, nazwa jest odpowiedzią — stąd różnica kontrastu. */
  .dir { color: var(--muted-2); }

  .facts {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px;
    margin: 0;
  }

  .badge {
    padding: 1px 7px;
    border-radius: 10px;
    font-size: 10.5px;
    background: var(--panel-3);
    color: var(--muted);
  }
  .action { color: var(--text); }
  .cat { background: transparent; border: 1px solid currentColor; }
  .review { color: var(--red); background: rgba(248, 81, 73, 0.12); }

  .confidence { font-size: 12px; font-variant-numeric: tabular-nums; }
  .method { font-family: var(--font-mono); font-size: 10.5px; color: var(--muted-2); }

  .reason {
    margin: 6px 0 0;
    font-size: 11.5px;
    color: var(--muted-2);
  }

  .ids {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px;
    margin: 0;
    font-size: 11px;
    color: var(--muted-2);
  }
  .sha { font-family: var(--font-mono); white-space: nowrap; }
  .chip { padding: 1px 6px; border-radius: 4px; background: var(--panel-3); white-space: nowrap; }
  .grow { flex: 1; }
  .studio { color: var(--accent); text-decoration: none; white-space: nowrap; }
  .studio:hover { text-decoration: underline; }
</style>
