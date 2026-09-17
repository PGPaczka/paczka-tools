---
name: organizer-ship
description: "Użyj do wykonania i weryfikacji konkretnego planu migracji przedmiotu po jego jawnej akceptacji przez użytkownika. Bez zgody tylko sprawdź bramki i poproś o akceptację; nie wykonuj apply."
disable-model-invocation: false
argument-hint: "SKROT SEMESTR"
arguments: [skrot, semestr]
---

# organizer-ship — $skrot sem $semestr (tylko po akceptacji)

Automatyczny wybór skillu nie jest zgodą na zmiany ani commit materiałów.
Operacje w `<target_repo>` wykonuj tylko w zakresie jawnie zatwierdzonego
procesu i po spełnieniu poniższych bramek. Lokalne commity kodu, konfiguracji,
testów, dokumentacji i tekstowych raportów w `paczka-tools` są domyślne po
walidacji. Push i PR nadal wymagają osobnego polecenia, zgodnie z `AGENTS.md`.

## Bramka — sprawdź WSZYSTKO, inaczej STOP
1. Użytkownik w tej rozmowie napisał wprost, że plan `$skrot` jest zaakceptowany. Jeśli nie widzisz
   takiego zdania — zapytaj i czekaj. Nie interpretuj milczenia jako zgody.
2. `scripts/validate_plan.py reports/plan.$skrot.$semestr.jsonl` → exit 0 (bez `--dry-run`, pełna walidacja).
3. `<target_repo>` jest na branchu `subject/$skrot` (nie `master`), working tree czyste.
4. Wszystkie `needs_review` rozstrzygnięte albo świadomie zostawione jako `quarantine`.

## Kroki

Uruchamiaj przez `just` lub skrypty; do kontekstu wprowadzaj tylko liczby i
błędy.
1. **snapshot**: `scripts/apply.py --snapshot` (`cp -al` katalogu przedmiotu w `paczka/` do `<work>/snapshots/`).
2. **apply**: `scripts/apply.py reports/plan.$skrot.$semestr.jsonl` — kopiuje z CAS/źródeł do
   `<target_repo>/paczka/…`; idempotentne; kolizja → log, nie nadpisuje. Media → `<media>/$skrot/…`
   + wpis w `inne/nagrania.txt`.
3. **verify**: `scripts/verify.py reports/plan.$skrot.$semestr.jsonl` — hash celu == źródła,
   kompletność. Błąd → STOP, nic nie commituj, pokaż raport.
4. **docs**: `scripts/provenance.py --semester $semestr --skrot $skrot` → `reports/provenance.jsonl`
   (tu) + `README.md` przedmiotu w `paczka/SEM$semestr/($skrot)_…/`. Możesz użyć
   dostępnego agenta dokumentacyjnego, ale wynik musi zostać zweryfikowany.
5. **git w `<target_repo>`** (branch `subject/$skrot`):
   - `git add paczka/SEM$semestr/...` → commit `apply($skrot): materiały sem$semestr` 
   - `git add` README/nagrania.txt → commit `docs($skrot): provenance + README`
   - `git push -u origin subject/$skrot` → `gh pr create --fill --body "Closes #<nr z
     reports/subject.$skrot.$semestr.json>"`. **Nie merguj.** Merge robi użytkownik.
6. **git w `paczka-tools`**: commit `docs($skrot): provenance, applied.jsonl, STATUS.md`.

## STOP
Pokaż: link do PR, liczby (skopiowane / pominięte-duplikaty / media / kwarantanna), ścieżkę snapshotu.
Następny przedmiot uruchamia użytkownik.
