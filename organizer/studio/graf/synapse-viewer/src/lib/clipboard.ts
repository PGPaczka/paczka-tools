/**
 * Copying to the clipboard, with the confirmation the caller has to show.
 *
 * Kept in one place because the detail panel now offers several things worth copying —
 * a target path, a hash, every source path in the provenance tree — and four hand-rolled
 * copies of the same timeout dance is how they drift apart.
 */
export const COPIED_FOR_MS = 1500

export interface CopyState {
  /** True right after a successful copy; the caller turns it into a tick. */
  done: boolean
}

/**
 * Writes `text` and calls `onChange(true)`, then `onChange(false)` after a moment.
 * Returns a cancel function, so a component unmounting mid-confirmation leaves nothing
 * behind. A refused or missing clipboard reports `false` rather than throwing: this is
 * a convenience, never the only way to get at a value.
 */
export function copyText(
  text: string,
  onChange: (done: boolean) => void,
): () => void {
  let timer: ReturnType<typeof setTimeout> | undefined

  const cancel = () => {
    if (timer !== undefined) clearTimeout(timer)
    timer = undefined
  }

  const write = navigator?.clipboard?.writeText?.(text)
  Promise.resolve(write)
    .then(() => {
      if (write === undefined) return
      onChange(true)
      cancel()
      timer = setTimeout(() => onChange(false), COPIED_FOR_MS)
    })
    .catch(() => onChange(false))

  return cancel
}
