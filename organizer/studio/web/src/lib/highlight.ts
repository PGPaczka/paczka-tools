/**
 * Kolorowanie składni podglądu tekstu — dodatek, nie fundament.
 *
 * Dwie zasady, obie wynikają z tego, czym jest studio:
 *  1. Język rozstrzyga backend (`preview.text_language`), bo to reguła o treści,
 *     a front nie zgaduje po rozszerzeniu (`studio/AGENTS.md`, reguła 1).
 *  2. Biblioteka doczytuje się dopiero, gdy naprawdę jest co pokolorować —
 *     pierwsze wejście do studia ma być szybkie także przez tailscale na telefonie.
 *
 * Gdy cokolwiek się nie uda, zwracamy `null`: widok pokazuje wtedy czysty tekst,
 * bo czytelny plik bez kolorów jest lepszy niż brak podglądu.
 */

type Hljs = typeof import('highlight.js')['default'];

let pending: Promise<Hljs> | null = null;

function load(): Promise<Hljs> {
  if (pending === null) {
    pending = import('highlight.js').then((module) => module.default);
  }
  return pending;
}

export async function highlight(text: string, language: string | null): Promise<string | null> {
  // `plaintext` to uczciwa odpowiedź backendu „to zwykły tekst" — nie ma czego kolorować.
  if (!language || language === 'plaintext' || text === '') return null;
  try {
    const hljs = await load();
    if (!hljs.getLanguage(language)) return null;
    // `ignoreIllegals`: podgląd to GŁOWA pliku, więc urwana składnia jest normą.
    return hljs.highlight(text, { language, ignoreIllegals: true }).value;
  } catch {
    return null;
  }
}
