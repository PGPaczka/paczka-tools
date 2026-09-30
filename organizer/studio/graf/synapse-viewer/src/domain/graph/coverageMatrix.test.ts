import { describe, expect, it } from 'vitest'

import { buildCoverageMatrix, cellOf } from './coverageMatrix'
import type { GraphEdge, RealNode } from './GraphModel'

function node(
  id: string, type: string, title = id, extra: Partial<RealNode> = {},
): RealNode {
  return {
    id, kind: 'real', title, path: `${id}.md`, category: 'x', level: null,
    status: null, tags: [], aliases: [], modified: '', excerpt: '', wordCount: 0, type,
    ...extra,
  }
}

function file(id: string, category: string, level: number): RealNode {
  return node(id, 'file', id, { category, level })
}

function belongsTo(child: string, parent: string): GraphEdge {
  return { source: child, target: parent, linkText: parent, kind: 'belongs_to' }
}

const NODES: RealNode[] = [
  node('sem3', 'semester', 'Semestr 3'),
  node('sem2', 'semester', 'Semestr 2'),
  node('sem3-ako', 'subject', 'AKO'),
  node('sem3-bd', 'subject', 'BD'),
  node('sem2-so', 'subject', 'SO'),
  node('ako-kat-kolokwia', 'category', 'Kolokwia', { category: 'kolokwia' }),
  node('ako-kat-laby', 'category', 'Laboratoria', { category: 'laboratoria' }),
  node('ako-grp-lab05', 'group', 'lab_05', { category: 'laboratoria' }),
  file('ako-kol-1', 'kolokwia', 1),
  file('ako-kol-2', 'kolokwia', 3),
  file('ako-lab-1', 'laboratoria', 2),
  node('bd-kat-egzamin', 'category', 'Egzamin', { category: 'egzamin' }),
  file('bd-1', 'egzamin', 1),
  node('so-kat-kolokwia', 'category', 'Kolokwia', { category: 'kolokwia' }),
  file('so-1', 'kolokwia', 2),
]

const EDGES: GraphEdge[] = [
  belongsTo('sem3-ako', 'sem3'),
  belongsTo('sem3-bd', 'sem3'),
  belongsTo('sem2-so', 'sem2'),
  belongsTo('ako-kat-kolokwia', 'sem3-ako'),
  belongsTo('ako-kat-laby', 'sem3-ako'),
  belongsTo('ako-grp-lab05', 'ako-kat-laby'),
  belongsTo('ako-kol-1', 'ako-kat-kolokwia'),
  belongsTo('ako-kol-2', 'ako-kat-kolokwia'),
  belongsTo('ako-lab-1', 'ako-grp-lab05'),
  belongsTo('bd-kat-egzamin', 'sem3-bd'),
  belongsTo('bd-1', 'bd-kat-egzamin'),
  belongsTo('so-kat-kolokwia', 'sem2-so'),
  belongsTo('so-1', 'so-kat-kolokwia'),
]

describe('macierz pokrycia', () => {
  it('liczy pliki przedmiotu, choć wiszą pod kategorią albo katalogiem', () => {
    // `ako-lab-1` leży dwa poziomy niżej (kategoria → katalog), a i tak jest plikiem AKO.
    const matrix = buildCoverageMatrix(NODES, EDGES)
    const ako = matrix.rows.find((r) => r.subject.id === 'sem3-ako')!

    expect(cellOf(ako, 'kolokwia').count).toBe(2)
    expect(cellOf(ako, 'laboratoria').count).toBe(1)
    expect(ako.total).toBe(3)
  })

  it('komórka niesie rozkład stanu, nie jedną dominantę', () => {
    // „Część w paczce, część do przeglądu" to typowy stan przedmiotu w trakcie pracy;
    // dominanta zjadałaby dokładnie tę informację, po którą się tu przychodzi.
    const matrix = buildCoverageMatrix(NODES, EDGES)
    const ako = matrix.rows.find((r) => r.subject.id === 'sem3-ako')!

    expect(cellOf(ako, 'kolokwia')).toMatchObject({ inPackage: 1, planned: 0, needsHuman: 1 })
    expect(cellOf(ako, 'laboratoria')).toMatchObject({ inPackage: 0, planned: 1, needsHuman: 0 })
  })

  it('pusta komórka istnieje i ma zero, bo luka jest treścią tego widoku', () => {
    const matrix = buildCoverageMatrix(NODES, EDGES)
    const bd = matrix.rows.find((r) => r.subject.id === 'sem3-bd')!

    expect(cellOf(bd, 'kolokwia')).toEqual({ count: 0, inPackage: 0, planned: 0, needsHuman: 0 })
  })

  it('kolumny są kategoriami PLIKÓW, nie kategoriami węzłów zbiorczych', () => {
    // Semestr ma `category: "semestr"`, przedmiot — `SEM3`. Gdyby weszły do kolumn,
    // macierz opisywałaby własne rusztowanie zamiast materiału.
    const matrix = buildCoverageMatrix(NODES, EDGES)

    expect(matrix.categories).toEqual(['kolokwia', 'egzamin', 'laboratoria'])
  })

  it('NIE scala rozjechanego słownika kategorii', () => {
    // `wykład` i `wyklad` to znany problem danych (docs/SYNAPSE.md). Ten widok ma go
    // pokazać dwiema kolumnami, a nie zamaskować — inaczej nikt się o nim nie dowie.
    const nodes = [...NODES, file('ako-w-1', 'wykład', 1), file('ako-w-2', 'wyklad', 1)]
    const edges = [
      ...EDGES,
      belongsTo('ako-w-1', 'ako-kat-kolokwia'),
      belongsTo('ako-w-2', 'ako-kat-kolokwia'),
    ]

    const matrix = buildCoverageMatrix(nodes, edges)

    expect(matrix.categories).toContain('wykład')
    expect(matrix.categories).toContain('wyklad')
  })

  it('wiersze idą semestrami, a w semestrze po nazwie przedmiotu', () => {
    const matrix = buildCoverageMatrix(NODES, EDGES)

    expect(matrix.rows.map((r) => r.subject.title)).toEqual(['SO', 'AKO', 'BD'])
    expect(matrix.rows[0].semester?.title).toBe('Semestr 2')
  })

  it('przedmiot bez plików zostaje w macierzy jako pusty wiersz', () => {
    const nodes = [...NODES, node('sem3-gk', 'subject', 'GK')]
    const matrix = buildCoverageMatrix(nodes, [...EDGES, belongsTo('sem3-gk', 'sem3')])
    const gk = matrix.rows.find((r) => r.subject.id === 'sem3-gk')!

    expect(gk.total).toBe(0)
    expect(matrix.emptyRowCount).toBe(1)
  })

  it('kolumny ustawia liczba plików, a przy remisie nazwa', () => {
    const matrix = buildCoverageMatrix(NODES, EDGES)

    expect(matrix.categories[0]).toBe('kolokwia')
    expect(matrix.categoryTotals.get('kolokwia')).toBe(3)
  })

  it('plik bez przedmiotu nie wywraca macierzy', () => {
    const matrix = buildCoverageMatrix([...NODES, file('sierota', 'inne', 2)], EDGES)

    expect(matrix.rows.every((r) => r.subject.type === 'subject')).toBe(true)
    expect(matrix.categories).not.toContain('inne')
  })

  it('poziom spoza trójki liczy się do sumy, ale nie do żadnego paska', () => {
    // `level` bierze się z front mattera i bywa pusty; pozycja ma być policzona, bo
    // istnieje, ale nie wolno jej dopisać do stanu, którego nie deklaruje.
    const nodes = [...NODES, node('ako-x', 'file', 'x', { category: 'kolokwia', level: null })]
    const matrix = buildCoverageMatrix(nodes, [...EDGES, belongsTo('ako-x', 'ako-kat-kolokwia')])
    const ako = matrix.rows.find((r) => r.subject.id === 'sem3-ako')!

    const cell = cellOf(ako, 'kolokwia')
    expect(cell.count).toBe(3)
    expect(cell.inPackage + cell.planned + cell.needsHuman).toBe(2)
  })
})
