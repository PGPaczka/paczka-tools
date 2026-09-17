# SKILLS.md — proponowane skille

Reużywalne procedury dla tego projektu. Każdy skill to zwięzły, powtarzalny
przepis: kiedy użyć, wejście, kroki, wyjście. Większość jest **deterministyczna
(skrypt)**; tylko dwa dotykają AI. Skille deterministyczne mogą być zwykłymi
komendami CLI; dwa „AI" można docelowo zarejestrować jako skille Claude Code /
Codex (kontrakt manifest→plan).

Legenda: 🔧 = skrypt (bez AI) · 🤖 = używa AI · 👤 = wymaga człowieka.

## Walidacja zainstalowanych skilli

Uruchom `just skills-check` w `organizer/`. Sprawdzane są nagłówki YAML
w `.claude/skills/organizer-*/SKILL.md` oraz symlinki w `.agents/skills/`.
Ta sama kontrola działa w zwykłym `just test`.

Agent ma sam dobierać procedury do zadania, bez ręcznego wpisywania ich nazw.
We wszystkich pięciu skillach ustawiono `disable-model-invocation: false`
dla Claude i `policy.allow_implicit_invocation: true` w `agents/openai.yaml`
dla Codexa. Parametry wynikają z kontekstu rozmowy; brakujące agent doprecyzowuje.
To nie jest zgoda na `apply` — akceptacja konkretnego planu nadal jest wymagana.

`argument-hint` pozostaje podpowiedzią do opcjonalnego ręcznego wywołania.
Nie usuwamy ustawień hosta dla zgodności z ogólnym `quick_validate.py` z skill-creator,
który dopuszcza mniej pól. Walidator projektu sprawdza znane pola i ich typy,
odrzuca literówki, powtórzone klucze i błędny YAML; nie zmienia plików.
To kontrola statyczna, nie test wykonania procedur w Claude ani Codexie.

---

## 🔧 scan-inventory
**Kiedy:** na starcie i przy dorzuceniu nowej paczki.
**Wejście:** `00_SOURCES/`.
**Kroki:** przejdź drzewo (tylko `stat`) → zapisz `files` i `folders`
(file_count, total_bytes, max_mtime, structural_signature). Na re-runie pomiń
poddrzewa niezmienione od ostatniego razu.
**Wyjście:** tabele `files`/`folders`, `reports/inventory.jsonl`, `reports/SOURCES_TREE.md`.

## 🔧 hash-content
**Kiedy:** po `scan-inventory`.
**Wejście:** `files` bez hasha.
**Kroki:** policz sha256 (+ opcjonalnie blake3) każdego pliku → wypełnij
`content` (dedup plików). Idempotentne (UPSERT po sha256).
**Wyjście:** `content`, `exact_duplicates.csv`.

## 🔧 fold-hash
**Kiedy:** po `hash-content`.
**Kroki:** policz `tree_hash` (ścieżka+treść) i `content_set_hash` (treść bez
nazw) per folder; oznacz `duplicate_of` dla równych drzew (całe poddrzewo →
tylko-provenance).
**Wyjście:** wypełnione `folders`, `folder_overlap.csv` (pokrycie częściowe).

## 🔧 dedup-report
**Kiedy:** po `fold-hash`, przed pilotażem.
**Kroki:** policz treść unikalną vs zduplikowaną (bajty i pliki), rozmiar per
paczka; złóż z `ncdu` (interaktywnie).
**Wyjście:** `reports/size_report.md`.

## 🔧 extract-text
**Kiedy:** przed klasyfikacją, tylko dla poddrzew `unique`.
**Kroki:** PDF→tekst (PyMuPDF), DOCX/PPTX→tekst, obrazy→phash+metadane;
**OCR tylko gdy brak warstwy tekstowej** (na żądanie). Zapisz tekst keyed by hash.
**Wyjście:** `20_WORK/extracted_text/`, `norm_text_hash`, `simhash`, `phash`.

## 🔧 classify-subject-deterministic
**Kiedy:** dla jednego przedmiotu, po `extract-text`.
**Wejście:** `config/subjects.yaml`, `config/syntax.yaml`, pliki przedmiotu.
**Kroki:** dopasuj przedmiot po nazwie komponentu ścieżki **gdziekolwiek**
(fuzzy, aliasy), rozstrzygnij kolizję skrótu przez **semestr**; przypisz
kategorię i `target_relative_path` + confidence. Waliduj względem `forms`
przedmiotu (np. ME nie ma laboratoriów).
**Wyjście:** wpisy `classifications` (method=deterministic/heuristic), kolejka
`unresolved`.

## 🤖 ai-resolve-ambiguous
**Kiedy:** dla `unresolved` jednego przedmiotu; tanie, wsadowe.
**Wejście:** `manifest_slice.jsonl` (nazwa+ścieżka+głowa tekstu ~1–2 KB), zasady.
**Kroki:** model proponuje kategorię/ścieżkę + confidence + reason. Cache po
sha256. Backend przez `llm_client` (Claude/Codex).
**Wyjście:** dopisane linie do `plan.jsonl` (method=llm).

## 🤖 relate-cluster
**Kiedy:** relacje wymagające zestawienia (zdjęcie egzaminu ↔ opracowanie,
wersje). Drogie, rzadkie.
**Kroki:** bucketuj kandydatów (ten sam przedmiot, zbliżony rok, obraz×dokument),
OCR zdjęć na żądanie, model proponuje relacje (`original_exam`,
`processed_version`, `older_version`...) + confidence + reason. Oba pliki zostają.
**Wyjście:** wpisy `relations`.

## 🔧 build-move-plan
**Kiedy:** po klasyfikacji + AI.
**Kroki:** złóż `plan.jsonl` (jedna decyzja/linia, operuje na sha256, nie na
ścieżce): action (copy/quarantine/skip), target, relacje, confidence, method,
reason, needs_review.
**Wyjście:** `reports/plan.{SKROT}.jsonl`.

## 🔧 validate-plan
**Kiedy:** przed każdym `apply`.
**Kroki:** schema OK; każdy source_sha256 istnieje; target pod `paczka/`, bez
`..`, zgodny z `syntax.yaml` (+ lint nazw); brak kolizji (ten sam target różna
treść); bramka confidence; integralność relacji; **dry-run diff** (drzewo +
liczby).
**Wyjście:** raport walidacji; exit≠0 przy twardym błędzie.

## 👤🔧 review-near-dupe-diff
**Kiedy:** near-dupe i przedział 0.70–0.90.
**Kroki:** dla par near-dupe wygeneruj **diff wyciągniętego tekstu**
(`difflib.HtmlDiff`) + miniatury obrazów; człowiek decyduje. Decyzje zapisz jako
`manual` (conf=1.0) do `manual_decisions.jsonl`.
**Wyjście:** `reports/review/{SKROT}.html`, `manual_decisions.jsonl`.

## 🔧 apply-and-verify
**Kiedy:** PO akceptacji planu.
**Kroki:** snapshot (`cp -al`) → `apply` (copy z CAS, idempotentne, kolizje→log)
→ `verify` (hash celu == źródła, kompletność).
**Wyjście:** zaktualizowane `paczka/`, `reports/applied.jsonl`.

## 🔧 provenance-report
**Kiedy:** po `apply`.
**Kroki:** z `files`+`content`+`relations` wygeneruj `provenance.jsonl` +
per-przedmiot `README.md` + (opcjonalnie) notatki `.md` z wikilinkami dla
`synapse`.
**Wyjście:** `provenance.jsonl`, README przedmiotów, graf.

## 🔧 subject-git-flow
**Kiedy:** cykl jednego przedmiotu.
**Kroki:** `gh issue create` → `gh issue develop` (branch) → commity semantyczne
(`plan`→`apply`→`docs`) → `gh pr create` z `Closes #NN`.
**Wyjście:** issue + PR powiązane; po merge issue zamknięte.

---

### Uwaga
Skille 🤖 są celowo jedynymi punktami styku z modelem — działają na kontrakcie
`manifest→plan`, więc Claude i Codex są wymienne. Reszta to czyste skrypty.
