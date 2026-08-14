# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""wsc-tail.py — ceremony.wsc_tail native trampoline (DoE/claude-klabauter wsc_tail cutover).

Purpose: fronts the claude-klabauter op `ceremony.wsc_tail` — the ONE call that replaces
the /workstream-complete mechanical cluster (consumed-handoff resolution,
commit, post-commit stamp-and-ship, origin-stub close, receipt emission).
This module owns transport + the DoE-side exit ladder only; every ceremony
decision (which handoffs resolve, whether the stub-close is soft-fail, what
the commit trailers are) is engine-internal claude-klabauter judgment this trampoline
does not second-guess or re-derive.

Spec backlink: cross-repo/inbox/2026-07-22-claude-klabauter-em-wsc-tail-cutover-clear.md
Spec backlink (claude-klabauter SHAs cited by that memo): 33443b62 (Detector B + spoof guard
+ regression net), 7f512026 (origin-stub fold, step 5d), 3ec1bde5 (review
integration + production-path fix).

Param surface — the 9 keys THIS trampoline wires as CLI flags (per the memo,
wsc_tail.py:413-448) — NOTE these diverge from the DORMANT wsc_commit op's names
(wsc_paths/commit_subject/commit_prose); do not copy that surface:
    sid                required   (resolved caller-side; see session-id tiers below)
    subject            required   (HARD — op returns exit_code 1 without it)
    completion_title   ACCEPT-AND-IGNORE — deprecated, transitional (see below);
                                   no longer required as of 2026-07-23 C4 Phase 1
    prose              optional
    stage_paths        optional   (the SKILL.md's WSC_PATHS)
    trailers           optional   (caller-supplied wins verbatim, else op derives
                                   via commit.anchors)
    governing_plan_slug, deleted_paths, kept_entries, swept_renames
                       optional, forwarded verbatim when the caller supplies them.
    review_trail       optional   (dict, assembled from discrete `--review-*`
                                   flags — see below; forwarded to the op's
                                   `review_trail.write` tail-op)

`review_trail` (wired 2026-07-22 — coverage.gate was returning UNCOVERED on
every ceremony run because this trampoline never exposed it, so
`review_trail.write` always hit its `no-review-metadata` skip and
`coverage.gate` had no review metadata to read). The op
(`coordinator_core/ops/ceremony/tail_ops.py:443-502`, `write_review_trail`)
takes `review_trail` as a dict requiring ALL of `sha_range`/`reviewer`/
`scope`/`verdict`/`diff_loc` (op-side `_REVIEW_TRAIL_REQUIRED_FIELDS`,
tail_ops.py:101) before it forwards the call at all — an incomplete dict is
treated as "no review this session" and skipped cleanly, not an error. This
CLI exposes discrete flags (`--review-sha-range`, `--review-reviewer`,
`--review-scope`, `--review-verdict`, `--review-diff-loc`, plus optional
`--review-scope-kind`/`--review-workstream`) assembled into the dict, matching
the existing `coordinator-write-review-trail.py` flag-naming idiom, rather
than asking the caller to hand-write a JSON blob on a command line.

**N partitioned-review slices (partitioned-review fix, second half):**
`decisions["review"]` upstream can be a `list[dict]` as well as a single
`dict` (`workstream_complete.build_write_trail_directives`,
`directives_commit_tail._review_fields_present`) — the repeatable
`--review-slice <json>` flag carries that shape through THIS trampoline's
single embedded `review_trail.write` call: one flag per slice, each value a
compact JSON object with the same five required keys the discrete flags
below carry plus optional `scope_kind` (`_REVIEW_SLICE_ALLOWED_KEYS`).
Mutually exclusive with the discrete `--review-*` flags — supplying both is
a hard error (`_review_slices_and_discrete_flags_both_supplied`), never a
silent pick-one. Every slice is validated up front, same JSON-shape/
required-field/closed-enum checks the discrete flags get
(`_parse_review_slices`) — malformed input refuses the WHOLE dispatch,
consistent with the discrete-flag partial-supply guard's own posture.
Op-side (`tail_ops.write_review_trail_many`), each qualifying slice is
written as its own independent `review_trail.write` record: one slice's
foreign-session-range refusal never suppresses a sibling's write.

**Partial-supply guard (wired 2026-07-22, same day as the wiring above):**
if the caller supplies ANY `--review-*` flag but not all five required ones,
this trampoline refuses to dispatch (exit 1, stderr names the missing
fields) rather than forwarding a partial dict for the op to silently skip.
The op cannot distinguish "no review happened" from "caller fumbled the
flags" — only the caller knows which — so that distinction is enforced here,
not op-side. Supplying none of the seven flags is unaffected: that is still
the legitimate no-review-this-session case and stays a clean omission.

*Deliberate divergence — this guard is STRICTER than the engine, do not
"correct" it to match.* The op's own required-field check is
`review_trail.get(field) not in (None, "")` (`tail_ops.py`) — it does not
strip, so a whitespace-only value passes as present and the op writes a
review-trail record with a blank verdict. That is worse than the silent skip
this guard exists to prevent: garbage data rather than missing data. Here,
`.strip()`-empty counts as missing, so `--review-verdict " "` is rejected as
the caller fumble it plainly is. EM ruling 2026-07-22 — a boundary that only
rejects what the engine rejects adds nothing; catching what the engine
swallows is the entire point of the guard.

The op's full optional surface (per the memo) is larger than what this CLI
exposes: `caller_paths`, `nature`, `b_adjudication_present`, `coverage_range`,
`coverage_from_handoff`, `coverage_scope_paths` are available op-side but have
no corresponding argparse flag on this trampoline — not yet exposed on this
CLI. No current caller (the SKILL.md Step 3 invocation) needs them; wire a
flag for one only when a caller actually does.

completion_title — ACCEPT-AND-IGNORE, transitional (2026-07-23 wsc-tail-slim-down
plan, C4 Phase 1; `docs/plans/2026-07-23-wsc-tail-slim-down.md` § Param Disposition).
Until 2026-07-23 this flag was HARD-REQUIRED on the DoE side specifically because
the op silently omits Step 2.6's completion-entry scaffold when it's absent (the
op does not error) — the memo named that silent-omission failure mode "the single
most likely way the cutover goes subtly wrong," and refusing to dispatch without
the flag was the corrective. That corrective is now SUPERSEDED by a bilateral
landing-order decision: C4's own disposition moves the completion-entry scaffold
OUT of this op entirely and into a DoE-side WSC skill Step 2.6 re-expansion
(direct `coordinator-complete-entry.py` invocation), so the flag's hard-required
posture would otherwise hard-fail every ceremony in the skew window between
Claude-klabauter landing this change and DoE landing its re-expansion (see the plan's
§ Landing Order and Skew Tolerance — "every claude-klabauter-side shed chunk must tolerate
the pre-DoE-landing state, accept-and-ignore params rather than hard-failing").
Phase 1 (this change): `--completion-title` is `required=False`; supplying it
or omitting it both dispatch cleanly, no warning, no error either way. The op's
own scaffold behaviour is UNCHANGED in this phase — if the flag IS supplied, the
value is still genuinely forwarded and still feeds Step 2.6's completion-entry
scaffold (see `_run_precommit_tail`'s `if completion_title:` branch,
`coordinator_core/ops/ceremony/wsc_tail.py`) — this is a requiredness change, not
a behaviour change. Phase 2 (DoE, tracked separately, not this repo): the skill
re-expansion lands and stops passing this flag. Phase 3 (later, separate change):
the flag is removed from this trampoline once no consumer passes it — never in
the same wave as Phase 1 or 2. Do NOT re-add `required=True` to this flag, and
do NOT "clean it up" by dropping it early — see the parser help text and the
Negative-spec below.

Exit-ladder implementation choice: this module calls cc_invoke.route() directly
and inspects the returned payload's exit_code itself, rather than
route_mutation(). route_mutation() raises RouteMutationError on ANY non-zero
exit_code, which would turn claude-klabauter's exit-2 soft-fail (a landed commit with a
recoverable tail-item issue — e.g. an unclosed origin stub) into an uncaught
DoE hard failure. The memo's exit-2 semantics ("recoverable, not a breach")
are a normal, expected, print-diagnostics-and-continue outcome here, not a
mutation refusal shape route_mutation is built to catch. Distinguishing
"exit 1 hard failure" from "exit 2 landed-but-flagged" requires reading the
payload before deciding whether to fail loud — route() applied that
discrimination inline is cleaner than catching-and-inspecting a raised
RouteMutationError for the same purpose.

DoE-side exit ladder (this module's contract, distinct from the op's internal
exit_code semantics which this module reads, not re-emits verbatim):
    0 -> success, no tail-item concerns.
    2 -> commit landed but a tail item needs attention (op exit_code 2 —
         failed_critical / soft-fail / integrity_breach / empty_consumed_set).
         NOT a halt: diagnostics/tail_results printed to stderr verbatim;
         re-running blindly would be wrong since the commit already landed.
    1 -> hard failure: op exit_code 1 (e.g. commit_failed), a bare 'error'
         string in the payload, or repo-root resolution failure.
    3 -> transport failure / seam absent (cc_invoke.route() raised).

Session-id resolution mirrors append-plan-session.py's tiers 1-3
(COORDINATOR_SESSION_ID > CLAUDE_SESSION_ID > CLAUDE_CODE_SESSION_ID); tier 4
(the .git/coordinator-sessions sentinel) is intentionally not ported here,
for the same reason that exemplar gives (modern Claude Code always sets
CLAUDE_CODE_SESSION_ID).

Negative-spec (what this module does NOT do):
    - Does NOT require `--completion-title` (transitional, C4 Phase 1,
      2026-07-23) — a future reader must not "clean up" this param by making it
      required again or dropping it early; see the flag's own help text and
      the module docstring's `completion_title` paragraph above for the full
      Phase 1/2/3 landing-order rationale. Phase 2 (DoE) and Phase 3 (later,
      separate removal) are NOT this change.
    - No business logic: does not decide which handoffs are consumed, does not
      compute trailers, does not decide stub-close severity — all engine-internal.
    - No engine internals: does not import coordinator_core directly; the sole
      transport is cc_invoke.route().
    - Does NOT re-derive committed_sha — that is the op's own on_committed
      callback; this trampoline only reads whatever the op's payload reports.
    - Does NOT swallow exit 2 — a soft-fail tail item is always surfaced to
      stderr verbatim, never silently absorbed into a bare 0 exit.
    - Does NOT sequence a second op call (e.g. handoff.close_origin_stub) —
      the memo folded stub-close into wsc_tail step 5d specifically so no
      caller has to carry that judgment; this trampoline makes ONE call.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_BIN_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import cc_invoke  # noqa: E402
from repo_identity import resolve_checked_repo_root  # noqa: E402

_SESSION_ID_ENV_TIERS = (
    "COORDINATOR_SESSION_ID",
    "CLAUDE_SESSION_ID",
    "CLAUDE_CODE_SESSION_ID",
)


def _resolve_session_id() -> str:
    """Tiers 1-3 only — see module docstring for the tier-4 carve-out."""
    for var in _SESSION_ID_ENV_TIERS:
        val = os.environ.get(var, "")
        if val:
            return val
    return ""


def legacy_wsc_tail() -> None:
    """Fail-loud stand-in — reached only when coordinator_core.invoke is NOT
    importable on disk (State-1 dispatch target). There is no pre-cutover
    legacy body for wsc_tail to fall back to; a genuinely-absent seam is a
    hard error, not a legacy path.
    """
    raise RuntimeError(
        "wsc-tail.py: coordinator_core.invoke seam absent — no legacy path "
        "(wsc_tail cutover); cannot dispatch ceremony.wsc_tail"
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wsc-tail.py",
        description="Trampoline for ceremony.wsc_tail — the /workstream-complete tail.",
    )
    parser.add_argument(
        "--sid",
        default=None,
        help="Session id. Defaults to the resolved COORDINATOR_SESSION_ID / "
        "CLAUDE_SESSION_ID / CLAUDE_CODE_SESSION_ID env tier chain.",
    )
    parser.add_argument("--subject", required=True, help="Commit subject (HARD required by the op).")
    parser.add_argument(
        "--completion-title",
        required=False,
        default=None,
        dest="completion_title",
        help="Completion-entry title (DEPRECATED, transitional accept-and-ignore — "
        "2026-07-23 wsc-tail-slim-down C4 Phase 1). No longer required: supplying "
        "it or omitting it both dispatch cleanly. When SUPPLIED, the value is "
        "still genuinely forwarded to the op and still feeds Step 2.6's "
        "completion-entry scaffold today — this flag is not yet a no-op, only "
        "no longer mandatory. Phase 2 (DoE-side WSC skill re-expansion) moves "
        "the scaffold invocation to a direct CLI call and stops passing this "
        "flag here; Phase 3 (separate, later change) removes the flag once no "
        "consumer passes it. Do not re-add required=True to this flag — see "
        "module docstring negative-spec.",
    )
    parser.add_argument("--prose", default=None, help="Commit prose (optional).")
    parser.add_argument(
        "--stage-paths",
        dest="stage_paths",
        nargs="+",
        default=None,
        help="Paths to stage (repeatable / space-separated). The SKILL.md's WSC_PATHS.",
    )
    parser.add_argument("--trailers", default=None, help="Caller-supplied commit trailers (optional).")
    parser.add_argument(
        "--governing-plan-slug",
        dest="governing_plan_slug",
        default=None,
        help="Governing plan slug (optional) — also used by the op to derive plan_path "
        "for the origin-stub close.",
    )
    parser.add_argument(
        "--deleted-paths",
        dest="deleted_paths",
        nargs="+",
        default=None,
        help="Deleted paths (optional, repeatable).",
    )
    parser.add_argument(
        "--kept-entries",
        dest="kept_entries",
        nargs="+",
        default=None,
        help="Kept entries (optional, repeatable).",
    )
    parser.add_argument(
        "--swept-renames",
        dest="swept_renames",
        default=None,
        help="Swept renames (optional; JSON string forwarded verbatim).",
    )
    parser.add_argument(
        "--review-sha-range",
        dest="review_sha_range",
        default=None,
        help="review_trail: reviewed sha range. Part of a 5-flag all-or-nothing group "
        "with --review-reviewer/--review-scope/--review-verdict/--review-scope-kind — "
        "supply all five together or none at all (see module docstring).",
    )
    parser.add_argument(
        "--review-reviewer",
        dest="review_reviewer",
        default=None,
        help="review_trail: reviewer name. Part of a 5-flag all-or-nothing group with "
        "--review-sha-range/--review-scope/--review-verdict/--review-scope-kind — "
        "supply all five together or none at all. Allowed: "
        f"{' | '.join(sorted(_VALID_REVIEWERS))}.",
    )
    parser.add_argument(
        "--review-scope",
        dest="review_scope",
        default=None,
        help="review_trail: reviewed scope. Part of a 5-flag all-or-nothing group with "
        "--review-sha-range/--review-reviewer/--review-verdict/--review-scope-kind — "
        "supply all five together or none at all. Allowed: "
        f"{' | '.join(sorted(_VALID_SCOPES))}.",
    )
    parser.add_argument(
        "--review-verdict",
        dest="review_verdict",
        default=None,
        help="review_trail: reviewer verdict. Part of a 5-flag all-or-nothing group with "
        "--review-sha-range/--review-reviewer/--review-scope/--review-scope-kind — "
        "supply all five together or none at all. Allowed: "
        f"{' | '.join(sorted(_VALID_VERDICTS))}.",
    )
    parser.add_argument(
        "--review-diff-loc",
        dest="review_diff_loc",
        default=None,
        help="review_trail: diff LOC reviewed (optional; see --review-sha-range).",
    )
    parser.add_argument(
        "--review-scope-kind",
        dest="review_scope_kind",
        default=None,
        help="review_trail: scope kind (default 'diff' when omitted). Part of a 5-flag "
        "all-or-nothing group with --review-sha-range/--review-reviewer/--review-scope/"
        "--review-verdict — supply all five together or none at all. Allowed: "
        f"{' | '.join(sorted(_VALID_SCOPE_KINDS))}.",
    )
    parser.add_argument(
        "--review-workstream",
        dest="review_workstream",
        default=None,
        help="review_trail: workstream label (optional passthrough).",
    )
    parser.add_argument(
        "--review-reviewer-evidence",
        dest="review_reviewer_evidence",
        default=None,
        help="review_trail: evidence correlating --review-reviewer with an actual review "
        "(optional passthrough, but REQUIRED op-side for every reviewer except "
        "wsc-auto-adjudication -- see coordinator_core/ops/review_trail_write.py's "
        "reviewer_evidence design; state/bug-backlog/2026-08-10-coordinator-write-"
        "review-trail-accepts-a-295d3cd80d13.yaml).",
    )
    parser.add_argument(
        "--review-slice",
        dest="review_slices",
        action="append",
        default=None,
        help="review_trail: ONE partitioned-review slice as a compact JSON object "
        "(keys: sha_range/reviewer/scope/verdict/diff_loc, required; scope_kind, "
        "optional) -- repeatable, one flag per slice. Additive to the discrete "
        "--review-* flags above (which stay the single-record shape, byte-identical); "
        "mutually exclusive with them -- supplying both is a hard error. See module "
        "docstring's 'N partitioned-review slices' section.",
    )
    return parser


# Mirrors the op's own `_REVIEW_TRAIL_REQUIRED_FIELDS` (claude-klabauter
# coordinator_core/ops/ceremony/tail_ops.py:101) — kept in sync deliberately,
# not imported, since this trampoline does not import coordinator_core.
_REVIEW_TRAIL_REQUIRED_FIELDS = ("sha_range", "reviewer", "scope", "verdict", "diff_loc")

# Mirrors `coordinator_core/ops/review_trail_write.py`'s closed enums
# (`_VALID_REVIEWERS`/`_VALID_SCOPES`/`_VALID_VERDICTS`/`_VALID_SCOPE_KINDS`) —
# kept in sync deliberately, not imported (same rationale as
# `_REVIEW_TRAIL_REQUIRED_FIELDS` above: this trampoline never imports
# coordinator_core). Validated HERE, before dispatch, because the op-side
# `_validate()` raising ValueError only surfaces post-dispatch as an ordinary
# `failed[]`/`failed_critical[]` tail entry — usable at the receipt level, but
# invisible to an operator who never opens the receipt (the fail-quiet defect
# this guard exists to close; see 2026-07-28 incident: all three of
# `--review-reviewer`/`--review-scope`/`--review-scope-kind` were invalid
# against these enums and `--help` never named the allowed values, so the
# caller had no way to know before dispatching).
_VALID_REVIEWERS = frozenset(
    {
        "code-reviewer",
        "staff-eng",
        "code-reviewer+staff-eng",
        "waived",
        "ubt-compile",
        "wsc-auto-adjudication",
        "em-verified",
    }
)
_VALID_SCOPES = frozenset({"chain", "session", "workstream-close-auto"})
_VALID_VERDICTS = frozenset({"ok", "warn", "blocked", "waived", "pending"})
_VALID_SCOPE_KINDS = frozenset({"diff", "plan", "integration"})


def _review_trail_fields(args: argparse.Namespace) -> dict:
    """Raw `--review-*` values keyed by their review_trail field name."""
    return {
        "sha_range": args.review_sha_range,
        "reviewer": args.review_reviewer,
        "scope": args.review_scope,
        "verdict": args.review_verdict,
        "diff_loc": args.review_diff_loc,
        "scope_kind": args.review_scope_kind,
        "workstream": args.review_workstream,
        "reviewer_evidence": args.review_reviewer_evidence,
    }


def _missing_review_trail_fields(args: argparse.Namespace) -> list[str]:
    """Which required review_trail fields are absent/blank, IF any --review-*
    flag was supplied at all.

    Guard lives here, not the op: the op's own required-fields check
    (tail_ops.py:101/466-468) treats an incomplete `review_trail` dict as
    "no review this session" and skips `review_trail.write` cleanly — correct
    when the caller truly supplied nothing, but the op cannot tell that case
    apart from a caller who fumbled the flags and supplied only some of them.
    Only the caller knows which; failing loud here is the only place that
    distinction can be made. Returns [] when no `--review-*` flag was
    supplied (the legitimate no-review-this-session case, unchanged) or when
    all five required fields are present and non-blank.
    """
    fields = _review_trail_fields(args)
    if all(v is None for v in fields.values()):
        return []
    return [
        name
        for name in _REVIEW_TRAIL_REQUIRED_FIELDS
        if fields[name] is None or not fields[name].strip()
    ]


def _invalid_review_trail_enum_fields(args: argparse.Namespace) -> list[str]:
    """Which supplied `--review-*` fields fail their closed-enum check, pre-dispatch.

    Only meaningful once `_missing_review_trail_fields` has already returned []
    (i.e. either none of the flags were supplied — nothing to validate here —
    or all five required fields are present). `scope_kind` is optional and
    defaults to ``"diff"`` op-side when omitted, so it is only checked here
    when the caller actually supplied `--review-scope-kind`.

    Returns a list of human-readable ``"<flag>: <value> — allowed: ..."``
    messages, one per invalid field, in flag order (reviewer, scope, verdict,
    scope_kind) — empty when every supplied field is enum-valid.
    """
    checks = (
        ("--review-reviewer", args.review_reviewer, _VALID_REVIEWERS),
        ("--review-scope", args.review_scope, _VALID_SCOPES),
        ("--review-verdict", args.review_verdict, _VALID_VERDICTS),
    )
    messages = [
        f"{flag} {value!r} is invalid; allowed: {' | '.join(sorted(allowed))}"
        for flag, value, allowed in checks
        if value is not None and value not in allowed
    ]
    if args.review_scope_kind is not None and args.review_scope_kind not in _VALID_SCOPE_KINDS:
        messages.append(
            "--review-scope-kind "
            f"{args.review_scope_kind!r} is invalid; allowed: "
            f"{' | '.join(sorted(_VALID_SCOPE_KINDS))}"
        )
    return messages


def _build_review_trail(args: argparse.Namespace) -> dict | None:
    """Assemble the `review_trail` dict from the discrete `--review-*` flags.

    Returns None when the caller supplied none of them — omitting the key
    entirely (rather than sending an empty dict) preserves the op's own
    "no review this session" skip path. By the time this runs,
    `_missing_review_trail_fields` has already refused to dispatch on any
    incomplete-but-nonempty subset, so a non-None return here always carries
    all five required fields.
    """
    fields = _review_trail_fields(args)
    review_trail = {k: v for k, v in fields.items() if v is not None}
    return review_trail or None


#: The subset of `_review_trail_fields`' keys a `--review-slice` JSON object
#: may carry -- still narrower than the discrete-flag surface (no
#: `workstream`): parity with `directives_commit_tail.build_close_tail_args_
#: directive`'s own single-dict `--review-*` branch, which does not emit it
#: either. Widen both surfaces together if that ever changes, not just this
#: one. `reviewer_evidence` joined this set with that branch's
#: `--review-reviewer-evidence` (2026-08-13): the op-side gate
#: (`review_trail_write._verify_reviewer_evidence`) checks a correlation only
#: this argv can deliver, so a narrower slice surface drops the value one
#: layer above the check.
_REVIEW_SLICE_ALLOWED_KEYS = (*_REVIEW_TRAIL_REQUIRED_FIELDS, "scope_kind", "reviewer_evidence")


def _parse_review_slices(args: argparse.Namespace) -> "tuple[list[dict], list[str]]":
    """Parses every `--review-slice` JSON token into a dict, returning
    `(slices, errors)`. `errors` is empty iff every supplied token is valid
    JSON, an object (not a list/scalar), carries no key outside
    `_REVIEW_SLICE_ALLOWED_KEYS`, has all five required fields present and
    non-blank (`.strip()`-empty counts as missing, same divergence
    `_missing_review_trail_fields` documents for the discrete-flag form), and
    passes the same closed-enum checks `_invalid_review_trail_enum_fields`
    applies to the discrete flags. A malformed `--review-slice` is
    unambiguously a caller mistake (unlike an upstream-filtered incomplete
    list entry, which never reaches this CLI as a token at all -- see
    `tail_ops.write_review_trail_many`'s own docstring) so this refuses the
    WHOLE dispatch rather than silently dropping the bad slice, mirroring the
    discrete-flag partial-supply guard's own "fail loud, don't guess"
    posture. Returns `([], [])` when `args.review_slices` is `None`.
    """
    if not args.review_slices:
        return [], []
    slices: "list[dict]" = []
    errors: "list[str]" = []
    for index, raw in enumerate(args.review_slices):
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError) as exc:
            errors.append(f"--review-slice[{index}]: invalid JSON ({exc})")
            continue
        if not isinstance(parsed, dict):
            errors.append(f"--review-slice[{index}]: must be a JSON object, got {type(parsed).__name__}")
            continue
        unknown = sorted(set(parsed) - set(_REVIEW_SLICE_ALLOWED_KEYS))
        if unknown:
            errors.append(f"--review-slice[{index}]: unrecognized key(s) {unknown}")
            continue
        missing = [
            name
            for name in _REVIEW_TRAIL_REQUIRED_FIELDS
            if not isinstance(parsed.get(name), str) or not parsed[name].strip()
        ]
        if missing:
            errors.append(f"--review-slice[{index}]: missing/blank required field(s): {', '.join(missing)}")
            continue
        if parsed["reviewer"] not in _VALID_REVIEWERS:
            errors.append(
                f"--review-slice[{index}]: reviewer {parsed['reviewer']!r} is invalid; "
                f"allowed: {' | '.join(sorted(_VALID_REVIEWERS))}"
            )
        if parsed["scope"] not in _VALID_SCOPES:
            errors.append(
                f"--review-slice[{index}]: scope {parsed['scope']!r} is invalid; "
                f"allowed: {' | '.join(sorted(_VALID_SCOPES))}"
            )
        if parsed["verdict"] not in _VALID_VERDICTS:
            errors.append(
                f"--review-slice[{index}]: verdict {parsed['verdict']!r} is invalid; "
                f"allowed: {' | '.join(sorted(_VALID_VERDICTS))}"
            )
        scope_kind = parsed.get("scope_kind")
        if scope_kind is not None and scope_kind not in _VALID_SCOPE_KINDS:
            errors.append(
                f"--review-slice[{index}]: scope_kind {scope_kind!r} is invalid; "
                f"allowed: {' | '.join(sorted(_VALID_SCOPE_KINDS))}"
            )
        slices.append(parsed)
    return slices, errors


def _review_slices_and_discrete_flags_both_supplied(args: argparse.Namespace) -> bool:
    """True when the caller supplied at least one `--review-slice` AND at
    least one discrete `--review-*` flag -- an ambiguous mix `main()` refuses
    outright rather than guessing which shape wins."""
    if not args.review_slices:
        return False
    return any(v is not None for v in _review_trail_fields(args).values())


def _build_params(args: argparse.Namespace, sid: str) -> dict:
    params: dict = {
        "sid": sid or None,
        "subject": args.subject,
    }
    # `--review-slice` (list-of-dicts) and the discrete `--review-*` flags
    # (single dict) are mutually exclusive (enforced in `main()` before this
    # is called) -- at most one of the two ever contributes a value here.
    review_trail: "dict | list[dict] | None"
    if args.review_slices:
        review_trail, _errors = _parse_review_slices(args)
        # `main()` already refused to reach this point if `_errors` was
        # non-empty -- see the mutual-exclusion/validation pre-flight below.
    else:
        review_trail = _build_review_trail(args)
    optional_map = {
        "completion_title": args.completion_title,
        "prose": args.prose,
        "stage_paths": args.stage_paths,
        "trailers": args.trailers,
        "governing_plan_slug": args.governing_plan_slug,
        "deleted_paths": args.deleted_paths,
        "kept_entries": args.kept_entries,
        "swept_renames": args.swept_renames,
        "review_trail": review_trail,
    }
    for key, value in optional_map.items():
        if value is not None:
            params[key] = value
    return params


def _print_failure_footer(result: dict, *, landed: bool) -> None:
    """Re-emit every failing tail item as the LAST thing on stderr.

    The full payload dump above is authoritative but head-heavy: the failure
    text sits near the top of a multi-hundred-line JSON blob, and the blob's
    tail is the timing map, which reads like a clean run. A caller piping this
    through `| tail -N` -- the shape the 2026-08-03 project-rag-em memo
    (`cross-repo/inbox/2026-08-03-project-rag-em-wsc-tail-exits-zero-without-
    committing.md`) reported closing a workstream with -- therefore sees only
    timings and concludes the ceremony succeeded. It did not: the exit code was
    non-zero and the reason was printed, just above the clip. Repeating the
    reason last means the diagnosis survives truncation from either end.

    Negative-spec: this does NOT change the exit ladder, suppress the payload
    dump, or invent a failure the payload does not carry -- with no failing
    tail item it prints nothing at all. `landed` selects the committed-state
    sentence only; it never gates whether the failures are printed.
    """
    tail_results = result.get("tail_results") or {}
    if not isinstance(tail_results, dict):
        return
    failures: list[str] = []
    for label, item in tail_results.items():
        if not isinstance(item, dict):
            continue
        for key in ("failed_critical", "failed"):
            for entry in item.get(key) or []:
                failures.append(f"{label} [{key}]: {entry}")
    if not failures:
        return
    headline = (
        "commit LANDED but a tail item failed"
        if landed
        else "NOTHING WAS COMMITTED"
    )
    print(
        f"wsc-tail.py: {headline} — failing tail item(s):",
        file=sys.stderr,
    )
    for failure in failures:
        print(f"  - {failure}", file=sys.stderr)


def main(argv: list[str]) -> int:
    # `argv` is args-only (no leading program-name token) -- the convention
    # every sibling consumes-manifest CLI's `main(argv)` follows (see e.g.
    # `workday-complete-reconcile.py`'s identical comment, and
    # `workday_complete.apply._invoke_cli_main` / `workstream_complete.apply.
    # _invoke_cli_main`, which both call `main_fn(list(directive_args))`
    # in-process with no argv[0] placeholder). This function previously did
    # `argv[1:]` here, an off-by-one relative to every sibling that silently
    # ate the first real flag (e.g. `--sid`) under in-process apply dispatch
    # (2026-07-27 arg-mismatch audit — mirrors the 2026-07-26 fix to
    # `workday-complete-reconcile.py`'s identical defect).
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if _review_slices_and_discrete_flags_both_supplied(args):
        print(
            "wsc-tail.py: --review-slice and a discrete --review-* flag were both "
            "supplied -- ambiguous. Use --review-slice (repeatable) for a "
            "partitioned review, or the discrete --review-* flags for a single "
            "record, never both in the same call.",
            file=sys.stderr,
        )
        return 1

    if args.review_slices:
        _slices, slice_errors = _parse_review_slices(args)
        if slice_errors:
            print(
                "wsc-tail.py: invalid --review-slice supply:\n  " + "\n  ".join(slice_errors),
                file=sys.stderr,
            )
            return 1
        # Discrete-flag validation below is moot when slices were supplied
        # (the mutual-exclusion check above already refused any mix, and
        # `_missing_review_trail_fields`/`_invalid_review_trail_enum_fields`
        # both no-op on an all-None discrete-flag Namespace regardless) --
        # skip explicitly rather than relying on that no-op, for clarity.
        missing_review_fields: list[str] = []
        invalid_review_fields: list[str] = []
    else:
        missing_review_fields = _missing_review_trail_fields(args)
        invalid_review_fields = _invalid_review_trail_enum_fields(args)
    if missing_review_fields:
        print(
            "wsc-tail.py: partial review_trail supply — missing/blank required "
            f"field(s): {', '.join(missing_review_fields)}. The op requires all "
            "five of sha_range/reviewer/scope/verdict/diff_loc or it silently "
            "skips review_trail.write with no-review-metadata (no error) — "
            "supply all five --review-* flags, or none at all.",
            file=sys.stderr,
        )
        return 1

    # Enum pre-flight (2026-07-28 fail-quiet fix): reject BEFORE the commit
    # pipeline ever runs, naming the allowed values, rather than letting the
    # op's own `_validate()` raise post-dispatch where the failure is only
    # visible in the receipt file (nothing committed yet at this point, so
    # exit 1 -- no landed-commit disposition to preserve). (`invalid_review_
    # fields` was already computed above -- discrete-flag branch calls
    # `_invalid_review_trail_enum_fields`, slice branch's own per-slice enum
    # checks already ran inside `_parse_review_slices`.)
    if invalid_review_fields:
        print(
            "wsc-tail.py: invalid review_trail field value(s):\n  "
            + "\n  ".join(invalid_review_fields),
            file=sys.stderr,
        )
        return 1

    repo_root, verdict = resolve_checked_repo_root(explicit_root=None)
    if repo_root is None:
        print(
            f"wsc-tail.py: cannot resolve git repo root from {os.getcwd()}",
            file=sys.stderr,
        )
        return 1
    if verdict["verdict"] == "MISMATCH":
        # DR-277: READER (no write into resolved root) -- warn and proceed
        # rather than refuse. UNRESOLVED never refuses either (AC4).
        print(verdict["message"], file=sys.stderr)

    # Directory pathspec pre-flight (2026-08-03, project-rag-em memo
    # `cross-repo/inbox/2026-08-03-project-rag-em-wsc-tail-exits-zero-without-
    # committing.md`, ask 3): the engine's own pre-stage guard
    # (`commit_pipeline.run_commit_pipeline`) already refuses a directory in
    # `stage_paths` and the refusal already reaches this trampoline as
    # exit_code=1 -- but only AFTER a full op dispatch, so the operator reads
    # it out of a post-dispatch failure dump instead of a usage error at the
    # keyboard they are standing at. Refusing here converts the whole class
    # into an immediate argument error, before any transport or receipt.
    # Deliberately a plain `is a directory` test rather than a
    # `git_native.directory_pathspecs()` call: this module's Negative-spec
    # forbids importing coordinator_core (cc_invoke.route is the sole
    # transport), and the engine-side predicate stays the load-bearing guard
    # -- this is a caller-side superset of it, not a replacement.
    stage_dirs = [
        p
        for p in (args.stage_paths or [])
        if os.path.isdir(os.path.join(repo_root, p))
    ]
    if stage_dirs:
        print(
            "wsc-tail.py: --stage-paths rejects a directory pathspec -- a "
            "directory matches whatever is inside it AT COMMIT TIME, including "
            "a peer's file added after this path set was computed. Pass "
            "explicit file paths instead. Offending: "
            + ", ".join(repr(p) for p in stage_dirs),
            file=sys.stderr,
        )
        return 1

    sid = args.sid or _resolve_session_id()
    params = _build_params(args, sid)

    try:
        result = cc_invoke.route("ceremony.wsc_tail", params, repo_root, legacy_wsc_tail)
    except RuntimeError as exc:
        # Transport failure (State-3) or legacy-seam-absent raise (State-1).
        print(f"wsc-tail.py: {exc}", file=sys.stderr)
        return 3

    if not isinstance(result, dict):
        print(
            f"wsc-tail.py: unexpected non-dict payload from ceremony.wsc_tail: "
            f"{result!r}",
            file=sys.stderr,
        )
        return 1

    error_field = result.get("error")
    if isinstance(error_field, str) and error_field and "exit_code" not in result:
        print(f"wsc-tail.py: op refused: {error_field}", file=sys.stderr)
        return 1

    raw_exit_code = result.get("exit_code", 0)
    try:
        exit_code = int(raw_exit_code) if raw_exit_code is not None else 0
    except (TypeError, ValueError):
        exit_code = 0

    # Defense-in-depth (2026-07-28 fail-quiet fix): review_trail metadata WAS
    # supplied (the missing/invalid-field pre-flights above both already
    # passed) yet `review_trail.write` still landed in this tail item's own
    # `failed[]` -- e.g. the write-side foreign-session scope guard, a race,
    # or any op-side failure this trampoline's enum mirror doesn't (yet)
    # anticipate. The op's own `soft_failed` aggregation (wsc_tail.py's
    # exit-code discriminator) already forces `exit_code=2` for this case
    # today, but that aggregation spans every tail item, not just
    # review_trail -- this check is the narrow, review_trail-specific
    # guarantee: a commit landing while genuinely-supplied review metadata
    # silently failed to record MUST NOT read as exit 0, independent of
    # whatever the op's cross-item aggregation happens to compute. Never
    # DOWNGRADES an exit_code the op already escalated (e.g. 1) -- only
    # bumps a 0 up to 2, and only for this one named tail item.
    review_trail_result = result.get("tail_results", {}).get("review_trail.write", {})
    review_trail_failed = review_trail_result.get("failed") or review_trail_result.get(
        "failed_critical"
    )
    if review_trail_failed and exit_code == 0:
        print(
            "wsc-tail.py: review_trail.write failed with metadata supplied, but "
            f"ceremony.wsc_tail reported exit_code=0 -- forcing exit_code=2 "
            f"(commit landed; review record was NOT written): {review_trail_failed!r}",
            file=sys.stderr,
        )
        exit_code = 2

    if exit_code == 1:
        print(
            f"wsc-tail.py: ceremony.wsc_tail hard failure (exit_code=1): "
            f"{json.dumps(result, indent=2, default=str)}",
            file=sys.stderr,
        )
        _print_failure_footer(result, landed=False)
        return 1

    if exit_code == 2:
        print(
            "wsc-tail.py: commit landed; a tail item needs attention "
            "(exit_code=2 — soft-fail/failed_critical/integrity_breach/"
            "empty_consumed_set). Diagnostics:",
            file=sys.stderr,
        )
        # Latent-bug fix (this dispatch): `result.get("diagnostics", ...)`'s
        # default only fires when the key is ABSENT, never when it's present
        # but an empty list -- and `diagnostics` is always a present key on
        # this payload (see wsc_tail.py's return contract), often populated
        # with generic timing entries rather than the actual per-tail-item
        # failure text. That silently hid the real reason (e.g. a
        # review_trail.write validation error) behind timing noise on every
        # exit_code=2 pass. Print both explicitly instead of choosing one via
        # a `.get(..., default)` that can't actually reach its default.
        print(
            json.dumps(
                {
                    "diagnostics": result.get("diagnostics") or [],
                    "tail_results": result.get("tail_results", {}),
                },
                indent=2,
                default=str,
            ),
            file=sys.stderr,
        )
        _print_failure_footer(result, landed=True)
        return 2

    if exit_code != 0:
        print(
            f"wsc-tail.py: unexpected exit_code={exit_code!r} from ceremony.wsc_tail: "
            f"{json.dumps(result, indent=2, default=str)}",
            file=sys.stderr,
        )
        return 1

    # Silent-exit-0 fix (cross-repo/inbox/2026-08-10-doe-claude-em-wsc-tail-
    # silent-noop-and-gate-rewalk.md finding 1): this branch used to `return 0`
    # with NOTHING printed, on every genuinely-clean pass AND on a pass that
    # landed a commit without a terminal flip alike -- exit 0 with empty
    # stdout/stderr is indistinguishable from "verified nothing was due" (see
    # module docstring negative-spec: "Does NOT swallow exit 2 ... never
    # silently absorbed into a bare 0 exit" -- that guarantee never covered
    # exit 0 itself). The op now always names its disposition explicitly in
    # `diagnostics` (wsc_tail.py's own chain_terminal=False branch), so print
    # it here when present -- still exit 0, never escalated; this is
    # observability, not a new failure class.
    diagnostics = result.get("diagnostics") or []
    if diagnostics:
        print(
            "wsc-tail.py: ceremony.wsc_tail exit_code=0 -- diagnostics:",
            file=sys.stderr,
        )
        for line in diagnostics:
            print(f"  - {line}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
