import type { GraphEdge, RealNode } from './GraphModel'
import { BELONGS_TO } from './millerTree'

/**
 * Subjects × categories, counted from the files that hang under each.
 *
 * The graph answers "what is connected to what". It does not answer "what do I still not
 * have" — and in a course package that is the question: a subject with no lectures, or one
 * where everything is still waiting for a human, looks exactly like a healthy one when it
 * is a cloud of dots.
 */

/** Levels as this vault means them (`orglib/synapse_vault.py`). */
const LEVEL_IN_PACKAGE = 1
const LEVEL_PLANNED = 2
const LEVEL_NEEDS_HUMAN = 3

const NODE_SUBJECT = 'subject'
const NODE_SEMESTER = 'semester'
const NODE_FILE = 'file'

export interface MatrixCell {
  count: number
  inPackage: number
  planned: number
  needsHuman: number
}

export interface MatrixRow {
  subject: RealNode
  semester: RealNode | null
  total: number
  cells: Map<string, MatrixCell>
}

export interface CoverageMatrix {
  /** Category columns, widest first — the eye should meet the bulk of the material. */
  categories: string[]
  categoryTotals: Map<string, number>
  rows: MatrixRow[]
  /** Subjects with nothing under them; the view folds these away by default. */
  emptyRowCount: number
}

const EMPTY_CELL: MatrixCell = { count: 0, inPackage: 0, planned: 0, needsHuman: 0 }

/** A row's cell for a category, or a real zero — an absent cell IS the finding here. */
export function cellOf(row: MatrixRow, category: string): MatrixCell {
  return row.cells.get(category) ?? EMPTY_CELL
}

export function buildCoverageMatrix(
  nodes: readonly RealNode[],
  edges: readonly GraphEdge[],
): CoverageMatrix {
  const byId = new Map(nodes.map((n) => [n.id, n]))
  const parent = new Map<string, string>()
  for (const edge of edges) {
    if (edge.kind !== BELONGS_TO) continue
    if (!byId.has(edge.source) || !byId.has(edge.target)) continue
    if (!parent.has(edge.source)) parent.set(edge.source, edge.target)
  }

  const rows = new Map<string, MatrixRow>()
  for (const node of nodes) {
    if (node.type !== NODE_SUBJECT) continue
    rows.set(node.id, {
      subject: node,
      semester: ancestorOfType(node.id, NODE_SEMESTER, parent, byId),
      total: 0,
      cells: new Map(),
    })
  }

  const categoryTotals = new Map<string, number>()

  for (const node of nodes) {
    if (node.type !== NODE_FILE) continue
    const subject = ancestorOfType(node.id, NODE_SUBJECT, parent, byId)
    // A file with no subject is a loose end of the export, not a column: counting it
    // would invent a category nobody can navigate to.
    if (!subject) continue

    const row = rows.get(subject.id)
    if (!row) continue

    // The raw category, deliberately not normalised: `wykład` and `wyklad` are two
    // columns because they are two values in the data, and this view is where that
    // shows up (docs/SYNAPSE.md — the split dictionary).
    const category = node.category
    const cell = row.cells.get(category) ?? { ...EMPTY_CELL }
    cell.count += 1
    if (node.level === LEVEL_IN_PACKAGE) cell.inPackage += 1
    else if (node.level === LEVEL_PLANNED) cell.planned += 1
    else if (node.level === LEVEL_NEEDS_HUMAN) cell.needsHuman += 1
    row.cells.set(category, cell)
    row.total += 1

    categoryTotals.set(category, (categoryTotals.get(category) ?? 0) + 1)
  }

  const categories = [...categoryTotals.keys()].sort((a, b) => {
    const byCount = (categoryTotals.get(b) ?? 0) - (categoryTotals.get(a) ?? 0)
    return byCount !== 0 ? byCount : a.localeCompare(b, 'pl')
  })

  const ordered = [...rows.values()].sort((a, b) => {
    const bySemester = (a.semester?.title ?? '').localeCompare(b.semester?.title ?? '', 'pl')
    if (bySemester !== 0) return bySemester
    return a.subject.title.localeCompare(b.subject.title, 'pl')
  })

  return {
    categories,
    categoryTotals,
    rows: ordered,
    emptyRowCount: ordered.filter((r) => r.total === 0).length,
  }
}

/**
 * Walks up the containment chain to the nearest node of `type`.
 *
 * A file does not hang off its subject directly — there is a category between them, and
 * often a source folder below that — so counting has to climb rather than look at the
 * parent. The step limit is there because a malformed vault must not hang the view.
 */
function ancestorOfType(
  id: string,
  type: string,
  parent: ReadonlyMap<string, string>,
  byId: ReadonlyMap<string, RealNode>,
): RealNode | null {
  let current = parent.get(id)
  for (let steps = 0; current !== undefined && steps < 16; steps += 1) {
    const node = byId.get(current)
    if (node?.type === type) return node
    current = parent.get(current)
  }
  return null
}
