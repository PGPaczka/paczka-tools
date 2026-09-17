# HANDOFF

## Kontekst ręczny

- Cel bieżącej pracy: domyślne lokalne commity zmian narzędzi zgodnie z decyzją użytkownika; zapisanie reorganizacji repo i automatycznego doboru skilli.
- Aktywny przedmiot `(semestr, skrót, grupa)`: brak — praca infrastrukturalna.
- Ostatni zakończony krok: reorganizacja zapisana w `0d3e32e` — snapshot drzewa w `reports/SOURCES_TREE.md`, raporty historyczne w `reports/bootstrap/`, dane ECTS w `ects_extractor/data/`, konwerter cookies w `multi-folder-downloader/scripts/` i standardowy README downloadera. Odwołania oraz ścieżki zapisu poprawione; bez push.
- Wykonane testy: pełny pytest organizera 261/261; unittest downloadera 3/3; unittest ECTS 1/1 (bez sieci, na atrapach); `bash -n` ekstraktora; `git diff --check`; `just --fmt --check`. Pięć przeniesionych plików danych/raportów porównano bajt po bajcie z HEAD — treść identyczna. Reguły ignorowania sekretów, bazy i logów nadal działają.
- Następny zakończony krok: wszystkie pięć skilli ma `disable-model-invocation: false` i `agents/openai.yaml` z `allow_implicit_invocation: true`. Opisy wskazują warunki użycia, AGENTS dopuszcza dobór z kontekstu; przejścia między procedurami nie wymagają ręcznych komend. Zgoda na konkretny plan przed `apply` oraz reguły commit/push/PR pozostają obowiązkowe.
- Walidacja skilli naprawiona: `scripts/agent/validate_skills.py` i `just skills-check` sprawdzają metadane Claude, politykę Codexa i współdzielone symlinki. Ogólny `quick_validate.py` ma zbyt wąską listę pól; nie zmieniano go ani nie usuwano potrzebnych ustawień dla zgodności z nim.
- Decyzja użytkownika o Git: sprawdzone zmiany kodu, konfiguracji, skryptów, testów, dokumentacji i tekstowych raportów technicznych `paczka-tools` koordynator domyślnie commituje lokalnie, bez osobnego pytania. Reguła w głównym `AGENTS.md`, zasadach organizera i skillach. Materiały są wyłączone niezależnie od lokalizacji; przed `apply` nadal jawna zgoda na plan, commit materiałów tylko w zatwierdzonym procesie po `verify`. Push/PR wymagają osobnego polecenia.
- Skille, walidator i nowa polityka Git stanowią zakres bieżącego commita z tym handoffem. Sekcja AUTO jest snapshotem sprzed jego utworzenia, nie deklaracją końcowego stanu working tree.
- Testy po zmianie skilli: `just skills-check` 5/5; 32 nowe testy; pełny `just test` 293/293; `just --fmt --check` i `git diff --check` bez błędów. To kontrola statyczna i testy lokalne, nie smoke test automatycznego doboru w żywej sesji hosta. Nie uruchamiano pobierania, ekstrakcji ECTS ani migracji materiałów.
- Kontrole powtórzone przed commitami: `just test` 293/293, unittest ECTS 1/1, unittest downloadera 3/3, `just skills-check` 5/5, `bash -n`, `just --fmt --check`, `git diff --check`; bez błędów. Sekrety i baza downloadera nadal ignorowane przez Git; materiałów nie zmieniano ani nie dodawano do commitów.
- Poprzedni etap: infrastruktura agent-agnostic jest w commitach `12f9c60`, `809dea4`, `8f6e5ad`, `d66643f`, dokumentacja w `c0f9d70`. Nadal bez smoke testu rzeczywistego subagenta i pełnej sesji Claude.
- Następna dokładna czynność: TODO B1 — zaimplementować `scripts/prepare_subject.py` i testy wycinka manifestu.
- Blokery / otwarte decyzje: brak dla reorganizacji. Pełne `subject-start` i `subject-pr` w `justfile` czekają na B1–B14. Starszy generator struktury ECTS nadal ma `main_dir="../../../"` względem CWD — ostrzeżenie jest w jego nowym README; nie był uruchamiany.
- Stan akceptacji planu: `brak` — nie trwa cykl przedmiotu.
- Zakazy dla następnego agenta: nie wykonuj `apply`; nie dodawaj `00_SOURCES` jako writable root; nie usuwaj globalnego CCR.

<!-- BEGIN AUTO -->
- Odświeżono: 2026-09-18T01:38:40+02:00
- Branch: `master`
- Commit: `0d3e32e`
- Git status:
  ```text
  M .claude/agents/readme-generator.md
   M .claude/skills/organizer-ai-resolve/SKILL.md
   M .claude/skills/organizer-first-pass/SKILL.md
   M .claude/skills/organizer-review/SKILL.md
   M .claude/skills/organizer-ship/SKILL.md
   M .claude/skills/organizer-subject/SKILL.md
   M AGENTS.md
   M README.md
   M SKILLS.md
   M TODO.md
   M justfile
   M reports/HANDOFF.md
  ?? ../AGENTS.md
  ?? .claude/skills/organizer-ai-resolve/agents/
  ?? .claude/skills/organizer-first-pass/agents/
  ?? .claude/skills/organizer-review/agents/
  ?? .claude/skills/organizer-ship/agents/
  ?? .claude/skills/organizer-subject/agents/
  ?? scripts/agent/validate_skills.py
  ?? tests/test_skills.py
  ```
- Pierwsze otwarte TODO: - [ ] B1. `scripts/prepare_subject.py --semester N --skrot X` — wycinek manifestu przedmiotu (kandydaci po ścieżce/aliasach) → `reports/{SKROT}/manifest_slice.jsonl`
<!-- END AUTO -->
