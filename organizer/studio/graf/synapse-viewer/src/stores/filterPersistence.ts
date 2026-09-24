import type { GraphFilters } from '../domain/graph/selectors'

/**
 * Zapamiętywanie filtrów między odświeżeniami.
 *
 * Bez tego każde wejście zaczyna od widoku domyślnego, a praca nad jednym przedmiotem
 * to kilkanaście odświeżeń dziennie — za każdym razem trzeba było wyklikać zakres od
 * nowa (zgłoszone 2026-09-24).
 *
 * Zapis jest ODPORNY NA ZMIANĘ DANYCH: wybór odnosi się do konkretnych tagów, typów
 * i kategorii, a te znikają, gdy graf zostanie przebudowany. Dlatego przy wczytaniu
 * zostawiamy tylko to, co w tym grafie nadal istnieje — resztę po cichu odrzucamy,
 * bo filtr wskazujący nieistniejący tag gasi widok bez śladu, dlaczego.
 */
export const STORAGE_KEY = 'synapse-filters-v1'

export interface FilterVocabulary {
  categories: Set<string>
  statuses: Set<string>
  levels: Set<number | null>
  tags: Set<string>
  nodeTypes: Set<string>
  relationKinds: Set<string>
}

export function sanitizeFilters(
  stored: unknown, vocabulary: FilterVocabulary,
): GraphFilters | null {
  if (typeof stored !== 'object' || stored === null) return null
  const raw = stored as Partial<GraphFilters>
  const keep = <T>(values: unknown, allowed: Set<T>): T[] =>
    Array.isArray(values) ? (values as T[]).filter((value) => allowed.has(value)) : []

  return {
    categories: keep(raw.categories, vocabulary.categories),
    statuses: keep(raw.statuses, vocabulary.statuses),
    levels: keep(raw.levels, vocabulary.levels),
    tags: keep(raw.tags, vocabulary.tags),
    nodeTypes: keep(raw.nodeTypes, vocabulary.nodeTypes),
    relationKinds: keep(raw.relationKinds, vocabulary.relationKinds),
    tagMode: raw.tagMode === 'any' ? 'any' : 'all',
    connectedOnly: Boolean(raw.connectedOnly),
  }
}

/** Czy zapisany wybór cokolwiek zawęża? Pusty nie jest wart przywracania. */
export function narrowsAnything(filters: GraphFilters): boolean {
  return (
    filters.categories.length > 0 ||
    filters.statuses.length > 0 ||
    filters.levels.length > 0 ||
    filters.tags.length > 0 ||
    filters.nodeTypes.length > 0 ||
    filters.relationKinds.length > 0 ||
    Boolean(filters.connectedOnly)
  )
}

export function readStoredFilters(): unknown {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function writeStoredFilters(filters: GraphFilters): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(filters))
  } catch {
    // Tryb prywatny albo zablokowane dane stron: brak zapisu nie może psuć widoku.
  }
}
