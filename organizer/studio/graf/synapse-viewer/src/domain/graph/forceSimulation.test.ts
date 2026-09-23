import { describe, expect, it } from 'vitest'

import { alphaDecayFor, LARGE_LAYOUT_NODES } from './forceSimulation'

/** Liczba tyknięć do zatrzymania: alpha startuje z 1 i mnoży się przez (1 - decay). */
const ticksToSettle = (decay: number): number => Math.ceil(Math.log(0.004) / Math.log(1 - decay))

describe('chłodzenie układu sił', () => {
  it('mały vault stygnie jak w prototypie — układanie jest tam częścią obrazu', () => {
    expect(alphaDecayFor(120)).toBe(0.025)
    expect(ticksToSettle(alphaDecayFor(120))).toBeGreaterThan(200)
  })

  it('duży układ stygnie szybciej, bo każde tyknięcie liczy siły dla wszystkich', () => {
    // 2565 węzłów × 220 tyknięć to kilkadziesiąt sekund zajętego canvasu na tablecie —
    // przez ten czas przesuwanie grafu było jak brodzenie w kleju (zgłoszone 2026-09-23).
    expect(alphaDecayFor(2565)).toBe(0.08)
    expect(ticksToSettle(0.08)).toBeLessThan(ticksToSettle(0.025) / 3)
  })

  it('próg jest progiem, nie płynnym przejściem', () => {
    expect(alphaDecayFor(LARGE_LAYOUT_NODES)).toBe(0.025)
    expect(alphaDecayFor(LARGE_LAYOUT_NODES + 1)).toBe(0.08)
  })
})
