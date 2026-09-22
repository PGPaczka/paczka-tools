import type { PaletteAction } from './actionsRegistry'
import type { GraphNode } from '../graph/GraphModel'

export interface PaletteResult {
  type: 'action' | 'note' | 'content'
  label: string
  hint?: string
  run: () => void
  // for notes / content
  id?: string
  category?: string
  color?: string
  status?: string | null
}

/**
 * Search the command palette.
 *
 * - query="" → all actions first, then all notes
 * - query≠"" → substring filter (case-insensitive) on label/title
 * - actions always precede notes in the result
 */
export function searchPalette(
  query: string,
  actions: PaletteAction[],
  nodes: GraphNode[],
  catColor: (cat: string) => string,
  onSelectNote: (id: string) => void,
): PaletteResult[] {
  const q = query.trim().toLowerCase()

  const matchAction = (a: PaletteAction): boolean =>
    !q || a.label.toLowerCase().includes(q) || a.hint.toLowerCase().includes(q)

  const matchNode = (n: GraphNode): boolean => {
    if (!q) return true
    if (n.title.toLowerCase().includes(q)) return true
    if (n.kind === 'real') {
      if (n.category.toLowerCase().includes(q)) return true
      if (n.tags.some((t) => t.toLowerCase().includes(q))) return true
    }
    return false
  }

  const actionResults: PaletteResult[] = actions.filter(matchAction).map((a) => ({
    type: 'action',
    label: a.label,
    hint: a.hint,
    run: a.run,
  }))

  const noteResults: PaletteResult[] = nodes.filter(matchNode).map((n) => ({
    type: 'note',
    id: n.id,
    label: n.title,
    hint: n.kind === 'real' ? n.category : 'Ghost note',
    category: n.kind === 'real' ? n.category : undefined,
    color: n.kind === 'real' ? catColor(n.category) : '#7d8590',
    status: n.kind === 'real' ? n.status : null,
    run: () => onSelectNote(n.id),
  }))

  return [...actionResults, ...noteResults]
}
