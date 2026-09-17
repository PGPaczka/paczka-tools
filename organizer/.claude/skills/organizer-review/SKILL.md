---
name: organizer-review
description: "Review planu jednego przedmiotu i zapis decyzji człowieka. Claude: /organizer-review; Codex: $organizer-review."
disable-model-invocation: true
argument-hint: "SKROT [SEMESTR]"
arguments: [skrot, semestr]
---

# organizer-review — $skrot $semestr

Człowiek decyduje; Ty przygotowujesz materiał do decyzji i zapisujesz odpowiedzi. Bez `apply`.

## Kroki
1. Wczytaj `reports/plan.$skrot.$semestr.jsonl` (+ `.ai.jsonl`, jeśli jest). Nie czytaj plików źródłowych.
2. `scripts/review_report.py --semester $semestr --skrot $skrot` → `reports/review/$skrot.html`
   (`difflib.HtmlDiff` na wyciągniętym tekście par near-dupe + miniatury obrazów). Brak skryptu →
   zaimplementuj coding agentem, zweryfikuj testami i wróć.
3. Podziel pozycje na 3 listy i pokaż **każdą w ≤15 wierszach** (sha256 skrócone do 8 znaków,
   nazwa, proponowany target, confidence, reason):
   a) `needs_review` 0.70–0.90, b) `quarantine`/unresolved, c) pary z relacją do potwierdzenia
   (`near_duplicate` vs `older_version`; kandydaci na `outdated` — tylko tu wolno je oznaczyć).
4. Zbieraj decyzje użytkownika partiami. Każdą zapisz do `reports/manual_decisions.jsonl`:
   `{"sha256":"…","decision_type":"target|relation|outdated|skip","target_relative_path":"…",
   "relation_override":null,"decided_by":"human","decided_at":"<ISO>","note":"…"}` (confidence=1.0).
5. Po zakończeniu: `scripts/build_plan.py` (scala manual → plan) i `scripts/validate_plan.py --dry-run`.

## STOP
Pokaż stan: ile decyzji zapisano, ile pozostało `unresolved` (zostają w kwarantannie, to OK),
wynik walidatora. Zaproponuj workflow `organizer-ship` (Claude:
`/organizer-ship`, Codex: `$organizer-ship`). Nie uruchamiaj go sam.
