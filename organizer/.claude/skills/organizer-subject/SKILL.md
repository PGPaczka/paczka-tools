---
name: organizer-subject
description: "Cykl planowania jednego przedmiotu, zatrzymuje się przed review i apply. Claude: /organizer-subject; Codex: $organizer-subject."
disable-model-invocation: true
argument-hint: "SKROT SEMESTR   (np. AKO 3)"
arguments: [skrot, semestr]
---

# organizer-subject — jeden przedmiot: $skrot, semestr $semestr

Tożsamość przedmiotu = **(semestr, skrót)**, bo skrót nie jest unikalny (`config/subjects.yaml`).
Jeśli para nie istnieje w `subjects.yaml` — STOP i zapytaj.

## Warunki wstępne
- First-pass zrobiony (`reports/size_report.md` istnieje, baza ma `content` i `folders`).
- Klon celu (`config/paths.yaml: target_repo`) jest na `master` bez zmian roboczych
  (`git -C <target_repo> status --porcelain` puste). Jeśli nie — STOP, powiedz co jest brudne.

## Kroki
1. **subject-start** (git): w `<target_repo>` — `gh issue create --title "[$skrot sem$semestr] migracja
   materiałów" --label "semester:$semestr,subject:$skrot"` → `gh issue develop <nr> --name subject/$skrot
   --checkout`. Zapisz numer issue do `reports/subject.$skrot.$semestr.json`.
2. **extract-text**: `scripts/extract_text.py --semester $semestr --skrot $skrot` — tylko poddrzewa
   `unique` przypisane do przedmiotu (fuzzy po komponentach ścieżki, aliasy). OCR tylko na żądanie.
   Uruchom przez `just`/skrypt; do kontekstu wraca tylko licznik plików + błędy.
3. **classify-deterministic**: `scripts/classify.py --semester $semestr --skrot $skrot` → wpisy
   `classifications` (method=deterministic/heuristic) + kolejka `unresolved`. Sprawdź `forms`
   (np. ME bez laboratoriów).
4. **unresolved?** Jeśli kolejka pusta → krok 6. Jeśli nie:
5. **AI dla resztek** — NIE w tym kontekście. Uruchom `scripts/ai_resolve.py --semester $semestr --skrot
   $skrot` (backend i model per zadanie z `config/thresholds.yaml: llm.classify` / `llm.relate`;
   domyślnie `agy_cli` = Gemini flash przez `agy -p --sandbox`, zero tokenów Anthropic; cache po
   sha256). Backend `claude_cli` woła `claude -p` z promptem z `prompts/` (odpowiednik
   `/organizer-ai-resolve`). Do kontekstu wraca: ile rozwiązane, ile nadal `unresolved`, ile
   `needs_review`.
6. **build-move-plan**: `scripts/build_plan.py --semester $semestr --skrot $skrot` →
   `reports/plan.$skrot.$semestr.jsonl` (jedna decyzja/linia, po sha256, z `_meta`).
7. **validate-plan**: `scripts/validate_plan.py reports/plan.$skrot.$semestr.jsonl --dry-run` — schemat,
   istnienie sha256, target pod `paczka/` i zgodny z `config/syntax.yaml`, brak kolizji, bramka
   confidence, relacje, **dry-run diff drzewa**. Exit≠0 → napraw przyczynę (wróć do 3), nie obchodź.

Brakujący skrypt → zaimplementuj go coding agentem w bieżącym hoście albo
zleć dostępnemu subagentowi. Brief musi zawierać kontrakt z ARCHITEKTURA §6–8,
`syntax.yaml`, `thresholds.yaml`, ścieżki z `paths.yaml` i kryteria testów.
Potem wykonaj niezależny review i wróć do kroku.

## Wyjście i STOP (👤 bramka raz na przedmiot)
Pokaż użytkownikowi **≤30 linii**: liczby (plików, % auto, review 0.70–0.90, unresolved), dry-run diff
drzewa (skrót), ścieżka planu, ścieżka `reports/review/$skrot.html` jeśli są near-dupe.
Zaproponuj workflow `organizer-review` (Claude: `/organizer-review`, Codex:
`$organizer-review`) albo po akceptacji `organizer-ship`.
**Nie wykonuj `apply`. Nie commituj w `<target_repo>`.** Commit `plan($skrot)` z `plan.jsonl` w
`paczka-tools` — tak, tu wolno (to raport tekstowy).
