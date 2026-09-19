# CLAUDE.md — studio (adapter Claude Code)

**Najpierw przeczytaj `AGENTS.md` w tym katalogu, a przed nim `organizer/AGENTS.md`.**
Ten plik zawiera wyłącznie to, co dotyczy Claude Code w zakresie studia; w razie
konfliktu wygrywa `AGENTS.md`.

Sesję nadal uruchamiaj przez `just claude` z katalogu `organizer/` — studio jest
podprojektem, nie osobnym workspace'em. Uprawnienia, hooki i guard źródeł są wspólne.

## Delegacja w tym zakresie

Obowiązuje zasada kosztowa z `organizer/CLAUDE.md`: limit Anthropic idzie na myślenie.
Podział pracy specyficzny dla studia:

| Zadanie | Gdzie |
|---|---|
| widoki, układ, czytelność, klawiatura | **zostaje w Opusie** — to ocenia oko, nie test |
| endpointy CRUD wg gotowego wzorca, schematy Pydantic | `python-pro` / `muxer:writer` |
| testy kontraktu API wg istniejących | `test-automator` albo agent `codex` |
| zapytania do SQLite i indeksy | `sql-pro` |
| sprawdzenie, czy widok da się realnie przeglądać | Playwright na realnych danych, ocena w sesji |

Frontendu **nie** deleguj na tańsze modele: to jest ta część, o którą chodzi
w całym podprojekcie, i to po niej widać, czy narzędzie oszczędza czas.

## Obowiązki na końcu kroku

Odhaczaj w `TODO-studio.md` (nie w `organizer/TODO.md`), dopisując datę i zdanie
o tym, co z zadania wynikło. Poza tym bez zmian: `just handoff` i ręczna część
`reports/HANDOFF.md` w organizerze.
