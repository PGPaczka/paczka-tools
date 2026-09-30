<script lang="ts">
  import { graph, filters } from '../../stores/graphStore'
  import { selectedId } from '../../stores/selectionStore'
  import { realNodesIgnoringNodeType } from '../../domain/graph/selectors'
  import { buildCoverageMatrix, cellOf, type MatrixRow } from '../../domain/graph/coverageMatrix'
  import { scopeLevels } from '../../domain/graph/scope'
  import type { RealNode } from '../../domain/graph/GraphModel'

  export let onPick:
    | ((tag: string | null, category: string, subjectId?: string) => void)
    | undefined = undefined

  $: nodes = $graph ? realNodesIgnoringNodeType($graph, $filters) : []
  $: matrix = buildCoverageMatrix(nodes, $graph?.edges ?? [])

  // Which tag identifies a subject on its own is already solved for the scope picker —
  // reusing it keeps one answer to that question instead of two that can disagree.
  $: subjectTags = subjectTagMap($graph?.nodes ?? [])

  function subjectTagMap(all: readonly { kind: string }[]): Map<string, string> {
    const real = all.filter((n): n is RealNode => n.kind === 'real')
    const levels = scopeLevels(real)
    const map = new Map<string, string>()
    for (const level of levels) {
      for (const option of level.options) map.set(option.id, option.tag)
    }
    return map
  }

  let showEmpty = false

  $: visibleRows = showEmpty ? matrix.rows : matrix.rows.filter((r) => r.total > 0)

  /** Rows carry their semester so the table can break between them. */
  function semesterChanged(rows: MatrixRow[], index: number): boolean {
    if (index === 0) return true
    return rows[index - 1].semester?.id !== rows[index].semester?.id
  }

  function pick(row: MatrixRow, category: string) {
    const tag = subjectTags.get(row.subject.id) ?? null
    selectedId.set(row.subject.id)
    // The node id goes along with the tag: the tag narrows THIS view, the id is what
    // the host can resolve back to a subject without parsing anything by hand.
    onPick?.(tag, category, row.subject.id)
  }
</script>

<div class="matrix-view">
  <div class="toolbar">
    <span class="count">{visibleRows.length} przedmiotów · {matrix.categories.length} kategorii</span>
    <span class="flex-1"></span>
    <label class="toggle">
      <input type="checkbox" bind:checked={showEmpty} />
      pokaż {matrix.emptyRowCount} pustych
    </label>
    <span class="legend">
      <span class="chip l1"></span> w paczce
      <span class="chip l2"></span> zaplanowane
      <span class="chip l3"></span> do przeglądu
    </span>
  </div>

  <div class="scroll">
    {#if matrix.categories.length === 0}
      <p class="empty">Żaden plik nie pasuje do tych filtrów.</p>
    {:else}
      <table>
        <thead>
          <tr>
            <th class="corner">przedmiot</th>
            {#each matrix.categories as category}
              <th class="cat" title="{category} · {matrix.categoryTotals.get(category)} plików">
                <span>{category}</span>
              </th>
            {/each}
            <th class="total">razem</th>
          </tr>
        </thead>
        <tbody>
          {#each visibleRows as row, index (row.subject.id)}
            {#if semesterChanged(visibleRows, index)}
              <tr class="sem-break">
                <th class="sem" colspan={matrix.categories.length + 2}>
                  {row.semester?.title ?? 'bez semestru'}
                </th>
              </tr>
            {/if}
            <tr class:selected={$selectedId === row.subject.id}>
              <th class="subject" title={row.subject.title}>{row.subject.title}</th>
              {#each matrix.categories as category}
                {@const cell = cellOf(row, category)}
                <!-- svelte-ignore a11y-click-events-have-key-events -->
                <td
                  class="cell"
                  class:gap={cell.count === 0}
                  role={cell.count > 0 ? 'button' : undefined}
                  tabindex={cell.count > 0 ? 0 : -1}
                  on:click={() => cell.count > 0 && pick(row, category)}
                  title="{row.subject.title} · {category}: {cell.count}"
                >
                  {#if cell.count > 0}
                    <span class="num">{cell.count}</span>
                    <!-- Trzy paski zamiast jednego koloru: „część w paczce, część do
                         przeglądu" to typowy stan i dominanta by go zjadła. -->
                    <span class="bars">
                      {#if cell.inPackage}
                        <span class="seg l1" style="flex:{cell.inPackage}"></span>
                      {/if}
                      {#if cell.planned}
                        <span class="seg l2" style="flex:{cell.planned}"></span>
                      {/if}
                      {#if cell.needsHuman}
                        <span class="seg l3" style="flex:{cell.needsHuman}"></span>
                      {/if}
                    </span>
                  {/if}
                </td>
              {/each}
              <td class="cell total">{row.total || ''}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </div>
</div>

<style>
  .matrix-view {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .toolbar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 12px;
    border-bottom: 1px solid var(--border);
    background: var(--panel);
    font-size: 12px;
    color: var(--muted);
    flex-shrink: 0;
    overflow-x: auto;
    white-space: nowrap;
  }
  .flex-1 { flex: 1; }

  .toggle, .legend {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11.5px;
    color: var(--muted-2);
    cursor: pointer;
  }

  .chip, .seg {
    display: inline-block;
    border-radius: 2px;
  }
  .chip { width: 9px; height: 9px; }
  .l1 { background: #3fb950; }
  .l2 { background: #d29922; }
  .l3 { background: #f85149; }

  .scroll { flex: 1; overflow: auto; }
  .empty { padding: 20px; color: var(--muted); font-size: 12.5px; }

  table {
    border-collapse: separate;
    border-spacing: 0;
    font-size: 11.5px;
  }

  th, td {
    border-bottom: 1px solid var(--border);
    border-right: 1px solid var(--border);
    padding: 0;
  }

  /* Nagłówek i pierwsza kolumna zostają na ekranie: bez tego przy 98 przedmiotach
     i ~22 kategoriach nie wiadomo, którą liczbę się czyta. */
  thead th {
    position: sticky;
    top: 0;
    z-index: 2;
    background: var(--panel);
    color: var(--muted);
    font-weight: 500;
    padding: 6px 8px;
    text-align: left;
    white-space: nowrap;
  }

  th.corner {
    left: 0;
    z-index: 3;
  }

  th.subject, th.sem {
    position: sticky;
    left: 0;
    z-index: 1;
    background: var(--panel);
    color: var(--text);
    font-weight: 500;
    text-align: left;
    padding: 4px 8px;
    max-width: 180px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  tr.sem-break th.sem {
    color: var(--muted-2);
    background: var(--panel-2);
    font-size: 11px;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  .cell {
    min-width: 46px;
    height: 30px;
    text-align: center;
    vertical-align: middle;
    color: var(--text);
    position: relative;
  }
  .cell[role='button'] { cursor: pointer; }
  .cell[role='button']:hover { background: var(--panel-2); }

  /* Luka jest treścią tego widoku, więc musi być widoczna, a nie biała. */
  .cell.gap {
    background: repeating-linear-gradient(
      -45deg, transparent, transparent 4px, var(--border) 4px, var(--border) 5px
    );
  }

  .num { display: block; line-height: 1; padding-top: 5px; }

  .bars {
    position: absolute;
    left: 4px;
    right: 4px;
    bottom: 4px;
    height: 3px;
    display: flex;
    gap: 1px;
  }
  .seg { height: 3px; }

  /* Poniżej 820px powłoka wystawia pływający przycisk szuflady filtrów w lewym górnym
     rogu obszaru roboczego (left 8px, top 68px, 36×36). Pasek ustępuje mu miejsca w obu
     osiach: wcięcie z lewej odsłania treść, a wysokość sprawia, że przycisk siada NA
     pasku zamiast na pierwszym wierszu listy, który jest celem kliknięcia. */
  @media (max-width: 820px) {
    .toolbar { padding-left: 52px; min-height: 60px; }
  }

  td.total, th.total { color: var(--muted); }
  tr.selected th.subject { color: var(--accent, #58a6ff); }
</style>
