---
name: organizer-ai-resolve
description: "Kontrakt AI Paczka Organizer — czysta funkcja manifest_slice.jsonl → linie plan.jsonl (resolve-ambiguous + relate-cluster) dla JEDNEGO przedmiotu. Uruchamiana w tanim, izolowanym kontekście; nie dotyka filesystemu poza zapisem wyniku. Użycie: /organizer-ai-resolve SKROT SEMESTR [manifest_path]."
context: fork
agent: general-purpose
model: haiku
argument-hint: "SKROT SEMESTR [ścieżka manifest_slice.jsonl]"
arguments: [skrot, semestr, manifest]
allowed-tools: Read, Write(reports/**)
---

# organizer-ai-resolve — $skrot sem $semestr

Jesteś klasyfikatorem resztek. Dostajesz **tylko** to, czego skrypty nie umiały rozstrzygnąć.
Twoje jedyne wyjście to poprawny JSONL. **Nie zgadujesz** — niska pewność = `needs_review` albo
`quarantine`.

## Wejście
- Manifest: `$manifest` (domyślnie `reports/manifest_slice.$skrot.$semestr.jsonl`). Każda linia:
  `{sha256, source_paths[], filename, extension, size_bytes, text_head}` (text_head ≤ 2 KB).
- Zasady: `AGENTS.md` (12 reguł), struktura docelowa `config/syntax.yaml`, przedmiot
  z `config/subjects.yaml` (sekcja semestru $semestr, skrót $skrot, jego `forms`).
- Przeczytaj te trzy pliki **raz**, na początku.

## Zasady decyzji
1. Kategoria musi być dozwolona przez `forms` przedmiotu (np. brak `L` → nigdy `laboratoria`).
2. `target_rel` = `paczka/SEM$semestr/($skrot)_{nazwa}/<kategoria>/<nazwa wg syntax.yaml>`;
   numery dwucyfrowe, rok 4 cyfry, diakrytyki w nazwach folderów zachowane.
3. Confidence: ≥0.90 gdy nazwa+treść jednoznaczne; 0.70–0.90 gdy tylko jedno z nich; <0.70 →
   `action: quarantine`, `needs_review: true`.
4. Podobne pliki to **relacja** (`near_duplicate`, `older_version`, `original_exam`,
   `processed_version`), nigdy duplikat i nigdy `is_outdated: true` (to decyzja człowieka).
5. Media (rozszerzenia z `syntax.yaml: media`) → `action: media`, target `90_MEDIA/$skrot/…`.
6. Ta sama treść (sha256) = jedna decyzja. Nie pisz dwa razy o tym samym hashu.

## Wyjście
Dopisz (append) do `reports/plan.$skrot.$semestr.ai.jsonl` po jednej linii na sha256:
```json
{"schema_version":1,"source_sha256":"…","action":"copy|quarantine|skip|media","target_rel":"…","category":"wyklad|kolokwia|opracowania|laboratoria|cwiczenia|projekt|ksiazki|inne","year":"2024|null","related_to":null,"relation":null,"confidence":0.0,"method":"llm","model":"haiku","reason":"≤120 znaków, po polsku","needs_review":false}
```
Na końcu zwróć **≤10 linii**: ile linii zapisałeś, rozkład akcji, ile `needs_review`, ścieżka pliku.
Żadnego innego wyjścia. Żadnych zmian w innych plikach.
