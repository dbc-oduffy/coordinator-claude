---
title: Sibling Surface Parity Testing
status: active
kind: doctrine-wiki
created: 2026-05-18
recurring: 2
---

# Sibling Surface Parity Testing

## Overview

A "sibling surface" is two or more implementations that publish the same contract but evolve
independently — `/review` and `/review-code`, `coordinator-safe-commit` and
`coordinator-auto-push`, `pickup` and `handoff`, etc. Each pair shares a written contract (a
wiki, a snippet, a doctrine line) and a written shape (a config schema, a CLI surface, a
frontmatter scheme). When ONE sibling gets a capability the others don't, the divergence is
silent — the doctrine still reads as if siblings are equivalent.

This wiki defines when to file parity tests, what they assert, and how to discover sibling
pairs before the second divergence forces the issue.

## The Recurring Symptom

- Skill A grows a new flag/branch/preamble; skill B in the same family doesn't.
- A reviewer adds a sidecar emission; another reviewer in the chain doesn't.
- A snippet's consumers drift from the snippet — `bin/verify-*-sync.sh` catches THIS class;
  the wider sibling-surface class is broader.
- Recurrence in the queue: 2026-05-05 (queue L149) flagged; recurred 2026-05-06 evening
  session.

The common thread: one sibling is the active workstream path; the other is used less often
and misses the update because it was never in scope when the change was made.

## The Parity Test

For each sibling-pair, file a one-shot test under
`tests/sibling-parity/<surface>.{sh,py}` that asserts all four dimensions:

### 1. Identical Doctrinal Shape

Both siblings reference the same wiki or snippet. Assert the sentinel is present in both.

```bash
# Example: both pickup and handoff must reference handoff-lineage wiki
grep -l 'handoff-lineage' coordinator/skills/pickup/SKILL.md coordinator/skills/handoff/SKILL.md
```

Failure mode caught: one skill updated to reference a renamed wiki; the other still points at
the old path and silently drifts.

### 2. Identical Config-Schema Coverage

If sibling A reads `setting.foo`, sibling B's `--help` output or schema dump must also
reference `setting.foo`. For YAML-config siblings, diff the key-set rather than the values.

```bash
# Extract top-level keys from both schema files and diff
python3 -c "import yaml,sys; print(sorted(yaml.safe_load(open(sys.argv[1])).keys()))" A.yml
python3 -c "import yaml,sys; print(sorted(yaml.safe_load(open(sys.argv[1])).keys()))" B.yml
```

### 3. Identical Preamble / Snippet Block

When siblings share a snippet (e.g., `reviewer-calibration`, `prior-art-check-consumption`),
both sentinel-block instances must match the source-of-truth in `coordinator/snippets/`.

The `bin/verify-*-sync.sh` scripts catch intra-snippet drift but do NOT check whether both
siblings include the snippet at all. The parity test adds that outer check.

```bash
# Assert both siblings contain the sentinel start tag
grep -l 'BEGIN reviewer-calibration' \
  coordinator/agents/staff-eng.md \
  coordinator/agents/code-reviewer.md
```

### 4. Identical Version Cadence

When siblings share a version bump (e.g., schema migration, frontmatter field addition), both
must move together. Assert that both files contain the same version string or schema field.

```bash
grep 'schema_version' coordinator/skills/workstream-complete/SKILL.md coordinator/skills/handoff/SKILL.md \
  | awk -F: '{print $2}' | sort -u | wc -l  # must equal 1
```

## Discovery: How to Find Sibling Pairs

Run these before filing a new capability against only one member of a family.

```bash
# Skills sharing a wiki or snippet reference
grep -rl 'docs/wiki/<topic>.md' coordinator/skills/

# Agents sharing a sidecar emission contract
grep -rl 'kind: review-sidecar' coordinator/agents/

# Skills in the same directory family (common prefix)
ls coordinator/skills/ | sed 's/-[^-]*$//' | sort | uniq -d

# Bin scripts wrapping the same underlying tool
grep -rl 'coordinator-safe-commit' coordinator/bin/ coordinator/skills/
```

A pair qualifies as a sibling surface when: (a) both implement the same external contract OR
(b) both are cited as equivalent in doctrine (e.g., "either X or Y achieves Z").

## When to Write a Parity Test

**File after the second instance of a divergence symptom.** The first instance is fixed
in-place; the second instance proves the pattern is recurring and warrants an executable gate.

**File when adding a new sibling to an existing family.** The parity test prevents
"added capability to A, forgot B." The test is written for the family at creation time of the
second member, not retroactively.

**Do NOT file speculatively** for surfaces with only one implementation — parity tests have no
meaning until there are two things to compare.

## Lifecycle

1. **New sibling added** → author writes parity test for the pair in the same commit.
2. **Capability added to one sibling** → CI runs `tests/sibling-parity/` before the commit
   lands; parity test fails if the other sibling is missing the assertion surface.
3. **Sibling retired** → delete its parity test; note the retirement in the commit message.

Parity tests are not regression tests — they do not run the siblings, they assert structural
equivalence. Runtime divergence is a different concern (→ `round-trip-contract-tests.md`).

## Anti-Patterns

**Parity-by-convention-only.** Documenting "these should match" in CLAUDE.md without an
executable check decays at first drift. The doctrine note is still useful as the why; the
test is the gate.

**Parity tests that grep for absence.** A grep asserting "should not contain X" silently
passes when X is renamed. Prefer presence-assertion: grep for the canonical form, not the
absence of the deprecated form.

**Mega-parity tests.** One test file per family, not one file for all families. Scoped tests
fail loud and fast; a single failing assertion in a 400-line omnibus test is slow to diagnose.

**Testing values instead of shapes.** Parity tests assert that the same keys/fields/sentinels
exist in both siblings, not that their values agree. Value-level agreement is a contract
test, not a parity test — keep them separate.

## Related

- `docs/wiki/round-trip-contract-tests.md` — broader contract-test patterns including
  runtime producer/consumer verification
- `docs/wiki/test-design-discipline.md` § Drift-detection tests — general discipline for
  tests whose job is to catch silent drift over time
- `coordinator/snippets/` + `bin/verify-*-sync.sh` — the narrower snippet-sync mechanism
  that parity tests build on top of
- `coordinator/CLAUDE.md` § Snippet-sync — tripwire listing which snippets have sync scripts
