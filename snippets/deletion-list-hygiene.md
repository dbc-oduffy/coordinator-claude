# Deletion-List Hygiene

Phase 3d emits a structured YAML manifest (`schema_version: 1`, `deletions:` key). Consume the YAML directly — do NOT parse the prose Markdown table (if present) and do NOT use column-extraction tools like `awk -F'|'` to extract paths from it. The prose table is a derived PM-readable view; the YAML is the source of truth.

## Required procedure

1. **Read the YAML manifest** from the Phase 3d scratch file. The manifest begins with `schema_version: 1` and contains a `deletions:` list.
2. **Filter by disposition.** Extract entries where `disposition: DELETE`. Entries with `disposition: SKIP` or `disposition: PRESERVE` are not candidates for deletion.
3. **Per-row validation.** Each `artifact_path` value must parse as a single relative path (no spaces, no commas, no bracket syntax). Any entry that fails parse → abort and report the row to the EM.
4. **Fail closed on count mismatch.** Count of `DELETE` entries from YAML must equal the count of paths you intend to pass to `git rm`. Mismatch = abort.

## Why YAML, not column extraction

`awk -F'|'` column extraction on the prose Markdown table is unsafe and must not be used — the YAML manifest is the sole source of truth.

The prose failure mode that drove the original awk guidance still applies to the prose table (if retained): a `grep '\.md'` over the manifest body matches paths in both the `artifact_path` column AND paths cross-referenced in the `reason` text, silently expanding the deletion list. YAML consumption eliminates this failure mode structurally — each field is typed and separately addressable; the `artifact_path` field is never confused with `reason` text.

<!-- negative-spec: do NOT use awk -F'|' or grep-based column extraction on the Phase 3d prose table to build deletion lists. The prose table is a derived view; only the YAML deletions: list is authoritative. -->

## See also

- `pipelines/artifact-distillation/PIPELINE.md` Phase 5 step 5 — primary consumer
- Related principle: "detect-then-silently-pick is a footgun" — surface an ambiguity for a decision rather than resolving it silently.
