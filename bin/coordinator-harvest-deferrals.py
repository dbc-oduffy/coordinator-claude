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

Idempotency: keyed on (plan_id, row id), and a plan carrying no `plan_id` keys
on its filename stem instead (`_path_harvest_id`) rather than skipping — the
skip made a lost harvest read like a plan with nothing to defer. Note that
`plan_tasks_mutate._dispatch_backlogged`, which reuses this module's key and
dedup scan for a single row, still ABORTS on a missing `plan_id`: it is handed
the plan's text but not its path, so it has no stem to key on. That refusal is
loud and writes nothing, which is the acceptable half of the same choice.
The plan's frontmatter `plan_id` field
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


_BIN_DIR = os.path.dirname(os.path.abspath(__file__))

_LIB_DIR = os.path.join(_BIN_DIR, "lib")

_CLI_CMD_CACHE: dict[tuple[str, bool], list[str] | None] = {}

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
        # `coordinator_core` at ITS OWN module level via the LOCATOR-axis
        import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
        from cc_invoke import _resolve_claude_klabauter_root, require_dispatch_engine_on_path  # noqa: F401
        
        require_dispatch_engine_on_path()
        # LOAD-BEARING, NOT DEAD. Do not delete on an unused-import sweep: this line is
        import coordinator_core  # noqa: F401
        
        from coordinator_registry import doe_root, _DoeUnresolvable
        
        # cli_shared.claude_klabauter_root() resolves repos.claude_klabauter (CLAUDE_KLABAUTER_ROOT env ->
        # implementations", 2026-07-23). doe_root() resolves the DIFFERENT
        import cli_shared
        
        if _BIN_DIR not in sys.path:
            sys.path.insert(0, _BIN_DIR)
        from _queue_append_locator import find_cli_cmd
        
        # Grouping-approval contract (2026-07-29). Selection on a GOVERNED plan keys
        from coordinator_core.frontmatter.schema_validate import (
            compute_grouping_digest,
            is_governed_plan,
            parse_frontmatter,
        )

        _claude_klabauter_root = cli_shared.claude_klabauter_root

        try:
            import yaml  # type: ignore  # noqa: F401
        except ImportError:
            yaml = None  # type: ignore

    finally:
        _resolved = locals()
        for _name in _BOOTSTRAPPED_NAMES:
            if _name not in globals() and _name in _resolved:
                globals()[_name] = _resolved[_name]

    _BOOTSTRAP_DONE = True


def __getattr__(name: str):
    if name in _BOOTSTRAPPED_NAMES:
        _bootstrap_engine()
        if name not in globals():
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
    _bootstrap_engine()
    sibling_only = _child_cli_must_come_from_tree()
    cache_key = (cli_name, sibling_only)
    if cache_key not in _CLI_CMD_CACHE:
        _CLI_CMD_CACHE[cache_key] = find_cli_cmd(
            _BIN_DIR, cli_name, sibling_only=sibling_only
        )
    return _CLI_CMD_CACHE[cache_key]

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

_LESSON_PROMOTE_CHANGE_KINDS = frozenset({"doctrine-edit", "snippet-sync-update"})

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


_QUEUE_APPEND_OUTPUT_ROOT_ENV = "QUEUE_APPEND_OUTPUT_ROOT"


def _isolation_root(env_var: str, caller_name: str) -> str | None:
    value = (os.environ.get(env_var) or "").strip()
    if not value:
        return None
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return value
    print(
        f"{caller_name}: ignoring inherited {env_var}={value} — a test-isolation "
        f"redirect outside a test run. Writing to the resolved repo path instead.",
        file=sys.stderr,
    )
    return None

_LESSON_PROMOTE_OUTBOX_ROOT_ENV = "LESSON_PROMOTE_OUTBOX_ROOT"


def _child_cli_must_come_from_tree() -> bool:
    """True when a spawned child CLI must be this tree's source, not the
    launcher the bare name resolves to on PATH.

    A write-seam redirect (`QUEUE_APPEND_OUTPUT_ROOT`,
    `LESSON_PROMOTE_OUTBOX_ROOT`) is a promise the CHILD has to keep, and a
    bare name does not resolve to a child that can keep it. It resolves to
    the generic warm DOOR, whose payload carries argv and cwd and NO env, so
    the CLI executes inside the resident engine under the SERVER's
    environment — and `warm/server.py::_scrub_test_harness_env` drops these
    exact vars at boot by design, because an inherited one is the inverse
    leak (a server spawned inside pytest served every later request from a
    stale tmpdir, 2026-09-18).

    So the redirect is not mishandled downstream; it never arrives. Set here,
    honoured by this process, gone one process boundary out. Measured
    2026-09-20: 148+ fixture rows in a sibling repo's tracked
    `state/lessons-outbox/` going back to 2026-07-04. Pinning the tree runs
    the child cold, in this process tree, which is the only route where these
    vars apply by design.

    Requires BOTH a redirect and `PYTEST_CURRENT_TEST`, matching
    `_isolation_root`'s own gate above: a redirect inherited outside a test
    run is already ignored there, and must not pin the tree either.

    Negative-spec: a live harvest pins NOTHING. It sets no redirect, so this
    returns False and the launcher stays the door — routing production work
    to the source checkout is the inverse defect, and the dispatch-axis stamp
    gate exists to refuse exactly that.
    """
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    return any(
        (os.environ.get(var) or "").strip()
        for var in (_QUEUE_APPEND_OUTPUT_ROOT_ENV, _LESSON_PROMOTE_OUTBOX_ROOT_ENV)
    )


def _minimal_yaml_list_parse(text: str) -> list[dict]:
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

        if current is None:
            continue

        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", stripped)
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip()

        if value == "|" or value == "|-" or value.startswith("|"):
            in_block_key = key
            block_lines = []
            block_indent = None
            continue

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

    return rows


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

    next_heading = re.search(r"^##\s+\S", after_heading, re.MULTILINE)
    section_text = (
        after_heading[: next_heading.start()] if next_heading else after_heading
    )

    fence_in_section = _FENCE_RE.search(section_text)
    if fence_in_section is None:
        return None

    # span to return the ORIGINAL (un-blanked) block body. The yaml block
    start, end = fence_in_section.span(1)
    heading_offset = heading_match.end()
    return plan_text[heading_offset + start : heading_offset + end]


_DEFERRED_TRUE_RE = re.compile(r"^\s*deferred:\s*true\s*$", re.MULTILINE)


def _tasks_section_has_deferred_marker(plan_text: str) -> bool:
    heading_match = _TASKS_HEADING_RE.search(plan_text)
    if heading_match is None:
        return False
    rest = plan_text[heading_match.end():]
    next_heading = re.search(r"^##\s+\S", rest, re.MULTILINE)
    section = rest[: next_heading.start()] if next_heading else rest
    return _DEFERRED_TRUE_RE.search(section) is not None


def _parse_plan_id(plan_text: str) -> str | None:
    fm_match = re.match(r"^---\n(.*?)\n---\n", plan_text, re.DOTALL)
    if fm_match is None:
        return None
    fm = fm_match.group(1)
    m = re.search(r'^plan_id:\s*"?([^"\n]+?)"?\s*$', fm, re.MULTILINE)
    if m is None:
        return None
    return m.group(1).strip()


def _parse_rows(tasks_yaml_text: str) -> tuple[list[dict], int]:
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

    rows = _minimal_yaml_list_parse(tasks_yaml_text)
    return rows, 0


def _row_is_well_formed(row: dict) -> str | None:
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

    defer_approved = False
    if governed and isinstance(plan_fm, dict):
        blocks = plan_fm.get("grouping_approvals")
        if not isinstance(blocks, dict):
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
            is_candidate = disposition == "backlogged" and defer_approved
        elif disposition:
            is_candidate = disposition == "backlogged" and row.get("pm_approved") is True
        else:
            is_candidate = row.get("deferred") is True and row.get("pm_approved") is True

        if is_candidate:
            candidates.append(row)

    return candidates, warnings, malformed_count


def _path_harvest_id(plan_path: Path) -> str | None:
    stem = plan_path.stem.strip()
    return f"plan-path-{stem}" if stem else None


def _harvest_key(plan_id: str, row_id: str) -> str:
    return f"harvest-key: {plan_id}:{row_id}"


# subprocess) once PER CANDIDATE ROW inside _harvest()'s loop — N redundant
# _CLI_CMD_CACHE pattern above (also a per-process, first-call memo). Never
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
    _bootstrap_engine()
    if _UNSET not in _resolved_claude_klabauter_root_cache:
        _resolved_claude_klabauter_root_cache[_UNSET] = cli_shared.claude_klabauter_data_home()
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
    lessons_override = _isolation_root(
        _LESSON_PROMOTE_OUTBOX_ROOT_ENV, "coordinator-harvest-deferrals"
    )
    if lessons_override:
        dirs.append(lessons_override)

    if not queue_override:
        resolved_claude_klabauter_root = _resolved_claude_klabauter_root()
        if resolved_claude_klabauter_root:
            dirs.append(os.path.join(resolved_claude_klabauter_root, "state", "improvement-queue"))

    if not lessons_override:
        resolved_doe_root = _resolved_doe_root()
        if resolved_doe_root:
            dirs.append(os.path.join(resolved_doe_root, "state", "lessons-outbox"))

    return dirs


_SENTENCE_TERMINATOR_RE = re.compile(r"(?<=\S)[.!?](?=\s|$)")

_PROPOSED_ACTION_MAX_LEN = 200


def _derive_proposed_action(body: str, title: str, surface: str) -> str:
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


def _body_argv(body: object) -> tuple[list[str], "str | None"]:
    body_text = str(body).rstrip("\n")
    if "\n" not in body_text:
        return ["--body", body_text], None
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".txt", delete=False, encoding="utf-8", newline="\n"
    )
    with handle:
        handle.write(body_text)
    return ["--body-file", handle.name], handle.name


def _unlink_body_file(body_file: "str | None") -> None:
    if body_file:
        try:
            os.unlink(body_file)
        except OSError:
            pass


def _run_queue_append(row: dict, key: str, dry_run: bool) -> bool:
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

    body_args, body_file = _body_argv(body)
    cmd = [
        *prefix,
        "--schema",
        "improvement-queue",
        "--title",
        str(row["title"]),
        *body_args,
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
    finally:
        _unlink_body_file(body_file)
    if result.returncode != 0:
        print(
            f"error: coordinator-harvest-deferrals: coordinator-queue-append failed for "
            f"row '{row.get('id')}': {result.stderr.strip() or result.stdout.strip()}",
            file=sys.stderr,
        )
        return False
    return True


def _run_lesson_promote(row: dict, key: str, dry_run: bool) -> bool:
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

    body_args, body_file = _body_argv(body)
    cmd = [
        *prefix,
        "--title",
        str(row["title"]),
        *body_args,
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
        _unlink_body_file(body_file)
    if result.returncode != 0:
        print(
            f"error: coordinator-harvest-deferrals: coordinator-lesson-promote failed for "
            f"row '{row.get('id')}': {result.stderr.strip() or result.stdout.strip()}",
            file=sys.stderr,
        )
        return False
    return True


def _harvest(
    plan_id: str,
    candidates: list[dict],
    dry_run: bool,
    legacy_plan_id: str | None = None,
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

    search_dirs = _candidate_search_dirs({}) if candidates else []
    evidence_lines = _collect_evidence_lines(search_dirs)

    for row in candidates:
        row_id = str(row["id"])
        key = _harvest_key(plan_id, row_id)
        # The window is PROSPECTIVE, not historical. Kira (2026-09-11, F6) read
        prior_keys = [key]
        if legacy_plan_id:
            prior_keys.append(_harvest_key(legacy_plan_id, row_id))

        if any(_already_harvested(k, evidence_lines) for k in prior_keys):
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


def _resolve_archived_plan(plan: str) -> str:
    path = Path(plan)
    if path.exists() or path.parent.parts[-2:] != ("docs", "plans"):
        return plan
    from coordinator_core.ops.fleet.archive_plans import plan_archive_dest

    dest = plan_archive_dest(path.parent.parent.parent, path)
    return str(dest) if dest is not None and dest.is_file() else plan


def main(argv: list[str] | None = None) -> int:
    _bootstrap_engine()

    parser = _build_parser()
    args = parser.parse_args(argv)
    args.plan = _resolve_archived_plan(args.plan)

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

    minted_plan_id = _parse_plan_id(plan_text)
    path_plan_id = _path_harvest_id(Path(args.plan))
    plan_id = minted_plan_id or path_plan_id
    legacy_plan_id = path_plan_id if minted_plan_id else None
    if not minted_plan_id and plan_id:
        print(
            "warn: coordinator-harvest-deferrals: plan frontmatter has no 'plan_id'; "
            f"harvesting under the plan-path key '{plan_id}' instead. The rows ARE "
            "queued. Renaming this plan file changes the key, so give it a 'plan_id' "
            "if it will be harvested again.",
            file=sys.stderr,
        )
    if not plan_id:
        print(
            "error: coordinator-harvest-deferrals: plan frontmatter has no 'plan_id' and "
            f"'{args.plan}' has no usable filename stem to key on, so no stable "
            "idempotency key can be formed. Refusing rather than harvesting rows that "
            "would be re-queued on every run. Give the plan a 'plan_id'.",
            file=sys.stderr,
        )
        return 1

    rows, parse_error_count = _parse_rows(tasks_block)
    if parse_error_count:
        print("Queued 0 deferred items: (none)")
        return 0

    plan_fm = parse_frontmatter(plan_text).get("frontmatter")
    candidates, malformed_warnings, malformed_count = _select_harvest_candidates(
        rows, plan_fm=plan_fm if isinstance(plan_fm, dict) else None
    )
    for w in malformed_warnings:
        print(f"warn: coordinator-harvest-deferrals: {w}", file=sys.stderr)

    queued_ids, deduped, failed, skipped_unroutable = _harvest(plan_id, candidates, args.dry_run, legacy_plan_id)

    id_list = ", ".join(queued_ids) if queued_ids else "(none)"
    if failed:
        attempted = len(queued_ids) + failed
        print(
            f"Queued {len(queued_ids)} of {attempted} deferred items "
            f"({failed} FAILED): {id_list}"
        )
    else:
        print(f"Queued {len(queued_ids)} deferred items: {id_list}")
    if deduped:
        print(f"  ({deduped} already-harvested row(s) deduped-skipped)")
    if malformed_count:
        print(f"  ({malformed_count} malformed row(s) skipped-with-warning)")
    if skipped_unroutable:
        skipped_list = ", ".join(f"{s['id']} ({s['change_kind']})" for s in skipped_unroutable)
        print(f"  ({len(skipped_unroutable)} unroutable row(s) skipped: {skipped_list})")

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
