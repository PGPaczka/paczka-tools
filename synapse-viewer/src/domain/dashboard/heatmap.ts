export interface HeatmapCell {
  date: string  // yyyy-mm-dd
  col: number   // 0..25 (week)
  row: number   // 0..6 (day of week, 0=Sun)
  count: number
  level: number // 0..1 float (0 = no activity)
}

/**
 * Build a 26×7 heatmap grid from history dates.
 *
 * - weeks = 26 (going back ~6 months)
 * - Grid starts on the Sunday that aligns to (today − 26*7 + 1 days)
 * - Cells where the computed date > today are omitted
 * - level = count / max  (0 when count = 0)
 */
export function buildHeatmapCells(
  historyDates: string[], // all dates from all real nodes' history arrays
  today: Date,            // injected for testability
): HeatmapCell[] {
  // Count occurrences per date
  const counts: Record<string, number> = {}
  for (const d of historyDates) {
    counts[d] = (counts[d] ?? 0) + 1
  }

  const weeks = 26

  // Use UTC date arithmetic throughout to avoid timezone shift issues.
  // today's UTC date string is used as the reference "today" key.
  const todayKey = today.toISOString().slice(0, 10)

  // Start = today − (weeks*7 − 1) days, then align back to the nearest Sunday.
  // All arithmetic via setUTCDate / getUTCDate so the date string never shifts.
  const start = new Date(today)
  start.setUTCDate(start.getUTCDate() - (weeks * 7 - 1))
  start.setUTCDate(start.getUTCDate() - start.getUTCDay()) // step back to Sunday

  // Max count (at least 1 to avoid division by zero)
  const countValues = Object.values(counts)
  const max = countValues.length > 0 ? Math.max(1, ...countValues) : 1

  const cells: HeatmapCell[] = []

  for (let w = 0; w < weeks; w++) {
    for (let d = 0; d < 7; d++) {
      const dt = new Date(start)
      dt.setUTCDate(start.getUTCDate() + w * 7 + d)

      const key = dt.toISOString().slice(0, 10)

      // Skip future cells (compare as ISO strings — lexicographic order is correct)
      if (key > todayKey) continue
      const count = counts[key] ?? 0
      const level = count === 0 ? 0 : count / max

      cells.push({ date: key, col: w, row: d, count, level })
    }
  }

  return cells
}
