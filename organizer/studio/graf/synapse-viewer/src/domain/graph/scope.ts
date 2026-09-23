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
 * The rule here is the one a vault can actually honour: a coarse note is identified by
 * the tag NO OTHER note of its own type carries — `sem3` for a semester, `ako` for a
 * subject — and among those, by the one most of its descendants carry. That tag selects
 * the note together with everything below it.
 *
 * Rarity alone is not enough, and pretending otherwise showed immediately: a subject
 * with no files yet shares no tag with any file, so "the rarest tag shared downwards"
 * handed it `sem7` — and picking that subject filtered the graph down to nothing.
 */
export interface ScopeOption {
  /** Node id of the coarse note (semester, subject, …). */
  id: string
  label: string
  /** The tag to put into the filters — it matches this note AND everything under it. */
  tag: string
  /** All tags of the note, so a finer level can be narrowed to the coarser choice. */
  tags: string[]
  /** How many notes of finer types carry this tag. */
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
 * `peerCounts` counts tags across the note's own level, `coarserTags` holds every tag
 * seen above it, `finerCounts` counts tags below it. A tag shared with a peer, or one
 * that already names a coarser note, cannot name this one; among the tags that remain,
 * the one with the most descendants is the one worth filtering by.
 */
export function scopeTagOf(
  node: RealNode,
  peerCounts: Map<string, number>,
  coarserTags: ReadonlySet<string>,
  finerCounts: Map<string, number>,
): string | null {
  let best: string | null = null
  let bestCount = -1
  for (const tag of node.tags) {
    if ((peerCounts.get(tag) ?? 0) > 1) continue
    // Tag noszony przez poziom WYŻEJ nazywa tamtą notatkę, nie tę: przedmiot bez
    // plików bywa jedynym w swoim semestrze i `sem4` wygląda przy nim na własny.
    if (coarserTags.has(tag)) continue
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
  for (let index = 0; index < types.length - 1; index++) {
    const peers = byType.get(types[index]) ?? []
    const finer = types.slice(index + 1).flatMap((t) => byType.get(t) ?? [])
    const coarserTags = new Set(
      types.slice(0, index).flatMap((t) => byType.get(t) ?? []).flatMap((n) => n.tags),
    )
    const peerCounts = tagCounts(peers)
    const counts = tagCounts(finer)
    const options: ScopeOption[] = []
    for (const node of peers) {
      const tag = scopeTagOf(node, peerCounts, coarserTags, counts)
      if (tag === null) continue
      options.push({
        id: node.id,
        label: node.title,
        tag,
        tags: node.tags,
        count: counts.get(tag) ?? 0,
      })
    }
    options.sort((a, b) => a.label.localeCompare(b.label))
    if (options.length > 0) levels.push({ type: types[index], options })
  }
  return levels
}
