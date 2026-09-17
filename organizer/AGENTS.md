# AGENTS.md — zasady dla agenta (model-agnostyczne)

Pełne zasady: `CLAUDE.md`. Skrót obowiązujący każdy model (Claude / Codex / Gemini via `agy`;
`GEMINI.md` tylko odsyła tutaj):

1. Never modify or delete anything under `00_SOURCES` — read-only archive.
2. `paczka/` is the canonical package being constructed.
3. The agent NEVER touches the filesystem. Its only output is `plan.jsonl`.
4. Prefer deterministic script decisions; handle only `unresolved` items.
5. Exact duplicates are decided by hash (file: sha256, folder: tree_hash), never by you.
6. Never treat similar files as duplicates — emit a relation, keep both.
7. Process ONE subject at a time. Subject identity = (semester, skrót); the skrót
   is NOT unique — use the semester to resolve collisions (AK, PO, SI, SK, ASK...).
8. Every planned copy must carry provenance (source_sha256, source_paths).
9. If confidence < threshold, set needs_review=true or action=quarantine. Do not guess.
10. `outdated/` is a semantic decision made in review, never automatic from similarity.
11. Large media never enter the package — route to `90_MEDIA/` + `inne/nagrania.txt`.
12. Output only valid JSONL matching schema_version. No filesystem changes before apply.
