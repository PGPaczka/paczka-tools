import { describe, expect, it } from 'vitest'

import {
  adaptRenderScale,
  containerRadius,
  detailLevel,
  placeLabelsByLevel,
  discInBounds,
  maxEdgePx,
  renderScale,
  segmentOffscreen,
  shouldLabel,
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

describe('etykiety', () => {
  it('po przybliżeniu pliki dostają nazwy', () => {
    // Sedno zgłoszenia: przy 359 węzłach na ekranie i promieniu 9 px nazw nie było,
    // bo próg patrzył na 2565 węzłów przepuszczonych przez filtr, a nie na ekran.
    expect(shouldLabel(9, 359, false)).toBe(true)
  })

  it('przy tłoku zostają tylko duże węzły — inaczej robi się szary dywan', () => {
    expect(shouldLabel(9, 2565, false)).toBe(false)
    expect(shouldLabel(20, 2565, false)).toBe(true)
  })

  it('węzeł wskazany palcem ma nazwę zawsze', () => {
    expect(shouldLabel(1, 4000, true)).toBe(true)
  })

  it('kropka mniejsza od własnej etykiety jej nie dostaje', () => {
    expect(shouldLabel(3, 50, false)).toBe(false)
  })
})

describe('długie krawędzie', () => {
  it('przy oddaleniu rysują się wszystkie — to one pokazują kształt całości', () => {
    expect(maxEdgePx(false, 412, 915)).toBe(Number.POSITIVE_INFINITY)
  })

  it('po przybliżeniu odpada to, czego drugiego końca i tak nie widać', () => {
    const limit = maxEdgePx(true, 412, 915)
    const przekatna = Math.hypot(412, 915)

    expect(limit).toBeGreaterThan(przekatna)
    expect(limit).toBeLessThan(przekatna * 2)
  })

  it('bliska relacja między sąsiednimi plikami zostaje', () => {
    // 200 px przy ekranie telefonu to dwa węzły obok siebie — dokładnie to, po co
    // ktoś przybliża graf.
    expect(200).toBeLessThan(maxEdgePx(true, 412, 915))
  })
})

describe('etykiety kontenerów', () => {
  it('przedmiot i kategoria mają podpis nawet w największym tłoku', () => {
    // Jest ich garstka, a to po nich poznajesz, na co patrzysz.
    expect(shouldLabel(3, 4000, false, true)).toBe(true)
  })
})

describe('rozmiar kontenera', () => {
  it('przy oddaleniu kontener nie schodzi poniżej widoczności', () => {
    // Przy skali 0,05 przedmiot o promieniu 25 miałby 1,25 px i ginął wśród plików.
    expect(containerRadius(25, 0.05) * 0.05).toBeGreaterThanOrEqual(6)
  })

  it('przy przybliżeniu nic nie rozdmuchuje', () => {
    expect(containerRadius(25, 1)).toBe(25)
  })
})

describe('układanie podpisów poziomami', () => {
  const box = (x: number, y: number, priority: number, id: string) =>
    ({ x, y, w: 100, h: 16, priority, id })

  it('gdy poziom się mieści, wchodzi w całości', () => {
    const przedmioty = [box(0, 0, 1.7, 'a'), box(0, 200, 1.7, 'b')]

    expect(placeLabelsByLevel([przedmioty])).toHaveLength(2)
  })

  it('gdy choć jedna nazwa nie ma miejsca, milknie CAŁY poziom', () => {
    // Podpisanie części przedmiotów, a części nie, wygląda na usterkę i każe zgadywać,
    // czemu akurat te (zgłoszone z ręki 2026-09-23).
    const przedmioty = [box(0, 0, 1.7, 'a'), box(10, 0, 1.7, 'b'), box(0, 300, 1.7, 'c')]

    expect(placeLabelsByLevel([przedmioty])).toEqual([])
  })

  it('grubszy poziom wchodzi pierwszy i blokuje drobniejszy', () => {
    const semestry = [box(0, 0, 2.2, 'sem')]
    const kategorie = [box(10, 0, 1.3, 'kat')]

    expect(placeLabelsByLevel([kategorie, semestry]).map((i) => i.id)).toEqual(['sem'])
  })

  it('drobniejszy poziom wchodzi, gdy nie koliduje z grubszym', () => {
    const semestry = [box(0, 0, 2.2, 'sem')]
    const kategorie = [box(0, 300, 1.3, 'kat')]

    expect(placeLabelsByLevel([kategorie, semestry])).toHaveLength(2)
  })

  it('kolejność wejścia nie zmienia wyniku', () => {
    const a = [box(0, 0, 2.2, 'sem')]
    const b = [box(10, 0, 1.7, 'przedmiot')]

    expect(placeLabelsByLevel([a, b]).map((i) => i.id))
      .toEqual(placeLabelsByLevel([b, a]).map((i) => i.id))
  })
})
