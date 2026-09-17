---
name: organizer-first-pass
description: "Pierwszy przebieg Paczka Organizer (kroki 0–7 z docs/ARCHITEKTURA_FINALv1.md §13A) — mapa dublowania całego 00_SOURCES: bootstrap rmlint/ncdu, scan, hash, fold_hash, raport rozmiaru, skan ground truth paczka/. Uruchamiaj raz na całości lub po dorzuceniu nowej paczki źródłowej."
disable-model-invocation: true
argument-hint: "[--from N]  (N = numer kroku, od którego wznowić; domyślnie 0)"
---

# organizer-first-pass — kroki 0–7 (jednorazowo, deterministycznie, bez AI)

Jesteś koordynatorem. **Nie czytasz sam plików z `00_SOURCES`** — to robią skrypty i
`muxer:scout`. Argument: `$ARGUMENTS` (opcjonalnie `--from N`).

## Warunki wstępne (sprawdź, zanim ruszysz)
1. `config/paths.yaml` istnieje i 4 ścieżki (`sources`, `work`, `media`, `target_repo`) się resolvują.
2. `.venv/` istnieje (`setup/install.sh` był uruchomiony). Jeśli nie — STOP, powiedz użytkownikowi.
3. Jeśli brakuje skryptu dla danego kroku (`scripts/scan.py`, `scripts/hash_files.py`,
   `scripts/fold_hash.py`, `scripts/dedup_report.py`, `scripts/scan_target.py`) — **najpierw zleć jego
   napisanie** agentowi `python-pro` (schemat SQLite: `sql-pro`; testy: `test-automator`), z briefem:
   kontrakt z `docs/ARCHITEKTURA_FINALv1.md` §4–5, idempotencja (UPSERT po sha256 / (pack, rel_path)),
   status machine `discovered → hashed → …`, ścieżki tylko z `config/paths.yaml`. Potem `muxer:reviewer`.

## Kroki (każdy: uruchom → `muxer:runner` streszcza wynik → zapisz 1 linię do `reports/STATUS.md`)
0. **Bootstrap** (bez bazy): `rmlint --merge-directories <sources> -o json:reports/rmlint.json` (rmlint
   TYLKO raportuje; nigdy nie uruchamiaj wygenerowanego `rmlint.sh`) oraz `ncdu -o reports/ncdu.json <sources>`.
   Skala dublowania → 3 liczby w STATUS.md.
1. **Szkielet**: baza `<work>/organizer.sqlite` ze schematem z §4 (`scripts/init_db.py`).
2. **Config**: `config/subjects.yaml` + `thresholds.yaml` załadowane bez błędów (walidator YAML).
3. **scan**: `scripts/scan.py` → `files`, `folders`, `reports/inventory.jsonl`, `docs/SOURCES_TREE.md`.
4. **hash**: `scripts/hash_files.py` → `content`, `reports/exact_duplicates.csv`. (Długie — uruchom w tle,
   `muxer:runner` sprawdza postęp; wznawialne.)
5. **fold_hash**: `scripts/fold_hash.py` → `tree_hash`, `content_set_hash`, `duplicate_of`,
   `reports/folder_overlap.csv`.
6. **dedup report**: `scripts/dedup_report.py` → `reports/size_report.md` (unikalne vs zduplikowane, per paczka).
7. **ground truth**: `scripts/scan_target.py` → skan `<target_repo>/paczka` do bazy jako `source_package =
   "_target"` (lock: te pliki są kanoniczne, nie ruszamy).

## Wyjście i STOP
Po kroku 7 pokaż użytkownikowi **≤20 linii**: liczby z `size_report.md`, ile poddrzew `duplicate_of`,
ścieżki raportów. **Zatrzymaj się.** Następny krok (pilotaż `AK` sem 3) to `/organizer-subject AK 3`,
uruchamiany osobno przez użytkownika.

## Zakazy
- Żadnych zmian w `<sources>` (hook i tak zablokuje). Żadnego `apply`. Żadnego AI na tym etapie.
- Nie wklejaj surowych listingów katalogów do kontekstu — tylko liczby i ścieżki raportów.
