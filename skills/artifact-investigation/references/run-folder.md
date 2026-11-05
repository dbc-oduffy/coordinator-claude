# Artifact-investigation run folder

One folder per investigation. Each stage writes one file there; the next stage and every gate read it.
`scripts/run_folder.py` is the contract; the stage registry `STAGES` lives there and is the one place a
stage flips to landed.

## Layout

| File | Writer | Content |
|------|--------|---------|
| `requirements.json` | the investigator | `{"items": [{id, priority, excluded, stage}]}`; `priority` is `must`, `should` or `could`; `excluded` marks a deliberate exclusion |
| `<NN>-<stage>.json` | the stage | `{"claims": [{..., source_link, requirement_ids}]}`; `NN` is the stage's 1-based registry position |
| `<stage>.dropped.json` | claim filter | claims removed for lacking a `source_link` |
| `coverage.json` | coverage scorer | per-stage coverage |
| `sweep.json` | sweep gate | blockers, or the skipped-stage record |

## Stages

Registry order: `parse-ingest` (C16+C5), `index-query` (C4), `record-claims` (C3), `judgment` (none).
Only `judgment` is landed. Every sibling stage is not landed and reads `coverage: unknown`,
`provisional: true`.

## Evidenced

A requirement item is evidenced when a claim with a non-empty `source_link` in its stage file names the
item's `id` in `requirement_ids`. The scorer and the sweep gate both call `evidenced_ids`; a claim
without a `source_link` evidences nothing.

## Keys

`source_link` and `requirement_ids` are run-folder keys only. The claims and unknowns record shape is
owned by project-rag; this folder is working scratch, not that record.
