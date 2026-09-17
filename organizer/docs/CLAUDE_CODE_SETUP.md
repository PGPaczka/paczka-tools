# Claude Code pod organizację materiałów — ocena 4 repo + rekomendowana konfiguracja

> Kontekst: plan Pro + ~$75 kredytów extra usage (wygasają za kilka dni). Cel: **Fable jako koordynator**, a research/edycję materiałów wykonują tańsze modele (Haiku/Sonnet, Opus tylko gdy trzeba), żeby nie spalić kredytów naraz. Praca przez Claude Code w repo/folderze.
>
> ✅ Dopasowane do planu **„Paczka Organizer v2"**: to realny projekt programistyczny — pipeline w Pythonie (`scan→hash→dedup→extract→classify→plan→apply→verify`), baza SQLite, wykrywanie duplikatów (sha256 / normalized_text_hash / simhash / phash), integracja LLM przez cienki `llm_client.py` z wymiennymi backendami, automatyzacja `gh` (PR/issue per przedmiot), generator grafu pod `synapse`. To zmienia rekomendację: agenty **kodowe** z VoltAgent są tu jak najbardziej na miejscu, a warstwy muxera mapują się 1:1 na etapy pipeline'u.

---

## Kluczowa mechanika kosztów (dlaczego to w ogóle działa)

Na planie **Pro**:
- **Fable** — dostępny **wyłącznie z kredytów** ($75). Każdy token Fable'a schodzi z puli.
- **Opus / Sonnet / Haiku** — **wliczone w normalny limit Pro** (dopiero po jego przekroczeniu sięgają po kredyty).

Wniosek, który zmienia wszystko: jeśli Fable tylko **koordynuje** (cienka warstwa decyzji), a całą objętościową robotę — czytanie, grepowanie, pisanie, edycję — robią Sonnet/Haiku, to **$75 starcza bardzo długo**, bo Fable przerabia mało tokenów. Gros pracy leci z Twojego zwykłego limitu Pro. To jest cały sens tej układanki.

Drugi filar: **kontekst Fable'a trzymany chudy**. Nawet jako koordynator Fable „widzi" wszystko, co subagenci mu zwrócą — więc subagenci muszą oddawać **zwięzłe podsumowania, nie surowe pliki**, inaczej bulk treści wpada w kontekst Fable'a po jego stawce.

### ⚠️ Pułapka: masz DWIE różne pule, a Twój plan (pkt 16) używa obu

Twój `llm_client.py` ma wymienne backendy — i od backendu zależy, **z czego** płacisz:

| Backend w `llm_client.py` | Z jakiej puli schodzi | Uwagi |
|---|---|---|
| Interaktywny Claude Code / `claude -p` (headless) | **Subskrypcja Pro** (Fable = z $75 kredytów extra usage) | To jest miejsce, gdzie realnie wydasz $75 — ale tylko warstwa Fable. |
| `anthropic` (Messages API z Pythona) | **Kredyty API w Console** (osobna pula!) | **NIE dotyka $75.** To zupełnie inne konto. |
| `openai` / `codex exec` | konto OpenAI | inne konto. |

**Konsekwencja dla Ciebie:** masowa klasyfikacja `classify_one` (setki tanich wywołań), którą plan słusznie chce puścić headless/API — jeśli poleci przez `anthropic` API, **nie ruszy Twoich $75 w ogóle**. Żeby wydać te kredyty, spalasz je na **warstwie Fable w interaktywnym Claude Code**: projektowanie pipeline'u, schematu, orkiestracja, trudne `relate_cluster`, decyzje architektoniczne. Czyli: $75 idzie na **budowę i nadzór narzędzia**, a nie na wysokowolumenowe klasyfikacje (te rób taniej, z Pro albo API).

---

## Ocena 4 repo: jak użyć + wpływ na sesję i kredyty

### 1. DangerousYams/muxer — silnik kosztowy (rdzeń) ⭐~4
**Co to:** plugin do Claude Code robiący **dokładnie** Twój wzorzec — drogi model prowadzi sesję, tańsze wykonują. Ma gotowe warstwy:
- `muxer:scout` (Haiku) — eksploracja i streszczanie,
- `muxer:writer` (Sonnet) — dokumentacja, boilerplate,
- `muxer:builder` (Opus) — implementacja, debugging,
- `muxer:reviewer` (Opus) — weryfikacja,
- `muxer:oracle` (Fable) — eskalacja do trudnych decyzji.
Plus: **hook** wstrzykujący politykę routingu, **PreToolUse guard** który łapie wbudowane subagenty (Explore/Plan) i nie pozwala im dziedziczyć modelu sesji, oraz **raport kosztów** (estymata przed + „paragon" po, liczony względem scenariusza „wszystko na modelu sesji").

**Jak użyć:**
```bash
git clone https://github.com/DangerousYams/muxer
claude plugin marketplace add ./muxer
# w settings/env:
#   MUXER_GUARD=1        (guard na wbudowane subagenty)
#   MUXER_REPORT=1       (raport kosztów)
#   MUXER_REPORT_MIN_USD=... (próg raportowania)
```
Delegatów zewnętrznych (`muxer:codex`, `muxer:gemini`) **pomiń** — wymagają osobnych kluczy API OpenAI/Google, do Twojego celu niepotrzebne.

**Wpływ na sesję:** ⭐ największy pozytywny na spalanie kredytów — to jedyne z tych repo, które realnie egzekwuje „Fable koordynuje, tanie wykonują", i jeszcze pokazuje oszczędność liczbowo. `oracle=Fable` idealnie pasuje: to cienka warstwa eskalacji, którą karmisz z $75.
**Ryzyko:** bardzo świeży projekt (~4⭐), eksperymentalny. Hook + guard dokładają drobny narzut na turę. **Przejrzyj kod hooków przed zaufaniem mu z kredytami.** Zacznij od małego, testowego zadania i sprawdź raport.

---

### 2. VoltAgent/awesome-claude-code-subagents — biblioteka agentów ⭐~23k
**Co to:** 154+ gotowych subagentów w 10 kategoriach (Core Dev, Language Specialists, Infra, Quality & Security, Data & AI, **Research & Analysis**, Meta & Orchestration, …). Każdy to plik markdown z frontmatterem, w tym pole **`model:`** (Opus/Sonnet/Haiku). Instalacja: marketplace pluginów, albo ręczne kopiowanie do `~/.claude/agents/` lub `.claude/agents/`, albo installer.

**Pod organizację materiałów istotne agenty:** `research-analyst`, `knowledge-synthesizer`, `documentation-engineer`, `readme-generator`, `scientific-literature-researcher`. Kodowe (language-specialists itd.) — **pomiń**, to nie Twój przypadek.

**Jak użyć:** zainstaluj **tylko** te kilka agentów, które faktycznie potrzebujesz, i **audytuj pole `model:`** — domyślnie część może być na Opusie; zejdź na Haiku (czytanie/research) i Sonnet (pisanie).

**Wpływ na sesję:** same pliki agentów **nie palą tokenów** (to definicje na dysku). Zysk pojawia się, gdy używasz ich do ciężkiego czytania w **izolowanych kontekstach** — bulk treści nie dotyka wtedy kontekstu Fable'a. Instalowanie wszystkich 154 to niepotrzebny narzut na wykrywanie/opisy — **bierz minimum.**
**Ryzyko:** domyślne przypisania modeli bywają zbyt „drogie" — bez audytu `model:` możesz nieświadomie puszczać research na Opusie.

---

### 3. centminmod/my-claude-code-setup — higiena kontekstu + tracking ⭐~2.5k
**Co to:** starter z **memory bankiem CLAUDE.md** (3 szablony: ~101 / ~153 / ~105 linii, wg best practices Anthropic), plus `.claude/` (settings, rules, skills, agenty), custom komendy (`/security-audit`, `/refactor-code`), **status line z licznikiem tokenów i kosztów** oraz MCP do metryk zużycia i eksport metryk sesji do HTML.

**Jak użyć:** skopiuj `.claude/`, wybierz **jeden** szablon CLAUDE.md, odpal `/init`. Wywal to, czego nie używasz (Cloudflare/Convex/Notion) — inaczej niepotrzebnie puchnie kontekst.

**Wpływ na sesję:** dwojaki. (+) Memory bank pozwala nie tłumaczyć kontekstu od nowa co sesję → mniej rozdętego kontekstu koordynatora; status line + MCP metryk dają Ci **podgląd spalania na żywo** (bezcenne przy 5 dniach na kredyty). (−) Sam szablon to **stały koszt** ~100–150 linii ładowanych co sesję do kontekstu Fable'a. Netto dodatnie, jeśli realnie korzystasz z memory banku; inaczej to tylko narzut.
**Ryzyko:** opiniotwórczy i „nadmiarowy" — trzeba przyciąć do swoich potrzeb.

---

### 4. shanraisshan/claude-code-best-practice — czysta wiedza ⭐~66k
**Co to:** **dokumentacja/przewodnik**, nie instalowalny config. Pokrywa subagenty, komendy/skille/workflowy, memory (CLAUDE.md), model selection, **optymalizację kosztów i zarządzanie oknem kontekstu**, oraz wzorzec **Research → Plan → Execute → Review → Ship**. Ma runnable przykłady (np. `weather-orchestrator`).

**Jak użyć:** **czytać, nie instalować.** Przejrzyj sekcje o zarządzaniu kontekstem i orkiestracji, przenieś wzorce do swojego `CLAUDE.md`.

**Wpływ na sesję:** **zerowy** bezpośredni — nic nie ładujesz. Czysty zysk wiedzy, brak kosztu tokenów. Punkt odniesienia dla dobrych nawyków.

---

## Rekomendowany pakiet pod „Paczka Organizer"

Zasada: **minimum ruchomych części**, żeby nie tworzyć konfliktów i nie puchnąć kontekstu.

| Warstwa | Co bierzesz | Po co |
|---|---|---|
| **Silnik kosztowy (rdzeń)** | **muxer** | Egzekwuje Fable-koordynuje / tanie-wykonują + raport oszczędności. Serce układu — jego tiery mapują się na Twój pipeline. |
| **Agenty budujące pipeline** | z **VoltAgent** kategoria Core Dev / Language: `python-pro` (lub `backend-developer`), `sql-pro`/database, `test-automator` — pinned: Sonnet, cięższe Opus | Piszą deterministyczne skrypty, schemat SQLite, testy dedup/hashy. To realna robota kodowa Twojego planu. |
| **Agenty treściowe** | z **VoltAgent**: `documentation-engineer`, `readme-generator` (pinned: Haiku/Sonnet) | Generatory `STATUS.md`, per-przedmiot `README`, provenance, notatki `.md` pod `synapse` (pkt 13, 17). |
| **Higiena kontekstu + tracking** | **centminmod**: jeden szablon CLAUDE.md + status line kosztów + MCP metryk | Chudy kontekst koordynatora + **podgląd spalania $75 na żywo** (kluczowe przy 5 dniach). |
| **Referencja** | **shanraisshan** (tylko czytać) | Wzorzec **Research→Plan→Execute→Review→Ship** — pokrywa się z Twoim plan→gate→apply. Przenieś do `CLAUDE.md`/`AGENTS.md`. |

### Mapowanie warstw muxera na Twój pipeline

| Etap pipeline (z planu) | Kto to robi | Model | Pula |
|---|---|---|---|
| Projekt schematu SQLite, architektura, `AGENTS.md` | **koordynator** | **Fable** | **$75** (cienko, wartościowo) |
| Trudne `relate_cluster`, decyzje „outdated" (semantyczne, pkt 11) | `muxer:oracle` / koordynator | **Fable** | **$75** |
| Pisanie skryptów `scan/hash/dedup/extract/plan/apply/verify` | `muxer:builder` + `python-pro` | **Opus** | limit Pro |
| `classify_one` masowo (setki wywołań, pkt 16) | **poza sesją**: `anthropic` API / `claude -p` | Haiku/Sonnet | **API console** lub Pro — **nie $75** |
| Generatory README/STATUS/graf, boilerplate | `muxer:writer` + `documentation-engineer` | **Sonnet** | limit Pro |
| Eksploracja repo, streszczanie źródeł, grep | `muxer:scout` | **Haiku** | limit Pro |
| Review/weryfikacja planu (diff HTML) | `muxer:reviewer` | **Opus** | limit Pro |

Sedno: **Fable dotyka tylko architektury i najtrudniejszych decyzji** — reszta jedzie z limitu Pro lub osobnych pul. Tak $75 starczy na całą fazę projektowania i nadzoru, a nie spali się na jednym `apply`.

**Dlaczego taki dobór:** muxer realizuje rdzeń (koordynacja + routing + raport). VoltAgent dokłada **konkretnie kodowe** ręce do zbudowania pipeline'u (Python + SQLite + testy) i generatory dokumentacji/grafu — bo Twój plan to w 80% pisanie deterministycznego software'u. centminmod pilnuje chudego kontekstu i **pokazuje zużycie**. shanraisshan to wiedza, nie obciążenie.

### Kolejność wdrożenia (bez marnowania kredytów)
1. **Najpierw sam muxer** na małym teście (np. „zaprojektuj `CREATE TABLE` dla `files`+`content`"). Włącz `MUXER_REPORT=1`, sprawdź w raporcie, czy Fable faktycznie tylko koordynuje, a Opus/Sonnet piszą.
2. **Dodaj `CLAUDE.md` + `AGENTS.md`** (szablon centminmod, przycięty) z regułami z Twojego planu: *agent nie dotyka filesystemu poza `apply`* (pkt 14), *koordynator deleguje i wymaga zwięzłych zwrotów*, *człowiek = bramka raz na przedmiot*.
3. **Dołóż 2–4 agenty VoltAgent** (python/sql/test + documentation), każdemu ustaw `model:` wg tabeli wyżej. Nie instaluj całych 154 — tylko te.
4. **Wynieś masową klasyfikację poza sesję** — `classify_one` przez `llm_client.py` z backendem API/`claude -p` na Haiku. To świadomie **omija Fable**, żeby nie palić $75 na wolumenie.
5. **Nie ruszaj** delegatów zewnętrznych muxera (codex/gemini), chyba że i tak chcesz być multi-model per plan (wtedy tylko jako backend w `llm_client.py`, nie w sesji Fable).

### Na co uważać
- **Konflikt agentów:** muxer ma własne `scout/writer/builder/reviewer`. Dokładając VoltAgent, pilnuj, żeby nie kolidowały nazwami i żeby guard/polityka muxera nad nimi panowały. Zacznij od built-inów muxera; VoltAgent dodawaj punktowo tam, gdzie potrzebujesz specjalizacji (np. `sql-pro`).
- **Audyt `model:`** w każdym dodanym agencie — VoltAgent bywa Opus-heavy; zejdź na Sonnet/Haiku gdzie się da.
- **Świeżość muxera** (~4⭐): przejrzyj kod hooków, testuj na małym, zanim rzucisz na to realną robotę z kredytami.
- **Dwie pule** (patrz sekcja „Pułapka"): jeśli chcesz REALNIE wydać $75 — rób architekturę i orkiestrację w interaktywnym Claude Code na Fable. Jeśli przypadkiem wszystko puścisz przez API, $75 zostanie nietknięte.
- **Limit Pro:** workery (Sonnet/Haiku/Opus) idą z limitu Pro; po jego przekroczeniu też sięgną po kredyty. Status line centminmod ostrzeże.

---

## Sensowne następne kroki (gdy dasz zielone światło)
Zgodnie z Twoim planem (pkt 14 — jeszcze bez skryptów/promptów), mogę przygotować:
1. Gotowy `CLAUDE.md` + `AGENTS.md` z regułami delegacji i bramką „agent nie tyka FS poza `apply`", pod Fable-koordynatora.
2. Gotowy `settings.json`: env muxera (`MUXER_GUARD`, `MUXER_REPORT`) + `CLAUDE_CODE_SUBAGENT_MODEL` jako default, + nadpisane `Explore`/`Plan`.
3. Konkretną listę agentów VoltAgent do zainstalowania (nazwy + `model:`), dopasowaną do etapów pipeline'u.
4. Szkielet `llm_client.py` z wymiennymi backendami (świadomie oddzielający wolumen od $75).

Powiedz, od którego zacząć.
