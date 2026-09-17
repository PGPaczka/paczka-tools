# HANDOFF

## Kontekst ręczny

- Cel bieżącej pracy: utwardzenie projektu jako agent-agnostic z Claude jako domyślnym koordynatorem i płynnym przejęciem przez Codex.
- Aktywny przedmiot `(semestr, skrót, grupa)`: brak — praca infrastrukturalna.
- Ostatni zakończony krok: implementacja zapisana w czterech commitach: backendy AI (`12f9c60`), wspólny guard (`809dea4`), launchery i skille (`8f6e5ad`), role Codexa (`d66643f`). Dokumentacja i ten checkpoint trafiają do osobnego commita. Delegatory `codex` i `agy` pozostają adapterami Claude; bez push do remote.
- Wykonane testy: pełny pytest 260/260; testy ról i guardu; parser wszystkich plików TOML; `git diff --check`; `just --fmt --check`; `agent-doctor` potwierdza profil OpenAI i login ChatGPT; Codex Doctor akceptuje config (tymczasowy profil bez auth/network zgłosił wyłącznie oczekiwane błędy środowiska).
- Walidacja przed commitami: ponownie 260/260 testów, `just --fmt --check`, `bash -n` launcherów i instalatorów oraz kontrola staged diff. Nadal bez smoke testu rzeczywistego subagenta i pełnej sesji Claude.
- Następna dokładna czynność: TODO B1 — zaimplementować `scripts/prepare_subject.py` i testy wycinka manifestu.
- Blokery / otwarte decyzje: pełne `subject-start` i `subject-pr` w `justfile` czekają na B1–B14; automatyczny fallback nie jest potrzebny, bo backend wybiera jawnie launcher hosta.
- Stan akceptacji planu: `brak` — nie trwa cykl przedmiotu.
- Zakazy dla następnego agenta: nie wykonuj `apply`; nie dodawaj `00_SOURCES` jako writable root; nie usuwaj globalnego CCR.

<!-- BEGIN AUTO -->
- Odświeżono: 2026-09-18T01:15:09+02:00
- Branch: `master`
- Commit: `d66643f`
- Git status:
  ```text
  M ../README.md
   M AGENTS.md
   M CLAUDE.md
   M GEMINI.md
   M README.md
   M TODO.md
   M docs/ARCHITEKTURA_FINALv1.md
   M docs/ORGANIZACJA.md
   M setup/PLUGINS.md
  ?? reports/HANDOFF.md
  ```
- Pierwsze otwarte TODO: - [ ] B1. `scripts/prepare_subject.py --semester N --skrot X` — wycinek manifestu przedmiotu (kandydaci po ścieżce/aliasach) → `reports/{SKROT}/manifest_slice.jsonl`
<!-- END AUTO -->
