import { describe, expect, it } from 'vitest'

import {
  adaptRenderScale,
  containerRadius,
  detailLevel,
  keepTopContainers,
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

describe('podpisy kontenerów', () => {
  const przedmiot = { priority: 1.7, radiusPx: 1.1, id: 'AKO' }
  const kategorie = [1, 2, 3].map((n) => ({ priority: 1.3, radiusPx: 0.7, id: `kat${n}` }))

  it('przy wybranym JEDNYM przedmiocie kategorie mają nazwy przy każdym oddaleniu', () => {
    // Osiem kontenerów na ekranie — przedmiot i jego kategorie. Ich nazwy są całą
    // treścią tego widoku, więc nie ma czego oszczędzać (zgłoszone z ręki).
    const widoczne = keepTopContainers([przedmiot, ...kategorie])

    expect(widoczne).toHaveLength(4)
  })

  it('w tłumie kontenerów drobniejsze poziomy milkną przy oddaleniu', () => {
    // Widok całej paczki: 232 nazwy naraz to ściana, z której nie da się nic odczytać.
    const tlum = Array.from({ length: 40 }, (_, n) => ({
      priority: n < 8 ? 1.7 : 1.3, radiusPx: 1, id: `k${n}`,
    }))

    expect(keepTopContainers(tlum).every((i) => i.priority === 1.7)).toBe(true)
  })

  it('po przybliżeniu kategorie wracają także w tłumie', () => {
    const tlum = Array.from({ length: 40 }, (_, n) => ({
      priority: n < 8 ? 1.7 : 1.3, radiusPx: n < 8 ? 6 : 4.5, id: `k${n}`,
    }))

    expect(keepTopContainers(tlum)).toHaveLength(40)
  })

  it('gdy nawet po odsianiu jest ich za dużo, wygrywają najgrubsze poziomy', () => {
    // Semestr (2,2) przed przedmiotem (1,7) przed kategorią (1,3). Wszystkie na tyle
    // duże, że przechodzą próg rozmiaru — o kolejności decyduje sam budżet.
    const items = [
      ...Array.from({ length: 30 }, (_, n) => ({ priority: 1.3, radiusPx: 9, id: `kat${n}` })),
      { priority: 2.2, radiusPx: 9, id: 'semestr' },
      { priority: 1.7, radiusPx: 9, id: 'przedmiot' },
    ]

    expect(keepTopContainers(items, 2).map((i) => i.id)).toEqual(['semestr', 'przedmiot'])
  })

  it('pusty wybór nie wywraca reguły', () => {
    expect(keepTopContainers([])).toEqual([])
  })
})
