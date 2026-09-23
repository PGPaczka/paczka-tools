import { describe, expect, it } from 'vitest'

import { scopeLevels, scopeTagOf } from './scope'
import type { RealNode } from './GraphModel'

function node(id: string, type: string, tags: string[], title = id): RealNode {
  return {
    id, kind: 'real', title, path: `${id}.md`, category: 'x', level: null,
    status: 'completed', tags, aliases: [], modified: '', excerpt: '', wordCount: 0, type,
  }
}

const VAULT_Z_KATEGORIAMI: RealNode[] = [
  node('sem3', 'semester', ['semestr', 'sem3'], 'Semestr 3'),
  node('sem7', 'semester', ['semestr', 'sem7'], 'Semestr 7'),
  node('sem3-ako', 'subject', ['sem3', 'ako'], 'AKO'),
  node('sem3-bd', 'subject', ['sem3', 'bd'], 'BD'),
  node('sem7-ako', 'subject', ['sem7', 'ako'], 'AKO (sem 7)'),
  node('sem3-ako-kat-kolokwia', 'category', ['sem3', 'ako', 'kategoria-kolokwia'], 'Kolokwia'),
  node('sem3-ako-kat-laby', 'category', ['sem3', 'ako', 'kategoria-laby'], 'Laboratoria'),
  node('sem3-bd-kat-kolokwia', 'category', ['sem3', 'bd', 'kategoria-kolokwia'], 'Kolokwia'),
  node('ako-1', 'file', ['sem3', 'ako', 'kategoria-kolokwia']),
  node('ako-2', 'file', ['sem3', 'ako', 'kategoria-laby']),
  node('bd-1', 'file', ['sem3', 'bd', 'kategoria-kolokwia']),
]

const VAULT: RealNode[] = [
  node('sem3', 'semester', ['semestr', 'sem3'], 'Semestr 3'),
  node('sem4', 'semester', ['semestr', 'sem4'], 'Semestr 4'),
  node('sem3-ako', 'subject', ['sem3', 'ako', 'grupa-wspolne'], 'AKO — Architektura'),
  node('sem3-so', 'subject', ['sem3', 'so', 'grupa-wspolne'], 'SO — Systemy'),
  node('ako-1', 'file', ['sem3', 'ako', 'rodzaj-pdf']),
  node('ako-2', 'file', ['sem3', 'ako', 'rodzaj-pdf']),
  node('so-1', 'file', ['sem3', 'so', 'rodzaj-pdf']),
]

describe('zakres: semestr i przedmiot', () => {
  it('przedmiot wybiera się swoim skrótem, nie semestrem', () => {
    // Sedno zgłoszenia: filtr po tym, co widać przy przedmiocie (`SEM3`), pokazywał
    // przedmioty BEZ ich plików. Tag przedmiotu bierze jedno i drugie.
    const levels = scopeLevels(VAULT)
    const subject = levels.find((l) => l.type === 'subject')!

    expect(subject.options.map((o) => o.tag)).toEqual(['ako', 'so'])
    expect(subject.options[0].count).toBe(2)
  })

  it('semestr wybiera się tagiem, który niosą także pliki', () => {
    const semester = scopeLevels(VAULT).find((l) => l.type === 'semester')!

    expect(semester.options.map((o) => o.tag)).toEqual(['sem3', 'sem4'])
    expect(semester.options[0].count).toBe(5)
  })

  it('przedmiot bez plików nadal wybiera się SOBĄ, nie semestrem', () => {
    // Pierwsza wersja brała „najrzadszy tag wspólny z poziomem niżej" i dla takiego
    // przedmiotu wychodził z tego tag semestru: wybór przedmiotu gasił cały graf.
    const pusty = node('sem4-fiz', 'subject', ['sem4', 'fiz', 'grupa-wspolne'], 'FIZ — Fizyka')
    const subject = scopeLevels([...VAULT, pusty]).find((l) => l.type === 'subject')!

    const wybor = subject.options.find((o) => o.id === 'sem4-fiz')!
    expect(wybor.tag).toBe('fiz')
    expect(wybor.count).toBe(0)
  })

  it('nie robi poziomu z najdrobniejszego typu — nie ma w co schodzić', () => {
    expect(scopeLevels(VAULT).map((l) => l.type)).toEqual(['semester', 'subject'])
  })

  it('vault bez typów nie dostaje wyboru zakresu', () => {
    expect(scopeLevels([node('a', '', ['x'])])).toEqual([])
  })

  it('notatka bez własnego tagu nie jest zakresem', () => {
    // Tag, który niosą wszyscy rówieśnicy, nie nazywa żadnego z nich.
    expect(
      scopeTagOf(node('x', 'subject', ['wspolny']), new Map([['wspolny', 3]]), new Set(), new Map()),
    ).toBeNull()
  })
})

describe('zakres z poziomem kategorii', () => {
  it('kategoria ma własny tag, choć „kolokwia" ma każdy przedmiot', () => {
    // Rodzeństwem kategorii są kategorie TEGO przedmiotu, nie wszystkie w paczce.
    const poziomy = scopeLevels(VAULT_Z_KATEGORIAMI)
    const kategorie = poziomy.find((l) => l.type === 'category')!

    expect(kategorie.options.map((o) => o.tag)).toEqual([
      'kategoria-kolokwia', 'kategoria-kolokwia', 'kategoria-laby',
    ])
  })

  it('schodzi się po kolei: semestr, przedmiot, kategoria', () => {
    expect(scopeLevels(VAULT_Z_KATEGORIAMI).map((l) => l.type)).toEqual([
      'semester', 'subject', 'category',
    ])
  })

  it('przedmiot o skrócie powtórzonym w innym semestrze nadal jest zakresem', () => {
    // Wcześniej odpadał: tag `ako` nosiły dwa przedmioty, więc reguła „unikalny w całym
    // poziomie" odrzucała oba. W obrębie semestru jest jednoznaczny.
    const przedmioty = scopeLevels(VAULT_Z_KATEGORIAMI).find((l) => l.type === 'subject')!

    expect(przedmioty.options.filter((o) => o.tag === 'ako')).toHaveLength(2)
  })

  it('wybór kategorii zawęża się do wybranego przedmiotu', () => {
    // Zawężaniem zajmuje się panel (po `tags`), tu sprawdzamy, że dane na to pozwalają.
    const kategorie = scopeLevels(VAULT_Z_KATEGORIAMI).find((l) => l.type === 'category')!
    const wAko = kategorie.options.filter((o) => o.tags.includes('ako'))

    expect(wAko.map((o) => o.label)).toEqual(['Kolokwia', 'Laboratoria'])
  })
})

describe('liczby przy opcjach', () => {
  it('mówią, ile zobaczysz po kliknięciu — nie ile jest w całej paczce', () => {
    // „Egzamin" przy AKO pokazywał 303 (wszystkie egzaminy paczki), a po wybraniu
    // zostawało 148. Licznik niezgodny z tym, co widać, jest gorszy niż jego brak.
    const kategorie = scopeLevels(VAULT_Z_KATEGORIAMI).find((l) => l.type === 'category')!
    const kolokwiaAko = kategorie.options.find(
      (o) => o.tags.includes('ako') && o.label === 'Kolokwia',
    )!

    expect(kolokwiaAko.count).toBe(1)
  })
})
