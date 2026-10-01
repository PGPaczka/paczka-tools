# organizer (Paczka Organizer)

Projekt w `paczka-tools/` — jednorazowe narzędzie do scalenia kilku starych
studenckich „paczek" materiałów w jedną, uporządkowaną paczkę. Deterministycznie
tam, gdzie się da; AI tylko tam, gdzie trzeba zrozumieć treść. Nie jest
deployowane — uruchamiane na żądanie, produkuje PR-y do repo docelowego
(`config/paths.yaml: target_repo`; dziś `10_NEW/PaczkaInfaPG`, docelowo `paczka-content`).

Rodzeństwo w `paczka-tools/`: `ects_extractor` (buduje strukturę paczki z
oficjalnej strony przedmiotów) — organizer robi to samo, tylko ze starych paczek.

- **Zaczynasz tutaj:** [`docs/PIPELINE.md`](docs/PIPELINE.md) — co znaczy każdy etap,
  jakiej decyzji wymaga i jak go przejść w studiu
- Architektura: [`docs/ARCHITEKTURA.md`](docs/ARCHITEKTURA.md)
- Struktura repo i organizacji: [`docs/ORGANIZACJA.md`](docs/ORGANIZACJA.md)
- Zasady wspólne agentów: [`AGENTS.md`](AGENTS.md); adapter Claude:
  [`CLAUDE.md`](CLAUDE.md)
- Setup Claude Code (muxer, agenty, skille, status line): [`setup/PLUGINS.md`](setup/PLUGINS.md),
  ocena źródeł (historyczna): [`reports/historia/2026-09-17-ocena-claude-code.md`](reports/historia/2026-09-17-ocena-claude-code.md)

## Idea w jednym zdaniu

Skrypty robią wszystko, co da się ustalić deterministycznie (hash, dedup,
klasyfikacja po ścieżce/nazwie); AI dostaje wyłącznie niejednoznaczne resztki,
jeden przedmiot na raz; człowiek zatwierdza plan zanim cokolwiek zostanie
skopiowane. Źródła są read-only, nic nie jest kasowane, provenance zachowane.

## Quickstart

```bash
bash setup/install.sh --with-apt   # raz na maszynę
just db-init

# 1. Pierwszy przebieg na całości źródeł (nic nie kasuje)
just scan && just hash && just fold-hash && just dedup-report && just extract
just scan-target                   # ground truth: co już leży w repo paczki
just status                        # reports/STATUS.md — przedmioty × etapy

# 2. Jeden przedmiot od początku do końca
just subject-prepare 3 AKO
just subject-classify 3 AKO
just subject-relate 3 AKO
just subject-ai-resolve 3 AKO
just subject-plan 3 AKO
just subject-validate 3 AKO        # bramka: kod 2 = planu NIE wolno wykonać
just subject-review 3 AKO          # reports/AKO/review.html do obejrzenia

# 3. Dopiero po Twojej akceptacji konkretnego planu
just subject-apply 3 AKO                                  # DRY-RUN
just subject-apply 3 AKO --yes --expect-hash <odcisk>     # wykonanie
just subject-verify 3 AKO                                 # dowód; potem commit
```

Pełny przewodnik z wariantami i diagnostyką: **`docs/CLI.md`**. To samo
w przeglądarce: **`studio/README.md`** (`just studio`).

## Pipeline

```
scan → hash → dedup (pliki + foldery) → extract → classify (det.) →
  [AI dla unresolved] → plan → validate → [review] → apply → verify
```

Co każdy etap **znaczy** i jakiej decyzji od Ciebie wymaga —
[`docs/PIPELINE.md`](docs/PIPELINE.md). Same komendy — [`docs/CLI.md`](docs/CLI.md).

Wynik (`apply`) trafia do `paczka/` w klonie repo docelowego, na branchu
`subject/{SKROT}`, i dalej jako PR. Kod i operacyjne raporty zostają tutaj.

## Testy

Pięć warstw (kontrakt kodu, środowisko, kontrakt CLI, e2e, sonda) plus
własności i warstwa mutacyjna — co sprawdza każda i dlaczego akurat ten
podział, w [`docs/TESTY.md`](docs/TESTY.md).

## Skrypty

Pełny przewodnik po komendach, etap po etapie, z kodami wyjścia i tym, co
zrobić po błędzie, jest w [`docs/CLI.md`](docs/CLI.md). Etapy cyklu
per-przedmiot, w kolejności: B1 (wycinek indeksu) → B2 (ekstrakcja tekstu) →
B3 (klasyfikacja deterministyczna) → B5 (klasyfikacja AI) → B6 (podobieństwo
treści) → B7 (plan) → B8 (walidacja) → B9 (przegląd) → B10 (apply) → B11
(verify). B4 nie istnieje, B12–B13 są nadal do implementacji.

## Studio — lokalny warsztat nad indeksem

Ten sam proces co wyżej, tylko w przeglądarce: pulpit przedmiotów, kolejka decyzji
z podglądem dokumentu, porównywarka klastrów, historia i statystyki na żywo.

> **Przewodnik — `studio/README.md`**: start, zakładki, klawiatura, API i model
> bezpieczeństwa. Plan i uzasadnienia: `studio/PLAN.md`, stan prac:
> `studio/TODO-studio.md`.

Studio nie jest drugim potokiem — woła ten sam kod i pisze do tej samej bazy co
komendy `just`. Zapisuje **wyłącznie decyzje**; materiały rusza tylko `apply`.

```bash
just studio-build     # front do postaci, którą serwuje `just studio`
just studio           # http://127.0.0.1:8765 — API + zbudowany front
just studio-dev       # praca nad widokiem: backend --reload + Vite z proxy na /api
just studio --check   # preflight: adres i baza, bez zajmowania portu
```

Serwer nasłuchuje **wyłącznie na pętli zwrotnej**: adres spoza `127.0.0.0/8`/`::1`
to odmowa startu z kodem 2, nie ostrzeżenie (`just studio --host 0.0.0.0` nie
wystartuje). Na tym założeniu stoi decyzja, że studio nie ma kont ani autoryzacji —
dlatego bramka ma własny test i własną mutację (`tests/mutations/studio-loopback-only.yaml`).

Liczby w widoku pochodzą z tego samego kodu co `just status`: `/api/subjects` woła
`status_report.collect`, a nie własne zapytania. Front niczego nie przelicza
(`studio/AGENTS.md`, reguła 1).

## Układ

```
paczka-tools/organizer/          # ← tu odpalasz `just claude` lub `just codex`
├── AGENTS.md  CLAUDE.md  GEMINI.md  # zasady wspólne + adaptery Claude/muxer/Gemini
├── .agents/                     # wspólne hooki + symlinki skills dla Codexa
├── ../.codex/                   # hook, ustawienia multi-agent i role Codexa
├── README.md  SKILLS.md  pyproject.toml  # metadane, zależności i konfiguracja pytest
├── .claude/                     # commitowane: settings.json, hooks/guard-sources.py,
│                                #   agents/ (5 z VoltAgent), skills/ (organizer-*),
│                                #   statuslines/statusline.sh
├── docs/                        # ARCHITEKTURA, CLI, ORGANIZACJA, PIPELINE, SYNAPSE,
│                                #   TESTY, AGENCI, INSTALACJA
├── config/                      # paths.yaml, subjects.yaml, syntax.yaml, thresholds.yaml
├── prompts/                     # prompty AI (classify_ambiguous, relate_cluster)
├── scripts/                     # etapy pipeline (Python)
├── studio/                      # lokalny warsztat nad indeksem: api/ (FastAPI) + web/ (Svelte)
│   └── graf/                    #   źródła synapse (generator .NET + viewer) — fork jednokierunkowy
├── tests/                       # unit/, studio/, cli/, synapse/, e2e/, mutations/ (YAML), fixtures/
├── reports/                     # SOURCES_TREE.md, inventory, plany, handoff (w gicie)
│   ├── bootstrap/                #   historyczne raporty wstępne
│   └── historia/                 #   zamknięte decyzje i oceny (poza bieżącym TODO)
└── setup/                       # install.sh, PLUGINS.md, requirements.txt, agent/ (narzędzia agentów)
```

## Agenci interaktywni

`just claude` i `just codex` uruchamiają sesje koordynatora i GPT nad tym
repo — launcher, tryby zapisu, które konto wykonuje pracę AI pipeline'u
i dlaczego `--ignore-user-config` jest zakazane, opisuje
[`docs/AGENCI.md`](docs/AGENCI.md).

## Zależności

Instalację robi jeden idempotentny skrypt (`bash setup/install.sh --with-apt`);
narzędzia systemowe, zależności Pythona (źródło prawdy: `pyproject.toml`)
i co robić ręcznie, gdy skrypt nie wystarczy — w [`docs/INSTALACJA.md`](docs/INSTALACJA.md).
