"""
coordinator-doc-new — scaffold a conformant coordinator document (handoff, spinoff, memo, plan, decision, audit-record, completion, sidecar, run-report [alias: flight-recorder], research-synthesis, review-findings) or delegate to a typed writer for queue/lesson/workflow types.
# Review: code-reviewer slice-B F7 — module docstring updated to list all supported types.

Spec backlink: docs/plans/2026-06-25-example-initiative-tc-0-canonical-baton-shape.md § C4 (D3)
Spec backlink (A4): docs/plans/2026-06-25-example-initiative-tc-4-fleet-machinery-contract-emit.md § A4
Spec backlink (C3b): pln-fleet-deliverable-spine-identity-and-facets-2b331c § D1, D2, D3, C3b

Purpose: Emit conformant frontmatter + the canonical section skeleton for a baton
artifact, writing it to a file. The EM fills the body via Edit. This is the GENERATE
altitude of the schema registry — the third altitude that kills frontmatter drift at
the source by making the schema the production template, not just the validation rule.

Supported types:
  handoff            — session continuation baton (kind: session-handoff)
                       handoff_phase: continuation is scaffolded unconditionally;
                       execution_authorized_* fields are deliberately NOT scaffolded
                       (stamped only at execution-authorization time — see
                       docs/plans/2026-07-17-execution-handoff-phase-doe-contract.md § C4)
  recovery           — crash-recovery baton (kind: recovery); predecessor is a crashed
                       commit SHA or null (NOT a predecessor handoff path);
                       recovers_session names the crashed session id
  spinoff            — workstream-fork baton (kind: spinoff)
  roadmap-baton      — roadmap stub baton (kind: roadmap-baton)  requires --roadmap-id --stub-id
                       BACKWARD-COMPAT ALIAS: --type spinoff-roadmap (same emitter, same
                       output shape) — the flag now agrees with the kind it scaffolds.
  goal-seed          — goal-scoped fork baton (kind: goal-seed), no predecessor baton
                       BACKWARD-COMPAT ALIAS: --type spinoff-goal
  roadmap-seed       — roadmap-stub-producing fork baton (kind: roadmap-seed), no predecessor baton
                       BACKWARD-COMPAT ALIAS: --type spinoff-roadmap-creator
  memo               — cross-repo memo LOCAL skeleton (not delivered; send via cross-repo-memo)
  plan               — plan document (docs/plans/YYYY-MM-DD-<slug>.md)
                       REQUIRES an explicit sizing answer: --sizing-object PATH, or
                       --no-sizing-object to declare the plan genuinely has none
  decision           — architecture decision record (docs/decisions/DR-NNN-<slug>.md,
                       DR number allocated + collision-checked; optional --dr-prefix)
  audit-record       — architecture audit record (docs/architecture/audit-records/YYYY-MM-DD-<system>.md)  requires --system <name>
  completion         — workstream completion log entry (archive/completed/YYYY-MM/YYYY-MM-DD-<slug>.md)  optional --nature, --chain
  goal               — goal artifact with OKR frontmatter (state/goals/YYYY-MM-DD-<slug>.yaml)
  sizing-object      — fleet routing-lobby sizing record (state/sizings/YYYY-MM-DD-<slug>.yaml)
  health-status      — daily health summary record (state/health/YYYY-MM-DD-health-summary.md)
  strategic-self-description — per-repo strategic self-description, whole-document-YAML
                       (state/strategic/self-description.yaml); one-per-repo, not date/slug-derived
  review             — review sidecar (docs/plans/<stem>.review.md)  requires --plan <stem>
  prior-art-check    — prior-art-check sidecar               requires --plan <stem>
  plan-coverage-check — plan-coverage-check sidecar          requires --plan <stem>
  docs-check         — docs-check sidecar                    requires --plan <stem>
  run-report         — universal subagent run-report sidecar requires --plan <path> --chunk <id> --out <path>
                       --out is REQUIRED (no default path); the live output location is
                       state/subagent-share/<session-id>/<key>.md, path owned and computed
                       by claude-klabauter's provision_report engine at spawn time
                       (superset schema — subsumes flight-recorder; DEC-3, plan
                       2026-07-13-subagent-run-report-subsume.md § C4)
  flight-recorder    — BACKWARD-COMPAT ALIAS for --type run-report (same emitter,
                       same output path/shape). Kept so in-flight callers do not break.
  research-synthesis — deep-research synthesis record (docs/research/YYYY-MM-DD-<slug>.md)
                       frontmatter index over a PROTECTED expressive prose body (HEADERS ONLY in scaffold)
  review-findings    — code-reviewer self-persist findings sidecar  requires --slice <id> --scope <comma-paths>
                       outputs to state/subagent-share/<session-id>/YYYY-MM-DD-codereview-slice<ID>-<SLUG>.md
                       (the DR-091 home -- same session-scoped root provision_report uses; SLUG is
                       sanitized from --scope; the <!-- FINDINGS --> sentinel is the Edit anchor)
  subagent-sidecar   — agent-side decision-object container (schemas/decision-object.schema.json
                       $defs/subagent_sidecar)  requires --plan <path> --chunk <id> --out <path>
                       --out is REQUIRED (no default); the LIVE sidecar path is computed by
                       coordinator_core.dispatch.provision at spawn time under
                       state/subagent-share/<session-id>/<key>.md. This CLI branch is the
                       manual/test scaffold path only. Carries completion_status (backlinks the
                       existing query-completions surface, not a fourth store),
                       divergence_from_plan, and tell_the_EM (freeform exit interview) --
                       distinct from --type run-report's lifecycle-tracker shape.
                       (docs/plans/2026-07-24-canonical-resolution-engine.md § W2-B3, R7 Addendum)

  Queue types (A4 — delegate to coordinator-queue-append, do NOT re-implement schema):
  improvement-queue  — DELEGATES to coordinator-queue-append --schema improvement-queue
  bug-backlog        — DELEGATES to coordinator-queue-append --schema bug-backlog
  debt-backlog       — DELEGATES to coordinator-queue-append --schema debt-backlog

  Lesson type (A4 — delegate to coordinator-lesson-promote, outbox/promote altitude):
  lesson             — DELEGATES to coordinator-lesson-promote
                       (lessons-outbox YAML, NOT a lessons.md capture line — per tc-2 D3)

  Workflow type (delegate to coordinator-workflow-scaffold.py, claude-klabauter workflow.scaffold op):
  workflow           — DELEGATES to coordinator-workflow-scaffold.py
                       requires --name (or --title) --description (or --title)
                       COMPUTE_ONLY op: returns Workflow-skeleton script text, not a
                       frontmatter document; writes to --out (or stdout when omitted)

Fail-loud on unknown --type: exits non-zero and lists the known type set.

For memo: uses the shared memo_compose.compose_frontmatter (extracted from
bin/cross-repo-memo) to emit validator-clean frontmatter. The memo delivery
surface (routing, realpath containment, claim-lock) stays wholly in cross-repo-memo.

Invocation:
  coordinator-doc-new --type handoff [--title "..."] [--branch "..."] [--out PATH]
  coordinator-doc-new --type spinoff [--title "..."] [--branch "..."] [--out PATH]
  coordinator-doc-new --type memo --to RECEIVER --topic SLUG --title "..." [--out PATH]
                                  [--from-repo SENDER]

Output: the scaffolded file path is printed to stdout.
Uncommitted — leaves the file dirty so it surfaces in `git status`.

Negative-spec: coordinator-doc-new does NOT deliver memos, route to receivers,
check realpath containment, stamp claim-locks, or manage the memo lifecycle. Those
surfaces belong wholly to bin/cross-repo-memo. This tool creates the LOCAL skeleton.

Negative-spec: does not modify any schema, skill, or hook — it reads schemas at
runtime to derive section vocabulary but does not write to any registry file.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime
import hashlib
import io
import json
import os
import random
import re
import subprocess
import sys
import tempfile

# ---------------------------------------------------------------------------
# Shared memo composer — bin/lib/memo_compose.py (example-initiative tc-0 C4)
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_SCRIPT_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from memo_compose import (  # noqa: E402
    compose_memo as _memo_compose,  # Review: code-reviewer S3-F3 — use compose_memo (full-doc composer) instead of compose_frontmatter + manual concat
    _today,
    _yaml_quote,
    _SUMMARY_MAX_CHARS,
)
from machine_local_impl_resolve import (  # noqa: E402
    claude_home as _mlir_claude_home,
    settings_home as _mlir_settings_home,
)
from dr_allocator import (  # noqa: E402
    allocate_dr_number as _allocate_dr_number,
    assert_dr_id_unique as _assert_dr_id_unique,
    DrAllocatorError as _DrAllocatorError,
)

# ---------------------------------------------------------------------------
# Engine seam — claude-klabauter checkout on sys.path
# ---------------------------------------------------------------------------
_CLAUDE_KLABAUTER_ROOT_RESOLVED: str | None = None


def _ensure_engine_on_path() -> str | None:
    """Put the claude-klabauter checkout on ``sys.path`` so ``coordinator_core`` imports.

    Memoizing wrapper over ``cc_invoke.ensure_engine_on_path`` — that function
    owns the ladder (env var → self-location walk-up → settings-home
    pointer file → machine-local ``repos.claude_klabauter``), so a hand-set
    ``PYTHONPATH`` is never a prerequisite of this CLI and the ordering cannot
    drift away from the ~26 sibling entrypoints resolving through the same seam.

    Called once at import time and again from each engine-touching seam below,
    so a published/vendored copy that only resolves through a later rung still
    gets the path in place on the arm that needs it. ``coordinator_core.ops``
    registers ops lazily, unconditionally, so the handoff arm's import budget
    needs no priming for that.

    Best-effort: returns None when every rung misses, matching this file's
    graceful-skip convention for un-migrated installs (see
    ``_assert_no_archived_handoff_twin``) rather than failing a scaffold that
    has no engine work to do.

    Memoization applies only to a SUCCESSFUL resolution — ``_CLAUDE_KLABAUTER_ROOT_RESOLVED``
    is only ever assigned a non-None value, so a failed/degraded resolution is
    never cached and re-attempts on every subsequent call. This costs repeated
    resolution work per call site on a failing install, not a correctness bug.

    Spec backlink: cross-repo memo — coordinator-doc-new broken from its .cmd
    forwarder (ModuleNotFoundError: coordinator_core without a hand-set
    PYTHONPATH); the engine-touching seams below resolved the root ad hoc
    through ``cc_invoke._resolve_claude_klabauter_root`` (registry-only, no
    self-location rung) or not at all.

    Negative-spec: does NOT export the engine root into ``os.environ`` — child
    processes run their own resolution through the same ladder.
    """
    global _CLAUDE_KLABAUTER_ROOT_RESOLVED
    if _CLAUDE_KLABAUTER_ROOT_RESOLVED is not None:
        return _CLAUDE_KLABAUTER_ROOT_RESOLVED
    try:
        # Review: code-reviewer dccd9967 F3 — the resolution CALL, not just the
        # import, must sit inside this guard: ensure_engine_on_path's internal
        # path-walk (Path.resolve()/.parents/.is_dir()) can raise OSError/
        # PermissionError on a broken junction or symlink loop, which its own
        # `except RuntimeError` does not catch. This runs at MODULE IMPORT time,
        # so an uncaught OSError here would crash every invocation outright —
        # restores ce48a1adb's wrap-the-whole-attempt posture the refit narrowed.
        from cc_invoke import ensure_engine_on_path  # noqa: PLC0415
        _CLAUDE_KLABAUTER_ROOT_RESOLVED = ensure_engine_on_path(__file__)
    except Exception:  # noqa: BLE001 -- lib seam absent or resolution failed; degrade to no-engine
        return None
    return _CLAUDE_KLABAUTER_ROOT_RESOLVED


_ensure_engine_on_path()

# Canonical Session Ledger block — owned by coordinator_core.session_ledger (the
# package that also parses it, session_ledger.aggregate_chain_loe). Best-effort
# import matching _ensure_engine_on_path()'s documented graceful-skip convention:
# an unresolvable engine must not hard-fail every doc type (memo, plan, decision,
# sidecar, ...), only the six ledger-owing scaffolders that actually need this
# constant — those fail loudly at the point of use instead (see
# _require_session_ledger_block below).
# Review: code-reviewer 49e8b242 P1 — bare module-level import broke --help and
# every non-ledger-owing doc type on an unresolvable engine; this restores the
# file's own fail-open convention while keeping the six ledger-owing scaffolders
# loud on the same failure.
# Spec backlink: pln-ledger-owing-handoff-kinds-emi-648818 § C2
try:
    from coordinator_core.session_ledger import SESSION_LEDGER_BLOCK_LINES  # noqa: E402
except ImportError:  # noqa: BLE001 -- best-effort import; unresolvable engine degrades to None
    SESSION_LEDGER_BLOCK_LINES = None

# `canonical_kind` — the ONE canonical legacy<->target `kind` aliasing
# function (coordinator_core.frontmatter.baton_class), routed through here
# instead of a local literal --type alias table so this CLI stays covered by
# `coordinator_core/tests/test_baton_class_is_the_only_membership_set.py`'s
# single-owner rule. Same best-effort degrade-to-None posture as
# SESSION_LEDGER_BLOCK_LINES above: an unresolvable engine costs the legacy
# --type spellings' normalization (they fail the known-type gate below
# instead, same as any other unrecognized --type), not a crash on every
# other doc type.
try:
    from coordinator_core.frontmatter.baton_class import canonical_kind as _canonical_kind  # noqa: E402
except ImportError:  # noqa: BLE001 -- best-effort import; unresolvable engine degrades to None
    _canonical_kind = None

# `derive_readiness` — the ONE readiness-deriving predicate set (C1,
# docs/plans/2026-08-19-gate-notes-are-advisory-blocked-by-derives-readiness.md).
# --gated-open (C3 below) feeds it a scaffold-time `blocked_by` guess — the
# flag DECLARES THE BLOCKER, it does not hardcode the readiness trio itself;
# C1 derives deployment_state/pickup_ready from that declared blocker. The
# no-flag (`blocked_by: []`) path also routes through this same function so
# there is exactly one place that decides readiness — not a hardcoded literal
# duplicating C1's empty-blocked_by rule. Same best-effort degrade-to-None
# posture as the two imports above: an unresolvable engine costs --gated-open
# specifically (it fails loud at the point of use, see _scaffold_handoff) and
# falls back to the pre-C1 hardcoded ready_to_fire default for the no-flag
# path (no engine dependency for the byte-identical majority case), not every
# other doc type.
try:
    from coordinator_core.reconcile.gate_eval import derive_readiness as _derive_readiness  # noqa: E402
except ImportError:  # noqa: BLE001 -- best-effort import; unresolvable engine degrades to None
    _derive_readiness = None


def _no_console_creationflags() -> dict:
    """``subprocess`` kwargs that suppress a console window on Windows.

    Degrade-to-empty wrapper over ``coordinator_core.win_portability``'s helper
    of the same name: the engine seam stays the source of truth when it is
    importable, and an unresolvable engine costs a console flash on Windows
    rather than a ``ModuleNotFoundError`` traceback out of a scaffold arm that
    is otherwise engine-independent.
    """
    _ensure_engine_on_path()
    try:
        from coordinator_core.win_portability import (  # noqa: PLC0415
            no_console_creationflags,
        )
    except Exception:  # noqa: BLE001 -- engine absent; no console-suppression kwargs
        return {}
    return no_console_creationflags()


def _no_console_passthrough_kwargs() -> dict:
    """``_no_console_creationflags`` for a child whose output must reach the
    operator.

    Console suppression alone makes the child bind its standard handles to the
    window-less console ``CREATE_NO_WINDOW`` allocates rather than inheriting
    this process's, so the delegate's output is lost. Same degrade-to-empty
    posture as its sibling above; canonical implementation is
    ``coordinator_core.win_portability.no_console_passthrough_kwargs``.
    """
    kwargs = dict(_no_console_creationflags())
    for key, stream in (("stdout", sys.stdout), ("stderr", sys.stderr)):
        try:
            fd = stream.fileno()
        except (AttributeError, ValueError, OSError):
            continue
        if fd >= 0:
            kwargs[key] = fd
    return kwargs

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Type registries — derived from schemas/coordinator-registry.manifest.json via bin/lib/coordinator_registry.py.
# Do not add literal type lists here; update the manifest instead.
from coordinator_registry import (  # noqa: E402
    KNOWN_TYPES as _KNOWN_TYPES,
    DOC_TYPES as _DOC_TYPES,                 # raw docTypes tuple — offerable/excludeReason for the non-scaffoldable guard
    SIDECAR_TYPES as _SIDECAR_TYPES,
    SIDECAR_SUFFIXES as _SIDECAR_SUFFIXES,  # review F3 — replaces local _SIDECAR_SUFFIX dict
    QUEUE_TYPES as _QUEUE_TYPES,
    REPO_ALIASES as _REPO_KEY_ALIASES,
    em_id_for_root as _em_id_for_root,      # C2b — shared resolver; no home param
)  # Review: code-reviewer — F2: removed dead import repo_key_to_em_id; only _em_id_for_root is called here

# --type run-report — LOCAL shim, not yet manifest-registered.
#
# coordinator-registry.manifest.json's docTypes/kindOfferOverride entries for
# "run-report" (replacing "flight-recorder") are C8a's write-target in the
# subagent-run-report-subsume plan (schema/registry retirement chunk, gated on
# this chunk (C4) + C2/C5 landing first). Until C8a lands, "run-report" is
# unknown to the manifest-derived _KNOWN_TYPES import above, so it is unioned
# in locally here — a minimal, additive shim scoped to THIS file only. C8a's
# manifest edit will make this shim redundant (harmless to keep; the union is
# idempotent), not conflicting — do not pre-empt C8a's surface from here.
#
# Spec backlink: docs/plans/2026-07-13-subagent-run-report-subsume.md § C4, C8a
_KNOWN_TYPES = _KNOWN_TYPES | frozenset({"run-report"})

# subagent-sidecar formerly carried a LOCAL shim here identical in shape to
# the run-report one above (docs/plans/2026-07-24-canonical-resolution-
# engine.md § W2-B3). coordinator-registry.manifest.json now carries a
# "subagent-sidecar" docTypes entry (offerable: false — the agent-side
# decision-object container is always caller-scaffolded via --out, never
# offered), so _KNOWN_TYPES already includes it via the import above and the
# local union was retired rather than kept as a harmless-idempotent no-op.

# Slug regex — mirrors cross-repo-memo's _TOPIC_SLUG_RE.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*$")

# Slice ID regex — allows uppercase because slice IDs like "Z", "A", "B1" are common in wave-maps.
_SLICE_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9\-]*$")


def _slug_from_scope(scope: str) -> str:
    """Derive a filesystem-safe slug from a comma-separated scope string (e.g. paths).

    Lowercases the input, replaces non-alphanumeric characters (path separators,
    dots, commas, spaces) with dashes, collapses consecutive dashes, and truncates
    to 40 characters to keep filenames manageable.

    Examples:
      "tests/x.py"            -> "tests-x-py"
      "bin/foo.sh,lib/bar.py" -> "bin-foo-sh-lib-bar-py"
    """
    slug = scope.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    # review F7 — all-non-alphanumeric input (e.g. "---") produces "" after strip;
    # fall back to a placeholder so the output path is never malformed with a trailing dash.
    return slug[:40] or "unknown-scope"


# Session-id segment whitelist — mirrors coordinator_core.subagent_sandbox.provision_report
# ._sanitize_segment's character set exactly ([A-Za-z0-9._-], reject '', '.', '..' after
# whitelisting) so a self-scaffolded review-findings sidecar's session directory leaf gets
# the identical sanitization discipline as the engine's spawn-time provisioning. Duplicated
# rather than imported: this CLI is invoked from an arbitrary consumer repo's cwd (the
# reviewer's own confined Bash call), and must keep working even when claude-klabauter's own
# package tree is not importable from there — see _resolve_session_id's docstring.
_SESSION_SEGMENT_WHITELIST_RE = re.compile(r"[^A-Za-z0-9._-]")
_REJECTED_SESSION_SEGMENTS = {"", ".", ".."}


def _resolve_session_id() -> str:
    """Resolve the current harness session id for session-scoped self-scaffolds
    (currently: --type review-findings's fallback path, when no sidecar arrived
    pre-provisioned).

    Same env var + precedence chain this file already uses for --type run-report
    and --type subagent-sidecar's `dispatched_by` field (COORDINATOR_SESSION_ID >
    CLAUDE_SESSION_ID > CLAUDE_CODE_SESSION_ID) -- and the same overall harness
    session identity coordinator_core.subagent_sandbox.provision_report reads via
    its spawn-time hook payload's `session_id` field (see that module's
    _provision()). The EM and every subagent it spawns via the Task tool share
    ONE harness session; provision_report captures that identity from the
    EM-side spawn hook's payload, while this self-scaffold path reads it directly
    from the running process's own environment -- same identity, two different
    capture points, not two mechanisms. Falls back to the literal 'em-unknown'
    when unset, matching this file's existing dispatched_by fallback.
    """
    return (
        os.environ.get("COORDINATOR_SESSION_ID")
        or os.environ.get("CLAUDE_SESSION_ID")
        or os.environ.get("CLAUDE_CODE_SESSION_ID")
        or "em-unknown"
    )


def _sanitize_session_segment(seg: str) -> str:
    """Reduce ``seg`` to a single safe path segment for the subagent-share
    session directory leaf, or 'em-unknown' if sanitizing empties it out.

    Whitelists [A-Za-z0-9._-] (dropping '/', '\\', and everything else that
    could smuggle a directory separator), then rejects the degenerate
    '.'/'..'/empty results the whitelist alone would let through -- mirrors
    provision_report._sanitize_segment's contract (see module comment above),
    except this fails CLOSED to a safe placeholder rather than None, since the
    scaffolder has no eligibility gate to fail open through: --type
    review-findings always needs a directory to write into.
    """
    sanitized = _SESSION_SEGMENT_WHITELIST_RE.sub("", seg)
    if sanitized in _REJECTED_SESSION_SEGMENTS:
        return "em-unknown"
    return sanitized


# Precedence chain _resolve_session_id() reads, named here so the missing---out
# refusal below can quote the exact variables a caller with no session identity
# would have to look at. Kept adjacent to the resolver rather than inlined into
# the message so the two can never drift apart.
_SESSION_ID_ENV_VARS = ("COORDINATOR_SESSION_ID", "CLAUDE_SESSION_ID", "CLAUDE_CODE_SESSION_ID")


def _missing_out_message(type_label: str) -> str:
    """Compose the ``--out``-is-required refusal shared by the two session-scoped
    sidecar types (--type run-report and --type subagent-sidecar).

    Neither type gains a derived default here, and this function does not add
    one: the live path is computed by ``coordinator_core.dispatch.provision`` at
    spawn time, and a scaffold that guessed a session-scoped path would write a
    sidecar into a directory nothing reaps (the DEC-3 rationale pinned at both
    call sites and in ``_default_path``). What differs is the *remediation named
    to the reader*, per docs/wiki/guard-messaging.md § Key Patterns — "only offer
    remediation the current reader can actually run":

      - a dispatched agent carrying a harness session id can construct the path
        itself, so the message resolves the session-scoped root for it rather
        than restating the formula;
      - a caller with no session identity resolvable at all has no path to
        construct and no flag value to invent, so the message names the missing
        identity instead of the missing flag.

    Session id comes from ``_resolve_session_id()``/``_sanitize_session_segment()``
    -- the same resolver and precedence chain --type review-findings's fallback
    path uses; that resolver's 'em-unknown' unset sentinel selects the second arm.

    Spec backlink: state/improvement-queue/2026-08-21-a-dispatched-executor-
    cannot-scaffold-it-7c2ccafdf81a.yaml
    Negative-spec: returns message text only -- never exits, never writes, and
    never derives an --out value for the caller.
    """
    session_id = _sanitize_session_segment(_resolve_session_id())
    head = (
        f"error: --out <path> is required for --type {type_label}. "
        "There is no default output path -- the live sidecar path is computed by "
        "coordinator_core.dispatch.provision at spawn time and travels in the dispatch brief."
    )
    if session_id == "em-unknown":
        return (
            f"{head} No session id is set here ("
            + ", ".join(_SESSION_ID_ENV_VARS)
            + "), so no session-scoped path is derivable from this process. "
            "Take the sidecar path from the dispatch brief."
        )
    return (
        f"{head} Absent one, write under state/subagent-share/{session_id}/ "
        "and pass that path as --out."
    )


# ---------------------------------------------------------------------------
# from_repo resolution — mirrors coordinator-queue-append._resolve_from_repo
#
# Resolution order:
#   1. cwd git-root → reverse-lookup against machine-local repos.* table
#   2. DoE-claude repo (repos.doe_claude) path-match → "claude-central-em"
#   3. Unregistered git repo → basename of git root + "-em"
#   4. Not in a git repo → "unknown-sender-em"
#
# Negative-spec: ~/.claude is no longer a memo-identity anchor; central identity
# flows through repos.doe_claude only (C2b central-identity-flip).
# ---------------------------------------------------------------------------

# _REPO_KEY_ALIASES is imported above from coordinator_registry (REPO_ALIASES alias).
# See schemas/coordinator-registry.manifest.json § identity.repoAliases for the canonical mapping.


def _claude_home() -> str:
    """Return the ~/.claude root, honouring CLAUDE_HOME env var for test isolation.

    Delegates to machine_local_impl_resolve.claude_home() (shared resolver).
    """
    return _mlir_claude_home()


def _machine_local_impl() -> str:
    """Return the path to _machine_local.py, honouring MACHINE_LOCAL_IMPL for tests.

    NOTE: MACHINE_LOCAL_IMPL must point to a Python script (.py). This function
    always invokes it via sys.executable (never as a raw executable), so the stub
    convention cross-repo-memo uses (run-as-executable if path doesn't end in .py)
    does not apply here. Tests that override MACHINE_LOCAL_IMPL must provide a .py file.
    # Review: code-reviewer S3-F5 — documents that sys.executable is always prepended;
    # mirrors the constraint instead of silently differing from cross-repo-memo's ext check.

    Security: MACHINE_LOCAL_IMPL is validated before use — must be an absolute path to
    an existing .py file. An unvalidated env var reaching subprocess.run as an arg is an
    arbitrary-code-execution vector if a caller can control the env. Invalid values fall
    back to the default impl with a stderr warning rather than executing the supplied path.

    Settings-home first (DR-210 Amendment 2026-07-24: "resolves nothing
    through ~/.claude/bin") once past the (unchanged) MACHINE_LOCAL_IMPL
    validation above — falls back to the retired compat mirror only when the
    settings-home candidate is absent on disk.
    """
    override = os.environ.get("MACHINE_LOCAL_IMPL")
    if override:
        if os.path.isabs(override) and override.endswith(".py") and os.path.isfile(override):
            return override
        print(
            f"warning: MACHINE_LOCAL_IMPL='{override}' is not a valid path "
            "(must be an absolute path to an existing .py file); "
            "falling back to default _machine_local.py.",
            file=sys.stderr,
        )
    settings_home_impl = os.path.join(_mlir_settings_home(), "bin", "_machine_local.py")
    if os.path.exists(settings_home_impl):
        return settings_home_impl
    return os.path.join(_claude_home(), "bin", "_machine_local.py")


def _machine_local_get(key: str) -> str | None:
    """Call machine-local get <key> and return the value, or None on failure."""
    impl = _machine_local_impl()
    try:
        result = subprocess.run(
            [sys.executable, impl, "get", key],
            capture_output=True, text=True,
        )
    except OSError:
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()


def _machine_local_dump_repos() -> dict[str, str]:
    """Resolve every repos.* key in one machine-local process (the batch
    counterpart to enumerate-then-get). `dump --prefix repos` shares
    resolve_one with `get`, so a batched value is byte-identical to what a
    per-key `get` would print — see _machine_local.py::cmd_dump docstring.
    Returns {} on any spawn/parse failure OR a non-zero returncode (matches
    _machine_local_get's fail-closed contract — a non-zero exit with
    parseable stdout is a partial/crashed dump, not a value to trust);
    callers already tolerate an empty/partial paths table.
    """
    impl = _machine_local_impl()
    try:
        result = subprocess.run(
            [sys.executable, impl, "dump", "--prefix", "repos", "--format", "json"],
            capture_output=True, text=True,
        )
    except OSError:
        return {}
    if result.returncode != 0 or not result.stdout.strip():
        return {}
    try:
        data = json.loads(result.stdout)
    except ValueError:
        return {}
    return {k: v for k, v in data.items() if isinstance(v, str) and v}


def _machine_local_repos_keys() -> list[str]:
    """Return all repos.* keys from the machine-local registry."""
    impl = _machine_local_impl()
    try:
        result = subprocess.run(
            [sys.executable, impl, "keys"],
            capture_output=True, text=True,
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    return [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip().startswith("repos.")
    ]


# _same_path deleted (C2b) — not needed in this CLI. _em_id_for_root imported from coordinator_registry above.
# Review: code-reviewer — F2: removed stale _repo_key_to_em_id reference; import was unused


def _current_repo_root() -> str | None:
    """Return the git repo root of the cwd, or None if not inside a git repo."""
    _ensure_engine_on_path()
    from coordinator_core.git.repo_root import show_toplevel

    return show_toplevel()


def _stamp_completion_scaffold_liveness(repo_root: str | None) -> None:
    """Best-effort stamp the shared `completion_scaffold` housekeeping-liveness key.

    Called from the success path only (immediately after a genuinely NEW completion
    entry has been written to disk — never on a write failure, and never for any
    other `--type`). Mirrors `sweep-terminal-plans.py::_import_housekeeping_seam` /
    `_stamp_archive_sweeps_liveness` verbatim: this trampoline's own `__file__` lives
    inside the claude-klabauter checkout, but `repo_root` here is the CALLER's repo (may be a
    sibling repo), so the seam is imported via the resolved engine root rather than a
    relative import. Never raises -- a liveness-stamp failure must not surface as a
    scaffold failure.

    Spec backlink: pln-wsc-tail-slim-down-op-scoped-c-e9a265 § C17b (four missing
    stamp_liveness call sites -- completion_scaffold leg).
    """
    if not repo_root:
        return
    try:
        _ensure_engine_on_path()
        from coordinator_core.ops.ceremony.housekeeping_liveness import (
            COMPLETION_SCAFFOLD,
            stamp_liveness,
        )

        stamp_liveness(repo_root, COMPLETION_SCAFFOLD)
    except Exception:  # noqa: BLE001 -- best-effort; never let seam-import/stamp failure mask the real scaffold outcome
        pass


def _assert_no_archived_handoff_twin(out_path: str, handoff_id: str | None, repo_root: str | None) -> None:
    """Fail loud (sys.exit 1) if ``out_path`` (about to be created) shares a
    filename or ``handoff_id`` with an already-archived ``archive/handoffs/`` record.

    Scoped by CALL SITE, not by ``doc_type``: only invoked from the one write
    site (just before ``open(out_path, "w")``) and only when the resolved
    output path's parent directory is literally named ``handoffs`` — this
    covers every handoff-schema-family ``--type`` (handoff, recovery, spinoff,
    goal-seed, roadmap-baton, roadmap-seed) AND an explicit
    ``--out state/handoffs/...`` override for any doc_type, since the
    invariant is about the DESTINATION directory, not the type label.

    Degrades gracefully (skips the check, no exit) when ``repo_root`` cannot
    be resolved (no git repo, the engine root unconfigured) or when
    ``coordinator_core`` cannot be imported — matches this file's existing
    graceful-skip convention for un-migrated installs (see
    ``_resolve_state_root``'s docstring) rather than hard-failing every
    scaffold on an environment this tool already tolerates elsewhere.

    Spec backlink: docs/audits/2026-07-26-handoff-live-archive-duplication-origin.md
    (DoE-claude); coordinator_core.handoff_creation_guard (claude-klabauter) — the
    shared guard this call delegates to, also enforced at the two engine-side
    handoff-creation ops (handoff.author_fork, handoff.scaffold_from_queue).
    """
    if not repo_root:
        return
    if os.path.basename(os.path.dirname(out_path)) != "handoffs":
        return
    try:
        _ensure_engine_on_path()
        from coordinator_core.handoff_creation_guard import (
            HandoffArchivedTwinError,
            assert_no_archived_twin,
        )
    except Exception:  # noqa: BLE001 -- best-effort import; unresolvable seam degrades to no-check
        return
    try:
        assert_no_archived_twin(out_path, repo_root, handoff_id=handoff_id)
    except HandoffArchivedTwinError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


# Handoff-family kinds that owe a `## Session Ledger` block (C1: all six scaffolders
# now emit it, C3 makes its absence a write-time refusal). PM ruling 2026-08-11
# (docs/plans/2026-08-11-ledger-owing-handoff-kinds-emit-the-sess.md § Problem):
# all handoff-family kinds are ledger-owing, including goal-seed.
_LEDGER_OWING_KINDS: frozenset[str] = frozenset({
    "session-handoff",
    "recovery",
    "spinoff",
    "roadmap-baton",
    "roadmap-seed",
    "goal-seed",
})


def _assert_scaffold_content_valid(content: str, out_path: str, repo_root: str | None) -> None:
    """Fail loud (sys.exit 1) if the freshly-generated ``content`` fails the
    schema its own kind/path resolves to in this repo's vendored corpus
    (``coordinator_core/frontmatter/schemas/``), so the emitter cannot mint a
    record its own repo's validator would reject. Also refuses (sys.exit 1)
    a ledger-owing kind (``_LEDGER_OWING_KINDS``) whose body carries no
    ``## Session Ledger`` heading (C3) — the write-time backstop for "every
    present and future baton generator remembering to do so" that C1's
    generator-side emission alone cannot guarantee.

    Scoped to doc types whose kind or output path resolves to a schema in
    that corpus (``match_schema``/``match_schema_for_path``) — most doc
    types this CLI scaffolds (memo, plan, decision, completion, goal,
    review sidecars, etc.) have no schema in claude-klabauter's own ~14-schema corpus
    and resolve to no match, so this check is a no-op for them rather than
    a weakened warning: only doc types WITH a schema are actually enforced.
    Content with no parseable frontmatter is likewise left alone here (this
    is a self-check on the emitter's own output shape, not a general
    frontmatter-presence gate). The ledger-heading check is scoped the same
    way — it only ever runs on content whose frontmatter parsed and whose
    schema matched, so an unresolvable/malformed scaffold degrades exactly
    like the schema check does, never a separate failure mode.

    Degrades gracefully (skips the check, no exit) when ``repo_root`` cannot
    be resolved or when ``coordinator_core`` cannot be imported — mirrors
    ``_assert_no_archived_handoff_twin``'s existing graceful-skip convention
    for un-migrated installs, rather than hard-failing every scaffold on an
    environment this tool already tolerates elsewhere. A schema-corpus load
    or frontmatter-parse failure degrades the same way (fail-open — never
    block a write on the self-check's own infra trouble); only an actual
    schema-shape violation, or a ledger-owing kind missing its heading, on
    the generated content triggers the hard exit.

    Spec backlink: cross-repo memo
    2026-08-01-doe-claude-em-roadmap-baton-write-guard-warns-where-claim-gate-denies.md
    § "Also worth noting regardless of the above".
    Spec backlink (C3): pln-ledger-owing-handoff-kinds-emi-648818 § C3
    """
    if not repo_root:
        return
    try:
        _ensure_engine_on_path()
        from coordinator_core.session_ledger import SESSION_LEDGER_HEADING_RE
        from coordinator_core.frontmatter.schema_validate import (
            _SCHEMAS_DIR,
            _lint_is_sidecar_file,
            load_schemas,
            match_schema,
            parse_frontmatter,
            validate_frontmatter_obj,
        )
    except Exception:  # noqa: BLE001 -- best-effort import; unresolvable seam degrades to no-check
        return

    try:
        repo_rel = os.path.relpath(
            os.path.realpath(out_path), os.path.realpath(repo_root)
        ).replace(os.sep, "/")
        # match_schema has no sidecar concept: a sidecar written under
        # docs/plans/ (prior-art-check, plan-coverage-check, docs-check,
        # review) falls through its glob fallback to docs/plans/*.md and
        # resolves to the `plan` schema, so it would always fail plan-shape
        # validation. The lint layer's own sidecar exemption
        # (_lint_is_sidecar_file) is the canonical recognizer for this same
        # gap; reuse it here rather than re-deriving a second sidecar-suffix
        # predicate that could drift from it.
        if _lint_is_sidecar_file(repo_rel):
            return
        parsed = parse_frontmatter(content)
        frontmatter = parsed.get("frontmatter")
        body = parsed.get("body") or ""
        schemas = load_schemas(_SCHEMAS_DIR)
        match = match_schema(repo_rel, frontmatter, schemas)
    except Exception:  # noqa: BLE001 -- fail-open on corpus-load/parse trouble, never block on infra
        return

    if not match or frontmatter is None:
        return

    result = validate_frontmatter_obj(frontmatter, match["schema"])
    if not result.get("ok"):
        schema_name = match.get("schemaName", "(unknown schema)")
        lines = [
            f"error: refusing to write {out_path} — generated frontmatter fails "
            f"its own schema ({schema_name}). The emitter refused to write:",
        ]
        for e in result.get("errors") or []:
            field = e.get("field") or "(unknown)"
            hint = f" (hint: {e['hint']})" if e.get("hint") else ""
            lines.append(f"  {field}: {e.get('error')}{hint}")
        print("\n".join(lines), file=sys.stderr)
        sys.exit(1)

    kind = frontmatter.get("kind") if isinstance(frontmatter, dict) else None
    if kind in _LEDGER_OWING_KINDS:
        # Review: code-reviewer 49e8b242 P2/P3 — was _compile_heading_re("Session Ledger")
        # over the full frontmatter+body `content` (near-missed the parser's grammar,
        # and a frontmatter field literal-matching the heading text could spuriously
        # satisfy it); now the canonical parser-shared regex, scoped to `body` only.
        if not SESSION_LEDGER_HEADING_RE.search(body):
            print(
                f"error: refusing to write {out_path} — kind: {kind} is ledger-owing "
                "and its body carries no '## Session Ledger' heading. "
                "session_ledger.aggregate_chain_loe sums that block's rows to compute "
                "chain effort; a ledger-owing handoff with no block silently renders any "
                "chain headed by it as zero effort. The emitter refused to write.",
                file=sys.stderr,
            )
            sys.exit(1)


def _resolve_state_root(central: bool = False) -> str | None:
    """Resolve the coordinator state root via the coordinator_state_root seam.

    Invokes coordinator-state-root.py (a Python CLI trampoline over claude-klabauter's
    native coordinator_core.state_root — de-bash campaign,
    docs/plans/2026-07-16-bash-clean-slate-residual-migration.md) from the
    sibling lib/ directory (relative to this script's bin/ location) as a
    subprocess and captures its stdout. Returns None on any failure
    (the engine root not configured, git unavailable, lib absent).

    Placement law spec backlink:
        docs/plans/2026-07-03-stop-the-rot-claude-klabauter-state-home-placement.md § C10 / AC7

    Taxonomy:
        central=True  → coordinator_state_root --central → claude-klabauter/state (always)
        central=False → coordinator_state_root            → claude-klabauter/state when meta-repo,
                                                            $GIT_ROOT/state for siblings

    Negative-spec: does NOT fall back silently — returns None on any failure so callers
    can degrade gracefully (fallback to repo-root anchoring on un-migrated installs).
    Negative-spec: does NOT call coordinator_state_root with both flags at once.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # This script lives in bin/; the lib is at bin/../lib/ = coordinator/lib/.
    lib_dir = os.path.join(script_dir, "..", "lib")
    state_root_py = os.path.realpath(os.path.join(lib_dir, "coordinator-state-root.py"))
    if not os.path.isfile(state_root_py):
        return None
    cmd = [sys.executable, state_root_py]
    if central:
        cmd.append("--central")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            **_no_console_creationflags(),
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except OSError:
        pass
    return None


def _mint_deliverable_id(
    deliverable_id: str | None = None,
    stub_id: str | None = None,
    slug: str | None = None,
    carry_source: str | None = None,
) -> str | None:
    """Carry or mint a deliverable_id via bin/mint-deliverable-id.py.

    Three paths (matching the mint helper — C3a):
      carry      — deliverable_id supplied → return unchanged (never re-mint)
      stub       — stub_id supplied → python3 mint-deliverable-id.py --stub-id <stub_id>
      slug       — slug supplied   → python3 mint-deliverable-id.py --slug <slug>

    Logs which path was taken to stderr — the stub/slug paths via the mint
    helper's own stderr output; the carry path via its own stderr echo here
    (AC2, C1 — this branch used to return silently with no shell-out and no
    log line; DR-207 D1 requires the carry-vs-mint path be logged on EVERY
    invocation, not only the new session-state tier's). ``carry_source`` names
    which rung supplied the carried id for the log line (e.g. "explicit
    --deliverable-id", "DELIVERABLE_ID env", "session-state parent
    (roadmap stub)"); defaults to the generic "carry" label when a
    caller doesn't pass one.
    Returns None on any failure (graceful — callers emit 'null' in that case).

    Spec backlink: pln-fleet-deliverable-spine-identity-and-facets-2b331c § D1, C3b
    Spec backlink (AC2 carry-path logging): pln-deliverable-id-fork-remediatio-894e26 § C1
    Negative-spec: does NOT re-mint when deliverable_id is supplied — carry path only.
    Negative-spec: does NOT write to disk — pure identity computation.
    """
    if deliverable_id:
        # carry — return directly; no shell-out needed (no hash computation)
        # Intentionally logs alongside deliverable_carry.py's own carry-path
        # print (handoff-deliverable-carry:) on the handoff arm's cascade —
        # two independently-owned layers (this CLI-local mint helper, and
        # the shared deliverable_carry cascade) each naming their own
        # decision. Do not collapse to one call; each layer must remain
        # able to log its own resolution in isolation.
        print(
            f"coordinator-doc-new: {carry_source or 'carry'} path — "
            f"using existing id: {deliverable_id}",
            file=sys.stderr,
        )
        return deliverable_id
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mint_script = os.path.join(script_dir, "mint-deliverable-id.py")
    if not os.path.isfile(mint_script):
        return None
    if stub_id:
        cmd_args = ["--stub-id", stub_id]
    elif slug:
        cmd_args = ["--slug", slug]
    else:
        return None
    try:
        result = subprocess.run(
            [sys.executable, mint_script] + cmd_args,
            capture_output=True,
            text=True,
            **_no_console_creationflags(),
        )
        if result.returncode == 0 and result.stdout.strip():
            # Echo the mint helper's stderr so callers see carry-vs-mint log
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)
            return result.stdout.strip()
    except OSError:
        pass
    return None


def _resolve_session_held_spinoff_roadmap_stub_path(repo_root: str | None) -> str | None:
    """Resolve the path of a `handoff`-class artifact the RUNNING SESSION holds a
    claim on, for the C1/AC1 session-state parent tier.

    Reads SESSION STATE only (`coordinator_core.session.claims` /
    `coordinator_core.session.core`) — never the file being scaffolded (that file
    has no session-state claim on itself yet, and its own `predecessor_handoff`
    field is emitted commented out; see
    `coordinator_core.ops.deliverable_carry.resolve_session_state_parent_
    deliverable_id`'s docstring for why a scaffold-time read of that field is
    always empty).

    Scans only `handoff-claims` (the class roadmap stubs — `kind: roadmap-
    baton`, or the retired `kind: spinoff-roadmap` still found on archived
    stubs — are claimed under; memo/plan claims cannot carry such a stub) and
    resolves each claimed basename against `state/handoffs/<basename>` first,
    falling back to `archive/handoffs/**/<basename>` (a handoff claim survives
    both ship and archive) — the FIRST resolvable file wins, where "first" is
    ALPHABETICAL by basename (this caller uses the unchecked
    `list_claims_by_session` wrapper, which iterates claims in the same
    `sorted(class_dir.iterdir())` order as `list_claims_by_session_checked` —
    see that function's docstring for the underlying read semantics — but
    discards its `errors` arm; an unresolvable session-state store is treated
    identically to "holds nothing", which is the intended degrade-to-empty
    behaviour for this advisory resolution, not a bug). Ordering is NOT
    chronological, so under multiple concurrent roadmap stubs in one
    session the earliest-alphabetical basename wins regardless of claim
    recency (mirrors this file's existing graceful, no-detector-for-concurrent-
    stubs posture; see the plan's Critical-1 review note for the known
    residual gap).

    The actual `kind` gate (which values count as a roadmap stub) lives in
    `coordinator_core.ops.deliverable_carry._ROADMAP_STUB_KINDS`, applied by
    `resolve_session_state_parent_deliverable_id` — this function only
    resolves a candidate PATH from session state; it does not itself inspect
    `kind`.

    Degrades to `None` (never raises) when `coordinator_core` cannot be
    imported, no repo root is resolvable, no session id resolves, the session
    holds no handoff-class claim, or no claimed basename resolves to a real
    file — every one of those falls through to mint-from-slug exactly as
    before this tier existed (AC3).
    """
    if not repo_root:
        return None
    try:
        _ensure_engine_on_path()
        from coordinator_core.session import claims as _claims
        from coordinator_core.session import core as _session_core
    except Exception:  # noqa: BLE001 -- best-effort import; unresolvable seam degrades to no-carry
        return None

    try:
        sid = _session_core.resolve_session_id(repo_root)
    except Exception:  # noqa: BLE001 -- session-state resolution is advisory here; degrade to no-carry
        return None
    if not sid:
        return None

    try:
        held_claims = _claims.list_claims_by_session(sid, repo_root)
    except Exception:  # noqa: BLE001 -- degrade to no-carry on any session-state read failure
        return None

    for class_, basename in held_claims:
        if class_ != "handoff-claims":
            continue
        live_path = os.path.join(repo_root, "state", "handoffs", basename)
        if os.path.isfile(live_path):
            return live_path
        try:
            for dirpath, _dirnames, filenames in os.walk(
                os.path.join(repo_root, "archive", "handoffs")
            ):
                if basename in filenames:
                    return os.path.join(dirpath, basename)
        except OSError:
            continue
    return None


def _mint_artifact_id(prefix: str, slug: str) -> str:
    """Mint a stable artifact id: <prefix>-<slug>-<6hex>.

    Reconciled (2026-07-08, lvv-01/C1) onto the ONE canonical uniqueness basis
    shared across every mint site in this codebase — the shell/JS basis:
    sha1(slug|epoch-SECONDS|pid|random)[:6]. Before this reconciliation,
    two DIFFERENT bases had already diverged on disk: this function's predecessor
    (_mint_plan_id) used epoch-MICROSECONDS with NO random component, while
    bin/mint-deliverable-id.py (the cross-language seam also mirrored in
    bin/normalize-handoff-frontmatter.js's mintDeliverableIdFromSlug) used
    epoch-seconds + pid + $RANDOM. The shell/JS basis is canonical because it is
    the one with real cross-language callers (mint-deliverable-id.py is invoked
    from skills/handoff, skills/spinoff, skills/roadmap-planning, and mirrored
    independently in JS) — this function now matches that formula instead of
    adding a third divergent variant. Slug truncated to 30 chars so the id stays
    manageable; inputs are commonly pre-truncated to 40 chars by callers
    (see _slug_from_title) already, so this 30-char clamp is a defensive
    re-clamp, not the primary truncation point.

    Parity note (review finding, lvv-01/A F1/F5): this reconciliation matches
    the shell/JS basis on hash-input SHAPE (slug|epoch-seconds|pid|random),
    NOT on the exact random-number range. Python (random.randint(0, 65535))
    and the JS mirror (Math.floor(Math.random() * 65536)) both draw from a
    16-bit range; bash's $RANDOM is a 15-bit PRNG yielding [0, 32767]. Python
    and JS agree with each other but neither matches bash's exact entropy
    range — the "same formula" claim holds on shape, not on this one axis.
    Not a correctness issue (collision odds remain comfortably low either
    way); flagging so a future reader doesn't assume bit-for-bit parity.

    Provenance note (review finding, corpus-sweep F2): a hand-cured or swept
    id's 6-hex suffix (e.g. an archived record whose handoff_id was rewritten
    to fix a stale/placeholder slug while preserving the original hex) is NOT
    reproducible from that record's current slug — the hex above is only ever
    computed from the slug at the moment of a fresh mint. Do not infer
    slug-hex provenance for an id that could have been hand-cured after mint.

    Spec backlink: docs/plans/2026-07-08-lifecycle-vocab-c2-durable-links-rollup.md § C1
    Negative-spec: does NOT shell out to mint-deliverable-id.py — the formula is
    replicated in-process (same pattern normalize-handoff-frontmatter.js already
    uses in JS) so this stays a pure, dependency-free computation like its
    _mint_plan_id predecessor; only the FORMULA changed, not the call shape.
    """
    # Re-strip after truncation (review finding, corpus-sweep F1): if the 30-char
    # clamp lands exactly on a separator, a trailing dash here would produce a
    # double-dash id (<prefix>-<slug>--<hex>) at the hex boundary — schema-valid
    # under [a-z0-9-]+ but not what a slug/hex reader would expect. Mirrors the
    # equivalent re-strip added to _slug_from_title for the same boundary.
    slug_part = slug[:30].strip("-")
    epoch_seconds = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    rand_component = random.randint(0, 65535)
    # hash_input uses the FULL slug (not slug_part) so long, similar titles
    # still diverge — do not "simplify" to slug_part here (review finding F3).
    hash_input = f"{slug}|{epoch_seconds}|{os.getpid()}|{rand_component}"
    six_hex = hashlib.sha1(hash_input.encode()).hexdigest()[:6]
    return f"{prefix}-{slug_part}-{six_hex}"


def _mint_plan_id(slug: str) -> str:
    """Mint a plan_id: pln-<slug>-<6hex>.

    Thin shim over _mint_artifact_id(prefix="pln", slug) — kept so no existing
    caller of _mint_plan_id breaks after the C1 generalization.

    Spec backlink: docs/plans/2026-07-08-lifecycle-vocab-c2-durable-links-rollup.md § C1
    """
    return _mint_artifact_id("pln", slug)


# _em_id_for_root deleted (C2b) — imported from coordinator_registry above (2-arg form: no home param).
# Central identity now anchored on repos.doe_claude path-match, not ~/.claude.


def _resolve_from_repo() -> str:
    """Identify the from_repo for the scaffolded document from cwd context."""
    root = _current_repo_root()
    paths_dict = _machine_local_dump_repos()
    # Ensure repos.doe_claude is present so the central-identity path-match in
    # em_id_for_root fires even when the machine-local keys enumeration omits it.
    paths_dict.setdefault("repos.doe_claude", _machine_local_get("repos.doe_claude"))
    return _em_id_for_root(root, paths_dict)


def _resolve_session_display_name() -> str | None:
    """Resolve THIS session's human-readable harness name (e.g.
    `claude-klabauter-76`), or `None` when it can't be resolved.

    Reads `coordinator_core.session.harness_registry.self_record()` — the O(1)
    single-file read of this process's own registry record, keyed off
    `CLAUDE_PID` — and takes its `name` field directly. That name is the
    harness's own per-session identity (`slug(basename(cwd)) + "-" +
    one-random-byte-hex`, see `coordinator_core.session.reachability`'s module
    docstring), generated independently of whether cross-session messaging is
    bound, so it is present far more often than a `SendMessage`-ready
    `name [ref]` address would be (that bracketed form additionally requires
    `messaging_socket_path`, which is off by default — see
    `harness_registry.self_record`'s own docstring, "44/44 records on this box
    omit the field"). The bracketed ref exists to disambiguate CONCURRENT live
    peers for messaging, not to identify one session for a durable-file stamp;
    the bare name is already session-specific and traces back through
    `ListAgents`/registry history.

    Shared by two callers with two different degrade conventions, so this
    function itself never fabricates a fallback — that decision belongs to
    the caller: `_resolve_plan_author` (a required field — falls back to the
    repo-level `_resolve_from_repo()` identity) and the `authoring_session:`
    UUID's inline-comment annotation on handoff/spinoff (optional — simply
    omits the comment when this returns `None`).
    """
    try:
        _ensure_engine_on_path()
        from coordinator_core.session import harness_registry as _harness_registry
    except Exception:  # noqa: BLE001 -- engine seam absent; degrade to no display name
        return None
    try:
        self_info = _harness_registry.self_record()
    except Exception:  # noqa: BLE001 -- registry read failed; degrade to no display name
        return None
    if self_info is None:
        return None
    _sid, record = self_info
    return record.name or None


def _resolve_plan_author() -> str:
    """Stamp a plan's `author:` with the MINTING SESSION's own resolvable
    name (e.g. `claude-klabauter-76`), not the repo-wide EM role string
    `_resolve_from_repo()` returns.

    Thin wrapper over `_resolve_session_display_name()` with a required-field
    fallback: when that resolver returns `None` (registry seam unavailable,
    `CLAUDE_PID` doesn't resolve, or the record carries no `name`), falls back
    to `_resolve_from_repo()` — today's repo-level EM identity. Honest
    degrade: it never fabricates a session number, it reuses the same
    deterministic-but-coarser identity the field already carried before this
    change.
    """
    return _resolve_session_display_name() or _resolve_from_repo()


# ---------------------------------------------------------------------------
# Branch detection
# ---------------------------------------------------------------------------

def _current_branch() -> str:
    """Detect the current git branch, or return a placeholder on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout.strip() not in ("", "HEAD"):
            return result.stdout.strip()
    except OSError:
        pass
    return "work/MACHINE/YYYY-MM-DD"


# ---------------------------------------------------------------------------
# Slug helper
# ---------------------------------------------------------------------------

def _slug_from_title(title: str) -> str:
    """Sanitize a title into a filesystem-safe slug (≤40 chars)."""
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    slug = slug[:40]
    # Re-strip after truncation (review finding, corpus-sweep F1): a 40-char cut
    # landing exactly on a separator would otherwise leave a trailing dash, which
    # _mint_artifact_id/_mint_deliverable_id would then carry into a double-dash
    # id (...-a--<hex>) at the prefix boundary. Real example: "Execute the
    # Tier-F grant gate — a sibling repo is blocked on chunk one" truncates its
    # _mint_artifact_id slug at char 30 exactly on "...grant-gate-|a...".
    return slug.strip("-")


def _is_placeholder_title(title: str) -> bool:
    """True when `title` is still a scaffold placeholder, not an author-written title.

    Every `--title`-less scaffold defaults `title` to a "PLACEHOLDER — replace with
    …" string (see § Resolve title default). That string then flows into
    _slug_from_title and on into the durable id mints, producing ids like
    `hnd-placeholder-replace-with-one-l-5f04ba` that survive the author fixing the
    title afterwards — the id is minted once, at scaffold time, and nothing re-mints
    it. Callers use this predicate to REFUSE to mint rather than bake a
    placeholder-derived value into a durable, cross-repo identifier.

    Why refusal beats a placeholder id: a placeholder id is *well-formed*. It matches
    gate_eval's `_HANDOFF_ID_PATTERN` (`^hnd-[a-z0-9-]+-[0-9a-f]{6}$`), so a
    `blocked_by` pointing at one RESOLVES and silently clears instead of dangling —
    every polluted record is a live false-clear edge. An absent id dangles honestly
    and is trivially sweepable; a wrong one is indistinguishable from a right one.

    Spec backlink: cross-repo/inbox/2026-08-05-doe-claude-em-placeholder-id-minting-fix-unfiled.md
    Sizing: state/sizings/2026-08-05-placeholder-title-guard-at-artifact-id-m.yaml

    Negative-spec: matches on the scaffold's own sentinel prefix, NOT on the word
    "placeholder" appearing anywhere in a title — a legitimate handoff titled
    "Placeholder ids leak into blocked_by" must mint normally. The check is
    anchored at the start and case-sensitive for exactly that reason.
    Negative-spec: does NOT guard _slug_from_title itself. That helper also derives
    FILENAMES, and scaffolding an untitled doc is a supported workflow — a refusal
    there would break it. The guard belongs at the mint sites, which are the only
    places a placeholder becomes durable.
    """
    return title.startswith("PLACEHOLDER")


def _warn_placeholder_id_skipped(field: str, doc_type: str) -> None:
    """Tell the author why a durable id field is absent, and how to get one."""
    print(
        f"note: {field} not minted — the title is still the scaffold placeholder, and "
        f"an id minted from it would be durable, wrong, and indistinguishable from a "
        f"real one. Re-run with --title \"<the real title>\" to mint {field} for this "
        f"{doc_type}, or fill it in when the title lands.",
        file=sys.stderr,
    )


# Set once from `--new-chain` in main(); read by _resolve_session_chain_deliverable_id.
# A module-level switch rather than a parameter because the mint-from-title fallback is
# reached from five call sites across three arms, none of which otherwise carry an
# authoring-intent flag — threading one through all of them would widen five signatures
# to express a single process-wide fact the CLI resolves once, at parse time.
_NEW_CHAIN_REQUESTED = False


def _resolve_session_held_handoff_path(repo_root: str | None) -> str | None:
    """Absolute path of the handoff THIS session holds a claim on, or None.

    Reuses `baton_assemble._resolve_held_handoff_for_session` — the ONE
    resolver from the durable claim ledger to a baton path (see its own
    docstring's "this is the ONE place" contract) — rather than re-deriving
    the claim-store lookup here. That resolver returns the LIVE-directory
    string even for a handoff since swept to `archive/handoffs/`, so the
    swept case is handed to `resolve_swept_baton._find_first_match`, the
    same shared archive walk `_resolve_qualified_path_or_raise` and
    `/pickup` use — never a second hand-rolled archive-dir list here.

    Returns None — never raises — on every ambiguity or absence: no claim,
    a `degraded` set (the resolver could not distinguish two held claims, so
    no single chain is named and guessing one would be the very silent
    mis-join this tier exists to prevent), the resolver's own loud
    `ValueError`, or a repo root that will not resolve.
    """
    if not repo_root:
        return None
    try:
        _ensure_engine_on_path()
        from pathlib import Path as _Path  # noqa: PLC0415

        # Cheap pre-gate before the expensive import: `coordinator_core.
        # baton_assemble` costs ~95ms to import, `coordinator_core.session`
        # ~47ms, and the overwhelmingly common case is a session holding no
        # handoff claim at all. Ask the ledger the yes/no question with the
        # cheaper module first and pay for the resolver only on a hit —
        # the resolver imports this same module anyway, so the hit path
        # pays nothing extra for the gate.
        from coordinator_core.session import claims as _claims  # noqa: PLC0415
        from coordinator_core.session import core as _session_core  # noqa: PLC0415

        _sid = _session_core.resolve_session_id(repo_root)
        if not _sid:
            return None
        if not any(
            _class == "handoff-claims"
            for _class, _basename in _claims.list_claims_by_session(_sid, repo_root)
        ):
            return None

        from coordinator_core.baton_assemble import (  # noqa: PLC0415
            _resolve_held_handoff_for_session,
        )

        with contextlib.redirect_stderr(io.StringIO()):
            _primary, _additional, _degraded = _resolve_held_handoff_for_session(
                _Path(repo_root), allow_standalone=True
            )
    except Exception:  # noqa: BLE001 -- discovery is best-effort; never blocks scaffolding
        return None
    if not _primary or _degraded:
        return None
    _live = os.path.join(repo_root, _primary.replace("/", os.sep))
    if os.path.isfile(_live):
        return _live
    try:
        from coordinator_core.ops.resolve_swept_baton import (  # noqa: PLC0415
            _find_first_match,
        )

        _swept = _find_first_match(_Path(repo_root), os.path.basename(_primary))
    except Exception:  # noqa: BLE001 -- discovery is best-effort; never blocks scaffolding
        return None
    return str(_swept) if _swept else None


def _resolve_session_chain_deliverable_id(
    doc_type: str, repo_root: str | None
) -> str | None:
    """Session-chain discovery — the id of the chain this session is already
    authoring into, or None.

    The gap this closes: every other rung answers "was an id HANDED to me"
    (flag, env, cited sizing, explicit predecessor edge). None asks whether
    the chain already HAS one, so two artifacts of one deliverable authored
    under two titles with no id passed mint two different ids off two title
    slugs — silently, each scaffolder doing the locally-normal thing — and
    the split only surfaces at a deliverable-level rollup, by which time it
    is in shared history and unrepairable in place (2026-08-25 bug record
    `deliverable-id-minted-from-title-not-discovered`, two independent
    chains).

    Three doc types are exempt by ruling, not by convenience:
      spinoff — a `kind: spinoff` baton mints its own id (PM, 2026-08-05;
                `baton_assemble.resolve_lineage` owns that branch).
      roadmap-baton — its identity is its `stub_id`, not a discovered chain
                (D1); the stub path above already mints from it.
      plan — plan authoring ALREADY asks this question, one tier earlier and
                with a stricter answer. `deliverable_carry.resolve_session_
                state_parent_deliverable_id` reads the very same session-held
                artifact and REJECTS it unless its `kind` is a roadmap stub,
                because holding a claim is not evidence a plan descends from
                it (pln-deliverable-id-fork-remediatio-894e26 § C2 AC4b: a
                false merge joins two unrelated works under one id and, unlike
                a fork, nothing can ever detect it — nothing diverges). Left
                unexempt, this tier reads that same rejected file and carries
                its id anyway, silently reversing the decision the tier before
                it just logged as "falling through to mint-from-slug". Two
                tiers must not answer the same question about the same file
                two ways; for `plan` the kind-gated one is authoritative.
    `--new-chain` is the author's own exemption for the remaining types:
    deliberately rooting a NEW deliverable while a claim on another chain is
    still held.

    Never raises: every failure mode degrades to None and mint-from-title,
    exactly the behaviour that stood before this tier existed.
    """
    if _NEW_CHAIN_REQUESTED or doc_type in {"spinoff", "roadmap-baton", "plan"}:
        return None
    _chain_path = _resolve_session_held_handoff_path(repo_root)
    if not _chain_path:
        return None
    try:
        _ensure_engine_on_path()
        from coordinator_core.ops.deliverable_carry import (  # noqa: PLC0415
            resolve_session_chain_deliverable_id,
        )
        from coordinator_core.ops.read_frontmatter_field import (  # noqa: PLC0415
            read_frontmatter_field as _read_frontmatter_field,
        )

        return resolve_session_chain_deliverable_id(
            _read_frontmatter_field, _chain_path
        )
    except Exception:  # noqa: BLE001 -- discovery is best-effort; never blocks scaffolding
        return None


def _mint_deliverable_id_from_title(
    title: str, doc_type: str, repo_root: str | None = None
) -> str | None:
    """Discover the session's chain id, else mint from the title, refusing on
    a placeholder title.

    Wraps the slug-basis _mint_deliverable_id call so the placeholder guard lives in
    ONE place rather than being re-inlined at each of its four call sites. Carry-path
    and stub_id-path mints are deliberately NOT routed through here — those derive
    from a caller-supplied id or a real stub_id, never from the title, so the
    placeholder failure mode cannot reach them.

    Discovery runs AHEAD of the placeholder refusal on purpose: a discovered id is
    not title-derived, so a placeholder title is no reason to withhold it — the
    refusal exists to stop a placeholder becoming durable, and carrying the chain's
    real id does the opposite.

    ``repo_root`` is the discovery scope; omitting it (the default, kept for the
    unit call sites that pass a title alone) disables discovery and preserves the
    pre-2026-08-25 mint-from-title behaviour exactly.

    See _is_placeholder_title for why refusal beats minting a placeholder-derived id.
    """
    _chain_dlv = _resolve_session_chain_deliverable_id(doc_type, repo_root)
    if _chain_dlv:
        return _mint_deliverable_id(
            deliverable_id=_chain_dlv, carry_source="session-chain discovery"
        )
    if _is_placeholder_title(title):
        _warn_placeholder_id_skipped("deliverable_id", doc_type)
        return None
    return _mint_deliverable_id(slug=_slug_from_title(title))


def _resolve_cited_sizing_deliverable_id(
    sizing_object_relpath: str, repo_root: str,
) -> str | None:
    """Read a cited sizing-object's `deliverable_id` for the `plan` arm's
    carry tier, degrading to ``None`` (mint-from-slug) on any read failure.

    Reuses `deliverable_cascade._read_sizing_meta` — the same whole-document
    YAML reader `deliverable_cascade.py` uses for `state/sizings/*.yaml`
    records, since a sizing-object has no `---` frontmatter fence and a
    fenced-frontmatter reader would silently return `{}` on it rather than
    the record's real fields. Never raises: a malformed/unreadable sizing
    must not block plan scaffolding (2026-08-10 deliverable-id-fork-
    remediation follow-up) — it only means this plan cannot carry an id and
    falls back to minting its own, exactly as it did before this fix.

    Spec backlink: sizing-object.schema.json's `deliverable_id` description
    ("minted once at the earliest artifact ... carried verbatim by every
    downstream artifact").
    Negative-spec: does NOT write to disk — pure read.
    """
    try:
        _ensure_engine_on_path()
        from coordinator_core.ops.deliverable_cascade import (  # noqa: PLC0415
            _read_sizing_meta,
        )

        _sizing_abs_path = os.path.join(repo_root, sizing_object_relpath)
        _sizing_meta = _read_sizing_meta(_sizing_abs_path)
        return _sizing_meta.get("deliverable_id") or None
    except Exception as _sizing_read_exc:  # noqa: BLE001 -- malformed/unreadable sizing degrades to mint, never blocks scaffolding
        print(
            "coordinator-doc-new: cited sizing-object at "
            f"{sizing_object_relpath!r} could not be read for a "
            f"deliverable_id carry ({type(_sizing_read_exc).__name__}: "
            f"{_sizing_read_exc}) — degrading to mint-from-slug.",
            file=sys.stderr,
        )
        return None


def _resolve_explicit_predecessor_edge_tier(
    predecessor_relpath: str | None,
    repo_root: str | None,
    doc_type: str,
    title: str,
    *,
    narrow_catch: bool,
) -> str | None:
    """C2 explicit-predecessor-edge tier (AC1/AC3/AC4/AC5/AC9) — folded to
    ONE resolve-mint-warn implementation for both reachable call sites (the
    `plan` arm and the newly-reached-type fallthrough for `spinoff`/
    `roadmap-seed`/`recovery`). Reads `--predecessor`'s referenced
    artifact's `deliverable_id` regardless of its `kind`, via
    `deliverable_carry.resolve_explicit_predecessor_edge_deliverable_id`.

    Review: coordinator:code-reviewer (be51a7b7) P1/P3 — EM ruling:
    parameterise rather than collapse, since the two call sites' fail-soft
    postures are deliberately different and must survive byte-for-byte:

    - `narrow_catch=False` (the `plan` arm, formerly `_resolve_explicit_
      predecessor_edge_carry`): swallows ANY exception silently (`except
      Exception`), writes no degradation record — mirrors `_resolve_cited_
      sizing_deliverable_id`'s own never-raises posture.
    - `narrow_catch=True` (the newly-reached-type fallthrough): only
      catches the enumerated `(DroppedDeliverableJoinError,
      DivergentDeliverableIdError)` family (AC9's chunk body — "enumerate
      them from deliverable_carry.py, do not catch bare Exception"); on
      that catch, writes AC9's degradation record via
      `_write_deliverable_carry_degradation` instead of AC5's warning (the
      two are mutually exclusive — a degradation record already names the
      failure). Any OTHER exception propagates uncaught — deliberately
      narrower than the `plan` arm's posture; the family is exhaustive
      against the real callee today
      (test_ac9_error_family_discovery_matches_known_baseline pins it).

    Both branches mint the final `deliverable_id` themselves (`carry` on a
    resolved edge, `mint-from-title` on an empty/degraded resolution) so
    each call site reduces to a single assignment. `deliverable_carry.py`'s
    own accept/reject stderr diagnostic is swallowed here (redirected, not
    printed) so AC5's "exactly once" naming contract is owned solely by
    `_warn_predecessor_spine_not_inherited` below — a duplicate diagnostic
    line naming the same predecessor would violate it.

    ``predecessor_relpath`` is passed straight through as given (relative
    to the process CWD), mirroring the `handoff` arm's own `_predecessor_
    path` contract (`getattr(args, "predecessor", None)`, never joined
    against `repo_root`).

    Spec backlink: docs/plans/2026-08-14-baton-closes-when-its-plan-ships.md § C1/C2, AC1/AC3/AC4/AC5/AC9
    """
    if not predecessor_relpath:
        return _mint_deliverable_id_from_title(title, doc_type, repo_root)

    _ensure_engine_on_path()
    from coordinator_core.ops.deliverable_carry import (  # noqa: PLC0415
        DivergentDeliverableIdError,
        DroppedDeliverableJoinError,
        resolve_explicit_predecessor_edge_deliverable_id,
    )
    from coordinator_core.ops.read_frontmatter_field import (  # noqa: PLC0415
        read_frontmatter_field as _read_frontmatter_field,
    )

    if narrow_catch:
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                _edge_dlv = resolve_explicit_predecessor_edge_deliverable_id(
                    _read_frontmatter_field, predecessor_relpath
                )
        except (DroppedDeliverableJoinError, DivergentDeliverableIdError) as _nr_carry_exc:
            _fallback = _mint_deliverable_id_from_title(title, doc_type, repo_root)
            _write_deliverable_carry_degradation(
                repo_root, doc_type, _nr_carry_exc, _fallback, title,
                predecessor_path=predecessor_relpath,
            )
            return _fallback
    else:
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                _edge_dlv = resolve_explicit_predecessor_edge_deliverable_id(
                    _read_frontmatter_field, predecessor_relpath
                )
        except Exception:  # noqa: BLE001 -- best-effort; degrade to no-carry, never block scaffolding
            _edge_dlv = None

    if _edge_dlv:
        return _mint_deliverable_id(
            deliverable_id=_edge_dlv, carry_source="explicit predecessor edge"
        )
    _warn_predecessor_spine_not_inherited(predecessor_relpath)
    return _mint_deliverable_id_from_title(title, doc_type, repo_root)


def _warn_predecessor_spine_not_inherited(predecessor_relpath: str) -> None:
    """AC5 loud fallthrough — one line naming the predecessor whose spine
    was not inherited, per docs/wiki/guard-messaging.md § Register: one
    fact, stated once, plus the terse alternative (falls through to mint-
    from-slug). No block, no override key. Callers only invoke this when a
    predecessor edge WAS supplied and no rung resolved it (anti-scope: never
    on the legitimate no-predecessor path)."""
    print(
        "coordinator-doc-new: predecessor "
        f"{predecessor_relpath!r} carries no deliverable_id — spine not "
        "inherited, falling through to mint-from-slug",
        file=sys.stderr,
    )


def _write_deliverable_carry_degradation(
    repo_root: str | None,
    doc_type: str,
    error: Exception,
    fallback_deliverable_id: str | None,
    title: str,
    claimed_plan_path: str | None = None,
    predecessor_path: str | None = None,
) -> None:
    """AC9's fail-soft degradation trace, shared by the `handoff` arm and
    C1's newly-reached-type fallthrough (AC9's body: "reuse that code
    path — do not author a second copy"). Emits one stderr line naming the
    error type, then writes the same durable
    `state/audits/<date>-*-deliverable-carry-degradation.jsonl` record the
    `handoff` arm originally established (2026-08-03 deliverable-id-carry-
    plan-handoff-agree).

    Negative-spec: never raises — an unwritable `state/audits/` directory
    degrades to a stderr-only note (the original `handoff` arm's own
    posture), never blocking scaffolding.

    Spec backlink: docs/plans/2026-08-14-baton-closes-when-its-plan-ships.md § C1, AC9
    """
    print(
        f"coordinator-doc-new: {doc_type} deliverable-carry degraded to "
        f"no-carry ({type(error).__name__}): {error}",
        file=sys.stderr,
    )
    if not repo_root:
        return
    audit_dir = os.path.join(repo_root, "state", "audits")
    try:
        os.makedirs(audit_dir, exist_ok=True)
        audit_path = os.path.join(
            audit_dir,
            f"{datetime.date.today().isoformat()}"
            f"-{doc_type}-deliverable-carry-degradation.jsonl",
        )
        with open(audit_path, "a", encoding="utf-8", newline="\n") as audit_fh:
            audit_fh.write(
                json.dumps(
                    {
                        "timestamp": datetime.datetime.now(
                            datetime.timezone.utc
                        ).isoformat(),
                        "error_type": type(error).__name__,
                        "error_message": str(error),
                        "claimed_plan_path": claimed_plan_path,
                        "predecessor_path": predecessor_path,
                        "fallback_deliverable_id": fallback_deliverable_id,
                        "scaffolded_title": title,
                    }
                )
                + "\n"
            )
    except OSError:
        print(
            "coordinator-doc-new: failed to write the durable audit "
            f"record to {audit_dir!r} — the stderr warning above "
            "is the only surviving record of this degradation",
            file=sys.stderr,
        )


def _mint_artifact_id_from_title(prefix: str, title: str, doc_type: str, field: str) -> str | None:
    """Title-derived artifact-id mint (hnd-/cmp-), refusing on a placeholder title.

    Review: coordinator:code-reviewer (913d6318) F2 — the hnd-/cmp- guard was
    previously two inline if/else blocks in main(), untested independently of the
    shared `_is_placeholder_title` predicate. Wrapping unifies the hnd-/cmp- call
    sites with the same shape as `_mint_deliverable_id_from_title`, so all four id
    spaces route through one pattern and this wrapper is directly unit-testable.
    """
    if _is_placeholder_title(title):
        _warn_placeholder_id_skipped(field, doc_type)
        return None
    return _mint_artifact_id(prefix, _slug_from_title(title))


def _plan_slug_from_path(plan_path: str) -> str:
    """Derive the plan slug from a plan path, mirroring fan-out-dispatch.sh logic.

    Strips the leading YYYY-MM-DD- prefix and .md suffix from the plan basename.
    E.g.: docs/plans/2026-06-09-executor-sidecar-flight-recorder.md
          → executor-sidecar-flight-recorder

    Port of: fan-out-dispatch.sh § PLAN_SLUG (DoE 65e5d199, 2026-07-19)
    Negative-spec: if the basename has no YYYY-MM-DD- prefix the full basename (minus .md)
    is used as-is — no error is raised, matching fan-out-dispatch.sh fallback behaviour.
    Negative-spec: if stripping the date prefix and .md suffix yields an empty string (e.g.
    basename "2026-06-30-.md"), the function returns the original basename as-is. This edge
    case cannot occur with a valid plan file (date-only names are not valid plan stems);
    fan-out-dispatch.sh exits 2 in this case while this function returns the raw basename.
    # Review: code-reviewer item-5 F7 — documents the empty-after-strip edge case and the parity gap with fan-out-dispatch.sh
    """
    basename = os.path.basename(plan_path)
    # Strip leading YYYY-MM-DD- prefix (8 digits + dash), mirroring fan-out-dispatch.sh:
    # plan_slug_tmp="${plan_basename#[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-}"
    slug = re.sub(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}-", "", basename)
    # Strip trailing .md suffix
    if slug.endswith(".md"):
        slug = slug[:-3]
    return slug or basename


# ---------------------------------------------------------------------------
# Delegation helpers — queue and lesson types (A4)
# ---------------------------------------------------------------------------

def _peek_doc_type() -> str | None:
    """Pre-scan sys.argv for --type <value> without full argparse.

    Returns the type value if found, None otherwise.
    Used for early delegation before argparse: queue-type args (--body, --risk,
    --severity, etc.) are not known to this parser and would be rejected if we
    called parse_args() first.

    Handles both '--type VALUE' (two-token form) and '--type=VALUE' (one-token form).
    """
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--type" and i + 1 < len(args):
            return args[i + 1]
        if arg.startswith("--type="):
            return arg.split("=", 1)[1]
    return None


def _argv_without_type() -> list[str]:
    """Return sys.argv[1:] with the --type <value> token pair (or --type=value) stripped,
    AND with any --schema <value> / --schema=value pair stripped.

    The delegation functions call the delegate binary with this stripped arg list
    so the delegate tool does not see an unexpected --type argument.

    --schema is also stripped so that a caller-supplied --schema cannot override the
    delegation's intended --schema <doc_type> (argparse last-wins would otherwise
    cause the delegate to write to the WRONG queue with exit 0).
    # Review: code-reviewer CORRECTNESS — strip --schema pairs so delegated --schema wins.
    """
    result = []
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--type" and i + 1 < len(args):
            i += 2  # skip --type <value>
        elif args[i].startswith("--type="):
            i += 1  # skip --type=value
        elif args[i] == "--schema" and i + 1 < len(args):
            i += 2  # skip --schema <value> — prevent caller from overriding delegation schema
        elif args[i].startswith("--schema="):
            i += 1  # skip --schema=value
        else:
            result.append(args[i])
            i += 1
    return result


def _find_sibling_binary(name: str) -> str:
    """Find the path to a coordinator binary in the same bin/ directory as this script.

    Fails loud (sys.exit 1) if the binary is not found — this is a coordinator
    installation issue, not a caller error.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(script_dir, name)
    if not os.path.isfile(path):
        print(
            f"error: delegate binary '{name}' not found at expected path '{path}'. "
            "This is a coordinator installation issue — ensure the plugin is fully installed.",
            file=sys.stderr,
        )
        sys.exit(1)
    return path


def _delegate_to_queue_append(doc_type: str) -> None:
    """Delegate a queue type to coordinator-queue-append --schema <doc_type>.

    Queue types (improvement-queue, bug-backlog, debt-backlog) MUST delegate here
    rather than re-implement the YAML schema shape. This ensures A4 inherits tc-2's
    queue consolidation — coordinator-queue-append owns the schema, validation, YAML
    emission, and output path for all three queue schemas.

    All sys.argv args (minus --type) are forwarded to the delegate. The --schema
    flag is prepended so the delegate receives: --schema <doc_type> <remaining args>.

    Explicit capture-then-forward, not bare stdio inheritance: mirrors
    _delegate_to_workflow_scaffold's fix for the same defect (see that
    function's docstring) — CREATE_NO_WINDOW from _no_console_creationflags()
    combined with a parent whose own stdout/stderr is already redirected
    (any caller that itself captures this CLI's output, e.g. subprocess.run
    with capture_output=True) was observed losing the delegate's stdout/stderr
    entirely on Windows. A common failure shape this fixes: coordinator-doc-new
    --type bug-backlog without --status delegates to coordinator-queue-append,
    which parser.error()s "the following arguments are required: --status" and
    exits 2 — but that diagnostic never reached the caller, producing a
    silent exit 2 with empty stdout AND stderr.

    Spec backlink: docs/plans/2026-06-25-example-initiative-tc-4-fleet-machinery-contract-emit.md § A4
    Spec backlink: state/bug-backlog/2026-08-10-coordinator-doc-new-type-bug-backlog-exi-f711f2bcf677.yaml
    Negative-spec: does NOT re-implement queue YAML shape — delegation is MANDATORY per spec.
    Negative-spec: does NOT default --status (or any other missing required queue
    field) — the delegate's own parser.error is the source of truth for what's
    required per schema, and now reaches the caller intact; inventing a default
    here would be a product decision (e.g. "open" is not universally correct)
    this scaffold has no authority to make.
    """
    delegate = _find_sibling_binary("coordinator-queue-append.py")
    passthrough = _argv_without_type()
    cmd = [sys.executable, delegate, "--schema", doc_type] + passthrough
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        **_no_console_creationflags(),
    )
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    sys.exit(result.returncode)


def _delegate_to_lesson_promote() -> None:
    """Delegate --type lesson to coordinator-lesson-promote.

    Scaffolds a lessons-outbox YAML entry at the PROMOTE altitude — NOT a lessons.md
    capture line. Capture stays a low-friction direct append per tc-2 D3.

    All sys.argv args (minus --type) are forwarded to coordinator-lesson-promote.

    Spec backlink: docs/plans/2026-06-25-example-initiative-tc-4-fleet-machinery-contract-emit.md § A4
    Negative-spec: does NOT append to lessons.md — that surface stays a direct-append
    low-friction operation; this scaffolder is for the outbox/promote altitude only.
    """
    delegate = _find_sibling_binary("coordinator-lesson-promote.py")
    passthrough = _argv_without_type()
    cmd = [sys.executable, delegate] + passthrough
    result = subprocess.run(cmd, **_no_console_passthrough_kwargs())
    sys.exit(result.returncode)


def _delegate_to_workflow_scaffold() -> None:
    """Delegate --type workflow to coordinator-workflow-scaffold.py.

    workflow.scaffold is a COMPUTE_ONLY claude-klabauter op — it returns Workflow-skeleton
    text, it does not write a frontmatter document. There is no local schema to
    scaffold; the veneer is a Python bin invoked via sys.executable (owns the
    cc_invoke transport seam), not a schema-generating scaffold itself. All
    sys.argv args (minus --type)
    are forwarded verbatim to the veneer.

    --repo is NEVER injected here. workflow.scaffold is a "none"-scoped op, so
    DR-279 makes the veneer refuse --repo rather than silently no-op it; injecting
    a resolved repo root (which this delegate did until 2026-08-21) refused every
    invocation of --type workflow, not just the ones that passed --repo. An
    explicit --repo from the caller is forwarded unchanged so it meets that
    refusal, which is DR-279's point.

    Spec backlink: pln-workflow-skeleton-stamper-maki-adab0d
    Negative-spec: does NOT parse or validate --name/--phase/--pattern here — the
    veneer owns all flag parsing and the op contract. This function only forwards.
    """
    delegate = _find_sibling_binary("coordinator-workflow-scaffold.py")
    passthrough = _argv_without_type()
    # An empty-string --repo value ("--repo ""` or `--repo=`) is treated the same
    # as absent: strip it before the presence check so it falls through to
    # auto-resolution rather than passing an empty value to the veneer, which
    # would then hit its own generic "--repo is required" error.
    if "--repo" in passthrough:
        _idx = passthrough.index("--repo")
        if _idx + 1 < len(passthrough) and passthrough[_idx + 1] == "":
            del passthrough[_idx : _idx + 2]
    passthrough = [a for a in passthrough if a != "--repo="]
    cmd = [sys.executable, delegate] + passthrough
    # Explicit capture-then-forward, not bare stdio inheritance: a parent
    # whose OWN stdout is already a redirected pipe (the common shape for
    # any caller that itself captures this CLI's output — see
    # test_workflow_delegation_auto_resolves_repo_when_omitted /
    # test_workflow_delegation_empty_repo_flag_auto_resolves) combined with
    # `_no_console_creationflags()`'s CREATE_NO_WINDOW on the delegate spawn
    # was observed losing the delegate's stdout/stderr entirely on Windows —
    # the delegate itself exits 0 having written real output, but the
    # caller's own captured stdout comes back empty. Capturing here and
    # writing it through explicitly sidesteps whatever handle-inheritance
    # interaction produced that, and is strictly no worse in the normal
    # (inherited-console) case.
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        **_no_console_creationflags(),
    )
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    sys.exit(result.returncode)


# ---------------------------------------------------------------------------
# Scaffold generators
# ---------------------------------------------------------------------------

# Valid category enum values for handoff-schema-family records (handoff, recovery,
# spinoff, roadmap-baton, goal-seed, roadmap-seed). Hand-copied from
# coordinator_core/frontmatter/schemas/handoff.schema.json's category property — kept
# honest by test_handoff_category_enum_parity.py, which fails loud on drift.
#
# Spec backlink: cross-repo/inbox/2026-07-23-example-cockpit-repo-em-coordinator-doc-new-category-no-validation.md
_HANDOFF_CATEGORY_ENUM = (
    "roadmap",
    "infra",
    "bug",
    "docs",
    "research",
    "refactor",
    "uncategorized",
    "queue-derived-baton",
)


def _validate_category(value: str) -> None:
    """Fail loud (sys.exit 1) if value is not a legal handoff category:.

    Called from every handoff-schema-family scaffolder, BEFORE the frontmatter is
    written — this guards a hand-supplied --category value AND each scaffolder's own
    hardcoded default alike, so a bad category can no longer be scaffolded and only
    surface later at gate-recheck/claim-handoff stamp time in a different session.

    Spec backlink: cross-repo/inbox/2026-07-23-example-cockpit-repo-em-coordinator-doc-new-category-no-validation.md
    """
    if value not in _HANDOFF_CATEGORY_ENUM:
        print(
            f"error: category '{value}' is not a valid handoff category. "
            f"Must be one of: {', '.join(_HANDOFF_CATEGORY_ENUM)}.",
            file=sys.stderr,
        )
        sys.exit(1)


# Canonical Session Ledger block, shared verbatim by every handoff-family scaffolder
# (_scaffold_handoff/_scaffold_recovery/_scaffold_spinoff/_scaffold_roadmap_baton/
# _scaffold_roadmap_seed/_scaffold_goal_seed). session_ledger.aggregate_chain_loe sums this
# block's rows; the comment's one-line grammar MUST stay the format parse_session_ledgers
# reads (_ONELINE_RE) — do not fork this literal per-kind, that duplication is the defect
# this constant exists to close.
# Owned by coordinator_core.session_ledger (the parser's own package) — imported here,
# not re-typed, so emitter and parser cannot drift independently.
# Spec backlink: pln-ledger-owing-handoff-kinds-emi-648818 § C1/C2
_SESSION_LEDGER_BLOCK: list[str] | None = SESSION_LEDGER_BLOCK_LINES


def _require_session_ledger_block() -> list[str]:
    """Fail loudly (sys.exit 1) if the module-level import of
    ``SESSION_LEDGER_BLOCK_LINES`` degraded to ``None`` (unresolvable engine).

    Called by each of the six ledger-owing scaffolders before they emit their
    body — those kinds cannot produce a conformant, ledger-summable body
    without the canonical block, so silently proceeding without it would
    reproduce the exact "chain reads zero effort" defect this plan exists to
    close. Non-ledger-owing doc types never call this and are unaffected by
    an absent engine.
    """
    if _SESSION_LEDGER_BLOCK is None:
        print(
            "error: cannot scaffold this doc type — coordinator_core.session_ledger "
            "did not import (unresolvable engine seam), and this kind owes a "
            "'## Session Ledger' block. Fix the engine seam (see "
            "_ensure_engine_on_path) and retry.",
            file=sys.stderr,
        )
        sys.exit(1)
    return _SESSION_LEDGER_BLOCK


def _scaffold_handoff(
    title: str,
    branch: str,
    deliverable_id: str | None = None,
    initiative: str | None = None,
    handoff_id: str | None = None,
    origin_handoff_id: str | None = None,
    predecessor: str | None = None,
    predecessor_id: str | None = None,
    category: str | None = None,
    additional_predecessors: list[str] | None = None,
    summary: str | None = None,
    gated_open: str | None = None,
    gate_note: str | None = None,
    gated_predicate: str | None = None,
    deliverable_ids: list[str] | None = None,
    plan_ids: list[str] | None = None,
) -> str:
    """Generate validator-clean handoff frontmatter + canonical section skeleton.

    Produces a conformant handoff (kind: session-handoff) against the handoff schema.
    Cross-field required fields for post-2026-05-29 created dates: category, summary.
    All required fields are present with placeholder values the EM replaces via Edit.

    deliverable_id and initiative are D9 present-as-null: emitted as 'null' when
    not supplied, never key-absent. deliverable_id is auto-inherited from the
    DELIVERABLE_ID env var (set by the skill when a plan's session is active) or
    minted fresh when no parent id is discoverable from session context.

    handoff_id (lvv-01/C1) is the new durable-link stable ID (hnd-<slug>-<6hex>),
    OPTIONAL in the schema — omitted entirely (not emitted as null) when not
    supplied, matching the schema's "optional, no migration" backfill policy for
    pre-existing artifacts that predate this field.

    origin_handoff_id/predecessor_id (C2, ID-companions) are pure carry-through —
    the calling skill resolves the value by reading handoff_id off the artifact
    the companion's path field (origin_handoff/predecessor) names; this scaffolder
    never resolves or mints them. Omitted entirely (not null) when not supplied,
    matching handoff_id's optional-omit convention above.

    predecessor (the path field predecessor_id companions) is carry-through on
    the same terms — the caller supplies a repo-relative path to the baton this
    handoff continues, and this scaffolder neither resolves nor validates it.
    Defaults to the literal 'none' when not supplied, so a fork (and every
    pre-existing caller) scaffolds byte-identically to before this parameter
    existed. Only the session-handoff scaffolder takes it: the spinoff kinds are
    predecessor:none-by-design (schema_validate.py Rule A3a-3
    _cf_spinoff_predecessor_none) and the recovery baton's 'predecessor' means a
    crashed commit SHA, not a baton path — neither may be threaded here.

    additional_predecessors (--additional-predecessor, repeatable) is the
    successor-side down-edge of a fan-in succession: the extra parent batons
    beyond `predecessor`. Carry-through on the same terms as predecessor —
    neither resolved nor normalized here; the calling engine (baton_assemble's
    `_build_directives`) renders every entry repo-relative before it arrives,
    because the schema's cross-field integrity rule
    (`_cf_additional_predecessors_integrity`) compares by EXACT STRING, so an
    unnormalized entry would evade the duplicate-of-primary check. Emitted as a
    YAML block sequence when non-empty; the key is omitted entirely when empty,
    matching handoff_id/predecessor_id's optional-omit convention above and
    `pickup_assemble._LIST_FIELD_KEYS`, which already parses this field as a
    multi-line list.

    Duplicate entries, and an entry equal to `predecessor`, are refused
    (fail-loud) rather than silently deduped — the same posture as the
    predecessor_id-without-predecessor refusal below, and for the same reason:
    the scaffolder must not be able to author frontmatter the validator will
    then reject. Deduping silently would also hide a genuine caller bug (a
    fan-in leg resolved twice) behind a clean-looking artifact.

    Spec backlink: roadmap stub sedge-02 (state/roadmap/sedge-2026-08-06/),
    § Successor-side back-edge on a fan-in.

    summary (--summary) replaces the hardcoded placeholder summary when
    supplied; the placeholder is emitted unchanged when omitted (byte-identical
    to before this parameter existed). Refused fail-loud when blank or over the
    handoff schema's 140-char cap (_cf_summary_length_cap) — the caller fixes it
    here rather than the scaffolder authoring frontmatter the validator will
    then reject.

    gated_open (--gated-open) DECLARES THE BLOCKER, it does not author the
    readiness trio directly (C3, docs/plans/2026-08-19-gate-notes-are-
    advisory-blocked-by-derives-readiness.md). Supplying it writes
    `blocked_by: [<gated_open>]` and readiness (deployment_state/
    pickup_ready) is DERIVED from that via `reconcile.gate_eval
    .derive_readiness` (C1) — the same one-evaluator seam every other reader
    of `blocked_by` goes through, rather than this scaffolder hardcoding
    awaiting_gate/pickup_ready:false itself. Against an empty resolution
    index (scaffold time has no corpus to check) an unresolved id derives
    awaiting_gate/pickup_ready:false, matching the pre-C3 DR-173-trio output
    for the common case. Omitted → `blocked_by: []` derives ready_to_fire/
    pickup_ready:true, byte-identical to today (AC2). Refused fail-loud when
    blank. Refused fail-loud (not silently degraded) when the engine is
    unresolvable, since a caller supplying --gated-open needs the derivation
    to actually run — the no-flag path degrades gracefully instead (see
    body), because it must not gain an engine dependency it never had.

    gate_note (--gate-note) sets `blocking_notes` ONLY — it is advisory
    prose and, per the 2026-08-19 ruling, must NEVER flip readiness; only
    `blocked_by` may. Two flags because they are two concepts: --gated-open
    declares the mechanical blocker, --gate-note carries the human-readable
    reason. Legal alone (leaves the baton pickup_ready — this is the CLI-
    surface assertion of the ruling, AC4) and legal together with
    --gated-open (a blocked baton that also carries a note). Refused
    fail-loud when blank.

    Spec backlink: docs/plans/2026-08-19-promote-fills-its-own-placeholders.md
    Spec backlink: docs/plans/2026-08-19-gate-notes-are-advisory-blocked-by-derives-readiness.md § C3

    Supplying predecessor_id WITHOUT predecessor is refused (fail-loud). The two
    are the ID and path representations of one edge, and the referential-integrity
    checker cannot catch the inconsistent pairing — it explicitly skips the
    comparison when the path field is unset ('ID present, path absent — nothing to
    compare', schema_validate.py _check_handoff_id_refs). A scaffold emitting
    predecessor: none alongside a real predecessor_id is self-contradictory
    frontmatter that validates clean, so the refusal has to live here, at the only
    point that has both values in hand.

    handoff_phase is emitted unconditionally as the literal 'continuation' —
    a third emission pattern distinct from deliverable_id/initiative's
    present-as-null and handoff_id's optional-omit above. execution_authorized_*
    fields (by/at/sha/note) are deliberately NOT scaffolded here — they are
    stamped only at execution-authorization time, not at generic scaffold.

    authoring_session (2026-07-30, cross-authorship adoption gap) is stamped
    from `_resolve_session_id()` — the SAME resolver + precedence chain this
    file already uses for --type run-report and --type subagent-sidecar's
    `dispatched_by` field. Omitted entirely (not null, not 'PLACEHOLDER') when
    the resolver yields only its own 'em-unknown' fallback sentinel —
    matching handoff_id's optional-omit convention above, not the literal
    PLACEHOLDER string the OTHER scaffolders (spinoff/goal-seed/roadmap-seed)
    emit for a human to fill in later via EM Edit. That distinction is
    load-bearing, not cosmetic: `coordinator_core.baton_assemble
    ._adopt_prior_attempt_scaffold_path` gates cross-authorship adoption on
    this field being a machine-trustworthy fact, and a stray 'em-unknown' or
    'PLACEHOLDER' string sitting in it would be exactly the operator-typed
    prose that predicate's docstring says it must never gate on.

    category (--category) is validated against _HANDOFF_CATEGORY_ENUM before the
    frontmatter is written (fail-loud, naming all legal values on mismatch) —
    defaults to 'infra' unchanged when not supplied (behavior-preserving default).
    Spec backlink: cross-repo/inbox/2026-07-23-example-cockpit-repo-em-coordinator-doc-new-category-no-validation.md

    deliverable_ids/plan_ids (--deliverable-ids/--plan-ids, repeatable, C1 plural
    carriers) are pure carry-through on the same terms as additional_predecessors:
    never resolved or minted here. Emitted as a YAML block sequence ONLY when the
    corresponding flag was supplied at all (list is not None) — omitted entirely
    (not `[]`, not `null`) when the flag was never passed. The 2+-distinct-id
    threshold that decides WHEN a caller passes these flags is not decided here
    (C2 owns it); this scaffolder emits exactly what it is handed.
    The singular --deliverable-id emission above is untouched by this addition —
    it does not route the singular value through these new flags.

    Spec backlink: pln-fleet-deliverable-spine-identity-and-facets-2b331c § D1, D2, C3b
    Spec backlink (handoff_id): docs/plans/2026-07-08-lifecycle-vocab-c2-durable-links-rollup.md § C1
    Spec backlink (handoff_phase): docs/plans/2026-07-17-execution-handoff-phase-doe-contract.md § C4
    Spec backlink (origin_handoff_id/predecessor_id): cross-repo memo
    2026-07-22-claude-klabauter-em-c2-id-companions (ask 1);
    docs/plans/2026-07-08-lifecycle-vocab-c2-durable-links-rollup.md § C2
    Negative-spec: does NOT generate body prose — placeholder comments only.
    The EM authors the body; the scaffolder provides the shape.
    """
    today = _today()
    # Placeholder summary: ≤140 chars, non-empty — satisfies the post-cutoff cross-field rule.
    placeholder_summary = f"PLACEHOLDER — replace with one-line session summary (≤140 chars)"
    _dlv = _yaml_quote(deliverable_id) if deliverable_id else "null"
    _ini = _yaml_quote(initiative) if initiative else "null"
    _category = category if category else "infra"
    _validate_category(_category)
    _predecessor = predecessor.strip() if predecessor and predecessor.strip() else "none"
    if predecessor_id and _predecessor in ("none", "null"):
        print(
            "coordinator-doc-new: --predecessor-id was supplied without --predecessor. "
            "They are the ID and path representations of the same continuation edge; "
            "emitting predecessor_id alongside 'predecessor: none' produces "
            "self-contradictory frontmatter that the referential-integrity checker "
            "cannot catch (it skips the comparison when the path field is unset). "
            "Pass --predecessor <repo-relative-path> as well, or drop --predecessor-id.",
            file=sys.stderr,
        )
        sys.exit(1)
    # Review: coordinator-code-reviewer — an empty/whitespace-only entry is the
    # same class of caller bug as a duplicate or a primary-collision (a fan-in
    # leg silently dropped), so it is refused fail-loud rather than filtered
    # out, matching this function's stated posture everywhere else here.
    if additional_predecessors and any(not e or not e.strip() for e in additional_predecessors):
        print(
            "coordinator-doc-new: --additional-predecessor was supplied an empty or "
            "whitespace-only value. additional_predecessors carries the fan-in legs "
            "beyond --predecessor; a blank entry would be silently dropped rather than "
            "emitted, which is exactly the silent edge-loss this stub exists to remove. "
            "Pass a real repo-relative path, or omit the flag for that leg.",
            file=sys.stderr,
        )
        sys.exit(1)
    _extra_preds = [e.strip() for e in (additional_predecessors or [])]
    if len(set(_extra_preds)) != len(_extra_preds):
        print(
            "coordinator-doc-new: --additional-predecessor was supplied the same path "
            "more than once. The handoff schema's cross-field rule "
            "(_cf_additional_predecessors_integrity) forbids duplicate entries, so "
            "emitting them would author frontmatter the validator rejects. A repeated "
            "leg usually means the caller resolved one fan-in predecessor twice.",
            file=sys.stderr,
        )
        sys.exit(1)
    if _predecessor not in ("none", "null") and _predecessor in _extra_preds:
        print(
            f"coordinator-doc-new: --additional-predecessor {_predecessor!r} duplicates "
            "--predecessor. additional_predecessors carries the fan-in legs BEYOND the "
            "primary; the schema's cross-field rule forbids an entry equal to the "
            "primary predecessor. Note the rule compares by exact string, not by "
            "resolved path — pass every entry already normalized repo-relative.",
            file=sys.stderr,
        )
        sys.exit(1)
    # --summary is refused fail-loud (not silently truncated/emitted) when it
    # would author frontmatter the handoff schema's own cross-field rules
    # reject outright — blank (_cf_summary_required_post_cutoff) or over 140
    # chars (_cf_summary_length_cap). The caller fixes it here rather than
    # discovering the rejection downstream.
    if summary is not None and not summary.strip():
        print(
            "coordinator-doc-new: --summary was supplied an empty or whitespace-only "
            "value. Omit --summary entirely to keep the placeholder summary, or pass "
            "real summary text.",
            file=sys.stderr,
        )
        sys.exit(1)
    if summary is not None and len(summary) > 140:
        print(
            f"coordinator-doc-new: --summary exceeds 140 characters (got {len(summary)}). "
            "The handoff schema's _cf_summary_length_cap rejects it outright; shorten "
            "it before scaffolding.",
            file=sys.stderr,
        )
        sys.exit(1)
    # --gated-open declares the blocker (blocked_by), not the readiness (see
    # docstring) — blank is refused for the same reason as --summary above:
    # blocked_by must be a non-empty id naming what this baton is blocked by.
    if gated_open is not None and not gated_open.strip():
        print(
            "coordinator-doc-new: --gated-open was supplied an empty or whitespace-only "
            "value. blocked_by must be a non-empty id naming the blocker; omit "
            "--gated-open entirely to scaffold ready_to_fire instead.",
            file=sys.stderr,
        )
        sys.exit(1)
    # --gate-note is advisory prose only (blocking_notes) — it must NEVER
    # flip readiness (2026-08-19 ruling); see docstring.
    if gate_note is not None and not gate_note.strip():
        print(
            "coordinator-doc-new: --gate-note was supplied an empty or whitespace-only "
            "value. blocking_notes must be a non-empty string naming the reason; omit "
            "--gate-note entirely, or pass real note text.",
            file=sys.stderr,
        )
        sys.exit(1)
    # --gated-predicate is DR-173's arm: a MECHANICAL gate with no graph node.
    # The condition (a required field sitting empty) is checked by the caller
    # and is as derivable as an unresolved blocked_by -- it simply has no
    # deliverable id to name, so it must NOT be forced into blocked_by. Doing
    # that mints an entry nothing can ever resolve, which parks the baton
    # permanently even after the fields are filled: the plan's § Anti-scope
    # "do not force a fake stub id into blocked_by", and the exact break-class
    # outcome this whole surface exists to prevent. The reason text rides in
    # blocking_notes, where it is advisory and does no gating -- deleting it
    # would not unpark the baton, because the predicate is what parks it.
    if gated_predicate is not None and not gated_predicate.strip():
        print(
            "coordinator-doc-new: --gated-predicate was supplied an empty or "
            "whitespace-only value. It must name the mechanical condition that "
            "parks this baton; omit it entirely to scaffold ready_to_fire instead.",
            file=sys.stderr,
        )
        sys.exit(1)
    _summary_value = summary if summary else placeholder_summary
    _blocked_by = [gated_open] if gated_open else []
    if gated_predicate:
        # Parked by the predicate, with or without an accompanying blocked_by.
        _deployment_state = "awaiting_gate"
        _pickup_ready = "false"
    elif gated_open:
        if _derive_readiness is None:
            print(
                "coordinator-doc-new: --gated-open needs the readiness derivation "
                "engine (coordinator_core.reconcile.gate_eval.derive_readiness, C1) "
                "and it could not be resolved. Omit --gated-open to scaffold "
                "ready_to_fire instead, or fix engine resolution "
                "(_ensure_engine_on_path).",
                file=sys.stderr,
            )
            sys.exit(1)
        _readiness = _derive_readiness({"blocked_by": _blocked_by}, [])
        _deployment_state = _readiness["deployment_state"] or "awaiting_gate"
        _pickup_ready = "true" if _readiness["pickup_ready"] else "false"
    elif _derive_readiness is not None:
        _readiness = _derive_readiness({"blocked_by": _blocked_by}, [])
        _deployment_state = _readiness["deployment_state"] or "ready_to_fire"
        _pickup_ready = "true" if _readiness["pickup_ready"] else "false"
    else:
        # Engine unresolvable and no --gated-open: the no-flag path must not
        # gain an engine dependency it never had, so it keeps the pre-C1
        # hardcoded default rather than failing loud like --gated-open does.
        _deployment_state = "ready_to_fire"
        _pickup_ready = "true"
    # An unnamed scaffold advertises nothing, so it is not pickup-ready --
    # the same judgment `_is_placeholder_title` already enforces at the
    # durable-id mint sites, applied to the field that decides whether the
    # pickup index offers this baton as available work. A placeholder-titled
    # record with `pickup_ready: true` is well-formed and meaningless in
    # exactly that helper's sense: a future `/pickup` or `/workday-start`
    # surfaces it as actionable and whoever takes it finds a comment-only
    # skeleton. Reported live from DoE-claude 2026-08-20 (`cross-repo/inbox/
    # 2026-08-20-doe-claude-em-pickup-mints-a-phantom-successor.md`), where
    # one held the genuine successor's `deliverable_id` for three and a half
    # hours.
    #
    # Negative-spec: this narrows ONLY the untitled case, and only ever
    # toward `false`. A `--title`-bearing scaffold -- every roadmap and
    # spinoff stub, and every `/handoff` that names its own continuation --
    # keeps whatever `derive_readiness` decided, byte-identical to before,
    # so nothing that reads `ready_to_fire`/`pickup_ready: true` off a named
    # stub changes behaviour (`ops/handoff_close_origin_stub`, whose own
    # docstring names that pairing, operates on stubs carrying real titles).
    # It is also NOT a second gating mechanism: `deployment_state` is left
    # exactly as derived, because the baton is not blocked on anything -- it
    # is unwritten, which is a different fact and DR-173's ratified
    # awaiting_gate trio must not be counterfeited to express it.
    if _is_placeholder_title(title):
        _pickup_ready = "false"
    lines = [
        "---",
        f"title: {_yaml_quote(title)}",
        f"created: {today}",
        f"branch: {_yaml_quote(branch)}",
        "status: open",
        f"predecessor: {_predecessor if _predecessor == 'none' else _yaml_quote(_predecessor)}",
        "kind: session-handoff",
        "handoff_phase: continuation",
        "baton_role: work",
        f"deployment_state: {_deployment_state}",
        f"category: {_category}",
        f"summary: {_yaml_quote(_summary_value)}",
        f"pickup_ready: {_pickup_ready}",
    ]
    if _blocked_by:
        lines.append("blocked_by:")
        lines.extend(f"  - {_yaml_quote(_entry)}" for _entry in _blocked_by)
    # DR-173's ratified trio ships unchanged: awaiting_gate + pickup_ready:
    # false + the blocking_notes reason text. The reason is OUTPUT the gating
    # decision writes, never an input anything reads.
    # Both may be supplied: --gated-predicate names the mechanical condition
    # that parked the baton, --gate-note is an unrelated advisory constraint.
    # JOIN them rather than letting one win (review: code-reviewer slice C) --
    # `gate_note or gated_predicate` silently dropped DR-173's ratified reason
    # text whenever a caller passed both, leaving the baton parked with no
    # record of what parked it.
    _notes = [n for n in (gated_predicate, gate_note) if n]
    if _notes:
        lines.append(f"blocking_notes: {_yaml_quote('; '.join(_notes))}")
    lines += [
        f"deliverable_id: {_dlv}",
        f"initiative: {_ini}  # FK to state/initiatives/<id>.yaml; null when no named initiative",
    ]
    if handoff_id:
        lines.append(f"handoff_id: {_yaml_quote(handoff_id)}")
    if origin_handoff_id:
        lines.append(f"origin_handoff_id: {_yaml_quote(origin_handoff_id)}")
    if predecessor_id:
        lines.append(f"predecessor_id: {_yaml_quote(predecessor_id)}")
    if _extra_preds:
        lines.append("additional_predecessors:")
        lines.extend(f"  - {_yaml_quote(_entry)}" for _entry in _extra_preds)
    # deliverable_ids/plan_ids (C1, plural carriers) are pure carry-through, same
    # posture as additional_predecessors: never resolved or minted here. Emitted
    # ONLY when the flag was supplied at all — not on `[]`, not on `None` — because
    # the schema reserves `[]` for a future "explicitly zero" distinction and
    # treats absent/null alike as "no plural set authored". The 2+ threshold is
    # NOT decided here (C2 owns it); this scaffolder emits exactly what it is
    # handed, unconditionally.
    if deliverable_ids is not None:
        lines.append("deliverable_ids:")
        lines.extend(f"  - {_yaml_quote(_entry)}" for _entry in deliverable_ids)
    if plan_ids is not None:
        lines.append("plan_ids:")
        lines.extend(f"  - {_yaml_quote(_entry)}" for _entry in plan_ids)
    _authoring_session = _resolve_session_id()
    if _authoring_session != "em-unknown":
        # Readable-name annotation (2026-08-20 extension): the id above is a
        # machine-joinable UUID, opaque to a human skimming the file. The
        # display name is a YAML trailing COMMENT, not a new field -- it
        # changes no schema shape, so it degrades to nothing (not a stray
        # placeholder) when unresolvable rather than blocking the id itself.
        _display_name = _resolve_session_display_name()
        if _display_name:
            lines.append(f"# minted by {_display_name}")
        lines.append(f"authoring_session: {_yaml_quote(_authoring_session)}")
    lines.extend([
        "---",
        "",
        "## What Was Accomplished",
        "",
        "<!-- Replace with what was built, fixed, or shipped this session. -->",
        "",
        "## Current State",
        "",
        "<!-- Replace with where things stand now. -->",
        "",
        "## Next Steps",
        "",
        "<!-- Replace with what the next session should do first. -->",
        "",
        "## What I Learned",
        "",
        "<!-- What did you learn that you'd resent re-deriving? -->",
        "",
        *_require_session_ledger_block(),
    ])
    return "\n".join(lines)


def _scaffold_recovery(
    title: str,
    branch: str,
    deliverable_id: str | None = None,
    initiative: str | None = None,
    handoff_id: str | None = None,
    recovers_session: str | None = None,
    origin_handoff_id: str | None = None,
    predecessor_id: str | None = None,
    category: str | None = None,
) -> str:
    """Generate validator-clean recovery-kind handoff frontmatter + canonical section skeleton.

    Produces a conformant handoff (kind: recovery) against the handoff schema. Differs from
    kind: session-handoff on several fields (real incident: a hand-rolled recovery handoff
    shipped a 193-char summary against the <=120 cap — this scaffold exists so recovery batons
    stop being hand-rolled and drifting from the schema):

      predecessor: the hint says "crashed commit SHA or null" — NOT a predecessor handoff
        path (a recovery baton has no predecessor baton to continue; it reconstructs a
        crashed session's state from the last-known-good commit). Scaffold default: null.
      recovers_session: null — pointer to the crashed session id being reconstructed;
        the EM fills this in via Edit once the crashed session id is known. OPTIONAL field,
        no cross-field enforcement yet (see schemas/handoff.schema.json description).
      deployment_state: ready_to_fire — the crash reconstruction itself clears the gate;
        ready_to_fire forbids gate_dependency (cross-field rule), so gate_dependency is
        correctly absent here.
      additional_predecessors: [] — the schema-sanctioned fan-in mechanism for multi-handoff
        recovery reconstructions (e.g. merging state from two crashed concurrent threads).
        Prefer this over inventing a custom merged_inputs-style field.

    Body skeleton sections are DISTINCT from session-handoff's (## What Was Accomplished /
    ## Current State / ## Next Steps): ## Recovery Context, ## What Was Accomplished (by the
    crashed session, before it died), ## In-Progress Work — because a recovery baton is
    reconstructing a death, not continuing a live session.

    Spec backlink: docs/plans/2026-07-08-lifecycle-vocab-c2-durable-links-rollup.md § C2
    (predecessor_id/origin_handoff_id ancestry); recovery-scaffold task (add --type recovery
    to coordinator-doc-new).

    origin_handoff_id/predecessor_id are pure carry-through (see _scaffold_handoff's
    docstring for the full carry-not-mint contract) — omitted entirely when not supplied.
    Spec backlink: cross-repo memo 2026-07-22-claude-klabauter-em-c2-id-companions (ask 1).
    Negative-spec: does NOT generate body prose — placeholder comments only, same convention
    as _scaffold_handoff. Does NOT add a hard cross-field rule requiring recovers_session
    non-null when kind=recovery — left as a follow-up per CROSS_FIELD_RULES['handoff'] comment.

    category (--category) is validated against _HANDOFF_CATEGORY_ENUM before the
    frontmatter is written — defaults to 'infra' unchanged when not supplied.
    Spec backlink: cross-repo/inbox/2026-07-23-example-cockpit-repo-em-coordinator-doc-new-category-no-validation.md
    """
    today = _today()
    placeholder_summary = "PLACEHOLDER — replace with one-line recovery summary (≤140 chars)"
    _dlv = _yaml_quote(deliverable_id) if deliverable_id else "null"
    _ini = _yaml_quote(initiative) if initiative else "null"
    _recovers = _yaml_quote(recovers_session) if recovers_session else "null"
    _category = category if category else "infra"
    _validate_category(_category)
    lines = [
        "---",
        f"title: {_yaml_quote(title)}",
        f"created: {today}",
        f"branch: {_yaml_quote(branch)}",
        "status: open",
        "predecessor: null  # crashed commit SHA or null — NOT a predecessor handoff path",
        "kind: recovery",
        "deployment_state: ready_to_fire  # crash reconstruction clears the gate; ready_to_fire forbids gate_dependency",
        f"category: {_category}",
        f"summary: {_yaml_quote(placeholder_summary)}",
        "pickup_ready: true",
        f"recovers_session: {_recovers}  # session-id of the crashed session being reconstructed",
        "additional_predecessors: []  # schema-sanctioned fan-in mechanism for multi-handoff recovery reconstructions",
        f"deliverable_id: {_dlv}",
        f"initiative: {_ini}  # FK to state/initiatives/<id>.yaml; null when no named initiative",
    ]
    if handoff_id:
        lines.append(f"handoff_id: {_yaml_quote(handoff_id)}")
    if origin_handoff_id:
        lines.append(f"origin_handoff_id: {_yaml_quote(origin_handoff_id)}")
    if predecessor_id:
        lines.append(f"predecessor_id: {_yaml_quote(predecessor_id)}")
    lines.extend([
        "---",
        "",
        "## Recovery Context",
        "",
        "<!-- Replace with what crashed, when, and what was lost. -->",
        "",
        "## What Was Accomplished (by the crashed session, before it died)",
        "",
        "<!-- Replace with what the crashed session built, fixed, or shipped before it died. -->",
        "",
        "## In-Progress Work",
        "",
        "<!-- Replace with any partially-written work recovered from the crashed session. -->",
        "<!-- Usually \"nothing partially written\" — state that explicitly if true. -->",
        "",
        *_require_session_ledger_block(),
    ])
    return "\n".join(lines)


def _resolve_spinoff_workstream() -> str | None:
    """READ-ONLY resolve of a spinoff's `workstream` off the baton this
    session currently holds.

    Locates the held baton via `coordinator_core.ops.handoff_author_fork.
    _resolve_origin_handoff` -- the same ledger-first claim-holder scan that
    op uses to populate `origin_handoff` on a fork -- then reads that
    baton's own `workstream:` frontmatter scalar via
    `coordinator_core.ops._fm_util.extract_frontmatter_scalar`. Read-only:
    calls neither module's mutating surface, and does not import or touch
    anything else in `handoff_author_fork` beyond this one resolver.

    Degrades to None (never a hardcoded default) when: the engine is
    unresolvable, no repo root resolves, no session id resolves
    (`_resolve_session_id() == "em-unknown"`), no baton is currently held by
    this session, or the held baton has no `workstream:` field -- matching
    this file's graceful-skip convention for engine-touching seams
    (`_ensure_engine_on_path`). The caller (`_scaffold_spinoff`) omits the
    `workstream:` key entirely on None rather than emitting a placeholder --
    per state/handoffs/2026-08-21-scaffold-knows-the-session.md ("either
    derive it or stop pretending it is required").
    """
    _ensure_engine_on_path()
    try:
        from coordinator_core.ops.handoff_author_fork import (  # noqa: PLC0415
            _resolve_origin_handoff,
        )
        from coordinator_core.ops._fm_util import extract_frontmatter_scalar  # noqa: PLC0415
    except Exception:  # noqa: BLE001 -- best-effort; unresolvable engine degrades to None
        return None
    session_id = _resolve_session_id()
    if session_id == "em-unknown":
        return None
    repo_root_str = _current_repo_root()
    if not repo_root_str:
        return None
    from pathlib import Path as _Path  # noqa: PLC0415

    worktree_root = _Path(repo_root_str)
    handoffs_dir = worktree_root / "state" / "handoffs"
    try:
        origin_handoff, _origin_handoff_id = _resolve_origin_handoff(
            handoffs_dir, session_id, repo_root=worktree_root
        )
    except OSError:
        return None
    except RuntimeError:
        # `_resolve_origin_handoff` refuses fail-loud (AmbiguousOriginHandoffError,
        # a RuntimeError) when this session holds several live claims that claim
        # recency cannot rank. That refusal is provenance-critical for
        # `handoff.author_fork`, which STAMPS origin_handoff -- it is not critical
        # here, where the only consequence is one derived, optional field.
        #
        # Negative-spec: does NOT re-raise and does NOT pick a candidate. The
        # ambiguity is surfaced by the op that writes provenance; degrading to
        # omit-the-key matches this helper's every other unresolvable arm rather
        # than turning a scaffold into a traceback. Caught as RuntimeError, not by
        # importing the concrete class -- this CLI reaches coordinator_core through
        # a best-effort seam that is allowed to be absent.
        return None
    if not origin_handoff:
        return None
    try:
        text = (worktree_root / origin_handoff).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return extract_frontmatter_scalar(text, "workstream") or None


def _scaffold_spinoff(
    title: str,
    branch: str,
    deliverable_id: str | None = None,
    initiative: str | None = None,
    handoff_id: str | None = None,
    origin_handoff_id: str | None = None,
    predecessor_id: str | None = None,
    category: str | None = None,
) -> str:
    """Generate validator-clean spinoff frontmatter + canonical section skeleton.

    Produces a conformant spinoff (kind: spinoff) against the handoff schema.
    Spinoffs use the same schema as session-handoffs; kind discriminates the body dialect.

    authoring_session (2026-08-21) is stamped from `_resolve_session_id()` --
    same resolver + precedence chain `_scaffold_handoff` uses for the same
    field. Unresolvable (the resolver's own 'em-unknown' fallback sentinel)
    is refused fail-loud (sys.exit 1) rather than degrading to a hand-typed
    'PLACEHOLDER' the EM had to Edit in afterward -- a prior silent degrade
    that let a since-fixed resolver regression go unnoticed for a full day
    (state/handoffs/2026-08-21-scaffold-knows-the-session.md).

    workstream (2026-08-21) is resolved read-only off the baton this session
    currently holds via `_resolve_spinoff_workstream` (see its docstring).
    Omitted entirely (not a placeholder) when nothing resolves -- matching
    `_scaffold_handoff`'s own omit-the-key convention for `authoring_session`.

    deliverable_id and initiative are D9 present-as-null: emitted as 'null' when
    not supplied. deliverable_id is auto-inherited from DELIVERABLE_ID env var or
    minted fresh when no parent id is discoverable.

    handoff_id (lvv-01/C1) is the new durable-link stable ID (hnd-<slug>-<6hex>) —
    spinoffs share the handoff schema family, so they mint from the same hnd- prefix.
    OPTIONAL; omitted entirely (not emitted as null) when not supplied.

    origin_handoff_id/predecessor_id are pure carry-through ID-companions (C2) —
    see _scaffold_handoff's docstring for the full carry-not-mint contract.
    Omitted entirely (not null) when not supplied.

    Spec backlink: pln-fleet-deliverable-spine-identity-and-facets-2b331c § D1, D2, C3b
    Spec backlink (handoff_id): docs/plans/2026-07-08-lifecycle-vocab-c2-durable-links-rollup.md § C1
    Spec backlink (origin_handoff_id/predecessor_id): cross-repo memo
    2026-07-22-claude-klabauter-em-c2-id-companions (ask 1);
    docs/plans/2026-07-08-lifecycle-vocab-c2-durable-links-rollup.md § C2

    category (--category) is validated against _HANDOFF_CATEGORY_ENUM before the
    frontmatter is written — defaults to 'infra' unchanged when not supplied.
    Spec backlink: cross-repo/inbox/2026-07-23-example-cockpit-repo-em-coordinator-doc-new-category-no-validation.md
    """
    today = _today()
    placeholder_summary = f"PLACEHOLDER — replace with one-line spinoff summary (≤140 chars)"
    _dlv = _yaml_quote(deliverable_id) if deliverable_id else "null"
    _ini = _yaml_quote(initiative) if initiative else "null"
    _category = category if category else "infra"
    _validate_category(_category)
    # 2026-08-21 extension: the 'em-unknown' arm used to degrade to a
    # hand-typed literal 'PLACEHOLDER' the EM had to Edit in after every
    # spinoff scaffold -- a silent degrade that let a since-fixed resolver
    # regression go unnoticed for a full day (state/handoffs/2026-08-21-
    # scaffold-knows-the-session.md). This field is a machine-trustworthy
    # fact or nothing: `coordinator_core.baton_assemble
    # ._adopt_prior_attempt_scaffold_path` gates cross-authorship adoption on
    # it (see `_scaffold_handoff`'s docstring), so an unresolvable session id
    # now fails the scaffold loudly instead of authoring a fact-shaped field
    # that isn't one.
    _authoring_session_value = _resolve_session_id()
    if _authoring_session_value == "em-unknown":
        print(
            "coordinator-doc-new: --type spinoff could not resolve the authoring "
            "session id (COORDINATOR_SESSION_ID / CLAUDE_SESSION_ID / "
            "CLAUDE_CODE_SESSION_ID all unset). authoring_session must be a "
            "machine-trustworthy fact, not a hand-typed placeholder -- set one "
            "of those env vars and retry.",
            file=sys.stderr,
        )
        sys.exit(1)
    _display_name = _resolve_session_display_name()
    _authoring_session_line = (
        f"# minted by {_display_name}\n" if _display_name else ""
    ) + f"authoring_session: {_yaml_quote(_authoring_session_value)}"
    # Spinoff takes no blocker input at all, so this is always the empty-
    # blocked_by leg of C1's derive_readiness (docs/plans/2026-08-19-gate-
    # notes-are-advisory-blocked-by-derives-readiness.md § C3) -- one
    # evaluator deciding readiness rather than a second hardcoded literal
    # duplicating its own empty-blocked_by rule. Same degrade-to-hardcoded
    # posture as _scaffold_handoff's no-flag path: an unresolvable engine
    # must not break spinoff scaffolding, which never depended on it before.
    if _derive_readiness is not None:
        _readiness = _derive_readiness({"blocked_by": []}, [])
        _deployment_state = _readiness["deployment_state"] or "ready_to_fire"
        _pickup_ready = "true" if _readiness["pickup_ready"] else "false"
    else:
        _deployment_state = "ready_to_fire"
        _pickup_ready = "true"
    lines = [
        "---",
        f"title: {_yaml_quote(title)}",
        f"created: {today}",
        f"branch: {_yaml_quote(branch)}",
        "status: open",
        "predecessor: none",
        "kind: spinoff",
        "baton_role: work",
        f"deployment_state: {_deployment_state}",
        f"category: {_category}",
        f"summary: {_yaml_quote(placeholder_summary)}",
        f"pickup_ready: {_pickup_ready}",
        _authoring_session_line,
    ]
    # 2026-08-21 extension (same baton as authoring_session above): 'workstream'
    # used to hand-type a literal 'PLACEHOLDER' unconditionally. It is now
    # resolved off the baton this session currently holds
    # (_resolve_spinoff_workstream, read-only) when possible; when nothing
    # resolves, the key is OMITTED entirely rather than re-emitting a
    # placeholder -- "either derive it or stop pretending it is required"
    # (state/handoffs/2026-08-21-scaffold-knows-the-session.md § 2), the same
    # omit-the-key convention `_scaffold_handoff` already uses for its own
    # `authoring_session` arm.
    _resolved_workstream = _resolve_spinoff_workstream()
    if _resolved_workstream:
        lines.append(f"workstream: {_yaml_quote(_resolved_workstream)}")
    lines.extend([
        f"deliverable_id: {_dlv}",
        f"initiative: {_ini}  # FK to state/initiatives/<id>.yaml; null when no named initiative",
    ])
    if handoff_id:
        lines.append(f"handoff_id: {_yaml_quote(handoff_id)}")
    if origin_handoff_id:
        lines.append(f"origin_handoff_id: {_yaml_quote(origin_handoff_id)}")
    if predecessor_id:
        lines.append(f"predecessor_id: {_yaml_quote(predecessor_id)}")
    lines.extend([
        "---",
        "",
        # Review: code-reviewer S4-F2 — expanded to canonical spinoff section grammar per
        # skills/spinoff/SKILL.md; replaced orphan ## Context with the full addressable-section set.
        "## What this covers",
        "",
        "<!-- One paragraph: origin context, what surface is in play, who's affected. -->",
        "",
        "## Reference materials (read first)",
        "",
        "<!-- List file paths the picking-up EM will need, each with a one-line annotation. -->",
        "",
        "## Specification",
        "",
        "<!-- The actual work spec. Be concrete enough that a context-less EM can act. -->",
        "",
        "## Acceptance criteria",
        "",
        "<!-- Checklist the picking-up EM gates completion against. -->",
        "<!-- `- [ ]`/`- [x]` checkboxes only — the consumed-handoff completeness -->",
        "<!-- gate counts boxes and reads a prose list as indeterminate. -->",
        "",
        "- [ ] ",
        "",
        "## Recommended next steps for the picking-up EM",
        "",
        "<!-- 3-7 numbered steps, each verifiable. -->",
        "",
        "## Anti-scope",
        "",
        "<!-- Failure modes a context-less EM might hit. Negative scope. -->",
        "",
        "## What travels with this spinoff",
        "",
        "<!-- Sizings, plans, or components leaving this EM's hands with the -->",
        "<!-- spinoff. Ask, don't search or guess -- nothing to log? Leave this -->",
        "<!-- section empty; that absence stays truthful. -->",
        "",
        *_require_session_ledger_block(),
        "",
        _spinoff_marker(today, _authoring_session_value, _display_name),
    ])
    return "\n".join(lines)


def _spinoff_marker(
    created: str, authoring_session: str, display_name: str | None
) -> str:
    """Render the trailing ``<!-- spinoff: ... -->`` greppability marker.

    Every fact in this line is already resolved at scaffold time — ``created``
    is the same value emitted as the ``created:`` frontmatter field,
    ``authoring_session`` the same value emitted as ``authoring_session:``, and
    ``display_name`` the same value the ``# minted by`` comment carries. The
    marker is therefore machine-knowable in full, and stamping it here is R6
    (`docs/research/spike-verdicts/2026-08-21-ceremony-assemblers-cost-
    attribution.md` § PM rulings) applied to the authoring surface: facts the
    machine knows at write time get stamped, only facts the EM alone knows get
    asked.

    Before 2026-08-21 the hand path retyped this line from
    `skills/spinoff/SKILL.md` Step 2 while the machine path
    (`coordinator_core/backlog_grind_assemble/readers_blitz.py`, bug-blitz's
    `build_spinoff_handoff`) already emitted it programmatically — one chore,
    two producers, and a measured ZERO consumers across `coordinator_core/`,
    `coordinator/`, `schemas/`, and the skills tree. Greppability is preserved
    by keeping the `<!-- spinoff: ` prefix byte-identical to the bug-blitz
    producer's, so the two paths remain one grep.

    Negative-spec: the `by <who>` slot is the session DISPLAY NAME, never a
    reconstructed identity — an unresolvable display name degrades to the
    literal `current EM` (the same words the hand-typed form used) rather than
    scanning for one. R1: absence is information, never a corpus search.
    """
    who = display_name if display_name else "current EM"
    return f"<!-- spinoff: {created} by {who} during {authoring_session} -->"


def _scaffold_roadmap_baton(
    title: str,
    branch: str,
    roadmap_id: str,
    stub_id: str,
    deliverable_id: str | None = None,
    initiative: str | None = None,
    category: str | None = None,
    handoff_id: str | None = None,
    gate_dependency: str | None = None,
    sizing_object: str | None = None,
) -> str:
    """Generate validator-clean roadmap-baton frontmatter + canonical section skeleton.

    Emits the full graph-field frontmatter set for kind: roadmap-baton, conformant
    against the handoff schema + CROSS_FIELD_RULES (roadmap_id/stub_id/wave/blocks/
    blocked_by required; deployment_state=awaiting_gate requires at least one of
    gate_dependency (deprecated), blocked_by, or blocking_notes; category/summary
    required post-2026-05-29).

    Graph field placeholders (sprint, wave, cost, blocks, blocked_by, scope) are
    best-effort stubs — the author fills them via Edit after the topo sort via
    bin/roadmap-number-stubs (skills/roadmap-planning/SKILL.md § Step 2.1.5).
    gate_dependency is the deprecated single-string gate field (C2); when not
    supplied a scaffolded stub instead gets a blocking_notes placeholder (C1 of
    docs/plans/2026-08-03-gate-dependency-template-emission-spec.md) — the
    non-deprecated field satisfies the same cross-field OR without writing the
    field the template was deprecating it away from.

    pickup_ready is OMITTED per SKILL § Phase 2.1 note: absence triggers a non-blocking
    /pickup warn; awaiting_gate + a named gate (blocking_notes, gate_dependency, or
    blocked_by) is the real sequencing gate.

    deliverable_id is auto-minted from stub_id when not supplied (D1: roadmap stubs
    reuse stub identity → dlv-<stub_id>). initiative is D9 present-as-null.

    sizing_object is emitted as a real frontmatter key, mirroring the `plan` arm.
    A roadmap arrives THROUGH the sizing lobby and every stub is assigned its own
    `loe:` at mint, so a roadmap baton IS sized work — the FK simply went
    unwritten, which left PM-ratified stubs reading `unsized` to
    `coordinator_core.sizing_disposition` and would have bounced them back to the
    lobby to re-make a size that already existed. The literal string "null" (from
    --no-sizing-object) emits an explicit `sizing_object: null` — the checkable
    declaration of absence, never a silent omission.

    handoff_id (lvv-01/C1) is the new durable-link stable ID (hnd-<slug>-<6hex>) —
    roadmap-baton was excluded from the handoff-id-minting doc_type tuple at C1
    (real asymmetry, not a documented exception; see AC13 backfill fix). Omitted
    entirely (not null) when not supplied, matching every other handoff-family
    scaffold's optional-omit convention above.

    Spec backlink: docs/plans/2026-06-29-cli-scaffold-deterministic-docs.md § C3c
    Spec backlink: pln-fleet-deliverable-spine-identity-and-facets-2b331c § D1, D2, C3b
    Spec backlink (handoff_id): docs/plans/2026-08-01-baton-spine-information-integrity.md § A5 (AC13)

    category (--category) is validated against _HANDOFF_CATEGORY_ENUM before the
    frontmatter is written — defaults to 'roadmap' unchanged when not supplied.
    Spec backlink: cross-repo/inbox/2026-07-23-example-cockpit-repo-em-coordinator-doc-new-category-no-validation.md
    """
    today = _today()
    placeholder_summary = "PLACEHOLDER — replace with one-line stub summary (≤140 chars)"
    _dlv = _yaml_quote(deliverable_id) if deliverable_id else "null"
    _ini = _yaml_quote(initiative) if initiative else "null"
    _category = category if category else "roadmap"
    _validate_category(_category)
    lines = [
        "---",
        f"title: {_yaml_quote(title)}",
        f"created: {today}",
        f"branch: {_yaml_quote(branch)}",
        "status: open",
        "predecessor: none",
        "kind: roadmap-baton",
        f"roadmap_id: {_yaml_quote(roadmap_id)}",
        f"stub_id: {_yaml_quote(stub_id)}",
        # authoring_session is path-shaped so /pickup can deterministically Read origin context.
        # Narrowing from the wiki's general "one-line description" to a directory path — roadmap-specific.
        # See skills/roadmap-planning/SKILL.md § Step 2.1, authoring_session field semantics.
        f"authoring_session: {_yaml_quote(f'state/roadmap/{roadmap_id}/')}  # path-shaped; /pickup reads origin context here",
        # Review: code-reviewer — F6: _yaml_quote applied to authoring_session interpolation (matches adjacent quoted fields)
        "workstream: PLACEHOLDER  # replace with roadmap short prefix slug",
        "sprint: 1  # fill from roadmap-number-stubs topo output (Step 2.1.5)",
        "wave: 1    # fill from roadmap-number-stubs topo output (Step 2.1.5)",
        "cost: T1   # T0 trivial | T1 small (<1h) | T2 medium (1-4h) | T3 multi-day",
        "deployment_state: awaiting_gate",
        "blocks: []",
        "blocked_by: []",
        "scope:",
        "  - PLACEHOLDER  # replace with in-scope pathspecs (git pathspec syntax)",
        f"category: {_category}",
        f"summary: {_yaml_quote(placeholder_summary)}",
        f"deliverable_id: {_dlv}",
        f"initiative: {_ini}  # FK to state/initiatives/<id>.yaml; null when no named initiative",
    ]
    if sizing_object:
        if sizing_object == "null":
            lines.append("sizing_object: null")
        else:
            lines.append(f"sizing_object: {_yaml_quote(sizing_object)}")
    # awaiting_gate requires at least one of gate_dependency (deprecated),
    # blocked_by, or blocking_notes (CROSS_FIELD_RULES). An explicit
    # --gate-dependency writes the deprecated field as before; otherwise the
    # stub gets a blocking_notes placeholder — non-dominating scaffolding is
    # not possible here (both fields dominate gate_eval rule 1/1a), but the
    # placeholder at least stops parking the deprecated field by default.
    if gate_dependency:
        lines.append(f"gate_dependency: {_yaml_quote(gate_dependency)}  # deprecated; superseded by blocked_by/blocking_notes")
    else:
        lines.append("blocking_notes: PLACEHOLDER — name the condition gating this baton, or delete this line once blocked_by names it")
    if handoff_id:
        lines.append(f"handoff_id: {_yaml_quote(handoff_id)}")
    lines += [
        "---",
        "",
        f"# {title}",
        "",
        "<!-- One paragraph: why this stub exists as its own session. -->",
        "",
        "## What this covers",
        "",
        "<!-- Origin context, scope. MUST cite state/roadmap/<run-id>/OVERVIEW.md § <cluster-section> -->",
        "<!-- and state/roadmap/<run-id>/research-corpus/<topic-slug>.md files this stub leans on. -->",
        "",
        "## Reference materials (read first)",
        "",
        "<!-- List file paths the picking-up EM will need, each with a one-line annotation. -->",
        "<!-- MUST cite state/roadmap/<run-id>/OVERVIEW.md and relevant research-corpus files. -->",
        "",
        "## Specification",
        "",
        "<!-- Concrete enough that a context-less EM can act. -->",
        "",
        "## Acceptance criteria",
        "",
        "<!-- Binary checklist the picking-up EM gates completion against. -->",
        "<!-- `- [ ]`/`- [x]` checkboxes only — the consumed-handoff completeness -->",
        "<!-- gate counts boxes and reads a prose list as indeterminate. -->",
        "",
        "- [ ] ",
        "",
        "## Recommended next steps for the picking-up EM",
        "",
        "<!-- 3-7 numbered steps, each verifiable. -->",
        "",
        "## Anti-scope",
        "",
        "<!-- Failure modes a context-less EM might hit. Negative scope. -->",
        "",
        "## Soft seams",
        "",
        "<!-- Bulleted enumeration of workstreams/PRs/stubs this stub may overlap with. -->",
        "<!-- Each entry: one line naming peer + overlap nature (file-region, schema-shape, timing). -->",
        "<!-- MAY be empty (single bullet below); MUST be present. -->",
        "<!-- Distinct from frontmatter scope: (HARD pathspec) and blocked_by: (HARD graph edge). -->",
        "<!-- See docs/wiki/spinoff-handoffs.md § Soft-seams discipline. -->",
        "",
        "- None identified at authoring time.",
        "",
        *_require_session_ledger_block(),
        f"<!-- roadmap-baton: {roadmap_id} {stub_id} by roadmap-planning -->",
    ]
    return "\n".join(lines)


def _scaffold_goal_seed(
    title: str,
    branch: str,
    goals: list[str] | None = None,
    gate_dependency: str | None = None,
    handoff_id: str | None = None,
    origin_handoff_id: str | None = None,
    predecessor_id: str | None = None,
    category: str | None = None,
) -> str:
    """Generate validator-clean goal-seed frontmatter + canonical section skeleton.

    Produces a conformant fork (kind: goal-seed) against the handoff schema —
    a deferred vision-slice captured for a future goal-setting invocation
    (coordinator:goal-setting SKILL.md § Step 5b, "pickup-from-goal-seed" entry
    point). Like spinoff/roadmap-seed, this is a PM-directive fork with
    no baton branch-point: predecessor: none, no forked_from (CROSS_FIELD_RULES
    Rule A3a-3, Negative-spec at bin/lib/schema.js:1404).

    goals (origin_goal_id in the emitted frontmatter — schema field name, NOT the
    SKILL's colloquial "goals:") is OPTIONAL for goal-seed: a deferred
    vision-slice may not yet be tagged to a ratified goal (that's the whole point
    of "deferred vision capture, not deferred goal-setting" — SKILL.md § 5b).
    Emitted as an array per Rule C2-2b (bare scalar is validation-illegal);
    omitted entirely (not null) when not supplied, matching handoff_id's
    optional-omit convention.

    deployment_state defaults to awaiting_gate — a vision-slice stub is dormant
    until a PM picks it up via the goal-setting ceremony's second entry point.
    An explicit gate_dependency writes the deprecated single-string gate field
    (C2 of handoff.schema.json); when not supplied the stub instead gets a
    blocking_notes placeholder, which satisfies the same cross-field OR
    (handoff.schema.json § awaiting_gate needs at least one of gate_dependency
    (deprecated), blocked_by, or blocking_notes) without scaffolding the
    deprecated field by default (C1 of
    docs/plans/2026-08-03-gate-dependency-template-emission-spec.md).

    origin_handoff_id/predecessor_id are pure carry-through ID-companions (C2) —
    see _scaffold_handoff's docstring for the full carry-not-mint contract.
    Omitted entirely (not null) when not supplied.

    Spec backlink: docs/plans/2026-07-07-spinoff-provenance-ancestry.md § Field shape
    Spec backlink: coordinator/skills/goal-setting/SKILL.md § Step 5b
    Spec backlink (origin_handoff_id/predecessor_id): cross-repo memo
    2026-07-22-claude-klabauter-em-c2-id-companions (ask 1);
    docs/plans/2026-07-08-lifecycle-vocab-c2-durable-links-rollup.md § C2

    category (--category) is validated against _HANDOFF_CATEGORY_ENUM before the
    frontmatter is written — defaults to 'infra' unchanged when not supplied.
    Spec backlink: cross-repo/inbox/2026-07-23-example-cockpit-repo-em-coordinator-doc-new-category-no-validation.md

    pickup_ready is OMITTED (not scaffolded as true) per the same convention as
    _scaffold_roadmap_baton: absence triggers a non-blocking /pickup warn;
    awaiting_gate + a named gate (blocking_notes or gate_dependency) is the real
    sequencing gate. A deferred vision-slice under awaiting_gate must not also
    advertise pickup-readiness — that pairing is now a CROSS_FIELD_RULES error.
    Spec backlink: cross-repo/inbox/2026-08-06-example-market-data-repo-em-pickup-ready-true-under-unmet-gate.md

    authoring_session (2026-08-21) is resolved off `_resolve_session_id()` when
    the engine can supply it, same resolver `_scaffold_handoff`/`_scaffold_spinoff`
    use for the same field. Unlike `_scaffold_spinoff`, an unresolvable session id
    degrades to the prior hand-typed 'PLACEHOLDER' rather than exiting fail-loud --
    this scaffolder fires from coordinator:goal-setting's Step 5b entry point, an
    invocation context not audited by this fix, so resolve-or-degrade is applied
    as a strict improvement without a new failure mode.
    """
    today = _today()
    placeholder_summary = "PLACEHOLDER — replace with one-line vision-slice summary (≤140 chars)"
    _category = category if category else "infra"
    _validate_category(_category)
    lines = [
        "---",
        f"title: {_yaml_quote(title)}",
        f"created: {today}",
        f"branch: {_yaml_quote(branch)}",
        "status: open",
        "predecessor: none",
        "kind: goal-seed",
        "deployment_state: awaiting_gate",
        f"category: {_category}",
        f"summary: {_yaml_quote(placeholder_summary)}",
    ]
    # 2026-08-21 extension (same baton as _scaffold_spinoff's authoring_session
    # fix): resolved off `_resolve_session_id()` when the engine can supply it,
    # same as every other resolvable-fact seam in this file. Deliberately NOT
    # given the spinoff's fail-loud arm -- goal-seed is minted by
    # coordinator:goal-setting's Step 5b entry point, an invocation context
    # this fix has not audited, so an unresolvable session id keeps the prior
    # degrade (hand-typed PLACEHOLDER) rather than risking a hard exit inside
    # an unverified ceremony.
    _authoring_session_value = _resolve_session_id()
    if _authoring_session_value != "em-unknown":
        _display_name = _resolve_session_display_name()
        if _display_name:
            lines.append(f"# minted by {_display_name}")
        lines.append(f"authoring_session: {_yaml_quote(_authoring_session_value)}")
    else:
        lines.append("authoring_session: PLACEHOLDER")
    lines.append("workstream: PLACEHOLDER")
    # awaiting_gate requires at least one of gate_dependency (deprecated),
    # blocked_by, or blocking_notes (CROSS_FIELD_RULES). An explicit
    # --gate-dependency writes the deprecated field as before; otherwise the
    # stub gets a blocking_notes placeholder instead of defaulting the
    # deprecated field.
    if gate_dependency:
        lines.append(f"gate_dependency: {_yaml_quote(gate_dependency)}  # deprecated; superseded by blocked_by/blocking_notes")
    else:
        lines.append("blocking_notes: PLACEHOLDER — name the condition gating this baton, or delete this line once blocked_by names it")
    if goals:
        lines.append("origin_goal_id:")
        lines.extend(f"  - {_yaml_quote(g)}" for g in goals)
    if handoff_id:
        lines.append(f"handoff_id: {_yaml_quote(handoff_id)}")
    if origin_handoff_id:
        lines.append(f"origin_handoff_id: {_yaml_quote(origin_handoff_id)}")
    if predecessor_id:
        lines.append(f"predecessor_id: {_yaml_quote(predecessor_id)}")
    lines.extend([
        "---",
        "",
        "## What this covers",
        "",
        "<!-- Capture the deferred vision-slice verbatim. Raw is fine — fidelity matters more than polish. -->",
        "",
        "## Reference materials (read first)",
        "",
        "<!-- List file paths the picking-up EM/goal-setting session will need. -->",
        "",
        "## Specification",
        "",
        "<!-- The vision-slice as stated by the PM. Not yet ratified into OKR form. -->",
        "",
        "## Acceptance criteria",
        "",
        "<!-- Filled at pickup, when this feeds a future goal-setting ceremony. -->",
        "<!-- `- [ ]`/`- [x]` checkboxes only — the consumed-handoff completeness -->",
        "<!-- gate counts boxes and reads a prose list as indeterminate. -->",
        "",
        "- [ ] ",
        "",
        "## Recommended next steps for the picking-up EM",
        "",
        "<!-- Typically: re-invoke coordinator:goal-setting (pickup-from-goal-seed entry point). -->",
        "",
        "## Anti-scope",
        "",
        "<!-- This stub does NOT auto-flesh into a goal — PM re-entry via goal-setting is required. -->",
        "",
        *_require_session_ledger_block(),
    ])
    return "\n".join(lines)


def _scaffold_roadmap_seed(
    title: str,
    branch: str,
    goals: list[str] | None = None,
    gate_dependency: str | None = None,
    deliverable_id: str | None = None,
    initiative: str | None = None,
    handoff_id: str | None = None,
    origin_handoff_id: str | None = None,
    predecessor_id: str | None = None,
    category: str | None = None,
) -> str:
    """Generate validator-clean roadmap-seed frontmatter + section skeleton.

    Produces a conformant fork (kind: roadmap-seed) against the handoff
    schema — the session that will produce roadmap stubs (kind: roadmap-baton)
    against an already-ratified goal (coordinator:goal-setting SKILL.md § Step 5a).
    Distinct from roadmap-baton (kind: roadmap-baton) itself: the -creator kind
    is the PM-gated baton that FIRES a future coordinator:roadmap-planning
    invocation; it does NOT carry the roadmap's graph-primitive fields (sprint,
    wave, blocks, blocked_by) — CROSS_FIELD_RULES rejects graph primitives on
    roadmap-seed (bin/lib/schema.js:1102-1105, negative-spec).

    Like spinoff/goal-seed, this is a PM-directive fork with no baton
    branch-point: predecessor: none, no forked_from (Rule A3a-3).

    goals (origin_goal_id in the emitted frontmatter — schema field name; the
    SKILL's "goals:" FK is the same concept, different vocabulary) is the FK to
    the goal artifact ratified in Step 4 — SKILL.md § 5a requires every
    roadmap-seed stub to carry this FK, so unlike goal-seed, an
    empty goals list here is a SKILL-process gap, not a valid deferred state.
    Emitted as an array per Rule C2-2b; caller (goal-setting ceremony) supplies it.

    deployment_state defaults to awaiting_gate (PM fire required). An explicit
    gate_dependency writes the deprecated single-string gate field (C2 of
    handoff.schema.json); when not supplied the stub instead gets a
    blocking_notes placeholder, which satisfies the same cross-field OR
    (handoff.schema.json § awaiting_gate needs at least one of gate_dependency
    (deprecated), blocked_by, or blocking_notes) without scaffolding the
    deprecated field by default (C1 of
    docs/plans/2026-08-03-gate-dependency-template-emission-spec.md).

    origin_handoff_id/predecessor_id are pure carry-through ID-companions (C2) —
    see _scaffold_handoff's docstring for the full carry-not-mint contract.
    Omitted entirely (not null) when not supplied.

    Spec backlink: docs/plans/2026-07-07-spinoff-provenance-ancestry.md § Field shape
    Spec backlink: coordinator/skills/goal-setting/SKILL.md § Step 5a
    Spec backlink (origin_handoff_id/predecessor_id): cross-repo memo
    2026-07-22-claude-klabauter-em-c2-id-companions (ask 1);
    docs/plans/2026-07-08-lifecycle-vocab-c2-durable-links-rollup.md § C2

    category (--category) is validated against _HANDOFF_CATEGORY_ENUM before the
    frontmatter is written — defaults to 'roadmap' unchanged when not supplied.
    Spec backlink: cross-repo/inbox/2026-07-23-example-cockpit-repo-em-coordinator-doc-new-category-no-validation.md

    pickup_ready is OMITTED (not scaffolded as true) per the same convention as
    _scaffold_roadmap_baton: absence triggers a non-blocking /pickup warn;
    awaiting_gate + a named gate (blocking_notes or gate_dependency) is the real
    sequencing gate. A roadmap-seed under awaiting_gate must not also advertise
    pickup-readiness — that pairing is now a CROSS_FIELD_RULES error.
    Spec backlink: cross-repo/inbox/2026-08-06-example-market-data-repo-em-pickup-ready-true-under-unmet-gate.md

    authoring_session (2026-08-21) is resolved off `_resolve_session_id()` when
    the engine can supply it, same resolver `_scaffold_handoff`/`_scaffold_spinoff`
    use for the same field. Unlike `_scaffold_spinoff`, an unresolvable session id
    degrades to the prior hand-typed 'PLACEHOLDER' rather than exiting fail-loud --
    this scaffolder fires from coordinator:goal-setting's Step 5a entry point, an
    invocation context not audited by this fix, so resolve-or-degrade is applied
    as a strict improvement without a new failure mode. `workstream` stays a
    hand-typed placeholder (operator-chosen roadmap slug), unaffected by this fix.
    """
    today = _today()
    placeholder_summary = "PLACEHOLDER — replace with one-line capability-arc summary (≤140 chars)"
    _dlv = _yaml_quote(deliverable_id) if deliverable_id else "null"
    _ini = _yaml_quote(initiative) if initiative else "null"
    _category = category if category else "roadmap"
    _validate_category(_category)
    lines = [
        "---",
        f"title: {_yaml_quote(title)}",
        f"created: {today}",
        f"branch: {_yaml_quote(branch)}",
        "status: open",
        "predecessor: none",
        "kind: roadmap-seed",
        "deployment_state: awaiting_gate",
        f"category: {_category}",
        f"summary: {_yaml_quote(placeholder_summary)}",
    ]
    # 2026-08-21 extension (same baton as _scaffold_spinoff's authoring_session
    # fix): resolved off `_resolve_session_id()` when the engine can supply it.
    # Deliberately NOT given the spinoff's fail-loud arm -- roadmap-seed is
    # minted by coordinator:goal-setting's Step 5a entry point, an invocation
    # context this fix has not audited, so an unresolvable session id keeps
    # the prior degrade (hand-typed PLACEHOLDER) rather than risking a hard
    # exit inside an unverified ceremony. `workstream` here is left as an
    # operator-typed placeholder on purpose -- "replace with roadmap short
    # prefix slug" is an operator choice, not an engine-resolvable fact
    # (matching _scaffold_roadmap_baton's identical field).
    _authoring_session_value = _resolve_session_id()
    if _authoring_session_value != "em-unknown":
        _display_name = _resolve_session_display_name()
        if _display_name:
            lines.append(f"# minted by {_display_name}")
        lines.append(f"authoring_session: {_yaml_quote(_authoring_session_value)}")
    else:
        lines.append("authoring_session: PLACEHOLDER")
    lines.extend([
        "workstream: PLACEHOLDER  # replace with roadmap short prefix slug",
        f"deliverable_id: {_dlv}",
        f"initiative: {_ini}  # FK to state/initiatives/<id>.yaml; null when no named initiative",
    ])
    # awaiting_gate requires at least one of gate_dependency (deprecated),
    # blocked_by, or blocking_notes (CROSS_FIELD_RULES). An explicit
    # --gate-dependency writes the deprecated field as before; otherwise the
    # stub gets a blocking_notes placeholder instead of defaulting the
    # deprecated field.
    if gate_dependency:
        lines.append(f"gate_dependency: {_yaml_quote(gate_dependency)}  # deprecated; superseded by blocked_by/blocking_notes")
    else:
        lines.append("blocking_notes: PLACEHOLDER — name the condition gating this baton, or delete this line once blocked_by names it")
    if goals:
        lines.append("origin_goal_id:")
        lines.extend(f"  - {_yaml_quote(g)}" for g in goals)
    if handoff_id:
        lines.append(f"handoff_id: {_yaml_quote(handoff_id)}")
    if origin_handoff_id:
        lines.append(f"origin_handoff_id: {_yaml_quote(origin_handoff_id)}")
    if predecessor_id:
        lines.append(f"predecessor_id: {_yaml_quote(predecessor_id)}")
    lines.extend([
        "---",
        "",
        "## What this covers",
        "",
        "<!-- One paragraph: the roadmap-worth-of-work boundary this stub scaffolds — -->",
        "<!-- one coherent domain/capability arc, one /roadmap-planning invocation. -->",
        "",
        "## Reference materials (read first)",
        "",
        "<!-- Cite the goal artifact (state/goals/<id>.yaml) this stub is tagged to. -->",
        "",
        "## Specification",
        "",
        "<!-- Concrete enough that a context-less EM can fire coordinator:roadmap-planning. -->",
        "",
        "## Acceptance criteria",
        "",
        "<!-- Checklist the picking-up EM gates completion against. -->",
        "<!-- `- [ ]`/`- [x]` checkboxes only — the consumed-handoff completeness -->",
        "<!-- gate counts boxes and reads a prose list as indeterminate. -->",
        "",
        "- [ ] ",
        "",
        "## Recommended next steps for the picking-up EM",
        "",
        "<!-- Typically: invoke coordinator:roadmap-planning against the goal + this stub's scope. -->",
        "",
        "## Anti-scope",
        "",
        "<!-- This stub does NOT author the roadmap plan itself — roadmap-planning owns that. -->",
        "",
        *_require_session_ledger_block(),
    ])
    return "\n".join(lines)


def _scaffold_memo(title: str, to: str, topic: str, from_id: str) -> str:
    """Generate validator-clean memo frontmatter + placeholder body.

    Uses memo_compose.compose_frontmatter (the shared lib) to emit the
    frontmatter block so both this scaffolder and cross-repo-memo use one
    source of truth for memo frontmatter grammar.

    The memo body is a placeholder — the EM fills it via Edit before sending.
    Sending is done via cross-repo-memo (NOT this scaffolder).

    Negative-spec: does NOT route, deliver, or apply claim-locks. This is a
    LOCAL skeleton only. All delivery surfaces stay in bin/cross-repo-memo.
    """
    placeholder_body = (
        "<!-- Replace with the memo body. -->\n"
        "<!-- Send when ready: cross-repo-memo send {topic}   (drafted to {to}) -->\n".format(
            to=to, topic=topic
        )
    )
    # compose_memo derives summary from the first non-empty body line when summary=None.
    # The placeholder body starts with an HTML comment (stripped → empty by derive_summary).
    # Provide an explicit summary so the frontmatter is non-empty and validator-clean.
    # Review: code-reviewer S3-F3 — body= was previously dead when summary is set (compose_frontmatter
    # only calls _derive_summary when summary=None); switching to compose_memo (full-doc composer)
    # removes the manual frontmatter+body concat and eliminates the dead parameter entirely.
    explicit_summary = title[:_SUMMARY_MAX_CHARS]
    return _memo_compose(
        from_id=from_id,
        title=title,
        to=to,
        topic=topic,
        body=placeholder_body,
        summary=explicit_summary,
    )


def _scaffold_plan(
    title: str,
    branch: str,
    author: str,
    plan_id: str | None = None,
    deliverable_id: str | None = None,
    initiative: str | None = None,
    sizing_object: str | None = None,
    problem_set: str | None = None,
) -> str:
    """Generate validator-clean plan frontmatter + canonical section skeleton.

    Produces a conformant plan against schemas/plan.yaml: required title/created/
    author/status:draft + commented skeleton of promoted optional keys + the
    canonical four-section body (## Problem / ## Acceptance Criteria /
    ## Anti-scope / ## Out of scope as DISTINCT sections per D2).

    plan_id is minted fresh (pln-<slug>-<6hex>) — always present, never null (D3).
    deliverable_id is auto-inherited from DELIVERABLE_ID env var or minted fresh
    when no parent id is discoverable from session context (D1).
    initiative is D9 present-as-null (null when this plan has no named initiative).
    sizing_object, when supplied, is emitted as a real frontmatter key (its
    on-disk resolution is asserted by the caller before this function runs —
    see main()'s --sizing-object validation block). When omitted, the existing
    commented-optional-key skeleton is left unchanged (no behavior change).

    problem_set, when supplied, is emitted as a real frontmatter key (a ratified
    problem-set slug, or the literal 'inline') instead of the commented
    `# problem_set: inline` template line — the DoE census's requested bind to
    the generic insert_fm_field-plus-a-key shape; no new named op required.
    When omitted, the existing commented-optional-key skeleton is left
    unchanged (no behavior change). Unlike sizing_object this is never
    required — a plan with no ratified problem set simply leaves the
    placeholder commented.

    Spec backlink: docs/plans/2026-06-25-example-initiative-tc-1-records-consolidation.md § C5
    Spec backlink: pln-fleet-deliverable-spine-identity-and-facets-2b331c § D1, D3, C3b
    Spec backlink: pln-plan-sizing-citation-gate-scaf-45eaed § AC2
    Spec backlink: docs/plans/2026-08-21-engine-half-of-the-roadmap-sprint-spine-split.md § C7
    """
    today = _today()
    _pid = _yaml_quote(plan_id) if plan_id else "null"
    _dlv = _yaml_quote(deliverable_id) if deliverable_id else "null"
    _ini = _yaml_quote(initiative) if initiative else "null"
    _author_line = (
        f"author: {author}  # replace with actual author"
        if author == "unknown-sender-em"
        else f"author: {author}"
    )
    lines = [
        "---",
        f"title: {_yaml_quote(title)}",
        f"created: {today}",
        _author_line,
        "status: draft",
        f"branch: {_yaml_quote(branch)}",
        f"plan_id: {_pid}",
        f"deliverable_id: {_dlv}",
        f"initiative: {_ini}  # FK to state/initiatives/<id>.yaml; null when no named initiative",
    ]
    if sizing_object:
        # Real key, only when supplied — the caller (main()) has already
        # asserted this path resolves on disk (AC3), or is threading the
        # literal string "null" for --no-sizing-object (sizing-citation-
        # absence-is-checkable § C1, AC2). The literal null is emitted
        # UNQUOTED so it parses as YAML null, not the string "null" —
        # _yaml_quote always double-quotes, which would otherwise turn the
        # sanctioned absence-declaration into a dangling-looking citation
        # the sweep can't distinguish from a real (wrong) path.
        if sizing_object == "null":
            lines.append("sizing_object: null")
        else:
            lines.append(f"sizing_object: {_yaml_quote(sizing_object)}")
    lines += [
        "# Optional keys — uncomment and fill as needed (promoted de-facto keys, D1):",
        "# scope_mode: additive-only         # planning posture",
    ]
    if problem_set:
        # Real key, only when supplied — mirrors the sizing_object arm above.
        # No absence-declaration sentinel exists for this field (unlike
        # sizing_object's "null" convention): problem_set is genuinely
        # optional, so an unsupplied value simply leaves the commented
        # template line in place rather than emitting a stamped null.
        lines.append(f"problem_set: {_yaml_quote(problem_set)}  # ratified problem-set slug or 'inline'")
    else:
        lines.append("# problem_set: inline               # ratified problem-set slug or 'inline'")
    lines += [
        "# predecessor_handoff: state/handoffs/YYYY-MM-DD-<slug>.md",
        "# prerequisite_of: docs/plans/YYYY-MM-DD-<slug>.md",
        "# source_memo: YYYY-MM-DD-<topic>.md",
        "# review_signals:                   # reviewer routing; ids from coordinator/contract/review-signals.json",
        "#   - architecture                  # absent = positive claim: no specialist surface in play",
        "# scope:",
        "#   - path/or/item/one",
        "#   - path/or/item/two",
        "---",
        "",
        f"# {title}",
        "",
        "## Problem",
        "",
        "<!-- State the problem this plan solves. -->",
        "",
        "## Acceptance Criteria",
        "",
        "<!-- Checklist or table the EM gates completion against. -->",
        "",
        "## Anti-scope",
        "",
        "<!-- Failure modes / pitfalls a context-less EM might hit. Negative scope. -->",
        "<!-- Distinct from 'Out of scope' — see canonical-artifact-shapes.md § D2. -->",
        "",
        "## Out of scope",
        "",
        "<!-- Adjacent work explicitly excluded from this plan's deliverables. -->",
        "",
        "## Tasks",
        "",
        "<!-- Machine-parseable task spine — the EM edits row values in place; the structure",
        "     below is a lay-up, not a from-scratch authoring task. Exactly ONE fenced",
        "     `yaml plan-tasks` block belongs directly under this heading (parser-locate",
        "     rule — zero or >1 blocks is a defined error). Each list item validates against",
        "     schemas/plan-tasks.schema.json. Delete the two sample rows below and replace with",
        "     real chunks; keep at least the shape (id/title/change_kind/surface/writes required",
        "     on every non-deferred row — dispatch.emit cannot fire without writes:. The two",
        "     empty forms are NOT interchangeable: `writes: []` claims this row writes NOTHING,",
        "     while an ABSENT writes: key means 'unknown', which forces wave separation. Omit the",
        "     key ONLY on a row gated epistemic-premise, whose surface a predecessor names).",
        "     KEEP THE CLOSING ``` FENCE when you replace the rows: `locate_fenced_block` matches",
        "     an OPEN-and-CLOSED pair, so a dropped closing fence reads as ABSENT — the spine is",
        "     visibly there and every plan-tasks CLI refuses it with 'task spine is absent'.",
        "     change_kind enum SSOT: docs/wiki/lessons-outbox-schema.md § Change-kind enum.",
        "     Full authoring contract: docs/wiki/writing-plans.md § Machine-Parseable Task Spine. -->",
        "",
        "```yaml plan-tasks",
        "- id: C1",
        "  title: PLACEHOLDER — one-line brief for the first shipped chunk",
        "  change_kind: script-edit  # replace with the actual change kind for this row",
        "  surface: path/to/primary/target  # single path or subsystem, not the full write-files set",
        "  writes: [path/to/file/this/chunk/writes.py]  # REQUIRED on a non-deferred row —",
        "              # dispatch.emit cannot fire without it. Replace with the real repo-relative",
        "              # paths this chunk writes. An empty `writes: []` is a POSITIVE claim that",
        "              # it writes nothing — NOT 'not known yet'. If the surface is not knowable,",
        "              # omit this key entirely (UNDECLARED), which is legal only on a row gated",
        "              # epistemic-premise; see spine_read's AC2 for why they differ.",
        "  # depends_on:",
        "  #   - chunk: C0  # predecessor row's id — SCHEMA-CORRECT object form only, never a bare id",
        "  #     gate_kind: output-consumption-runtime  # or epistemic-premise — the only two writable kinds",
        "  #     note: one-line rationale for the edge",
        "  queue_scope: project  # project (default) | central",
        "  disposition: open  # open (default) | coded | spun_off | backlogged | wont_do",
        "  # case_against: >",
        "  #   Required when disposition is backlogged or wont_do (not spun_off — nothing",
        "  #   leaves the corpus there). The strongest HONEST case for doing this work now,",
        "  #   plus the EM's recommendation, confidence, and what would change it — not a",
        "  #   token counter-argument to satisfy the schema.",
        "  body: |",
        "    Optional multi-line detail. Delete this key if not needed.",
        "- id: C2",
        "  title: PLACEHOLDER — one-line brief for the second shipped chunk",
        "  change_kind: doc-edit  # replace with the actual change kind for this row",
        "  surface: path/to/secondary/target",
        "  writes: [path/to/another/file/this/chunk/writes.py]  # REQUIRED — see C1's writes: comment",
        "  queue_scope: project",
        "  disposition: open",
        "  body: |",
        "    Optional multi-line detail.",
        "```",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Reverse write-back — plan -> sizing (C4, plan
# 2026-08-10-sizing-objects-join-the-deliverable-spine.md § C4)
# ---------------------------------------------------------------------------

_SIZING_REVERSE_STATUS = "routed"
"""The live-set status value C4 writes at plan-CREATION time.

Deliberately NOT the cascade's terminal value (`shipped`, written by
`deliverable.cascade_terminal` / C3 at plan-IMPLEMENTED time) — this chunk is
a SECOND writer to the same field, and reusing the terminal value here would
exclude every freshly-plan-linked sizing from the cascade's live-candidate
scan the moment its plan is created (silent `candidates_matched: 0`, the
exact failure mode this plan exists to remove). `routed` is already a member
of `sizing-object.schema.json`'s `status` enum (`route chosen and handed
off`), already in the kind's live set (the terminal set is `{shipped}`
alone), and describes exactly this moment: a plan now exists for the route
this sizing chose.
"""

# Review: staff-eng — Finding 6: the terminal-status guard's own vocabulary.
# Kept as this file's local mirror of
# `coordinator_core.ops.deliverable_cascade._SIZING_TERMINAL_STATUS` — not
# imported directly because that module self-registers
# "deliverable.cascade_terminal" against the JSON-RPC op registry as an
# import-time side effect (`register_op` at module scope), which this
# lightweight CLI must not trigger just to read one frozenset. The coupling
# is made mechanical instead of conventional by
# `coordinator_core/ops/tests/test_sizing_terminal_status_mirror_sync.py`,
# which asserts this set equals the engine's — the next divergence fails a
# test rather than opening a silent guard hole (see Review: coordinator:
# code-reviewer — Finding 5, which found the two sets exactly out of sync
# for `declined`).
_SIZING_TERMINAL_STATUSES = frozenset({"shipped", "declined"})


def _mutate_sizing_reverse_edge(old_text: str, plan_repo_rel_path: str) -> str:
    """Return sizing-object YAML text with `plan:` and `status:` set.

    Whole-document-YAML (no frontmatter fence) — same shape `_scaffold_sizing`
    emits. Line-level regex substitution (replace an existing `status:`/
    `plan:` line in place, else append a new one) rather than a full
    load+dump: this file is hand-authored prose-adjacent YAML (comments,
    the sizing skill's own formatting), and a parse/re-dump round-trip would
    silently drop both, exactly the failure class this repo's `sizing-
    object.schema.json` vendoring note calls out for schema files (STRUCTURAL
    MERGE, NOT A BYTE COPY) — the same discipline applies to instance data.

    `status:` is forced to `_SIZING_REVERSE_STATUS`, UNLESS the sizing's
    existing `status:` is already terminal (`shipped`) — see the guard below
    (Review: staff-eng — Finding 6: a scaffold against an already-shipped
    sizing must not silently re-route/un-ship it). Otherwise this is the
    plan-creation writer's own value, independent of whatever non-terminal
    value the sizing already carried (draft/sized/routed), matching a plan
    now existing for the route this sizing chose. `plan:` is set/overwritten
    to `plan_repo_rel_path` (repo-root-relative, POSIX-normalized, matching
    the schema's `^docs/plans/.+\\.md$` pattern) — UNLESS the sizing already
    carries a different, non-null `plan:` value, in which case this is a
    re-route rather than a first routing and raises ``MutateAbort`` (caller
    translates to a clean CLI error) rather than silently overwriting the
    existing FK. A `plan:` value byte-identical to `plan_repo_rel_path` is
    treated as idempotent, not a clobber (re-running the same scaffold).

    Review: staff-eng — Findings 2/3: this used to hand-roll its own
    `re.search`/`re.sub` line surgery instead of composing
    `coordinator_core.frontmatter.primitives` — the exact defect class that
    module's own docstring names ("three hand-copies ... each independently
    reproduced the corruption"). Two concrete corruptions this closes: (a)
    the old `\\s*`-based `plan:` read walked past a present-but-empty
    `plan:` line's own newline and captured the FOLLOWING line's text as the
    "existing FK" — `read_fm_field_unquoted` uses the primitives' own
    negative-spec'd `[ \\t]`-only padding, never `\\s`; (b) the old
    `re.MULTILINE` `re.sub(r"(?m)^status:.*$", ...)` consumed a CRLF
    document's trailing `\\r` on the rewritten line without re-emitting it,
    leaving the file with MIXED line endings —
    `replace_fm_field_raw`/`insert_fm_field_raw` re-emit/adopt the document's
    own EOL, so this can no longer happen. `plan:`'s own quoting stays this
    file's `_yaml_quote` convention (always double-quoted) rather than
    `serialize_yaml_scalar`'s bare-unless-structural rule, matching this
    reverse edge's own pre-existing on-disk shape and this suite's fixtures —
    both the replace branch (`replace_fm_field_raw`) and the insert branch
    (`insert_fm_field_raw`) take the pre-quoted `_plan_raw` value, so neither
    branch can diverge from the other's quoting.

    Review: coordinator:code-reviewer — the insert branch used to call
    `insert_fm_field` with the raw unquoted path, which serializes via
    `serialize_yaml_scalar`'s bare-unless-structural rule and left a
    first-time scaffold's `plan:` unquoted while a re-run (replace branch)
    was double-quoted — the docstring's always-double-quoted claim was false
    on that branch. `insert_fm_field_raw` (added to the primitives module,
    mirroring `replace_fm_field_raw`) closes the gap.
    """
    from coordinator_core.frontmatter.primitives import (  # noqa: PLC0415
        insert_fm_field_raw,
        read_fm_field_unquoted,
        replace_fm_field_raw,
    )
    from coordinator_core.locked_write import MutateAbort as _MutateAbort  # noqa: PLC0415

    _existing_plan_value = read_fm_field_unquoted(old_text, "plan")
    if _existing_plan_value and _existing_plan_value != "null" and _existing_plan_value != plan_repo_rel_path:
        raise _MutateAbort(
            f"sizing object already cites plan '{_existing_plan_value}' — "
            f"refusing to overwrite with '{plan_repo_rel_path}'. This is a "
            "re-route, not a first routing; resolve the conflict by hand "
            "before re-running with --sizing-object."
        )

    # Review: staff-eng — Finding 6: refuse (rather than silently un-ship)
    # when the sizing's own status is already terminal.
    _existing_status_value = read_fm_field_unquoted(old_text, "status")
    if _existing_status_value in _SIZING_TERMINAL_STATUSES:
        raise _MutateAbort(
            f"sizing object status is already '{_existing_status_value}' "
            "(terminal) — refusing to re-route a shipped sizing back to "
            f"'{_SIZING_REVERSE_STATUS}'. Resolve by hand before re-running "
            "with --sizing-object."
        )

    new_text = replace_fm_field_raw(old_text, "status", _SIZING_REVERSE_STATUS)
    if read_fm_field_unquoted(new_text, "status") is None:
        new_text = insert_fm_field_raw(new_text, "status", _SIZING_REVERSE_STATUS)

    _plan_raw = _yaml_quote(plan_repo_rel_path)
    if read_fm_field_unquoted(new_text, "plan") is not None:
        new_text = replace_fm_field_raw(new_text, "plan", _plan_raw)
    else:
        new_text = insert_fm_field_raw(new_text, "plan", _plan_raw, "status")

    # Review: staff-eng — Finding 10: validate the mutated document against
    # the vendored sizing schema before returning, rather than trusting the
    # text surgery blind — a `plan:` value the schema's
    # `^docs/plans/.+\.md$` pattern rejects must abort here, not land on
    # disk and be discovered by a later reader.
    import yaml as _yaml  # noqa: PLC0415
    from pathlib import Path as _ValidatePath  # noqa: PLC0415
    from coordinator_core.frontmatter.schema_validate import (  # noqa: PLC0415
        format_validation_errors as _format_validation_errors,
        validate_frontmatter as _validate_frontmatter,
    )

    try:
        _parsed = _yaml.safe_load(new_text) or {}
    except Exception as _exc:  # noqa: BLE001
        raise _MutateAbort(f"sizing reverse edge: post-mutation YAML parse failed: {_exc}") from _exc
    _schema_path = (
        _ValidatePath(__file__).resolve().parent.parent.parent
        / "coordinator_core" / "frontmatter" / "schemas" / "sizing-object.schema.json"
    )
    _errors = _validate_frontmatter(_parsed, _schema_path)
    if _errors:
        raise _MutateAbort(
            "sizing reverse edge: post-mutation schema validation failed: "
            f"{_format_validation_errors(_errors)}"
        )
    return new_text


def _write_sizing_reverse_edge(
    sizing_abs_path: str, plan_repo_rel_path: str, repo_root: str,
) -> str:
    """Write the plan->sizing reverse edge under a cross-process file lock.

    Uses ``coordinator_core.locked_write.locked_rmw`` (the same primitive
    ``deliverable_cascade``'s write side uses) so a concurrent sizing-side
    writer cannot interleave with this write. Returns the PRE-MUTATION text
    (not the new text) so the caller can revert via
    ``_revert_sizing_reverse_edge`` if the subsequent plan-file write fails —
    this is the write-order + revert-on-failure mechanism AC7 requires to be
    named explicitly (see main()'s call site for the ordering and the revert
    call). Raises whatever ``locked_rmw`` raises (LockTimeout, OSError) —
    this write is NOT best-effort/degrade-to-skip like this file's other
    engine-touching helpers, because a silently-skipped reverse edge is
    exactly the hand-maintained-link status quo this chunk exists to close.
    """
    _ensure_engine_on_path()
    from pathlib import Path as _Path  # noqa: PLC0415
    from coordinator_core.locked_write import locked_rmw as _locked_rmw  # noqa: PLC0415

    _captured: dict[str, str] = {}

    def _mutate(old_text: str) -> str:
        _captured["old_text"] = old_text
        return _mutate_sizing_reverse_edge(old_text, plan_repo_rel_path)

    _locked_rmw(_Path(sizing_abs_path), _mutate, repo_root=_Path(repo_root))
    return _captured.get("old_text", "")


def _revert_sizing_reverse_edge(
    sizing_abs_path: str, old_text: str, repo_root: str,
) -> None:
    """Restore ``sizing_abs_path`` to ``old_text``, best-effort.

    Called only from the plan-write failure path (see main()): the sizing
    reverse edge already landed on disk, the plan file did not, and this
    restores the sizing to its pre-mutation content so a half-written pair
    never survives a failed scaffold. Best-effort (swallows its own
    exceptions) — a revert failure must surface the ORIGINAL plan-write
    error, not mask it with a new one; the caller's own error message names
    the sizing path so an operator can restore it by hand if this also fails.
    """
    try:
        _ensure_engine_on_path()
        from pathlib import Path as _Path  # noqa: PLC0415
        from coordinator_core.locked_write import locked_rmw as _locked_rmw  # noqa: PLC0415

        _locked_rmw(_Path(sizing_abs_path), lambda _old: old_text, repo_root=_Path(repo_root))
    except Exception:  # noqa: BLE001 -- best-effort revert; original error takes priority
        pass


def _scaffold_decision(title: str, dr_id: str) -> str:
    """Generate validator-clean decision frontmatter + canonical section skeleton.

    Produces a conformant decision against schemas/decision.yaml: required
    title/created/status:proposed/deciders (placeholder list) + a real, collision-
    checked `id:` allocated by `_allocate_dr_number` (never a `DR-XXX` placeholder —
    see the collision memo backlink below for why the placeholder scheme was
    retired). Uses canonical `created` (NOT `date` — see D4). Canonical four-section
    body.

    Spec backlink: docs/plans/2026-06-25-example-initiative-tc-1-records-consolidation.md § C5, D3, D4
    Spec backlink: cross-repo/inbox/2026-07-20-example-game-repo-em-dr-number-allocator-collision.md
    """
    today = _today()
    lines = [
        "---",
        f"title: {_yaml_quote(title)}",
        f"created: {today}",
        "status: proposed",
        f"id: {dr_id}",
        "deciders:",
        "  - PLACEHOLDER  # replace with decision-maker names",
        "---",
        "",
        f"# {title}",
        "",
        "## Problem",
        "",
        "<!-- What problem does this decision solve? -->",
        "",
        "## Decision",
        "",
        "<!-- The chosen approach and rationale. -->",
        "",
        "## Alternatives Considered",
        "",
        "<!-- Alternatives that were evaluated and why they were rejected. -->",
        "",
        "## Implementation",
        "",
        "<!-- How this decision is implemented. Links to plans, commits, or code. -->",
        "",
    ]
    return "\n".join(lines)


def _scaffold_audit_record(title: str, system: str) -> str:
    """Generate validator-clean audit-record frontmatter + canonical section skeleton.

    Emits the D1 field set from tc-3: run_id (YYYY-MM-DD-HHhMM placeholder stamped
    at scaffold time), system (from --system), grade/health_status as TODO placeholders
    the reviewer fills, reviewer placeholder, created (today). Optional mode field is
    emitted as a commented-out line so the reviewer can uncomment and fill it without
    adding a bare key.

    Canonical body section order (this scaffolder is the SSOT for the section grammar;
    C3's reviewer prompt MUST reference this scaffolder or canonical-artifact-shapes.md
    § Diagram (ASCII) Rule, not independently restate the list):

        ## 1. System Health Grade
        ## 2. Convergent Findings
        ### Diagram (ASCII)  — fenced code block; format rule per canonical-artifact-shapes.md § Diagram (ASCII) Rule (:301)
        ## Verified Findings Slate
        ## Grade Rationale
        ## Suggested Spinoff Groupings
        ## Ambition Check

    Spec backlink: docs/plans/2026-06-25-example-initiative-tc-3-expressive-audit-canonical-shape.md § C2, D1, D3
    """
    today = _today()
    # run_id placeholder: YYYY-MM-DD-HHhMM (reviewer replaces with the actual run timestamp).
    run_id_placeholder = f"{today}-HHhMM"
    lines = [
        "---",
        f"run_id: {run_id_placeholder}  # replace with actual run timestamp (YYYY-MM-DD-HHhMM)",
        f"system: {_yaml_quote(system)}",
        "grade: TODO  # fill: A | B | C | D | E | F",
        "health_status: TODO  # fill: HEALTHY | WATCH | ACTION | CRITICAL",
        "reviewer: PLACEHOLDER  # replace with reviewer identity",
        f"created: {today}",
        "# mode: RESEARCH_ONLY | FULL | REMEDIATION  # optional — uncomment and fill if relevant",
        "---",
        "",
        f"# {title}",
        "",
        "## 1. System Health Grade",
        "",
        "<!-- Overall grade + one-line rationale. The reviewer fills this first. -->",
        "",
        "## 2. Convergent Findings",
        "",
        "<!-- Findings that emerged from multiple independent signal sources. -->",
        "",
        "### Diagram (ASCII)",
        "",
        "<!-- Format and ≤100-char line rule: canonical-artifact-shapes.md § Diagram (ASCII) Rule (:301) -->",
        "```",
        "(ASCII diagram — reviewer fills this per canonical-artifact-shapes.md § Diagram (ASCII) Rule)",
        "```",
        "",
        "## Verified Findings Slate",
        "",
        "| # | Finding | Severity | Evidence | Spinoff candidate? |",
        "|----|---------|----------|----------|--------------------|",
        "",
        "## Grade Rationale",
        "",
        "<!-- Rationale for the grade: what moved it up or down from a B baseline. -->",
        "",
        "## Suggested Spinoff Groupings",
        "",
        "<!-- Cluster findings into candidate spinoffs for follow-on work. -->",
        "",
        "## Ambition Check",
        "",
        "<!-- Is the audit scope well-matched to the system's current risk and complexity? -->",
        "",
    ]
    return "\n".join(lines)


def _scaffold_problem_set(title: str) -> str:
    """Generate validator-clean problem-set frontmatter + canonical section skeleton.

    Emits the problem-set schema fields: title (required) + status: draft (required,
    NOT ratified — a freshly-scaffolded problem-set is unratified; skills/shape/SKILL.md
    flips it to ratified and stamps the > Ratified by PM … marker on PM convergence).
    date is emitted as today. kind: problem-set is included for kind-first schema matching.
    ratified_by and ratified_date are emitted as commented hints only — they carry a
    format: date constraint in the schema so PLACEHOLDER strings would fail validation;
    the body-filler uncomments and fills them on ratification.

    Canonical body sections (matches skills/shape/SKILL.md § The problem-set artifact):
        > Ratified by PM <name> <date>. Frozen before any solution. …  (integrity marker)
        ## Problems
        ## Out of scope (architectural reasons)

    Spec backlink: docs/plans/2026-06-29-cli-scaffold-deterministic-docs.md § C3a
    """
    today = _today()
    lines = [
        "---",
        f"title: {_yaml_quote(title)}",
        f"date: {today}",
        "status: draft",
        "kind: problem-set",
        "# estimated_horizon: session  # fill at ratification: session | week | initiative",
        "# ratified_by: PLACEHOLDER  # fill on PM ratification",
        "# ratified_date: PLACEHOLDER  # fill on PM ratification (YYYY-MM-DD)",
        "---",
        "",
        f"# {title}",
        "",
        "> Ratified by PM <name> <date>. Frozen before any solution. This is the external coverage oracle for plans that cite it.",
        "",
        "<!-- Fill this marker and flip status: draft → ratified on PM convergence (skills/shape/SKILL.md). -->",
        "",
        "## Problems",
        "",
        "<!-- List problems falsifiably. Numbering is plain enumeration, NOT prioritization. -->",
        "<!-- Do not use P<n> prefixes — they collide with the P0/P1/P2 priority convention. -->",
        "",
        "1. **<short name>.** <The problem, stated falsifiably. What's wrong / missing / needed and why.>",
        "",
        "## Out of scope (architectural reasons)",
        "",
        "<!-- List things explicitly NOT solved here, with hard architectural reasons (not 'later'). -->",
        "",
        "- **<Thing we're NOT solving>** — <hard architectural reason.>",
        "",
    ]
    return "\n".join(lines)


# Valid nature enum values for completion entries (mirrors completion-entry.schema.json).
_COMPLETION_NATURE_ENUM = ("roadmap", "bugfix", "tech-debt", "infra")


def _scaffold_completion(
    title: str,
    nature: str,
    chain: str | None,
    completion_id: str | None = None,
) -> str:
    """Generate validator-clean completion-entry frontmatter + canonical body placeholder.

    Emits the field set for archive/completed/*/*.md against completion-entry.schema.json:
    required title/created/nature (valid enum, default: infra) + optional nature_inferred
    (false), commits (empty list), status (pending-release), chain_terminal (false), loe
    block (all null). Runtime-filled fields authored_by, chain, and loe values are emitted
    as commented-out lines or schema-valid nulls — the skill fills them via
    coordinator-session-loe.py (loe block, Step 2.6.5a) and reconcile-completion-commits.py
    (commits list, Step 2.6.8).

    Design constraint: the scaffolder emits the SKELETON ONLY — it does NOT compute
    loe/commits. Those are filled at runtime by the existing sub-helpers the skill calls.
    Negative-spec: does NOT shell out to coordinator-session-loe.py or
    reconcile-completion-commits.py.

    completion_id (lvv-01/C1) is the new durable-link stable ID (cmp-<slug>-<6hex>).
    OPTIONAL — completion-entry.schema.json is a standalone JSON Schema with no
    CROSS_FIELD_RULES entry, so this is a pure additive-property emission with no
    rule wiring; omitted entirely (not emitted as null) when not supplied.

    Spec backlink: docs/plans/2026-06-29-cli-scaffold-deterministic-docs.md § C3b
    Spec backlink (completion_id): docs/plans/2026-07-08-lifecycle-vocab-c2-durable-links-rollup.md § C1
    """
    today = _today()
    lines = [
        "---",
        f"title: {_yaml_quote(title)}",
        f"created: {today}",
        f"nature: {nature}  # one of: roadmap|bugfix|tech-debt|infra",
        "nature_inferred: false  # true when auto-inferred by workstream-complete Step 3 Sonnet dispatch; false when explicitly set (--nature arg or COMPLETION_NATURE env var)",
        # Review: code-reviewer — F7: clarified nature_inferred comment to cover --nature arg path
    ]
    if completion_id:
        lines.append(f"completion_id: {_yaml_quote(completion_id)}")
    # chain: emit as a commented hint — the skill determines this at /workstream-complete time.
    # anyOf: [string, null] in the schema; emit the caller-supplied slug if provided, else
    # a comment so the field is absent (omitting chain is valid — not required by the schema).
    if chain:
        lines.append(f"chain: {_yaml_quote(chain)}")
    else:
        lines.append("# chain: null  # fill with chain slug; omit this line entirely for standalone (non-chain) entries")
    lines.extend([
        "commits: []  # fill via reconcile-completion-commits.py --append (Step 2.6.8)",
        "status: pending-release",
        "chain_terminal: false  # set to true on /pickup → /workstream-complete (chain-terminal entry)",
        "# authored_by: PLACEHOLDER  # fill with $em_sid at runtime (type: string; forensic tracing only)",
        "loe:",
        "  agent_dispatches: null",
        "  opus_dispatches: null",
        "  em_tokens: null",
        "  tshirt: null",
        "---",
        "",
        "<!-- ONE paragraph (≤8 sentences): what shipped + why it matters.",
        "     Banned ## sections: '## Reviewer chain', '## Deviations from plan',",
        "     '## Acceptance criteria', '## Universal lessons captured'.",
        "     The completion entry is the queryable index, not the synthesis archive. -->",
        "",
    ])
    return "\n".join(lines)


def _scaffold_health_status(title: str) -> str:
    """Generate validator-clean health-status frontmatter + canonical body placeholder.

    Produces a conformant health-status record against schemas/health-status.schema.json
    (applies_to: state/health/*.md). Emits BOTH required axes so they cannot be conflated:

      status: active  — LIFECYCLE axis (active | archived); liveness keys on status ONLY.
      health: HEALTHY — POSTURE axis (HEALTHY | WATCH | ACTION | CRITICAL).

    Required fields: title, created, status, health.
    Optional: owner (coordinator-claude), summary (placeholder).

    The leading `schema: health-status` key is emitted for consistency with the existing
    conformant record at state/health/2026-06-27-health-summary.md.

    After scaffolding, fill the health: posture axis and summary: narrative from the day's
    findings (see skills/code-health/SKILL.md § Step 7 — the skill calls this scaffolder
    then fills those fields via Edit).

    Spec backlink: docs/plans/2026-06-29-cli-scaffold-deterministic-docs.md § C3d
    Negative-spec: does NOT conflate status (LIFECYCLE) with health (POSTURE) — see schema
    description field for the canonical two-axis semantics.
    """
    today = _today()
    lines = [
        "---",
        "schema: health-status",
        f"title: {_yaml_quote(title)}",
        f"created: {today}",
        "status: active  # LIFECYCLE axis: active | archived",
        "health: HEALTHY  # POSTURE axis: HEALTHY | WATCH | ACTION | CRITICAL",
        "owner: coordinator-claude",
        "summary: \"PLACEHOLDER — replace with one-line health narrative after grading\"",
        "---",
        "",
        f"# {title}",
        "",
        "<!-- Fill health: posture and summary: narrative from the day's findings. -->",
        "<!-- Then add the body sections below. -->",
        "",
        "## Systems Graded",
        "",
        "<!-- Table: | System | Grade | Health | Notes | -->",
        "",
        "## Findings Summary",
        "",
        "<!-- Counts: total / P0 / P1 / P2 applied / deferred. -->",
        "",
        "## Action Items for Next Session",
        "",
        "<!-- List any P0/P1 items that need attention next session. -->",
        "",
    ]
    return "\n".join(lines)


def _scaffold_goal(title: str) -> str:
    """Generate validator-clean whole-document-YAML goal record.

    Produces a conformant goal record against schemas/goal.schema.json
    (applies_to: state/goals/*.yaml). Goals are pure .yaml files — the
    frontmatter IS the whole file; there is no markdown body (this scaffolder
    reverses the prior .md-with-body shape per 2026-07-13 § C1, which
    supersedes 2026-07-06 § C1's .md-over-.yaml decision).

    Required fields: schema, id, title, status, objective, key_results,
    created, period, period_value. Optional: owner, weekly_perceptible
    (top-level), parent_goal_id, goal_id.

    The id field is derived from the title slug with a 'goal-' prefix so it is
    stable and unique from inception. `period`/`period_value` are left as
    generic placeholders here — this is the FOUNDATION scaffolder shape; the
    weekly-authoring path (C2, workweek-start Step 5) populates period=week +
    a derived period_value + weekly_perceptible:true + goal_id automatically
    rather than requiring manual entry. After scaffolding, replace the
    objective placeholder and flesh out key_results items with real text and
    evidence sources (see SKILL.md for the goal-authoring procedure).

    Output path: state/goals/YYYY-MM-DD-<slug>.yaml — routed through the
    coordinator_state_root seam (sibling repos → $GIT_ROOT/state/goals/;
    meta-repo → claude-klabauter/state/goals/).

    Spec backlink: docs/plans/2026-07-06-deliverable-rollup-render-and-fk-population.md § C1
    Spec backlink: docs/plans/2026-07-13-close-weekly-goal-loop.md § C1 (.md→.yaml migration)
    Negative-spec: does NOT emit prose body content or `---` frontmatter
    fences — the entire file IS the YAML document (whole-document-yaml
    match_mode). Fabricates NO goal content beyond structural placeholders.
    """
    today = _today()
    slug = _slug_from_title(title)
    goal_id = f"goal-{slug}"
    lines = [
        "schema: goal",
        f"id: {_yaml_quote(goal_id)}",  # Review: code-reviewer — use _yaml_quote for consistency with other emitted fields (F13)
        f"title: {_yaml_quote(title)}",
        "status: active",
        "objective: \"PLACEHOLDER — replace with one-sentence statement of what this goal achieves\"",
        "key_results:",
        "  - id: kr-1",
        "    text: \"PLACEHOLDER — describe the first measurable key result\"",
        "    kind: outcome  # output | outcome",
        "    status: not-started  # not-started | in-progress | met | at-risk",
        "    weekly_perceptible: true",
        "    evidence_source: null",
        f"created: {today}",
        "# owner: PLACEHOLDER  # optional — EM or workstream identifier",
        "period: week  # required by emitter — day | week | repo | quarter | year",
        "period_value: \"PLACEHOLDER\"  # required: e.g. 2026-W28 (week), 2026-07-07 (day), DoE-2026 (repo), Q3-2026 (quarter), 2026 (year)",
        "# weekly_perceptible: true  # optional — TOP-LEVEL goal-scope flag, distinct from the per-KR field above",
        "# parent_goal_id: null  # optional — FK to a parent quarter/repo OKR goal_id, or null",
        f"# goal_id: {_yaml_quote(goal_id)}  # optional — deterministic sha1(repo|root|period|period_value|text); this is the structured-records (C15) facet key, DISTINCT from the wire goal_id (append-goal-event.py derives its own hash from id-prefixed text and currently ignores --goal-id); populate once period/period_value/objective are final",
    ]
    return "\n".join(lines) + "\n"


def _scaffold_sizing(title: str, deliverable_id: str | None = None) -> str:
    """Generate validator-clean whole-document-YAML sizing-object record.

    Produces a conformant record against schemas/sizing-object.schema.json
    (applies_to: state/sizings/*.yaml). Same whole-document-YAML shape as
    _scaffold_goal — the entire file IS the record, no `---` frontmatter
    fence and no markdown body.

    Required fields: schema, intent, estimate (tshirt + provisional),
    route, detents, fork, xl_exit, status, premise (provenance).
    `name` is OPTIONAL and scaffolded commented-out — see
    schemas/sizing-object.schema.json's `name` description for the
    60-char cap and label-not-identifier contract; this function never
    derives one from `title`/slug/`intent`, and leaves it commented so
    an unedited scaffold does not surface a placeholder in cockpit's
    tab strip.
    `title` is used only to seed the
    `intent` placeholder (sizing-object has no `title` field of its own —
    `intent` is the PM's verbatim ask). All enum-valued fields are
    scaffolded with a real, schema-valid member (not a bare PLACEHOLDER
    string) so the emitted skeleton validates as-is; the EM edits the
    values, not the shape, before commit.

    `deliverable_id` is minted HERE, at scaffold time, via the caller's
    resolved `_mint_deliverable_id` value (carry/stub/slug — the same
    seam `--type plan` uses; this function never re-derives it) — a
    sizing-object is the earliest artifact in the deliverable chain, so
    this is where the spine join key is first minted. See
    schemas/sizing-object.schema.json's `deliverable_id` description and
    docs/plans/2026-08-08-sizing-objects-join-the-deliverable-spine.md § C2.

    Output path: state/sizings/YYYY-MM-DD-<slug>.yaml.

    Spec backlink: docs/plans/2026-07-24-sizing-lobby-core.md § C1/C3
    Spec backlink: pln-a-sizing-mints-the-join-key-th-8eaca3 § C1
    Negative-spec: does NOT emit prose body content or `---` frontmatter
    fences — whole-document-yaml match_mode, matching _scaffold_goal.
    Does NOT resolve the sizing halt — `fork` scaffolds `null`;
    only the sizing skill (operator judgment) ever sets it non-null. `xl_exit`
    is the identical shape for the XL decision point: it scaffolds `null`, the
    engine never sets it, and only the sizing skill fills it once the PM has
    actually picked among split / shape / roadmap / accept_multi_session. A
    `null` there means NOT YET CHOSEN — never that the multi-session exit was
    accepted by default. Both fields are required-and-nullable in the schema,
    so both must be emitted here even when null.
    """
    intent_placeholder = title if title else "PLACEHOLDER — replace with the PM's ask, verbatim"
    lines = [
        "schema: sizing-object",
        "# name: PLACEHOLDER  # OPTIONAL, <=60 chars — a display LABEL only, nothing joins on it; do NOT slice from intent",
        f"intent: {_yaml_quote(intent_placeholder)}",
        "estimate:",
        "  tshirt: XS  # XS | S | M | L | XL | XXL — reuses loe.tshirt; coarse ROUTING estimate only",
        "  provisional: true  # always true — never the committed plan-body LoE",
        "route: dispatch  # dispatch | spec-dispatch | shape | plan | roadmap | pm-decision | goal-setting",
        "detents: []  # boundary detents crossed while sizing (e.g. appetite_exceeded); [] if none",
        "fork: null  # cut_to_fit | raise_appetite | null — set ONLY on genuine appetite/estimate divergence; never auto-resolved",
        "xl_exit: null  # split | shape | roadmap | accept_multi_session | null — the PM's pick at a pm-decision route; null means NOT YET CHOSEN, never 'accepted'",
        "status: draft  # draft | sized | routed | shipped | declined | superseded",
        "premise:",
        "  provenance: unrecorded  # executed | read | not-applicable | unrecorded — how the premise was verified; ADVISORY, never blocks a route",
        "  evidence: PLACEHOLDER — cite the file:line, test, or command output you actually looked at; answered in place, never spun into its own record",
        f"deliverable_id: {_yaml_quote(deliverable_id) if deliverable_id else 'null'}  # durable spine join key, minted at scaffold time — do not hand-edit",
    ]
    return "\n".join(lines) + "\n"


def _scaffold_strategic_self_description(title: str) -> str:
    """Generate validator-clean whole-document-YAML strategic-self-description record.

    Produces a conformant record against schemas/strategic-self-description.schema.json
    (x-schema-version 1.1.0, applies_to: state/strategic/self-description.yaml). This is
    a whole-document-YAML artifact — there is no `---` frontmatter fence and no markdown
    body; the entire file IS the record (same shape as _scaffold_goal), and the schema is
    additionalProperties:false at the top level, so no extra keys (no leading `schema:`
    marker line, unlike the markdown-frontmatter scaffolders) may be emitted.

    Required top-level fields: repo_identity, lifecycle, vision, version_highlights,
    competitors, call_to_action, hero_asset. `version_highlights` and `competitors` are
    emitted as empty arrays — both are documented as "may be empty" in the schema, and
    this scaffolder does NOT fabricate real milestone/competitor data (that is squarely
    human-authored editorial judgment). `call_to_action` uses the `none` branch (kind +
    label only) since a real url/claude-session payload is likewise not something to
    invent. `hero_asset` is emitted as an explicit `null` — the D9 typed-null read
    contract requires the key present-with-null, never omitted.

    `vision.value` and `call_to_action.label` are curated-provenance placeholder text
    the human replaces; `repo_identity.repo` is seeded from the --title argument (the
    scaffolding convention for this type is to title the document with the repo name),
    and `repo_identity.coordinator_root_path` is emitted as an explicit `null` — it is a
    machine-local location fact, not a member of the (owner, repo) join key, and is carried
    present-as-null per the D9 typed-null read contract (DR-069), never a cwd-derived path.

    Spec backlink: docs/plans/2026-07-11-strategic-self-description-standard.md § C1, C3
    Negative-spec: does NOT invent competitor/version-highlight content, does NOT emit a
    `schema:` marker key (additionalProperties:false forbids it), does NOT omit `hero_asset`.
    """
    repo_name = title.strip() if title and title.strip() else "PLACEHOLDER-repo"
    lines = [
        "repo_identity:",
        "  owner: PLACEHOLDER-owner  # e.g. a github org/user, or local/<basename> when this repo has no git remote",
        f"  repo: {_yaml_quote(repo_name)}",
        "  coordinator_root_path: null  # machine-local location, NOT part of the (owner, repo) join key — present-as-null, never a cwd-derived path (DR-069)",
        "lifecycle: prototype  # EDIT: prototype | vertical-slice | alpha | shipped | live-ops | sunset",
        "vision:",
        "  value: \"<one-paragraph statement of what this repo strategically is / is for>\"",
        "  provenance: curated  # curated | generated | asserted",
        "version_highlights: []  # optional; add {label, date, bullets, provenance} entries as dated milestones land",
        "competitors: []  # optional; add {name, relationship, note, provenance} entries — note is present-as-null when a competitor entry has none",
        "call_to_action:",
        "  kind: none  # none | url | claude-session — see schema $defs for the required payload shape of the other two kinds",
        "  label: \"<call-to-action label>\"",
        "hero_asset: null  # OPTIONAL hero image/screenshot URI — present-as-null when absent, never omit this key",
        "# maturity_axis: null  # OPTIONAL, consumer-set-only field — DoE schema does not interpret its value",
        "# depends_on: []  # OPTIONAL, consumer-set-only field — repo_identity tuples this repo depends on",
    ]
    return "\n".join(lines) + "\n"


def _scaffold_research_synthesis(title: str) -> str:
    """Generate validator-clean research-synthesis frontmatter + canonical section skeleton.

    Produces a conformant research-synthesis document against
    schemas/research-synthesis.schema.json (applies_to: docs/research/*.md).
    Emits all index fields as stubs/placeholders — required: [] in the schema;
    enforcement is producer-side (the research-synthesizer fills values at produce-time).

    HARD GUARDRAIL: the body is section HEADERS ONLY. Do NOT emit any prose,
    sentences, or filler text under the headers — the expressive prose body is
    agent-authored at produce-time, NEVER templated.

    Temporal key: emits `created:` (not `date:`) — fleet-canonical key read by
    query-records --since/--older-than (reads fm.created); `date:` is excluded from
    temporal filtering and would cause research-synthesis records to be silently skipped.

    Spec backlink: docs/plans/2026-06-29-deep-research-queryable-index-layer.md § C6 [DEAD-CITATION: plan file never committed to this repo]
    Negative-spec: does NOT emit body prose — section headers + HTML comments only.
    The research-synthesizer authors the body; the scaffolder provides the shape.
    """
    today = _today()
    lines = [
        "---",
        f"title: {_yaml_quote(title)}",
        "question: \"PLACEHOLDER — replace with the research question this synthesis addresses\"",
        f"created: {today}",  # fleet-canonical temporal key (query-records --since reads fm.created, not fm.date)
        "pipeline: web  # one of: web | repo | structured | notebooklm",
        "# source_count: 0  # fill with number of sources consulted",
        "topic_facets: []  # fill with list of topic facets/sub-themes covered",
        "# coverage_score: 0  # fill with 1-5 coverage score from gap-report",
        "# confidence_summary: \"\"  # optional; prefer research-claim confidence= queries",
        "---",
        "",
        "## Executive Summary",
        "",
        "<!-- author fills -->",
        "",
        "## Findings",
        "",
        "<!-- author fills -->",
        "",
        "## Conclusion",
        "",
        "<!-- author fills -->",
        "",
        "## Open Questions",
        "",
        "<!-- author fills -->",
        "",
        "## Source Bibliography",
        "",
        "<!-- author fills -->",
        "",
    ]
    return "\n".join(lines)


# dispatch_feed placeholder block — SHARED by _scaffold_run_report and
# _scaffold_review_findings below so the two self-persist scaffolders in this
# file cannot drift from each other the way this file's dispatch_feed
# literal drifted from coordinator_core.subagent_sandbox.provision_report.
# _frontmatter's own copy (C6, commit 8571f7f22273; fixed here in C6b).
#
# This is a HAND-MAINTAINED mirror of provision_report._frontmatter's
# dispatch_feed block, not an import of it: provision_report.py lives in the
# coordinator_core engine checkout, reached only through this file's
# best-effort _ensure_engine_on_path() seam (may be unresolvable on a
# published/vendored install with no claude-klabauter checkout on disk), while this
# scaffolder's dispatch_feed placeholder must render even when the engine is
# absent (same degrade-open posture as SESSION_LEDGER_BLOCK_LINES above).
# Importing across that seam would make an otherwise engine-independent
# scaffold arm engine-REQUIRED for the CLI's normal case. The shape is
# instead pinned by a shared regression test
# (coordinator/tests/test_flight_recorder_scaffolder.py) that parses BOTH
# producers' emitted dispatch_feed and asserts field-for-field agreement —
# see that test's module for the enforcement mechanism.
_DISPATCH_FEED_BLOCK_LINES: tuple[str, ...] = (
    "dispatch_feed:  # forward-declared, INERT until pcli-04 emitter",
    "  gate_kind: none",
    "  write_files: []",
)


def _scaffold_run_report(
    plan_path: str,
    chunk_id: str,
    dispatched_at: str,
    dispatched_by: str,
    agent_type: str | None = None,
) -> str:
    """Generate validator-clean run-report sidecar frontmatter + lifecycle body.

    Emits the universal subagent run-report SUPERSET schema
    (schemas/run-report.schema.json — DEC-3, subsumes flight-recorder.schema.json):
    plan, chunk, dispatched_at, dispatched_by, status: dispatched, agent_type,
    spawned_at, commits: [], sidecar_schema: v1, started_at/finished_at (null —
    executor-written), divergence (block-style `diverged: false` nested mapping —
    executor-written, post-run), and dispatch_feed (INERT placeholder — the
    field is optional/claude-klabauter-emitter-written per pcli-04/C3, executor-READ-ONLY;
    emitted as a block-style object containing ONLY the sub-fields with a
    real value at scaffold time (`gate_kind: none`, `write_files: []`) —
    every other declared sub-property (label/agent_type/model/effort/
    schema_ref/brief_ref/est_min) admits no null in run-report.schema.json
    and is OMITTED rather than null-valued (dispatch_feed has no `required`
    list and `additionalProperties: true`, so omission validates cleanly),
    per _DISPATCH_FEED_BLOCK_LINES above — matching the corrected shape
    coordinator_core.subagent_sandbox.provision_report._frontmatter emits
    (C6, commit 8571f7f22273, corrected in C6b after a staff review found
    C6's original all-null-subfields shape was schema-invalid). Field shape
    matches the printf the retired fan-out-dispatch.sh (DoE 65e5d199,
    2026-07-19) used to emit for the fields it still shares.

    This function is the former _scaffold_flight_recorder, renamed and extended
    for the run-report subsume (plan: 2026-07-13-subagent-run-report-subsume.md,
    chunk C4). --type flight-recorder remains a caller-facing BACKWARD-COMPAT
    ALIAS for --type run-report (see main()'s doc_type normalization) so in-flight
    callers (fan-out-dispatch.sh, pre-C5 executors) do not break.

    divergence is emitted in BLOCK style (key on its own line, nested `diverged:`
    indented below), NOT flow style (`divergence: {diverged: false}`) — this
    repo's minimal YAML parser (bin/lib/schema.js parseYaml) does not support
    flow-style mappings and would parse a flow-style value as a raw string,
    failing the object-shaped schema check (divergence: type object, required
    [diverged], additionalProperties: false). Block style is the only shape
    that parses correctly under the real validator. This is the OBJECT form
    mandated by DEC-3's reconcile — NEVER an array (a bare `divergence: []`
    does not validate against the object-typed schema; see run-report.schema.json's
    divergence property and the C10 retirement-gate assertion that guards this).

    agent_type is OPTIONAL (defaults to the literal "executor" when omitted) —
    the universal field naming which subagent kind was spawned (e.g. executor,
    review-integrator, code-reviewer); flight-recorder-shaped callers (fan-out-
    dispatch.sh chunk dispatch) always spawn an executor, so the default covers
    that call shape without requiring every caller to pass --agent-type.

    Spec backlink: docs/plans/2026-07-13-subagent-run-report-subsume.md § C4, DEC-3
    Spec backlink (predecessor shape): docs/plans/2026-06-09-executor-sidecar-flight-recorder.md § Sidecar shape
    Spec backlink: docs/plans/2026-07-09-dispatch-sidecar-executor-confinement.md § C-DOC, D-SCHEMA, D-DIGRESSION
    Negative-spec: does NOT transition status beyond 'dispatched' — the executor updates
    the sidecar in-place as it progresses through the lifecycle.
    Negative-spec: sidecar_schema stays 'v1' here too — it is a frozen structural-family
    sentinel (not a semver mirror); the superset schema's version field is the version
    discriminator, read via field presence downstream, not via this sentinel (the Staff Engineer
    Finding 0 / AC1c, carried forward from flight-recorder).
    """
    _agent_type = agent_type or "executor"
    lines = [
        "---",
        f"plan: {_yaml_quote(plan_path)}",
        f"chunk: {_yaml_quote(chunk_id)}",
        f"dispatched_at: {_yaml_quote(dispatched_at)}",  # Review: code-reviewer item-5 F2 — YAML 1.1 coerces bare ISO timestamps to datetime; schema declares string
        f"dispatched_by: {_yaml_quote(dispatched_by)}",  # Review: code-reviewer item-5 F2 — session ids may contain special chars; guard with _yaml_quote
        "status: dispatched",
        f"agent_type: {_yaml_quote(_agent_type)}",
        f"spawned_at: {_yaml_quote(dispatched_at)}",  # universal field mirrors dispatched_at at scaffold time
        "commits: []",
        "sidecar_schema: v1",
        "started_at: null",
        "finished_at: null",
        "divergence:",
        "  diverged: false",
        *_DISPATCH_FEED_BLOCK_LINES,
        "---",
        "",
        "<!-- Run-report lifecycle: dispatched → in_flight → complete | blocked | thrashing.",
        "     Lives at state/subagent-share/<session-id>/<key>.md (applies_to:",
        "     state/subagent-share/*/*.md), path owned and computed by claude-klabauter's",
        "     provision_report engine at spawn time (see CONTRACT.md). This scaffold's",
        "     --out path is caller-supplied; there is no default path.",
        "     Swept at /workstream-complete: complete entries are folded-and-deleted.",
        "     blocked and thrashing terminal sidecars SURVIVE the sweep.",
        "     See: docs/plans/2026-07-13-subagent-run-report-subsume.md -->",
        "",
        "## Run notes",
        "",
        "<!-- Offer-shape prose channel back to the EM (DEC-4). Jot run notes and any",
        "     divergence-from-instructions here — never a write mandate. -->",
        "",
        "## Observations",
        "",
        "<!-- Executor scratchpad. Append latent-bug notes, mid-flight decisions,",
        "     files-touched lists, and validation output snippets here. -->",
        "",
    ]
    return "\n".join(lines)


def _scaffold_review_findings(slice_id: str, scope: str, spawned_at: str, lead_session_id: str) -> str:
    """Generate a pre-scaffolded code-reviewer findings sidecar with FINDINGS sentinel anchor.

    FRONTMATTER-BEARING as of the run-report/review-findings schema unification (docs/plans/
    2026-07-24-reviewer-sidecar-provisioning-reconciliation.md): mirrors coordinator_core.
    subagent_sandbox.provision_report.py's ``_frontmatter()`` block byte-shape (same keys,
    same order: status/agent_type/spawned_at/lead_session_id/divergence/commits/
    dispatch_feed) so a self-scaffolded file is shape-identical to a provision_report-
    provisioned one -- both now validate against the SAME superset ``run-report.schema.json``
    (``applies_to: state/subagent-share/*/*.md``, ``required: ["status"]``), and the now-
    retired ``review-findings.schema.json`` no-frontmatter special-case is gone. ``agent_type``
    is stamped as the literal 'review-findings' (this scaffolder's doc TYPE, not a spawned
    agent's role -- provision_report's own agent_type field records the SPAWNED agent's type
    instead, e.g. 'code-reviewer'; the two producers diverge on this one field's semantic,
    not its presence).

    Emits a lightweight markdown skeleton consumed by agents/code-reviewer.md:
    a heading, Reviewer/Scope/Diff-range metadata lines, and a ## Findings section whose
    body is the single literal sentinel line <!-- FINDINGS -->. The reviewer replaces the
    sentinel via a single Edit so the full findings body lands in one atomic write, making
    no-ops detectable (the sentinel survives an Edit that touched nothing meaningful) and
    bounding the reviewer to one write action per slice.

    Negative-spec: does NOT reuse provision_report's own review-findings sentinel text
    (``<!-- One entry per finding: ... -->``) -- that producer's sentinel diverges from the
    ``<!-- FINDINGS -->`` anchor agents/code-reviewer.md and this schema's description
    document; this scaffolder keeps the documented ``<!-- FINDINGS -->`` anchor rather than
    silently adopting the other producer's different sentinel text. Pre-existing divergence,
    out of scope for this shape-unification fix.

    This is the SOLE self-persist scaffold path -- reached only when a code-reviewer
    dispatch arrived with NO sidecar pre-provisioned by the dispatching EM (the common
    case is engine-side spawn-time provisioning via coordinator_core.dispatch.provision /
    coordinator_core.subagent_sandbox.provision_report, which this scaffolder never
    duplicates). Code-reviewer returns the path in its DONE line either way.

    Output path: state/subagent-share/<session-id>/YYYY-MM-DD-codereview-slice<ID>-<SLUG>.md
    -- the DR-091 one-home (docs/decisions/DR-091-agent-citizenship-identity-typed-sidecar-
    contract.md), the SAME state/subagent-share/<session>/ root provision_report.py's
    _provision() already writes to for the pre-provisioned (common) path. <session-id> is
    resolved by _resolve_session_id() below using the identical env var + precedence chain
    coordinator-doc-new already uses for --type run-report/subagent-sidecar's
    `dispatched_by` (COORDINATOR_SESSION_ID > CLAUDE_SESSION_ID > CLAUDE_CODE_SESSION_ID) --
    this is the same overall harness session identity provision_report reads from its
    spawn-time hook payload's `session_id` field, just resolved from the running process's
    own environment instead of a payload, since a self-scaffold has no payload to read.
    Path formula is pinned here and in schemas/review-findings.schema.json's description.

    Confinement note: the Edit write-sandbox structural confinement (formerly "Mode A",
    restricting Edit to a fixed directory) was removed 2026-07-15 (DR-058) -- writing ONLY
    the findings sidecar is now a discipline the code-reviewer agent prompt upholds by
    convention, not a structural guarantee enforced here.

    Spec backlink: docs/plans/2026-06-30-reviewer-findings-self-persist.md § D1
    Spec backlink (self-persist design): cross-repo/inbox/2026-07-01-reviewer-selfpersist-confinement-redirect.md
    Spec backlink (subagent-share migration): docs/plans/2026-07-24-reviewer-sidecar-provisioning-reconciliation.md
    Negative-spec: does NOT contain prose findings — the reviewer authors those via Edit.
    Negative-spec: frontmatter here is scaffolded structure (status/agent_type/spawned_at/
    lead_session_id/divergence/commits/dispatch_feed), not reviewer-authored content — the
    reviewer only fills the body's ## Findings section. The JSON trail record at
    state/review-trail/*.json is a separate surface (unchanged by this scaffolder's move --
    reap_integrated_findings.py / reap_unintegrated_findings.py still operate on that JSON
    trail, not this markdown sidecar's frontmatter).
    Negative-spec: the retired 'code-reviewer-selfpersist' variant is gone; this scaffolder
    serves the one remaining code-reviewer agent (which self-persists by default).
    """
    lines = [
        "---",
        "status: open",
        "agent_type: review-findings",
        f"spawned_at: {spawned_at}",
        f"lead_session_id: {lead_session_id}",
        "divergence:",
        "  diverged: false",
        "commits: []",
        *_DISPATCH_FEED_BLOCK_LINES,
        "---",
        "",
        f"# Code Review: Slice {slice_id} -- {scope}",
        "",
        "Reviewer: code-reviewer",
        f"Scope: {scope}",
        "Diff range: PLACEHOLDER",
        "",
        "## Findings",
        "",
        "<!-- FINDINGS -->",
        "",
    ]
    return "\n".join(lines)


def _scaffold_subagent_sidecar(
    plan_path: str,
    chunk_id: str,
    dispatched_at: str,
    dispatched_by: str,
    agent_type: str | None = None,
) -> str:
    """Generate a subagent-sidecar decision-object container.

    Schema-of-record: schemas/decision-object.schema.json $defs/subagent_sidecar
    (DoE-owned CONTRACT artifact — this scaffolder is the claude-klabauter-side GENERATE
    altitude, not a schema fork). Reuses the run-report dispatch frontmatter
    shape (plan/chunk/dispatched_at/dispatched_by/status/agent_type/spawned_at/
    commits/sidecar_schema — see _scaffold_run_report) and layers the THREE
    decision-object fields on top: completion_status, divergence_from_plan,
    tell_the_EM.

    This is DISTINCT from --type run-report: run-report is the universal
    lifecycle tracker (status/commits/divergence prose, freeform ## Run notes
    / ## Observations sections); subagent-sidecar is the CURATED decision-
    object container an agent fills as its ONLY structured write-back —
    verdict-shaped, not lifecycle-shaped. Do not merge the two scaffolders;
    they serve different consumers (run-report: EM dispatch tracking;
    subagent-sidecar: the plan->wiki->prior-art divergence-truth pipeline).

    completion_status: a durable, queryable "task done" marker that backlinks
    the existing query-completions records surface (claude-klabauter work-state
    emission) -- NOT a fourth store; defaults to the literal "pending" at
    scaffold time, executor-written thereafter.
    divergence_from_plan: block-style nested mapping (diverged/summary/detail)
    -- untrusted narrative, never re-read as a directive by any automated
    consumer (see divergence_from_plan's schema description).
    tell_the_EM: freeform exit-interview channel, body section (not
    frontmatter) so it can carry arbitrary prose/markdown.

    Class-asymmetric behavior (R7 Addendum) is NOT encoded as a scaffolded
    field here -- it is a confinement/tool-grant property of the DISPATCHING
    side (generic executors: read-only-on-plan, sidecar is their only
    structured write-back; named Opus personas: offered-not-imposed, may
    also edit). This scaffolder emits the same container shape for both
    classes; the asymmetry lives in what tool grant the dispatched agent
    receives, never in this document's shape.

    Negative-spec: this is NOT the harness's raw JSONL transcript -- no
    duplication of that surface (AC-10). The curated container here is a
    human/EM-legible verdict + findings + tell_the_EM record, not a replay
    log.

    Spec backlink: docs/plans/2026-07-24-canonical-resolution-engine.md § W2-B3, R7 Addendum
    """
    _agent_type = agent_type or "executor"
    lines = [
        "---",
        f"plan: {_yaml_quote(plan_path)}",
        f"chunk: {_yaml_quote(chunk_id)}",
        f"dispatched_at: {_yaml_quote(dispatched_at)}",
        f"dispatched_by: {_yaml_quote(dispatched_by)}",
        "status: dispatched",
        f"agent_type: {_yaml_quote(_agent_type)}",
        f"spawned_at: {_yaml_quote(dispatched_at)}",
        "commits: []",
        "sidecar_schema: v1",
        "completion_status: pending",
        "divergence_from_plan:",
        "  diverged: false",
        "  summary: \"\"",
        "  detail: \"\"",
        "---",
        "",
        "<!-- Subagent-sidecar decision-object container (schemas/decision-",
        "     object.schema.json $defs/subagent_sidecar). Lives at",
        "     state/subagent-share/<session-id>/<key>.md, path owned and",
        "     computed by coordinator_core.dispatch.provision at spawn time.",
        "     This scaffold's --out path is caller-supplied; there is no",
        "     default path. See docs/plans/2026-07-24-canonical-resolution-",
        "     engine.md § W2-B3. -->",
        "",
        "## tell_the_EM",
        "",
        "<!-- Freeform exit-interview channel -- anything the executor wants",
        "     the dispatching EM to know that doesn't fit completion_status",
        "     or divergence_from_plan above. -->",
        "",
    ]
    return "\n".join(lines)


# review F3 — _SIDECAR_SUFFIX was a local static dict that duplicated manifest data.
# Deleted; replaced by _SIDECAR_SUFFIXES imported from coordinator_registry (manifest-derived).


def _scaffold_sidecar(doc_type: str, plan_stem: str) -> str:
    """Generate validator-clean sidecar frontmatter + shared section skeleton.

    Emits conformant frontmatter against the matching sidecar schema (review-sidecar,
    prior-art-check, plan-coverage-check, docs-check-sidecar). The plan_stem is the
    bare plan filename stem (e.g. '2026-06-25-foo'), NOT the full path. The canonical
    plan path is derived as docs/plans/<plan_stem>.md.

    All four sidecar types share the section grammar: ## Summary (verdict line) +
    ## Findings, per the shared sidecar-family grammar (D5).

    Spec backlink: docs/plans/2026-06-25-example-initiative-tc-1-records-consolidation.md § C5, D5
    """
    today = _today()
    plan_path = f"docs/plans/{plan_stem}.md"

    if doc_type == "review":
        # review-sidecar schema: required plan:; kind: from kinds list + optional reviewer/verdict.
        kinds_hint = (
            "staff-eng-review, eng-director-review, staff-ux-review, "
            "staff-game-dev-review, staff-data-sci-review, senior-front-end-review, "
            "code-review, plan-review, review"
        )
        # Review: code-reviewer slice-B F1 — _yaml_quote applied to plan_path to prevent
        # YAML injection if an unvalidated stem ever reaches here (defense-in-depth).
        fm_lines = [
            "---",
            f"plan: {_yaml_quote(plan_path)}",
            f"kind: staff-eng-review  # one of: {kinds_hint}",
            "reviewer: PLACEHOLDER",
            "verdict: PLACEHOLDER",
            f"created: {today}",
            "---",
        ]
    elif doc_type == "prior-art-check":
        # prior-art-check schema: required plan:; optional author/created/status/counts.
        fm_lines = [
            "---",
            f"plan: {_yaml_quote(plan_path)}",
            f"created: {today}",
            "author: PLACEHOLDER",
            "status: pending",
            "# conflicts: 0",
            "# compatible: 0",
            "# silent: 0",
            "---",
        ]
    elif doc_type == "plan-coverage-check":
        # plan-coverage-check schema: required plan:; optional author/created/verdict/status.
        fm_lines = [
            "---",
            f"plan: {_yaml_quote(plan_path)}",
            f"created: {today}",
            "author: PLACEHOLDER",
            "verdict: PLACEHOLDER",
            "---",
        ]
    elif doc_type == "docs-check":
        # docs-check-sidecar schema: required artifact: (NOT plan:); optional checker/counts.
        fm_lines = [
            "---",
            f"artifact: {_yaml_quote(plan_path)}",
            f"created: {today}",
            "checker: PLACEHOLDER",
            "# claims_checked: 0",
            "# verified: 0",
            "# unverified: 0",
            "# incorrect: 0",
            "# auto_fixed: 0",
            "---",
        ]
    else:
        # Unreachable — caller already validated doc_type in _SIDECAR_TYPES.
        raise AssertionError(f"unreachable sidecar type: {doc_type!r}")

    # Canonical section skeleton — type-specific per the agent contract.
    # Each scaffold emits the exact bucket headings the corresponding agent populates
    # so the receiving agent fills a pre-shaped body rather than hand-rolling structure.
    # Spec backlink: docs/plans/2026-06-29-cli-scaffold-deterministic-docs.md § C2
    if doc_type == "prior-art-check":
        # Three buckets from agents/prior-art-checker.md § Sidecar Format.
        body_lines = [
            "",
            "## Prior-Art Verification",
            "",
            "**Plan:** PLACEHOLDER",
            "**Verdict:** COMPATIBLE | WARN | BLOCKED-SURFACE-TO-PM | DEGRADED",
            "**Claims checked:** 0",
            "**Conflicts:** 0 | **Compatible-but-relevant:** 0 | **Silent:** 0",
            "**Corpora consulted:** project-wikis | global-wikis | lessons.md | improvement-queue",
            "",
            "### Conflicts (plan contradicts prior art)",
            "",
            "<!-- For each CONFLICT: claim topic, plan assertion, prior-art quote (verbatim), candidate directions for EM. -->",
            "",
            "### Compatible-but-relevant (plan should cite or align)",
            "",
            "<!-- For each COMPATIBLE-BUT-RELEVANT: claim topic, prior-art quote (verbatim), subtype, suggested action. -->",
            "",
            "### Silent areas (no prior art found)",
            "",
            "<!-- For each SILENT: Claim #N — [topic]: no prior art in any corpus. -->",
            "",
        ]
    elif doc_type == "plan-coverage-check":
        # Four headings (Missed / Ambiguous / Weak-OOS+Hedges / Substrate-drift) intentionally
        # matching the actual sidecar skeleton in agents/plan-coverage-checker.md lines ~194-206.
        # The plan describes "5 buckets" conceptually but Weak-OOS and Hedges share one heading
        # there — do NOT split into 5 here.
        # Review: code-reviewer — F5: document-only; 4-heading output matches agents/plan-coverage-checker.md
        body_lines = [
            "",
            "## Plan Coverage Verification",
            "",
            "**Plan:** PLACEHOLDER",
            "**Verdict:** COMPLETE | INCOMPLETE | BLOCKED-SURFACE-TO-PM | SCOPE-MISMATCH | DEGRADED",
            "**Oracle items:** 0",
            "**Slate items:** 0",
            "**Missed:** 0 | **Ambiguous:** 0 | **OOS-weak:** 0 | **Hedges:** 0 | **Substrate-drift:** 0",
            "",
            "### Missed audit items (no slate entry, no architectural OOS)",
            "",
            "<!-- For each MISSED: oracle item verbatim, suggested resolution (add to slate | architectural-OOS | oracle-was-wrong). -->",
            "",
            "### Ambiguous audit items (signal-partial — informational only)",
            "",
            "<!-- For each AMBIGUOUS: oracle item verbatim, reason for classification, EM action suggestion. -->",
            "",
            "### Weak OOS / hedges (appetite-based deferrals)",
            "",
            "<!-- For each WEAK-OOS/HEDGE: plan quote with context, doctrine citation, suggested action. -->",
            "",
            "### Substrate drift (in-repo paths/symbols cited that don't match disk)",
            "",
            "<!-- For each DRIFT: plan citation, current disk state, suggested action. -->",
            "",
        ]
    elif doc_type == "docs-check":
        # Verification TABLE from agents/docs-checker.md § Output Format.
        body_lines = [
            "",
            "## Docs Verification Report",
            "",
            "**Artifact:** PLACEHOLDER",
            "**Claims checked:** 0",
            "**Verified:** 0 | **Unverified:** 0 | **Incorrect:** 0 | **Auto-fixed:** 0",
            "",
            "### Verification Table",
            "",
            "| # | Claim | Source | Status | Action | Detail |",
            "|---|-------|--------|--------|--------|--------|",
            "",
            "### Incorrect Claims (action required)",
            "",
            "<!-- For each INCORRECT: Claim #N, what docs say, suggested correction, auto-fixed status. -->",
            "",
            "### Unverified Claims (could not confirm)",
            "",
            "<!-- For each UNVERIFIED: Claim #N, search attempted, why unconfirmed. -->",
            "",
        ]
    else:
        # doc_type == "review": Summary + Findings-by-severity + Verdict.
        # Generic enough for any reviewer persona (the Staff Engineer, the Game Dev Reviewer, the Director of Engineering, the Data Science Reviewer, the Front-End Reviewer, the UX Reviewer).
        body_lines = [
            "",
            "## Summary",
            "",
            "<!-- Overall verdict one-liner. -->",
            "",
            "## Findings",
            "",
            "### critical",
            "",
            "<!-- P0 issues that must be addressed before merge. -->",
            "",
            "### major",
            "",
            "<!-- Significant issues requiring fixes. -->",
            "",
            "### minor",
            "",
            "<!-- Suggestions and improvements. -->",
            "",
            "### nitpick",
            "",
            "<!-- Style / polish items. -->",
            "",
            "## Verdict",
            "",
            "<!-- APPROVED | APPROVED_WITH_NOTES | REQUIRES_CHANGES | REJECTED -->",
            "",
        ]
    return "\n".join(fm_lines + body_lines)


# ---------------------------------------------------------------------------
# Output path containment (security)
# ---------------------------------------------------------------------------

def _safe_output_roots() -> list:
    """Return realpath-resolved list of allowed write roots for --out path containment.

    Safe roots:
      - Git repo root of cwd (allows repo-relative paths: docs/plans/..., state/handoffs/...).
      - Coordinator state roots (per-repo and central) — may point to claude-klabauter sibling repo
        when the seam redirects state/ paths (placement law, AC7 / C10 stop-the-rot plan).
      - The platform temp dir (``tempfile.gettempdir()``) — resolves to $TMPDIR/
        /var/folders/... on macOS, /tmp on Linux, and %TEMP%
        (...\\AppData\\Local\\Temp) on Windows, so this one call is the
        cross-platform source of truth rather than three POSIX-only env/path
        checks that silently never matched a Windows temp path.
      - $TMPDIR env var explicitly (kept alongside tempfile.gettempdir() in case
        it's set to something tempfile itself wouldn't resolve to).
      - /tmp and /var/folders (POSIX fixed paths; harmless no-ops on Windows).

    Spec backlink: pln-stop-the-rot-claude-klabauter-state-home-placement-4cc787 § C10 / AC7
    """
    roots = []
    repo_root = _current_repo_root()
    if repo_root:
        roots.append(os.path.realpath(repo_root))
    # Placement law (AC7): coordinator_state_root may redirect state/ paths to claude-klabauter.
    # Add both the per-repo and central state roots so seam-routed paths pass containment.
    for _central in (False, True):
        _sr = _resolve_state_root(central=_central)
        if _sr:
            try:
                # The state root is a subdirectory (e.g. /claude-klabauter/state); we want the
                # parent repo root as the allowed root so any subpath passes containment.
                roots.append(os.path.realpath(os.path.dirname(_sr)))
            except OSError:
                pass
    try:
        roots.append(os.path.realpath(tempfile.gettempdir()))
    except OSError:
        pass
    tmpdir = os.environ.get("TMPDIR", "")
    if tmpdir:
        try:
            roots.append(os.path.realpath(tmpdir))
        except OSError:
            pass
    # /tmp and /var/folders — resolve in case of symlinks (e.g. /tmp → /private/tmp on macOS).
    for fixed in ("/tmp", "/var/folders"):
        try:
            roots.append(os.path.realpath(fixed))
        except OSError:
            pass
    return roots


def _assert_output_safe(out_path: str) -> None:
    """Fail loud (sys.exit 1) if out_path resolves outside the safe write roots.

    Resolves both the candidate path and each root via os.path.realpath (follows
    symlinks and collapses '..') before comparing, preventing path-traversal via
    '../../' sequences or symlink chains. Uses os.path.normcase for cross-platform
    case-insensitive comparison on Windows.

    Called on the resolved out_path immediately after it is finalised — before any
    os.makedirs or open() call — so no directory or file is ever created at a
    rejected destination.

    Security note: do NOT add a fallback that silently allows the write. Any path
    outside the safe roots is unconditionally rejected regardless of other checks.
    """
    resolved = os.path.realpath(os.path.abspath(out_path))
    norm_resolved = os.path.normcase(resolved)
    for root in _safe_output_roots():
        norm_root = os.path.normcase(root)
        if norm_resolved == norm_root or norm_resolved.startswith(norm_root + os.sep):
            return  # within a safe root — proceed
    print(
        f"error: --out path '{out_path}' resolves to '{resolved}', "
        "which is outside all allowed write roots "
        "(git repo root, platform temp dir, $TMPDIR, /tmp, /var/folders). "
        "Refusing to write.",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Output path helpers
# ---------------------------------------------------------------------------

def _default_output_path(
    doc_type: str,
    title: str,
    topic: str | None,
    plan_stem: str | None = None,
    system: str | None = None,
    stub_id: str | None = None,
    chunk_id: str | None = None,
    slice_id: str | None = None,
    scope: str | None = None,
    dr_id: str | None = None,
) -> str:
    """Compute the default output path for a scaffolded document.

    Paths are repo-root-relative defaults, anchored to repo-root at write time
    in main() via _current_repo_root():
      handoff/spinoff/recovery -> state/handoffs/YYYY-MM-DD-<slug>.md
      roadmap-baton  -> state/handoffs/YYYY-MM-DD_000000_roadmap-<stub_id>.md
                         (HHMMSS=000000 fallback; use --out to supply the full path at runtime)
      memo             -> YYYY-MM-DD-<topic>.md  (local draft, not in cross-repo/inbox/)
      plan             -> docs/plans/YYYY-MM-DD-<slug>.md
      decision         -> docs/decisions/<dr_id>-<slug>.md  (dr_id allocated by
                          _allocate_dr_number before this call — never a DR-XXX
                          placeholder; see docs/decisions/DR-XXX collision memo)
      audit-record     -> docs/architecture/audit-records/YYYY-MM-DD-<system>.md
      sidecar types    -> docs/plans/<plan_stem>.<suffix>.md  (single-.md canonical form, D5)
      run-report       -> NO DEFAULT. --out is REQUIRED for --type run-report (and its
                          --type flight-recorder alias). The retired tasks/<plan-slug>/flight/
                          guess was removed (DEC-3 subsume, docs/plans/2026-07-13-subagent-
                          run-report-subsume.md § C4 defect3) — the universal sidecar now
                          lives under state/subagent-share/, and the engine's provision_report
                          owns real path computation at spawn time; a manual scaffold invocation
                          must not silently guess a session-scoped path. main() enforces the
                          --out requirement before this function is ever reached for run-report.
      subagent-sidecar -> NO DEFAULT, same rationale as run-report — --out is REQUIRED
                          (main() enforces this before this function is reached).
      review-findings  -> state/subagent-share/<session-id>/YYYY-MM-DD-codereview-slice<ID>-<SLUG>.md
                         (the DR-091 home; session-id from _resolve_session_id(), sanitized
                         via _sanitize_session_segment(); slice_id from --slice; SLUG from
                         _slug_from_scope(scope))
    """
    today = _today()
    if doc_type in ("handoff", "spinoff", "recovery", "goal-seed", "roadmap-seed"):
        slug = _slug_from_title(title)
        return os.path.join("state", "handoffs", f"{today}-{slug}.md")
    elif doc_type == "roadmap-baton":
        # Canonical path includes real HHMMSS (see SKILL.md § Step 2.1); 000000 is the
        # best-effort fallback when --out is omitted. Use --out to supply the full path.
        id_slug = stub_id if stub_id else _slug_from_title(title)
        return os.path.join("state", "handoffs", f"{today}_000000_roadmap-{id_slug}.md")
    elif doc_type == "memo":
        slug = topic if topic else _slug_from_title(title)
        return f"{today}-{slug}.md"
    elif doc_type == "plan":
        slug = _slug_from_title(title)
        return os.path.join("docs", "plans", f"{today}-{slug}.md")
    elif doc_type == "decision":
        slug = _slug_from_title(title)
        prefix = dr_id or "DR-XXX"  # dr_id always set by main() before this call; fallback is defensive only
        return os.path.join("docs", "decisions", f"{prefix}-{slug}.md")
    elif doc_type == "audit-record":
        # Review: code-reviewer F7 — `or "SYSTEM"` fallback was dead; args.system is guaranteed
        # non-None for audit-record by the validation block in main() that exits 1 if absent.
        sys_slug = system
        return os.path.join("docs", "architecture", "audit-records", f"{today}-{sys_slug}.md")
    elif doc_type == "problem-set":
        slug = _slug_from_title(title)
        return os.path.join("docs", "problems", f"{today}-{slug}.md")
    elif doc_type == "completion":
        slug = _slug_from_title(title)
        month = today[:7]  # YYYY-MM
        return os.path.join("archive", "completed", month, f"{today}-{slug}.md")
    elif doc_type == "goal":
        slug = _slug_from_title(title)
        return os.path.join("state", "goals", f"{today}-{slug}.yaml")
    elif doc_type == "sizing-object":
        slug = _slug_from_title(title)
        return os.path.join("state", "sizings", f"{today}-{slug}.yaml")
    elif doc_type == "health-status":
        return os.path.join("state", "health", f"{today}-health-summary.md")
    elif doc_type == "strategic-self-description":
        # Single canonical per-repo path (schema applies_to) — not date/slug-derived,
        # this artifact class is one-per-repo, never one-per-day.
        return os.path.join("state", "strategic", "self-description.yaml")
    elif doc_type == "research-synthesis":
        slug = _slug_from_title(title)
        return os.path.join("docs", "research", f"{today}-{slug}.md")
    elif doc_type in _SIDECAR_TYPES:
        stem = plan_stem or "PLAN-STEM"
        # review F3 — use manifest-derived dict; new sidecar types auto-populate suffix field
        # in the manifest rather than requiring a matching edit to a local static dict here.
        suffix = _SIDECAR_SUFFIXES[doc_type]
        return os.path.join("docs", "plans", f"{stem}.{suffix}.md")
    elif doc_type == "review-findings":
        sid = slice_id or "SLICE"
        scp = scope or "SCOPE"
        scope_slug = _slug_from_scope(scp)
        session_id = _sanitize_session_segment(_resolve_session_id())
        return os.path.join(
            "state", "subagent-share", session_id,
            f"{today}-codereview-slice{sid}-{scope_slug}.md",
        )
    # Unknown type guarded upstream; unreachable.
    # Review: code-reviewer — F4: raise AssertionError matches main()/_scaffold_sidecar pattern; silent wrong-path fallback was a hazard.
    raise AssertionError(f"unreachable doc_type in _default_output_path: {doc_type!r}")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for coordinator-doc-new."""
    parser = argparse.ArgumentParser(
        prog="coordinator-doc-new",
        description=(
            "Scaffold a conformant coordinator document (handoff, spinoff, memo, "
            "plan, decision, or sidecar) with canonical frontmatter + section skeleton. "
            "The EM fills the body via Edit after scaffolding."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:

  # Session-continuation handoff:
  coordinator-doc-new --type handoff --title "Ship coordinator-doc-new scaffolder"

  # Workstream-fork spinoff:
  coordinator-doc-new --type spinoff --title "Migrate consumers to new baton shape" \\
      --out state/handoffs/2026-06-25-consumer-baton-migration.md

  # Local memo skeleton (fill body, then send via cross-repo-memo):
  coordinator-doc-new --type memo --to project-rag-em --topic rag-liveness-query \\
      --title "Query liveness predicate contract" \\
      --out state/memo-outbox/2026-06-25-rag-liveness-query.md

  # Architecture audit record (requires --system):
  coordinator-doc-new --type audit-record --system coordinator-runtime

  # Workflow skeleton (delegates to claude-klabauter's workflow.scaffold op via
  # coordinator-workflow-scaffold.py):
  coordinator-doc-new --type workflow --name migrate-baton-shape \\
      --description "Migrate consumers to the new baton shape" \\
      --phase "Survey::Enumerate every baton writer/reader" \\
      --phase "Migrate::Land the new shape behind a flag" \\
      --pattern disk-poll-fanout \\
      --out state/scratch/migrate-baton-shape.workflow.js

Spec backlink: docs/plans/2026-06-25-example-initiative-tc-0-canonical-baton-shape.md § C4
Spec backlink (workflow): pln-workflow-skeleton-stamper-maki-adab0d
""",
    )

    parser.add_argument(
        "--type",
        required=True,
        dest="doc_type",
        metavar="TYPE",
        help=(
            f"Document type to scaffold. Known types: {', '.join(sorted(_KNOWN_TYPES))}. "
            "Fail-loud (exit 1) on unknown type."
        ),
    )
    parser.add_argument(
        "--title",
        default=None,
        metavar="TEXT",
        help=(
            "Document title. Defaults to a placeholder when omitted. "
            "Required conceptually for memo (used as summary fallback). "
            "(strategic-self-description: seeds repo_identity.repo)"
        ),
    )
    parser.add_argument(
        "--out",
        default=None,
        metavar="PATH",
        help=(
            "Output file path. Defaults to the canonical path for each type: "
            "state/handoffs/YYYY-MM-DD-<slug>.md (handoff/spinoff), "
            "YYYY-MM-DD-<topic>.md (memo), docs/plans/YYYY-MM-DD-<slug>.md (plan), "
            "docs/decisions/DR-NNN-<slug>.md (decision, DR-NNN allocated + collision-checked), "
            "docs/architecture/audit-records/YYYY-MM-DD-<system>.md (audit-record), "  # Review: code-reviewer F8 — added missing audit-record default path
            "docs/plans/<stem>.<suffix>.md (sidecar types), "
            "docs/research/YYYY-MM-DD-<slug>.md (research-synthesis), "  # Review: code-reviewer Slice-B F5 — research-synthesis default path
            "state/subagent-share/<session-id>/YYYY-MM-DD-codereview-sliceID-SLUG.md (review-findings), "
            "state/strategic/self-description.yaml (strategic-self-description — single canonical per-repo path, not date/slug-derived). "
            "run-report (and its flight-recorder alias) has NO default — --out is REQUIRED."
        ),
    )

    # Handoff / spinoff fields.
    parser.add_argument(
        "--branch",
        default=None,
        metavar="NAME",
        help=(
            "(handoff, spinoff) Git branch name for the branch: frontmatter field. "
            "Auto-detected from cwd when omitted."
        ),
    )

    # Memo fields.
    parser.add_argument(
        "--to",
        default=None,
        metavar="RECEIVER",
        help="(memo) Receiver EM identity (e.g. project-rag-em). Required for --type memo.",
    )
    parser.add_argument(
        "--topic",
        default=None,
        metavar="SLUG",
        help=(
            "(memo) Filename slug for the memo. Lowercase alphanumeric + dashes. "
            "Required for --type memo."
        ),
    )
    parser.add_argument(
        "--from-repo",
        dest="from_repo",
        default=None,
        metavar="REPO",
        help=(
            "(memo) Override the auto-resolved from_repo sender identity "
            "(default: resolved from cwd git root via machine-local)."
        ),
    )

    # Sidecar and run-report fields.
    parser.add_argument(
        "--plan",
        default=None,
        metavar="STEM_OR_PATH",
        help=(
            "(sidecar types: review, prior-art-check, plan-coverage-check, docs-check) "
            "Bare plan filename stem used to derive the sidecar output path and the plan: "
            "frontmatter field. Example: '2026-06-25-my-plan' → output "
            "docs/plans/2026-06-25-my-plan.<suffix>.md, frontmatter plan: docs/plans/2026-06-25-my-plan.md. "
            "Required for all sidecar types. "
            "(run-report, alias flight-recorder) Full repo-relative plan path (e.g. "
            "docs/plans/2026-06-09-foo.md). Used as the plan: frontmatter field; slug "
            "is derived by stripping the YYYY-MM-DD- prefix and .md suffix from the basename. "
            "Required for --type run-report (or its --type flight-recorder alias). "
            "(subagent-sidecar) Same usage as run-report above. Required for --type "
            "subagent-sidecar."
        ),
    )
    parser.add_argument(
        "--chunk",
        default=None,
        metavar="ID",
        help=(
            "(run-report, alias flight-recorder) Chunk identifier matching the dispatch "
            "ledger row (e.g. C1-executor-prompt). Sets the chunk: frontmatter field. "
            "Output path has no default — pass --out explicitly (the live run-report "
            "sidecar lives under state/subagent-share/, computed by claude-klabauter's "
            "provision_report engine at spawn time). "
            "Required for --type run-report (or its --type flight-recorder alias). "
            "(subagent-sidecar) Same usage as run-report above. Required for --type "
            "subagent-sidecar."
        ),
    )
    parser.add_argument(
        "--agent-type",
        dest="agent_type",
        default=None,
        metavar="TYPE",
        help=(
            "(run-report, alias flight-recorder) Universal agent_type: frontmatter "
            "field naming the spawned subagent kind (e.g. executor, review-integrator, "
            "code-reviewer). Optional — defaults to 'executor', the shape every "
            "flight-recorder-style /execute-plan chunk dispatch uses. "
            "(subagent-sidecar) Same usage as run-report above. Optional for --type "
            "subagent-sidecar."
        ),
    )

    # Audit-record fields.
    parser.add_argument(
        "--system",
        default=None,
        metavar="NAME",
        help=(
            "(audit-record) System name slug for the audit record. Lowercase alphanumeric + dashes. "
            "Used as the system: frontmatter field and in the default output filename. "
            "Required for --type audit-record."
        ),
    )

    # Decision fields.
    parser.add_argument(
        "--dr-prefix",
        default=None,
        metavar="PREFIX",
        dest="dr_prefix",
        help=(
            "(decision) Explicit DR-number namespace prefix (e.g. 'PLATFORM' for "
            "DR-PLATFORM-NNN). Uppercase alphanumeric only. When omitted, the prefix "
            "is inferred from the shared prefix of existing docs/decisions/DR-*.md files "
            "(no prefix, i.e. plain DR-NNN, when existing records are unprefixed or the "
            "directory is empty/mixed)."
        ),
    )

    # Completion fields.
    parser.add_argument(
        "--nature",
        default="infra",
        metavar="NATURE",
        help=(
            "(completion) Work-category for the completion entry. "
            f"One of: {', '.join(_COMPLETION_NATURE_ENUM)}. "
            "Default: infra."
        ),
    )
    parser.add_argument(
        "--chain",
        default=None,
        metavar="SLUG",
        help=(
            "(completion) Optional chain slug (plan path, handoff path, or workstream slug) "
            "for the chain: frontmatter field. Omit for standalone (non-chain) entries."
        ),
    )

    # Review-findings fields.
    parser.add_argument(
        "--slice",
        dest="slice_id",
        default=None,
        metavar="ID",
        help=(
            "(review-findings) Slice identifier for this review (e.g. A, B, Z, 2a). "
            "Alphanumeric + dashes (uppercase allowed). Used in the output filename: "
            "state/subagent-share/<session-id>/YYYY-MM-DD-codereview-sliceID-SLUG.md. "
            "Required for --type review-findings."
        ),
    )
    parser.add_argument(
        "--scope",
        default=None,
        metavar="COMMA_PATHS",
        help=(
            "(review-findings) Comma-separated scope paths this review slice covers "
            "(e.g. 'bin/foo.sh,lib/bar.py'). Displayed in the sidecar heading and "
            "sanitized into the output filename SLUG. "
            "Required for --type review-findings."
        ),
    )

    # Deliverable-spine fields (handoff, spinoff, roadmap-baton, plan) — C3b.
    parser.add_argument(
        "--deliverable-id",
        dest="deliverable_id",
        default=None,
        metavar="ID",
        help=(
            "(handoff, spinoff, roadmap-baton, plan) Existing deliverable_id to carry "
            "(never re-mint). When omitted, auto-inherited from the DELIVERABLE_ID env var "
            "(session context); if neither is set, a new id is minted. "
            "Spec: docs/plans/2026-07-03-fleet-deliverable-spine-identity-and-facets.md § D1"
        ),
    )
    parser.add_argument(
        "--new-chain",
        dest="new_chain",
        action="store_true",
        help=(
            "Root a NEW deliverable, suppressing session-chain discovery. With no "
            "--deliverable-id and no other carry rung, the scaffolder joins the chain "
            "of the handoff this session holds a claim on, so two artifacts of one "
            "deliverable stop minting two ids off two title slugs. Pass this when the "
            "artifact genuinely starts its own chain while a claim on another is still "
            "held. Inert for spinoff and roadmap-baton, which mint their own identity "
            "either way. "
            "Spec: state/bug-backlog/2026-08-25-deliverable-id-minted-from-title-not-"
            "discovered-d2b445e3e44a.yaml"
        ),
    )
    parser.add_argument(
        "--initiative",
        dest="initiative",
        default=None,
        metavar="INITIATIVE_ID",
        help=(
            "(handoff, spinoff, roadmap-baton, plan) Initiative FK "
            "(state/initiatives/<id>.yaml). Nullable — omit or leave unset when this work "
            "does not belong to a named initiative. Also read from INITIATIVE_ID env var. "
            "Spec: docs/plans/2026-07-03-fleet-deliverable-spine-identity-and-facets.md § D2"
        ),
    )
    parser.add_argument(
        "--sizing-object",
        dest="sizing_object",
        default=None,
        metavar="PATH",
        help=(
            "(plan, roadmap-baton) Path to the state/sizings/<id>.yaml this record was "
            "sized against. "
            "When supplied, must resolve on disk (relative to the repo root) — the "
            "scaffolder fails loud and writes no file otherwise. When omitted, the "
            "commented-optional-key skeleton is unchanged. Route a missing sizing "
            "object through coordinator:sizing, never a hand-authored stub. "
            "Spec: docs/plans/2026-08-06-plan-sizing-citation-gate.md § AC2, AC3"
        ),
    )
    parser.add_argument(
        "--problem-set",
        dest="problem_set",
        default=None,
        metavar="SLUG_OR_INLINE",
        help=(
            "(plan) Ratified problem-set slug, or the literal 'inline'. "
            "When supplied, emitted as a real problem_set frontmatter key in place of "
            "the commented template line. Optional — omitted leaves the existing "
            "commented-optional-key skeleton unchanged (no --no-problem-set pairing; "
            "unlike --sizing-object this key is never required). "
            "Spec: docs/plans/2026-08-21-engine-half-of-the-roadmap-sprint-spine-split.md § C7"
        ),
    )
    parser.add_argument(
        "--no-sizing-object",
        dest="no_sizing_object",
        action="store_true",
        help=(
            "(plan, roadmap-baton) The sanctioned declaration that this record has no "
            "sizing object — "
            "not a bypass. Emits an explicit sizing_object: null frontmatter key. "
            "Exactly one of --sizing-object / --no-sizing-object is required for "
            "--type plan and --type roadmap-baton; a missing sizing object is "
            "produced via coordinator:sizing, "
            "never invented. "
            "Spec: docs/plans/2026-08-06-sizing-citation-absence-is-checkable.md, chunk C1"
        ),
    )
    parser.add_argument(
        "--category",
        dest="category",
        default=None,
        choices=_HANDOFF_CATEGORY_ENUM,
        metavar="CATEGORY",
        help=(
            "(handoff, recovery, spinoff, roadmap-baton, goal-seed, "
            "roadmap-seed) Workstream category: frontmatter field. "
            f"One of: {', '.join(_HANDOFF_CATEGORY_ENUM)}. Validated against the "
            "handoff schema's category enum before the file is written — fails "
            "loud, naming all legal values, on an unknown value. Defaults to each "
            "type's own established literal ('roadmap' for roadmap-baton and "
            "roadmap-seed, 'infra' for the rest) when omitted — NOT "
            "the same field as --nature (completion's work-category; a different "
            "field on a different record family). "
            "Spec: cross-repo/inbox/2026-07-23-example-cockpit-repo-em-coordinator-doc-new-category-no-validation.md"
        ),
    )
    parser.add_argument(
        "--summary",
        dest="summary",
        default=None,
        metavar="TEXT",
        help=(
            "(handoff) One-line session summary: frontmatter field. Replaces the "
            "hardcoded placeholder summary when supplied; the placeholder is "
            "emitted unchanged when omitted. Refused fail-loud (not silently "
            "truncated) when blank or over the handoff schema's 140-char cap — "
            "the caller fixes it here rather than authoring frontmatter the "
            "validator will then reject. Handoff-scoped: refused fail-loud for "
            "every other --type. "
            "Spec: docs/plans/2026-08-19-promote-fills-its-own-placeholders.md"
        ),
    )
    parser.add_argument(
        "--gated-open",
        dest="gated_open",
        default=None,
        metavar="BLOCKED_BY_ID",
        help=(
            "(handoff) Declare the blocker, not the readiness: writes "
            "blocked_by: [BLOCKED_BY_ID] and DERIVES deployment_state/"
            "pickup_ready from it via reconcile.gate_eval.derive_readiness "
            "(C1) -- an unresolved id derives awaiting_gate/pickup_ready:false. "
            "Omitted -> blocked_by: [] derives ready_to_fire/pickup_ready:true, "
            "byte-identical to today. Prose reasons belong in --gate-note "
            "instead (advisory only, never flips readiness -- 2026-08-19 "
            "ruling); the two are independent and may be combined. Refused "
            "fail-loud when blank. Handoff-scoped: refused fail-loud for every "
            "other --type. "
            "Spec: docs/plans/2026-08-19-gate-notes-are-advisory-blocked-by-derives-readiness.md § C3"
        ),
    )
    parser.add_argument(
        "--gate-note",
        dest="gate_note",
        default=None,
        metavar="TEXT",
        help=(
            "(handoff) Advisory gate note: writes blocking_notes: <TEXT> ONLY -- "
            "it is prose and per the 2026-08-19 ruling must NEVER flip readiness; "
            "only --gated-open may. Legal alone (baton stays pickup_ready) and "
            "legal combined with --gated-open (a blocked baton that also carries "
            "a note). Refused fail-loud when blank. Handoff-scoped: refused "
            "fail-loud for every other --type. "
            "Spec: docs/plans/2026-08-19-gate-notes-are-advisory-blocked-by-derives-readiness.md § C3"
        ),
    )
    parser.add_argument(
        "--gated-predicate",
        dest="gated_predicate",
        default=None,
        metavar="REASON",
        help=(
            "(handoff) Park this baton on a MECHANICAL condition that has no "
            "graph node to name -- DR-173's unfilled category/summary is the "
            "one caller. Emits awaiting_gate + pickup_ready: false + "
            "blocking_notes: <REASON>, and deliberately NO blocked_by: forcing "
            "a prose reason into blocked_by mints an entry nothing can ever "
            "resolve, parking the baton permanently even once the condition "
            "clears. The predicate parks it; the note only explains why, and "
            "deleting the note would not unpark it. Refused fail-loud when "
            "blank, and handoff-scoped like the other two. "
            "Spec: docs/plans/2026-08-19-gate-notes-are-advisory-blocked-by-derives-readiness.md § C9"
        ),
    )
    parser.add_argument(
        "--recovers-session",
        dest="recovers_session",
        default=None,
        metavar="SESSION_ID",
        help=(
            "(recovery) Crashed session id being reconstructed (recovers_session: "
            "frontmatter field). Optional — omit to fill in later via Edit once the "
            "crashed session id is known. "
            # Review: code-reviewer — parity with --deliverable-id/--initiative/--roadmap-id;
            # every other fill-after-scaffold optional field has a CLI override (Finding 1).
        ),
    )
    parser.add_argument(
        "--origin-handoff-id",
        dest="origin_handoff_id",
        default=None,
        metavar="HND_ID",
        help=(
            "(handoff, recovery, spinoff, goal-seed, roadmap-seed) "
            "ID-companion (C2) for origin_handoff: — the originating baton's handoff_id, "
            "carried as-is (never resolved or minted here). The calling skill resolves "
            "this by reading handoff_id off the artifact origin_handoff names. Omitted "
            "entirely (not null) when not supplied. "
            "Spec: cross-repo memo 2026-07-22-claude-klabauter-em-c2-id-companions (ask 1); "
            "docs/plans/2026-07-08-lifecycle-vocab-c2-durable-links-rollup.md § C2"
        ),
    )
    parser.add_argument(
        "--predecessor",
        dest="predecessor",
        default=None,
        metavar="PATH",
        help=(
            "(handoff ONLY) Repo-relative path to the baton this handoff continues "
            "— the path field --predecessor-id companions. Carried as-is verbatim: "
            "never resolved, validated, or minted here; the calling engine "
            "(baton_assemble) decides which path this names. Omitted -> the field "
            "stays the literal 'predecessor: none' scaffold default, byte-identical "
            "to every existing caller that does not pass it. NOT accepted for the "
            "spinoff kinds (predecessor:none-by-design, schema rule A3a-3) nor for "
            "--type recovery, whose own 'predecessor:' means a crashed commit SHA "
            "(or null) and never a baton path — see _scaffold_recovery's docstring. "
            "Supplying --predecessor-id without this flag is refused."
        ),
    )
    parser.add_argument(
        "--additional-predecessor",
        dest="additional_predecessors",
        action="append",
        default=None,
        metavar="PATH",
        help=(
            "(handoff ONLY) Repeatable. Repo-relative path to a fan-in predecessor "
            "beyond the primary --predecessor — the successor-side down-edge matching "
            "the up-edges the engine already stamps on every fan-in leg. Carried as-is "
            "verbatim, on the same terms as --predecessor: never resolved or minted "
            "here. Omitted -> the field is absent entirely, byte-identical to every "
            "existing caller that does not pass it. NOT accepted for the spinoff kinds "
            "(predecessor:none-by-design, schema rule A3a-3) nor for --type recovery, "
            "whose own 'predecessor:' is a crashed commit SHA and whose scaffold emits "
            "its own additional_predecessors: [] literal. An entry duplicating another "
            "entry, or duplicating --predecessor, is refused (schema cross-field rule "
            "_cf_additional_predecessors_integrity is exact-string, so callers must "
            "normalize before passing)."
        ),
    )
    parser.add_argument(
        "--deliverable-ids",
        dest="deliverable_ids",
        action="append",
        default=None,
        metavar="ID",
        help=(
            "(handoff ONLY) Repeatable, one deliverable_id per occurrence — NOT "
            "comma-joined (a comma-split would re-introduce the quoting seam the "
            ".cmd launcher already mangles). Carried as-is verbatim: never resolved "
            "or minted here. Emitted as a YAML block sequence (deliverable_ids:) "
            "ONLY when this flag is supplied at all; omitted entirely (not [], not "
            "null) when not supplied, matching additional_predecessors' optional-omit "
            "convention. Distinct from the singular --deliverable-id, which this flag "
            "does not route through."
        ),
    )
    parser.add_argument(
        "--plan-ids",
        dest="plan_ids",
        action="append",
        default=None,
        metavar="ID",
        help=(
            "(handoff ONLY) Repeatable, one plan_id per occurrence — NOT "
            "comma-joined, same rationale as --deliverable-ids. Carried as-is "
            "verbatim: never resolved or minted here. Emitted as a YAML block "
            "sequence (plan_ids:) ONLY when this flag is supplied at all; omitted "
            "entirely (not [], not null) when not supplied, matching "
            "additional_predecessors' optional-omit convention."
        ),
    )
    parser.add_argument(
        "--predecessor-id",
        dest="predecessor_id",
        default=None,
        metavar="HND_ID",
        help=(
            "(handoff, recovery, spinoff, goal-seed, roadmap-seed) "
            "ID-companion (C2) for predecessor: — the predecessor's handoff_id, "
            "carried as-is (never resolved or minted here). The calling skill resolves "
            "this by reading handoff_id off the artifact predecessor names. Omitted "
            "entirely (not null) when not supplied. "
            "Spec: cross-repo memo 2026-07-22-claude-klabauter-em-c2-id-companions (ask 1); "
            "docs/plans/2026-07-08-lifecycle-vocab-c2-durable-links-rollup.md § C2"
        ),
    )

    # Roadmap-baton fields.
    parser.add_argument(
        "--roadmap-id",
        dest="roadmap_id",
        default=None,
        metavar="SLUG",
        help=(
            "(roadmap-baton) Roadmap run identifier (roadmap_id: frontmatter field). "
            "Lowercase alphanumeric + dashes. Groups all stubs from one roadmap-planning "
            "invocation. Defaults to placeholder-rm when omitted."
        ),
    )
    parser.add_argument(
        "--stub-id",
        dest="stub_id",
        default=None,
        metavar="SLUG",
        help=(
            "(roadmap-baton) Globally-unique stub code (stub_id: frontmatter field). "
            "Format: <roadmap-prefix>-<N> (e.g. my-rm-1). Lowercase alphanumeric + dashes. "
            "Defaults to placeholder-stub-1 when omitted."
        ),
    )

    # Goal-seed / roadmap-seed fields.
    parser.add_argument(
        "--goals",
        dest="goals",
        default=None,
        metavar="GOAL_ID[,GOAL_ID...]",
        help=(
            "(goal-seed, roadmap-seed) Comma-separated goal-id FK(s) "
            "(origin_goal_id: frontmatter field — array; each entry must be goal- "
            "prefixed, e.g. goal-shipping-velocity). Required for "
            "roadmap-seed (SKILL.md § Step 5a); optional for goal-seed "
            "(deferred vision-slices may not yet be tagged to a ratified goal)."
        ),
    )
    parser.add_argument(
        "--gate-dependency",
        dest="gate_dependency",
        default=None,
        metavar="TEXT",
        help=(
            "(roadmap-baton, goal-seed, roadmap-seed) One-line, subsystem-named "
            "gate_dependency: frontmatter field (deprecated; superseded by "
            "blocked_by/blocking_notes). deployment_state=awaiting_gate (the "
            "default for all three types) requires at least one of "
            "gate_dependency, blocked_by, or blocking_notes. When omitted, the "
            "scaffold writes a blocking_notes placeholder instead — fill via "
            "Edit before the stub is pickup-ready."
        ),
    )

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point for coordinator-doc-new CLI."""
    # A4 — Early delegation for queue and lesson types.
    # MUST run before parser.parse_args() because queue-type flags (--body, --risk,
    # --severity, --change-kind, etc.) are not known to this parser — argparse would
    # reject them with "unrecognized arguments" before we could route to the delegate.
    # Both delegation functions call sys.exit() so control does not return here.
    # Spec backlink: docs/plans/2026-06-25-example-initiative-tc-4-fleet-machinery-contract-emit.md § A4
    _early_type = _peek_doc_type()
    if _early_type in _QUEUE_TYPES:
        _delegate_to_queue_append(_early_type)  # calls sys.exit() — does not return
    if _early_type == "lesson":
        _delegate_to_lesson_promote()  # calls sys.exit() — does not return
    if _early_type == "workflow":
        _delegate_to_workflow_scaffold()  # calls sys.exit() — does not return

    parser = _build_parser()
    args = parser.parse_args()

    doc_type = args.doc_type

    # --type spinoff-goal / spinoff-roadmap / spinoff-roadmap-creator are
    # BACKWARD-COMPAT ALIASES for --type goal-seed / roadmap-baton / roadmap-seed —
    # the baton-kind-vocabulary migration renamed the `kind:` values these scaffold
    # to goal-seed/roadmap-baton/roadmap-seed (the `spinoff-` prefix asserted a
    # roadmap baton was a kind of spinoff, which is false); this CLI's --type enum
    # is renamed to match. The legacy spellings are kept working permanently — not
    # a deprecation timer — because this manifest is percolated to the OSS mirror
    # and vendored into every fleet repo, and either side of that skew (newer skill
    # + older manifest, or the reverse) needs both spellings to keep scaffolding.
    # Normalize here, before the known-type gate and every doc_type branch below,
    # mirroring the --type flight-recorder alias pattern immediately below.
    # Routed through `baton_class.canonical_kind()` (see the module-level
    # best-effort import above) rather than a local literal alias dict — that
    # dict would re-pair a retired `kind` value with its D1 successor outside
    # `baton_class.py`, exactly what
    # `coordinator_core/tests/test_baton_class_is_the_only_membership_set.py`
    # forbids.
    # Spec backlink: docs/plans/2026-07-29-baton-kind-vocabulary-one-axis-per-field.md
    _canonical_type = _canonical_kind(doc_type) if _canonical_kind is not None else doc_type
    if _canonical_type and _canonical_type != doc_type:
        print(
            f"note: --type {doc_type} is a legacy alias — the canonical name is "
            f"--type {_canonical_type}. Both keep working; consider updating the caller.",
            file=sys.stderr,
        )
        doc_type = _canonical_type

    # --type flight-recorder is a BACKWARD-COMPAT ALIAS for --type run-report (C4 —
    # the run-report scaffolder is the superset emitter; flight-recorder is
    # migrated onto it, not reimplemented separately). Normalize here, before the
    # known-type gate and every doc_type branch below, so in-flight callers
    # (fan-out-dispatch.sh, pre-C5 executors) that still pass --type flight-recorder
    # keep working unchanged.
    # Spec backlink: docs/plans/2026-07-13-subagent-run-report-subsume.md § C4
    if doc_type == "flight-recorder":
        doc_type = "run-report"

    # Fail-loud on unknown --type — emit the full known set.
    if doc_type not in _KNOWN_TYPES:
        known = ", ".join(sorted(_KNOWN_TYPES))
        print(
            f"error: unknown --type '{doc_type}'. "
            f"Known types: {known}.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Resolve title default.
    title = args.title
    if not title:
        if doc_type == "handoff":
            title = "PLACEHOLDER — replace with one-line handoff title"
        elif doc_type == "recovery":
            title = "PLACEHOLDER — replace with one-line recovery handoff title"
        elif doc_type == "spinoff":
            title = "PLACEHOLDER — replace with one-line spinoff title"
        elif doc_type == "roadmap-baton":
            title = "PLACEHOLDER — replace with one-line roadmap-baton stub title"
        elif doc_type == "plan":
            title = "PLACEHOLDER — replace with one-line plan title"
        elif doc_type == "decision":
            title = "PLACEHOLDER — replace with one-line decision title"
        elif doc_type == "audit-record":
            title = "PLACEHOLDER — replace with one-line audit record title"
        elif doc_type == "problem-set":
            title = "PLACEHOLDER — replace with one-line problem title"
        elif doc_type == "completion":
            title = "PLACEHOLDER — replace with past-tense workstream title"
        elif doc_type == "health-status":
            title = f"Health Summary {_today()}"
        elif doc_type == "run-report":
            title = ""  # run-report has no title field; placeholder unused
        elif doc_type == "subagent-sidecar":
            title = ""  # subagent-sidecar has no title field; placeholder unused
        elif doc_type == "review-findings":
            title = ""  # review-findings has no title field; heading derived from --slice/--scope
        elif doc_type == "research-synthesis":
            title = "PLACEHOLDER — replace with one-line research synthesis title"
        elif doc_type == "goal":
            title = "PLACEHOLDER — replace with one-line goal title"
        elif doc_type == "sizing-object":
            title = "PLACEHOLDER — replace with the PM's ask, verbatim"
        elif doc_type == "strategic-self-description":
            title = "PLACEHOLDER-repo"  # used as the repo_identity.repo placeholder value
        elif doc_type == "goal-seed":
            title = "PLACEHOLDER — replace with one-line goal-seed title"
        elif doc_type == "roadmap-seed":
            title = "PLACEHOLDER — replace with one-line roadmap-seed title"
        elif doc_type in _SIDECAR_TYPES:
            title = f"PLACEHOLDER — replace with {doc_type} sidecar title"
        else:
            title = "PLACEHOLDER — replace with memo title"

    # Validate memo-specific required fields.
    if doc_type == "memo":
        if not args.to:
            print("error: --to is required for --type memo.", file=sys.stderr)
            sys.exit(1)
        if not args.topic:
            print("error: --topic is required for --type memo.", file=sys.stderr)
            sys.exit(1)
        # Security: guard --to with the same slug allowlist as --topic.
        # The --to value is interpolated into an HTML comment in the memo scaffold body
        # (<!-- Send when ready: ... --to {to} ... -->); a value containing '-->'
        # would close the comment and inject arbitrary body text.
        to_slug = args.to
        if not _SLUG_RE.match(to_slug):
            print(
                f"error: --to '{to_slug}' is not a valid slug. "
                "Use lowercase alphanumeric + dashes, starting with alphanum.",
                file=sys.stderr,
            )
            sys.exit(1)
        topic_slug = args.topic
        if not _SLUG_RE.match(topic_slug):
            print(
                f"error: --topic '{topic_slug}' is not a valid slug. "
                "Use lowercase alphanumeric + dashes, starting with alphanum.",
                file=sys.stderr,
            )
            sys.exit(1)

    # Validate sidecar-specific required fields.
    if doc_type in _SIDECAR_TYPES:
        if not args.plan:
            print(
                f"error: --plan <stem> is required for --type {doc_type}.",
                file=sys.stderr,
            )
            sys.exit(1)
        # Review: code-reviewer slice-B F1 — parse-time allowlist guard: reject stems containing
        # path separators, dots, colons, newlines or any char outside [a-z0-9-].
        # Prevents path traversal (../../evil) and YAML-breaking values (:, newline).
        # _SLUG_RE (^[a-z0-9][a-z0-9-]*$) matches the canonical date-prefixed plan stem
        # format (e.g. "2026-06-25-my-plan") as well as simple slugs.
        if not _SLUG_RE.match(args.plan):
            print(
                f"error: --plan '{args.plan}' is not a valid plan stem. "
                "Use lowercase alphanumeric + dashes only (^[a-z0-9][a-z0-9-]*$). "
                "Path separators, dots, colons, and other metacharacters are not allowed.",
                file=sys.stderr,
            )
            sys.exit(1)

    # Validate run-report-specific required fields (doc_type is already normalized
    # from the flight-recorder alias by this point — see main()'s alias check above).
    if doc_type == "run-report":
        if not args.plan:
            print("error: --plan <path> is required for --type run-report.", file=sys.stderr)
            sys.exit(1)
        if not args.chunk:
            print("error: --chunk <id> is required for --type run-report.", file=sys.stderr)
            sys.exit(1)
        # Review: code-reviewer item-5 F1 — parse-time slug guard on --chunk mirrors the --plan guard for
        # sidecar types. Closes path-injection: without this, `--chunk ../../../x` reaches
        # os.path.join("tasks", plan_slug, "flight", f"{cid}.md") carrying the raw traversal.
        # _SLUG_RE (^[a-z0-9][a-z0-9-]*$) matches canonical chunk ids (e.g. "c1-executor-prompt").
        # _assert_output_safe is a second-layer catch; this is the parse-time first layer.
        if not _SLUG_RE.match(args.chunk):
            print(
                f"error: --chunk '{args.chunk}' is not a valid chunk id. "
                "Use lowercase alphanumeric + dashes only (^[a-z0-9][a-z0-9-]*$). "
                "Path separators, dots, colons, and other metacharacters are not allowed.",
                file=sys.stderr,
            )
            sys.exit(1)
        # --out is REQUIRED for run-report — the retired tasks/<plan-slug>/flight/<chunk-id>.md
        # default-path guess was removed (DEC-3 subsume, docs/plans/2026-07-13-subagent-run-
        # report-subsume.md § C4 defect3). The universal sidecar now lives under
        # state/subagent-share/, whose real path is computed by the engine's provision_report
        # at spawn time — a manual scaffold invocation must not silently guess a session-scoped
        # path. Fail loud instead of writing to a wrong/stale default.
        if not args.out:
            print(
                _missing_out_message("run-report (and its --type flight-recorder alias)"),
                file=sys.stderr,
            )
            sys.exit(1)

    # Validate subagent-sidecar-specific required fields — mirrors the
    # run-report validation block above (same slug-guard rationale: --plan
    # and --chunk feed the frontmatter directly and must not carry path-
    # traversal or YAML-breaking characters).
    if doc_type == "subagent-sidecar":
        if not args.plan:
            print("error: --plan <path> is required for --type subagent-sidecar.", file=sys.stderr)
            sys.exit(1)
        if not args.chunk:
            print("error: --chunk <id> is required for --type subagent-sidecar.", file=sys.stderr)
            sys.exit(1)
        if not _SLUG_RE.match(args.chunk):
            print(
                f"error: --chunk '{args.chunk}' is not a valid chunk id. "
                "Use lowercase alphanumeric + dashes only (^[a-z0-9][a-z0-9-]*$). "
                "Path separators, dots, colons, and other metacharacters are not allowed.",
                file=sys.stderr,
            )
            sys.exit(1)
        # --out is REQUIRED — the live sidecar path is computed by
        # coordinator_core.dispatch.provision at spawn time, exactly the same
        # rationale as --type run-report's --out requirement above.
        if not args.out:
            print(_missing_out_message("subagent-sidecar"), file=sys.stderr)
            sys.exit(1)

    # Validate audit-record-specific required fields.
    if doc_type == "audit-record":
        if not args.system:
            print("error: --system <name> is required for --type audit-record.", file=sys.stderr)
            sys.exit(1)
        # Guard --system with the slug allowlist — same rationale as --plan for sidecars.
        # System name is embedded in the YAML frontmatter system: field and the output filename;
        # non-slug characters (dots, colons, slashes, newlines) would break both surfaces.
        if not _SLUG_RE.match(args.system):
            print(
                f"error: --system '{args.system}' is not a valid slug. "
                "Use lowercase alphanumeric + dashes only (^[a-z0-9][a-z0-9-]*$). "
                "Path separators, dots, colons, and other metacharacters are not allowed.",
                file=sys.stderr,
            )
            sys.exit(1)

    # Validate completion-specific fields.
    if doc_type == "completion":
        if args.nature not in _COMPLETION_NATURE_ENUM:
            print(
                f"error: --nature '{args.nature}' is not a valid completion nature. "
                f"Must be one of: {', '.join(_COMPLETION_NATURE_ENUM)}.",
                file=sys.stderr,
            )
            sys.exit(1)
        # Review: code-reviewer — F3: --chain is YAML-interpolated; guard with _SLUG_RE like other slug args.
        if args.chain and not _SLUG_RE.match(args.chain):
            print(
                f"error: --chain '{args.chain}' is not a valid slug. "
                "Use lowercase alphanumeric + dashes only (^[a-z0-9][a-z0-9-]*$).",
                file=sys.stderr,
            )
            sys.exit(1)

    # Validate plan-specific --sizing-object / --no-sizing-object: the write-time
    # half of the plan sizing-citation gate. A supplied path that does not resolve
    # on disk must fail loud and write no file — the scaffolder is the ergonomic
    # locus where the correct path is cheaper than the wrong one. An explicit
    # sizing answer (path or --no-sizing-object) is now REQUIRED for --type plan:
    # omitting both is the ordinary failure mode the absence gate exists to close
    # (assert_plan_sizing_citation's date-scoped absence check), so it is refused
    # here, at write time, rather than left for the sweep to catch after the fact.
    # Spec: docs/plans/2026-08-06-plan-sizing-citation-gate.md § AC3
    # Spec: docs/plans/2026-08-06-sizing-citation-absence-is-checkable.md, chunk C1
    # roadmap-baton is held to the SAME bar as plan, and for the same reason:
    # a roadmap arrives through the sizing lobby with a per-stub `loe:`, so the
    # sizing answer always exists at mint — depending on a skill step to
    # remember the flag is exactly the "the operator remembers" discharge this
    # repo does not accept. Cross-repo ask: cross-repo/inbox/2026-08-20-doe-
    # claude-em-pickup-brief-should-emit-the-sizing-disposition.md (follow-on).
    if doc_type in ("plan", "roadmap-baton"):
        if args.sizing_object and args.no_sizing_object:
            print(
                "error: --sizing-object and --no-sizing-object are mutually "
                "exclusive — supply the resolving path, or declare absence "
                "with --no-sizing-object, not both.",
                file=sys.stderr,
            )
            sys.exit(1)
        if not args.sizing_object and not args.no_sizing_object:
            print(
                f"error: --type {doc_type} requires an explicit sizing answer — "
                "neither --sizing-object nor --no-sizing-object was supplied. "
                "Produce the sizing object first via coordinator:sizing, then "
                "re-run with the resolved path, or pass --no-sizing-object if "
                "this record genuinely has none.",
                file=sys.stderr,
            )
            sys.exit(1)
        if args.sizing_object:
            _sizing_repo_root = _current_repo_root() or "."
            _sizing_abs_path = os.path.join(_sizing_repo_root, args.sizing_object)
            if not os.path.isfile(_sizing_abs_path):
                print(
                    f"error: --sizing-object '{args.sizing_object}' does not resolve "
                    f"on disk (looked for {_sizing_abs_path}). Produce the sizing object "
                    "first via coordinator:sizing, then re-run with the resolved path.",
                    file=sys.stderr,
                )
                sys.exit(1)

    # Validate review-findings-specific required fields.
    if doc_type == "review-findings":
        if not args.slice_id:
            print("error: --slice <id> is required for --type review-findings.", file=sys.stderr)
            sys.exit(1)
        if not args.scope:
            print("error: --scope <comma-paths> is required for --type review-findings.", file=sys.stderr)
            sys.exit(1)
        # review F8 — paths are expected (separators, dots fine) but markdown metacharacters
        # in the heading/Scope: line produce structurally odd sidecar markdown; block the
        # most obvious injection vectors while leaving path syntax unrestricted.
        _SCOPE_DENYLIST = ("\n", "\r", "`", "-->")
        if any(c in args.scope for c in _SCOPE_DENYLIST):
            print(
                f"error: --scope value contains a disallowed character "
                f"(newline, carriage-return, backtick, or markdown comment close).",
                file=sys.stderr,
            )
            sys.exit(1)
        if not _SLICE_RE.match(args.slice_id):
            print(
                f"error: --slice '{args.slice_id}' is not a valid slice id. "
                "Use alphanumeric + dashes only (^[a-zA-Z0-9][a-zA-Z0-9-]*$).",
                file=sys.stderr,
            )
            sys.exit(1)

    # Validate roadmap-baton-specific fields.
    if doc_type == "roadmap-baton":
        if args.roadmap_id and not _SLUG_RE.match(args.roadmap_id):
            print(
                f"error: --roadmap-id '{args.roadmap_id}' is not a valid slug. "
                "Use lowercase alphanumeric + dashes only (^[a-z0-9][a-z0-9-]*$).",
                file=sys.stderr,
            )
            sys.exit(1)
        if args.stub_id and not _SLUG_RE.match(args.stub_id):
            print(
                f"error: --stub-id '{args.stub_id}' is not a valid slug. "
                "Use lowercase alphanumeric + dashes only (^[a-z0-9][a-z0-9-]*$).",
                file=sys.stderr,
            )
            sys.exit(1)

    # Resolve branch (for handoff/spinoff/plan).
    branch = args.branch if args.branch else _current_branch()

    # Resolve from_id (for memo).
    from_id: str = ""  # Review: code-reviewer S3-F6 — narrowed from str|None; only assigned under doc_type=="memo" and _scaffold_memo requires str
    if doc_type == "memo":
        from_id = args.from_repo if args.from_repo else _resolve_from_repo()

    # Resolve author (for plan) — the MINTING SESSION's own name (e.g.
    # claude-klabauter-76), not a repo-wide EM role string, and never the
    # hardcoded central-EM literal this replaced (D1 authorship).
    plan_author: str = ""
    if doc_type == "plan":
        plan_author = _resolve_plan_author()

    # `--new-chain` is an authoring INTENT, resolved once here rather than threaded
    # through the five mint-from-title call sites below (see _NEW_CHAIN_REQUESTED).
    global _NEW_CHAIN_REQUESTED
    _NEW_CHAIN_REQUESTED = bool(getattr(args, "new_chain", False))

    # Resolve deliverable-spine fields (handoff, spinoff, roadmap-baton, plan) — C3b.
    # Session context inheritance: DELIVERABLE_ID env var is the mechanism by which the
    # skill layer (e.g. /handoff, /plan) propagates the parent deliverable_id so downstream
    # artifacts carry the same id without requiring author memory (D1, AC12).
    _spine_types = {"handoff", "spinoff", "roadmap-baton", "roadmap-seed", "plan", "recovery", "sizing-object"}
    _resolved_deliverable_id: str | None = None
    _resolved_plan_id: str | None = None
    _resolved_initiative: str | None = None
    # Set only by the `handoff` arm's carry cascade below; stays None (a
    # no-op in the explicit/env fallback line further down) for every other
    # doc_type, preserving that line's prior behavior exactly.
    _hnd_carried_initiative: str | None = None
    if doc_type in _spine_types:
        # Priority: explicit CLI arg → DELIVERABLE_ID env var → mint new
        #
        # AC5: `--deliverable-id` has default=None, so argparse already
        # distinguishes flag-ABSENT (None) from flag-EMPTY (""), the latter
        # being exactly what `baton_assemble._build_directives` emits for a
        # null lineage (`f"--deliverable-id={lineage.get('deliverable_id') or
        # ''}"`). An explicitly-empty flag now reads as "resolve via the
        # cascade" — it must NOT fall through to DELIVERABLE_ID env (that
        # would let session env silently override a deliberate empty
        # signal); only a genuinely omitted flag consults env.
        _explicit_dlv_raw = getattr(args, "deliverable_id", None)
        _flag_explicitly_empty = _explicit_dlv_raw is not None and not _explicit_dlv_raw
        _explicit_dlv = _explicit_dlv_raw or None
        _env_dlv = os.environ.get("DELIVERABLE_ID", "").strip() or None
        _carry_dlv = (
            _explicit_dlv if _explicit_dlv
            else (None if _flag_explicitly_empty else _env_dlv)
        )
        _carry_dlv_source = (
            "explicit --deliverable-id" if _explicit_dlv
            else ("DELIVERABLE_ID env" if _env_dlv else None)
        )
        if _carry_dlv:
            # carry path — caller or env supplied; log and carry unchanged
            _resolved_deliverable_id = _mint_deliverable_id(
                deliverable_id=_carry_dlv, carry_source=_carry_dlv_source
            )
        elif doc_type == "roadmap-baton":
            # stub path — roadmap stubs reuse stub_id as deliverable identity (D1)
            _sr_stub = args.stub_id if args.stub_id else None
            if _sr_stub:
                _resolved_deliverable_id = _mint_deliverable_id(stub_id=_sr_stub)
            else:
                # no stub_id yet (PLACEHOLDER) — mint from slug. Session-chain
                # discovery is inert here by doc_type (see
                # _resolve_session_chain_deliverable_id): a roadmap baton's
                # identity is its stub_id, never a chain it was authored beside.
                _resolved_deliverable_id = _mint_deliverable_id_from_title(
                    title, doc_type, _current_repo_root()
                )
        elif doc_type == "plan":
            # Session-state parent tier (2026-08-01 deliverable-id-fork-remediation
            # C1/AC1) — reachable for `plan` only, ordered after explicit/env carry
            # and before mint-from-slug. Resolves the parent from SESSION STATE
            # (never from this file's own commented-out predecessor_handoff — see
            # _resolve_session_held_spinoff_roadmap_stub_path's docstring), and
            # deliverable_carry.resolve_session_state_parent_deliverable_id gates
            # the carry on the held claim's own `kind` being a roadmap stub kind
            # (`roadmap-baton` or the retired `spinoff-roadmap` — see
            # deliverable_carry._ROADMAP_STUB_KINDS), never on mere claim
            # existence (AC1/AC4b false-merge guard).
            _session_stub_path = _resolve_session_held_spinoff_roadmap_stub_path(
                _current_repo_root()
            )
            _session_parent_dlv = None
            if _session_stub_path:
                try:
                    _ensure_engine_on_path()
                    from coordinator_core.ops.deliverable_carry import (
                        resolve_session_state_parent_deliverable_id,
                    )
                    from coordinator_core.ops.read_frontmatter_field import (
                        read_frontmatter_field as _read_frontmatter_field,
                    )

                    _session_parent_dlv = resolve_session_state_parent_deliverable_id(
                        _read_frontmatter_field, _session_stub_path
                    )
                except Exception:  # noqa: BLE001 -- best-effort; degrade to no-carry, never block scaffolding
                    _session_parent_dlv = None
            if _session_parent_dlv:
                _resolved_deliverable_id = _mint_deliverable_id(
                    deliverable_id=_session_parent_dlv,
                    carry_source="session-state parent (roadmap stub)",
                )
            else:
                # Cited-sizing carry tier (2026-08-10 deliverable-id-fork-
                # remediation follow-up) — ordered after explicit/env and the
                # session-state-parent tier above, and before mint-from-slug.
                # A sizing-object is the earliest artifact in the deliverable
                # chain (sizing-object.schema.json's own `deliverable_id`
                # description) — a plan citing one must carry its id verbatim
                # rather than minting a second, forked id that
                # `deliverable.cascade_terminal`'s exact-string join can never
                # match. Reached only when nothing more explicit (flag/env/
                # session-parent) already resolved an id, so a deliberate
                # caller-supplied id is never overridden by the cited sizing.
                _sizing_carry_dlv = None
                if getattr(args, "sizing_object", None):
                    _sizing_repo_root_for_carry = _current_repo_root() or "."
                    _sizing_carry_dlv = _resolve_cited_sizing_deliverable_id(
                        args.sizing_object, _sizing_repo_root_for_carry
                    )
                if _sizing_carry_dlv:
                    _resolved_deliverable_id = _mint_deliverable_id(
                        deliverable_id=_sizing_carry_dlv,
                        carry_source="cited sizing-object",
                    )
                else:
                    # Explicit-predecessor-edge tier (C2, AC1/AC3/AC4/AC9) —
                    # ordered BEHIND the session-state-parent (held-claim)
                    # tier above and the cited-sizing tier, so every input
                    # that resolved via either of those today keeps
                    # resolving identically (AC3's plan-arm collision case).
                    # Fires only when both yielded nothing.
                    _plan_predecessor_edge = getattr(args, "predecessor", None) or None
                    _resolved_deliverable_id = _resolve_explicit_predecessor_edge_tier(
                        _plan_predecessor_edge, _current_repo_root(), doc_type, title,
                        narrow_catch=False,
                    )
        elif doc_type == "handoff":
            # Session-plan/predecessor carry tier (2026-08-03 deliverable-id-
            # carry-plan-handoff-agree C1/AC1/AC2/AC6/AC19) — reachable for
            # `handoff` only, ordered after explicit/env carry and before
            # mint-from-slug, mirroring the `plan` arm's own session-state
            # tier above but resolving through the ONE cascade
            # implementation (`deliverable_carry.resolve_deliverable_and_
            # initiative`) rather than re-deriving the plan/predecessor
            # precedence here.
            #
            # `coordinator_core.ops` registers ops lazily, unconditionally, so
            # this arm -- which runs on EVERY direct handoff scaffold with no
            # explicit/env id -- never pays the ops package's eager-compile
            # tax. See coordinator_core/ops/__init__.py's lazy-mode docstring.
            _ensure_engine_on_path()
            from coordinator_core.session.claimed_plan import (
                resolve_claimed_plan_path as _resolve_claimed_plan_path,
            )
            from coordinator_core.ops.deliverable_carry import (
                DivergentDeliverableIdError,
                DroppedDeliverableJoinError,
                resolve_deliverable_and_initiative,
            )
            from coordinator_core.ops.read_frontmatter_field import (
                read_frontmatter_field as _read_frontmatter_field,
            )

            _hnd_repo_root = _current_repo_root()
            _claimed_plan_rel = _resolve_claimed_plan_path(_hnd_repo_root)
            _claimed_plan_path = (
                os.path.join(_hnd_repo_root, _claimed_plan_rel)
                if _claimed_plan_rel and _hnd_repo_root
                else _claimed_plan_rel
            )
            _predecessor_path = getattr(args, "predecessor", None) or None

            def _hnd_mint_adapter(deliverable_id=None, slug=None):
                # Bridges `_mint_deliverable_id`'s bare `str | None` return to
                # `resolve_deliverable_and_initiative`'s `mint(...)` 2-tuple
                # contract (verified against `deliverable_carry.py` source —
                # it unpacks `result, path_label = mint(...)`). Local to this
                # arm; `_mint_deliverable_id` itself keeps its bare-str
                # return, which the `plan` arm and other callers depend on.
                if deliverable_id:
                    return (
                        _mint_deliverable_id(
                            deliverable_id=deliverable_id, carry_source="carry"
                        ),
                        "carry",
                    )
                return _mint_deliverable_id(slug=slug), "mint-from-slug"

            # Chain-root legibility: when no rung carries an id, the cascade
            # mints from a slug, and its own fallback basis is the DATE
            # (`<YYYYMMDD>-handoff`) — an id naming the day, not the work, so
            # two unrelated chain roots scaffolded in one session both read as
            # `dlv-<today>-handoff-<hex>`. Hand it this handoff's own title
            # slug instead, matching the shape the degradation fallback below
            # already mints (`_mint_deliverable_id_from_title`). A placeholder
            # title yields nothing, so the date fallback still stands rather
            # than baking a placeholder into a durable id — same refusal
            # `_mint_deliverable_id_from_title` makes, same reason.
            _hnd_work_slug = None if _is_placeholder_title(title) else _slug_from_title(title)

            try:
                _resolved_deliverable_id, _hnd_carried_initiative = (
                    resolve_deliverable_and_initiative(
                        _read_frontmatter_field,
                        _hnd_mint_adapter,
                        _claimed_plan_path,
                        _predecessor_path,
                        slug_suffix="handoff",
                        work_slug=_hnd_work_slug,
                    )
                )
            except (DroppedDeliverableJoinError, DivergentDeliverableIdError) as _hnd_carry_exc:
                # NARROW catch — deliberate divergence from the `plan` arm's
                # blanket `except Exception` above. A blanket catch here
                # would also swallow a broken `_hnd_mint_adapter` wiring
                # (TypeError/ImportError) and degrade silently to permanent
                # no-carry — the exact defect this arm exists to prevent,
                # reintroduced by masking it. Do not widen this to
                # `except Exception` in a future tidying pass.
                _resolved_deliverable_id = _mint_deliverable_id_from_title(
                    title, doc_type, _hnd_repo_root
                )
                _hnd_carried_initiative = None
                _write_deliverable_carry_degradation(
                    _hnd_repo_root, doc_type, _hnd_carry_exc,
                    _resolved_deliverable_id, title,
                    claimed_plan_path=_claimed_plan_path,
                    predecessor_path=_predecessor_path,
                )
        elif doc_type == "sizing-object":
            # AC9 — sizing-object is the earliest artifact in the
            # deliverable chain (sizing-object.schema.json's own
            # `deliverable_id` description; DR-207 DD#1) and never takes a
            # DESCENT carry — no parent rung (session-state stub, cited
            # sizing, predecessor edge) is admissible here; mint, or
            # explicit/env id (already resolved above this elif chain).
            #
            # Session-chain discovery inside `_mint_deliverable_id_from_title`
            # is NOT such a rung and is deliberately live here (2026-08-25 bug
            # record `deliverable-id-minted-from-title-not-discovered`): it
            # asks co-membership, not descent — "is this session already
            # authoring a chain" — and it was precisely a sizing scaffolded
            # beside a live chain that minted the second id that record was
            # filed for. AC9's "earliest artifact" premise holds only when the
            # sizing IS the chain root; when it demonstrably is not, minting a
            # fresh id manufactures a fork rather than defending a root.
            # `--new-chain` is how an author asserts the root case explicitly.
            _resolved_deliverable_id = _mint_deliverable_id_from_title(
                title, doc_type, _current_repo_root()
            )
        else:
            # AC2/AC9 fallthrough — the carry cascade is the DEFAULT for
            # every OTHER spine-bearing doc_type. Today that is `spinoff`,
            # `roadmap-seed`, and `recovery`; a FUTURE doc_type added to
            # `_spine_types` lands here automatically with no edit to this
            # dispatch (AC2). No held-claim or claimed-plan tier exists for
            # these types to collide with, so per AC9's evidence table the
            # explicit-predecessor-edge tier (C2) is the ONLY admissible
            # carry rung, ordered ahead of mint-from-slug and behind
            # explicit/env id. Routed through `_resolve_explicit_
            # predecessor_edge_tier(narrow_catch=True)` so AC9's fail-soft
            # catch is the one thing standing between a forced resolution
            # error and the caller — that catch, not a blanket swallow, is
            # what AC9 pins.
            _newly_reached_predecessor_edge = getattr(args, "predecessor", None) or None
            _resolved_deliverable_id = _resolve_explicit_predecessor_edge_tier(
                _newly_reached_predecessor_edge, _current_repo_root(), doc_type, title,
                narrow_catch=True,
            )

        # plan_id — always minted fresh for plan type (D3); never null.
        # Review: coordinator:code-reviewer (913d6318) F1 — pln- was never in the
        # false-clear blast radius (gate_eval._HANDOFF_ID_PATTERN matches hnd- only),
        # so the placeholder-title guard bought nothing here and cost the D3
        # "always present, never null" contract baton_assemble's is_plan_input
        # discriminator depends on. Restored to unconditional minting.
        if doc_type == "plan":
            _resolved_plan_id = _mint_plan_id(_slug_from_title(title))

        # initiative FK — explicit CLI arg or INITIATIVE_ID env var; null when neither set
        _explicit_ini = getattr(args, "initiative", None)
        _env_ini = os.environ.get("INITIATIVE_ID", "").strip() or None
        # AC19: explicit/env still wins; otherwise fall back to whatever the
        # handoff carry-cascade resolved above (None for every other doc_type,
        # preserving prior behavior exactly there).
        _resolved_initiative = _explicit_ini or _env_ini or _hnd_carried_initiative

    # Resolve stable artifact ids (lvv-01/C1): hnd-<slug>-<6hex> for handoffs,
    # cmp-<slug>-<6hex> for completions. Optional fields — always minted fresh,
    # no carry path (unlike deliverable_id, these are per-artifact, not inherited
    # across a session lineage).
    _resolved_handoff_id: str | None = None
    _resolved_completion_id: str | None = None
    if doc_type in ("handoff", "spinoff", "recovery", "goal-seed", "roadmap-seed", "roadmap-baton"):
        _resolved_handoff_id = _mint_artifact_id_from_title("hnd", title, doc_type, "handoff_id")
    elif doc_type == "completion":
        _resolved_completion_id = _mint_artifact_id_from_title("cmp", title, doc_type, "completion_id")

    # Allocate a real, collision-checked DR number for decision records — never the
    # retired DR-XXX placeholder. Scans the repo's canonical docs/decisions/
    # directory regardless of --out, since allocation is about the shared
    # numbering namespace, not the write target of this particular invocation.
    # Spec backlink: cross-repo/inbox/2026-07-20-example-game-repo-em-dr-number-allocator-collision.md
    _resolved_dr_id: str | None = None
    if doc_type == "decision":
        _dr_repo_root = _current_repo_root() or "."
        _decisions_dir = os.path.join(_dr_repo_root, "docs", "decisions")
        try:
            _resolved_dr_id = _allocate_dr_number(_decisions_dir, explicit_prefix=args.dr_prefix)
            _assert_dr_id_unique(_decisions_dir, _resolved_dr_id)
        except _DrAllocatorError as exc:
            print(f"error: {exc}", file=sys.stderr)
            sys.exit(1)

    # Kind-gate the fan-in down-edge. Mirrors --predecessor's own handoff-only
    # contract (schema rule A3a-3 _cf_spinoff_predecessor_none makes the spinoff
    # kinds predecessor:none-by-design, and --type recovery's own scaffold emits
    # the `additional_predecessors: []` literal itself). Refused rather than
    # silently ignored: a caller passing fan-in legs to a kind that cannot carry
    # them has a real bug, and a no-op would drop the edge without saying so --
    # the exact silent-loss failure this stub exists to remove.
    if args.additional_predecessors and doc_type != "handoff":
        print(
            f"coordinator-doc-new: --additional-predecessor is not accepted for "
            f"--type {doc_type}. The fan-in down-edge is a handoff-only field, refused "
            "for every other --type (not only spinoff/recovery): the spinoff kinds are "
            "predecessor:none-by-design (schema rule A3a-3) and --type recovery "
            "scaffolds its own additional_predecessors: [] literal — no other kind "
            "carries a predecessor edge at all.",
            file=sys.stderr,
        )
        sys.exit(1)

    # --summary/--gated-open are handoff-scoped, same posture as
    # --additional-predecessor above: refused fail-loud for every other
    # --type rather than silently dropped (cross-repo/inbox/
    # 2026-08-18-project-rag-em-doc-new-silently-drops-type-inapplicable-flags.md
    # offered warn-or-refuse; refuse matches the existing
    # --additional-predecessor precedent, so no third posture is invented).
    if (
        args.summary or args.gated_open or args.gate_note or args.gated_predicate
    ) and doc_type != "handoff":
        if args.summary:
            _bad_flag = "--summary"
        elif args.gated_open:
            _bad_flag = "--gated-open"
        elif args.gate_note:
            _bad_flag = "--gate-note"
        else:
            _bad_flag = "--gated-predicate"
        print(
            f"coordinator-doc-new: {_bad_flag} is not accepted for --type {doc_type}. "
            "--summary, --gated-open, --gate-note, and --gated-predicate are "
            "handoff-only fields.",
            file=sys.stderr,
        )
        sys.exit(1)

    # --deliverable-ids/--plan-ids are handoff-scoped plural carriers (C1),
    # same posture as --additional-predecessor/--summary above: refused
    # fail-loud for every other --type rather than silently dropped (same
    # cross-repo/inbox/2026-08-18-project-rag-em-doc-new-silently-drops-
    # type-inapplicable-flags.md precedent).
    if (args.deliverable_ids or args.plan_ids) and doc_type != "handoff":
        if args.deliverable_ids:
            _bad_flag = "--deliverable-ids"
        else:
            _bad_flag = "--plan-ids"
        print(
            f"coordinator-doc-new: {_bad_flag} is not accepted for --type {doc_type}. "
            "--deliverable-ids and --plan-ids are handoff-only fields.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Generate scaffold content.
    if doc_type == "handoff":
        content = _scaffold_handoff(
            title=title,
            branch=branch,
            deliverable_id=_resolved_deliverable_id,
            initiative=_resolved_initiative,
            handoff_id=_resolved_handoff_id,
            origin_handoff_id=args.origin_handoff_id,
            predecessor=args.predecessor,
            predecessor_id=args.predecessor_id,
            category=args.category,
            additional_predecessors=args.additional_predecessors,
            summary=args.summary,
            gated_open=args.gated_open,
            gate_note=args.gate_note,
            gated_predicate=args.gated_predicate,
            deliverable_ids=args.deliverable_ids,
            plan_ids=args.plan_ids,
        )
    elif doc_type == "recovery":
        content = _scaffold_recovery(
            title=title,
            branch=branch,
            deliverable_id=_resolved_deliverable_id,
            initiative=_resolved_initiative,
            handoff_id=_resolved_handoff_id,
            recovers_session=args.recovers_session,
            origin_handoff_id=args.origin_handoff_id,
            predecessor_id=args.predecessor_id,
            category=args.category,
        )
    elif doc_type == "spinoff":
        content = _scaffold_spinoff(
            title=title,
            branch=branch,
            deliverable_id=_resolved_deliverable_id,
            initiative=_resolved_initiative,
            handoff_id=_resolved_handoff_id,
            origin_handoff_id=args.origin_handoff_id,
            predecessor_id=args.predecessor_id,
            category=args.category,
        )
    elif doc_type == "roadmap-baton":
        roadmap_id = args.roadmap_id if args.roadmap_id else "placeholder-rm"
        stub_id = args.stub_id if args.stub_id else "placeholder-stub-1"
        content = _scaffold_roadmap_baton(
            title=title,
            branch=branch,
            roadmap_id=roadmap_id,
            stub_id=stub_id,
            deliverable_id=_resolved_deliverable_id,
            initiative=_resolved_initiative,
            category=args.category,
            handoff_id=_resolved_handoff_id,
            gate_dependency=args.gate_dependency,
            sizing_object=("null" if args.no_sizing_object else args.sizing_object),
        )
    elif doc_type == "goal-seed":
        _goals_list = [g.strip() for g in args.goals.split(",") if g.strip()] if args.goals else None
        content = _scaffold_goal_seed(
            title=title,
            branch=branch,
            goals=_goals_list,
            gate_dependency=args.gate_dependency,
            handoff_id=_resolved_handoff_id,
            origin_handoff_id=args.origin_handoff_id,
            predecessor_id=args.predecessor_id,
            category=args.category,
        )
    elif doc_type == "roadmap-seed":
        _goals_list = [g.strip() for g in args.goals.split(",") if g.strip()] if args.goals else None
        content = _scaffold_roadmap_seed(
            title=title,
            branch=branch,
            goals=_goals_list,
            gate_dependency=args.gate_dependency,
            deliverable_id=_resolved_deliverable_id,
            initiative=_resolved_initiative,
            handoff_id=_resolved_handoff_id,
            origin_handoff_id=args.origin_handoff_id,
            predecessor_id=args.predecessor_id,
            category=args.category,
        )
    elif doc_type == "memo":
        content = _scaffold_memo(
            title=title,
            to=args.to,
            topic=args.topic,
            from_id=from_id,
        )
    elif doc_type == "plan":
        content = _scaffold_plan(
            title=title,
            branch=branch,
            author=plan_author,
            plan_id=_resolved_plan_id,
            deliverable_id=_resolved_deliverable_id,
            initiative=_resolved_initiative,
            sizing_object="null" if args.no_sizing_object else args.sizing_object,
            problem_set=args.problem_set,
        )
    elif doc_type == "decision":
        content = _scaffold_decision(title=title, dr_id=_resolved_dr_id)
    elif doc_type == "audit-record":
        content = _scaffold_audit_record(title=title, system=args.system)
    elif doc_type == "problem-set":
        content = _scaffold_problem_set(title=title)
    elif doc_type == "completion":
        content = _scaffold_completion(
            title=title,
            nature=args.nature,
            chain=args.chain,
            completion_id=_resolved_completion_id,
        )
    elif doc_type == "goal":
        content = _scaffold_goal(title=title)
    elif doc_type == "sizing-object":
        content = _scaffold_sizing(title=title, deliverable_id=_resolved_deliverable_id)
    elif doc_type == "health-status":
        content = _scaffold_health_status(title=title)
    elif doc_type == "strategic-self-description":
        content = _scaffold_strategic_self_description(title=title)
    elif doc_type == "research-synthesis":
        content = _scaffold_research_synthesis(title=title)
    elif doc_type in _SIDECAR_TYPES:
        content = _scaffold_sidecar(doc_type=doc_type, plan_stem=args.plan)
    elif doc_type == "run-report":
        # dispatched_at: current UTC time in ISO 8601 format (matches fan-out-dispatch.sh: date -u +%Y-%m-%dT%H:%M:%SZ).
        dispatched_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # Review: code-reviewer item-5 F4 — utcnow() deprecated Python 3.12+; now(tz) is identical output
        # dispatched_by: CLAUDE_CODE_SESSION_ID env var, falls back to 'em-unknown' (matches fan-out-dispatch.sh).
        dispatched_by = os.environ.get("CLAUDE_CODE_SESSION_ID", "em-unknown")
        content = _scaffold_run_report(
            plan_path=args.plan,
            chunk_id=args.chunk,
            dispatched_at=dispatched_at,
            dispatched_by=dispatched_by,
            agent_type=args.agent_type,
        )
    elif doc_type == "subagent-sidecar":
        dispatched_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        dispatched_by = os.environ.get("CLAUDE_CODE_SESSION_ID", "em-unknown")
        content = _scaffold_subagent_sidecar(
            plan_path=args.plan,
            chunk_id=args.chunk,
            dispatched_at=dispatched_at,
            dispatched_by=dispatched_by,
            agent_type=args.agent_type,
        )
    elif doc_type == "review-findings":
        _rf_spawned_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _rf_lead_session_id = _resolve_session_id()
        content = _scaffold_review_findings(
            slice_id=args.slice_id, scope=args.scope,
            spawned_at=_rf_spawned_at, lead_session_id=_rf_lead_session_id,
        )
    else:
        # A doc_type reached the dispatch chain with no scaffold branch. Two cases,
        # discriminated by the manifest's `neverManuallyScaffoldable` flag (DO NOT
        # collapse them — the distinction preserves the missing-emitter bug signal
        # that a green false-positive on strategic-self-description AC3 hid for 7
        # days; see docs/plans/2026-07-11-strategic-self-description-standard.md
        # Outcome correction):
        #   (a) neverManuallyScaffoldable: true — a manifest-registered type
        #       intentionally NOT manually scaffoldable via this CLI (e.g.
        #       spike-result, authored by its owning skill). Clean fail-loud with
        #       the excludeReason, no traceback.
        #   (b) neverManuallyScaffoldable absent (or false), no emitter — a genuine
        #       half-landed emitter BUG. This is the common case for `offerable: false`
        #       types that DO have a real elif branch (spinoff, memo, audit-record,
        #       run-report, review-findings, etc. — `offerable: false` there means
        #       only "excluded from the generic offer surface", not "unscaffoldable").
        #       Keep the loud AssertionError so it crashes visibly and the
        #       known-types<->emitter parity test catches it.
        # Review: code-reviewer Finding 1 — `offerable: false` conflated "never
        # manually scaffoldable" with "excluded from the generic offer surface
        # only"; the narrower `neverManuallyScaffoldable` field fixes the
        # discrimination so a deleted branch on the latter population still hits
        # the loud AssertionError below.
        _entry = next((d for d in _DOC_TYPES if d.get("type") == doc_type), None)
        if _entry is not None and _entry.get("neverManuallyScaffoldable") is True:
            _reason = _entry.get("excludeReason") or "not manually scaffoldable"
            print(
                f"error: --type {doc_type} is registered but not manually scaffoldable "
                f"via coordinator-doc-new (neverManuallyScaffoldable: true). {_reason}",
                file=sys.stderr,
            )
            sys.exit(2)
        raise AssertionError(f"unreachable doc_type: {doc_type!r}")

    # Resolve output path.
    out_path = args.out
    _anchored_repo_root: str | None = None  # set when default path is re-anchored to repo root
    if not out_path:
        topic_for_path = args.topic if doc_type == "memo" else None
        # For sidecar types, plan_stem is the bare stem. For run-report, it's the full path.
        plan_stem_for_path = args.plan if (doc_type in _SIDECAR_TYPES or doc_type in ("run-report", "subagent-sidecar")) else None
        system_for_path = args.system if doc_type == "audit-record" else None
        stub_id_for_path = (
            args.stub_id if doc_type == "roadmap-baton" and args.stub_id
            else None
        )
        chunk_id_for_path = args.chunk if doc_type in ("run-report", "subagent-sidecar") else None
        slice_id_for_path = args.slice_id if doc_type == "review-findings" else None
        scope_for_path = args.scope if doc_type == "review-findings" else None
        out_path = _default_output_path(
            doc_type, title, topic_for_path,
            plan_stem=plan_stem_for_path,
            system=system_for_path,
            stub_id=stub_id_for_path,
            chunk_id=chunk_id_for_path,
            slice_id=slice_id_for_path,
            scope=scope_for_path,
            dr_id=_resolved_dr_id,
        )
        # Anchor default relative paths to the correct root so the output lands in the
        # right location regardless of the caller's cwd.
        #
        # Placement law (AC7 / stop-the-rot): state/ paths route through the
        # coordinator_state_root seam so new artifacts land in claude-klabauter (not ~/.claude/state)
        # when running from the coordinator meta-repo. Falls back to repo-root anchoring
        # on un-migrated installs where the seam is unresolvable.
        #
        # Non-state paths (docs/, tasks/, archive/) anchor to the git repo root as before.
        #
        # Spec backlinks:
        #   docs/plans/2026-07-02-coordinator-doc-new-path-anchor-fix.md (original anchor fix)
        #   docs/plans/2026-07-03-stop-the-rot-claude-klabauter-state-home-placement.md § C10 / AC7
        if not os.path.isabs(out_path):
            # Detect state/ prefix (cross-platform: use os.path.join to get native separator).
            _state_prefix = "state" + os.sep
            _is_state_path = out_path.startswith(_state_prefix) or out_path == "state"
            if _is_state_path:
                # Route through coordinator_state_root seam.
                # Strip the leading "state/" prefix to get the sub-path (e.g. "handoffs/foo.md").
                _state_rel = out_path[len(_state_prefix):] if out_path.startswith(_state_prefix) else ""
                _state_root = _resolve_state_root()
                if _state_root:
                    out_path = os.path.join(_state_root, _state_rel) if _state_rel else _state_root
                    # For the printed output pointer: if the seam resolved to a path within the
                    # current repo root (non-meta-repo: seam returns $GIT_ROOT/state), keep the
                    # existing relative-path print behaviour by setting _anchored_repo_root.
                    # When the seam redirects to claude-klabauter (a DIFFERENT repo), _anchored_repo_root
                    # stays None and the absolute path is printed — callers need the absolute path
                    # to commit to the correct (claude-klabauter) repo.
                    _repo_root_for_relpath = _current_repo_root()
                    if _repo_root_for_relpath:
                        _rr = os.path.realpath(_repo_root_for_relpath)
                        _op = os.path.realpath(out_path)
                        if _op.startswith(_rr + os.sep) or _op == _rr:
                            _anchored_repo_root = _repo_root_for_relpath
                else:
                    # Seam unresolvable (e.g. the engine root not configured on this machine).
                    # Degrade gracefully: fall back to repo-root anchoring so the CLI keeps
                    # working on un-migrated installs. This matches AC13's graceful-skip pattern.
                    _repo_root = _current_repo_root()
                    if _repo_root:
                        out_path = os.path.join(_repo_root, out_path)
                        _anchored_repo_root = _repo_root
            else:
                # Non-state paths: anchor to repo root as before (docs/, tasks/, archive/, etc.).
                _repo_root = _current_repo_root()
                if _repo_root:
                    out_path = os.path.join(_repo_root, out_path)
                    _anchored_repo_root = _repo_root

    # Security: containment check — resolve symlinks + '..' and verify the output
    # path falls within an allowed write root before creating any directories or files.
    # Review: code-reviewer — _assert_output_safe → _safe_output_roots() calls
    # _current_repo_root() again, so default-path invocations resolve the repo root
    # twice (once above for anchoring, once here for containment). The double subprocess
    # spawn is an accepted minor cost for this one-shot scaffolding CLI: threading the
    # root through _safe_output_roots() would require a more invasive refactor that
    # outweighs the negligible performance gain on a review-time tool.
    _assert_output_safe(out_path)

    # Ensure parent directory exists.
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    # Guard: refuse to (re)create a live handoff sharing an already-archived
    # record's filename or handoff_id. Scoped internally to state/handoffs/
    # destinations only (no-op for every other doc_type/output path).
    _assert_no_archived_handoff_twin(
        out_path,
        _resolved_handoff_id,
        _anchored_repo_root or _current_repo_root(),
    )

    # Self-check: refuse to write content that fails this repo's own
    # vendored schema for the doc type it resolves to (no-op for doc types
    # with no schema in that corpus — see the function's own docstring).
    _assert_scaffold_content_valid(
        content,
        out_path,
        _anchored_repo_root or _current_repo_root(),
    )

    # cwd is the repo the write actually landed in (may differ from the
    # caller's process cwd when the placement-law state/ seam re-anchors to
    # a different repo, e.g. Claude-klabauter). Resolved here (rather than just before
    # the plan-file write below) because the C4 reverse write-back also
    # needs it, ahead of the plan-file write it precedes.
    _write_repo_root = _anchored_repo_root or _current_repo_root() or os.getcwd()

    # Reverse write-back: plan -> sizing, one transaction (C4, plan
    # 2026-08-10-sizing-objects-join-the-deliverable-spine.md § C4). Mechanism
    # named explicitly for AC7: the sizing edge is written FIRST, under a
    # cross-process lock (locked_rmw); the plan file is written SECOND. If the
    # plan-file write raises, the sizing edit is reverted to its captured
    # pre-mutation text before the exception propagates. This is write-order +
    # revert-on-failure, not a single cross-file atomic transaction — this
    # codebase has no shared-journal primitive spanning two independent files,
    # so a failure between the two writes (process kill between the sizing
    # write and the plan write) is a residual this mechanism does not close;
    # named honestly rather than claimed as full atomicity.
    _sizing_reverse_old_text: str | None = None
    if doc_type == "plan" and args.sizing_object:
        _ensure_engine_on_path()
        from coordinator_core.locked_write import MutateAbort as _MutateAbort  # noqa: PLC0415

        _plan_repo_rel_path = os.path.relpath(
            os.path.realpath(out_path), os.path.realpath(_write_repo_root)
        ).replace(os.sep, "/")
        try:
            _sizing_reverse_old_text = _write_sizing_reverse_edge(
                _sizing_abs_path, _plan_repo_rel_path, _write_repo_root,
            )
        except _MutateAbort as _abort_exc:
            print(f"error: {_abort_exc}", file=sys.stderr)
            sys.exit(1)

    # Write the scaffolded file.
    #
    # DR-276: this CLI owns its own main() (no single op module's main(argv) to
    # route through via coordinator_core.cli_entry.run_op_main), so the write is
    # wrapped in recording_declared_writes() directly, with declare_write() called
    # AFTER the write lands — mirrors coordinator_core.ops.append_integrator_dispositions'
    # own "declared after the write, never before" discipline.
    try:
        _ensure_engine_on_path()
        from coordinator_core.cli_entry import recording_declared_writes  # noqa: PLC0415
        from coordinator_core.session.declared_writes import declare_write  # noqa: PLC0415
    except Exception:  # noqa: BLE001 -- fail-open: a seam-import failure must never block the scaffold write itself
        recording_declared_writes = None
        declare_write = None

    try:
        if recording_declared_writes is not None:
            with recording_declared_writes(cwd=_write_repo_root):
                with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(content)
                    if not content.endswith("\n"):
                        fh.write("\n")
                declare_write(out_path)
                # The reverse edge is a SECOND file this invocation wrote, on
                # the calling session's behalf, outside the Edit/Write hot path
                # that fires `hooks.track_touched_files`. Undeclared, it carries
                # no `touched.txt` claim at all: `session.scope.compute_scope`
                # then sees it only through the Step-2 mtime fallback, routes it
                # to `mtime_only`, and Step 4(c) withholds it from `my_scope` —
                # so `safe-commit-offer` reports "nothing to commit" over a file
                # this CLI just dirtied, and the next peer's commit sweeps it.
                # Declared HERE, not at the write above, for two reasons: the
                # edge write precedes the collection opening, and it is reverted
                # when the plan write raises — a declaration inside the `except`
                # path's blast radius would claim a path that no longer differs
                # from HEAD. `is not None` (never truthiness): a sizing whose
                # pre-mutation text was empty is still a landed write.
                if _sizing_reverse_old_text is not None:
                    declare_write(_sizing_abs_path)
        else:
            with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(content)
                if not content.endswith("\n"):
                    fh.write("\n")
    except Exception:
        # The plan-file write failed after the sizing reverse edge already
        # landed — revert it so a half-written pair (sizing flipped to
        # `routed` with a `plan:` FK pointing at a file that does not exist)
        # never survives (AC7: "a half-written pair is worse than the
        # hand-maintained status quo it replaces, because it looks
        # maintained"). Re-raises the ORIGINAL exception either way.
        if _sizing_reverse_old_text is not None:
            _revert_sizing_reverse_edge(_sizing_abs_path, _sizing_reverse_old_text, _write_repo_root)
        raise

    # Author-side plan claim (wires the acquire half of the plan claim
    # lifecycle whose release half was already wired: /handoff's d5 directive
    # emits `session-claim-cli release-artifact plan <slug>` against a claim
    # nothing on the authoring path ever took). Taken only after the write
    # above lands — never on a doc_type/path that did not actually write a
    # plan file. Bare stem only (claim_plan rejects a path-shaped slug loud
    # and non-zero) — plan files are always `docs/plans/<stem>.md` (see
    # `_default_output_path`). Non-fatal, mirroring `claim_plan`'s own
    # session-shape.json write: the plan file is the deliverable, the claim
    # is instrumentation on top of it, so a failure here warns and continues
    # rather than failing the scaffold. The later re-claim at workstream-
    # complete's d-claim-plan-execution-lock (same session) is covered by
    # `claim_artifact`'s plan-class-only re-entrant self-claim branch — this
    # acquisition does not disturb that.
    if doc_type == "plan":
        _ensure_engine_on_path()
        try:
            from coordinator_core.session.claims import claim_plan  # noqa: PLC0415

            _plan_stem = os.path.splitext(os.path.basename(out_path))[0]
            if not claim_plan(_plan_stem, cwd=_write_repo_root):
                print(
                    f"coordinator-doc-new: plan claim not taken for {_plan_stem} "
                    "— scaffold written; reconcile the claim separately",
                    file=sys.stderr,
                )
        except Exception as _claim_exc:  # noqa: BLE001 -- non-fatal, see above
            print(
                f"coordinator-doc-new: plan claim not taken for {out_path} "
                f"({_claim_exc}) — scaffold written; reconcile the claim separately",
                file=sys.stderr,
            )

    # Success-path-only liveness stamp (completion_scaffold): reached only after the
    # write above completed without raising, and only for --type completion -- every
    # other doc_type's scaffold-write is out of this housekeeping class' remit.
    if doc_type == "completion":
        _stamp_completion_scaffold_liveness(_anchored_repo_root or _current_repo_root())

    # Print a repo-root-relative pointer so callers (e.g. code-reviewer DONE: <path>)
    # get a stable path regardless of the cwd from which they invoked this tool.
    # When the path was not re-anchored (no git repo or explicit --out), emit as-is.
    if _anchored_repo_root:
        # POSIX-normalized: this pointer is a stable cross-cwd id (fed into
        # sidecar_path:/markdown-link consumers, e.g. code-reviewer DONE:
        # <path>), not a filesystem handle a caller reopens locally --
        # os.path.relpath() returns native-separator (backslash) strings on
        # Windows, which those downstream consumers don't expect.
        print(
            os.path.relpath(
                os.path.realpath(out_path), os.path.realpath(_anchored_repo_root)
            ).replace(os.sep, "/")
        )
    else:
        print(out_path)


if __name__ == "__main__":
    main()
