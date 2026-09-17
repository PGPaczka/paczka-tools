---
name: organizer-ship
description: "Finalizacja przedmiotu Paczka Organizer PO akceptacji planu — snapshot, apply (kopiowanie do paczka/ w klonie celu), verify, provenance + README, media do 90_MEDIA, commity apply/docs na branchu subject/SKROT, PR z Closes #NN. Wymaga jawnej zgody użytkownika. Użycie: /organizer-ship SKROT SEMESTR."
disable-model-invocation: true
argument-hint: "SKROT SEMESTR"
arguments: [skrot, semestr]
---

# organizer-ship — $skrot sem $semestr (tylko po akceptacji)

## Bramka — sprawdź WSZYSTKO, inaczej STOP
1. Użytkownik w tej rozmowie napisał wprost, że plan `$skrot` jest zaakceptowany. Jeśli nie widzisz
   takiego zdania — zapytaj i czekaj. Nie interpretuj milczenia jako zgody.
2. `scripts/validate_plan.py reports/plan.$skrot.$semestr.jsonl` → exit 0 (bez `--dry-run`, pełna walidacja).
3. `<target_repo>` jest na branchu `subject/$skrot` (nie `master`), working tree czyste.
4. Wszystkie `needs_review` rozstrzygnięte albo świadomie zostawione jako `quarantine`.

## Kroki (każdy przez `muxer:runner`, do kontekstu tylko liczby i błędy)
1. **snapshot**: `scripts/apply.py --snapshot` (`cp -al` katalogu przedmiotu w `paczka/` do `<work>/snapshots/`).
2. **apply**: `scripts/apply.py reports/plan.$skrot.$semestr.jsonl` — kopiuje z CAS/źródeł do
   `<target_repo>/paczka/…`; idempotentne; kolizja → log, nie nadpisuje. Media → `<media>/$skrot/…`
   + wpis w `inne/nagrania.txt`.
3. **verify**: `scripts/verify.py reports/plan.$skrot.$semestr.jsonl` — hash celu == źródła,
   kompletność. Błąd → STOP, nic nie commituj, pokaż raport.
4. **docs**: `scripts/provenance.py --semester $semestr --skrot $skrot` → `reports/provenance.jsonl`
   (tu) + `README.md` przedmiotu w `paczka/SEM$semestr/($skrot)_…/` (`readme-generator`, haiku).
5. **git w `<target_repo>`** (branch `subject/$skrot`):
   - `git add paczka/SEM$semestr/...` → commit `apply($skrot): materiały sem$semestr` 
   - `git add` README/nagrania.txt → commit `docs($skrot): provenance + README`
   - `git push -u origin subject/$skrot` → `gh pr create --fill --body "Closes #<nr z
     reports/subject.$skrot.$semestr.json>"`. **Nie merguj.** Merge robi użytkownik.
6. **git w `paczka-tools`**: commit `docs($skrot): provenance, applied.jsonl, STATUS.md`.

## STOP
Pokaż: link do PR, liczby (skopiowane / pominięte-duplikaty / media / kwarantanna), ścieżkę snapshotu.
Następny przedmiot uruchamia użytkownik.
