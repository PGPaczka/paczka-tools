● Created CLAUDE.md. This repo isn't a normal codebase — it's a Claude Design
  handoff bundle: a single .dc.html prototype (SynapseVariants.dc.html) of a
  note-graph app called "Synapse," plus its generated runtime (support.js).
  There's no build/lint/test tooling to document since nothing here is built
  yet.

  The file covers: the handoff-bundle nature and README's instructions, the
  .dc.html template syntax ({{ }}, sc-if, sc-for, the Component extends DCLogic
  script block), and the app's actual architecture (views, layouts,
  skins/themes, note data model) so a future agent can jump straight to
  implementing without re-deriving all of that from the 1770-line file.

✻ Cooked for 1m 5s

❯ # Synapse — brief architektoniczny (web-app na headless RPi 5)                
                                                                                
  Dokument dla Claude Code. Cel: przepisać prototyp `SynapseVariants_dc.html`   
  (DCLogic)                                                                     
  na samodzielną aplikację webową serwowaną z headless Raspberry Pi 5,          
  wyświetlającą graf                                                            
  powiązań między notatkami vaulta. Prototyp definiuje **wygląd i zakres        
  funkcji**; dane pochodzą                                                      
  z realnego vaulta zsynchronizowanego przez git.                               
                                                                                
  **To NIE jest wtyczka Obsidian.** Headless RPi nie uruchamia GUI Obsidiana,   
  więc API Obsidiana                                                            
  (`ItemView`, `metadataCache`, `resolvedLinks`, `MarkdownRenderer`) jest       
  niedostępne. Rozwiązywanie                                                    
  linków, parsowanie frontmattera i renderowanie markdown dostarczamy sami.     
                                                                                
  ---                                                                           
                                                                                
  ## 0. Zasada nadrzędna: zero kodu na nową notatkę                             
                                                                                
  Prototyp trzyma wszystko w `seedNotes()`. W wersji docelowej **żadna          
  informacja o notatce nie żyje                                                 
  w kodzie**. Wymóg realizują trzy nogi:                                        
                                                                                
  1. **Dane z vaulta, nie z kodu** — generator czyta katalog `.md` z checkoutu  
  gita.                                                                         
  2. **Przebudowa na push** — git hook `post-receive` na RPi robi checkout i    
  odpala generator;                                                             
     nowy plik → nowy węzeł, automatycznie.                                     
  3. **Mapowanie frontmattera jest konfiguracją** — które klucze YAML mapują    
  się na                                                                        
     `category/level/status/tags` to ustawienie generatora, nie stała w kodzie. 
  Inny vault z inną                                                             
     konwencją działa bez rekompilacji.                                         
                                                                                
  Definicja ukończenia MVP: `git push` z notatką → po sekundach węzeł jest w    
  grafie z właściwą                                                             
  kategorią/kolorem/linkami, **bez zmian w kodzie i bez restartu ręcznego**.    
                                                                                
  ---                                                                           
                                                                                
  ## 1. Kształt systemu: dwa artefakty + jeden kontrakt                         
                                                                                
  ```                                                                           
     [urządzenia z Obsidianem]                      [Raspberry Pi 5, headless]  
     PC / telefon  --- git push --->  bare repo  --post-receive-->  checkout    
  vaulta (.md)                                                                  
          \                                                              |      
           \--- CouchDB LiveSync (edycja między urządzeniami) --\        v      
                                                                 |   Generator  
  C#  (Synapse.Generator)                                                       
     CouchDB NIE jest źródłem dla aplikacji.                     |   czyta      
  vault -> graph.json                                                           
     Trzyma pochunkowaną bazę, nie pliki .md.                    |        |     
                                                                 |        v     
                            [przeglądarka] <--- Caddy (static) --+--- Viewer    
  Svelte (SPA) + graph.json                                                     
  ```                                                                           
                                                                                
  - **Źródło prawdy dla aplikacji: gitowy checkout na RPi.** (Ustalone — nie    
  CouchDB. CouchDB LiveSync                                                     
    trzyma pochunkowaną, potencjalnie szyfrowaną bazę, nie pliki; zostaje do    
  synchronizacji edycji                                                         
    między twoimi urządzeniami                                                  
  ──── (165 lines hidden) ───────────────────────────────────────────────────── 
  ę homelabu.                                                                   
                                                                                
  ---                                                                           
                                                                                
  ## 9. Co WYRZUCIĆ z prototypu                                                 
                                                                                
  - `seedNotes()` — całość (dane z vaulta przez generator).                     
  - `mdRender`, `inline`, `hl`, `esc` — zastąpione `markdown-it` +              
  `highlight.js` w viewerze.                                                    
  - Render SVG głównego grafu (`graphEl`) — zastąpiony `CanvasGraphRenderer`.   
  - Cały system skórek (5×2) i przełącznik motywu — jeden motyw.                
  - Inline'owane style jako stringi — do `theme.css` + zmienne CSS.             
                                                                                
  Zachować jako referencję zachowania: `step()` (parametry fizyki i anchoring   
  kategorii),                                                                   
  `categoryAnchors`, `fitView`, `toWorld`, logika Venna/donuta/heatmapy, layout 
  paneli.                                                                       
                                                                                
  ---                                                                           
                                                                                
  ## 10. Flagi ryzyka                                                           
                                                                                
  - **Wydajność renderowania**: SVG per-węzeł pęka ~300-500 węzłów → Canvas od  
  startu. (Interfejs                                                            
    renderera zostawia drogę do PixiJS/WebGL dla bardzo dużych vaultów.)        
  - **Rozwiązywanie linków po twojej stronie**: `[[cel]]` może pasować          
  niejednoznacznie (dwa pliki                                                   
    o tej nazwie w różnych folderach). Ustal regułę dopasowania (ścieżka >      
  nazwa > alias) i obsłuż                                                       
    kolizje deterministycznie.                                                  
  - **Schemat graph.json**: wersjonuj (`schemaVersion`), by generator i viewer  
  nie rozjechały się cicho.                                                     
  - **CouchDB to nie źródło**: nie ulegnij pokusie czytania notatek z bazy      
  LiveSync — chunki                                                             
    i ewentualne E2E szyfrowanie to kruchy, drogi w utrzymaniu kierunek. Git    
  checkout jest kontraktem.                                                     
  - **Frontmatter opcjonalny/niespójny**: mapper odporny na braki; walidacja    
  miękka, nie twarde wyjątki.                                                   
                                                                                
  ---                                                                           
                                                                                
  ## 11. Kolejność implementacji (milestones)                                   
                                                                                
  1. **Kontrakt**: zdefiniuj schemat `graph.json` (`schemaVersion`,             
  nodes[Real|Ghost], edges) —                                                   
     to szew, ustalasz go pierwszy.                                             
  2. **Generator C# — rdzeń**: `VaultScanner` + `MarkdigParser` +               
  `WikiLinkExtractor` +                                                         
     `YamlFrontmatterReader` → surowe notatki. Testy na katalogu-fixture.       
  3. **Generator — graf**: `FrontmatterMapper` (konfigurowalny) +               
  `LinkResolver` (ghost-nody) +                                                 
     `GraphBuilder` + `JsonGraphSerializer` → działający `graph.json`.          
  4. **Viewer — domena + graf**: `GraphLoader` + `GraphModel` +                 
  `ForceSimulation` (d3-force) +                                                
     `CanvasGraphRenderer` + `Viewport` → żywy graf z Real i Ghost.             
  5. **Viewer — panele**: `DetailPanel` (+ markdown-it), `FilterPanel`,         
  `CommandPalette`, stores.                                                     
  6. **Wdrożenie**: bare repo + hook `post-receive` + Caddy → push zasila graf. 
  7. **Reszta widoków**: Dashboard/Venn/minimapa (SVG) + opcjonalny polling     
  ETag.                                                                         
                                                                                
  MVP osiągnięty, gdy: `git push` z nową notatką (z frontmatterem) → po         
  sekundach węzeł w grafie                                                      
  z właściwą kategorią/kolorem/linkami, ghost-nody dla nienapisanych celów,     
  **bez zmian w kodzie**.                                                       

● Explore(Extract prototype behavior to preserve)
  ⎿  Backgrounded agent (↓ to manage · ctrl+o to expand)

● User answered Claude's questions:
  ⎿  · The brief spans 7 milestones (schema → generator → viewer → panels → RPi 
     deployment). How much should this plan cover? → All 7 milestones
     · Where should the two new projects (Synapse.Generator in C#, 
     synapse-viewer in Svelte) live? → This repo, as subfolders
     · Do you have a real markdown vault to test the generator against, or 
     should the plan create a small fixture vault? → Create a fixture vault
     · For the Svelte viewer SPA, plain Svelte + Vite, or SvelteKit? → Svelte + 
     Vite

● Agent "Extract prototype behavior to preserve" finished · 2m 55s

● Plan(Design full Synapse rewrite implementation plan)
  ⎿  Backgrounded agent (↓ to manage · ctrl+o to expand)

❯ commituj zmiany jasymi commitami, tak żeby każdy commit stanowił działającą   
  całość! pisz testy do kodu, żeby móc weryfikować jego poprawność!             

● Noted — I'll build that into the plan: each milestone will be structured so it
  lands as one or more self-contained, working commits (build passes, tests
  pass) rather than a single giant change, and every non-trivial piece of logic
  (especially the pure Domain/domain layers) gets unit tests as part of that
  milestone's definition of done, not bolted on afterward. I'll also save this
  as a standing preference for future work once we're out of plan mode.

  The Plan agent is still working through the full 7-milestone design in the
  background — I'll continue once it reports back.

✻ Sautéed for 2m 43s

● Agent "Design full Synapse rewrite implementation plan" finished · 6m 25s

● User answered Claude's questions:
  ⎿  · The prototype has three chrome layouts (Classic top-bar, Rail side-nav, 
     Command). The brief only says to delete the 5-skin theme system — it 
     doesn't say which layout(s) to keep for the real app. Which should the plan
     target? → Keep all three
     · The plan recommends making DetailPanel read-only (no in-browser note 
     editing) since the git checkout on the Pi is the source of truth and 
     there's no write path back into the vault. Does that match what you want? →
     Want editing eventually
     · The activity heatmap (dashboard) has no real data source yet — the 
     prototype's per-note activity dates are fake seed data, and per-note git 
     history isn't in the 7 milestones. How should Milestone 7 handle it? → 
     Include now via git log

● Updated plan
  ⎿  /plan to preview  ⎿  User rejected Claude's plan:
     ╭─────────────────────────────────────────────────────────────────────────╮
     │ Synapse — rewrite plan (prototype → real app)                           │
     │                                                                         │
     │ Context                                                                 │
     │                                                                         │
     │ /home/billy/dev/synapse currently holds only a Claude-Design handoff    │
     │ bundle: SynapseVariants.dc.html (a 1773-line prototype of "Synapse," a  │
     │ note-graph knowledge-vault viewer, populated with fake hardcoded data)  │
     │ and its runtime support.js. The prototype defines the look and feature  │
     │ scope the user wants; it is not code to be lifted — it's a spec to      │
     │ reimplement against a real markdown vault.                              │
     │                                                                         │
     │ The user wants two decoupled, real artifacts, driven by a git-push      │
     │ workflow on a headless Raspberry Pi 5 (no GUI, so Obsidian's own plugin │
     │ APIs are unavailable — link resolution, frontmatter parsing, and        │
     │ markdown rendering must all be built from scratch):                     │
     │                                                                         │
     │ 1. Synapse.Generator (C#) — reads a markdown vault checked out on the   │
     │ Pi, resolves [[wikilinks]] into a graph (with ghost nodes for links     │
     │ that don't resolve to a real note), and emits a single versioned        │
     │ graph.json. Runs only on git push (via a post-receive hook), not        │
     │ always-on — the Pi co-hosts other services (e.g. a Minecraft server)    │
     │ and idle load must stay near zero.                                      │
     │ 2. synapse-viewer (Svelte + Vite SPA) — loads graph.json client-side    │
     │ and renders the graph (Canvas + d3-force), cards/dashboard/venn views,  │
     │ a note detail panel, filters, and a command palette. One theme only     │
     │ (the prototype's 5-skin system is deleted); all three chrome layouts    │
     │ (Classic/Rail/Command) are kept.                                        │
     │                                                                         │
     │ graph.json is the only contract between them. Both projects live as     │
     │ subfolders of this repo. No real vault exists yet, so a small fixture   │
     │ vault (checked into the generator's tests) stands in for one throughout │
     │ development.                                                            │
     │                                                                         │
     │ Core principle carried through every milestone: Domain/ (C#) and        │
     │ domain/ (TS) are pure — zero IO, zero framework imports, unit-testable  │
     │ in isolation. Config (frontmatter→field mapping, category colors)       │
     │ drives behavior instead of hardcoded branches, so a                     │
     │ differently-conventioned vault or a new category needs a config edit,   │
     │ not a recompile.                                                        │
     │                                                                         │
     │ Confirmed scope decisions (from user Q&A):                              │
     │ - Keep all three chrome layouts (Classic/Rail/Command), not just one.   │
     │ - DetailPanel is read-only for this plan, but component boundaries must │
     │ leave room for a future write-back path (edits synced via               │
     │ Obsidian/CouchDB today; no write path from the viewer yet — don't       │
     │ design against that assumption permanently).                            │
     │ - The activity heatmap ships now, backed by real git log history per    │
     │ note (not deferred) — this adds a history: string[] field to real nodes │
     │ and a new git-log-reading component to the generator.                   │
     │                                                                         │
     │ Commit & test discipline (explicit user instruction — applies to all    │
     │ milestones): implement in small commits, each of which leaves the repo  │
     │ in a working, buildable, test-passing state — never a commit that       │
     │ doesn't compile or breaks existing tests. Every non-trivial unit of     │
     │ logic, especially anything in Domain//domain/, gets a unit test in the  │
     │ same commit (or immediately following) that introduces it, not bolted   │
     │ on later. Milestones below are already broken into stage-sized          │
     │ deliverables for this reason — treat each bullet list of files as       │
     │ roughly one commit's worth of work, not one milestone = one commit.     │
     │                                                                         │
     │ ---                                                                     │
     │ Milestone 0 — Repo & tooling scaffolding                                │
     │                                                                         │
     │ No .sln/package.json exists yet; this creates the skeleton later        │
     │ milestones build on.                                                    │
     │                                                                         │
     │ Generator — /home/billy/dev/synapse/Synapse.Generator/                  │
     │ - Synapse.Generator.sln, Synapse.Generator/Synapse.Generator.csproj     │
     │ (console app, current .NET LTS, nullable+implicit usings enabled;       │
     │ NuGet: Markdig, YamlDotNet; JSON via System.Text.Json)                  │
     │ - Synapse.Generator.Tests/Synapse.Generator.Tests.csproj (xUnit +       │
     │ FluentAssertions)                                                       │
     │ - .editorconfig, .gitignore (bin/, obj/, publish/)                      │
     │                                                                         │
     │ Viewer — /home/billy/dev/synapse/synapse-viewer/                        │
     │ - Scaffold via npm create vite@latest -- --template svelte-ts           │
     │ - Deps: d3-force, d3-quadtree, markdown-it, highlight.js,               │
     │ @types/markdown-it; dev deps: vitest, jsdom                             │
     │ - .gitignore (node_modules/, dist/)                                     │
     │                                                                         │
     │ Done: dotnet build and npm run build both succeed empty; dotnet test /  │
     │ npm run test both run green with 0 tests.                               │
     │                                                                         │
     │ ---                                                                     │
     │ Milestone 1 — Contract: graph.json schema                               │
     │                                                                         │
     │ Locked down first since both sides build against it independently.      │
     │                                                                         │
     │ Files: /home/billy/dev/synapse/schema/graph.schema.v1.json (JSON Schema │
     │ draft-07), /home/billy/dev/synapse/schema/graph-schema.md (field docs   │
     │ + one real-node + one ghost-node example).                              │
     │                                                                         │
     │ Shape:                                                                  │
     │ {                                                                       │
     │   "schemaVersion": 1,                                                   │
     │   "generatedAt": "2026-08-03T21:14:02Z",                                │
     │   "vault": { "name": "informatyka", "notesCount": 21, "ghostCount": 3,  │
     │ "orphanCount": 2 },                                                     │
     │   "nodes": [                                                            │
     │     {                                                                   │
     │       "id": "docker-basics", "kind": "real", "title": "Docker Basics",  │
     │       "path": "devops/docker-basics.md", "category": "DevOps", "level": │
     │ 1,                                                                      │
     │       "status": "completed", "tags": ["containers", "cli"], "aliases":  │
     │ [],                                                                     │
     │       "modified": "2026-06-10", "excerpt": "...", "wordCount": 138,     │
     │       "history": ["2026-04-02", "2026-05-18", "2026-06-10"]             │
     │     },                                                                  │
     │     { "id": "kubernetes-advanced", "kind": "ghost", "title":            │
     │ "kubernetes-advanced",                                                  │
     │       "referencedBy": ["docker-networking", "kubernetes-intro"],        │
     │ "referenceCount": 2 }                                                   │
     │   ],                                                                    │
     │   "edges": [                                                            │
     │     { "source": "docker-basics", "target": "linux-fundamentals",        │
     │ "linkText": "linux-fundamentals" }                                      │
     │   ],                                                                    │
     │   "warnings": [                                                         │
     │     { "kind": "ambiguous-link", "noteId": "docker-networking",          │
     │ "linkText": "docker", "resolvedTo": "docker-basics" }                   │
     │   ]                                                                     │
     │ }                                                                       │
     │                                                                         │
     │ Design decisions to lock in now:                                        │
     │ - One polymorphic nodes[] array with a kind: "real"|"ghost"             │
     │ discriminant (not two parallel arrays). Ghost nodes carry only          │
     │ id/kind/title/referencedBy/referenceCount.                              │
     │ - Missing optional frontmatter degrades gracefully, never throws:       │
     │ category→"Uncategorized", level/status→null, tags/aliases→[].           │
     │ - Real node id = filename stem, matched case-insensitively during       │
     │ resolution but displayed with original casing. Ghost id =               │
     │ trimmed/collapsed/lower-cased raw link target text (dedup key — this is │
     │ new logic, no prototype precedent).                                     │
     │ - Edge direction: source = the note containing the [[wikilink]], target │
     │ = the resolved note/ghost. This is not the prototype's level-based      │
     │ reordering (its edges() pointed prereq→dependent using a curated links  │
     │ field) — real wikilinks have no reliable directional semantic to invert │
     │ on, so "backlinks" and "outgoing" in the real app simply mean "edges    │
     │ where I'm target" vs "where I'm source."                                │
     │ - edges[].linkText carries the raw wikilink text (including             │
     │ |alias/#heading) so the viewer's markdown-it plugin can map a rendered  │
     │ [[...]] span back to its resolved edge without re-implementing          │
     │ resolution rules in TypeScript.                                         │
     │ - warnings[]: non-fatal generator concerns (ambiguous resolution,       │
     │ duplicate ids) — pipeline never fails the build over vault hygiene, but │
     │ issues stay visible.                                                    │
     │ - Versioning policy: schemaVersion is a bare integer; viewer does hard  │
     │ equality check, mismatch → blocking "regenerate graph.json" message. No │
     │ migration machinery — single-operator tool, "just re-run the            │
     │ generator" is cheaper than versioned readers.                           │
     │ - Atomic write guarantee: generator writes to a temp file and renames   │
     │ over graph.json, never writes in place.                                 │
     │ - history: string[] on real nodes (yyyy-mm-dd, from git log) —          │
     │ optional/absent if git history isn't available for a note (e.g.         │
     │ untracked file at generation time).                                     │
     │                                                                         │
     │ Done: reviewed schema doc + JSON Schema file that Milestones 2/3 (C#    │
     │ DTOs) and Milestone 4 (TS types) build against without further          │
     │ negotiation.                                                            │
     │                                                                         │
     │ ---                                                                     │
     │ Milestone 2 — Generator core: scan → parse → extract, + fixture vault   │
     │                                                                         │
     │ Produces RawNotes from real files on disk — the only milestone touching │
     │ filesystem/Markdig/YamlDotNet before Milestone 3's pure Domain layer.   │
     │                                                                         │
     │ Fixture vault —                                                         │
     │ /home/billy/dev/synapse/Synapse.Generator.Tests/Fixtures/Vault/         │
     │                                                                         │
     │ Must itself be a git repository (not just files) since Milestone 3      │
     │ needs real git log output for the history feature — commit each fixture │
     │ file separately with staggered --date values so history has real,       │
     │ distinct dates to assert on.                                            │
     │                                                                         │
     │ File: docker-basics.md                                                  │
     │ Frontmatter: full                                                       │
     │ Scenario covered: plain resolved link [[linux-fundamentals]]            │
     │ ────────────────────────────────────────                                │
     │ File: dockerfile.md                                                     │
     │ Frontmatter: full                                                       │
     │ Scenario covered: resolved link [[docker-basics]]; link inside fenced   │
     │ code                                                                    │
     │ block must NOT be extracted                                             │
     │ ────────────────────────────────────────                                │
     │ File: docker-compose.md                                                 │
     │ Frontmatter: missing category                                           │
     │ Scenario covered: category → "Uncategorized" fallback                   │
     │ ────────────────────────────────────────                                │
     │ File: docker-networking.md                                              │
     │ Frontmatter: missing level                                              │
     │ Scenario covered: level → null fallback; links [[docker-compose]]       │
     │ ────────────────────────────────────────                                │
     │ File: linux-fundamentals.md                                             │
     │ Frontmatter: full, aliases: [Linux Basics]                              │
     │ Scenario covered: alias-resolution target                               │
     │ ────────────────────────────────────────                                │
     │ File: process-scheduling.md                                             │
     │ Frontmatter: full                                                       │
     │ Scenario covered: links [[Linux Basics]] → resolves via alias tier      │
     │ ────────────────────────────────────────                                │
     │ File: kubernetes-intro.md                                               │
     │ Frontmatter: full                                                       │
     │ Scenario covered: links [[Kubernetes Advanced|kubernetes-advanced]]     │
     │ (unresolved/ghost) + [[docker-compose#Scaling]] (heading-suffix)        │
     │ ────────────────────────────────────────                                │
     │ File: docker-volumes.md                                                 │
     │ Frontmatter: full                                                       │
     │ Scenario covered: second link to kubernetes-advanced → ghost dedup      │
     │ (referencedBy has both, referenceCount: 2)                              │
     │ ────────────────────────────────────────                                │
     │ File: vim-shortcuts.md                                                  │
     │ Frontmatter: full                                                       │
     │ Scenario covered: no links in/out → orphan fixture                      │
     │                                                                         │
     │ Files                                                                   │
     │                                                                         │
     │ Synapse.Generator/Domain/Notes/RawNote.cs, Domain/Links/WikiLinkRef.cs  │
     │ — pure records.                                                         │
     │                                                                         │
     │ Synapse.Generator/Scanning/IVaultScanner.cs / FileSystemVaultScanner.cs │
     │ — recursive *.md enumeration, skips dotfiles/.obsidian/.                │
     │                                                                         │
     │ Synapse.Generator/Parsing/                                              │
     │ - IFrontmatterReader.cs / YamlFrontmatterReader.cs — splits leading --- │
     │ YAML block, deserializes to a loosely-typed dict (no strong typing yet  │
     │ — Milestone 3's job).                                                   │
     │ - IMarkdownParser.cs / MarkdigNoteParser.cs — Markdig AST (also used to │
     │ identify fenced-code-block spans for the extractor, and later for       │
     │ excerpt/wordCount).                                                     │
     │ - WikiLinkExtractor.cs — new logic, no prototype precedent (prototype   │
     │ never parses body wikilinks). Regex \[\[([^\]]+)\]\] over raw markdown, │
     │ explicitly skipping spans identified as fenced-code-blocks via the      │
     │ Markdig AST first. Splits on # (heading) then | (alias).                │
     │                                                                         │
     │ Synapse.Generator/Git/IGitHistoryReader.cs / GitHistoryReader.cs —      │
     │ shells out to git log --follow --format=%ad --date=short -- <path>      │
     │ against the vault's git repo for each note file, returns date strings   │
     │ oldest→newest. Interface exists specifically so                         │
     │ Domain-layer/graph-building code depends on an abstraction (DIP) and so │
     │ tests can inject a fake reader instead of shelling out. On the Pi, the  │
     │ vault checkout is a git working tree tied to the bare repo              │
     │ (--git-dir=<bare> --work-tree=<checkout>), so this works there;         │
     │ document that requirement.                                              │
     │                                                                         │
     │ Testing                                                                 │
     │                                                                         │
     │ - Scanning/FileSystemVaultScannerTests.cs — 9 files found, correct      │
     │ relative paths.                                                         │
     │ - Parsing/YamlFrontmatterReaderTests.cs — correct dict per fixture,     │
     │ missing-field files simply lack the key.                                │
     │ - Parsing/WikiLinkExtractorTests.cs — dockerfile.md → 1 link (not the   │
     │ fenced one); kubernetes-intro.md → both pipe-alias and heading-fragment │
     │ forms split correctly; vim-shortcuts.md → 0.                            │
     │ - Git/GitHistoryReaderTests.cs — against the real fixture git repo,     │
     │ asserts correct staggered dates per file; a fake IGitHistoryReader is   │
     │ used everywhere else so unit tests don't depend on git being            │
     │ installed/available.                                                    │
     │                                                                         │
     │ Done: fixture vault → 9 RawNotes with correct raw frontmatter dicts,    │
     │ WikiLinkRef lists, and git history — verified by unit tests. No         │
     │ mapping/resolution/graph logic yet.                                     │
     │                                                                         │
     │ ---                                                                     │
     │ Milestone 3 — Generator graph: mapping, resolution, build, serialize    │
     │                                                                         │
     │ Where the pure Domain/ layer does its real work and graph.json is       │
     │ produced for the first time.                                            │
     │                                                                         │
     │ Files                                                                   │
     │                                                                         │
     │ Synapse.Generator/Configuration/GeneratorConfig.cs,                     │
     │ FrontmatterMapConfig.cs (which YAML key maps to                         │
     │ category/level/status/tags/aliases — config, not code) +                │
     │ generator.config.json (shipped default) +                               │
     │ Synapse.Generator.Tests/Fixtures/generator.config.json (matches fixture │
     │ vault's keys).                                                          │
     │                                                                         │
     │ Domain/Mapping/IFrontmatterMapper.cs, MappedFrontmatter.cs (defaults    │
     │ baked in once, here) → concrete                                         │
     │ Mapping/ConfigurableFrontmatterMapper.cs (handles tags-as-comma-string  │
     │ vs list vs single-scalar coercion explicitly and defensively — never    │
     │ silently mangles data, see Risks).                                      │
     │                                                                         │
     │ Domain/Resolution/ResolvedLink.cs, ILinkResolver.cs / LinkResolver.cs   │
     │ (in Resolution/ outside Domain if it needs IO; pure otherwise) —        │
     │ resolves each WikiLinkRef by trying, in order: (1) full relative-path   │
     │ match, (2) filename-stem match (case-insensitive), (3) alias match.     │
     │ First match wins; ambiguous within-tier matches resolve                 │
     │ first-scanned-wins + emit a warnings entry; no match →                  │
     │ Unresolved/ghost. New logic, no prototype precedent — needs its own     │
     │ dedicated tests.                                                        │
     │                                                                         │
     │ Domain/Graph/GraphNode.cs, GraphEdge.cs, KnowledgeGraph.cs (holds       │
     │ Adjacency()/OrphanIds() — this part does port directly from the         │
     │ prototype's adjacency()/orphanSet(), same "id→Set<id> map, orphan=empty │
     │ set" shape, just built from resolved wikilink edges instead of curated  │
     │ links), GraphBuilder.cs (pure orchestrator; dedups ghost targets by     │
     │ normalized id, accumulating referencedBy — new logic).                  │
     │                                                                         │
     │ Synapse.Generator/Serialization/GraphJsonDto.cs (+                      │
     │ Node/Edge/VaultMeta/Warning DTOs matching the schema exactly),          │
     │ IGraphSerializer.cs / JsonGraphSerializer.cs (deterministic ordering —  │
     │ nodes by id, edges by (source,target) — for stable, diffable,           │
     │ snapshot-testable output), atomic-write helper (temp file +             │
     │ File.Move(overwrite:true)).                                             │
     │                                                                         │
     │ Synapse.Generator/Pipeline/GeneratorPipeline.cs orchestrates all        │
     │ stages; Program.cs is the composition root (manual constructor          │
     │ injection, no DI container needed at this size).                        │
     │                                                                         │
     │ Testing                                                                 │
     │                                                                         │
     │ - Domain/Mapping/FrontmatterMapperTests.cs — table-driven               │
     │ default/coercion cases.                                                 │
     │ - Domain/Resolution/LinkResolverTests.cs — one test per fixture         │
     │ scenario (path/name/alias tier wins, unresolved→ghost).                 │
     │ - Domain/Graph/GraphBuilderTests.cs — fixture vault yields exactly 1    │
     │ ghost (kubernetes-advanced,                                             │
     │ referencedBy=[kubernetes-intro,docker-volumes], referenceCount=2);      │
     │ vim-shortcuts in orphan set.                                            │
     │ - EndToEnd/FixtureVaultGraphTests.cs — full pipeline run, validate      │
     │ output against graph.schema.v1.json, golden-file/snapshot assertion     │
     │ (deterministic ordering makes this stable).                             │
     │ - Publish smoke test here, not deferred: dotnet publish -r linux-arm64  │
     │ --self-contained -p:PublishSingleFile=true, run the actual published    │
     │ binary (not dotnet run) against the fixture vault once, to catch        │
     │ YamlDotNet/System.Text.Json reflection-vs-trimming breakage early.      │
     │                                                                         │
     │ Done (matches user's own milestone wording): fixture vault →            │
     │ graph.json, schema-valid, snapshot-asserted, ≥1 ghost node with correct │
     │ dedup, ≥1 orphan, correctly-defaulted missing frontmatter, real         │
     │ history dates populated.                                                │
     │                                                                         │
     │ ---                                                                     │
     │ Milestone 4 — Viewer domain + graph rendering                           │
     │                                                                         │
     │ Files                                                                   │
     │                                                                         │
     │ synapse-viewer/src/domain/graph/                                        │
     │ - GraphModel.ts — pure types (RealNode, GhostNode, GraphEdge) +         │
     │ fromDto().                                                              │
     │ - selectors.ts — visibleNodes(graph, filters), orphanIds(graph) (ports  │
     │ orphanSet()), backlinks(graph,id)/outgoing(graph,id) (new — sourced     │
     │ from resolved edges[], not a curated links[]).                          │
     │ - categoryAnchors.ts — near-verbatim port of categoryAnchors()          │
     │ (prototype: AR=min(vw,vh)*0.24, angle from 12 o'clock, evenly spaced by │
     │ category count).                                                        │
     │ - forceSimulation.ts — wraps d3-force. Not a literal port of the        │
     │ prototype's custom step() loop — re-expressed in d3-force's model:      │
     │ forceManyBody() (repulsion), forceLink(edges).distance(linkDist)        │
     │ (springs), a custom category-anchor force (via d3-force's               │
     │ force(alpha)/initialize(nodes) protocol, using categoryAnchors.ts),     │
     │ forceCollide(radius) (replacing the prototype's manual 3-iteration      │
     │ relaxation), center-pull term. Document in comments which prototype     │
     │ constant maps to which d3-force parameter to preserve the "feel."       │
     │                                                                         │
     │ synapse-viewer/src/domain/color/categoryColor.ts — new, no prototype    │
     │ precedent (prototype: fixed map + flat #888 fallback only).             │
     │ Deterministic string-hash→HSL/hex for any category without an explicit  │
     │ color. Precedence order (document this once, e.g. in a                  │
     │ color/README.md): generator config > user's localStorage override >     │
     │ hash fallback.                                                          │
     │                                                                         │
     │ synapse-viewer/src/data/GraphLoader.ts — fetch('graph.json'), hard      │
     │ schemaVersion equality check, DTO→GraphModel mapping, captures          │
     │ ETag/Last-Modified (used by Milestone 7's optional polling).            │
     │                                                                         │
     │ synapse-viewer/src/render/                                              │
     │ - IGraphRenderer.ts — mount/updatePositions/setViewport/hitTest/destroy │
     │ + hover/click event surface (LSP boundary — Canvas swappable for        │
     │ PixiJS/WebGL later).                                                    │
     │ - CanvasGraphRenderer.ts — ghost=dashed/hollow, real=filled by category │
     │ color with status-color border; positions read from a non-reactive      │
     │ buffer updated by the sim and pushed to stores only throttled (mirrors  │
     │ the prototype's this.sim kept off React state + forceUpdate() pattern). │
     │ - hitTesting.ts — new engineering (Canvas has no DOM event targets).    │
     │ d3-quadtree over current positions, queried on pointer events; z-order  │
     │ tie-break for overlapping nodes replicates the prototype's pri()        │
     │ (selected > hovered > default).                                         │
     │ - Viewport.ts — near-literal port of fitView() (bbox + 84px pad, scale  │
     │ clamp [0.4,1.35]), onWheel() (zoom-to-cursor, scale clamp [0.35,2.6]),  │
     │ toWorld(), and the drag/pan 4px click-vs-drag threshold.                │
     │                                                                         │
     │ synapse-viewer/src/components/graph/GraphCanvas.svelte — mounts         │
     │ renderer+viewport in onMount, global window-level mousemove/mouseup     │
     │ (drag continues outside canvas, matching the prototype), teardown in    │
     │ onDestroy.                                                              │
     │                                                                         │
     │ synapse-viewer/src/stores/graphStore.ts, selectionStore.ts — hold the   │
     │ loaded graph + selected/hovered id, not per-node reactive positions.    │
     │                                                                         │
     │ Testing                                                                 │
     │                                                                         │
     │ - categoryAnchors.test.ts — exact positions for N=1..7 categories.      │
     │ - selectors.test.ts — backlinks/outgoing/orphanIds against a hand-built │
     │ or Milestone-3 fixture graph.                                           │
     │ - categoryColor.test.ts — same string→same color; config/override       │
     │ precedence honored.                                                     │
     │ - Viewport.test.ts — pure math: fitView bbox/clamp, wheel               │
     │ zoom-to-cursor formula.                                                 │
     │ - hitTesting.test.ts — known positions/radii → expected id/null,        │
     │ including overlap tie-break.                                            │
     │ - Force sim: no exact-coordinate assertions (non-deterministic by       │
     │ nature, see Risks); unit-test the custom anchor force's per-tick        │
     │ contribution in isolation; rely on manual visual QA for overall         │
     │ settling.                                                               │
     │                                                                         │
     │ Done: fixture graph.json renders a live, interactive force-directed     │
     │ graph in the Vite dev server; ghost nodes visually distinct;            │
     │ pan/zoom/drag/click-to-select all work.                                 │
     │                                                                         │
     │ ---                                                                     │
     │ Milestone 5 — Viewer panels + layout chrome                             │
     │                                                                         │
     │ Files                                                                   │
     │                                                                         │
     │ synapse-viewer/src/markdown/                                            │
     │ - renderer.ts — markdown-it + highlight.js, floor matching the          │
     │ prototype's supported subset (h1/h2, single-line blockquote, unordered  │
     │ lists, fenced code+lang, bold, inline code), superseding the            │
     │ hand-rolled mdRender/hl/inline/esc.                                     │
     │ - wikilinkPlugin.ts — markdown-it inline rule for [[...]], functional   │
     │ not cosmetic (the one place behavior must differ from the prototype).   │
     │ Renders <a class="wikilink" data-linktext="...">; click resolves        │
     │ data-linktext against the current note's edges[].linkText from          │
     │ graph.json (avoids re-implementing C#'s resolution rules in TS).        │
     │                                                                         │
     │ synapse-viewer/src/components/detail/                                   │
     │ - DetailPanel.svelte — read-only for this plan; structure the component │
     │ so a future edit affordance (e.g. an EditPanel.svelte swapped in        │
     │ behind a capability flag) can be added later without a rewrite — but no │
     │ write path is built now.                                                │
     │ - MarkdownBody.svelte — renders via renderer.ts; wikilink clicks wired  │
     │ via event delegation (rendered HTML is injected via {@html}, so normal  │
     │ Svelte on:click bindings don't reach generated anchors — one delegated  │
     │ listener on the container, event.target.closest('.wikilink')). Confirm  │
     │ markdown-it's raw-HTML passthrough stays disabled.                      │
     │ - Backlinks/outgoing sections computed via domain/graph/selectors.ts    │
     │ from graph.json edges, not any per-note links field.                    │
     │                                                                         │
     │ synapse-viewer/src/components/filters/FilterPanel.svelte +              │
     │ stores/filterStore.ts — status/category/level/tag toggle state;         │
     │ selectors.visibleNodes(graph, filters).                                 │
     │                                                                         │
     │ synapse-viewer/src/domain/commandPalette/                               │
     │ - actionsRegistry.ts — data-driven {id,label,hint,icon,run}[] (OCP).    │
     │ Ports the prototype's 4 actions minus theme-toggle (dropped — one theme │
     │ only); "switch mode" iterates the Milestone 7 view-mode registry        │
     │ instead of a hardcoded graph⇄venn toggle; add a "switch layout" action  │
     │ iterating the new layout registry below.                                │
     │ - search.ts — pure substring filter, actions-then-notes, no fuzzy       │
     │ scoring (matches prototype semantics exactly).                          │
     │                                                                         │
     │ synapse-viewer/src/components/palette/CommandPalette.svelte —           │
     │ ⌘K/Ctrl+K, arrow-key nav, enter-to-run.                                 │
     │                                                                         │
     │ synapse-viewer/src/layout/ — new scope (all three chrome variants kept, │
     │ per user decision):                                                     │
     │ - layoutRegistry.ts — {id: 'classic'|'rail'|'command', label,           │
     │ component}[] (OCP, same registry pattern as views/actions).             │
     │ - components/layout/ClassicShell.svelte, RailShell.svelte,              │
     │ CommandShell.svelte — port the three chrome variants'                   │
     │ structure/behavior (top bar vs side rail vs command-first placement of  │
     │ search/palette-trigger, skin/theme switcher UI removed since one theme  │
     │ only). Each shell hosts the same GraphView/DetailPanel/FilterPanel      │
     │ content, differing only in chrome placement.                            │
     │ - stores/settingsStore.ts — adds layout alongside existing settings     │
     │ (repulsion/linkDist/minimap toggle/color overrides), persisted to       │
     │ localStorage.                                                           │
     │                                                                         │
     │ Testing                                                                 │
     │                                                                         │
     │ - search.test.ts — same shape as prototype: empty query → everything,   │
     │ actions precede notes.                                                  │
     │ - wikilinkPlugin.test.ts — [[Target]] / [[Target|Alias]] → correct      │
     │ data-linktext.                                                          │
     │ - selectors.test.ts (extends M4) — backlinks/outgoing against real      │
     │ fixture graph.json.                                                     │
     │ - Manual/component QA for FilterPanel/DetailPanel/each layout shell     │
     │ against the fixture graph.                                              │
     │                                                                         │
     │ Done: loading fixture graph.json, clicking a node opens DetailPanel     │
     │ with rendered markdown; clicking an in-body wikilink navigates (or      │
     │ shows a not-found state for ghosts); backlinks/outgoing match resolved  │
     │ edges; filters narrow the visible graph/cards; ⌘K works; all three      │
     │ layouts render and are switchable.                                      │
     │                                                                         │
     │ ---                                                                     │
     │ Milestone 6 — Deployment                                                │
     │                                                                         │
     │ Files                                                                   │
     │                                                                         │
     │ /home/billy/dev/synapse/deploy/                                         │
     │ - post-receive — on push: git --work-tree=<vault-checkout> checkout -f  │
     │ <ref>, invoke the published generator binary (--config <prod-config>    │
     │ --vault <checkout> --out <viewer-static-dir>/graph.json), log output,   │
     │ exit promptly (no daemon — satisfies near-zero-idle-load constraint).   │
     │ - generator.config.production.json — placeholder until the real vault's │
     │ frontmatter conventions are known.                                      │
     │ - Caddyfile — serves synapse-viewer's built dist/ (+ graph.json) behind │
     │ WireGuard/basic-auth, coexisting with other homelab service blocks.     │
     │ - README-deploy.md — bare-repo setup, hook install, first-push smoke    │
     │ test, binary/dist locations, a lock-file note for overlapping           │
     │ concurrent hook runs (see Risks).                                       │
     │                                                                         │
     │ Publish (documented, not new source): dotnet publish Synapse.Generator  │
     │ -c Release -r linux-arm64 --self-contained true                         │
     │ -p:PublishSingleFile=true -o publish/. PublishTrimmed flagged risky     │
     │ (see Risks) — already smoke-tested untrimmed in Milestone 3; only add   │
     │ trimming later if binary size actually matters.                         │
     │                                                                         │
     │ Viewer's static bundle rebuild is a separate concern from vault pushes  │
     │ (only needs rebuilding when the viewer app itself changes) — document   │
     │ this distinction clearly so it isn't conflated with per-push graph.json │
     │ regeneration.                                                           │
     │                                                                         │
     │ Testing                                                                 │
     │                                                                         │
     │ Fully simulable locally with the fixture vault: git init --bare a local │
     │ test repo → install a local post-receive pointed at a local checkout    │
     │ dir + locally-published binary + vite preview → git push the fixture    │
     │ vault in → assert graph.json updates and the locally-served viewer      │
     │ reflects it.                                                            │
     │                                                                         │
     │ Done (matches user's wording exactly): a push to the bare repo produces │
     │ an updated graph.json that the viewer picks up on reload.               │
     │                                                                         │
     │ ---                                                                     │
     │ Milestone 7 — Remaining views                                           │
     │                                                                         │
     │ Files                                                                   │
     │                                                                         │
     │ synapse-viewer/src/components/dashboard/                                │
     │ - DashboardView.svelte, StatCard.svelte                                 │
     │ - Donut.svelte — port of donutSvg() (stacked stroke-dasharray rings,    │
     │ one circle, category first-seen order).                                 │
     │ - Heatmap.svelte — port of heatmapSvg() (26×7 GitHub-style grid,        │
     │ color-mix 25–90% green ramp), backed by the real history field from     │
     │ Milestone 2/3 (git log dates) instead of fake seed data, with a real    │
     │ new Date() "today" anchor (not the prototype's hardcoded fixture date). │
     │ Pure date-bucketing logic factored into a testable                      │
     │ domain/dashboard/heatmap.ts.                                            │
     │                                                                         │
     │ synapse-viewer/src/domain/sets/venn.ts +                                │
     │ components/venn/VennView.svelte — port of vennEl(): fixed circle        │
     │ layouts per set-count (1-4), single-set membership via the prototype's  │
     │ hash-seed seed() function (ported verbatim, pure), multi-set membership │
     │ → centroid ± deterministic jitter, fixed 4-color palette independent    │
     │ of category colors, tag/category dimension toggle.                      │
     │                                                                         │
     │ synapse-viewer/src/components/graph/Minimap.svelte — port of            │
     │ minimapSvg() (bbox-fit SVG, faint edges, dimmed-if-filtered nodes,      │
     │ viewport rect overlay).                                                 │
     │                                                                         │
     │ synapse-viewer/src/data/pollGraphJson.ts (optional/stretch per the      │
     │ brief) — periodic conditional check against graph.json's                │
     │ ETag/Last-Modified, prompt or auto-reload on change.                    │
     │                                                                         │
     │ Testing                                                                 │
     │                                                                         │
     │ - venn.test.ts — deterministic placement given fixed seed strings;      │
     │ circle-center formulas for 2/3/4 sets.                                  │
     │ - donut.ts unit test — arc lengths sum to full circumference, category  │
     │ order matches first-seen.                                               │
     │ - heatmap.ts unit test — given an injected fixed "today," grid cell     │
     │ dates/labels correct; buckets real history dates correctly.             │
     │ - Manual QA: dashboard/venn/minimap against the fixture vault's         │
     │ graph.json (now with real multi-date history from the fixture git       │
     │ repo).                                                                  │
     │                                                                         │
     │ Done: Dashboard (donut + heatmap + stat cards), Venn mode, and Minimap  │
     │ all work against the fixture vault's graph.json; polling implemented or │
     │ explicitly deferred.                                                    │
     │                                                                         │
     │ ---                                                                     │
     │ Cross-cutting divergence summary                                        │
     │                                                                         │
     │ Prototype concept: links: string[] curated field                        │
     │ Real-app equivalent: [[wikilink]] parsing + resolution                  │
     │ Portable?: New — no prior art                                           │
     │ ────────────────────────────────────────                                │
     │ Prototype concept: edges() level-based direction                        │
     │ Real-app equivalent: source=referencing note, target=resolved           │
     │ Portable?: New rule                                                     │
     │ ────────────────────────────────────────                                │
     │ Prototype concept: orphanSet()                                          │
     │ Real-app equivalent: selectors.orphanIds()                              │
     │ Portable?: Ports directly                                               │
     │ ────────────────────────────────────────                                │
     │ Prototype concept: Ghost nodes                                          │
     │ Real-app equivalent: —                                                  │
     │ Portable?: New concept                                                  │
     │ ────────────────────────────────────────                                │
     │ Prototype concept: catColor() fixed map + #888                          │
     │ Real-app equivalent: hash-based deterministic fallback                  │
     │ Portable?: New utility                                                  │
     │ ────────────────────────────────────────                                │
     │ Prototype concept: step()/initSim() custom physics                      │
     │ Real-app equivalent: d3-force forces                                    │
     │ Portable?: Reimplement in d3's model                                    │
     │ ────────────────────────────────────────                                │
     │ Prototype concept: fitView()/onWheel()/toWorld()                        │
     │ Real-app equivalent: Viewport.ts                                        │
     │ Portable?: Ports near-literally                                         │
     │ ────────────────────────────────────────                                │
     │ Prototype concept: donutSvg()/vennEl()/minimapSvg()                     │
     │ Real-app equivalent: same-named Svelte components                       │
     │ Portable?: Port math directly                                           │
     │ ────────────────────────────────────────                                │
     │ Prototype concept: heatmapSvg() (fake activity[])                       │
     │ Real-app equivalent: real history[] via git log                         │
     │ Portable?: Data source is new; visual math ports                        │
     │ ────────────────────────────────────────                                │
     │ Prototype concept: mdRender()/hl()/esc()                                │
     │ Real-app equivalent: markdown-it + highlight.js                         │
     │ Portable?: Replace, don't port                                          │
     │ ────────────────────────────────────────                                │
     │ Prototype concept: cosmetic wikilink spans                              │
     │ Real-app equivalent: functional click-to-navigate                       │
     │ Portable?: New behavior                                                 │
     │ ────────────────────────────────────────                                │
     │ Prototype concept: edit mode (editing/draft/saveEdit)                   │
     │ Real-app equivalent: read-only DetailPanel, room left for future edit   │
     │ Portable?: Deferred, not dropped forever                                │
     │ ────────────────────────────────────────                                │
     │ Prototype concept: 5 skins × light/dark                                 │
     │ Real-app equivalent: carbon dark only, 3 layouts kept                   │
     │ Portable?: Skin machinery deleted; layout machinery kept                │
     │                                                                         │
     │ ---                                                                     │
     │ Risks and open questions                                                │
     │                                                                         │
     │ 1. d3-force determinism. Barnes-Hut approximation + float iteration     │
     │ order means coordinates aren't bit-stable run-to-run. Test pure inputs  │
     │ to custom forces in isolation; rely on visual QA for overall settling,  │
     │ not coordinate snapshots.                                               │
     │ 2. Canvas hit-testing is new engineering, not a port — quadtree         │
     │ rebuilt/queried against live positions, throttled to rAF, with a        │
     │ z-order tie-break for overlaps.                                         │
     │ 3. markdown-it wikilink clicks cross a reactivity boundary —            │
     │ {@html}-injected anchors need event delegation, not on:click. Confirm   │
     │ HTML passthrough stays disabled.                                        │
     │ 4. Self-contained linux-arm64 publish + reflection-based libraries —    │
     │ PublishTrimmed can silently break YamlDotNet/System.Text.Json           │
     │ reflection; smoke-test the actual published binary early (Milestone 3), │
     │ not first at deploy time.                                               │
     │ 5. Concurrent post-receive runs — atomic write prevents torn reads, but │
     │ overlapping generator invocations should be an explicit decision        │
     │ (simple lock file, or accept last-write-wins) not an accident.          │
     │ 6. Frontmatter list-vs-string coercion — YAML tags: can be a comma      │
     │ string, inline list, or block list; coercion rules must be explicit and │
     │ tested, not silently wrong (e.g. treating a whole comma-string as one   │
     │ tag).                                                                   │
     │ 7. Ambiguous same-name notes in different folders aren't fully resolved │
     │ by path>name>alias when the link is bare-name; surface via warnings[]   │
     │ rather than silently picking one.                                       │
     │ 8. Git history requires the vault checkout to be a real git working     │
     │ tree tied to its bare repo (--git-dir/--work-tree) — the fixture vault  │
     │ must also be a git repo for tests to exercise this realistically, which │
     │ is a heavier fixture-setup step than a plain file tree.                 │
     │ 9. Category color precedence across three sources (generator config,    │
     │ user override, hash fallback) — documented above as config > override > │
     │ hash; make sure Milestone 7's Dashboard/Venn both actually read it      │
     │ from one shared place, not independently.                               │
     │ 10. Three-layout scope roughly triples Milestone 5's shell-component    │
     │ surface (three chrome components instead of one) — if this turns out    │
     │ heavier than expected once M4/M5 are underway, it's fine to sequence    │
     │ Classic first and treat Rail/Command as fast-follow within the same     │
     │ milestone rather than blocking on all three simultaneously.             │
     │                                                                         │
     │ ---                                                                     │
     │ Verification                                                            │
     │                                                                         │
     │ - Each milestone's own unit tests (dotnet test, npm run test) must pass │
     │ before moving to the next.                                              │
     │ - Milestone 3: run the actual dotnet publish -r linux-arm64             │
     │ --self-contained -p:PublishSingleFile=true binary against the fixture   │
     │ vault, not just dotnet run.                                             │
     │ - Milestone 4 onward: npm run dev in synapse-viewer, manually verify    │
     │ against the fixture graph.json in a browser (drag/pan/zoom, ghost-node  │
     │ styling, filters, palette, all three layouts).                          │
     │ - Milestone 6: simulate the full push→hook→generate→serve loop locally  │
     │ (bare repo + local hook + vite preview) before touching the real Pi.    │
     │ - Final end-to-end check: a git push of the fixture vault into a local  │
     │ bare repo results in a graph.json that the locally-served viewer picks  │
     │ up with correct real nodes, ≥1 ghost node, ≥1 orphan, real history      │
     │ dates in the heatmap, and all views/layouts functional.                 │
     ╰─────────────────────────────────────────────────────────────────────────╯
  ⎿  You've hit your session limit · resets 3:20am (Europe/Warsaw)
     /upgrade to increase your usage limit.

✻ Cogitated for 57m 15s