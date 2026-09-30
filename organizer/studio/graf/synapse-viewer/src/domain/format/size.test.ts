import { describe, expect, it } from 'vitest'

import { humanSize } from './size'

describe('rozmiar dla człowieka', () => {
  it('poniżej kilobajta podaje bajty', () => {
    // Zaokrąglanie do kilobajtów robiło z 761 notatek „0 kB" — zero ma znaczyć „nie wiem".
    expect(humanSize(166)).toBe('166 B')
    expect(humanSize(1)).toBe('1 B')
  })

  it('kilobajty i megabajty jak po stronie vaulta', () => {
    expect(humanSize(2048)).toBe('2 kB')
    expect(humanSize(172032)).toBe('168 kB')
    expect(humanSize(5 * 1024 * 1024)).toBe('5.0 MB')
  })

  it('brak danych to puste miejsce, nie zero', () => {
    expect(humanSize(0)).toBe('')
    expect(humanSize(undefined)).toBe('')
    expect(humanSize(null)).toBe('')
  })
})
