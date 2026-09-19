/**
 * Formatowanie liczb i dat w widoku. Wyłącznie prezentacja — żadna z tych funkcji
 * nie podejmuje decyzji o danych (te są po stronie `orglib`, patrz studio/AGENTS.md).
 *
 * Grupowanie cyfr robimy sami, a nie przez `Intl`: wynik ma być identyczny
 * niezależnie od tego, jakie ICU ma przeglądarka i node uruchamiający testy.
 */

/** Wąska spacja nierozdzielająca — separator tysięcy w polskiej typografii. */
const THIN_SPACE = ' ';

/** 2570 → „2 570”. Wartości spoza liczb (null z API) → „—”. */
export function count(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const sign = value < 0 ? '-' : '';
  const digits = Math.abs(Math.trunc(value)).toString();
  let out = '';
  for (let i = 0; i < digits.length; i += 1) {
    if (i > 0 && (digits.length - i) % 3 === 0) out += THIN_SPACE;
    out += digits[i];
  }
  return sign + out;
}

/** Rozmiar pliku w jednostkach binarnych, z przecinkiem dziesiętnym. */
export function bytes(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
  let size = Math.abs(value);
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  const rounded = unit === 0 ? Math.round(size) : Math.round(size * 10) / 10;
  return `${rounded.toString().replace('.', ',')}${THIN_SPACE}${units[unit]}`;
}

/** ISO-8601 z bazy → „2026-09-19 00:25”. Puste → „—”. */
export function stamp(value: string | null | undefined): string {
  if (!value) return '—';
  const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/.exec(value);
  return match ? `${match[1]} ${match[2]}` : value;
}

/** Pewność 0..1 → „95%”. Brak decyzji → „—”. */
export function percent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${Math.round(value * 100)}%`;
}

/** Ostatni segment ścieżki POSIX — nazwa pliku bez drogi do niego. */
export function basename(path: string | null | undefined): string {
  if (!path) return '—';
  const parts = path.split('/').filter(Boolean);
  return parts.length ? parts[parts.length - 1] : path;
}

/** Ścieżka bez ostatniego segmentu (do wyświetlenia przygaszonym kolorem). */
export function dirname(path: string | null | undefined): string {
  if (!path) return '';
  const index = path.lastIndexOf('/');
  return index <= 0 ? '' : path.slice(0, index);
}
