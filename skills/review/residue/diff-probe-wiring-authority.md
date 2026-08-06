---
segment_id: diff-probe-wiring-authority
surface: diff
class: droppable
order: 70
---

**`--surface diff` — probe-wiring brief authority surface.** When building an executor brief that wires a new coordinator-doctor probe (adding or editing a health/drift probe), name this repo's own coordinator-doctor documentation, if one exists, as the authority surface in the brief — never a generic "find the doctor command" instruction. The coordinator doctor is **wiki-only by design** — there is no `commands/doctor.md`, so a brief phrased that way sends the delegate searching for a file that does not exist. Confirm the doc path actually exists before quoting it (spec backlinks outlive their cited spec); if this repo carries no such documentation, say so rather than inventing a path.
