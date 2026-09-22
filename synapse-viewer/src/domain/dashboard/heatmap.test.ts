import { describe, it, expect } from 'vitest'
import { buildHeatmapCells } from './heatmap'

/**
 * We use a Saturday (2026-06-20) as the injected "today" for all tests.
 *
 * Why Saturday?  The grid start is aligned to the Sunday that precedes
 * (today − 181 days).  When today is a Saturday, (today − 181 days) is also
 * a Sunday, so no additional alignment step moves the start further back.
 * This means the last cell of the 26×7 grid lands exactly on today, which
 * makes it easy to assert that today is present in the output.
 *
 * If any other weekday were used the last visible cell would be up to 6 days
 * before today, and the "today is in the grid" assertion would fail.
 */
const TODAY = new Date('2026-06-20') // Saturday

describe('buildHeatmapCells', () => {
  it('today appears in the grid with count=1', () => {
    const cells = buildHeatmapCells(['2026-06-20'], TODAY)
    const cell = cells.find((c) => c.date === '2026-06-20')
    expect(cell).toBeDefined()
    expect(cell!.count).toBe(1)
    expect(cell!.level).toBeGreaterThan(0)
  })

  it('date before the 26-week window is excluded', () => {
    // 26*7 = 182 days.  Grid starts on Sunday ≥ (today − 182 days).
    // Something well outside, like 2025-01-01, should never appear.
    const cells = buildHeatmapCells(['2025-01-01'], TODAY)
    expect(cells.find((c) => c.date === '2025-01-01')).toBeUndefined()
  })

  it('future dates are excluded', () => {
    const cells = buildHeatmapCells(['2026-06-21'], TODAY)
    expect(cells.find((c) => c.date === '2026-06-21')).toBeUndefined()
  })

  it('col=0 row=0 maps to the correct Sunday start date', () => {
    const cells = buildHeatmapCells([], TODAY)
    // Implementation: start = today − 181 days, aligned to Sunday via UTC
    const expected = new Date(TODAY)
    expected.setUTCDate(expected.getUTCDate() - (26 * 7 - 1))
    expected.setUTCDate(expected.getUTCDate() - expected.getUTCDay())
    const expectedStr = expected.toISOString().slice(0, 10)

    const first = cells.find((c) => c.col === 0 && c.row === 0)
    expect(first).toBeDefined()
    expect(first!.date).toBe(expectedStr)
  })

  it('cell at col=w row=d is exactly w*7+d days from start', () => {
    const cells = buildHeatmapCells([], TODAY)
    const start = new Date(TODAY)
    start.setUTCDate(start.getUTCDate() - (26 * 7 - 1))
    start.setUTCDate(start.getUTCDate() - start.getUTCDay())

    // Spot-check the first 20 cells
    for (const { col: w, row: d, date } of cells.slice(0, 20)) {
      const expected = new Date(start)
      expected.setUTCDate(start.getUTCDate() + w * 7 + d)
      expect(date).toBe(expected.toISOString().slice(0, 10))
    }
  })

  it('level=0 for every cell when historyDates is empty', () => {
    const cells = buildHeatmapCells([], TODAY)
    expect(cells.length).toBeGreaterThan(0)
    cells.forEach((c) => {
      expect(c.level).toBe(0)
      expect(c.count).toBe(0)
    })
  })

  it('level is proportional to count / max', () => {
    // 2 hits on 2026-06-20 (today, the max), 1 hit on 2026-06-19 (yesterday)
    const cells = buildHeatmapCells(
      ['2026-06-20', '2026-06-20', '2026-06-19'],
      TODAY,
    )
    const todayCell = cells.find((c) => c.date === '2026-06-20')!
    const yestCell = cells.find((c) => c.date === '2026-06-19')!

    expect(todayCell).toBeDefined()
    expect(yestCell).toBeDefined()
    // max = 2 → today level = 1.0, yesterday level = 0.5
    expect(todayCell.level).toBeCloseTo(1.0)
    expect(yestCell.level).toBeCloseTo(0.5)
  })

  it('multiple identical dates accumulate count', () => {
    const cells = buildHeatmapCells(
      ['2026-06-20', '2026-06-20', '2026-06-20'],
      TODAY,
    )
    const cell = cells.find((c) => c.date === '2026-06-20')!
    expect(cell).toBeDefined()
    expect(cell.count).toBe(3)
  })

  it('total number of cells does not exceed weeks*7', () => {
    const cells = buildHeatmapCells([], TODAY)
    expect(cells.length).toBeLessThanOrEqual(26 * 7)
    // Because today is Saturday the full 182 cells should be present
    expect(cells.length).toBe(26 * 7)
  })
})
