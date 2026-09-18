# HANDOFF

## Kontekst ręczny

- Cel bieżącej pracy: weryfikacja warstwy agent-agnostic po przebudowie (Claude/Codex/Gemini) oraz przestawienie pracy klasyfikacyjnej z limitu koordynatora na konto ChatGPT. Domknięte B5. Nie ruszano pilotażu ani materiałów.
- Aktywny przedmiot `(semestr, skrót, grupa)`: brak — praca narzędziowa; `ai_resolve.py` sprawdzony end-to-end na syntetycznym manifeście w scratchpadzie (SEM1/HiH), nie na realnych źródłach.
- Ostatni zakończony krok: commit `eb96ca4`. B5 kompletne — `scripts/ai_resolve.py`, `prompts/classify_ambiguous.md`, `prompts/relate_cluster.md`, recepta `just subject-ai-resolve`, 77 testów w `tests/test_ai_resolve.py`.
- Polityka kosztowa (nowa, wiążąca): `thresholds.yaml: llm` kieruje `classify` i `relate` na `codex_cli`/`gpt-6-astra`. Koordynator uruchamia klasyfikator i **ocenia** wynik; nie klasyfikuje w sesji i nie forkuje do tego podagenta. `just claude` nie nadpisuje już `PACZKA_LLM_RELATE_BACKEND` — wcześniej samo uruchomienie sesji przenosiło `relate` z powrotem na limit Anthropic. Skierowanie na Claude to świadoma decyzja: `PACZKA_LLM_RELATE_BACKEND=claude_cli just claude`.
- Kontrakt B5: wejście `manifest_slice.jsonl`, wyjście `plan.ai.jsonl` obok manifestu, jedna linia na sha256, walidowana wobec `prompts/plan_line.schema.json`. Progi `confidence` z `thresholds.yaml` są wiążące i nadpisują deklarację modelu (`< review_min` → `quarantine`, `< auto_apply` → `needs_review`). Kategoria musi wynikać z form przedmiotu (`subjects.yaml: forms` × `syntax.yaml: categories.*.forms`). `source_sha256` zawsze z manifestu — model nie może podmienić tożsamości treści. Przebieg wznawialny: sha256 obecne w wyjściu są pomijane.
- Pułapka do zapamiętania: tryb strukturalny OpenAI odrzuca kanoniczny schemat (`'required' … Missing 'year'`, brak wsparcia dla `pattern`/`minimum`). `wire_schema()` robi wariant „po drucie”; walidacja lokalna zostaje przy oryginale. Nie wysyłaj kanonicznego schematu wprost do `--output-schema`.
- Infrastruktura: `claude-code-router` usunięty z bazowego `~/.codex/config.toml` (kopia `~/.codex/config.toml.pre-ccr-removal-20260918-105323`). Powód krytyczny: obejście proxy flagą `--ignore-user-config` odcina `[hooks.state]`, przez co Codex **przestaje uruchamiać** `.codex/hooks.json` — guard `00_SOURCES` milczy (test różnicowy: bez flagi w logu jest `hook: PreToolUse`, z flagą nie ma). Delegacja używa teraz `-c model_provider="openai"`. Nie przywracaj tej flagi.
- Wykonane testy: `just test` 430/430; `tests/test_ai_resolve.py` 77/77; `just skills-check` 5/5; `just agent-doctor` bez błędów (dochodzi kontrola `agy` i wykrywanie nawrotu proxy — zweryfikowane na kopii configu sprzed czyszczenia). Żywe CLI: `claude -p`, `agy -p`, `codex exec` (provider: openai), `just codex` i `just codex-read` wstają jako TUI pod pty. Cache AI zweryfikowany (drugie wywołanie `cached=true`, 0.0 s).
- Skille/delegacja: testy `ai_resolve` napisał Codex (`codex exec -s workspace-write`, zero tokenów Anthropic). Jego raport nie został wzięty na wiarę — przy przeglądzie wyszło, że wkleił zamrożoną kopię `plan_line.schema.json` do pliku testowego; zastąpiono ją `load_schema()` i dołożono test pilnujący, że stub `syntax.yaml` nie rozjedzie się z realnym plikiem.
- Następna dokładna czynność: B2 — `scripts/extract_text.py` i testy PDF/DOCX/PPTX, cache, opcjonalny OCR. To odblokuje `text_head` w manifeście, bez którego `ai_resolve.py` klasyfikuje głównie po nazwie i wrzuca nieczytelne skany do `quarantine`.
- Blokery / otwarte decyzje: brak. Dziura w `guard-sources.py` zamknięta w `ada28e7`: hook analizuje teraz argumenty i odbiornik wywołania, więc łapie mutacje ukryte w kodzie interpretera (`python3 -c`, `perl -e`, `node -e`, heredoc), `find -delete`, zapis wskazany flagą (`cp -t`, `sort -o`) i wymuszone nadpisanie `>|`, a czysty odczyt nadal przechodzi. Kopiowanie jest asymetryczne: źródłem wolno być katalogowi źródeł, celem nie.
- Znany, świadomie zostawiony fałszywy alarm guarda: `tee` jest na liście słów twardo mutujących, więc potok ze źródeł do `tee` poza nimi zostanie zablokowany — używaj przekierowania `>`. Ogólniej hook blokuje każdą komendę Bash, której **tekst** zawiera ścieżkę źródeł razem ze słowem mutującym (także w komunikacie commita); w takich wypadkach używaj narzędzi Edit/Write zamiast powłoki.
- Uruchamianie agentów interaktywnie: rozpisane w `README.md`, sekcja „Agenci interaktywni” (pierwsza konfiguracja, `just claude`, trzy tryby sandboxu Codeksa, przekazywanie argumentów **bez** `--`, potwierdzanie konta). `AGENTS.md` i `CLAUDE.md` tylko tam odsyłają — nie duplikuj tej treści.
- Stan akceptacji planu: `brak` — nie przygotowano ani nie zaakceptowano planu migracji materiałów.
- Git: `eb96ca4` to lokalny commit narzędzi (19 plików), bez push i bez PR. Drzewo czyste. Materiałów nie dotykano.
- Zakazy dla następnego agenta: nie wykonuj apply bez jawnej zgody na konkretny plan; nie dodawaj sources jako writable root; nie przywracaj `--ignore-user-config` w delegacji Codeksa; nie przestawiaj `classify`/`relate` z powrotem na `claude_cli` bez decyzji użytkownika; nie commituj materiałów razem z narzędziami.

<!-- BEGIN AUTO -->
- Odświeżono: 2026-09-18T12:07:12+02:00
- Branch: `master`
- Commit: `ada28e7`
- Git status:
  ```text
  (clean)
  ```
- Pierwsze otwarte TODO: - [ ] B2. `scripts/extract_text.py` — głowa tekstu (PDF/DOCX/PPTX, OCR awaryjnie) do `20_WORK/extracted_text/{sha256}.txt`, `normalized_text_hash`, `simhash`, `phash`; tylko unique, status `extracted`
<!-- END AUTO -->
