import { describe, expect, it } from 'vitest'

import { narrowsAnything, sanitizeFilters, type FilterVocabulary } from './filterPersistence'

const SŁOWNIK: FilterVocabulary = {
  categories: new Set(['SEM3']),
  statuses: new Set(['completed']),
  levels: new Set<number | null>([1, 2]),
  tags: new Set(['sem3', 'ako']),
  nodeTypes: new Set(['semester', 'subject', 'file']),
  relationKinds: new Set(['belongs_to']),
}

describe('zapamiętane filtry', () => {
  it('wracają w całości, gdy wszystko nadal istnieje', () => {
    const zapisane = { tags: ['sem3', 'ako'], nodeTypes: ['file'], tagMode: 'all' }

    expect(sanitizeFilters(zapisane, SŁOWNIK)).toMatchObject({
      tags: ['sem3', 'ako'],
      nodeTypes: ['file'],
    })
  })

  it('gubią to, czego w tym grafie już nie ma', () => {
    // Graf bywa przebudowany: tag po przedmiocie, którego nie ma, wygasiłby widok
    // bez śladu, dlaczego.
    const zapisane = { tags: ['sem3', 'przedmiot-ktory-zniknal'], nodeTypes: ['plik-x'] }

    expect(sanitizeFilters(zapisane, SŁOWNIK)).toMatchObject({ tags: ['sem3'], nodeTypes: [] })
  })

  it('odrzucają śmieci zamiast się wywracać', () => {
    expect(sanitizeFilters('nie-obiekt', SŁOWNIK)).toBeNull()
    expect(sanitizeFilters(null, SŁOWNIK)).toBeNull()
    expect(sanitizeFilters({ tags: 'nie-lista' }, SŁOWNIK)).toMatchObject({ tags: [] })
  })

  it('pusty wybór nie jest wart przywracania', () => {
    const pusty = sanitizeFilters({}, SŁOWNIK)!

    expect(narrowsAnything(pusty)).toBe(false)
    expect(narrowsAnything({ ...pusty, tags: ['sem3'] })).toBe(true)
  })
})
