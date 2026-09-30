import type { RealNode } from './GraphModel'

/**
 * Where the keyboard is in a column browser.
 *
 * `path` holds the containers opened so far, so the columns on screen are the roots
 * followed by the children of each entry. `cursor` is the highlighted row in the LAST
 * column — the only one a key can move within. Everything else on screen is history.
 */
export interface FocusState {
  path: string[]
  cursor: number
}

const BACK_KEYS = new Set(['ArrowLeft', 'Escape', 'Backspace'])
const ENTER_KEYS = new Set(['ArrowRight', 'Enter'])

/**
 * The next focus after a key, given the columns currently drawn.
 *
 * Pure on purpose: this is the part that is easy to get wrong and impossible to check by
 * looking at the screen. `openable` says which ids have children — the caller knows it
 * from the tree, and passing it keeps this function free of the tree.
 *
 * Returns the same object when nothing moves, so a caller can skip a redraw.
 */
export function nextFocus(
  state: FocusState,
  key: string,
  columns: readonly RealNode[][],
  openable: ReadonlySet<string>,
): FocusState {
  const active = columns[columns.length - 1] ?? []
  // A column shrinks when filters change while the state survives it; clamping here means
  // the first key press after such a change lands somewhere real instead of nowhere.
  const cursor = Math.min(state.cursor, Math.max(active.length - 1, 0))

  if (key === 'ArrowDown') return move(state, cursor, Math.min(cursor + 1, active.length - 1))
  if (key === 'ArrowUp') return move(state, cursor, Math.max(cursor - 1, 0))
  if (key === 'Home') return move(state, cursor, 0)
  if (key === 'End') return move(state, cursor, Math.max(active.length - 1, 0))

  if (ENTER_KEYS.has(key)) {
    const focused = active[cursor]
    if (!focused || !openable.has(focused.id)) return same(state, cursor)
    return { path: [...state.path, focused.id], cursor: 0 }
  }

  if (BACK_KEYS.has(key)) {
    if (state.path.length === 0) return same(state, cursor)
    const closing = state.path[state.path.length - 1]
    const path = state.path.slice(0, -1)
    // Land back ON the container just closed: coming out of a folder and finding the
    // cursor at the top of the list loses the place you were working in.
    const parentColumn = columns[columns.length - 2] ?? []
    const index = parentColumn.findIndex((n) => n.id === closing)
    return { path, cursor: index >= 0 ? index : 0 }
  }

  return state
}

function move(state: FocusState, cursor: number, next: number): FocusState {
  if (next < 0 || next === state.cursor) return same(state, cursor)
  return { path: state.path, cursor: next }
}

/** Keeps object identity when the cursor did not really change. */
function same(state: FocusState, cursor: number): FocusState {
  return cursor === state.cursor ? state : { path: state.path, cursor }
}

/** The node the cursor points at, or null when the column is empty. */
export function focusedNode(
  state: FocusState,
  columns: readonly RealNode[][],
): RealNode | null {
  const active = columns[columns.length - 1] ?? []
  return active[Math.min(state.cursor, active.length - 1)] ?? null
}
