# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

An implemented application with three parts:

- **`Synapse.Generator/`** — .NET 8 console app. Scans a vault of `.md` notes, reads YAML
  frontmatter through a *configurable* key mapping, extracts `[[wikilinks]]` and typed
  `relations:`, optionally reads git history, and writes `graph.json` + `search-index.json`.
  Tests: `cd Synapse.Generator/Synapse.Generator.Tests && dotnet test`.
- **`synapse-viewer/`** — Svelte + Vite SPA consuming `graph.json`. `npm install`, then
  `npm run dev` / `npm test` (vitest) / `npm run build`.
- **`deploy/`** — Raspberry Pi deployment: bare `vault.git`, a `post-receive` hook that
  regenerates the graph on every push, Caddy in front of the built viewer.

`schema/graph.schema.v2.json` and `schema/graph-schema.md` are the contract between the two
halves; `schemaVersion` is hard-equality-checked by the viewer, with no migration machinery.

**Historical note, because it costs people a day:** `SynapseVariants.dc.html`, `support.js`,
`claude-code-plan.md` and `.thumbnail` are the original Claude Design handoff bundle — the
mock-up this app was built from. They are kept for reference and are **not** the data model.
Anything about `seedNotes()` in that prototype is obsolete; the real model is `schema/` plus
`Domain/Graph/*.cs`. A clone that contains only those files is a stale copy of the bundle,
not of this repository.

## Data model

A node is a note on disk (`kind: "real"`) or an unresolved link target (`kind: "ghost"`).
Real nodes carry `type` — the vault's own taxonomy of what a note IS (free-form; a course
package uses `semester` / `subject` / `file`) — alongside `category`, `level`, `status`,
`tags` and `aliases`.

An edge says **why** two notes are connected: `kind` is `link` for a plain wikilink, or
whatever a typed relation declared, with optional `confidence`:

```yaml
relations:
  - target: docker-basics     # resolved through the same tiers as a wikilink
    kind: near_duplicate      # free-form; the viewer styles what it finds
    confidence: 0.82
```

An unresolved relation target becomes a ghost node, exactly like a dangling wikilink.

## Conventions worth knowing before changing anything

- A node's `id` is the **file name stem**, unique across the vault; duplicates raise a
  `duplicate-id` warning and one of them stops being linkable.
- The generator is deterministic and its end-to-end test compares output byte-for-byte with
  `Fixtures/golden-graph.json`, so any field change needs the schema AND a regenerated golden.
- `--no-git` (or `skipGitHistory` in the config) skips history for generated vaults that are
  not repositories; without it the generator spawns one failing `git log` per note.
- Frontmatter key names are configurable (`Configuration/generator.config.json`), so a vault
  is never forced to rename its fields.

## Known-failing tests

None — the suite is green as of 2026-09-23. The four that used to fail
(`categoryAnchors` ×3, `Viewport` ×1) were **stale expectations, not broken code**: they
called `categoryAnchors` without a centre while expecting the viewport centre, and the
`fitView` floor had been lowered for large vaults. Both were rewritten against what the
code actually does.

## Who else generates vaults for this

`paczka-tools/organizer` (course-package organiser) exports its SQLite index as a vault:
semesters, subjects and files with `near_duplicate` / `older_version` relations. Its side of
the contract is documented in that repo's `docs/SYNAPSE.md`, and it has a test that runs THIS
generator against a synthetic vault and validates the output — so a change here that breaks
the contract turns red over there.

When that package is checked out around this clone, `just synapse-view` (run in the
organiser) regenerates `synapse-viewer/public/graph.json`, `search-index.json` and
`public/vault/` from its database. Those are **build artefacts of someone else's data**:
expect them dirty in `git status`, and do not commit them here — `git checkout` on the two
tracked ones brings the demo vault back.
