"""
coordinator-queue-append — append a structured YAML entry to a coordinator queue.

Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, and correct
for this shape. On Windows, this file's co-located `.cmd` twin wins via
`PATHEXT` when invoked as a bareword, so the shebang is never read there; on
macOS/Linux `python3` is the right interpreter. Caution: callers must invoke
via the extensionless name or a resolved-interpreter prefix, never a bareword
`.py` through git-bash — git-bash DOES honor the shebang and would exec-127
with no `python3` present. See the carve-out in DoE-claude's
coordinator/docs/wiki/bash-on-windows-gotchas.md § Carve-out (cross-repo —
this wiki lives in the DoE-claude repo, not here). There is no separate
polyglot trampoline line — this file is the pure-`.py`-with-`.cmd` shape
end to end.

Spec backlink: docs/plans/2026-06-25-example-initiative-tc-2-queues-lessons-consolidation.md § C1
Prior spec: docs/plans/2026-06-15-structured-queue-medium-rollout.md § C4

Purpose: Write ONE YAML entry to state/<output_dir>/<ISO-date>-<slug>.yaml
relative to cwd. The file is left uncommitted (dirty) so it surfaces in
`git status`.

Output path: state/<output_dir from schema>/<ISO-date>-<slug>.yaml
  - ISO-date: current date in YYYY-MM-DD format
  - Slug: title sanitised to lowercase alphanumeric + hyphens, truncated to 40 chars

from_repo resolution order (same convention as cross-repo-memo and
coordinator-lesson-promote):
  1. cwd git-root → reverse-lookup against machine-local repos.* table
  2. DoE-claude repo (repos.doe_claude) → "claude-central-em"
  3. Unregistered git repo → basename of git root + "-em"
  4. Not in a git repo → "unknown-sender-em"
  Never uses `git remote get-url origin` — that yields a URL, not a shortname.
  Negative-spec: ~/.claude is no longer a memo-identity anchor; central identity
  flows through repos.doe_claude path-match only.

Schemas supported (validation delegated to the native "schema.describe"/"schema.validate"
coordinator_core ops, which read coordinator_core/frontmatter/schemas/*.yaml/*.schema.json
at runtime; the markdown docs at docs/wiki/*-schema.md are NOT parsed at runtime):
  debt-backlog      → state/debt-backlog/<date>-<slug>.yaml
  bug-backlog       → state/bug-backlog/<date>-<slug>.yaml
  improvement-queue → state/improvement-queue/<date>-<slug>.yaml
  lessons           → state/lessons/<date>-<slug>.yaml  (prefer coordinator-lesson-add wrapper for dedup)
  workstream        → state/workstreams/<workstream-id>.yaml  (definition; render-from-queue store)
  workstream-event  → state/workstreams/events/<date>-<workstream-id>-<session>.yaml  (field-scoped event)
  cross-repo-commitment → state/cross-repo-commitments/<date>-<slug>.yaml  (sibling-owed watch-ledger entry)

All three shared-base-field-set schemas use a unified base field-set (D1, tc-2):
  Required base: created, title, body, status
  Optional base: from_repo, surface, proposed_action, closed_at, closed_by, tags, evidence
  Base status enum: {open, closed, deferred}

Domain extensions layer on top:
  debt-backlog      — also requires: source, risk, proposed_action; optional: severity
  bug-backlog       — also requires: surface, severity; optional: repro_steps, environment, why_blocked; status += wontfix
  improvement-queue — also requires: surface, proposed_action, from_repo, change_kind; optional: queue_scope

cross-repo-commitment does NOT share the base field-set's from_repo/status-enum shape —
it pins its own status enum {open, fulfilled, withdrawn} (NOT {open, closed, deferred})
and replaces from_repo with committed_by (see docs/wiki/cross-repo-commitments-schema.md
§ Negative-spec — committed_by names the SIBLING counterparty, never this repo's own
cwd-resolved identity). Also requires: committed_by, memo, commitment, observed.

workstream / workstream-event do NOT share the base field-set above — see
docs/wiki/workstream-store-schema.md. workstream requires: workstream_id, title,
created, coordinator_root_path. workstream-event requires: workstream, field,
value, sequence, session, coordinator_root_path. Both auto-resolve
coordinator_root_path from the cwd git root (override via --coordinator-root-path).
Spec backlink: docs/plans/2026-07-08-project-tracker-render-from-queue.md § Chunks C2

Negative-spec (tc-2 D2): NO id field is generated or accepted. The filename
<date>-<slug>.yaml is the canonical entry handle. Do NOT restore id generation,
--id flag, or id_prefix_pattern validation — those are intentionally dropped.

Invocation:
  coordinator-queue-append \\
      --schema debt-backlog \\
      --title "Title here" \\
      --body "Multi-line body" \\
      --source "daily-review/2026-06-15" \\
      --status open \\
      --risk "Risk text" \\
      --proposed-action "Action text" \\
      [--severity P2] [--evidence "BS-2026-06-14-1"]

  coordinator-queue-append \\
      --schema bug-backlog \\
      --title "Bug title" \\
      --body "Bug description" \\
      --surface "coordinator/auto-push" \\
      --severity P1 \\
      --status open

  coordinator-queue-append \\
      --schema improvement-queue \\
      --title "Improvement title" \\
      --body "Improvement description" \\
      --surface "setup/publish.sh:88-95" \\
      --proposed-action "setup/publish.sh (REVIEW_PATTERNS array)" \\
      --change-kind script-edit \\
      --status open \\
      [--queue-scope central|project]  # central → lands in the claude-klabauter control-plane repo; project (default) → cwd-relative

Negative-spec (runtime reads): the CLI does NOT parse the markdown schema docs
(docs/wiki/*-schema.md) at runtime — those are human-readable prose, not the
authoritative schema source. The authoritative source is
coordinator_core/frontmatter/schemas/*.yaml/*.schema.json; validation is delegated
to the native "schema.describe"/"schema.validate" coordinator_core ops (routed via
cc_invoke.route(), see the Native schema seam section below) which read that
vendored schema set at runtime. No third-party Python libraries; stdlib only.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import tempfile
from typing import Any

# PARSE-only, never a serializer — the YAML-emission section below (§ YAML
# emission) stays hand-serialized, no pyyaml on the write path; yaml.safe_load
# is used exclusively by the C2 round-trip gate in _build_yaml to VALIDATE the
# already-hand-composed document, never to construct it.
import yaml

# ---------------------------------------------------------------------------
# Shared registry loader — bin/lib/coordinator_registry.py derives REPO_ALIASES
# and shared identity-resolution helpers from schemas/coordinator-registry.manifest.json
# at import time. Local copies of _repo_key_to_em_id, _same_path, and _em_id_for_root
# are deleted; the canonical implementations live in coordinator_registry.
# ---------------------------------------------------------------------------
_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from coordinator_registry import (  # noqa: E402
    REPO_ALIASES as _REPO_KEY_ALIASES,
    repo_key_to_em_id as _repo_key_to_em_id,
    _same_path,
)
from cc_invoke import route as _cc_route  # noqa: E402
import cli_shared  # noqa: E402
from repo_identity import resolve_checked_repo_root  # noqa: E402

# ---------------------------------------------------------------------------
# Native schema seam — schema introspection and validation via the
# "schema.describe"/"schema.validate" coordinator_core ops.
# Spec backlink: dual-yaml-parser option-d, C3 (original Node-CLI bridge)
# Spec backlink: coordinator_core/frontmatter/schema_cli.py (parity port + op
#   dual-registration this seam routes to)
#
# schema-cli.js was deleted in 480ad8f8 — coordinator_core/frontmatter/schema_cli.py
# is the byte-identical parity successor, reachable here ONLY via cc_invoke.route()
# (never a direct `python3 -m coordinator_core.frontmatter.schema_cli` subprocess
# repoint — that would bypass the native op-registry seam this CLI already uses for
# queue.append below). There is NO legacy fallback: the legacy_fn passed to route()
# always raises, so State-1 (native seam absent) fails loud naming the missing seam
# instead of silently degrading validation to "everything passes" — a fail-open
# legacy_fn here would be strictly worse than the loud MODULE_NOT_FOUND break this
# seam replaces. Two callers:
#   _build_yaml   → _schema_cli_describe  (schema.describe: field order for emit)
#   _validate     → _schema_cli_validate  (schema.validate: required-field + enum checks)
# ---------------------------------------------------------------------------


def _schema_cli_no_legacy(schema_name: str, op: str) -> Any:
    """route() legacy_fn for the schema.describe/schema.validate ops — always raises.

    schema-cli.js (the former Node bridge) was deleted in 480ad8f8; there is no
    legacy implementation left to fall back to. route()'s State-1 path wraps this
    RuntimeError in the four-rung CLAUDE_KLABAUTER_ROOT remediation message (cc_invoke.py
    _state1_remediation_message), so the operator sees exactly which rung to fix.
    """
    raise RuntimeError(
        f"coordinator-queue-append: schema-cli.js was deleted (480ad8f8) — "
        f"{op} requires the native coordinator_core.invoke seam "
        f"(schema='{schema_name}'); no legacy fallback exists."
    )


def _schema_cli_describe(schema_name: str) -> dict:
    """Call the native "schema.describe" op and return its result dict.

    Returns {"required": [field names in schema order], "optional": [...], "enums": {...},
    "applies_to": str|None}. The required/optional lists are ORDERED arrays — schema
    declaration order.

    Routes via cc_invoke.route(): State-2 (native seam present) calls the op; State-1
    (seam absent) raises a hard, actionable error (see _schema_cli_no_legacy) — never
    a silent fallback. Any route()/transport failure or "unknown schema" op-level
    error is reported and this process exits 1.

    Spec backlink: dual-yaml-parser option-d, C3
    """
    repo_root = _current_repo_root() or os.getcwd()
    try:
        return _cc_route(
            "schema.describe",
            {"schema_name": schema_name},
            repo_root,
            lambda: _schema_cli_no_legacy(schema_name, "schema.describe"),
        )
    except RuntimeError as exc:
        print(
            f"error: schema introspection failed for '{schema_name}': {exc}",
            file=sys.stderr,
        )
        sys.exit(1)


def _schema_cli_validate(schema_name: str, fields: dict) -> tuple[bool, list[str]]:
    """Call the native "schema.validate" op against fields and return (ok, errors).

    Returns (ok: bool, errors: list[str]) — errors is ALWAYS a (possibly empty) list,
    matching the op's own "field: error" flattened-string envelope.

    fields is JSON-round-tripped (json.dumps(..., default=str) then json.loads())
    before being sent as op params — mirrors the former stdin-pipe serialization's
    default=str safety net, so any non-JSON-native value (e.g. a date object) is
    stringified the same way it was when piped to schema-cli.js --validate.

    Routes via cc_invoke.route(): State-2 (native seam present) calls the op; State-1
    (seam absent) raises a hard, actionable error (see _schema_cli_no_legacy) — never
    a silent fallback that would degrade validation to "everything passes". Any
    route()/transport failure is reported and this process exits 1 — a genuine
    validation REJECTION (ok:false) is a normal op result, not an exception, and is
    returned to the caller unchanged.

    Spec backlink: dual-yaml-parser option-d, C3
    """
    json_safe_fields = json.loads(json.dumps(fields, default=str))
    repo_root = _current_repo_root() or os.getcwd()
    try:
        result = _cc_route(
            "schema.validate",
            {"schema_name": schema_name, "fields": json_safe_fields},
            repo_root,
            lambda: _schema_cli_no_legacy(schema_name, "schema.validate"),
        )
    except RuntimeError as exc:
        print(
            f"error: schema validation failed for '{schema_name}': {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    ok = result.get("ok") is True
    errors = result.get("errors") or []
    if not isinstance(errors, list):
        errors = [str(errors)]
    return ok, errors


# ---------------------------------------------------------------------------
# Schema output directory routing — CLI routing, NOT validation.
# Spec backlink: docs/plans/2026-06-25-example-initiative-tc-2-queues-lessons-consolidation.md § D1
#
# Validation (required fields, enum values) is delegated to the native
# "schema.validate" op, which reads coordinator_core/frontmatter/schemas/*.yaml/
# *.schema.json at runtime. This dict retains only the CLI routing concern
# (output_dir) that is absent from the schema files.
# Negative-spec: do NOT add required/optional/enums back here — those now live
# exclusively in coordinator_core/frontmatter/schemas/ and are served via the
# native schema.describe/schema.validate ops.
# ---------------------------------------------------------------------------

# Valid queue_scope values — mirrors BacklogQueueScope in cockpit-contract.
# "project" is the default (per-project local entries); "central" is for
# universal patterns destined for claude-klabauter's central improvement queue / lessons
# store (docs/wiki/state-placement-law.md § Taxonomy "Central/global state").
_VALID_QUEUE_SCOPES = ("central", "project")

# output_dir routing: maps schema name → state/<queue> directory.
# Derived from the applies_to glob in each coordinator/schemas/*.yaml file
# (e.g. "state/debt-backlog/*.yaml" → "state/debt-backlog").
_SCHEMA_OUTPUT_DIRS: dict[str, str] = {
    "debt-backlog": os.path.join("state", "debt-backlog"),
    "bug-backlog": os.path.join("state", "bug-backlog"),
    "improvement-queue": os.path.join("state", "improvement-queue"),
    "lessons": os.path.join("state", "lessons"),
    "workstream": os.path.join("state", "workstreams"),
    "workstream-event": os.path.join("state", "workstreams", "events"),
    "cross-repo-commitment": os.path.join("state", "cross-repo-commitments"),
}

# Schemas whose per-record shape diverges from the shared base field-set
# (created/title/body/status) — the render-from-queue workstream store (C2).
# Definitions are keyed by workstream_id (not title+date-slug); events are
# keyed by workstream+session (not title+date-slug), each field-scoped.
# Spec backlink: docs/plans/2026-07-08-project-tracker-render-from-queue.md § Chunks C2
_WORKSTREAM_STORE_SCHEMAS = ("workstream", "workstream-event")

# Maps CLI --schema names to the vendored schema names when they differ.
# Needed when the file is registered as lesson-entry.yaml (schema: lesson-entry)
# but the CLI surface offers --schema lessons for ergonomics.
# cross-repo-commitment needs NO entry here — schemas/cross-repo-commitment.yaml
# declares `schema: cross-repo-commitment` verbatim, matching the --schema flag
# name, so schema.describe resolves it directly without a CLI-name remap.
_SCHEMA_CLI_NAME: dict[str, str] = {
    "lessons": "lesson-entry",
}

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SLUG_MAX_CHARS = 40

# Env var overrides for test isolation. Canonical spellings now live in
# bin/lib/cli_shared.py (T2-g2a consolidation) — aliased here so existing
# doc/error-message references in this file don't need a rename.
_MACHINE_LOCAL_IMPL_ENV = cli_shared.MACHINE_LOCAL_IMPL_ENV
_CLAUDE_HOME_ENV = cli_shared.CLAUDE_HOME_ENV
_QUEUE_APPEND_OUTPUT_ROOT_ENV = "QUEUE_APPEND_OUTPUT_ROOT"

# Env var for CLAUDE_KLABAUTER_ROOT override — mirrors coordinator-claude-klabauter-root.sh §4b
# idempotency gate. Set to the claude-klabauter repo root to bypass machine-local resolution.
# Spec backlink: pln-stop-the-rot-claude-klabauter-state-home-placement-4cc787 § AC1 / AC13
_CLAUDE_KLABAUTER_ROOT_ENV = cli_shared.CLAUDE_KLABAUTER_ROOT_ENV


class _ClaudeKlabauterUnresolvable(RuntimeError):
    """Raised when CLAUDE_KLABAUTER_ROOT cannot be resolved via env var or machine-local registry.

    Callers in the per-project (meta-repo cwd) write loop catch this and degrade
    gracefully (WARN + skip, exit 0) per AC13. The low-level shell primitive
    coordinator-claude-klabauter-root.sh fails loud; this is the Python caller-layer resilience
    wrapper. The central-scope write path (queue_scope == "central") also raises
    this same exception — central state routes to claude-klabauter unconditionally per
    state-placement-law.md § Taxonomy "Central/global state", the same seam the
    meta-repo per-project branch already used.

    Spec backlink: pln-stop-the-rot-claude-klabauter-state-home-placement-4cc787 § AC13
    """

# Registry aliases: stable doctrine EM names derived from
# schemas/coordinator-registry.manifest.json via bin/lib/coordinator_registry.py.
# _REPO_KEY_ALIASES is imported above (REPO_ALIASES from coordinator_registry).

# ---------------------------------------------------------------------------
# from_repo resolution — mirrors coordinator-lesson-promote._resolve_from_repo
# ---------------------------------------------------------------------------


# _claude_home / _claude_klabauter_root / _machine_local_impl / _resolve_python /
# _machine_local_get / _machine_local_repos_keys / _current_repo_root: extracted
# to bin/lib/cli_shared.py (T2-g2a consolidation, ~150 LoC dup with
# coordinator-lesson-promote). Thin aliases preserve the pre-consolidation call
# sites below without a mass rename.
_claude_home = cli_shared.claude_home
_claude_klabauter_root = cli_shared.claude_klabauter_root
_machine_local_impl = cli_shared.machine_local_impl
_resolve_python = cli_shared.resolve_python
_machine_local_get = cli_shared.machine_local_get
_machine_local_repos_keys = cli_shared.machine_local_repos_keys


def _current_repo_root() -> str | None:
    """cwd's git root via the checked resolver (`repo_identity`).

    Was `cli_shared.current_repo_root`, deleted by C2 of the one-checked-resolver
    plan on the premise that `resolve_from_repo` was its only caller. This alias,
    `coordinator-lesson-promote`'s twin, and `coordinator-queue-close` were three
    surviving callers, so the deletion left this file dead at import.

    Classification: READER — a MISMATCH warns and proceeds with the resolved
    root (identity attribution, not a destructive action), matching
    `cli_shared.resolve_from_repo`'s disposition under DR-277.
    """
    root, verdict = resolve_checked_repo_root(explicit_root=None)
    if verdict.get("verdict") == "MISMATCH":
        print(
            verdict.get("message", "coordinator-queue-append: repo-identity MISMATCH"),
            file=sys.stderr,
        )
    return root


def _resolve_session_id() -> str:
    """Delegates to ``coordinator_core.session.core.resolve_session_id``
    (KS-6, 2026-08-07): the full 3-tier ``SESSION_ENV_PRECEDENCE`` ladder
    (``COORDINATOR_SESSION_ID``, ``CLAUDE_SESSION_ID``,
    ``CLAUDE_CODE_SESSION_ID``), widened from the prior
    ``CLAUDE_CODE_SESSION_ID``-only read to match the canonical reference —
    see that constant's own docstring for the prior break-class defect two
    disagreeing copies of this ladder caused. Returns "" if unresolved,
    including on an import/CLAUDE_KLABAUTER_ROOT resolution failure (fail-soft — an
    unresolved id here correctly degrades provenance_completeness to
    "unknown" below, the pre-existing contract of this function's
    env-var-only predecessor).

    Former tier 2 (KS-3, 2026-08-07) REMOVED — was the sentinel file at
    <git_root>/.git/coordinator-sessions/.current-session-id. Unsound under
    concurrency (documented last-writer-wins across concurrent sessions
    sharing one worktree — coordinator_core/bash_guards/guard_inprocess_search.py
    ~L84) AND its sole writer (session-init.py, the DoE-claude SessionStart
    hook) was deleted by PM directive 2026-07-15 — no production writer
    survives.

    Spec backlink: docs/plans/2026-06-26-queue-schema-unify.md § C2 STEP 1
    """
    try:
        claude_klabauter_root = _claude_klabauter_root()
        if claude_klabauter_root and claude_klabauter_root not in sys.path:
            sys.path.insert(0, claude_klabauter_root)
        from coordinator_core.session.core import resolve_session_id

        return resolve_session_id()
    except Exception:  # noqa: BLE001 — fail-soft, matches the prior env-only read's contract
        return ""


# _resolve_from_repo: extracted to bin/lib/cli_shared.py (T2-g2a consolidation) —
# same cwd git-root -> machine-local reverse-lookup -> doe_claude -> unregistered
# -> "unknown-sender-em" ladder, byte-identical to the pre-consolidation body.
_resolve_from_repo = cli_shared.resolve_from_repo


# ---------------------------------------------------------------------------
# Output path helpers
# ---------------------------------------------------------------------------


def _today_iso() -> str:
    """Return today's date in YYYY-MM-DD format."""
    return datetime.date.today().isoformat()


def _slug_from_title(title: str) -> str:
    """Sanitize a title into a filesystem-safe slug.

    Lowercase, alphanumeric + hyphens only, no leading/trailing hyphens.
    Truncated to _SLUG_MAX_CHARS chars.
    """
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    # Review: code-reviewer — F3: strip("-") before truncation, but truncation can
    # leave a trailing hyphen (e.g. "foo-bar-" at char 40). rstrip("-") after
    # truncation, matching migrate-queues-to-base.py:292.
    return slug[:_SLUG_MAX_CHARS].rstrip("-")


# Review: code-reviewer — F1 (P1): --workstream-id / --workstream / --session are
# interpolated into filenames with zero validation, and os.path.join does not
# neutralize ".." or a leading "/" in its second argument. Enforce an allowlist
# regex at ingestion time (parser.error, fail loud) before any of these reach
# _output_path's filename_override. Charset matches the existing slug convention
# (lowercase/hyphen) but permits mixed case since these are caller-supplied ids,
# not title-derived slugs.
_WORKSTREAM_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def _validate_workstream_identifier(name: str, value: str, parser: argparse.ArgumentParser) -> None:
    """Reject path-traversal-shaped values for workstream-store filename components.

    Applies to --workstream-id / --workstream / --session, all of which are
    interpolated directly into filenames (see _output_path's filename_override
    branch). Rejects empty values, path separators, ".." segments, and leading
    dots via a conservative allowlist charset — fails loud via parser.error
    rather than silently sanitizing.
    """
    # Review: coordinator:code-reviewer — .match() against a `$`-anchored
    # pattern lets a trailing "\n" through (Python's `$` is satisfied before a
    # single trailing newline); .fullmatch() requires the whole string consumed.
    if not value or not _WORKSTREAM_IDENTIFIER_RE.fullmatch(value):
        parser.error(
            f"--{name} must match {_WORKSTREAM_IDENTIFIER_RE.pattern} "
            f"(no path separators, no leading dot, non-empty), got {value!r}"
        )


# Review: code-reviewer (parity pass) — F1-class hole also present in --created on the
# workstream-event branch: `filename_override = f"{created}-{args.workstream}-{args.session}.yaml"`
# (see main()) interpolates --created into a filename exactly like --workstream/--session
# above, but --created was never routed through ANY validation, allowing
# `--created "../../../evil"` to escape state/workstreams/events/ the same way an
# unvalidated --workstream did before _validate_workstream_identifier closed that hole.
# --created is a DATE field, not an identifier, so _WORKSTREAM_IDENTIFIER_RE (which
# accepts non-dates and rejects nothing meaningful about date shape) would be the wrong
# oracle here — a dedicated YYYY-MM-DD allowlist is the correct guard.
# Negative-spec: do NOT remove this as "redundant with schema validation" — `created` is
# not a declared property of workstream-event.schema.json, and that schema has no
# top-level `additionalProperties: false`, so schema.validate raises nothing for a
# path-traversal-shaped --created value; this CLI-level check is the only gate.
# Review: code-reviewer (Finding 1/2) — `\d` matches any Unicode Nd digit (not just
# [0-9]), and `.match()` against a `$`-terminated pattern accepts one trailing "\n".
# [0-9] is chosen over re.ASCII as more obviously scoped at this call site; paired
# with .fullmatch() below to close the trailing-newline gap.
_CREATED_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


def _validate_created_date(value: str, parser: argparse.ArgumentParser) -> None:
    """Reject a non-YYYY-MM-DD --created value before it reaches a filename.

    Called for workstream-event (--created is a filename_override component, see
    main()) and, for validation-coverage symmetry (Finding 7), for workstream too
    (not a filename component there, but otherwise asymmetrically unvalidated) —
    the shared base-field schemas emit --created into YAML only, never into their
    own <date>-<slug>.yaml path (which is built from _today_iso(), not
    args.created). Callers must only invoke this when args.created is not None —
    the default-to-today behaviour (a value _today_iso() already produces in this
    exact shape) must not be routed through this check.

    Review: review-integrator (Finding 6) — validates DATE SHAPE only; does not
    confirm the value is a real calendar date (e.g. "9999-99-99" passes).
    """
    if not _CREATED_DATE_RE.fullmatch(value):
        parser.error(
            f"--created must match {_CREATED_DATE_RE.pattern} (YYYY-MM-DD), got {value!r}"
        )


def _reject_newline_in_list_items(flag: str, items: list[str] | None, parser: argparse.ArgumentParser) -> None:
    """Fail loud (parser.error) if any item in a repeatable text list carries a newline.

    Applies to --deliverables / --specs / --dependency-annotations. `_emit_yaml_field`
    routes a multi-line string to a literal block scalar, but `parse_yaml`'s
    list-item-mapping path (deliverables' block-map form) synthesizes the inline
    part of a `- text: |` item from a single line, so a block scalar nested inside
    a list item does not round-trip. Rejecting at write time is cheaper than
    emitting a value the reader cannot parse back.

    Spec backlink: docs/plans/2026-07-30-workstream-store-writer-and-parser.md § C2
    """
    if not items:
        return
    for item in items:
        if "\n" in item:
            parser.error(
                f"--{flag} entries must not contain a newline — got an item with "
                f"an embedded newline. Split into multiple --{flag} flags (one "
                f"line each) instead; a block scalar nested inside a list item "
                f"does not round-trip through the store's reader."
            )


def _output_path(
    schema_name: str,
    title: str,
    queue_scope: str | None = None,
    filename_override: str | None = None,
) -> str:
    """Compute the output path for a new queue entry.

    Precedence:
      1. QUEUE_APPEND_OUTPUT_ROOT env override wins (test isolation).
      2. Else if queue_scope == "central": central state routes to claude-klabauter
         unconditionally, via the same seam the meta-repo per-project branch below
         uses. Raises _ClaudeKlabauterUnresolvable if CLAUDE_KLABAUTER_ROOT cannot be resolved — caller
         must catch and degrade gracefully (WARN + skip, exit 0).
      3. Else (project scope): routes via the seam (L7 fix — git root, not bare cwd).
         Meta-repo cwd routes to claude-klabauter; sibling-repo cwd routes to its own state/.
         Falls back to cwd only when not in a git repo.

    filename_override: when provided, used verbatim as the output filename instead
    of the shared <date>-<slug>.yaml scheme. Needed by the workstream store schemas
    (C2), whose filenames are keyed by workstream_id / workstream+session-id, not
    by title — e.g. definitions are `<workstream_id>.yaml` (no date prefix, single
    file per workstream, rewritten atomically) and events are
    `<date>-<workstream_id>-<session>.yaml` (per § Substrate).

    Invariant: each schema's output_dir is expected to include 'state/' as its first
    path component (e.g. 'state/improvement-queue'). The central-scope branch joins
    the claude-klabauter root directly with output_dir, giving <claude_klabauter_root>/state/<schema-dir>/
    — correct only when this invariant holds for all supported schemas.

    Spec backlinks:
      - docs/wiki/state-placement-law.md § Taxonomy — "Central/global state" routes
        to claude-klabauter unconditionally (central)
      - docs/plans/2026-07-03-stop-the-rot-claude-klabauter-state-home-placement.md § C12 / AC13 (meta-repo)
      - docs/plans/2026-07-08-project-tracker-render-from-queue.md § Substrate / § Chunks C2 (filename_override)
      - Landmine L7 (per-repo cwd-fallback): closed here by using git root, not os.getcwd().

    Negative-spec: [DoE-claude] docs/plans/2026-07-06-gate2-w23-state-seam-caller-switch.md § C1
    proposed routing central state to DoE instead of claude-klabauter, but that plan is
    `status: draft` with AC1/AC2 `pending` and its own C3 HELD (recorded disk proof
    the flip never took effect on the production path) — it was never ratified and
    must not be cited as authority for this branch's routing decision.
    """
    output_dir = _SCHEMA_OUTPUT_DIRS[schema_name]
    override_root = os.environ.get(_QUEUE_APPEND_OUTPUT_ROOT_ENV)
    if override_root:
        # Non-absolute has no legitimate use-case — defense-in-depth for the test knob.
        if not os.path.isabs(override_root):
            print(
                f"error: coordinator-queue-append: QUEUE_APPEND_OUTPUT_ROOT must be an absolute path, got {override_root!r}",
                file=sys.stderr,
            )
            sys.exit(1)
        base = os.path.join(override_root, output_dir)
    elif queue_scope == "central":
        # Review: code-reviewer — F2: defensive invariant — only improvement-queue supports
        # central scope. If this check fires, a new code path reached central-write
        # without going through the schema guard in main(). Fail loud rather than silently
        # writing to the wrong directory.
        # Review: code-reviewer Slice-B — (B-F4) replaced assert with explicit RuntimeError
        # so the guard survives python -O (assert evaporates under optimised bytecode).
        if schema_name not in ("improvement-queue", "lessons"):
            raise RuntimeError(
                f"_output_path: central queue_scope only valid for improvement-queue or lessons, got '{schema_name}'"
            )
        # Central state routes to claude-klabauter unconditionally — see
        # docs/wiki/state-placement-law.md § Taxonomy "Central/global state".
        # (The [DoE-claude] docs/plans/2026-07-06-gate2-w23-state-seam-caller-switch.md
        # plan's proposal to route this branch to DoE was never ratified: that plan is `status: draft`,
        # AC1/AC2 are `pending`, and its own C3 is HELD with recorded disk proof
        # the flip never took effect on the production path.)
        # _claude_klabauter_root() raises _ClaudeKlabauterUnresolvable when repos.claude_klabauter is
        # unregistered and CLAUDE_KLABAUTER_ROOT env var is not set — legacy_fn() catches and
        # degrades gracefully (WARN + skip, exit 0) per the graceful-degradation
        # contract, mirroring the meta-repo per-project branch below.
        claude_klabauter_root = _claude_klabauter_root()
        if claude_klabauter_root is None:
            raise _ClaudeKlabauterUnresolvable(
                "repos.claude_klabauter not set; cannot route central-scope write to claude-klabauter"
            )
        base = os.path.join(claude_klabauter_root, output_dir)
    else:
        # Per-repo state: use git root, not os.getcwd() (L7 fix — cwd can be a subdir,
        # giving a wrong state path and silently writing to the wrong location).
        # When the git root is the meta-repo (~/.claude), route to claude-klabauter (stop-the-rot
        # taxonomy: per-repo class for meta-repo → claude-klabauter).
        git_root = _current_repo_root()
        home = _claude_home()
        if git_root and _same_path(git_root, home):
            # Meta-repo cwd → route to claude-klabauter via seam.
            claude_klabauter_root = _claude_klabauter_root()
            if claude_klabauter_root is None:
                raise _ClaudeKlabauterUnresolvable(
                    "repos.claude_klabauter not set; cannot route meta-repo per-repo state to claude-klabauter"
                )
            base = os.path.join(claude_klabauter_root, output_dir)
        elif git_root:
            # Sibling repo → per-repo state stays in the repo itself.
            base = os.path.join(git_root, output_dir)
        else:
            # Not in a git repo — fall back to cwd (last-resort; at least not wrong-subdir).
            base = os.path.join(os.getcwd(), output_dir)
    if filename_override is not None:
        return os.path.join(base, filename_override)
    date_str = _today_iso()
    slug = _slug_from_title(title)
    filename = f"{date_str}-{slug}.yaml"
    return os.path.join(base, filename)


def _write_out_path_excl(out_path: str, content: str) -> str:
    """Write content to out_path using an exclusive-create + retry-with-suffix loop.

    Thin wrapper over bin/lib/cli_shared.write_path_excl (T2-g2a consolidation,
    ~150 LoC dup with coordinator-lesson-promote) — pins caller_name so the
    exhausted-retry error message still names this CLI. Byte-identical retry/cap/
    fail-loud-after-cap-exhausted behavior to the pre-consolidation body.

    Negative-spec: do NOT swap this for a plain os.replace()/open("w") — that
    silently clobbers a same-key concurrent write. Do NOT swap this for a bare
    fail-loud FileExistsError (the cross-repo-memo shape) either — legacy_fn() here
    is a terminal caller with no retry path, so failing loud on the FIRST collision
    would drop the entry rather than preserve it; retry-with-suffix is required.

    Spec backlink: F1/F2 legacy-fallback silent-overwrite collision guard (chunk C1).
    """
    return cli_shared.write_path_excl(
        out_path, content, caller_name="coordinator-queue-append"
    )


def _write_out_path_overwrite(out_path: str, content: str) -> str:
    """Write content to out_path via write-temp + atomic rename, OVERWRITING
    any existing file at out_path.

    Distinct from `_write_out_path_excl` (create-only, retry-with-suffix on
    collision): this helper is for definition files that are genuinely
    REWRITTEN in place — a second write to the same `workstream_id` must
    update the single canonical `<id>.yaml`, not fork a `<id>-2.yaml`
    sibling. Last-write-wins is acceptable here per the single-writer,
    low-contention assumption documented in workstream.schema.json's own
    description field.

    Review: code-reviewer — Finding 1 (P1). `_write_out_path_excl` was wired
    to the `workstream` (definition) schema in error — that primitive is
    create-only and forks a new file on any second write to an existing
    workstream_id, contradicting the schema's own "rewritten atomically"
    doc-comment. This helper gives the definition writer the overwrite
    semantics the schema actually promises; `workstream-event` (append-safe,
    both survive) stays on `_write_out_path_excl` unchanged.

    Negative-spec: do NOT swap this in for `workstream-event` writes — events
    are append-only-by-design (two events for the same base path must BOTH
    survive under distinct filenames); overwrite semantics here would
    silently drop one event's history.

    Spec backlink: docs/plans/2026-07-08-project-tracker-render-from-queue.md
    § Definition/event boundary (finding 6); workstream.schema.json:7.
    """
    directory = os.path.dirname(out_path) or "."
    fd, tmp_path = tempfile.mkstemp(
        prefix=os.path.basename(out_path) + ".",
        suffix=".tmp",
        dir=directory,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_path, out_path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return out_path


# ---------------------------------------------------------------------------
# YAML emission (stdlib only — no pyyaml for COMPOSING the document; the C2
# round-trip gate at the bottom of _build_yaml uses yaml.safe_load to VALIDATE
# the already-composed string, never to build it — see that gate's docstring)
# ---------------------------------------------------------------------------


def _yaml_quote_string(value: str) -> str:
    """Wrap a string in double-quotes if it contains special YAML characters.

    Quoted when the string contains: colon+space, leading/trailing whitespace,
    special start chars (|, >, !, &, *, {, }, [, ], ', `, ", %, @, ?, ,), a
    trailing colon (also catches a lone `:`, which both starts and ends with
    it), a whitespace-preceded comment-introducer (<space># or <tab>#) anywhere
    in the line, is empty, is a YAML-reserved scalar (true/false/null/yes/no/~,
    any case), or an all-digit (integer-looking) scalar.

    Negative-spec: a whitespace-preceded `#` introduces an inline YAML comment at
    ANY column, not only column 0 — a start-position-only check silently truncates
    titles/bodies like "PR #123" on re-parse. The `(^|\\s)#` scan is the SOLE `#`
    gate: its `^` branch already covers a leading `#` and `\\s` covers space- and
    tab-preceded ones, so `#` is intentionally absent from the start-chars set.

    Review: code-reviewer — reserved-scalar + all-digit quoting added so a value
    like --evidence "true" or --title "123" round-trips as a string instead of
    being silently reparsed as bool/int (parity with coordinator-lesson-promote
    ._yaml_str's reserved-scalar check; all-digit quoting is a further hardening
    not present in that sibling).

    2026-08-11 widening (queue-append quoter gap): the start-char set was missing
    `'` and `` ` `` — both YAML indicators that cannot begin a plain scalar — plus
    `"`, `%`, `@`, `?`, `,`, and a lone/trailing `:`. Verified against the fleet
    lesson/improvement-queue corpus (project-rag-em's fleet_prose unparseable-YAML
    report, 2026-08-11).
    """
    if not value:
        return '""'
    needs_quoting = (
        ": " in value
        or value != value.strip()
        or value[0] in "|>!&*{}[]'`\"%@?,"
        or value.endswith(":")
        or re.search(r"(^|\s)#", value) is not None
        or value.startswith("- ")
        or "\n" in value
        or value.lower() in ("true", "false", "null", "yes", "no", "~")
        or re.fullmatch(r"-?\d+(\.\d+)?", value) is not None
    )
    if needs_quoting:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _yaml_block_scalar(value: str) -> str:
    """Format a multi-line string as a YAML literal block scalar (body: |-)."""
    lines = value.splitlines()
    indented = "\n".join("  " + line if line else "" for line in lines)
    # Review: code-reviewer — F2: clip chomping (|) adds a trailing newline on
    # round-trip, so 'line1\nline2' parses back as 'line1\nline2\n'. Use strip
    # chomping (|-) to match migrate-queues-to-base.py:317 and preserve exact
    # byte-fidelity for the tc-4 contract.
    return "|-\n" + indented


def _emit_system_block(system: dict) -> str:
    """Emit the system: provenance block with 2-space child indentation.

    Field order (per spec): created_by_session (if present), created_by_agent
    (if present), linked_sessions, linked_commits (if present), provenance_completeness.

    Empty linked_sessions list emits as 'linked_sessions: []' (not a null key).

    Spec backlink: docs/plans/2026-06-26-queue-schema-unify.md § C2 STEP 2
    """
    child_lines: list[str] = []
    for k, v in system.items():
        if v is None:
            continue
        if isinstance(v, list):
            if not v:
                child_lines.append(f"  {k}: []")
            else:
                items = "\n".join(f"    - {_yaml_quote_string(str(i))}" for i in v)
                child_lines.append(f"  {k}:\n{items}")
        elif isinstance(v, str):
            child_lines.append(f"  {k}: {_yaml_quote_string(v)}")
        else:
            child_lines.append(f"  {k}: {v}")
    return "system:\n" + "\n".join(child_lines)


def _emit_yaml_field(key: str, value) -> str:
    """Emit a single YAML field line or block, handling type dispatch.

    - None values are skipped (caller must check before calling).
    - Multi-line strings → literal block scalar.
    - Lists → block sequence (empty list → `key: []`, not a stray empty block).
    - Scalars → quoted if needed.

    Parity note: coordinator_core/ops/queue_append.py's own copy of this helper
    states it mirrors this one exactly — the empty-list `key: []` shortcut below
    keeps that parity invariant true (an optional list field like `specs` left
    empty must not render as a bare `key:` with no items, which the tracker
    would then have to special-case).
    """
    if value is None:
        return ""
    if isinstance(value, list):
        if not value:
            return f"{key}: []"
        items = "\n".join(f"  - {_yaml_quote_string(str(item))}" for item in value)
        return f"{key}:\n{items}"
    if isinstance(value, str) and "\n" in value:
        return f"{key}: {_yaml_block_scalar(value)}"
    if isinstance(value, str):
        return f"{key}: {_yaml_quote_string(value)}"
    return f"{key}: {value}"


def _emit_block_map_list_field(key: str, items: list[dict], item_key: str = "text") -> str:
    """Emit a YAML block-sequence of single-key mappings: `- text: "..."` per item.

    `items` is a list of single-key dicts (e.g. `[{"text": "..."}, ...]`) — the
    schema-validated in-memory shape workstream `deliverables` fields carry (each
    item must be an object with a required string `text` property per
    workstream.schema.json). This is also the form `schema_validate.parse_yaml`'s
    list-item-mapping reader accepts. Distinct from `_emit_yaml_field`'s plain
    scalar-list branch (`- "value"`), which stays in use for plain-string list
    fields (`specs`, `dependency_annotations`).

    Negative-spec: do NOT emit the inline flow-map form (`- {text: "..."}`) — the
    frontmatter validator rejects it.

    Spec backlink: docs/plans/2026-07-30-workstream-store-writer-and-parser.md § C2
    """
    if not items:
        return f"{key}: []"
    lines = [f"{key}:"]
    for item in items:
        lines.append(f"  - {item_key}: {_yaml_quote_string(item[item_key])}")
    return "\n".join(lines)


def _offending_field_for_yaml_error(exc: "yaml.YAMLError", line_owners: list[str]) -> str:
    """Map a `yaml.YAMLError`'s mark back to the field that composed that line.

    `line_owners[i]` names the field key responsible for the i-th (0-indexed)
    physical line of the document `_build_yaml` composed — see that function's
    `line_owners` construction. Falls back to a placeholder when the error
    carries no mark or the mark falls outside the tracked range (should not
    happen for a document this module itself composed, but this is
    diagnostic text, not a load-bearing invariant).

    Mirrors coordinator_core.ops.queue_append._offending_field_for_yaml_error exactly.
    """
    mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
    if mark is not None and 0 <= mark.line < len(line_owners):
        return line_owners[mark.line]
    return "<unknown field>"


def _build_yaml(schema_name: str, fields: dict) -> str:
    """Construct the YAML document string for a queue entry.

    Field order: base required fields first (created, title, body, status),
    then domain-required extensions, then optional fields present in the data.
    from_repo is emitted after created when present (base optional for
    debt/bug; domain required for improvement).

    Required and optional field lists are derived from the schema via the native
    schema.describe op, which returns ordered arrays preserving schema declaration
    order — simpler than the old dict-key iteration.

    Fail-loud round-trip gate (C2, docs/plans/2026-08-11-queue-append-quoter-gap-
    and-the-unparsea.md): the composed document is `yaml.safe_load`-parsed
    before being returned. On a `yaml.YAMLError` this RAISES a `ValueError`
    naming the offending field — it does not warn, log-and-continue, or return
    the malformed document. A warning on a corpus writer is how the unparseable-
    YAML class this gate closes accumulated unnoticed in the first place.

    Byte-parity is preserved BY CONSTRUCTION: this is parse-to-CHECK only — the
    parsed object is discarded and the ORIGINAL composed string is what gets
    returned on success. No `yaml.dump`/`yaml.safe_dump` anywhere on this path
    (§ YAML emission section header, above).
    """
    described = _schema_cli_describe(_SCHEMA_CLI_NAME.get(schema_name, schema_name))
    required = described.get("required") or []   # ordered list of field names in schema order
    optional = described.get("optional") or []   # ordered list of field names in schema order

    # Determine emit order: required fields first, then optional fields
    # that are present in the data.
    emit_order = list(required)
    for opt in optional:
        if opt in fields and fields[opt] is not None:
            if opt not in emit_order:
                emit_order.append(opt)

    lines = []
    # line_owners[i] names the field key that produced the i-th physical line
    # of the eventual "\n".join(lines) document — the offending-field lookup
    # the round-trip gate below uses to name a field in its raised error.
    line_owners: list[str] = []
    for key in emit_order:
        value = fields.get(key)
        if value is None:
            continue
        # system is a nested dict — emit with indented children, not as a scalar.
        if key == "system" and isinstance(value, dict):
            line = _emit_system_block(value)
        elif key == "deliverables" and isinstance(value, list):
            # workstream.schema.json requires block-map items ({text: "..."}) —
            # distinct from specs/dependency_annotations, which stay plain strings.
            # Review: code-reviewer (Finding 3) — the op's parallel copy dropped the
            # `value and isinstance(value[0], dict)` truthiness gate so an explicit
            # empty list routes into _emit_block_map_list_field's own "if not items:
            # return f'{key}: []'" shortcut instead of falling through to
            # _emit_yaml_field (which would emit a bare "deliverables:\n", parsing as
            # null, not []). Mirrored here so both copies dispatch identically again.
            line = _emit_block_map_list_field(key, value)
        else:
            line = _emit_yaml_field(key, value)
        if line:
            lines.append(line)
            line_owners.extend([key] * (line.count("\n") + 1))

    document = "\n".join(lines) + "\n"
    try:
        yaml.safe_load(document)
    except yaml.YAMLError as exc:
        offending_field = _offending_field_for_yaml_error(exc, line_owners)
        raise ValueError(
            f"queue.append: composed YAML document failed to parse — offending "
            f"field: {offending_field!r}. Fix the value passed for that field. "
            f"Underlying parser error: {exc}"
        ) from exc
    return document


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _format_validation_error(schema_name: str, raw_error: str) -> str:
    """Translate one schema.validate raw error string into a CLI-flag-shaped message.

    Handles the two recognised error shapes (missing required field, invalid enum
    value) by rewriting the schema field name into its `--kebab-case` CLI flag and,
    for enum errors, looking up the allowed-value list via _schema_cli_describe.
    Any other error shape passes through unchanged (fallback).

    Extracted from the former single-error branch of _validate() so both the
    single-error and multi-error (F12 fix) callers share one formatting path.
    """
    m_missing = re.match(r'^(.+): required field missing$', raw_error)
    if m_missing:
        field = m_missing.group(1)
        return f"missing required field: --{field.replace('_', '-')}"

    m_enum = re.match(r'^(.+): invalid enum value "(.+)"$', raw_error)
    if m_enum:
        field = m_enum.group(1)
        value = m_enum.group(2)
        described = _schema_cli_describe(_SCHEMA_CLI_NAME.get(schema_name, schema_name))
        enums = described.get("enums") or {}
        allowed = enums.get(field) or []
        if allowed:
            return (
                f"invalid value for --{field.replace('_', '-')}: '{value}'. "
                f"Valid values: {', '.join(str(v) for v in allowed)}."
            )
        return f"invalid value for --{field.replace('_', '-')}: '{value}'."

    # Fallback — surface the raw error string for any other error shape.
    return raw_error


def _validate(schema_name: str, fields: dict) -> None:
    """Fail-loud validation of field values against the schema.

    Delegates to the native schema.validate op for required-field presence and enum
    value checks. schema.validate reads coordinator_core/frontmatter/schemas/*.yaml/
    *.schema.json at runtime.

    Checks: unknown schema, missing required fields, invalid enum values.
    Negative-spec (tc-2 D2): no id field or id_prefix_pattern check —
    the filename is the canonical handle; id generation and validation are dropped.

    F12 fix: reports ALL missing-required / invalid-enum errors in one pass instead
    of failing on the first — schema.validate's underlying validateFrontmatter already
    collects the full errors list (docs/plans/2026-06-25 D1 base+extension shape), so
    this was previously discarding data schema.validate already computed. Single-error
    output text is byte-identical to the pre-fix single-error case (test battery
    compat); multi-error output prefixes a count line and bullets each formatted
    message.
    Spec backlink: tasks/2026-07-08-install-dogfood-friction.md § F12
    """
    if schema_name not in _SCHEMA_OUTPUT_DIRS:
        known = ", ".join(sorted(_SCHEMA_OUTPUT_DIRS.keys()))
        print(
            f"error: unknown schema '{schema_name}'. Known: {known}.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Delegate required-field + enum validation to the native schema.validate op.
    # Strip None/"" values before passing: the CLI populates all argparse
    # destinations into the fields dict (with None for absent flags), but
    # schema.validate treats absent keys as missing required fields.
    # Filtering out None/"" here aligns the two representations.
    effective_fields = {k: v for k, v in fields.items() if v is not None and v != ""}

    # _schema_cli_validate exits loudly on any route()/transport infra error.
    # Only a genuine op-level validation rejection is returned as (False, errors_list).
    cli_schema_name = _SCHEMA_CLI_NAME.get(schema_name, schema_name)
    ok, errors_list = _schema_cli_validate(cli_schema_name, effective_fields)

    if not ok:
        if not errors_list:
            print("error: validation failed", file=sys.stderr)
            sys.exit(1)

        formatted = [_format_validation_error(schema_name, e) for e in errors_list]

        if len(formatted) == 1:
            # Single-error shape is byte-identical to pre-fix behavior — test
            # battery assertions on this exact text continue to pass.
            print(f"error: {formatted[0]}", file=sys.stderr)
        else:
            print(f"error: {len(formatted)} validation errors:", file=sys.stderr)
            for msg in formatted:
                print(f"  - {msg}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Per-schema --help (F12)
# ---------------------------------------------------------------------------
#
# Fixes F12 (tasks/2026-07-08-install-dogfood-friction.md § F12): plain
# `--help` lists every flag across all six schemas as equally-optional, with no
# indication of which are required for a given --schema or what enum values a
# field accepts. Filing one queue entry previously took 3 rounds of
# trial-and-error (missing --status, invalid --severity, missing
# --proposed-action, unknown change-kind values) because none of that was
# discoverable from --help. `--schema NAME --help` now prints the schema's
# actual required/optional fields and any enum's allowed values, sourced from
# the SAME _schema_cli_describe() call the CLI's own validation path uses —
# so --help and enforcement cannot drift apart.
#
# Negative-spec: do NOT hand-maintain a second required-field/enum table here —
# always route through _schema_cli_describe so this stays in lockstep with
# coordinator_core/frontmatter/schemas/.

# Fields that are auto-resolved/auto-filled by the CLI even though the schema
# marks them required — worth calling out so a filer doesn't think they must
# pass them explicitly.
_AUTO_FILLED_FIELDS = {
    "created": "auto-filled with today's date if omitted",
    "from_repo": "auto-resolved from cwd git root if omitted",
}

# Fields present in a schema's required/optional list that have no matching
# CLI flag (built internally, not user-supplied) — excluded from --schema --help
# output so it doesn't advertise a flag that does not exist.
_NO_CLI_FLAG_FIELDS = {"system"}


def _flag_name_for_field(field: str) -> str:
    """Map a schema field name (snake_case) to its CLI flag (--kebab-case).

    All argparse destinations in this CLI use the field name with underscores
    swapped for hyphens as the flag spelling (e.g. proposed_action → --proposed-action,
    change_kind → --change-kind) — see _build_parser. No exceptions currently exist.
    """
    return "--" + field.replace("_", "-")


def _extract_schema_arg(argv: list[str]) -> str | None:
    """Best-effort extraction of a --schema value from argv for pre-parse --help routing.

    Handles both `--schema NAME` and `--schema=NAME` forms. Returns None if --schema
    is absent — caller falls through to argparse's normal --help behavior in that case.
    """
    for i, arg in enumerate(argv):
        if arg == "--schema" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--schema="):
            return arg.split("=", 1)[1]
    return None


def _print_schema_help(schema_name: str) -> None:
    """Print required/optional fields + enum allowed-values for one schema, then exit.

    Triggered when --help/-h is combined with --schema <name> on the command line
    (see main()). Exits 0 on a known schema (help request satisfied), exits 1 with
    the same "unknown schema" message _validate() uses if the schema name is bad —
    consistent error shape whether the CLI fails on --help or on validation.

    Spec backlink: tasks/2026-07-08-install-dogfood-friction.md § F12
    """
    if schema_name not in _SCHEMA_OUTPUT_DIRS:
        known = ", ".join(sorted(_SCHEMA_OUTPUT_DIRS.keys()))
        print(
            f"error: unknown schema '{schema_name}'. Known: {known}.",
            file=sys.stderr,
        )
        sys.exit(1)

    cli_schema_name = _SCHEMA_CLI_NAME.get(schema_name, schema_name)
    described = _schema_cli_describe(cli_schema_name)
    required = described.get("required") or []
    optional = described.get("optional") or []
    enums = described.get("enums") or {}

    def _field_line(field: str, requiredness: str) -> str | None:
        if field in _NO_CLI_FLAG_FIELDS:
            return None
        flag = _flag_name_for_field(field)
        parts = [f"  {flag:<24} ({requiredness})"]
        if field in enums:
            parts.append(f"— enum: {', '.join(str(v) for v in enums[field])}")
        if field in _AUTO_FILLED_FIELDS:
            parts.append(f"[{_AUTO_FILLED_FIELDS[field]}]")
        return " ".join(parts)

    print(f"coordinator-queue-append --schema {schema_name}")
    print()
    print("Required fields:")
    for field in required:
        line = _field_line(field, "required")
        if line:
            print(line)
    print()
    print("Optional fields:")
    for field in optional:
        line = _field_line(field, "optional")
        if line:
            print(line)
    print()
    print(
        "Run 'coordinator-queue-append --help' (without --schema) for full usage, "
        "flag descriptions, and worked examples."
    )
    sys.exit(0)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for coordinator-queue-append."""
    parser = argparse.ArgumentParser(
        prog="coordinator-queue-append",
        description=(
            "Append a structured YAML entry to a coordinator queue "
            "(debt-backlog, bug-backlog, improvement-queue, or lessons)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:

  # Debt backlog entry:
  coordinator-queue-append \\
      --schema debt-backlog \\
      --title "Fan-out overlap pass verifies interface presence, not correctness" \\
      --body "The overlap pass verifies a pinned interface file exists..." \\
      --source "daily-review/the Staff Engineer/2026-06-15" \\
      --status open \\
      --risk "Wrong pin causes divergent executor outputs." \\
      --proposed-action "Add interface-pin verification gate." \\
      --severity P2

  # Bug backlog entry:
  coordinator-queue-append \\
      --schema bug-backlog \\
      --title "publish.sh Phase 4 audit skips unchanged files" \\
      --body "AUDIT_FILES only covers newly-synced files..." \\
      --surface "setup/publish" \\
      --severity P1 \\
      --status open

  # Improvement queue entry:
  coordinator-queue-append \\
      --schema improvement-queue \\
      --title "Promote persona-name patterns into REVIEW_PATTERNS" \\
      --body "setup/publish.sh:88-95 should promote the 7 persona-name patterns..." \\
      --surface "setup/publish.sh:88-95" \\
      --proposed-action "setup/publish.sh (REVIEW_PATTERNS array)" \\
      --change-kind script-edit \\
      --status open

Spec backlink: docs/plans/2026-06-25-example-initiative-tc-2-queues-lessons-consolidation.md § C1
""",
    )

    # Universal fields (all schemas).
    parser.add_argument(
        "--schema",
        required=True,
        metavar="NAME",
        help="Queue schema to use: debt-backlog, bug-backlog, improvement-queue, or lessons.",
    )
    parser.add_argument(
        "--title",
        default=None,
        metavar="TEXT",
        help=(
            "One-line entry summary. Required for the shared base schemas "
            "(debt-backlog, bug-backlog, improvement-queue, lessons) and for "
            "--schema workstream (the workstream's display title). Not used by "
            "--schema workstream-event. Requiredness is enforced in main(), not "
            "here, so the workstream-store schemas can omit it (see "
            "_WORKSTREAM_STORE_SCHEMAS)."
        ),
    )
    parser.add_argument(
        "--body",
        default=None,
        metavar="TEXT",
        help=(
            "Multi-line description. Required for the shared base schemas "
            "(debt-backlog, bug-backlog, improvement-queue, lessons). Not used by "
            "--schema workstream or workstream-event. Use literal newlines or \\n. "
            "Requiredness is enforced in main(), not here (see _WORKSTREAM_STORE_SCHEMAS)."
        ),
    )
    parser.add_argument(
        "--status",
        default=None,
        metavar="VALUE",
        help="Lifecycle state. Valid base values: open, closed, deferred. bug-backlog also accepts wontfix. Defaults to open for --schema lessons.",
    )
    parser.add_argument(
        "--created",
        default=None,
        metavar="YYYY-MM-DD",
        help="Entry creation date. Defaults to today.",
    )

    # Unified cross-schema fields.
    parser.add_argument(
        "--surface",
        default=None,
        metavar="TEXT",
        help=(
            "The file/subsystem/script concerned. "
            "Required for bug-backlog (canonical name replacing legacy 'system') "
            "and improvement-queue. Optional for debt-backlog."
        ),
    )
    parser.add_argument(
        "--proposed-action",
        dest="proposed_action",
        default=None,
        metavar="TEXT",
        help=(
            "What to do about this entry — the remediation or fix target. "
            "Required for debt-backlog and improvement-queue; optional for bug-backlog."
        ),
    )
    parser.add_argument(
        "--tags",
        default=None,
        metavar="TAGS",
        help="Comma-separated filter tags (optional for all schemas).",
    )
    parser.add_argument(
        "--evidence",
        default=None,
        metavar="TEXT",
        help=(
            "Provenance: commit SHA, plan path, or related entry reference (optional, all schemas)."
        ),
    )
    parser.add_argument(
        "--case-against",
        dest="case_against",
        default=None,
        metavar="TEXT",
        help=(
            "(improvement-queue) The argument that lost — carried through from a plan "
            "deferral row's case_against, so a triager sees both sides. Optional."
        ),
    )

    # Closure fields (shared across debt/bug/improvement).
    parser.add_argument(
        "--closed-at",
        dest="closed_at",
        default=None,
        metavar="YYYY-MM-DD",
        help="Date the entry was closed/resolved (optional, all schemas).",
    )
    parser.add_argument(
        "--closed-by",
        dest="closed_by",
        default=None,
        metavar="SHA",
        help="Git commit SHA (or prose note) that closed the entry (optional, all schemas).",
    )

    # debt-backlog fields.
    parser.add_argument(
        "--source",
        default=None,
        metavar="TEXT",
        help=(
            "(debt-backlog) Originating review or observation — required for debt-backlog. "
            "Kept as a distinct required debt field, NOT folded into generic evidence, "
            "to preserve provenance audit trail discipline."
        ),
    )
    parser.add_argument(
        "--risk",
        default=None,
        metavar="TEXT",
        help="(debt-backlog) Why this debt matters — consequence of leaving it unaddressed (required for debt-backlog).",
    )
    parser.add_argument(
        "--severity",
        default=None,
        metavar="LEVEL",
        choices=["P0", "P1", "P2", "P3"],
        help="(debt-backlog, bug-backlog) Priority classification: P0, P1, P2, P3. Required for bug-backlog; optional (default P2) for debt-backlog.",
    )

    # bug-backlog fields.
    parser.add_argument(
        "--why-blocked",
        dest="why_blocked",
        default=None,
        metavar="TEXT",
        help="(bug-backlog) Why the bug is parked rather than fixed now.",
    )
    parser.add_argument(
        "--repro-steps",
        dest="repro_steps",
        default=None,
        metavar="TEXT",
        help="(bug-backlog) Steps to reproduce, if non-trivial.",
    )
    parser.add_argument(
        "--environment",
        default=None,
        metavar="TEXT",
        help="(bug-backlog) Platform/session constraint where the bug manifests.",
    )

    # improvement-queue fields.
    parser.add_argument(
        "--change-kind",
        dest="change_kind",
        default=None,
        metavar="VALUE",
        help=(
            "(improvement-queue) Classification of the target change. "
            "Valid: script-edit, skill-edit, wiki-append, wiki-new, hook-edit, "
            "agent-prompt-edit, doc-edit, test-edit, code-edit."
        ),
    )

    # lessons fields.
    parser.add_argument(
        "--scope",
        default=None,
        metavar="VALUE",
        help=(
            "(lessons) Lesson scope classification. "
            "Required for lessons. Valid: universal, project, wiki-only."
        ),
    )
    parser.add_argument(
        "--target-wiki",
        dest="target_wiki",
        default=None,
        metavar="TEXT",
        help="(lessons) The 'Belongs in <wiki>.md' routing clause. Optional.",
    )
    parser.add_argument(
        "--proposed-target",
        dest="proposed_target",
        default=None,
        metavar="TEXT",
        help="(lessons) Doctrine/wiki/hook/skill the lesson routes to. Optional.",
    )
    parser.add_argument(
        "--trigger",
        default=None,
        metavar="TEXT",
        help=(
            "(lessons) The concrete situation or event that surfaced this lesson. Optional. "
            "author-supplied; do NOT LLM-extract from existing prose."
        ),
    )
    parser.add_argument(
        "--why",
        default=None,
        metavar="TEXT",
        help=(
            "(lessons) Root-cause explanation — why this matters and what breaks without it. Optional. "
            "author-supplied; do NOT LLM-extract from existing prose."
        ),
    )
    parser.add_argument(
        "--how-to-apply",
        dest="how_to_apply",
        default=None,
        metavar="TEXT",
        help=(
            "(lessons) Actionable guidance for applying this lesson in future situations. Optional. "
            "author-supplied; do NOT LLM-extract from existing prose."
        ),
    )

    # workstream (definition) fields — C2 render-from-queue store.
    parser.add_argument(
        "--workstream-id",
        dest="workstream_id",
        default=None,
        metavar="ID",
        help=(
            "(workstream) Stable identifier for this workstream; also the "
            "definition filename stem (state/workstreams/<workstream-id>.yaml). "
            "Required for --schema workstream."
        ),
    )
    parser.add_argument(
        "--deliverables",
        dest="deliverables",
        action="append",
        default=None,
        metavar="TEXT",
        help=(
            "(workstream) A deliverable slot's description. Repeat the flag for "
            "multiple deliverables (e.g. --deliverables \"A\" --deliverables \"B\") "
            "— NOT comma-delimited, so comma-bearing text survives verbatim. "
            "Emitted as the block-map form (`- text: \"...\"`) workstream.schema.json "
            "requires. A newline in any item is rejected with a named error. Optional."
        ),
    )
    parser.add_argument(
        "--specs",
        dest="specs",
        action="append",
        default=None,
        metavar="TEXT",
        help=(
            "(workstream) A spec link associated with this workstream (e.g. a "
            "docs/plans/ path). Repeat the flag for multiple specs — NOT "
            "comma-delimited. A newline in any item is rejected with a named "
            "error. Optional."
        ),
    )
    parser.add_argument(
        "--dependency-annotations",
        dest="dependency_annotations",
        action="append",
        default=None,
        metavar="TEXT",
        help=(
            "(workstream) Free-text dependency/rationale note (e.g. 'blocked by "
            "X', 'depends on Y'). Repeat the flag for multiple annotations — NOT "
            "comma-delimited. A newline in any item is rejected with a named "
            "error. Optional."
        ),
    )

    # workstream-event fields — C2 render-from-queue store.
    parser.add_argument(
        "--workstream",
        dest="workstream",
        default=None,
        metavar="ID",
        help=(
            "(workstream-event) The workstream_id this event mutates a field of. "
            "Required for --schema workstream-event."
        ),
    )
    parser.add_argument(
        "--field",
        dest="field",
        default=None,
        metavar="NAME",
        help=(
            "(workstream-event) The field-scoped sub-state this event mutates — "
            "e.g. 'status', 'deliverable[0].done', 'order'. Required for "
            "--schema workstream-event."
        ),
    )
    parser.add_argument(
        "--value",
        dest="value",
        default=None,
        metavar="TEXT",
        help="(workstream-event) The new value for the named field. Required for --schema workstream-event.",
    )
    parser.add_argument(
        "--sequence",
        dest="sequence",
        default=None,
        metavar="N",
        help=(
            "(workstream-event) Explicit machine-independent order key — an integer "
            "the writer obtains by counting existing events for this (workstream, "
            "field) and adding 1. Required for --schema workstream-event. NEVER "
            "derived from wall-clock time."
        ),
    )
    parser.add_argument(
        "--session",
        dest="session",
        default=None,
        metavar="ID",
        help=(
            "(workstream-event) Session id of the writer; the lexical tiebreaker "
            "when two events share the same --sequence. Required for --schema "
            "workstream-event."
        ),
    )
    parser.add_argument(
        "--supersedes",
        dest="supersedes",
        default=None,
        metavar="TEXT",
        help="(workstream-event) Optional retraction/correction pointer to a prior event.",
    )
    parser.add_argument(
        "--coordinator-root-path",
        dest="coordinator_root_path",
        default=None,
        metavar="PATH",
        help=(
            "(workstream, workstream-event) Dual-tenant discriminator — the git "
            "root path of the repo this record belongs to. Auto-resolved from the "
            "cwd git root when omitted; override only for tests or cross-repo "
            "routed writes."
        ),
    )

    # cross-repo-commitment fields.
    parser.add_argument(
        "--committed-by",
        dest="committed_by",
        default=None,
        metavar="REPO",
        help=(
            "(cross-repo-commitment) Registry shortname of the SIBLING repo that made "
            "the commitment — the counterparty, never this repo's own identity. "
            "Required for --schema cross-repo-commitment. Distinct from --from-repo, "
            "which this schema does not use — see docs/wiki/cross-repo-commitments-schema.md "
            "§ Negative-spec."
        ),
    )
    parser.add_argument(
        "--memo",
        dest="memo",
        default=None,
        metavar="PATH",
        help=(
            "(cross-repo-commitment) Archive path to the source cross-repo memo that "
            "carried the commitment. Required for --schema cross-repo-commitment."
        ),
    )
    parser.add_argument(
        "--commitment",
        dest="commitment",
        default=None,
        metavar="TEXT",
        help=(
            "(cross-repo-commitment) The specific text of what the sibling committed "
            "to doing — quote or closely paraphrase their own words. Required for "
            "--schema cross-repo-commitment."
        ),
    )
    parser.add_argument(
        "--observed",
        dest="observed",
        default=None,
        metavar="YYYY-MM-DD",
        help=(
            "(cross-repo-commitment) Date the commitment was actually made by the "
            "sibling (may predate --created, the ledger-entry authoring date). "
            "Required for --schema cross-repo-commitment."
        ),
    )

    # from_repo override (normally auto-resolved).
    parser.add_argument(
        "--from-repo",
        dest="from_repo",
        default=None,
        metavar="REPO",
        help="Override the auto-resolved from_repo value (default: resolved from cwd git root).",
    )

    # queue_scope — improvement-queue only.
    parser.add_argument(
        "--queue-scope",
        dest="queue_scope",
        default=None,
        metavar="SCOPE",
        help=(
            "(improvement-queue, lessons) Scope of the entry: 'central' for universal patterns "
            "destined for claude-klabauter's central improvement-queue/lessons store, 'project' for "
            "per-project entries. Defaults to 'project'. Fail-loud on invalid value."
        ),
    )

    # system provenance — optional agent identity (C2).
    parser.add_argument(
        "--created-by-agent",
        dest="created_by_agent",
        default=None,
        metavar="NAME",
        help=(
            "Agent identity for the system.created_by_agent provenance field "
            "(optional). When provided, the value is recorded in the system block "
            "alongside the auto-resolved session ID."
        ),
    )

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for coordinator-queue-append CLI."""
    # F12: --schema NAME --help (or -h) routes to per-schema help BEFORE argparse's
    # own --help handling fires (argparse would otherwise print generic top-level
    # help and exit, never reaching this branch). --help without --schema falls
    # through unchanged to parser.parse_args()'s normal top-level help.
    # Spec backlink: tasks/2026-07-08-install-dogfood-friction.md § F12
    _argv = sys.argv[1:]
    if "--help" in _argv or "-h" in _argv:
        _schema_arg = _extract_schema_arg(_argv)
        if _schema_arg:
            _print_schema_help(_schema_arg)

    parser = _build_parser()
    args = parser.parse_args()

    schema_name = args.schema
    if schema_name not in _SCHEMA_OUTPUT_DIRS:
        known = ", ".join(sorted(_SCHEMA_OUTPUT_DIRS.keys()))
        print(
            f"error: unknown schema '{schema_name}'. Known: {known}.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Apply schema-specific status defaults before validation.
    if args.schema == "lessons" and args.status is None:
        args.status = "open"

    # The workstream-store schemas (C2) have their own required-field shape —
    # neither carries title/body/status per the shared base field-set; they are
    # keyed by workstream_id / workstream+field+sequence+session instead.
    # Spec backlink: docs/plans/2026-07-08-project-tracker-render-from-queue.md § Chunks C2
    if schema_name in _WORKSTREAM_STORE_SCHEMAS:
        if schema_name == "workstream":
            missing = [
                f"--{name}" for name, val in (
                    ("workstream-id", args.workstream_id),
                    ("title", args.title),
                    ("created", args.created),
                ) if val is None
            ]
            if missing:
                parser.error(f"the following arguments are required for --schema workstream: {', '.join(missing)}")
            # Review: code-reviewer — F1 (P1): validate at ingestion time, before
            # this value ever reaches _output_path's filename_override join.
            _validate_workstream_identifier("workstream-id", args.workstream_id, parser)
            # Review: review-integrator (Finding 7) — --created is not a filename
            # component for `workstream` (no traversal exposure), but was otherwise
            # left asymmetrically unvalidated next to workstream-event's discipline
            # below; validated here too for validation-coverage symmetry
            # (informational only), and only when explicitly supplied.
            if args.created is not None:
                _validate_created_date(args.created, parser)
            # C2: reject a newline in any --deliverables/--specs/--dependency-annotations
            # item before it ever reaches _build_yaml — see _reject_newline_in_list_items.
            _reject_newline_in_list_items("deliverables", args.deliverables, parser)
            _reject_newline_in_list_items("specs", args.specs, parser)
            _reject_newline_in_list_items(
                "dependency-annotations", args.dependency_annotations, parser
            )
        else:  # workstream-event
            missing = [
                f"--{name}" for name, val in (
                    ("workstream", args.workstream),
                    ("field", args.field),
                    ("value", args.value),
                    ("sequence", args.sequence),
                    ("session", args.session),
                ) if val is None
            ]
            if missing:
                parser.error(f"the following arguments are required for --schema workstream-event: {', '.join(missing)}")
            # Review: code-reviewer — F1 (P1): --workstream and --session are also
            # interpolated into the workstream-event filename (see legacy_fn's
            # filename_override branch) — validate both, not just --workstream-id.
            _validate_workstream_identifier("workstream", args.workstream, parser)
            _validate_workstream_identifier("session", args.session, parser)
            # Parity fix: --created is ALSO interpolated into this same filename
            # (f"{created}-{args.workstream}-{args.session}.yaml") but was never
            # validated — validate here, before any path construction, and only
            # when explicitly supplied (the default-to-today value is always
            # well-shaped). See _validate_created_date's doc-comment for why the
            # workstream-identifier allowlist is the wrong oracle for a date field.
            if args.created is not None:
                _validate_created_date(args.created, parser)
    else:
        # Shared base field-set schemas (debt-backlog, bug-backlog, improvement-queue,
        # lessons, cross-repo-commitment): the required-field set is DERIVED from the
        # native schema.describe op (the same call _print_schema_help already uses),
        # so one run names every missing required flag at once instead of disclosing
        # them one parser.error() at a time across repeated invocations. created/
        # from_repo are excluded — both auto-resolve when omitted (see
        # _AUTO_FILLED_FIELDS) — and `system` has no CLI flag (_NO_CLI_FLAG_FIELDS).
        # Fixes cross-repo memo 2026-08-11-project-rag-em-queue-append-required-fields-undiscoverable.md
        # items 1 (--title/--body one-per-run) and 2 (--status/--risk not
        # argparse-required despite the write refusing without them).
        described = _schema_cli_describe(_SCHEMA_CLI_NAME.get(schema_name, schema_name))
        required_fields = described.get("required") or []
        missing = [
            _flag_name_for_field(field)
            for field in required_fields
            if field not in _NO_CLI_FLAG_FIELDS
            and field not in _AUTO_FILLED_FIELDS
            and getattr(args, field, None) is None
        ]
        if missing:
            parser.error(
                f"the following arguments are required for --schema {schema_name}: "
                f"{', '.join(missing)}"
            )

    # Validate and resolve queue_scope (improvement-queue only; fail-loud on invalid).
    queue_scope = None
    if args.queue_scope is not None:
        if args.queue_scope not in _VALID_QUEUE_SCOPES:
            print(
                f"error: invalid --queue-scope value: '{args.queue_scope}'. "
                f"Valid values: {', '.join(_VALID_QUEUE_SCOPES)}.",
                file=sys.stderr,
            )
            sys.exit(1)
        queue_scope = args.queue_scope

    # Review: code-reviewer — F1: schema guard for --queue-scope; only improvement-queue supports it.
    # --queue-scope central on debt-backlog or bug-backlog would silently redirect those entries
    # into <claude-klabauter-root>/state/<schema>/ which is semantically wrong and undocumented.
    # Review: code-reviewer — B-F2 (nit): cross-repo-commitment is deliberately excluded
    # too — it has no central/project distinction (always a sibling-owed watch-ledger
    # written to the current repo), not merely an oversight from the C3b addition.
    if queue_scope is not None and schema_name not in ("improvement-queue", "lessons"):
        print(
            f"error: --queue-scope is only valid for --schema improvement-queue or lessons "
            f"(got '{schema_name}').",
            file=sys.stderr,
        )
        sys.exit(1)

    # Review: code-reviewer — (F3-parity hoist) _current_repo_root() spawns a
    # `git rev-parse`; hoist once here and reuse below (coordinator_root_path,
    # repo_root) instead of re-spawning, mirroring coordinator-lesson-promote's
    # documented F3 hoist.
    _raw_root = _current_repo_root()

    # Resolve from_repo (auto-detect or override).
    from_repo = args.from_repo if args.from_repo else _resolve_from_repo(root=_raw_root)

    # Resolve created date.
    created = args.created if args.created else _today_iso()

    # Parse tags: comma-separated string → list.
    tags = None
    if args.tags:
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    # Build system provenance block (C2).
    # provenance_completeness is valid-by-construction: "complete" when session_id
    # resolves (non-empty), "unknown" otherwise — no user path can set it to any
    # other value, satisfying the AC4 enum guard at the writer.
    session_id = _resolve_session_id()
    system: dict = {}
    if session_id:
        system["created_by_session"] = session_id
    if args.created_by_agent:
        system["created_by_agent"] = args.created_by_agent
    system["linked_sessions"] = [session_id] if session_id else []
    # linked_commits: omitted — not available at write time.
    system["provenance_completeness"] = "complete" if session_id else "unknown"

    if schema_name in _WORKSTREAM_STORE_SCHEMAS:
        # Auto-resolve the dual-tenant discriminator, mirroring from_repo's
        # auto-resolution — override only for tests/cross-repo routed writes.
        # coordinator_root_path is repo-ROOT-RELATIVE per the cockpit contract
        # (coordinator_root.py / goal.py): "." for a single-root repo, "subdir"
        # for a monorepo sub-root. The auto-resolve case IS the git root itself
        # (== coordinator root == repo root), so the relative form is ".". Passing
        # an absolute path (_raw_root / os.getcwd()) minted a machine-specific
        # coordinator_root_path → a distinct repo_fk per machine/checkout for one
        # logical repo (claude-klabauter-em fyi 2026-07-21). repo_root is resolved
        # and passed to the engine separately below (L~1681), so "." here does not
        # lose the filesystem anchor.
        # Spec backlink: docs/plans/2026-07-08-project-tracker-render-from-queue.md § Chunks C2
        coordinator_root_path = (
            args.coordinator_root_path
            if args.coordinator_root_path
            else "."
        )
        if schema_name == "workstream":
            fields = {
                "workstream_id": args.workstream_id,
                "title": args.title,
                "created": created,
                "coordinator_root_path": coordinator_root_path,
                # C2: block-map deliverables (schema-required object-with-text
                # items — converted here so both schema.validate and
                # _build_yaml's block-map emission see the same {"text": ...}
                # shape); specs/dependency_annotations stay plain string lists —
                # _emit_yaml_field's existing list branch already handles those.
                "deliverables": (
                    [{"text": item} for item in args.deliverables]
                    if args.deliverables
                    else None
                ),
                "specs": args.specs,
                "dependency_annotations": args.dependency_annotations,
            }
        else:  # workstream-event
            try:
                sequence = int(args.sequence)
            except (TypeError, ValueError):
                print(
                    f"error: --sequence must be an integer, got {args.sequence!r}",
                    file=sys.stderr,
                )
                sys.exit(1)
            # Review: code-reviewer — F4 (nit): int("-5") parses successfully with
            # no range check. The schema docstring/help text says sequence starts
            # at 1 and increments — reject non-positive values consistent with
            # that contract (does not cross-check against on-disk events; see F3).
            if sequence < 1:
                print(
                    f"error: --sequence must be >= 1 (starts at 1, increments), got {sequence}",
                    file=sys.stderr,
                )
                sys.exit(1)
            fields = {
                "workstream": args.workstream,
                "field": args.field,
                "value": args.value,
                "sequence": sequence,
                "session": args.session,
                "coordinator_root_path": coordinator_root_path,
                "supersedes": args.supersedes,
            }
    else:
        fields = {
            # Universal base fields.
            "created": created,
            "title": args.title,
            "body": args.body.replace("\\n", "\n"),
            "status": args.status,
            # Base optional fields (canonical unified names).
            "from_repo": from_repo,
            "surface": args.surface,
            "proposed_action": args.proposed_action,
            "closed_at": args.closed_at,
            "closed_by": args.closed_by,
            "tags": tags,
            "evidence": args.evidence,
            "case_against": args.case_against,
            # debt-backlog domain fields.
            "source": args.source,
            "risk": args.risk,
            "severity": args.severity,
            # bug-backlog domain fields.
            "why_blocked": args.why_blocked,
            "repro_steps": args.repro_steps,
            "environment": args.environment,
            # improvement-queue domain fields.
            "change_kind": args.change_kind,
            "queue_scope": queue_scope,
            # lessons domain fields.
            "scope": args.scope,
            "target_wiki": args.target_wiki,
            "proposed_target": args.proposed_target,
            "trigger": args.trigger,
            "why": args.why,
            "how_to_apply": args.how_to_apply,
            # cross-repo-commitment domain fields. Note: this schema does NOT use
            # from_repo (see docs/wiki/cross-repo-commitments-schema.md § Negative-spec)
            # — committed_by carries the sibling-counterparty identity instead. The
            # from_repo key above is still populated in this dict but is excluded
            # on BOTH write paths: dropped by _build_yaml on the legacy path (its
            # required/optional lists never name it), and explicitly stripped from
            # _op_params on the native cc_invoke routing path below (Review:
            # code-reviewer — Finding 1 (P1): the native path's "drop NO field"
            # loop previously leaked from_repo into queue.append op params for
            # this schema despite the negative-spec).
            "committed_by": args.committed_by,
            "memo": args.memo,
            "commitment": args.commitment,
            "observed": args.observed,
            # system provenance block (C2).
            "system": system,
        }

    # ── Routing gate: queue.append via native cc_invoke when seam present ──────────────────
    # Spec backlink: docs/plans/2026-07-06-strang-08-arm-queue-facade-invoke-retarget.md § C2
    #
    # State-1 (coordinator_core.invoke disk-absent via CLAUDE_KLABAUTER_ROOT) → legacy_fn() is called.
    # State-2 (seam present) → cc_invoke → queue.append native op.
    # Transport failure on State-2 is a hard error; never falls back to legacy_fn.
    # Negative-spec: do NOT add a liveness probe, do NOT add try/except→legacy after native.
    repo_root = _raw_root or os.getcwd()

    def legacy_fn() -> None:
        # Note: return from legacy_fn() returns None to route(), signalling legacy-complete.
        # Write-core body preserved byte-identical to pre-swap HEAD.
        # Validate before writing.
        _validate(schema_name, fields)

        # Build YAML content.
        yaml_content = _build_yaml(schema_name, fields)

        # Compute output path and ensure directory exists.
        # _ClaudeKlabauterUnresolvable is raised by BOTH the central-scope branch
        # (queue_scope == "central") and the meta-repo cwd else-branch of
        # _output_path — central state routes to claude-klabauter unconditionally per
        # state-placement-law.md § Taxonomy "Central/global state", the same seam
        # the meta-repo per-project branch already used. Both degrade gracefully
        # per the graceful-degradation contract (WARN + skip, exit 0), distinguished
        # below by queue_scope so the WARN text names the write that was skipped.
        # workstream-store filenames are keyed by workstream_id / workstream+session,
        # not by title — see _output_path's filename_override parameter.
        # Spec backlink: docs/plans/2026-07-08-project-tracker-render-from-queue.md § Substrate
        filename_override = None
        if schema_name == "workstream":
            filename_override = f"{args.workstream_id}.yaml"
        elif schema_name == "workstream-event":
            filename_override = f"{created}-{args.workstream}-{args.session}.yaml"

        try:
            out_path = _output_path(
                schema_name,
                args.title,
                queue_scope=queue_scope,
                filename_override=filename_override,
            )
        except _ClaudeKlabauterUnresolvable as exc:
            # AC2-analog (central): degrade gracefully on unresolvable CLAUDE_KLABAUTER_ROOT for
            # central-scope writes (queue_scope == "central"). A coordinator install
            # without repos.claude_klabauter registered WARNs and skips rather than
            # hard-erroring. Central-scope is guarded (main()) to only ever apply to
            # improvement-queue/lessons — never the workstream-store schemas — so no
            # fail-loud carve-out is needed on this leg.
            # Spec backlink: docs/wiki/state-placement-law.md § Taxonomy "Central/global state"
            if queue_scope == "central":
                print(
                    f"warn: coordinator-queue-append: CLAUDE_KLABAUTER_ROOT unresolvable — "
                    f"skipping central write: {exc}",
                    file=sys.stderr,
                )
                print(
                    "  Remediation: run 'machine-local set repos.claude_klabauter /path/to/claude-klabauter'\n"
                    "  or set CLAUDE_KLABAUTER_ROOT=/path/to/claude-klabauter before invoking this CLI.\n"
                    "  Reference: plugins/coordinator/docs/wiki/machine-local-registry.md §4c",
                    file=sys.stderr,
                )
                return  # exits 0 via normal return from legacy_fn()
            # AC13: degrade gracefully on unresolvable CLAUDE_KLABAUTER_ROOT for meta-repo per-project
            # cwd writes (else-branch of _output_path). Unchanged from pre-flip behaviour
            # for all pre-existing schemas.
            # Spec backlink: pln-stop-the-rot-claude-klabauter-state-home-placement-4cc787 § AC13
            #
            # Review: code-reviewer — F5 (P2): for the workstream-store schemas (C2)
            # specifically, a silent WARN + exit-0 no-op defeats the whole store's
            # collision-safety/fold-correctness contract — this store is explicitly
            # the meta-repo's own tracker use case, so callers must be able to trust
            # that "exit 0" means "written". Fail loud here instead of degrading;
            # every OTHER schema sharing this branch keeps the pre-existing
            # graceful-degrade behavior unchanged.
            # Spec backlink: docs/plans/2026-07-08-project-tracker-render-from-queue.md § Substrate
            if schema_name in _WORKSTREAM_STORE_SCHEMAS:
                print(
                    f"error: coordinator-queue-append: CLAUDE_KLABAUTER_ROOT unresolvable — "
                    f"cannot write workstream-store record (schema={schema_name}): {exc}",
                    file=sys.stderr,
                )
                print(
                    "  Remediation: run 'machine-local set repos.claude_klabauter /path/to/claude-klabauter'\n"
                    "  or set CLAUDE_KLABAUTER_ROOT=/path/to/claude-klabauter before invoking this CLI.\n"
                    "  Reference: plugins/coordinator/docs/wiki/machine-local-registry.md §4c",
                    file=sys.stderr,
                )
                sys.exit(1)
            print(
                f"warn: coordinator-queue-append: CLAUDE_KLABAUTER_ROOT unresolvable — "
                f"skipping meta-repo per-project write: {exc}",
                file=sys.stderr,
            )
            print(
                "  Remediation: run 'machine-local set repos.claude_klabauter /path/to/claude-klabauter'\n"
                "  or set CLAUDE_KLABAUTER_ROOT=/path/to/claude-klabauter before invoking this CLI.\n"
                "  Reference: plugins/coordinator/docs/wiki/machine-local-registry.md §4c",
                file=sys.stderr,
            )
            return  # exits 0 via normal return from legacy_fn()
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        # Review: code-reviewer Slice-A — (A-F1) atomic write via temp+os.replace prevents partial-read
        # clobber when two concurrent writes target the same slug on the same calendar day.
        #
        # Collision guard (C1, legacy-fallback silent-overwrite fix): os.replace(tmp_path, out_path)
        # is a silent overwrite when out_path already exists — a same-date+slug collision from a
        # concurrent second write would destroy the first entry with no error. _write_out_path_excl
        # below replaces the plain os.replace with an exclusive-create + retry-with-suffix loop so
        # BOTH entries persist under distinct filenames; only a genuinely exhausted retry cap raises.
        # Counter-pattern (deliberate divergence): coordinator/bin/cross-repo-memo.py's _write_file
        # FAILS LOUD (FileExistsError, no retry) on collision because its caller is interactive and
        # retries with a new --topic. legacy_fn() here is a TERMINAL caller with no retry path — a
        # fail-loud refusal would DROP the entry instead of preserving it, so retry-with-suffix is
        # the correct shape for this call site, not the memo's fail-loud shape.
        # Spec backlink: docs/plans (chunk C1) F1/F2 legacy-fallback silent-overwrite collision guard.
        #
        # Review: code-reviewer — Finding 1 (P1). `workstream` DEFINITION writes must
        # OVERWRITE the existing <workstream_id>.yaml (genuine rewrite, per the schema's
        # own "rewritten atomically" doc-comment) rather than fork a `-2.yaml` sibling on
        # a second write to the same workstream_id. `workstream-event` (append-safe, both
        # survive) stays on `_write_out_path_excl` unchanged — do NOT widen this branch to
        # cover events.
        if schema_name == "workstream":
            final_path = _write_out_path_overwrite(out_path, yaml_content)
        else:
            final_path = _write_out_path_excl(out_path, yaml_content)

        print(final_path)
        # C5 floor (docs/plans/2026-08-14-cli-authored-writes-get-claimed.md):
        # this genuine dual-path CLI's State-1 body writes in-process, so the
        # write must be declared, not just printed. Guarded import: `route()`
        # only calls legacy_fn() when coordinator_core.invoke was already
        # unresolvable, so coordinator_core is usually unimportable here too —
        # this degrades to a no-op except under the QUEUE_APPEND_OUTPUT_ROOT
        # test-isolation gate below, which forces legacy_fn with a live engine
        # still on sys.path.
        try:
            from coordinator_core.session.declared_writes import declare_write  # noqa: PLC0415

            declare_write(final_path)
        except ImportError:
            pass

    def _run_legacy_with_write_declaration() -> None:
        """Run `legacy_fn` inside cli_entry's declare-write collection when
        the engine happens to be importable — see legacy_fn's own comment on
        why this is usually a no-op degrade. Both legacy_fn call sites below
        route through this instead of calling legacy_fn directly.

        Review: coordinator:code-reviewer — the QUEUE_APPEND_OUTPUT_ROOT
        test-isolation gate is not a rare edge case: it is exactly the shape
        this repo's own test suite invokes, with coordinator_core genuinely
        importable, so `recording_declared_writes`/`declare_write` fire for
        real under it. What keeps that safe is
        `ipc._record_self_reported_touches`'s F1 containment (2026-08-04):
        a declared path is only recorded as a session claim when it resolves
        INSIDE the caller's own `_origin_worktree`; a fixture path outside
        the repo tree (every existing test here uses a `tmpdir` outside the
        repo as both the env-gate root and cwd) is skipped, never claimed
        against whatever real session is an ancestor of the test process.
        This stays safe only as long as fixtures for this gate live outside
        the repo tree — an in-tree fixture path would be a live claim
        against the wrong session.
        """
        try:
            from coordinator_core.cli_entry import recording_declared_writes  # noqa: PLC0415
        except ImportError:
            legacy_fn()
            return
        with recording_declared_writes(cwd=repo_root):
            legacy_fn()

    # Test isolation gate: QUEUE_APPEND_OUTPUT_ROOT redirects the output path, which the
    # native op does not honour (it constructs its own path from schema + title).
    # When set, routing native would write to the wrong location — use legacy instead.
    # In production, QUEUE_APPEND_OUTPUT_ROOT is NEVER set, so this check is a no-op.
    if os.environ.get(_QUEUE_APPEND_OUTPUT_ROOT_ENV):
        _run_legacy_with_write_declaration()
        return

    # Build op params from the complete fields dict — drop NO field.
    # from_repo is already CLI-resolved via _resolve_from_repo() above (AC11 provenance parity).
    # The op's basename default diverges from the registry value; must pass explicitly.
    # Strip None values: absent optional fields must not appear as null in the op params.
    _op_params: dict = {"schema": schema_name}
    for _k, _v in fields.items():
        if _k == "system":
            # Exclude the nested system block — the op builds its own provenance from the
            # session_id op param passed below (falling back to CLAUDE_CODE_SESSION_ID env).
            continue
        if _v is not None:
            _op_params[_k] = _v
    # Review: code-reviewer — Finding 1 (P1): cross-repo-commitment's negative-spec
    # ("this record must never carry from_repo") is enforced field-by-field on the
    # legacy path (_build_yaml filters by schema required/optional lists) but the
    # native op-params loop above has no such filter — strip explicitly here rather
    # than rely on an unverified downstream (claude-klabauter-side) schema filter.
    if schema_name == "cross-repo-commitment":
        _op_params.pop("from_repo", None)
    # created_by_agent is inside system (not a top-level fields key); include explicitly.
    if args.created_by_agent:
        _op_params["created_by_agent"] = args.created_by_agent

    # Session provenance (AC11): pass the sentinel-resolved session_id as a caller-authoritative
    # op param. queue.append accepts session_id param-first (env fallback) as of claude-klabauter a9f0a9e,
    # so provenance is authoritative at the call site — no parent os.environ mutation, no
    # in-process env bleed. When session_id is falsy the param is omitted and the op's own env
    # fallback yields provenance_completeness: unknown (unchanged behavior).
    if session_id:
        _op_params["session_id"] = session_id

    # Review: code-reviewer — F3: wrap route() call in try/except so a State-2 transport
    # RuntimeError (timeout, ImportError, bad JSON-RPC envelope) surfaces as a clean
    # 'error:' line, consistent with every other failure path in this CLI that uses
    # print("error: ...", file=sys.stderr); sys.exit(1). Non-zero exit already correct;
    # this makes the stderr shape consistent.
    try:
        _native_result = _cc_route(
            "queue.append", _op_params, repo_root, _run_legacy_with_write_declaration
        )
    except RuntimeError as _exc:
        print(f"error: coordinator-queue-append: native transport failed: {_exc}", file=sys.stderr)
        sys.exit(1)

    # Legacy path: legacy_fn() already handled validate, write, and print(out_path).
    # Returns None on normal completion or on _ClaudeKlabauterUnresolvable graceful-skip.
    if _native_result is None:
        return

    # Native path: apply the queue.append-specific signal-2 verdict.
    # Writer ops use out_path/skipped — NOT exit_code (which is a guard/query-op signal).
    if _native_result.get("skipped"):
        # Contract pt 5 (AC12): map skipped:true → legacy WARN + exit 0 (no path printed).
        # Parity with the legacy path's _ClaudeKlabauterUnresolvable WARN messages — both routes
        # degrade on unresolvable CLAUDE_KLABAUTER_ROOT, not DOE_ROOT (see docs/wiki/state-placement-law.md
        # § Taxonomy "Central/global state"). The native op's _output_path (coordinator_core/ops/
        # queue_append.py) raises _ClaudeKlabauterUnresolvable on THREE branches — central-scope,
        # meta-repo-cwd, and the caller_worktree-is-None fallback — not central-scope alone, so
        # the message is branched on queue_scope to avoid claiming "central write" for a
        # non-central skip (Review: code-reviewer — Finding 2).
        _skip_kind = "central" if queue_scope == "central" else "meta-repo per-project"
        print(
            f"warn: coordinator-queue-append: CLAUDE_KLABAUTER_ROOT unresolvable — "
            f"skipping {_skip_kind} write: {_native_result.get('reason', 'claude-klabauter root unresolvable')}",
            file=sys.stderr,
        )
        print(
            "  Remediation: run 'machine-local set repos.claude_klabauter /path/to/claude-klabauter'\n"
            "  or set CLAUDE_KLABAUTER_ROOT=/path/to/claude-klabauter before invoking this CLI.\n"
            "  Reference: plugins/coordinator/docs/wiki/machine-local-registry.md §4c",
            file=sys.stderr,
        )
        return

    # Native success: print the written path (stdout parity with legacy print(out_path) — AC2/AC5).
    # Review: code-reviewer — F1: guard against a malformed success envelope. A bare KeyError
    # gives an uninformative traceback; a contract violation (success envelope with neither
    # out_path nor skipped) should raise RuntimeError with diagnostics so the failure is
    # attributable without reading a traceback.
    out_path = _native_result.get("out_path")
    if not out_path:
        raise RuntimeError(
            f"queue.append: native op returned success envelope without 'out_path' or 'skipped'. "
            f"Result keys: {list(_native_result.keys())!r}"
        )
    print(out_path)


if __name__ == "__main__":
    main()
