import { describe, expect, it } from 'vitest'

import {
  adaptRenderScale,
  detailLevel,
  discInBounds,
  renderScale,
  segmentOffscreen,
  visibleWorldBounds,
} from './lod'

describe('kadrowanie widoku', () => {
  const bounds = visibleWorldBounds(0, 0, 1, 800, 600, 0)

  it('okno świata odpowiada ekranowi przy skali 1 i zerowym przesunięciu', () => {
    expect(bounds).toEqual({ minX: 0, minY: 0, maxX: 800, maxY: 600 })
  })

  it('przy oddaleniu okno świata rośnie, bo mieści się go więcej', () => {
    const daleko = visibleWorldBounds(0, 0, 0.25, 800, 600, 0)

    expect(daleko.maxX).toBe(3200)
  })

  it('margines liczy się w pikselach ekranu, nie świata', () => {
    const z = visibleWorldBounds(0, 0, 0.5, 800, 600, 100)

    expect(z.minX).toBe(-200)
  })

  it('węzeł tuż za krawędzią zostaje, jeśli sięga jej promieniem', () => {
    expect(discInBounds(bounds, -5, 300, 10)).toBe(true)
    expect(discInBounds(bounds, -5, 300, 1)).toBe(false)
  })

  it('krawędź przecinająca ekran nie jest wycinana, choć oba końce są poza nim', () => {
    // Zachowawczo: zgubiona długa krawędź rozrywa obrazek, a oszczędność jest żadna.
    expect(segmentOffscreen(bounds, -100, 300, 900, 300)).toBe(false)
    expect(segmentOffscreen(bounds, -100, -50, -80, -20)).toBe(true)
  })
})

describe('poziom szczegółu', () => {
  it('przy otwarciu paczki nie rysuje grotów ani pierścieni', () => {
    // Skala 0,06 i promień 11 to węzeł szerokości ~1,3 px — grot byłby większy od węzła.
    expect(detailLevel(0.06, 11)).toEqual({ arrows: false, richNodes: false })
  })

  it('po przybliżeniu wraca pełny rysunek', () => {
    expect(detailLevel(1.5, 11)).toEqual({ arrows: true, richNodes: true })
  })

  it('groty wracają później niż pierścienie — są drobniejsze od węzła', () => {
    expect(detailLevel(0.5, 11)).toEqual({ arrows: false, richNodes: true })
  })
})

describe('gęstość rysowania', () => {
  it('laptop rysuje jak dotąd', () => {
    expect(renderScale(1)).toBe(1)
    expect(renderScale(2)).toBe(2)
  })

  it('telefon z dpr 3 nie maluje dziewięciu pikseli na jeden', () => {
    // 3 × 3 to dziewięciokrotność pracy na klatkę przy obrazie złożonym z kropek.
    expect(renderScale(3)).toBe(2)
    expect(renderScale(3.5)).toBe(2)
  })

  it('brak wartości to jeden, nie zero', () => {
    expect(renderScale(0)).toBe(1)
  })
})

describe('dostrajanie gęstości do urządzenia', () => {
  it('wolne klatki obniżają gęstość krok po kroku', () => {
    expect(adaptRenderScale(2, 90, 3, false)).toBe(1.5)
    expect(adaptRenderScale(1.5, 90, 3, false)).toBe(1)
  })

  it('nie schodzi poniżej jednego piksela na piksel CSS', () => {
    expect(adaptRenderScale(1, 250, 3, false)).toBe(1)
  })

  it('płynne klatki nie zmieniają niczego', () => {
    expect(adaptRenderScale(1.5, 16, 3, false)).toBe(1.5)
  })

  it('po uspokojeniu wraca pełna ostrość', () => {
    // Obniżona gęstość ma być ceną za ruch, nie trwałym pogorszeniem obrazu.
    expect(adaptRenderScale(1, 16, 3, true)).toBe(2)
    expect(adaptRenderScale(1, 16, 1, true)).toBe(1)
  })
})
