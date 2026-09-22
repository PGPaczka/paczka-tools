# graph.json Schema — Synapse v2

`graph.json` is the sole contract between **Synapse.Generator** (C# producer)
and **synapse-viewer** (Svelte/Vite consumer). Both sides are versioned by
`schemaVersion`; the viewer hard-equality-checks it and shows a blocking
"regenerate graph.json" message on mismatch. No migration machinery — just
re-run the generator.

The generator writes atomically: temp file → `File.Move(overwrite:true)`.
Ordering is deterministic (nodes by id, edges by (source, target)) so the
file is snapshot-testable and git-diffable.

---

## Top-level fields

| Field          | Type     | Description |
|----------------|----------|-------------|
| `schemaVersion`| `integer`| Always `2`. Hard-equality-checked by the viewer. |
| `generatedAt`  | `string` | ISO-8601 UTC timestamp of the run. |
| `vault`        | object   | Aggregate stats (see below). |
| `nodes[]`      | array    | Polymorphic; each item is a `RealNode` or `GhostNode`. |
| `edges[]`      | array    | Directed wikilink edges. |
| `warnings[]`   | array    | Non-fatal pipeline concerns (ambiguous links, duplicate ids). |

---

## vault

```json
{
  "name": "informatyka",
  "notesCount": 21,
  "ghostCount": 3,
  "orphanCount": 2
}
```

`orphanCount` counts real nodes with no edges in or out.

---

## nodes[] — RealNode (`"kind": "real"`)

```json
{
  "id": "docker-basics",
  "kind": "real",
  "title": "Docker Basics",
  "path": "devops/docker-basics.md",
  "category": "DevOps",
  "level": 1,
  "status": "completed",
  "type": "file",
  "tags": ["containers", "cli"],
  "aliases": [],
  "modified": "2026-06-10",
  "excerpt": "Docker packages your application and its dependencies into a portable container…",
  "wordCount": 138,
  "history": ["2026-04-02", "2026-05-18", "2026-06-10"]
}
```

**Defaults when frontmatter key is absent:**

| Field      | Missing frontmatter value |
|------------|--------------------------|
| `category` | `"Uncategorized"`         |
| `type`     | *(key omitted)*           |
| `level`    | `null`                    |
| `status`   | `null`                    |
| `tags`     | `[]`                      |
| `aliases`  | `[]`                      |

**`id`** = filename stem. Matched case-insensitively during link resolution,
stored with original casing.

**`type`** = what the note IS in the vault's own taxonomy — e.g. `semester`, `subject`,
`file` for a vault generated from a course package. Free-form on purpose: the generator
carries whatever the vault declares and never validates it against a fixed list. It is
separate from `kind`, which only discriminates real from ghost.

**`history`** = commit dates from `git log --follow --format=%ad --date=short`,
oldest→newest. Absent (key omitted) when the file has no git history (e.g.
untracked at generation time). Pass `--no-git` (or `skipGitHistory` in the config) when the
vault is generated rather than hand-written and is not a repository at all: without it the
generator spawns one `git log` per note only to fail, which costs a process each time.

---

## nodes[] — GhostNode (`"kind": "ghost"`)

Ghost nodes represent wikilink targets that don't resolve to any real note.

```json
{
  "id": "kubernetes-advanced",
  "kind": "ghost",
  "title": "kubernetes-advanced",
  "referencedBy": ["docker-networking", "kubernetes-intro"],
  "referenceCount": 2
}
```

**`id`** = trimmed / collapsed-whitespace / lowercased raw link target text.
Used as the dedup key — two notes linking to `[[Kubernetes Advanced]]` and
`[[kubernetes-advanced]]` produce one ghost with `referenceCount: 2` and
both source IDs in `referencedBy`.

---

## edges[]

Direction: `source` = the note containing the `[[wikilink]]`,
`target` = the resolved real or ghost node.

```json
{
  "source": "docker-basics",
  "target": "dockerfile",
  "linkText": "dockerfile",
  "kind": "near_duplicate",
  "confidence": 0.82
}
```

**`kind`** says WHY the two notes are connected. `link` is a plain `[[wikilink]]` found in
the body; any other value comes from a **typed relation** declared in frontmatter:

```yaml
relations:
  - target: dockerfile        # resolved through the same tiers as a wikilink
    kind: near_duplicate      # free-form; the viewer styles what it finds
    confidence: 0.82          # optional, 0..1
```

A relation whose target does not resolve becomes a **ghost node**, exactly like a dangling
wikilink — an unresolved relation stays visible instead of being silently dropped. An entry
without a `target` is skipped; a bare string (`relations: [dockerfile]`) defaults to kind
`related`. `confidence` is emitted only when the vault declared one.

`linkText` carries the raw wikilink text (including `|alias` or `#heading`
suffixes) so the viewer's markdown-it wikilink plugin can map rendered
`[[…]]` spans back to resolved edges without re-implementing C#'s resolution
rules in TypeScript.

---

## warnings[]

Non-fatal. The pipeline never fails the build over vault hygiene.

```json
{
  "kind": "ambiguous-link",
  "noteId": "docker-networking",
  "linkText": "docker",
  "resolvedTo": "docker-basics"
}
```

| `kind`           | When emitted |
|------------------|-------------|
| `ambiguous-link` | Two or more notes match the same link target within the same resolution tier; first-scanned-wins, target recorded in `resolvedTo`. |
| `duplicate-id`   | Two `.md` files have the same filename stem (different directories). |

---

## Link resolution order

For each `[[wikilink]]` the generator tries in order, stopping at first match:

1. **Full relative-path match** — link text matches vault-relative path (without `.md`).
2. **Filename-stem match** — link text matches the stem of any `.md` file (case-insensitive).
3. **Alias match** — link text matches an alias from frontmatter (case-insensitive).

No match → ghost node. Ambiguous within a tier → first-scanned-wins + warning.

Pipe (`|`) and heading (`#`) suffixes are stripped before matching;
the full raw text is preserved in `edges[].linkText`.

---

## Versioning policy

`schemaVersion` is a bare integer. Increment it when the shape changes
incompatibly. The viewer does a hard `=== 2` check and blocks with a message
on mismatch — re-run the generator to produce a new `graph.json`. No reader
migration machinery.

**v1 → v2**: real nodes gained `type`, edges gained `kind` (required) and optional
`confidence`. `schema/graph.schema.v1.json` is kept for reference only.
