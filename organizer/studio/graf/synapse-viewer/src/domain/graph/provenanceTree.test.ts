import { describe, expect, it } from 'vitest'

import { buildProvenanceTree } from './provenanceTree'
import type { ProvenanceCopy } from './GraphModel'

function copy(pkg: string, path: string): ProvenanceCopy {
  return { package: pkg, path }
}

/** Pięć kopii z prawdziwego indeksu (sha 8ccda043) — trzy paczki, jedna rozgałęziona. */
const PIEC: ProvenanceCopy[] = [
  copy('Paczki INFA', 'Paczka 3 sem. 23_24/(AKO) Architektura/stara_paka/Ćwiczenia/2017/plik.pdf'),
  copy('Paczki Infa', '3 SEM/(AKO) Architektura/Stara paczka/Ćwiczenia/2017/plik.pdf'),
  copy('Paczki Infa', '3 SEM/Stare Paczki/Paczka III sem. 21_22/Ćwiczenia/2017/plik.pdf'),
  copy('Paczki Infa', '3 SEM/Stare Paczki/Semestr 3 paczka/Ćwiczenia/2017/plik.pdf'),
  copy('Semestr 3 paczka', 'Architektura/Ćwiczenia/2017/plik.pdf'),
]

describe('drzewo prowenancji', () => {
  it('korzeniem jest paczka źródłowa', () => {
    const tree = buildProvenanceTree(PIEC, PIEC.length)

    expect(tree.roots.map((r) => r.label)).toEqual(
      ['Paczki Infa', 'Paczki INFA', 'Semestr 3 paczka'],
    )
  })

  it('paczki różniące się WIELKOŚCIĄ LITER to osobne korzenie', () => {
    // W indeksie „Paczki INFA" i „Paczki Infa" to dwa różne wiersze `source_packages`.
    // Scalenie ich byłoby zmyśleniem faktu o pochodzeniu materiału.
    const tree = buildProvenanceTree(PIEC, PIEC.length)

    expect(tree.roots).toHaveLength(3)
  })

  it('rozgałęzienie jest jedyną rzeczą, która zajmuje pion', () => {
    // O to prosił użytkownik: widać, że z jednej paczki wychodzą trzy źródła, i widać,
    // GDZIE się rozchodzą. Łańcuch bez wyboru zwija się w jeden wiersz.
    const tree = buildProvenanceTree(PIEC, PIEC.length)
    const infa = tree.roots.find((r) => r.label === 'Paczki Infa')!

    // Katalog NIE zlewa się z nazwą paczki, nawet gdy jest jej jedynym dzieckiem:
    // „z której paczki" i „z którego katalogu" to dwa różne pytania.
    expect(infa.children.map((c) => c.label)).toEqual(['3 SEM'])
    expect(infa.children[0].children.map((c) => c.label)).toEqual([
      'Stare Paczki',
      '(AKO) Architektura/Stara paczka/Ćwiczenia/2017',
    ])
    const stare = infa.children[0].children[0]
    expect(stare.children.map((c) => c.label)).toEqual([
      'Paczka III sem. 21_22/Ćwiczenia/2017',
      'Semestr 3 paczka/Ćwiczenia/2017',
    ])
  })

  it('jedna kopia w paczce to jeden wiersz, bez zagnieżdżania', () => {
    const tree = buildProvenanceTree(PIEC, PIEC.length)
    const jedna = tree.roots.find((r) => r.label === 'Semestr 3 paczka')!

    expect(jedna.children.map((c) => c.label)).toEqual(['Architektura/Ćwiczenia/2017'])
    expect(jedna.children[0].children).toHaveLength(0)
  })

  it('wspólna nazwa pliku pokazuje się RAZ, nie przy każdej kopii', () => {
    // 92% treści ma tę samą nazwę we wszystkich kopiach — powtórzona pięć razy jest
    // najdłuższym i najmniej informacyjnym elementem każdego wiersza.
    const tree = buildProvenanceTree(PIEC, PIEC.length)

    expect(tree.commonName).toBe('plik.pdf')
    // Nazwa znika z ETYKIET; w `fullPath` zostaje, bo to ona idzie do schowka.
    const etykiety: string[] = []
    const zbierz = (n: { label: string; children: unknown[] }) => {
      etykiety.push(n.label)
      for (const c of n.children) zbierz(c as { label: string; children: unknown[] })
    }
    tree.roots.forEach(zbierz)
    expect(etykiety.some((l) => l.includes('plik.pdf'))).toBe(false)
  })

  it('nazwa odbiegająca od wspólnej zostaje przy swoim liściu', () => {
    const tree = buildProvenanceTree(
      [copy('P', 'a/plik.pdf'), copy('P', 'b/inna-nazwa.pdf')],
      2,
    )

    expect(tree.commonName).toBeNull()
    expect(tree.roots[0].children.map((c) => c.label)).toEqual(['a/plik.pdf', 'b/inna-nazwa.pdf'])
  })

  it('każdy liść niesie pełną ścieżkę do skopiowania', () => {
    const tree = buildProvenanceTree([copy('P', 'a/b/plik.pdf')], 1)

    expect(tree.roots[0].children[0].fullPath).toBe('P/a/b/plik.pdf')
  })

  it('kopia leżąca wprost w korzeniu paczki nie gubi się', () => {
    const tree = buildProvenanceTree([copy('P', 'plik.pdf')], 1)

    expect(tree.roots[0].label).toBe('P')
    expect(tree.roots[0].fullPath).toBe('P/plik.pdf')
    expect(tree.roots[0].children).toHaveLength(0)
  })

  it('paczki idą od najliczniejszej, przy remisie po nazwie', () => {
    const tree = buildProvenanceTree(
      [copy('Z', 'a/p.pdf'), copy('A', 'a/p.pdf'), copy('M', 'a/p.pdf'), copy('M', 'b/p.pdf')],
      4,
    )

    expect(tree.roots.map((r) => r.label)).toEqual(['M', 'A', 'Z'])
  })

  it('obcięta lista mówi, ilu kopii nie widać', () => {
    // Rekordzista w indeksie ma 260 kopii; węzeł wozi 25, a widok nie ma udawać,
    // że to wszystko.
    const tree = buildProvenanceTree(PIEC, 260)

    expect(tree.shown).toBe(5)
    expect(tree.total).toBe(260)
    expect(tree.hidden).toBe(255)
  })

  it('pusta prowenancja to puste drzewo, nie wyjątek', () => {
    const tree = buildProvenanceTree([], 0)

    expect(tree.roots).toEqual([])
    expect(tree.commonName).toBeNull()
    expect(tree.hidden).toBe(0)
  })

  it('duplikaty tej samej ścieżki nie mnożą gałęzi', () => {
    const tree = buildProvenanceTree([copy('P', 'a/p.pdf'), copy('P', 'a/p.pdf')], 2)

    expect(tree.roots[0].children).toHaveLength(1)
  })
})
