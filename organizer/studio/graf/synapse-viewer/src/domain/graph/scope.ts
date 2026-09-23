import type { RealNode } from './GraphModel'
import { presentNodeTypes } from './edgeStyle'

/**
 * Scope picker: "show me THIS semester", "show me THIS subject".
 *
 * A typed vault is a hierarchy (semester → subject → file), but its levels are joined
 * by EDGES, while the filters work on tags. Picking a level by category looked like it
 * worked and quietly did not: in a course package only subject notes carry `SEM3`, so
 * "SEM3 + files" answered with the subjects alone and no files at all.
 *
 * The rule here is the one a vault can actually honour: a note is identified by the tag
 * no SIBLING carries — siblings being the notes of its own type under the same coarser
 * choice. Within semester 3, `ako` names one subject; within that subject, `kategoria-
 * kolokwia` names one category, even though a hundred other subjects have a `kolokwia`
 * of their own. Filters combine with AND, so `sem3 + ako + kategoria-kolokwia` lands
 * exactly where it should.
 *
 * Two earlier rules failed on real data and are worth remembering: "the rarest tag
 * shared with the level below" handed a file-less subject the tag of its semester (so
 * picking it emptied the graph), and "unique among ALL notes of this type" dropped both
 * the subjects whose skrót repeats in another semester and nearly every category.
 */
export interface ScopeOption {
  /** Node id of the coarse note (semester, subject, …). */
  id: string
  label: string
  /** The tag to put into the filters — it matches this note AND everything under it. */
  tag: string
  /** All tags of the note, so a finer level can be narrowed to the coarser choice. */
  tags: string[]
  /** How many notes below this one carry its tag — counted INSIDE its parent. */
  count: number
}

export interface ScopeLevel {
  type: string
  options: ScopeOption[]
}

function tagCounts(nodes: RealNode[]): Map<string, number> {
  const counts = new Map<string, number>()
  for (const node of nodes) {
    for (const tag of node.tags) counts.set(tag, (counts.get(tag) ?? 0) + 1)
  }
  return counts
}

/**
 * The tag that identifies this note among notes of its own type, or null when it has none.
 *
 * `siblingCounts` counts tags across the notes sharing this one's coarser choice,
 * `takenTags` holds the tags coarser levels already claimed, `finerCounts` counts tags
 * below. A tag shared with a sibling, or one that already names a coarser note, cannot
 * name this one; among the tags that remain, the one with the most descendants wins.
 */
export function scopeTagOf(
  node: RealNode,
  siblingCounts: Map<string, number>,
  takenTags: ReadonlySet<string>,
  finerCounts: Map<string, number>,
): string | null {
  let best: string | null = null
  let bestCount = -1
  for (const tag of node.tags) {
    if ((siblingCounts.get(tag) ?? 0) > 1) continue
    // Tag, którym nazwał się już poziom WYŻEJ, nazywa tamtą notatkę, nie tę: przedmiot
    // bez plików bywa jedynym w swoim semestrze i `sem4` wygląda przy nim na własny.
    if (takenTags.has(tag)) continue
    const count = finerCounts.get(tag) ?? 0
    if (count <= bestCount) continue
    best = tag
    bestCount = count
  }
  return best
}

/**
 * One level per node type except the finest one — there is nothing to drill into below it.
 * A vault without types (or with just one) gets no picker at all, which is correct: there
 * is no hierarchy to walk.
 */
export function scopeLevels(nodes: readonly RealNode[]): ScopeLevel[] {
  const types = presentNodeTypes(nodes.map((n) => n.type))
  if (types.length < 2) return []

  const byType = new Map<string, RealNode[]>()
  for (const node of nodes) {
    const type = node.type ?? ''
    if (!byType.has(type)) byType.set(type, [])
    byType.get(type)!.push(node)
  }

  const levels: ScopeLevel[] = []
  /** Tags already used as scope by coarser levels — they name someone else's note. */
  const takenTags = new Set<string>()

  for (let index = 0; index < types.length - 1; index++) {
    const peers = byType.get(types[index]) ?? []
    const finer = types.slice(index + 1).flatMap((t) => byType.get(t) ?? [])

    // Siblings are the peers sharing the same coarser choice. Without this grouping a
    // category called `kolokwia` looks like a hundred other `kolokwia` and gets no name
    // of its own, while inside one subject it is unmistakable.
    const siblingKey = (node: RealNode): string =>
      node.tags.filter((t) => takenTags.has(t)).sort().join('\u0000')
    const siblingCounts = new Map<string, Map<string, number>>()
    for (const node of peers) {
      const key = siblingKey(node)
      let group = siblingCounts.get(key)
      if (group === undefined) {
        group = new Map()
        siblingCounts.set(key, group)
      }
      for (const tag of node.tags) group.set(tag, (group.get(tag) ?? 0) + 1)
    }

    // Liczby przy opcjach też są liczone W OBRĘBIE RODZICA. Globalnie „Egzamin" przy
    // AKO pokazywał 303 — tyle egzaminów ma cała paczka — a po wybraniu zostawało 148.
    // Licznik, który nie zgadza się z tym, co widać po kliknięciu, jest gorszy niż brak.
    const counts = new Map<string, Map<string, number>>()
    for (const node of finer) {
      const key = siblingKey(node)
      let group = counts.get(key)
      if (group === undefined) {
        group = new Map()
        counts.set(key, group)
      }
      for (const tag of node.tags) group.set(tag, (group.get(tag) ?? 0) + 1)
    }

    const options: ScopeOption[] = []
    for (const node of peers) {
      const key = siblingKey(node)
      const below = counts.get(key) ?? new Map<string, number>()
      const tag = scopeTagOf(node, siblingCounts.get(key) ?? new Map(), takenTags, below)
      if (tag === null) continue
      options.push({
        id: node.id,
        label: node.title,
        tag,
        tags: node.tags,
        count: below.get(tag) ?? 0,
      })
    }
    options.sort((a, b) => a.label.localeCompare(b.label))
    if (options.length > 0) {
      levels.push({ type: types[index], options })
      for (const option of options) takenTags.add(option.tag)
    }
  }
  return levels
}
