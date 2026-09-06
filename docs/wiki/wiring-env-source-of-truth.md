---
title: Wiring.env — Source of Truth (DEPRECATED — transitional layer)
created: 2026-05-18
status: deprecated
deprecated_at: 2026-05-20
superseded_by: docs/wiki/machine-local-registry.md
provenance:
  - spinoff_plan: docs/plans/2026-05-18-daemon-reads-wiring-env-directly.md
    audit_synthesis: tasks/comprehensive-audit-2026-05-18/SYNTHESIS.md
    audit_theme: Theme E (closed-circuit deprecation)
---

<!-- Imported from X:/project-rag at SHA d376cb01. Inherited substrate; canonical lineage now in Claude Central. Sibling-repo layout doctrine lives in this repo's own wiki. --> <!-- foreign-path-ok: import provenance, not a current-location claim -->

# Wiring.env — Source of Truth (DEPRECATED — transitional layer)

> **Deprecated.** `~/.project-rag/wiring.env` is the transitional
> write-through cache that the daemon-boot read path uses during the
> coordination window. The canonical source of per-machine config is
> **`~/.claude/machine-local/`**, populated via `machine-local set <key> <value>`
> and read via `machine-local get <key>` — see
> [`machine-local-registry.md`](machine-local-registry.md). New addons MUST
> target machine-local; wiring.env retirement is the worked precedent named in
> `machine-local-registry.md` §11.
>
> This page is retained as the reference for daemon-boot wiring while
> wiring.env still exists. Once host daemon reads
> `addons.ue.paths.corpus` (or the composed `core.whoami` CLI) directly, this
> page goes to `archive/`.

<!-- Spec backlink: docs/plans/2026-05-18-daemon-reads-wiring-env-directly.md § Chunk 3 -->

`~/.project-rag/wiring.env` carries environment-variable declarations that the
project-rag daemon needs at boot — typically corpus-band pointers set by addon
setup phases. This page is the single reference for **who writes it**, **who reads
it**, and **how precedence works** — wiring consumption runs from the daemon
itself, not shell wrappers.

## What writes wiring.env

**Producer: `scripts/wire.py` (AD-16 implementation).**

`project-rag-cli wire` (Phase 6 of `/project-rag:setup`) invokes `wire.py` to
persist addon-provided env declarations to `~/.project-rag/wiring.env`. The file
format is standard `KEY=VALUE` dotenv syntax.

Key properties of the writer:

- **Idempotent.** Re-running with the same key-value pair is a no-op; existing
  values are preserved.
- **Conflict-fail-loud.** If a second addon tries to set a key that already exists
  with a different value, the writer raises rather than silently overwriting.
  (Spec: `docs/plans/2026-05-17-engine-rag-setup-doctor-catalog.md` L-5.)
- **Location fixed at `~/.project-rag/wiring.env`.** The machine-local path is a
  producer-side decision — see § Producer-side open question below.

## What reads wiring.env

**Consumer: the daemon `main()` function in `project_rag_mcp/project_rag_server.py`, via
`_load_wiring_env`.**

`_load_wiring_env(project_root)` is called **before** `_boot_server()`'s
`_parse_args()` pass, so argparse env-fallback flags and any `os.environ.get(...)`
calls downstream of boot see the wiring.env values:

```
main()
  └── _pre_parser.parse_known_args()   ← extracts --project-root
  └── _load_wiring_env(project_root)   ← dotenv.load_dotenv(path, override=False)
  └── _boot_server()
        └── _parse_args()              ← sees mutated os.environ
```

Path resolution inside `_load_wiring_env`:

1. `PROJECT_RAG_WIRING_ENV` env override (undocumented escape hatch; used in tests
   to redirect to a `tmp_path` fixture).
2. `~/.project-rag/wiring.env` (current convention; matches `scripts/wire.py`'s
   `_WIRING_ENV` constant).

**Direct-launch behaviour is identical to wrapper-launch.** A daemon started with
`python project_rag_mcp/project_rag_server.py --project-root <p>` (bypassing
`scripts/ensure-project-rag-server.{sh,ps1}`) picks up wiring.env through exactly
the same `_load_wiring_env` call. There is no wrapper-vs-direct split.

**`_load_wiring_env` is the canonical reload primitive.** Every wiring.env consumer
— boot-time `main()`, the audit-remediation `_reload_env_from_marker()` handler
(per `docs/plans/2026-05-18-comprehensive-audit-remediation.md` line 340), any
future SIGHUP handler — invokes this same function. The precedence chain and
`override=False` invariant hold across all call sites.

## Precedence

```
operator-exported env  >  wiring.env  >  flag defaults
```

`load_dotenv(path, override=False)` enforces this: if a key is already present in
`os.environ` at the time `_load_wiring_env` runs, the wiring.env value is
**silently skipped**. An operator who does `export PROJECT_RAG_ENGINE_VECTOR_STORE=…`
in their shell always wins.

This inverts the historical bug (audit finding P1-5): the old `.sh` wrapper sourced
wiring.env *after* its own `_project_root` resolution, so `PROJECT_RAG_PROJECT_ROOT`
in wiring.env had zero effect on the wrapper's path decisions. The daemon-direct
approach runs the dotenv load in `main()` before any env-reading code path.

## Removed: shell-sourcing in wrappers

**Removed** by spinoff `docs/plans/2026-05-18-daemon-reads-wiring-env-directly.md`.

The two wrapper scripts previously sourced wiring.env before launching the daemon:

- `scripts/ensure-project-rag-server.sh` lines 32–36 (restart branch) and 80–85
  (pre-daemon-launch).
- `scripts/ensure-project-rag-server.ps1` lines 127–141 (full wiring block).

Those blocks are replaced with trail comments in the source (the comment text
explains what was removed and why). The sourcing was removed because:

- **Audit P1-3:** PS1 quoting heuristic missed tab-in-value and Windows paths
  containing `&`/`(`/`)`.
- **Audit P1-5:** `.sh` sourced wiring.env *after* `_project_root` resolution, so
  `PROJECT_RAG_PROJECT_ROOT` in wiring.env had no effect.
- **Audit P1-6:** PS1/SH parsers diverged on quoting, continuation lines, and
  shell-metacharacter handling.
- **Audit Theme E ("closed-circuit deprecation"):** the sourcing pattern was the
  recurring class of bug being closed by this spinoff.

## Producer-side open question — project-scoped wiring

The current location `~/.project-rag/wiring.env` is machine-local (global across
all project roots on the machine). A project-scoped location
(`<project_root>/.project-rag/wiring.env`) is a **producer-side design call**
that lives with `scripts/wire.py`, not with the daemon reader.

This spinoff is **consumer-only** and does not change where `wire.py` writes. The
machine-scoped location works today for project-rag-on-project-rag (the canonical
live Python consumer per `CLAUDE.md § Ambition`) because there is exactly one
daemon serving one project root, and `~/.project-rag/` is unambiguous on the
machine. When a second Python consumer ships (e.g., `example-repo`), the
producer-side plan re-opens the location question.

Note: a circular-bootstrap risk exists for project-scoped wiring — the daemon
needs to know `project_root` to find wiring.env, but wiring.env might declare
`PROJECT_RAG_PROJECT_ROOT`. The consumer's `project_root` parameter in
`_load_wiring_env` is accepted for forward-compat but currently unused while the
machine-scoped path is canonical.

## Cross-references

- **Writer:** `scripts/wire.py` — AD-16 implementation; conflict-fail-loud contract.
- **Reader:** `project_rag_mcp/project_rag_server.py::_load_wiring_env` — dotenv consumer,
  canonical reload primitive.
- **Conflict-fail-loud spec:** `docs/plans/2026-05-17-engine-rag-setup-doctor-catalog.md` L-5.
- **Audit synthesis Theme E:** `tasks/comprehensive-audit-2026-05-18/SYNTHESIS.md`.
- **Spinoff plan:** `docs/plans/2026-05-18-daemon-reads-wiring-env-directly.md`.
- **Operator-facing context:** `docs/wiki/project-rag-install-and-dogfood.md`
  § wire-project-rag-server.

## Verify a config-key against its RESOLVER, not the first matching file

A plan's substrate-verification can land on an inert placeholder. The example-store-repo rename assumed the machine-local key lived in `registry.toml` as an empty entry that resolved "by existence" — but the actual reader (`resolve_sibling_repo` rung 4) reads `registry.local.toml` **only**, and keys on a non-empty **VALUE**, not on the file merely containing the key. The premise matched a filename; it did not match the file the code consults.

**Rule:** before asserting any "config-file X carries key K with semantics S" premise, trace the actual reader code — grep the resolver and confirm *which* file it opens and *what* it keys on (existence vs. non-empty value vs. a specific field). A matching filename is not the same as the file the reader consults, and a present-but-empty entry is not the same as a resolvable value. This is the config-resolution analog of the reader-precedence discipline documented above for `wiring.env`: the file that looks authoritative and the file the code actually reads are two different questions.

*Source: example-store-repo rename.*

## `HOME` / `USERPROFILE` / `CLAUDE_HOME` — fail-loud vs warn-and-ignore

The three home-directory anchors have **different validity semantics by origin**, and conflating them produces silently-broken installs:

- **`CLAUDE_HOME` — operator override → fail-loud `ValueError` on relative value.** This env var exists only because an operator chose to set it. A relative value (`./claude`, `claude-home`) is a configuration error worth surfacing immediately. Silent fall-through hides operator intent and produces process-cwd-anchored installs whose later joins look correct in logs but resolve to wherever Claude Code happened to launch from.

- **`HOME` / `USERPROFILE` — OS-provided → warn-and-ignore relative values, try the next candidate.** These are inherited from the shell / process environment; the program did not ask for them. A relative value here is typically an OS quirk or transient shell state, not operator intent. Warn-and-ignore preserves the resolution chain (next candidate gets a chance) and avoids hard-failing well-installed users on environment noise we did not cause.

**Why the polarity matters.** Both classes end at the same join — `home_dir() / ".claude" / ...` — so a relative anchor at *any* layer of the chain anchors the whole tree at the process cwd. Catching the operator-set case loudly and the OS-supplied case quietly keeps the loud signal aimed at the layer where the human can act, and keeps the install path resilient to environments we do not control.

Empirical: `2026-05-28-claude-home-exec-hardening.md` introduced this split after a sequence of OS-environment-driven relative-path resolutions silently produced cwd-anchored installs.
