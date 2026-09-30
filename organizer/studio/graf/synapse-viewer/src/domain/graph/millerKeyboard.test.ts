import { describe, expect, it } from 'vitest'

import { nextFocus, type FocusState } from './millerKeyboard'
import type { RealNode } from './GraphModel'

function node(id: string, type: string): RealNode {
  return {
    id, kind: 'real', title: id, path: `${id}.md`, category: 'x', level: null,
    status: null, tags: [], aliases: [], modified: '', excerpt: '', wordCount: 0, type,
  }
}

// Kolumny takie, jakie zwraca `columnsFor` dla ścieżki ['sem3'].
const COLUMNS: RealNode[][] = [
  [node('sem3', 'semester'), node('sem4', 'semester')],
  [node('ako', 'subject'), node('bd', 'subject'), node('so', 'subject')],
]

const OPENED = new Set(['ako'])
const at = (path: string[], cursor: number): FocusState => ({ path, cursor })

describe('poruszanie się po kolumnach', () => {
  it('w dół i w górę przesuwa kursor w ostatniej kolumnie', () => {
    expect(nextFocus(at(['sem3'], 0), 'ArrowDown', COLUMNS, OPENED)).toEqual(at(['sem3'], 1))
    expect(nextFocus(at(['sem3'], 1), 'ArrowUp', COLUMNS, OPENED)).toEqual(at(['sem3'], 0))
  })

  it('kursor zatrzymuje się na krańcach zamiast zawijać', () => {
    // Zawijanie w widoku z 2563 pozycjami znaczy „skok na drugi koniec listy" — po tym
    // nie wiadomo, gdzie się jest.
    expect(nextFocus(at(['sem3'], 0), 'ArrowUp', COLUMNS, OPENED)).toEqual(at(['sem3'], 0))
    expect(nextFocus(at(['sem3'], 2), 'ArrowDown', COLUMNS, OPENED)).toEqual(at(['sem3'], 2))
  })

  it('w prawo wchodzi w kontener i staje na jego pierwszym dziecku', () => {
    expect(nextFocus(at(['sem3'], 0), 'ArrowRight', COLUMNS, OPENED)).toEqual(at(['sem3', 'ako'], 0))
  })

  it('w prawo na pozycji bez dzieci nie robi nic', () => {
    // Plik otwiera panel szczegółów; przesunięcie kolumny byłoby ruchem donikąd.
    expect(nextFocus(at(['sem3'], 1), 'ArrowRight', COLUMNS, OPENED)).toEqual(at(['sem3'], 1))
  })

  it('Enter działa jak strzałka w prawo', () => {
    expect(nextFocus(at(['sem3'], 0), 'Enter', COLUMNS, OPENED)).toEqual(at(['sem3', 'ako'], 0))
  })

  it('w lewo wraca do kolumny wyżej i staje na tym, z czego się weszło', () => {
    const columns = [COLUMNS[0], COLUMNS[1], [node('plik', 'file')]]

    expect(nextFocus(at(['sem3', 'bd'], 0), 'ArrowLeft', columns, OPENED)).toEqual(at(['sem3'], 1))
  })

  it('w lewo na pierwszej kolumnie nic nie psuje', () => {
    expect(nextFocus(at([], 1), 'ArrowLeft', COLUMNS, OPENED)).toEqual(at([], 1))
  })

  it('Escape i Backspace cofają tak samo jak strzałka w lewo', () => {
    const columns = [COLUMNS[0], COLUMNS[1], [node('plik', 'file')]]

    for (const key of ['Escape', 'Backspace']) {
      expect(nextFocus(at(['sem3', 'bd'], 0), key, columns, OPENED)).toEqual(at(['sem3'], 1))
    }
  })

  it('klawisz spoza zestawu zostawia stan nietknięty', () => {
    const state = at(['sem3'], 1)

    expect(nextFocus(state, 'x', COLUMNS, OPENED)).toBe(state)
  })

  it('Home i End skaczą na krańce kolumny', () => {
    expect(nextFocus(at(['sem3'], 2), 'Home', COLUMNS, OPENED)).toEqual(at(['sem3'], 0))
    expect(nextFocus(at(['sem3'], 0), 'End', COLUMNS, OPENED)).toEqual(at(['sem3'], 2))
  })

  it('kursor poza zakresem wraca do zakresu, zamiast wskazywać w pustkę', () => {
    // Kolumna kurczy się przy zmianie filtra, a stan przeżywa tę zmianę. Kursor 99
    // w trzyelementowej kolumnie ma znaczyć „ostatnia pozycja", a nie ruch w pustkę.
    expect(nextFocus(at(['sem3'], 99), 'ArrowDown', COLUMNS, OPENED)).toEqual(at(['sem3'], 2))
    expect(nextFocus(at(['sem3'], 99), 'ArrowUp', COLUMNS, OPENED)).toEqual(at(['sem3'], 1))
  })

  it('pusta kolumna nie wywraca ruchu', () => {
    expect(nextFocus(at([], 0), 'ArrowDown', [[]], OPENED)).toEqual(at([], 0))
  })
})
