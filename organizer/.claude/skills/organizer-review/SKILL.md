---
name: organizer-review
description: "Użyj, gdy plan materiałów jednego przedmiotu jest gotowy do przeglądu lub użytkownik przekazuje decyzje o planie: pokaż różnice, niejasności i zapisz decyzje. Bez apply."
disable-model-invocation: false
argument-hint: "SKROT [SEMESTR]"
arguments: [skrot, semestr]
---

# organizer-review — $skrot $semestr

Człowiek decyduje; Ty przygotowujesz materiał do decyzji i zapisujesz odpowiedzi. Bez `apply`.

## Kroki
1. Wczytaj `reports/$skrot/plan.jsonl` (nagłówek `_meta` + decyzje) oraz `validation.jsonl`
   i `unresolved.jsonl` z tego samego katalogu. Nie czytaj plików źródłowych.
   Brak planu → `just subject-plan $semestr $skrot`; powtarzające się skróty mają swój
   katalog `reports/SEM{semestr}/{grupa}/$skrot/`.
2. `just subject-review $semestr $skrot` → `reports/$skrot/review.html` (klastry near-dupe
   z `difflib.HtmlDiff` na tekście z etapu extract albo miniaturami obrazów, lista
   `needs_review` i `unresolved`, dry-run drzewa). Do kontekstu wracają LICZBY ze stdout,
   nie treść strony.
3. Podziel pozycje na 3 listy i pokaż **każdą w ≤15 wierszach** (sha256 skrócone do 8 znaków,
   nazwa, proponowany target, confidence, reason):
   a) `needs_review` 0.70–0.90, b) `quarantine`/unresolved, c) pary z relacją do potwierdzenia
   (`near_duplicate` vs `older_version`; kandydaci na `outdated` — tylko tu wolno je oznaczyć).
4. Zbieraj decyzje użytkownika partiami. Każdą zapisz do `reports/manual_decisions.jsonl`:
   `{"sha256":"…","decision_type":"target|relation|outdated|skip","target_relative_path":"…",
   "relation_override":null,"decided_by":"human","decided_at":"<ISO>","note":"…"}` (confidence=1.0).
5. Po zakończeniu: `just subject-plan $semestr $skrot` (scala decyzje w `plan.jsonl`
   i zapisuje je do bazy) oraz `just subject-validate $semestr $skrot` — kod wyjścia 2
   znaczy, że planu NIE WOLNO wykonać. Planu nie edytuj ręcznie: `plan_hash` w nagłówku
   przestanie się zgadzać i walidator to wyłapie.

## STOP
Pokaż stan: ile decyzji zapisano, ile pozostało `unresolved` (zostają w kwarantannie, to OK),
wynik walidatora. Poproś o jawną akceptację konkretnego planu i czekaj, jeśli
jeszcze jej nie ma. Po jej uzyskaniu możesz sam dobrać `organizer-ship`,
bez wymagania od użytkownika nazwy skillu lub specjalnej komendy.
