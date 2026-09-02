"""
coordinator-harvest-deferrals — PM-gated deferral harvest from a plan's
machine-parseable ## Tasks task-spine into the improvement queue / lessons-outbox.

Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, and correct
for this shape. On Windows, this file's co-located `.cmd` twin wins via
`PATHEXT` when invoked as a bareword, so the shebang is never read there; on
macOS/Linux `python3` is the right interpreter. Caution: callers must invoke
via the extensionless name or a resolved-interpreter prefix, never a bareword
`.py` through git-bash — git-bash DOES honor the shebang and would exec-127
with no `python3` present. See the carve-out in DoE-claude's
coordinator/docs/wiki/bash-on-windows-gotchas.md § Carve-out (cross-repo —
this wiki lives in the DoE-claude repo, not here).

Spec backlink: docs/plans/2026-07-09-plan-full-coverage-and-deferred-harvest.md § Architecture (C4a)

Purpose: read a plan's `## Tasks` fenced ```yaml plan-tasks``` block (the pinned
task-spine contract — see coordinator/schemas/plan-tasks.schema.json), select rows
where `disposition: backlogged` AND `pm_approved: true` — or, for a row carrying
no `disposition` at all, `deferred: true` AND `pm_approved: true` treated as
legacy-equivalent to `backlogged` intent (D8,
docs/plans/2026-07-27-plan-line-item-resolution-model.md § C5b — the field's
OTHER live consumer, alongside plan-coverage-checker, that D8 assigns the same
legacy-equivalence rule), and route each selected row to the matching write
seam:

  - change_kind in the 11-value project-tier improvement-queue subset
    (script-edit, skill-edit, wiki-append, wiki-new, hook-edit, agent-prompt-edit,
    doc-edit, test-edit, code-edit, config-edit, verification)
    -> coordinator-queue-append --schema improvement-queue --queue-scope <row's
       queue_scope, default project> --status open

  - change_kind in {doctrine-edit, snippet-sync-update} (the universal-doctrine
    slice of the wider change_kind enum, NOT accepted by improvement-queue at
    project scope)
    -> coordinator-lesson-promote --target-wiki <row's surface>

This script does NOT build a parallel YAML emitter — it shells out to the two
existing write-seam CLIs above and reuses their validation/output-path logic
verbatim.

Parser-locate rule (pinned contract, plan-tasks.schema.json): a plan's ## Tasks
section must carry EXACTLY ONE fenced block with info-string `yaml plan-tasks`
directly under the `## Tasks` heading. Zero such blocks, or more than one, is a
defined error for schema/coverage-tooling but is WARN-AND-SKIP here (exit 0) —
a plan mid-authoring may not have a spine yet, and the harvest is best-effort,
not a gate.

Selection rule (D8, widened by C5b): a row is a harvest candidate under
EITHER of two mutually-exclusive branches, keyed on whether `disposition` is
present:
  - `disposition: backlogged` AND `pm_approved: true` — the current authoring
    path (`resolve --backlogged`, C5, writes this).
  - No `disposition` key at all (or an empty/falsy one) AND `deferred: true`
    AND `pm_approved: true` — the legacy-equivalent path. A row carrying no
    `disposition` is treated exactly as if it were `disposition: backlogged`,
    the same legacy-equivalence rule D8 assigns plan-coverage-checker, applied
    here at this CLI as the field's OTHER live consumer.
A row carrying BOTH `deferred: true` AND `disposition: backlogged` is selected
by the first branch only (branch selection is `disposition`-presence, not an
OR of the two field checks) — it is never evaluated against the legacy branch,
so it harvests exactly once, not twice. Any row with a NON-backlogged
`disposition` (`open`, `coded`, `spun_off`, `wont_do`) is never a candidate,
regardless of `deferred`'s value — presence of `disposition` always routes
through the first branch, which requires `disposition == "backlogged"`.
`deferred: true` WITHOUT `pm_approved: true` (nor a ratified `disposition`) is
plan-coverage-checker's flag surface (an EM preference is not a scope
decision), NOT this script's concern — such rows are silently left
un-harvested (they will be picked up automatically once the PM flips
pm_approved and this script re-runs, by the ordinary idempotency-key mechanism
below). ## Anti-scope prose items are never harvested — they are not part of
the ## Tasks YAML spine at all, so they are structurally unreachable here;
this comment documents the invariant for a future reader who might be tempted
to add prose-section parsing.

The two-arm split above is the LEGACY rule and applies only when the plan's
frontmatter does NOT carry a `grouping_approvals` key at all (Review:
code-reviewer Finding 3 — this section originally never mentioned the
governed case). On a GOVERNED plan (frontmatter carries `grouping_approvals`,
bare presence — see `is_governed_plan`) the per-row `pm_approved` boolean is
NOT consulted, at all, and the legacy `deferred: true` arm is unreachable by
construction: a candidate is a well-formed row with `disposition ==
"backlogged"` whose `defer` grouping in `grouping_approvals` reads `status:
approved` with a digest matching a fresh recomputation over the spine's
CURRENT membership. See `_select_harvest_candidates`'s own docstring for the
full governed-vs-legacy axis writeup — this section states the same rule at
module-doc granularity so a reader trusting only this docstring still learns
that governed-plan behaviour exists and never falls through to the `deferred`
arm.

Malformed-row disposition: a row missing a required field (id, title, body,
change_kind, surface) — `deferred` is NOT in this required set (it is optional
per plan-tasks.schema.json; a row may carry `disposition: backlogged` with no
`deferred` field at all) — or otherwise failing to parse as a well-formed
task object is SKIPPED-WITH-WARNING (printed to stderr, counted, harvest
continues) — never a hard failure. This mirrors the plan-tasks contract's
defensive parse-or-skip posture; the coverage-checker (not this script) is the
enforcement surface that flags malformed rows.

Idempotency: keyed on (plan_id, row id). The plan's frontmatter `plan_id` field
(read from the YAML frontmatter block at the top of the plan markdown file) is
combined with the row's `id` to form a stable dedup key, e.g.
"harvest-key: pln-full-coverage-planning-posture-bca96f:D1". This key is
embedded verbatim in the queued/promoted entry's `evidence` field (the cleanest
existing carrier on both improvement-queue and lessons-outbox schemas — both
support a free-text `evidence: string` optional field intended for exactly this
kind of provenance pointer; adding a new field to either schema was rejected as
unnecessary schema churn for a value that already fits the existing contract).
Before writing a new entry, this script greps the plan's own harvest routing
target (project-scope: <repo-or-QUEUE_APPEND_OUTPUT_ROOT>/state/improvement-queue/*.yaml;
central-scope: <claude-klabauter-root-or-QUEUE_APPEND_OUTPUT_ROOT>/state/improvement-queue/*.yaml; lessons:
<doe-root-or-LESSON_PROMOTE_OUTBOX_ROOT>/state/lessons-outbox/*.yaml) for that exact
harvest-key string in the `evidence:` field of already-written entries. A match means
"already harvested from this plan" — skip, do not double-write. This is a best-effort
text scan (not a database query) but is sufficient given the low write-volume and
human-readable YAML corpus of these directories. The scan-dir resolution (see
_candidate_search_dirs) mirrors coordinator-queue-append's and coordinator-lesson-
promote's own root resolution COMPLETELY, not just their env-override leg: env
overrides (QUEUE_APPEND_OUTPUT_ROOT / LESSON_PROMOTE_OUTBOX_ROOT) win first exactly
as the write seams check them first, and when unset the central-scope
improvement-queue leg calls cli_shared.claude_klabauter_root() (repos.claude_klabauter) while
the lessons-outbox leg calls coordinator_registry.doe_root() (repos.doe_claude) —
the identical functions coordinator-queue-append's central branch and
coordinator-lesson-promote's _outbox_root() respectively call — so scan-root cannot
drift from write-root under either machine-local-registry-resolved case (the
expected steady state on any installed machine) any more than under the
respective env-var case. (Review: code-reviewer slice2 Finding 1 — an earlier
revision of this docstring/comment claimed env-override-precedence parity while
the implementation only reproduced the DOE_ROOT-env leg of doe_root()'s
three-step resolution for BOTH legs, silently dropping the machine-local-registry
leg; a later fix closed that gap but scanned doe_root() for the central-scope
improvement-queue leg too, missing commit 5b908173's repoint of that leg's
write-seam to cli_shared.claude_klabauter_root() — this revision fixes both legs'
implementation and this claim.)

--dry-run: prints what WOULD be queued/promoted (title, change_kind, target,
dedup-key, already-harvested disposition) without invoking either write-seam
CLI and without any filesystem writes.

Invocation:
  coordinator-harvest-deferrals --plan docs/plans/2026-07-09-some-plan.md [--dry-run]

Negative-spec: this script does NOT parse ## Anti-scope or any other prose
section of the plan — only the single fenced ```yaml plan-tasks``` block under
## Tasks. It does NOT re-implement queue-append's YAML emission or path
resolution — every actual write is delegated via subprocess to
coordinator-queue-append / coordinator-lesson-promote.
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))

# Review: code-reviewer (slice2 Finding 1) — import the SAME doe_root() the
# write seams (coordinator-queue-append / coordinator-lesson-promote) call,
# instead of re-deriving a partial (env-var-only) approximation of its
# resolution chain. Mirrors the _LIB_DIR sys.path pattern used by both seams.
_LIB_DIR = os.path.join(_BIN_DIR, "lib")

_CLI_CMD_CACHE: dict[str, list[str] | None] = {}

_BOOTSTRAPPED_NAMES = (
    "_resolve_claude_klabauter_root",
    "require_dispatch_engine_on_path",
    "doe_root",
    "_DoeUnresolvable",
    "cli_shared",
    "_claude_klabauter_root",
    "find_cli_cmd",
    "compute_grouping_digest",
    "is_governed_plan",
    "parse_frontmatter",
    "yaml",
)


_BOOTSTRAP_DONE = False


def _bootstrap_engine() -> None:
    """Bind the engine on the DISPATCH axis, then everything that depends on it.

    Idempotent. THE ORDER INSIDE THIS FUNCTION IS THE POINT -- it is one function
    rather than per-use-site deferred imports precisely so the sequence cannot be
    reordered by a later edit. The original comments are preserved verbatim below.

    What moved and what did not: this sequence ran at MODULE scope until now, so
    every import of this file mutated the `sys.path` of a warm server ~50 sessions
    share. Only the trigger moved; the order is byte-for-byte the same.
    """
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    try:

        # Bootstrap on the DISPATCH axis before anything below can bind
        # `coordinator_core` on the LOCATOR axis first. `cli_shared` (imported
        # below) transitively imports `repo_identity`, which resolves and imports
        # `coordinator_core` at ITS OWN module level via the LOCATOR-axis
        # `require_engine_on_path(__file__)` — on a conformant box the two axes can
        # return different roots (see `require_dispatch_engine_on_path`'s own
        # docstring), and once a package is bound in `sys.modules` no later
        # `sys.path` insert can rebind it. Must run before `import cli_shared` /
        # `from coordinator_registry import ...` below.
        import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
        from cc_invoke import _resolve_claude_klabauter_root, require_dispatch_engine_on_path  # noqa: F401
        
        require_dispatch_engine_on_path()
        # LOAD-BEARING, NOT DEAD. Do not delete on an unused-import sweep: this line is
        # what BINDS coordinator_core, and binding it HERE is the whole fix.
        # require_dispatch_engine_on_path() above only mutates sys.path -- it imports
        # nothing. Without this line the next module-level import below (a binder module
        # that resolves on the LOCATOR axis) wins the race and binds coordinator_core off
        # the working tree instead of the dispatch root, and no later sys.path insert can
        # rebind an already-imported package. Removing it restores a silent wrong-tree
        # divergence that require_dispatch_engine_on_path now raises on.
        # Why: docs/plans/2026-08-26-the-seam-reports-what-it-got.md C9,
        # docs/research/engine-provenance-carrier-dependence.md
        import coordinator_core  # noqa: F401
        
        from coordinator_registry import doe_root, _DoeUnresolvable
        
        # cli_shared.claude_klabauter_root() resolves repos.claude_klabauter (CLAUDE_KLABAUTER_ROOT env ->
        # machine-local registry) — the SAME function coordinator-queue-append's
        # _output_path() central branch calls for improvement-queue since commit
        # 5b908173 ("central scope routes to claude-klabauter, not DoE — reconcile the two
        # implementations", 2026-07-23). doe_root() resolves the DIFFERENT
        # repos.doe_claude key and is the correct root ONLY for lessons-outbox
        # (coordinator-lesson-promote's _outbox_root() was not touched by that
        # commit). Importing both, distinctly, is deliberate — do not conflate them.
        import cli_shared
        
        # coordinator-queue-append / coordinator-lesson-promote are extensionless
        # Python scripts — CreateProcess can't exec them directly on Windows
        # (WinError 193). find_cli_cmd() resolves each to a Windows-safe argv
        # prefix (PATH probe, then sys.executable + sibling-path fallback);
        # resolution is memoized per CLI per process (below) since _harvest()
        # calls these once per row and the probe itself spawns subprocesses.
        #
        # `_queue_append_locator` is a sibling module in THIS script's own
        # directory (`coordinator/bin/`, not `lib/`) — running this script directly
        # (`python3 coordinator-harvest-deferrals`) implicitly puts `_BIN_DIR` on
        # `sys.path[0]`, but the in-process dispatch every consumes-manifest CLI is
        # ALSO invoked through (`workstream_complete.apply._load_cli_module`, via
        # `importlib.util.spec_from_file_location`) never gets that implicit entry
        # — only an actual `__main__` script does. `import lib` (above) only puts
        # `_LIB_DIR` on `sys.path`, never `_BIN_DIR` itself, so it does not cover
        # this import. Left unguarded, this import always raised
        # `ModuleNotFoundError` under in-process dispatch, so every
        # `d-harvest-deferrals-*` directive (workstream_complete/directives_lessons_
        # plan.py's `build_deferral_harvest_directives`, ungated, fires once per
        # governing plan) always landed in `report["failed"]` (2026-07-27
        # arg-mismatch audit — a load-time defect found alongside, not caused by,
        # the prog-slot mismatch this audit chunk targets). The lazy-bootstrap
        # sweep (2026-08) deleted the `_BIN_DIR` sys.path insert that fixed this
        # while moving the import into this function, silently reintroducing the
        # regression; restored here, guarded and idempotent, scoped to this one
        # sibling-module import (NOT a general per-file `sys.path` preamble —
        # `import lib` above already covers everything under `_LIB_DIR`).
        if _BIN_DIR not in sys.path:
            sys.path.insert(0, _BIN_DIR)
        from _queue_append_locator import find_cli_cmd
        
        # Grouping-approval contract (2026-07-29). Selection on a GOVERNED plan keys
        # on the plan's approved `defer` grouping rather than each row's pm_approved
        # boolean — see `_select_harvest_candidates`.
        #
        # `coordinator_core` is already bound on the dispatch axis by the bootstrap
        # above (moved ahead of `cli_shared`/`coordinator_registry` — see the comment
        # there); this import just reaches into the now-established package.
        from coordinator_core.frontmatter.schema_validate import (
            compute_grouping_digest,
            is_governed_plan,
            parse_frontmatter,
        )

        _claude_klabauter_root = cli_shared.claude_klabauter_root

        # Optional PyYAML — degrade to the stdlib-only fallback parser
        # (`_minimal_yaml_list_parse`) on an install without it, same
        # graceful-degrade posture this bootstrap already applies to every
        # other name here. A bare `try/except ImportError: yaml = None`
        # used to sit at MODULE scope; moved in here for the same reason as
        # every other import in this function (see module docstring).
        try:
            import yaml  # type: ignore  # noqa: F401
        except ImportError:
            yaml = None  # type: ignore

        # Publish LAST, once every name is bound -- a publish placed mid-function
        # silently omits everything imported after it, and the omission surfaces as a
        # KeyError from `__getattr__` rather than as anything pointing here.
        #
        # NEVER overwrite a name a caller already installed: a test that monkeypatches
        # `doe_root` on this module and then calls a function that triggers the
        # bootstrap would otherwise have its patch replaced by the real resolver on
        # the first call, and the failure reads as "the patch never applied".
    finally:
        # Publish whatever bound, EVEN IF a later import raised. A bootstrap that
        # dies partway would otherwise lose the names that did bind, and the next
        # caller sees a missing name instead of the original exception -- which is
        # a strictly worse error than the one that actually happened.
        _resolved = locals()
        for _name in _BOOTSTRAPPED_NAMES:
            if _name not in globals() and _name in _resolved:
                globals()[_name] = _resolved[_name]

    # Only on a clean run: a partial bootstrap must stay retryable.
    _BOOTSTRAP_DONE = True


def __getattr__(name: str):
    """PEP 562 hook: a consumer that imports this module rather than executing it
    -- its own test suite, or `workstream_complete.apply._load_cli_module`'s
    in-process dispatch -- reaches these names before `main()` runs. Without this,
    deferring the bootstrap leaves them simply absent, which is what forced an
    earlier repair pass to hoist the whole block back to module scope. A
    `global`-bound name is module-visible only after its binder has been called;
    this hook is what calls it.
    """
    if name in _BOOTSTRAPPED_NAMES:
        _bootstrap_engine()
        if name not in globals():
            # The sentinel says bootstrapped, yet this name is absent: a prior
            # partial run published some names and set nothing else. Force one
            # re-run rather than surfacing a KeyError from the line below, which
            # names the symptom and hides which import actually failed.
            global _BOOTSTRAP_DONE
            _BOOTSTRAP_DONE = False
            _bootstrap_engine()
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r} after bootstrap"
            ) from None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _resolve_cli_cmd(cli_name: str) -> list[str] | None:
    """Resolve `cli_name` to a subprocess argv prefix, once per process."""
    _bootstrap_engine()
    if cli_name not in _CLI_CMD_CACHE:
        _CLI_CMD_CACHE[cli_name] = find_cli_cmd(_BIN_DIR, cli_name)
    return _CLI_CMD_CACHE[cli_name]

# The 11-value project-tier improvement-queue-eligible change_kind subset.
# SSOT: coordinator/docs/wiki/lessons-outbox-schema.md § Change-kind enum
# (the universal enum); this is the improvement-queue-eligible slice of it.
# Hand-maintained mirror of a DoE-owned enum — when the SSOT gains a
# project-tier member, it must be added here too or the harvest treats it as
# unroutable (and, since 2026-07-29, fails loud on a pm_approved row rather
# than dropping it silently).
#
# `verification` (added 2026-07-29, DoE 1239761c1) is the one member whose
# deliverable is evidence rather than a diff — a hardware- or
# environment-gated re-run, a manual dogfood. It is the only member naming no
# surface to edit, which is the point: this shape gets deferred precisely
# because the gating resource is not to hand at plan time. A defect the
# verification finds gets its own row with a change-shaped kind.
#
# Negative-spec: `script-port` is NOT a member and does not become one. These
# values name the SURFACE changed, not the flavour of the change — a
# bash-to-Python port of a `bin/` utility is `script-edit`. A coined
# work-shape token routes nowhere by design (DoE 1239761c1 decided this
# explicitly after such a token dropped a pm_approved row here).
_QUEUE_ELIGIBLE_CHANGE_KINDS = frozenset(
    {
        "script-edit",
        "skill-edit",
        "wiki-append",
        "wiki-new",
        "hook-edit",
        "agent-prompt-edit",
        "doc-edit",
        "test-edit",
        "code-edit",
        "config-edit",
        "verification",
    }
)

# The doctrine-class change_kind values routed to coordinator-lesson-promote
# instead of coordinator-queue-append (rejected by improvement-queue at
# project scope per its schema's change_kind enum).
_LESSON_PROMOTE_CHANGE_KINDS = frozenset({"doctrine-edit", "snippet-sync-update"})

# "deferred" is deliberately NOT in this set (C5b, D8) — it is optional per
# plan-tasks.schema.json now that disposition is the authoring surface; a
# disposition: backlogged row may carry no `deferred` field at all.
_REQUIRED_ROW_FIELDS = ("id", "title", "change_kind", "surface")

_VALID_QUEUE_SCOPES = ("project", "central")

_SUBPROCESS_TIMEOUT_SECS = 30


def _child_identity_env() -> dict:
    """The environment both spawns below must run under, never the inherited one.

    Each `cmd` here names a MUTATING, touch-recording CLI. Inherited identity
    vars name whoever spawned the process this one runs inside — the warm
    server's own spawner when a ceremony reaches this code in-process — so the
    child files its writes under a live peer and the author's later commit is
    refused on a provably-foreign owner. See
    `session.core.subprocess_identity_env` for the measured instance and for
    why an unresolvable identity strips the vars rather than inheriting them.

    Import is call-time: `_bootstrap_engine()` has run by the time either
    caller reaches its spawn, and module scope here stays engine-free.
    """
    _bootstrap_engine()
    from coordinator_core.session.core import subprocess_identity_env

    return subprocess_identity_env()


# Write-seam env-override names — MUST mirror the write seams' own resolution
# precedence exactly (see _candidate_search_dirs' write-seam-parity comment
# below for the failure mode this guards against).
_QUEUE_APPEND_OUTPUT_ROOT_ENV = "QUEUE_APPEND_OUTPUT_ROOT"


def _isolation_root(env_var: str, caller_name: str) -> str | None:
    """Local twin of `bin/lib/cli_shared.isolation_root_if_under_test` — see that
    docstring for the defect this closes.

    Deliberately dependency-free (stdlib only, no `cli_shared` import) rather than
    delegating: this module's bootstrap is order-sensitive, and forcing it early
    just to read an env var re-resolves the registry inside a caller's
    env-stripped window and changes which roots resolve. The predicate is four
    lines; the ordering hazard is not worth sharing them.
    """
    value = (os.environ.get(env_var) or "").strip()
    if not value:
        return None
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return value
    # WARNS EVERY TIME, not once. The dedup set that used to live at module
    # scope made this warn-once-per-PROCESS, and this name warm-serves: in a
    # warm server the process outlives the request, so the first caller
    # consumed the warning and every later caller was silently redirected with
    # no signal at all. Per-request is the semantic that was wanted and module
    # state cannot express it. The path is rare (an inherited isolation env var
    # outside a test run), so repeating it costs a line on stderr and buys back
    # the signal.
    print(
        f"{caller_name}: ignoring inherited {env_var}={value} — a test-isolation "
        f"redirect outside a test run. Writing to the resolved repo path instead.",
        file=sys.stderr,
    )
    return None

_LESSON_PROMOTE_OUTBOX_ROOT_ENV = "LESSON_PROMOTE_OUTBOX_ROOT"


# ---------------------------------------------------------------------------
# Minimal fallback YAML-list parser (no PyYAML on the machine) — reused shape
# from the coordinator's stdlib-only convention. Handles the specific shape
# the ## Tasks block requires: a top-level YAML list of flat-ish task objects
# with optional `body: |` literal block scalars. Falls back only when the
# `yaml` module is unavailable; PyYAML is preferred when present.
# ---------------------------------------------------------------------------


def _minimal_yaml_list_parse(text: str) -> list[dict]:
    """Parse a YAML list of task-spine row objects without PyYAML.

    Handles: `- id: X` list-item starts, `key: value` scalar fields (quoted or
    bare), `key: |` literal block scalars (indented continuation lines), and
    `#` full-line comments between items. This is intentionally narrow — it
    only needs to round-trip the task-spine row shape defined in
    plan-tasks.schema.json, not general YAML.
    """
    rows: list[dict] = []
    current: dict | None = None
    in_block_key: str | None = None
    block_lines: list[str] = []
    block_indent: int | None = None

    def _flush_block() -> None:
        nonlocal in_block_key, block_lines, block_indent
        if current is not None and in_block_key is not None:
            current[in_block_key] = "\n".join(block_lines) + ("\n" if block_lines else "")
        in_block_key = None
        block_lines = []
        block_indent = None

    for raw_line in text.splitlines():
        if in_block_key is not None:
            if raw_line.strip() == "" or (
                block_indent is not None
                and (len(raw_line) - len(raw_line.lstrip(" "))) >= block_indent
            ):
                stripped = raw_line[block_indent:] if block_indent else raw_line.strip()
                if raw_line.strip() == "":
                    block_lines.append("")
                else:
                    block_lines.append(stripped)
                continue
            _flush_block()

        line = raw_line.rstrip("\n")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("- "):
            if current is not None:
                rows.append(current)
            current = {}
            stripped = stripped[2:].strip()
            if not stripped:
                continue
            # falls through to key: value parsing below on the remainder

        if current is None:
            continue

        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", stripped)
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip()

        if value == "|" or value == "|-" or value.startswith("|"):
            in_block_key = key
            block_lines = []
            # Block indent is determined by the first continuation line.
            block_indent = None
            continue

        # Strip a trailing inline comment (space/tab preceded '#'), matching
        # the queue-append/_lesson-promote quoting convention's negative-spec.
        if not (value.startswith('"') or value.startswith("'")):
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()

        if value.startswith('"') and value.endswith('"') and len(value) >= 2:
            value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        elif value.startswith("'") and value.endswith("'") and len(value) >= 2:
            value = value[1:-1]
        elif value.lower() == "true":
            value = True  # type: ignore[assignment]
        elif value.lower() == "false":
            value = False  # type: ignore[assignment]

        current[key] = value

    _flush_block()
    if current is not None:
        rows.append(current)

    # Second pass: block continuation lines need their leading-indent computed
    # from the first non-empty continuation line, not the key line itself.
    # The single-pass loop above sets block_indent=None: fix up by re-deriving
    # indentation from the raw block text captured. Since this is a narrow
    # fallback (only exercised when PyYAML is absent) we recompute using a
    # simpler two-pass strategy: re-run block extraction using regex per row
    # is unnecessary — the primary path (PyYAML present) is exercised in
    # normal operation; this fallback only needs to not crash and to
    # best-effort recover fields other than deeply-nested block scalars.
    return rows


# ---------------------------------------------------------------------------
# ## Tasks fenced-block location (parser-locate rule)
# ---------------------------------------------------------------------------

_TASKS_HEADING_RE = re.compile(r"^##\s+Tasks\s*$", re.MULTILINE)
_FENCE_RE = re.compile(r"```yaml plan-tasks\n(.*?)\n```", re.DOTALL)


_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _locate_tasks_block(plan_text: str) -> str | None:
    """Return the fenced ```yaml plan-tasks``` block body directly under
    the first '## Tasks' heading, or None per the parser-locate rule.

    Per the pinned contract: exactly one such fenced block directly under
    '## Tasks' is well-formed. Zero, or the presence of more than one fenced
    `yaml plan-tasks` block ANYWHERE in the document, is a defined error —
    this function returns None in either case so the caller can warn-and-skip.

    HTML-comment blanking (silent-data-loss fix): the plan-template's
    authoring comment under '## Tasks' embeds a literal
    ```` ```yaml plan-tasks``` ```` string as documentation, and often sits
    as non-blank content between the heading and the real fence. Both of
    those template-comment shapes used to trip this function's guards and
    return None — which made the caller warn-and-skip on EVERY plan that
    still carried the unedited template comment, silently losing any
    deferred:true rows in that plan's real spine. Fix: scan against a
    comment-blanked COPY of plan_text (each `<!-- ... -->` span replaced by
    an equal-length run of spaces, so all byte offsets — and hence
    `.start()`/slice math against the ORIGINAL plan_text — stay valid).
    Genuine errors are unaffected: a plan with two REAL (non-comment) fenced
    blocks still counts as 2 fences post-blanking and still returns None
    (see fixtures/plan-tasks-spine/multiple-fenced-blocks.md).
    """
    scan_text = _HTML_COMMENT_RE.sub(lambda m: " " * len(m.group(0)), plan_text)

    all_fences = _FENCE_RE.findall(scan_text)
    if len(all_fences) != 1:
        return None

    heading_match = _TASKS_HEADING_RE.search(scan_text)
    if heading_match is None:
        return None

    after_heading = scan_text[heading_match.end():]

    # Containment, not adjacency: the fence must live INSIDE the '## Tasks'
    # section, bounded at the next '## ' heading (or end of document). Same
    # section-bounding shape as _tasks_section_has_deferred_marker below.
    next_heading = re.search(r"^##\s+\S", after_heading, re.MULTILINE)
    section_text = (
        after_heading[: next_heading.start()] if next_heading else after_heading
    )

    fence_in_section = _FENCE_RE.search(section_text)
    if fence_in_section is None:
        return None

    # Offsets are identical between scan_text and plan_text (comment
    # blanking is length-preserving), so re-slice plan_text with the same
    # span to return the ORIGINAL (un-blanked) block body. The yaml block
    # itself contains no HTML comments, so this is a no-op for well-formed
    # plans — the returned body is byte-identical either way.
    start, end = fence_in_section.span(1)
    heading_offset = heading_match.end()
    return plan_text[heading_offset + start : heading_offset + end]


_DEFERRED_TRUE_RE = re.compile(r"^\s*deferred:\s*true\s*$", re.MULTILINE)


def _tasks_section_has_deferred_marker(plan_text: str) -> bool:
    """Belt-and-suspenders silent-data-loss guard: does the '## Tasks'
    region (heading to next '## ' heading, or end of document) contain a
    `deferred: true` line, even though `_locate_tasks_block` could not
    locate a well-formed fenced block? If so, this is the exact silent-loss
    shape this fix targets — the caller escalates to a loud, non-zero-exit
    error instead of the default soft warn-and-skip.
    """
    heading_match = _TASKS_HEADING_RE.search(plan_text)
    if heading_match is None:
        return False
    rest = plan_text[heading_match.end():]
    next_heading = re.search(r"^##\s+\S", rest, re.MULTILINE)
    section = rest[: next_heading.start()] if next_heading else rest
    return _DEFERRED_TRUE_RE.search(section) is not None


def _parse_plan_id(plan_text: str) -> str | None:
    """Extract `plan_id: "..."` from the plan's YAML frontmatter block."""
    fm_match = re.match(r"^---\n(.*?)\n---\n", plan_text, re.DOTALL)
    if fm_match is None:
        return None
    fm = fm_match.group(1)
    m = re.search(r'^plan_id:\s*"?([^"\n]+?)"?\s*$', fm, re.MULTILINE)
    if m is None:
        return None
    return m.group(1).strip()


# ---------------------------------------------------------------------------
# Row parsing + validation
# ---------------------------------------------------------------------------


def _parse_rows(tasks_yaml_text: str) -> tuple[list[dict], int]:
    """Parse the fenced block body into a list of row dicts.

    Returns (rows, parse_error_count). A top-level parse failure (the whole
    block is not a YAML list) yields ([], 1) — treated by the caller as
    "nothing to harvest, warn and skip" rather than a hard crash, since a
    plan mid-authoring may have a transiently malformed spine.
    """
    _bootstrap_engine()
    if yaml is not None:
        try:
            data = yaml.safe_load(tasks_yaml_text)
        except Exception as exc:  # noqa: BLE001 — malformed YAML is data, not a bug
            print(
                f"warn: coordinator-harvest-deferrals: ## Tasks block failed to parse as YAML: {exc}",
                file=sys.stderr,
            )
            return [], 1
        if not isinstance(data, list):
            print(
                "warn: coordinator-harvest-deferrals: ## Tasks block did not parse to a YAML list — skipping harvest.",
                file=sys.stderr,
            )
            return [], 1
        return [row for row in data if isinstance(row, dict)], 0

    # Fallback: no PyYAML available.
    rows = _minimal_yaml_list_parse(tasks_yaml_text)
    return rows, 0


def _row_is_well_formed(row: dict) -> str | None:
    """Return None if row has all required fields, else a warning string."""
    missing = [f for f in _REQUIRED_ROW_FIELDS if f not in row or row[f] in (None, "")]
    if missing:
        row_id = row.get("id", "<unknown>")
        return f"row '{row_id}' missing required field(s): {', '.join(missing)}"
    return None


def _select_harvest_candidates(
    rows: list[dict],
    *,
    plan_fm: dict | None = None,
) -> tuple[list[dict], list[str], int]:
    """Split rows into (candidates, warnings, skipped_malformed_count).

    Selection has TWO axes, and keeping them straight matters — DoE's memo
    framed this as "both arms need re-pointing at the grouping predicate",
    which conflates them:

    - The LEGACY-vs-GOVERNED axis is a property of the PLAN (does its
      frontmatter carry the `grouping_approvals` key at all — bare presence,
      no `schema_version` conjunct; see `is_governed_plan` in
      schema_validate.py), resolved once by the caller and passed in as
      `plan_fm`.
    - The two-arm split below is a property of each ROW (is `disposition`
      present?), and exists only to read the legacy `deferred` vocabulary.

    They are orthogonal. Branching the wrong one silently opens the legacy
    corpus to ungated harvest.

    On a GOVERNED plan a candidate is a well-formed row with
    `disposition == "backlogged"` whose `defer` grouping reads
    `status: approved` with a digest matching a fresh recomputation over the
    current spine membership. The per-row `pm_approved` boolean is not
    consulted, and the legacy `deferred` arm is unreachable by construction
    (see the inline note).

    On a LEGACY plan (the default, and today's behaviour exactly) a candidate
    is a well-formed row meeting either branch (D8, widened by C5b — see the
    module docstring's "Selection rule" for the full rationale):
      - `disposition == "backlogged"` AND `pm_approved is True` (the current
        authoring path — `resolve --backlogged`, C5, writes this).
      - `disposition` ABSENT (no key, or a falsy value) AND `deferred is True`
        AND `pm_approved is True` (the legacy-equivalent path).
    Branch selection keys on `disposition` PRESENCE, not an OR of both field
    checks — a row carrying BOTH `deferred: true` and
    `disposition: backlogged` is evaluated ONLY against the first branch, so
    it is selected exactly once, never twice. A row with any other
    `disposition` value (`open`, `coded`, `spun_off`, `wont_do`) is never a
    candidate, regardless of `deferred`.

    Rows failing the well-formed check are SKIPPED-WITH-WARNING (never crash).
    """
    _bootstrap_engine()
    governed = is_governed_plan(plan_fm) if isinstance(plan_fm, dict) else False
    candidates: list[dict] = []
    warnings: list[str] = []
    malformed_count = 0

    # Plan-level, computed once: is the `defer` grouping approved over a
    # cut-set matching this spine's CURRENT membership? On a governed plan
    # this replaces the per-row pm_approved boolean entirely.
    defer_approved = False
    if governed and isinstance(plan_fm, dict):
        blocks = plan_fm.get("grouping_approvals")
        if not isinstance(blocks, dict):
            # Presence-only is_governed_plan already set governed=True; a
            # non-dict grouping_approvals is malformed frontmatter, not an
            # absent one. Never crash and never select — same skip-with-
            # warning discipline as a malformed row (see _row_is_well_formed
            # below), just at plan level instead of row level.
            warnings.append(
                "plan frontmatter 'grouping_approvals' is present but not a "
                "mapping — treating the 'defer' grouping as unapproved"
            )
        else:
            block = blocks.get("defer")
            if isinstance(block, dict) and block.get("status") == "approved":
                defer_approved = block.get("digest") == compute_grouping_digest(rows, "defer")

    for row in rows:
        problem = _row_is_well_formed(row)
        if problem is not None:
            warnings.append(problem)
            malformed_count += 1
            continue

        disposition = row.get("disposition")

        if governed:
            # Only the disposition arm exists on a governed plan. The legacy
            # `deferred: true` arm is deliberately NOT reachable here: a row
            # with no disposition defaults to `open`, which lands in the `do`
            # grouping and is not a deferral at all. Honouring the legacy arm
            # on a governed plan would harvest a row into the queue without
            # any grouping ever having been approved — the exact hole DoE
            # warned about in "Vocabulary — deferred: true is legacy on both
            # sides". Gate on disposition; read-tolerate deferred.
            is_candidate = disposition == "backlogged" and defer_approved
        elif disposition:
            is_candidate = disposition == "backlogged" and row.get("pm_approved") is True
        else:
            is_candidate = row.get("deferred") is True and row.get("pm_approved") is True

        if is_candidate:
            candidates.append(row)

    return candidates, warnings, malformed_count


# ---------------------------------------------------------------------------
# Idempotency — dedup key + already-harvested check
# ---------------------------------------------------------------------------


def _harvest_key(plan_id: str, row_id: str) -> str:
    """Stable dedup key embedded in the written entry's `evidence` field.

    Assumes `row_id` (and `plan_id`) contain no ':' — the key is later matched
    via a plain substring/line scan in `_already_harvested`, not parsed back
    apart, so an embedded ':' would not corrupt matching but would make the key
    ambiguous to a human reader distinguishing plan_id from row_id. Current
    task-spine `id` conventions (short slugs like `D1`) are colon-free; if this
    assumption is ever violated, prefer a JSON-safe delimiter (e.g. `::`).
    (Review: code-reviewer slice2 Finding 3 — nit, documented per suggested fix.)
    """
    return f"harvest-key: {plan_id}:{row_id}"


# Memoization for _repo_root() / _resolved_doe_root() / _resolved_claude_klabauter_root():
# each is a pure read whose answer cannot change within one process's harvest
# run, but _candidate_search_dirs() previously called all three (git
# subprocess + registry-ladder resolution, each potentially its own
# subprocess) once PER CANDIDATE ROW inside _harvest()'s loop — N redundant
# spawns for an answer computed once. This mirrors the existing
# _CLI_CMD_CACHE pattern above (also a per-process, first-call memo). Never
# invalidated mid-process: repo root / doe root / claude-klabauter root are read-only
# machine/worktree facts for the lifetime of a single CLI invocation. Does
# NOT touch the actual per-row write dispatch (_run_queue_append /
# _run_lesson_promote) — each row's mutating write stays one-spawn-per-row so
# one row's failure (a non-zero rc, or a hung child now caught as
# `TimeoutExpired`, both surfaced as a `False` return) never blocks another's;
# there is no per-row `try` inside `_harvest()` itself — the isolation is
# entirely the `_run_*` helpers' return-False contract (Review: staff review
# refuted an earlier revision of this comment that pointed at a "per-row try
# shape" in `_harvest()` that does not exist).
_repo_root_cache: dict[str, str | None] = {}
_resolved_doe_root_cache: dict[str, str | None] = {}
_resolved_claude_klabauter_root_cache: dict[str, str | None] = {}
_UNSET = "<unset>"


def _repo_root() -> str | None:
    if _UNSET not in _repo_root_cache:
        from coordinator_core.git.repo_root import show_toplevel

        _repo_root_cache[_UNSET] = show_toplevel()
    return _repo_root_cache[_UNSET]


def _collect_evidence_lines(search_dirs: list[str]) -> list[str]:
    """Glob + read every `*.yaml` file under `search_dirs` ONCE and return
    every line whose stripped text starts with `evidence:`.

    Hoisted out of the per-row loop (2026-08-15 staff review, Defect 2):
    `search_dirs` is invariant across a whole `_harvest()` run — it depends
    only on env overrides and the process-memoized root resolvers (see the
    `_repo_root_cache` / `_resolved_doe_root_cache` / `_resolved_claude_klabauter_root_cache`
    block above), never on any individual row — yet `_already_harvested` was
    previously called once PER CANDIDATE ROW and re-globbed + re-read EVERY
    `*.yaml` file in up to four directories on each call. This module's own
    `_derive_proposed_action` docstring measures those corpora at 605
    (DoE-claude) and 493 (claude-klabauter) entries: O(rows x ~1100 full file reads)
    for a key set invariant across the loop. Call this once before the loop
    in `_harvest()`; `_already_harvested` below then does an O(1)-per-row
    membership check against the returned list instead of re-scanning disk.
    """
    lines: list[str] = []
    for directory in search_dirs:
        if not directory or not os.path.isdir(directory):
            continue
        for path in glob.glob(os.path.join(directory, "*.yaml")):
            try:
                with open(path, encoding="utf-8") as fh:
                    content = fh.read()
            except OSError:
                continue
            for line in content.splitlines():
                if line.strip().startswith("evidence:"):
                    lines.append(line)
    return lines


def _already_harvested(key: str, evidence_lines: list[str]) -> bool:
    """Best-effort text scan for `key` inside any pre-collected `evidence:`
    line (see `_collect_evidence_lines`, called ONCE per `_harvest()` run,
    not once per row). Returns True on first match.

    Scoped to lines whose stripped text starts with `evidence:` (Review:
    code-reviewer slice2 Finding 4 — an earlier revision scanned the entire
    file content, which could false-positive-match a `body`/other field that
    happens to quote the literal harvest-key string, e.g. documentation prose
    discussing a specific harvest-key example; scoping to the evidence line
    tightens the match to the field this key is actually written into, per
    _harvest()/_run_queue_append()/_run_lesson_promote()'s `--evidence key`
    call site). This substring-match semantics is preserved exactly by the
    2026-08-15 hoist — only the file I/O moved, not the match rule.
    """
    return any(key in line for line in evidence_lines)


def _resolved_doe_root() -> str | None:
    """Call the SAME doe_root() coordinator-lesson-promote's _outbox_root()
    calls, degrading to None on _DoeUnresolvable (mirrors the write seam's own
    WARN+skip-on-unresolvable posture — this is a best-effort scan, never a
    hard requirement).

    doe_root() (repos.doe_claude) is the correct root for lessons-outbox ONLY
    — see _resolved_claude_klabauter_root() below for the central-scope improvement-queue
    leg, which resolves a DIFFERENT registry key as of commit 5b908173.

    Memoized (see _repo_root_cache block above): doe_root()'s own resolution
    ladder can itself spawn a subprocess (machine-local registry probe /
    marketplace-cache rung) and was previously re-run once per harvested row
    via _candidate_search_dirs() inside _harvest()'s loop for an answer that
    cannot change mid-process.
    """
    _bootstrap_engine()
    if _UNSET not in _resolved_doe_root_cache:
        try:
            _resolved_doe_root_cache[_UNSET] = doe_root()
        except _DoeUnresolvable:
            _resolved_doe_root_cache[_UNSET] = None
    return _resolved_doe_root_cache[_UNSET]


def _resolved_claude_klabauter_root() -> str | None:
    """Call the SAME cli_shared.claude_klabauter_root() coordinator-queue-append's
    _output_path() central branch calls (repos.claude_klabauter), never raising
    (mirrors that function's own None-on-unresolvable contract — see its
    docstring's Negative-spec).

    Deliberately distinct from _resolved_doe_root() above: commit 5b908173
    ("central scope routes to claude-klabauter, not DoE — reconcile the two
    implementations", 2026-07-23) repointed coordinator-queue-append's central
    improvement-queue write (both its legacy _output_path() branch and the
    native queue.append op) from doe_root() (repos.doe_claude) to
    _claude_klabauter_root() (repos.claude_klabauter). This function was NOT updated at
    that time — a latent dedup-scan/write-seam root mismatch for the
    central-scope improvement-queue leg, closed here.

    Memoized (see _repo_root_cache block above) for the same reason as
    _resolved_doe_root(): its own resolution ladder can spawn a subprocess
    and was previously re-run once per harvested row.
    """
    _bootstrap_engine()
    if _UNSET not in _resolved_claude_klabauter_root_cache:
        _resolved_claude_klabauter_root_cache[_UNSET] = _claude_klabauter_root()
    return _resolved_claude_klabauter_root_cache[_UNSET]


def _candidate_search_dirs(row: dict) -> list[str]:
    """Directories to scan for an already-harvested match.

    `row` is accepted but unused — the returned dirs never vary by row
    content (only by env overrides and the memoized root resolvers below),
    which is exactly why `_harvest()` now calls this ONCE before its loop
    (see `_collect_evidence_lines`) rather than once per row; the parameter
    is kept so `test_harvest_deferrals_dedup_scan_memoized.py`'s existing
    per-row call shape keeps exercising the same signature.

    Write-seam parity requirement (confirmed double-write failure mode):
    coordinator-queue-append's _output_path() and coordinator-lesson-promote's
    _outbox_root() BOTH check their own env-override var (QUEUE_APPEND_OUTPUT_ROOT /
    LESSON_PROMOTE_OUTBOX_ROOT respectively) FIRST, then fall back to a
    machine-local-registry-resolved root — but NOT the SAME root: lessons-outbox
    falls back to coordinator_registry.doe_root() (repos.doe_claude); central-scope
    improvement-queue falls back to cli_shared.claude_klabauter_root() (repos.claude_klabauter,
    since commit 5b908173). An earlier version of this function only reproduced
    the DOE_ROOT-env leg of doe_root()'s chain for BOTH legs (missing the
    machine-local-registry leg, the expected steady state on any installed
    machine) — that gap is closed here by importing and calling the real seam
    functions directly (Review: code-reviewer slice2 Finding 1 — option (a): call
    the same function the write seams call, so scan-root structurally cannot
    drift from write-root under ANY of either function's legs).

    Order per candidate class:
      - project-scope improvement-queue: QUEUE_APPEND_OUTPUT_ROOT env override
        first (matches coordinator-queue-append's _output_path()), else the
        repo-root fallback (this leg is a git-root proxy for the *current
        repo's own* project-scope queue, which is correct — it mirrors
        _output_path()'s project-scope branch, not the central one).
      - lessons-outbox: LESSON_PROMOTE_OUTBOX_ROOT env override first (matches
        coordinator-lesson-promote's _outbox_root()), else doe_root() (the
        exact function _outbox_root() itself calls).
      - central-scope improvement-queue: QUEUE_APPEND_OUTPUT_ROOT env override
        first, else cli_shared.claude_klabauter_root() (the exact function
        _output_path()'s central branch itself calls, post-5b908173).

    Best-effort throughout: missing/unresolvable roots are silently skipped by
    _already_harvested's isdir guard — this function only builds candidate
    paths, it does not require them to exist.
    """
    dirs: list[str] = []
    root = _repo_root()

    queue_override = _isolation_root(
        _QUEUE_APPEND_OUTPUT_ROOT_ENV, "coordinator-harvest-deferrals"
    )
    if queue_override:
        dirs.append(os.path.join(queue_override, "state", "improvement-queue"))
    elif root:
        dirs.append(os.path.join(root, "state", "improvement-queue"))

    # coordinator-lesson-promote's _outbox_root() returns LESSON_PROMOTE_OUTBOX_ROOT
    # VERBATIM when set (it IS the lessons-outbox dir itself, unlike
    # QUEUE_APPEND_OUTPUT_ROOT which is a root that "state/improvement-queue" is
    # joined onto) — do not append "state/lessons-outbox" onto it here.
    lessons_override = _isolation_root(
        _LESSON_PROMOTE_OUTBOX_ROOT_ENV, "coordinator-harvest-deferrals"
    )
    if lessons_override:
        dirs.append(lessons_override)

    # Central-scope improvement-queue routes through cli_shared.claude_klabauter_root()
    # (repos.claude_klabauter) when its env override is unset — call the real
    # seam function (not a partial re-derivation) so this can never drift.
    if not queue_override:
        resolved_claude_klabauter_root = _resolved_claude_klabauter_root()
        if resolved_claude_klabauter_root:
            dirs.append(os.path.join(resolved_claude_klabauter_root, "state", "improvement-queue"))

    # Lessons-outbox routes through coordinator_registry.doe_root()
    # (repos.doe_claude) when its env override is unset — unaffected by
    # 5b908173, which touched improvement-queue only.
    if not lessons_override:
        resolved_doe_root = _resolved_doe_root()
        if resolved_doe_root:
            dirs.append(os.path.join(resolved_doe_root, "state", "lessons-outbox"))

    return dirs


# ---------------------------------------------------------------------------
# Row routing + dispatch
# ---------------------------------------------------------------------------

# A sentence terminator must be preceded by a non-space char (so a lone "."
# doesn't match) and followed by whitespace-or-end (so a dotted filename or
# version like "boot_sweep.py" or "v1.2" is never split mid-token).
_SENTENCE_TERMINATOR_RE = re.compile(r"(?<=\S)[.!?](?=\s|$)")

_PROPOSED_ACTION_MAX_LEN = 200


def _derive_proposed_action(body: str, title: str, surface: str) -> str:
    """Derive a queue row's proposed_action from its intent-carrying text.

    coordinator-queue-append previously received `str(row["surface"])` for
    both --surface and --proposed-action, so every harvested row landed with
    proposed_action byte-identical to a bare file path (DoE cross-repo memo,
    measured 15/32 example-cockpit-repo, 11/493 DoE-claude, 12/605 here).
    proposed_action is the field that makes a queue entry actionable to a
    session that did not author it — a duplicated path reads as populated, so
    nothing ever prompts anyone to fill it in. This derives an actual action
    sentence from the row's body (first sentence) or title instead, falling
    back to surface only as a last resort, since proposed_action is a
    required improvement-queue field and must never come back empty.
    """
    for candidate in (body, title):
        text = " ".join((candidate or "").split())
        if not text:
            continue
        match = _SENTENCE_TERMINATOR_RE.search(text)
        action = text[: match.end()] if match else text
        if len(action) > _PROPOSED_ACTION_MAX_LEN:
            truncated = action[:_PROPOSED_ACTION_MAX_LEN]
            action = (truncated.rsplit(" ", 1)[0] or truncated).rstrip() + "…"
        assert action, "_derive_proposed_action: non-empty candidate produced an empty action"
        return action
    return str(surface)


def _run_queue_append(row: dict, key: str, dry_run: bool) -> bool:
    """Route one row to coordinator-queue-append --schema improvement-queue.

    Returns True on success (or on a dry-run no-op), False on a non-zero rc or a subprocess.TimeoutExpired (a hung child) — both degrade to a per-row failure, never propagating past this row.
    """
    queue_scope = row.get("queue_scope") or "project"
    if queue_scope not in _VALID_QUEUE_SCOPES:
        print(
            f"warn: coordinator-harvest-deferrals: row '{row.get('id')}' has invalid "
            f"queue_scope '{queue_scope}' — defaulting to 'project'.",
            file=sys.stderr,
        )
        queue_scope = "project"

    body = row.get("body") or row.get("title") or ""
    case_against = row.get("case_against")

    if dry_run:
        print(
            f"[dry-run] would queue (improvement-queue, scope={queue_scope}): "
            f"{row.get('id')} — {row.get('title')} [{key}]"
        )
        return True

    prefix = _resolve_cli_cmd("coordinator-queue-append")
    if prefix is None:
        print(
            "error: coordinator-harvest-deferrals: could not locate "
            f"coordinator-queue-append for row '{row.get('id')}'.",
            file=sys.stderr,
        )
        return False

    cmd = [
        *prefix,
        "--schema",
        "improvement-queue",
        "--title",
        str(row["title"]),
        "--body",
        str(body).rstrip("\n"),
        "--surface",
        str(row["surface"]),
        "--proposed-action",
        _derive_proposed_action(body, row.get("title") or "", row["surface"]),
        "--change-kind",
        str(row["change_kind"]),
        "--queue-scope",
        queue_scope,
        "--status",
        "open",
        "--evidence",
        key,
    ]
    # Carry-through (DoE cross-repo memo, leg 3): a row with no case_against
    # (legitimately possible — the ~84 already-stamped plans are not
    # retro-fitted) harvests cleanly with the field simply omitted — never an
    # empty string or a placeholder. Only append the flag when the row
    # actually carries a truthy value.
    if case_against:
        cmd.extend(["--case-against", str(case_against)])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT_SECS,
            env=_child_identity_env(),
        )
    except subprocess.TimeoutExpired:
        print(
            f"error: coordinator-harvest-deferrals: coordinator-queue-append timed out "
            f"after {_SUBPROCESS_TIMEOUT_SECS}s for row '{row.get('id')}' — treating as a "
            "per-row failure so the remaining rows still run.",
            file=sys.stderr,
        )
        return False
    if result.returncode != 0:
        print(
            f"error: coordinator-harvest-deferrals: coordinator-queue-append failed for "
            f"row '{row.get('id')}': {result.stderr.strip() or result.stdout.strip()}",
            file=sys.stderr,
        )
        return False
    return True


def _run_lesson_promote(row: dict, key: str, dry_run: bool) -> bool:
    """Route one row to coordinator-lesson-promote --target-wiki <surface>.

    Returns True on success (or on a dry-run no-op), False on a non-zero rc or a subprocess.TimeoutExpired (a hung child) — both degrade to a per-row failure, never propagating past this row.
    """
    body = row.get("body") or row.get("title") or ""

    if dry_run:
        print(
            f"[dry-run] would promote (lesson, target-wiki={row['surface']}): "
            f"{row.get('id')} — {row.get('title')} [{key}]"
        )
        return True

    prefix = _resolve_cli_cmd("coordinator-lesson-promote")
    if prefix is None:
        print(
            "error: coordinator-harvest-deferrals: could not locate "
            f"coordinator-lesson-promote for row '{row.get('id')}'.",
            file=sys.stderr,
        )
        return False

    # `--body` is single-line ONLY: coordinator-lesson-promote refuses a newline
    # outright ("--body contains a newline; pass --body-file instead"). A harvested
    # row's body is prose and routinely multi-line, so the single-arg form failed
    # every such row -- the doctrine-edit harvest path could not write at all.
    # `rstrip("\n")` was never enough: it clears the trailing newline and leaves
    # every interior one.
    body_text = str(body).rstrip("\n")
    body_file: "str | None" = None
    if "\n" in body_text:
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8", newline="\n"
        )
        with handle:
            handle.write(body_text)
        body_file = handle.name

    cmd = [
        *prefix,
        "--title",
        str(row["title"]),
        *(["--body-file", body_file] if body_file else ["--body", body_text]),
        "--change-kind",
        str(row["change_kind"]),
        "--target-wiki",
        str(row["surface"]),
        "--evidence",
        key,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT_SECS,
            env=_child_identity_env(),
        )
    except subprocess.TimeoutExpired:
        print(
            f"error: coordinator-harvest-deferrals: coordinator-lesson-promote timed out "
            f"after {_SUBPROCESS_TIMEOUT_SECS}s for row '{row.get('id')}' — treating as a "
            "per-row failure so the remaining rows still run.",
            file=sys.stderr,
        )
        return False
    finally:
        if body_file:
            # The child has read it by the time run() returns on either path,
            # including the timeout one -- run() has already killed the child.
            try:
                os.unlink(body_file)
            except OSError:
                pass
    if result.returncode != 0:
        print(
            f"error: coordinator-harvest-deferrals: coordinator-lesson-promote failed for "
            f"row '{row.get('id')}': {result.stderr.strip() or result.stdout.strip()}",
            file=sys.stderr,
        )
        return False
    return True


def _harvest(
    plan_id: str, candidates: list[dict], dry_run: bool
) -> tuple[list[str], int, int, list[dict]]:
    """Route + dispatch every candidate row.

    Returns (queued_ids, deduped_count, failed_count, skipped_unroutable). A
    row whose `change_kind` matches neither `_LESSON_PROMOTE_CHANGE_KINDS` nor
    `_QUEUE_ELIGIBLE_CHANGE_KINDS` cannot be routed to either write seam — it
    is never coerced onto a change_kind it doesn't carry (that would corrupt
    the record being harvested) and never silently default-sunk into the
    improvement queue (the improvement-queue schema's change_kind enum is
    DoE's SSOT — coercing here would be an unowned, undocumented widening of
    it). Instead it is collected into `skipped_unroutable` — {id, change_kind,
    pm_approved} — so the caller can surface it in the summary and, for a
    pm_approved row, fail loudly rather than let a PM-ratified deferral
    evaporate on exit 0.

    Dedup-scan directory listing AND the `evidence:`-line scan of every
    `*.yaml` in those directories are both computed ONCE here, before the
    loop, not once per row (2026-08-15 staff review, Defect 2) —
    `_candidate_search_dirs` does not vary by row content (it depends only on
    env overrides and the process-memoized root resolvers), so the loop's
    per-row work is now the O(1) `_already_harvested` membership check plus
    the row's own write dispatch.
    """
    queued_ids: list[str] = []
    deduped = 0
    failed = 0
    skipped_unroutable: list[dict] = []

    # `{}` is a throwaway `row` — `_candidate_search_dirs` doesn't vary by row
    # content (see docstring above), so the literal empty dict just satisfies
    # the pre-existing signature. Review: code-reviewer (F5, nit).
    search_dirs = _candidate_search_dirs({}) if candidates else []
    evidence_lines = _collect_evidence_lines(search_dirs)

    for row in candidates:
        row_id = str(row["id"])
        key = _harvest_key(plan_id, row_id)

        if _already_harvested(key, evidence_lines):
            deduped += 1
            if dry_run:
                print(f"[dry-run] already harvested, skipping: {row_id} [{key}]")
            continue

        change_kind = row.get("change_kind")
        if change_kind in _LESSON_PROMOTE_CHANGE_KINDS:
            ok = _run_lesson_promote(row, key, dry_run)
        elif change_kind in _QUEUE_ELIGIBLE_CHANGE_KINDS:
            ok = _run_queue_append(row, key, dry_run)
        else:
            print(
                f"warn: coordinator-harvest-deferrals: row '{row_id}' has unroutable "
                f"change_kind '{change_kind}' — skipping.",
                file=sys.stderr,
            )
            skipped_unroutable.append(
                {
                    "id": row_id,
                    "change_kind": change_kind,
                    "pm_approved": row.get("pm_approved") is True,
                }
            )
            continue

        if ok:
            queued_ids.append(row_id)
        else:
            failed += 1

    return queued_ids, deduped, failed, skipped_unroutable


def _refuse_if_live_foreign_plan_holder(plan_path: Path) -> str | None:
    """Sole write-site guard closing the deferral-harvest half of the
    session-shape misdetection incident (cross-repo memo `2026-08-10-
    project-rag-em-wsc-misdetection-wrote-to-a-live-peers-plan.md`): a
    misresolved governing plan would have this script mint improvement-
    queue / lessons-outbox entries from a LIVE PEER session's deferred
    rows, keyed `harvest-key: <plan_id>:<row id>` — idempotent, so the
    peer's later legitimate close of that SAME plan sees the rows as
    already harvested and silently loses them. Placed here (the CLI
    itself), not in `directives_lessons_plan.build_deferral_harvest_
    directives`, per the plan-claim-stamp precedent (that guard also sits
    at the sole write site): a directive-builder-only guard is bypassable
    by any other caller that shells out to this CLI directly (hand-run,
    a future directive builder, `--dry-run` aside), while this CLI is the
    only thing that ever performs the write.

    Reuses `plan_status_transition._refuse_if_live_foreign_holder`
    verbatim rather than re-deriving its live-foreign-holder discriminator
    (same reverse governing-handoff join, same liveness check, same
    terminal-deployment-state carve-out) — see that function's own
    docstring for why LIVENESS, not provenance equality, is the only
    condition that survives the misdetection this guards against, and for
    its full terminal-safe enumeration (zero/ambiguous handoffs, dead
    holder, self-held, terminal `deployment_state` all proceed). This
    wrapper only resolves the worktree root this script otherwise has no
    occasion to compute (`_repo_root()`, already used for the dedup scan
    above) and lets the reused function resolve the closing session id
    itself — this script, unlike `plan-status-transition`, has no `--by`
    flag of its own to thread through.

    Absence of a resolvable git worktree (best-effort `_repo_root()`
    returning `None`) proceeds rather than refuses — matching the
    reused function's own "ambiguity proceeds" discipline; this harvest
    sweep is best-effort, never a hard gate on plan closure.
    """
    root = _repo_root()
    if root is None:
        return None

    from coordinator_core.ops.plan_status_transition import _refuse_if_live_foreign_holder

    return _refuse_if_live_foreign_holder(plan_path, Path(root), None)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="coordinator-harvest-deferrals",
        description=(
            "PM-gated deferral harvest: parse a plan's ## Tasks task-spine and select "
            "disposition:backlogged rows to route to coordinator-queue-append "
            "(improvement-queue) or coordinator-lesson-promote "
            "(doctrine-edit/snippet-sync-update) by change_kind. On a GOVERNED plan "
            "(frontmatter carries a grouping_approvals key) a row is selected when its "
            "'defer' grouping reads status:approved with a digest matching the "
            "current spine membership — the per-row pm_approved boolean is not "
            "consulted. On a LEGACY plan (no grouping_approvals key) selection falls "
            "back to disposition:backlogged && pm_approved:true rows, or, "
            "legacy-equivalent, deferred:true && pm_approved:true rows carrying no "
            "disposition."
        ),
        epilog="Spec backlink: docs/plans/2026-07-09-plan-full-coverage-and-deferred-harvest.md § Architecture (C4a)",
    )
    parser.add_argument("--plan", required=True, metavar="PATH", help="Path to the plan markdown file.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be queued/promoted without writing anything.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    _bootstrap_engine()

    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        with open(args.plan, encoding="utf-8") as fh:
            plan_text = fh.read()
    except OSError as exc:
        print(f"error: coordinator-harvest-deferrals: could not read plan '{args.plan}': {exc}", file=sys.stderr)
        return 1

    live_foreign_refusal = _refuse_if_live_foreign_plan_holder(Path(args.plan))
    if live_foreign_refusal:
        print(f"error: coordinator-harvest-deferrals: {live_foreign_refusal}", file=sys.stderr)
        return 1

    tasks_block = _locate_tasks_block(plan_text)
    if tasks_block is None:
        print(
            "warn: coordinator-harvest-deferrals: no locatable ```yaml plan-tasks``` block "
            "under '## Tasks' (check for a stray second fenced block, or non-blank content "
            "— e.g. an un-blanked HTML comment — between the heading and the fence). A plan "
            "mid-authoring may not have a spine yet. Skipping harvest.",
            file=sys.stderr,
        )
        if _tasks_section_has_deferred_marker(plan_text):
            print(
                "ERROR: coordinator-harvest-deferrals: the '## Tasks' region appears to "
                "contain 'deferred: true' row(s), but no fenced ```yaml plan-tasks``` block "
                "could be located — deferred rows in this plan may be UNHARVESTED and "
                "SILENTLY LOST. This is not a soft skip: fix the plan's ## Tasks region "
                "(remove/blank any stray second fence, ensure only the real fence sits "
                "directly under the heading) and re-run the harvest.",
                file=sys.stderr,
            )
            return 1
        return 0

    plan_id = _parse_plan_id(plan_text)
    if not plan_id:
        print(
            "warn: coordinator-harvest-deferrals: plan frontmatter has no 'plan_id' field — "
            "cannot form a stable idempotency key. Skipping harvest.",
            file=sys.stderr,
        )
        return 0

    rows, parse_error_count = _parse_rows(tasks_block)
    if parse_error_count:
        # _parse_rows already printed the warning; nothing left to harvest.
        print("Queued 0 deferred items: (none)")
        return 0

    plan_fm = parse_frontmatter(plan_text).get("frontmatter")
    candidates, malformed_warnings, malformed_count = _select_harvest_candidates(
        rows, plan_fm=plan_fm if isinstance(plan_fm, dict) else None
    )
    for w in malformed_warnings:
        print(f"warn: coordinator-harvest-deferrals: {w}", file=sys.stderr)

    queued_ids, deduped, failed, skipped_unroutable = _harvest(plan_id, candidates, args.dry_run)

    id_list = ", ".join(queued_ids) if queued_ids else "(none)"
    print(f"Queued {len(queued_ids)} deferred items: {id_list}")
    if deduped:
        print(f"  ({deduped} already-harvested row(s) deduped-skipped)")
    if malformed_count:
        print(f"  ({malformed_count} malformed row(s) skipped-with-warning)")
    if skipped_unroutable:
        skipped_list = ", ".join(f"{s['id']} ({s['change_kind']})" for s in skipped_unroutable)
        print(f"  ({len(skipped_unroutable)} unroutable row(s) skipped: {skipped_list})")

    # Emitted BEFORE the pm_approved-unroutable exit below: both conditions can
    # hold at once, and an early return there would swallow this line entirely --
    # the exact quiet-diagnostic loss this whole change set exists to remove.
    if failed:
        print(f"  ({failed} row(s) failed to write — see warnings above)", file=sys.stderr)

    pm_approved_unroutable = [s for s in skipped_unroutable if s["pm_approved"]]
    if pm_approved_unroutable:
        for s in pm_approved_unroutable:
            print(
                f"ERROR: coordinator-harvest-deferrals: row '{s['id']}' is pm_approved:true "
                f"but its change_kind '{s['change_kind']}' does not route to either write "
                "seam (not in the improvement-queue-eligible set nor the "
                "doctrine-edit/snippet-sync-update lesson-promote set) — this PM-ratified "
                "deferral would otherwise be SILENTLY LOST. Fix: give the row a routable "
                "change_kind, or hand-write a handoff to preserve the deferral.",
                file=sys.stderr,
            )
        return 1

    if failed:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
