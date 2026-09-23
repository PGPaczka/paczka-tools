import { describe, expect, it } from 'vitest'

import { hierarchyAnchors, footprint, type AnchorNode } from './hierarchyAnchors'

const odleglosc = (a: { x: number; y: number }, b: { x: number; y: number }): number =>
  Math.hypot(a.x - b.x, a.y - b.y)

const DRZEWO: AnchorNode[] = [
  { id: 'sem3', parent: null, weight: 2600 },
  { id: 'sem7', parent: null, weight: 400 },
  { id: 'sem3-ako', parent: 'sem3', weight: 2570 },
  { id: 'sem3-bd', parent: 'sem3', weight: 30 },
  { id: 'sem3-ako-kat-laby', parent: 'sem3-ako', weight: 721 },
  { id: 'sem3-ako-kat-egzamin', parent: 'sem3-ako', weight: 147 },
  { id: 'sem7-abd', parent: 'sem7', weight: 400 },
]

describe('kotwice po hierarchii', () => {
  it('kategoria ląduje przy SWOIM przedmiocie, nie w losowym miejscu', () => {
    // Sedno zgłoszenia: skupiska były wystrzelone daleko od węzła, do którego należą.
    const pozycje = hierarchyAnchors(DRZEWO)
    const ako = pozycje.get('sem3-ako')!
    const laby = pozycje.get('sem3-ako-kat-laby')!
    const bd = pozycje.get('sem3-bd')!

    expect(odleglosc(ako, laby)).toBeLessThan(odleglosc(bd, laby))
  })

  it('rodzeństwo nie siada sobie na głowie', () => {
    const pozycje = hierarchyAnchors(DRZEWO)
    const laby = pozycje.get('sem3-ako-kat-laby')!
    const egzamin = pozycje.get('sem3-ako-kat-egzamin')!

    expect(odleglosc(laby, egzamin)).toBeGreaterThan(footprint(147))
  })

  it('większe skupisko dostaje więcej miejsca', () => {
    // Przedmiot z 2,5 tys. plików potrzebuje szerszego łuku niż ten z trzydziestoma.
    const pozycje = hierarchyAnchors(DRZEWO)
    const sem3 = { x: 0, y: 0 }
    const ako = pozycje.get('sem3-ako')!

    expect(odleglosc(sem3, ako)).toBeGreaterThan(0)
    expect(footprint(2570)).toBeGreaterThan(footprint(30) * 5)
  })

  it('jedyne dziecko siada na rodzicu, zamiast odlatywać', () => {
    const pozycje = hierarchyAnchors(DRZEWO)

    expect(pozycje.get('sem7-abd')).toEqual(pozycje.get('sem7'))
  })

  it('węzeł, którego rodzic wypadł z filtra, staje się korzeniem', () => {
    const sierota: AnchorNode[] = [{ id: 'kat', parent: 'nie-ma-go', weight: 5 }]

    expect(hierarchyAnchors(sierota).get('kat')).toEqual({ x: 0, y: 0 })
  })
})
