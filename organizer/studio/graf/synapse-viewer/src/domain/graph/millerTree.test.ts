import { describe, expect, it } from 'vitest'

import { autoPath, buildMillerTree, columnsFor, visiblePath } from './millerTree'
import type { GraphEdge, RealNode } from './GraphModel'

function node(id: string, type: string, title = id, extra: Partial<RealNode> = {}): RealNode {
  return {
    id, kind: 'real', title, path: `${id}.md`, category: 'x', level: null,
    status: null, tags: [], aliases: [], modified: '', excerpt: '', wordCount: 0, type,
    ...extra,
  }
}

/** `belongs_to` points from the CHILD to its parent — the vault declares it on the child. */
function belongsTo(child: string, parent: string): GraphEdge {
  return { source: child, target: parent, linkText: parent, kind: 'belongs_to' }
}

const NODES: RealNode[] = [
  node('sem3', 'semester', 'Semestr 3'),
  node('sem3-ako', 'subject', 'AKO'),
  node('sem3-bd', 'subject', 'BD'),
  node('ako-kat-kolokwia', 'category', 'Kolokwia'),
  node('ako-kat-laby', 'category', 'Laboratoria'),
  node('ako-grp-lab05', 'group', 'lab_05'),
  node('ako-kol-1', 'file', 'kolokwium.pdf'),
  node('ako-lab-1', 'file', 'zadanie1.c'),
  node('ako-lab-2', 'file', 'zadanie2.c'),
  node('bd-kat-egzamin', 'category', 'Egzamin'),
  node('bd-1', 'file', 'egzamin.pdf'),
]

const EDGES: GraphEdge[] = [
  belongsTo('sem3-ako', 'sem3'),
  belongsTo('sem3-bd', 'sem3'),
  belongsTo('ako-kat-kolokwia', 'sem3-ako'),
  belongsTo('ako-kat-laby', 'sem3-ako'),
  belongsTo('ako-grp-lab05', 'ako-kat-laby'),
  belongsTo('ako-kol-1', 'ako-kat-kolokwia'),
  belongsTo('ako-lab-1', 'ako-grp-lab05'),
  belongsTo('ako-lab-2', 'ako-grp-lab05'),
  belongsTo('bd-kat-egzamin', 'sem3-bd'),
  belongsTo('bd-1', 'bd-kat-egzamin'),
]

describe('drzewo zawierania', () => {
  it('bierze korzenie z węzłów, które nikogo nie wskazują', () => {
    const tree = buildMillerTree(NODES, EDGES)

    expect(tree.roots.map((n) => n.id)).toEqual(['sem3'])
  })

  it('czyta kierunek krawędzi od dziecka do rodzica', () => {
    const tree = buildMillerTree(NODES, EDGES)

    expect(tree.childrenOf('sem3').map((n) => n.id)).toEqual(['sem3-ako', 'sem3-bd'])
    expect(tree.parentOf('ako-lab-1')).toBe('ako-grp-lab05')
  })

  it('liczy WSZYSTKICH potomków, nie tylko dzieci', () => {
    // Przedmiot pokazuje, ile pod nim leży materiału — inaczej licznik przy AKO mówiłby
    // „2", bo tyle ma kategorii, a pod nimi siedzi kilka tysięcy plików.
    const tree = buildMillerTree(NODES, EDGES)

    expect(tree.descendantCount('sem3-ako')).toBe(6)
    expect(tree.descendantCount('ako-grp-lab05')).toBe(2)
    expect(tree.descendantCount('ako-kol-1')).toBe(0)
  })

  it('kolumny idą po ścieżce, a ostatnia pokazuje dzieci ostatniego wyboru', () => {
    const tree = buildMillerTree(NODES, EDGES)

    const columns = columnsFor(tree, ['sem3', 'sem3-ako'])

    expect(columns).toHaveLength(3)
    expect(columns[0].map((n) => n.id)).toEqual(['sem3'])
    expect(columns[1].map((n) => n.id)).toEqual(['sem3-ako', 'sem3-bd'])
    expect(columns[2].map((n) => n.id)).toEqual(['ako-kat-kolokwia', 'ako-kat-laby'])
  })

  it('ucina ścieżkę na pozycji, której już nie ma', () => {
    // Ścieżka przeżywa zmianę filtrów i przeładowanie grafu; wskazanie na nieistniejący
    // węzeł ma zwinąć widok do tego, co istnieje, a nie pokazać pustą kolumnę.
    const tree = buildMillerTree(NODES, EDGES)

    const columns = columnsFor(tree, ['sem3', 'nie-ma-takiego', 'sem3-ako'])

    expect(columns).toHaveLength(2)
    expect(columns[1].map((n) => n.id)).toEqual(['sem3-ako', 'sem3-bd'])
  })

  it('nie dokłada kolumny za liściem', () => {
    const tree = buildMillerTree(NODES, EDGES)

    expect(columnsFor(tree, ['sem3', 'sem3-bd', 'bd-kat-egzamin', 'bd-1'])).toHaveLength(4)
  })

  it('sortuje rodzeństwo kontenerami przed plikami, potem po nazwie', () => {
    const tree = buildMillerTree(
      [node('s', 'semester'), node('z-plik', 'file', 'z.pdf'), node('a-kat', 'category', 'A')],
      [belongsTo('z-plik', 's'), belongsTo('a-kat', 's')],
    )

    expect(tree.childrenOf('s').map((n) => n.id)).toEqual(['a-kat', 'z-plik'])
  })

  it('polskie znaki nie lądują na końcu alfabetu', () => {
    const tree = buildMillerTree(
      [node('s', 'semester'), node('c', 'file', 'Ćwiczenia'), node('d', 'file', 'Dane')],
      [belongsTo('c', 's'), belongsTo('d', 's')],
    )

    expect(tree.childrenOf('s').map((n) => n.title)).toEqual(['Ćwiczenia', 'Dane'])
  })
})

describe('zawężanie widoku', () => {
  it('zachowuje kontener, który prowadzi do pasującego pliku', () => {
    // Filtr „kategoria: kolokwia" odsiewa semestr i przedmiot, bo ICH kategoria to `SEM3`.
    // Bez tej reguły zawężenie zostawiłoby płaską listę plików bez drogi do nich.
    const tree = buildMillerTree(NODES, EDGES, (n) => n.id === 'ako-kol-1')

    expect(tree.roots.map((n) => n.id)).toEqual(['sem3'])
    expect(tree.childrenOf('sem3').map((n) => n.id)).toEqual(['sem3-ako'])
    expect(tree.childrenOf('sem3-ako').map((n) => n.id)).toEqual(['ako-kat-kolokwia'])
    expect(tree.descendantCount('sem3')).toBe(3)
  })

  it('pusty wynik zawężenia to puste drzewo, nie całe', () => {
    const tree = buildMillerTree(NODES, EDGES, () => false)

    expect(tree.roots).toHaveLength(0)
  })
})

describe('odporność na kształty, których nie powinno być', () => {
  it('sierota jest własnym korzeniem, nie znika', () => {
    const tree = buildMillerTree([node('sam', 'file', 'sam.pdf')], [])

    expect(tree.roots.map((n) => n.id)).toEqual(['sam'])
  })

  it('krawędź do nieistniejącego rodzica nie gubi węzła', () => {
    // Ghosty nie są węzłami tego drzewa, a plik potrafi wskazywać ghosta.
    const tree = buildMillerTree([node('plik', 'file')], [belongsTo('plik', 'ghost-1')])

    expect(tree.roots.map((n) => n.id)).toEqual(['plik'])
  })

  it('cykl nie zapętla liczenia potomków', () => {
    const tree = buildMillerTree(
      [node('a', 'category'), node('b', 'category')],
      [belongsTo('a', 'b'), belongsTo('b', 'a')],
    )

    expect(tree.descendantCount('a')).toBeLessThanOrEqual(2)
  })
})

describe('ścieżka, która przestała istnieć', () => {
  it('kończy się tam, gdzie kończą się kolumny', () => {
    // Powstał po cyklu reaktywnym w widoku: przycinanie ścieżki było ZAPISEM do stanu,
    // od którego liczyły się kolumny, więc `columns → state → columns`. Build to złapał,
    // svelte-check nie. Przycięcie musi być czystą funkcją, tak jak samo liczenie kolumn.
    const tree = buildMillerTree(NODES, EDGES)

    expect(visiblePath(tree, ['sem3', 'nie-ma', 'sem3-ako'])).toEqual(['sem3'])
  })

  it('nie wchodzi za liścia', () => {
    const tree = buildMillerTree(NODES, EDGES)

    expect(visiblePath(tree, ['sem3', 'sem3-bd', 'bd-kat-egzamin', 'bd-1'])).toEqual(
      ['sem3', 'sem3-bd', 'bd-kat-egzamin'],
    )
  })

  it('zgadza się z liczbą kolumn', () => {
    const tree = buildMillerTree(NODES, EDGES)
    const path = ['sem3', 'sem3-ako', 'ako-kat-laby']

    expect(visiblePath(tree, path).length).toBe(columnsFor(tree, path).length - 1)
  })
})

describe('rozwijanie jednoznacznego łańcucha', () => {
  it('po zawężeniu do jednego przedmiotu otwiera się aż do plików', () => {
    // Powstał po wpadce w widoku: klik w komórkę macierzy zawężał filtry poprawnie,
    // ale lądowało się na jednym wierszu „Kolokwia · AKO" i trzeba było klikać dalej,
    // żeby zobaczyć to, o co się właśnie poprosiło.
    const tree = buildMillerTree(NODES, EDGES, (n) => n.id === 'ako-kol-1')

    expect(autoPath(tree)).toEqual(['sem3', 'sem3-ako', 'ako-kat-kolokwia'])
  })

  it('zatrzymuje się tam, gdzie jest wybór', () => {
    // Dwa przedmioty pod semestrem to pytanie do człowieka, nie do widoku: łańcuch
    // otwiera sam semestr (jedyny korzeń) i staje.
    const tree = buildMillerTree(NODES, EDGES)

    expect(autoPath(tree)).toEqual(['sem3'])
  })

  it('nie otwiera niczego, gdy sam wybór korzenia jest pytaniem', () => {
    // Tak wygląda wejście bez filtra na prawdziwych danych: siedem semestrów.
    const tree = buildMillerTree(
      [...NODES, node('sem4', 'semester', 'Semestr 4')],
      EDGES,
    )

    expect(autoPath(tree)).toEqual([])
  })

  it('nie wchodzi w liścia', () => {
    const tree = buildMillerTree(NODES, EDGES, (n) => n.id === 'bd-1')

    expect(autoPath(tree)).toEqual(['sem3', 'sem3-bd', 'bd-kat-egzamin'])
  })

  it('puste drzewo nie ma czego otwierać', () => {
    expect(autoPath(buildMillerTree(NODES, EDGES, () => false))).toEqual([])
  })
})
