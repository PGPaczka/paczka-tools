/**
 * A file size for a human, matching the vault's own rule (`orglib/synapse_vault.py`).
 *
 * Below a kilobyte the size is printed in bytes on purpose: rounding to kilobytes turned
 * every small file into "0 kB" — 761 notes in the real package looked empty while holding
 * a few hundred bytes each. Zero is reserved for "we do not know", which is why an absent
 * or non-positive size returns an empty string instead of a number.
 */
export function humanSize(bytes: number | undefined | null): string {
  if (bytes === undefined || bytes === null || bytes <= 0) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} kB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
