# Cross-platform CI reference fragment

This directory contains a reference CI snippet for coordinator consumers that
declare cross-platform support.

## What this is

`cross-platform-matrix.snippet.yml` is a **copyable fragment**, not a
standalone installable workflow. Copy the sections you need into your own
`ci.yml` (or equivalent) and adapt the marked adapt-points to your project.

**This is a worked pytest example of the language-agnostic principle** — not
"the cross-platform CI reference." The YAML is GitHub-Actions-shaped as the
reference form because that is the most common CI system across coordinator
consumers. Adapt the matrix and honest-measurement marker conventions to your
own CI system and test runner; the structural principle is identical regardless
of CI platform or test framework.

## The principle

Test on every OS your project declares it supports. Mark cross-repo-blocked
and hardware-gated tests **honestly** — with named markers and clear reason
strings — rather than silently passing or skipping. "Green on your dev OS is
not green on the others."

Full principle, all three primitives, and the discriminator guards:
`docs/wiki/cross-platform-ci-discipline.md`

## What the snippet contains

**Section 1 — 3-OS matrix block.** The `os: [ubuntu-latest, windows-latest,
macos-latest]` matrix. Adapt to the OS set your project declares as supported.

**Section 2 — `shell: bash` marker-computation step.** A bash step that
computes the pytest `-m` marker string, handling two coordinator-standard
honest-measurement cases:

- **`cross_repo_fix_locus`** (coordinator-standard marker, keep verbatim):
  deselects tests whose fix-locus is a sibling repo, with an inline closure
  guard (self-documenting reason string, re-collection trigger, discriminator
  against misuse). This is the marker — the name is shared across all repos
  that adopt this discipline so the reason string is the project-specific part.

- **Hardware-gated markers** (project-specific, adapt by name): tests that
  require hardware unavailable on standard CI runners. The snippet shows the
  pattern and explains the coverage-equivalence rationale. Replace the
  placeholder marker names with your own; do not adopt the illustration names
  verbatim.

`shell: bash` is explicit so the OS-conditional runs identically on all three
runners — git-bash is present on the Windows runner, so bash is available on
ubuntu-latest, windows-latest, and macos-latest.

## How to use

1. Copy Section 1 into your job's `strategy:` block.
2. Copy Section 2 into your job's `steps:` list before your test-run step.
3. Adapt every `<!-- TEMPLATE: adapt -->` point to your project.
4. For non-pytest test runners, translate the `-m "$PYTEST_MARKERS"` pattern
   to your runner's equivalent filtering mechanism.
5. For non-GitHub CI systems, translate the `$RUNNER_OS` conditional and
   `$GITHUB_ENV` export to your system's equivalents.

## Non-Python / non-pytest projects

The marker-computation step is pytest-flavoured. For other runtimes:

- **Jest / Vitest (TypeScript):** Use test-file patterns or `--testPathPattern`
  exclusions; the OS-conditional bash logic is identical.
- **cargo test (Rust):** Use `--test` flag filtering or `#[cfg_attr(...)]`
  attribute markers; the OS-conditional structure is the same.
- **Other:** Translate the three primitives (macOS lane, cross-repo-fix-locus
  honest deselection, hardware-gated coverage-equivalence) to your framework's
  skip/filter vocabulary. The principle is the same; the syntax is yours to
  choose.

The language-agnostic principle and when-this-applies guidance live in:
`docs/wiki/cross-platform-ci-discipline.md`
