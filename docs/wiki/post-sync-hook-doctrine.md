---
name: post-sync-hook-doctrine
status: active
---

# Post-Sync Hook Doctrine

<!-- spec backlink: none — doctrine distilled from publish pipeline operational experience -->

Post-sync hooks that run after `rsync` or the publish pipeline (claude-klabauter `coordinator/bin/publish.py`) completes MUST constrain their work to the set of files the sync actually transferred. A hook that walks the destination tree as a whole operates on state it didn't create, and silently mutates files this sync had no stake in.

## The Leak

When `rsync` syncs a delta — say, 3 changed files out of 200 in the destination — a naive post-sync hook that iterates `dest/**` will process all 200. For read-only checks (grep audits, schema validation) this is usually harmless. For **mutating** hooks — depersonalisation scripts, link-rewriters, license-stampers — it is a corruption vector:

- Files that arrived in a previous sync run get re-mutated under the new run's assumptions.
- State the hook injects may not match what this sync delivered (e.g., rewriting a brand token using the source repo's identity when the file came from a different source).
- Idempotency is illusory: the hook appears to succeed on re-run, but output diverges from what a from-scratch sync would produce.

## The Discipline

A mutating post-sync hook MUST accept the rsync touched-file list on stdin and operate only on those paths. The hook is a pure function of `{rsync output} → {destination mutations}` — not of the destination tree's current state.

**Contract:**
```
# hook receives one relative path per line on stdin (rsync's --out-format='%n')
# and operates only on those paths in the destination
while IFS= read -r path; do
  mutate "$DEST_ROOT/$path"
done
```

The hook MUST NOT open `dest/` independently. If a path outside the stdin list needs mutating, that is a separate maintenance task — not a post-sync side-effect.

## rsync Recipe

Feed `rsync --out-format='%n'` through `tee` to both capture the list for the hook and let normal stdout progress flow:

```bash
rsync --out-format='%n' [OPTIONS] "$SRC/" "$DEST/" \
  | tee >(post-sync-hook --dest "$DEST")
```

The hook reads stdin. `tee` lets the caller see progress too. If you need the list for auditing as well:

```bash
rsync --out-format='%n' [OPTIONS] "$SRC/" "$DEST/" \
  | tee touched.log \
  | post-sync-hook --dest "$DEST"
```

On Windows/Git-Bash, `tee >()` process substitution may not be available — use an intermediate file:

```bash
rsync --out-format='%n' [OPTIONS] "$SRC/" "$DEST/" > touched.log
post-sync-hook --dest "$DEST" < touched.log
```

## When This Matters

Apply the touched-list constraint to any hook that **mutates** destination content:

- **Depersonalisation scripts** — strip author-specific strings, brand tokens, or machine paths.
- **Link-rewriters** — adjust cross-reference paths from source-repo layout to publish-repo layout.
- **License-stampers** — prepend or update license headers.
- **Tag-injectors** — embed version or provenance metadata into file content.

If the hook rewrites even one byte of a file it didn't receive via this sync, the constraint applies.

## Read-Only Checks Are Exempt

Post-sync checks that only **read** the destination — grep audits, schema validators, link-checkers, checksum verifiers — may scan the full destination tree. They produce no mutations, so destination-tree scope does not corrupt state. The touched-list constraint is a mutation guard, not a query guard.

## Injection Hooks — Exception to the Touched-List Rule

Not all post-rsync hooks operate on synced-content files. Three classes exist, with different
rules:

### (a) Per-file synced-content rewriters (the default class)

Hooks that mutate files the mirror sync transferred MUST operate only on the rsync-touched list
(stdin). The Leak and Discipline sections above describe this class fully. Examples:
depersonalisation scripts, link-rewriters, license-stampers, tag-injectors.

**Touched-list constraint: REQUIRED.**

<!-- Review: code-reviewer — the depersonalise sweep is a full-tree MUTATOR (rewrites every
.md/.sh in the destination), NOT a read-only checker. It has been moved out of class (b) into
its own sub-case (a') below. Class (b) must remain "inspect only, no mutations." -->

### (a') Full-tree idempotent mutators

A special sub-case of class (a): hooks that mutate the ENTIRE destination tree, not just the
rsync-touched subset. This is safe ONLY when the mutation is a **pure function of file content**
— i.e., the same input always produces the same output, regardless of which delivery batch
triggered the run.

The canonical example is the `coordinator-claude` post-rsync depersonalise sweep: it rewrites
every `.md` and `.sh` file in the destination, because persona-name leakage from previous
rounds accumulates in files not touched by the current delta. Touching only the current
delta's files would let old leakage accumulate indefinitely (observed 2026-05-17:
check-persona-names CI failed on eng-director.md, dep-cve-auditor.md etc. that had not been
touched since their leakage was introduced). This hook is therefore a full-tree mutating hook,
and its correctness depends on that scope.

The operative safety property: **idempotent full-tree mutation is safe when the mutation is a
pure function of file content, not of delivery-batch state.** A hook that keys its mutation
decisions on delivery-batch state (e.g., timestamps, rsync run count, or env vars that change
between runs) does NOT qualify for this class.

**Touched-list constraint: inapplicable for this class (scope is full-tree by design).**

### (b) Read-only checkers

Hooks that only **inspect** the destination — grep audits, schema validators, link-checkers —
may scan the full destination tree. No mutation, no corruption vector. The touched-list
constraint is a mutation guard, not a query guard. **Class (b) contains NO mutating hooks.**

**Touched-list constraint: exempt (no mutations).**

### (c) New-file / new-dir injectors with no source-synced-content analog

Some hooks inject files or directories into the destination that have NO corresponding path
in the mirror's source tree. The `/coordinator-update` OSS-only skill is the canonical
example: it lives under `coordinator/dist/oss-only-skills/` (excluded from the mirror by
`.percolate-ignore`) and is injected into `coordinator/skills/coordinator-update/` by a
post-rsync injection hook.

For this class, the touched-list stdin contract is **inapplicable** — there is no synced path
to scope to. The rsync-touched list will never contain `coordinator/skills/coordinator-update/`
because the mirror never synced it. Idempotency for this class does NOT come from "operate
only on what rsync touched." It comes from the inject being a **pure function of the `dist/`
source state**: `mkdir -p + cp -r` produces the same destination regardless of prior dest
state. Running the inject hook N times produces the same result as running it once.

The hook still receives the rsync-touched list on stdin (the publish pipeline always pipes it
for post-rsync hooks) — the hook MUST drain it (`cat >/dev/null`) to avoid pipe-buffer deadlock,
even though it ignores the content.

**Touched-list constraint: inapplicable. Idempotency via `dist/`-source purity.**

**Survival mechanism:** the mirror sync's delete-pass runs BEFORE the hook. Because the
inject source has no mirror analog (excluded by `.percolate-ignore`), the delete-pass removes
any previously-injected files on each publish. Running the inject hook post-delete-pass is
therefore unconditional and self-healing: every publish restores what the delete pass removed.

#### Generalisation from the version.txt carve-out

`agentic-install-integrity.md` §3 (deferred extensions) notes that the C3 sentinel-write hook
in the publish pipeline is a "root-level new-file mutation" distinct from per-file synced-content
rewrites, and that the touched-list constraint does not apply to it. This section generalises
that carve-out from the specific `version.txt` case (a single root-level file) to the broader
class: **any new-file or new-directory injection where the injected content has no
source-synced-content analog** is exempt from the touched-list constraint for the same reason.
The operative distinction is not "root-level" vs. "nested" — it is "content the mirror synced"
vs. "content the mirror never touched."

Cross-references:
- `docs/wiki/agentic-install-integrity.md` §3 — the version.txt carve-out this section generalises
- `plugins/coordinator-claude/.percolate-ignore` — `coordinator/dist/oss-only-skills/` exclusion
  that makes the inject the sole delivery path (prevents double-ship)
- `docs/plans/2026-05-30-oss-coordinator-update-skill.md` § Chunk 4 — the reviewed plan that
  introduced this pattern

## Cross-References

- `docs/wiki/percolate-setup.md` — percolation pipeline where hook scoping first mattered
- `docs/wiki/plugin-extraction-and-distribution.md` — publish pipeline (claude-klabauter `coordinator/bin/publish.py`) that drives the rsync invocations
- `docs/wiki/agentic-install-integrity.md` — classifier, sentinel, and three deferred extensions including §3 (the new-file mutation carve-out this section generalises)
