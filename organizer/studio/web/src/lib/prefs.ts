/**
 * Ustawienia widoku zapamiętywane między odświeżeniami (localStorage).
 *
 * Trzymamy tu wyłącznie **wybór człowieka** — co oglądał i w jakiej zakładce —
 * nigdy danych z indeksu. Odświeżenie strony na tablecie ma wrócić tam, gdzie
 * się skończyło, a nie na początek listy 98 przedmiotów.
 *
 * Każdy odczyt i zapis jest w `try`: w trybie prywatnym, przy zablokowanych
 * danych stron albo w widoku osadzonym `localStorage` potrafi rzucić wyjątkiem,
 * a brak zapamiętanego stanu nie może wywrócić aplikacji.
 */

export interface Prefs {
  /** Zakładka: browse | decide | clusters | plan | graph | history | stats. */
  mode?: string;
  semester?: number | null;
  grupa?: string | null;
  skrot?: string | null;
  /** Filtr etapu z kolejki po lewej. */
  stage?: string | null;
  /** Czy boczne panele są rozwinięte. */
  queueOpen?: boolean;
  listOpen?: boolean;
}

const KEY = 'paczka-studio:prefs:v1';

export function loadPrefs(): Prefs {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? (parsed as Prefs) : {};
  } catch {
    return {};
  }
}

export function savePrefs(prefs: Prefs): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(prefs));
  } catch {
    /* brak pamięci trwałej to niedogodność, nie błąd */
  }
}

export function clearPrefs(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* jw. */
  }
}
