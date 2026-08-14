# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""sweep-shipped-handoffs.py — batch sweep: find terminal handoffs, archive via
the native fleet.archive_completed_handoffs op.

Purpose: finder+dispatcher over state/handoffs/*.md.
Does NOT re-implement archival logic — delegates the accumulated candidate
list to fleet.archive_completed_handoffs (bulk op; self-commits its own
git-mv) via cc_invoke.route_mutation().

Coverage: the full TERMINAL class of deployment_state — per DR-084's
`coordinator_core.lifecycle_constants.HANDOFF_TERMINAL_DEPLOYMENT`
(shipped, abandoned, continued, closed) — not shipped-only. That constant
is the single source of truth for the selector; do not re-hardcode a
tuple here. The filename is retained for reference-stability even though
the selector covers the broader terminal set (orphan-reaper-flipped
abandoned/continued/closed handoffs are just as terminal as shipped ones
and must not be stranded in state/handoffs/). Note `superseded` is
deliberately NOT in this selector — per lifecycle_constants.py, it lives
on the `status` axis (HANDOFF_TERMINAL_STATUS), not `deployment_state`;
a disk scan of state/handoffs/ and archive/handoffs/ at fix time found no
handoff carrying `deployment_state: superseded`, and every other
HANDOFF_TERMINAL_DEPLOYMENT consumer (fleet/_common.py, reconcile/gate_eval.py)
reads the bare constant with no such union.

Usage:
    python3 sweep-shipped-handoffs.py

Env overrides:
    SWEEP_STALE_THRESHOLD_DAYS — staleness threshold in days for the
        unresolvable WARNING path (default: 14). Applies to the shipped
        subclass only (see negative-spec below).

Negative-spec — retained-forever failure mode, now escaped past the stale
threshold (C9 / AC15):
    A handoff whose deployment_state is "shipped" but whose shipped_in SHA
    can no longer be resolved (branch-tip commit gc'd after a
    squash/rebase merge to main, or an 8-char prefix became ambiguous) is
    retained SILENTLY by the fail-closed posture below the stale threshold.
    The only observable signal before the threshold is the WARNING line
    emitted when stale_unresolvable > 0 at sweep end. This SHA-resolvability
    gate applies ONLY to the shipped subclass — abandoned/continued/closed
    handoffs never carry a shipped_in SHA and skip this gate entirely.

    Past the stale threshold (§ Env overrides, SWEEP_STALE_THRESHOLD_DAYS),
    `_stamp_unresolvable_escape` fires instead of retaining forever: it
    records the dead SHA into the SEPARATE, non-discriminant
    `shipped_in_unresolvable_sha` frontmatter field and the handoff joins
    the normal archive candidate list. `shipped_in_kind` is NEVER touched by
    this path — whatever the writer originally stamped (ship-commit,
    no-commit, ...) survives unchanged; only a NEW field records the
    reader-side observation "this SHA was honestly recorded, then
    invalidated by history rewriting." A stamp failure (lock timeout,
    unparseable frontmatter) leaves the handoff exactly where it was before
    this chunk: retained, counted into unresolvable/stale_unresolvable, and
    retried next sweep. See docs/plans/2026-07-28-handoff-close-path-fail-loud.md
    § C9 for the corrected shape and why `shipped_in_kind` must not be
    rewritten to `no-commit` here (would replace a TRUE write-time
    provenance record with a FALSE one).

Exit codes:
    0 — normal (including all-retained / empty tree / stale-unresolvable).
    1 — the underlying fleet.archive_completed_handoffs dispatch failed:
        either a caught transport RuntimeError (no bash fallback) or the op
        itself reporting exit_code == 2 (partial). Candidates are retained
        for the next sweep either way, but the caller must not read that
        retention as a normal outcome. (C4 / AC13)
    2 — internal error (not inside a git repo, or state root unresolvable).

Negative-spec (C4 / AC13) — 0 is legitimate ONLY for all-retained (guard
retention: no candidates were dispatch-eligible, e.g. every shipped handoff
has an unresolvable SHA, including past the stale threshold),
empty-tree, and a fully successful dispatch. A caught RuntimeError or an
op-reported exit_code == 2 are dispatch FAILURES, not retention -- they
exit 1, distinct from the internal-error 2 above and from the legitimate-0
set. Do not fold either failure branch back into 0: that is the exact
"refusal indistinguishable from success at the caller's rc" defect this
chunk fixes (see docs/plans/2026-07-28-handoff-close-path-fail-loud.md § S12
site (a)).

Big-bang cutover (2026-07-19 Windows de-bash campaign, Wave F1): no legacy
bash fallback — a genuinely seam-absent install surfaces as a transport
failure (RuntimeError), caught below and logged (best-effort ceremony),
candidates retained for the next sweep.

Spec backlink: pln-shipped-handoff-archive-sweep-d61d01
Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md § Wave F1 (facade collapse)
Wraps: fleet.archive_completed_handoffs (native op, bulk primitive)

Liveness stamp (C2, 2026-07-23 wsc-tail-slim-down; exit-code note added C4/AC13):
every completion that reaches the sweep-processing tail -- exit 0 (including
zero-candidates and all-retained) AND exit 1 (dispatch failure, § Exit codes
above) -- stamps the shared `archive_sweeps` housekeeping-liveness key
(`coordinator_core.ops.ceremony.housekeeping_liveness.stamp_liveness`),
mirroring `sweep-boot.py`'s own `_stamp_archive_sweeps_liveness`. The stamp
means "a sweep ran," not "a sweep succeeded" -- it is orthogonal to the rc
distinction AC13 introduces. Multiple producers stamping the same key is
additive-safe (last-writer-wins liveness signal). The two internal-error
paths (exit 2 -- not a git repo / state root unresolvable) return before
reaching the tail and never stamp.
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
import cc_invoke  # noqa: E402
from repo_identity import resolve_checked_repo_root  # noqa: E402


def _ensure_claude_klabauter_on_path() -> str:
    """Idempotently put the claude-klabauter root on sys.path; returns it.

    The file's ONE claude-klabauter-root path-resolution site — every consumer
    (`_import_housekeeping_seam`, `_resolve_state_root`,
    `_terminal_deployment_states`) routes through this, never re-deriving
    the root or re-inserting it independently. (`_LIB_DIR` above is a
    different root — the `coordinator/bin/lib` dir for `cc_invoke` itself
    — and is not part of this dedup.)

    Resolves self-location-first (this script's own enclosing checkout)
    ahead of the pointer-file/registry rungs — see
    `cc_invoke.resolve_engine_root`'s docstring. Raises RuntimeError,
    same as the ladder it replaces, when every rung misses; callers that
    catch RuntimeError around this (`_resolve_state_root`,
    `_resolve_repo_root`) keep working unchanged.
    """
    return cc_invoke.require_engine_on_path(__file__)


def _import_housekeeping_seam():
    """Resolve CLAUDE_KLABAUTER_ROOT and import `housekeeping_liveness.{stamp_liveness,ARCHIVE_SWEEPS}`.

    Mirrors `sweep-boot.py::_import_housekeeping_seam` / the copies in the sibling
    per-class CLIs -- best-effort; returns None on any resolution/import failure.
    """
    try:
        _ensure_claude_klabauter_on_path()
        from coordinator_core.ops.ceremony.housekeeping_liveness import (
            ARCHIVE_SWEEPS,
            stamp_liveness,
        )
    except Exception:  # noqa: BLE001 -- best-effort; never let seam-import failure mask the real error
        return None
    return stamp_liveness, ARCHIVE_SWEEPS


def _stamp_archive_sweeps_liveness(repo_root: str) -> None:
    """Best-effort stamp the shared `archive_sweeps` housekeeping-liveness key.

    Called from the success path only (never on an internal-error exit).
    """
    seam = _import_housekeeping_seam()
    if seam is None:
        return
    stamp_liveness, archive_sweeps = seam
    try:
        stamp_liveness(repo_root, archive_sweeps)
    except Exception:  # noqa: BLE001 -- never raise out of a best-effort liveness stamp
        pass


def _stamp_unresolvable_escape(handoff_path: str, repo_root: str, dead_sha: str) -> bool:
    """Stamp the C9/AC15 unresolvable-escape marker; never touches `shipped_in_kind`.

    Records `dead_sha` into a SEPARATE, non-discriminant field
    (`shipped_in_unresolvable_sha`) so the caller can add this handoff to the
    archive candidate list without rewriting `shipped_in_kind` — see
    docs/plans/2026-07-28-handoff-close-path-fail-loud.md § C9: stamping the
    existing `no-commit` kind here would overwrite a TRUE write-time
    provenance record (a real ship commit, honestly stamped) with a FALSE
    one, purely to satisfy the archival predicate.

    `handoff.schema.json`'s top-level object carries no `additionalProperties:
    false` (verified at authoring time — every other undeclared-but-written
    field in this schema, e.g. `gate_cleared_by` pre-declaration, relies on
    the same openness), so this new field validates with no schema edit, no
    version bump, and no DR-097 notification — exactly the "data added to a
    non-discriminant field, not a vocabulary change" the plan's corrected C9
    body specifies.

    Idempotent: re-stamping the same dead_sha onto an already-marked handoff
    is a byte-identical no-op (locked_rmw's own no-write-on-identical
    contract) — a sweep that stamps and then dispatch-fails leaves a safe
    retry target for the next sweep, not a double-write.

    Returns True on a successful (or already-idempotent) stamp; False on any
    failure, which the caller treats as "still unresolvable, retry next
    sweep" — never as a whole-sweep dispatch failure. Best-effort by design:
    one handoff's malformed frontmatter or a lock timeout must not prevent
    every other candidate in this sweep from archiving.
    """
    _ensure_claude_klabauter_on_path()
    from coordinator_core.frontmatter.primitives import (  # noqa: PLC0415
        insert_fm_field,
        read_fm_field_unquoted,
        rebuild,
        replace_fm_field,
        split_frontmatter,
    )
    from coordinator_core.locked_write import locked_rmw  # noqa: PLC0415
    from coordinator_core.session.declared_writes import declare_write  # noqa: PLC0415

    target = Path(handoff_path)
    changed = False

    def mutate(old_text: str) -> str:
        nonlocal changed
        split = split_frontmatter(old_text)
        if split is None:
            raise ValueError(f"unresolvable-escape: no parseable frontmatter in {target}")

        existing = read_fm_field_unquoted(split.fm_text, "shipped_in_unresolvable_sha")
        if existing == dead_sha:
            return old_text  # already stamped with this exact dead SHA — no-op

        fm = split.fm_text
        if read_fm_field_unquoted(fm, "shipped_in_unresolvable_sha") is not None:
            fm = replace_fm_field(fm, "shipped_in_unresolvable_sha", dead_sha, numeric_quoting=True)
        else:
            fm = insert_fm_field(
                fm, "shipped_in_unresolvable_sha", dead_sha, "shipped_in_kind", numeric_quoting=True
            )
        changed = True
        return rebuild(split, fm)

    try:
        locked_rmw(target, mutate, repo_root=Path(repo_root))
    except Exception as exc:  # noqa: BLE001 -- best-effort per file; caller retries next sweep
        print(
            f"sweep-shipped-handoffs.py: unresolvable-escape stamp failed for {target}: {exc}",
            file=sys.stderr,
        )
        return False
    # DR-276: declared only when `mutate` actually produced new content —
    # locked_rmw's own no-write-on-identical contract means the already-
    # stamped (idempotent no-op) branch above must declare nothing.
    if changed:
        declare_write(target)
    return True


_FRONTMATTER_KEY_RE = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$')


def _parse_frontmatter(path: str) -> dict[str, str]:
    """Minimal YAML-frontmatter top-level key/value reader.

    Faithful port of the bash oracle's awk-based single-key extraction —
    reads only scalar top-level keys between the leading `---`/`---` pair
    (never a full YAML parse; mirrors the bash body's own narrow contract).
    """
    fields: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return fields

    in_fm = False
    seen_close = False
    for line in lines:
        stripped = line.rstrip("\n")
        if not in_fm:
            if stripped.strip() == "---":
                in_fm = True
            continue
        if stripped.strip() == "---":
            seen_close = True
            break
        m = _FRONTMATTER_KEY_RE.match(stripped)
        if m:
            key, val = m.group(1), m.group(2).strip()
            fields.setdefault(key, val)
    if not seen_close:
        return {}
    return fields


def _strip_quotes(value: str) -> str:
    """Strip a single matched pair of surrounding quotes.

    serializeYamlScalar (coordinator/bin/lib/schema.js) single-quotes
    all-digit values (SHA-shaped strings would otherwise YAML-coerce to
    int); this reader must tolerate that quoting or an all-digit SHA
    prefix fails the git cat-file lookup below.
    """
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _batch_resolve_shipped_shas(shas: "set[str]", cwd: str) -> "dict[str, bool]":
    """Batch-resolve MANY `shipped_in` SHA tokens to commit-existence in ONE
    `git cat-file --batch-check` spawn (C11) -- replaces the retired
    `_git_cat_file_e`'s one-spawn-per-handoff `git cat-file -e <sha>^{commit}`.

    Adopts `coordinator_core.coverage._batch_check_hex_tokens` AS-IS (the
    site's own safe-primitive map -- Task C site 8 -- rules this an
    unconditionally-safe OBJECT-existence batch, not a RANGE batch: each
    stdin line is resolved independently, so the rev-list set-algebra
    forbidding this class for RANGE batching never applies here). Each token
    is fed as `<sha>^{{commit}}` -- the same peel-to-commit expression the
    retired per-item call used -- so a tag or other non-commit object is
    correctly rejected rather than accepted as resolved.

    Reconciliation (§ anti-scope 25): `_batch_check_hex_tokens` is documented
    (its own docstring) to return exactly one entry per requested token --
    an unresolved token maps to None, it is never OMITTED from the returned
    dict. This function does not assume that contract holds silently: it
    reconciles the returned key set against every peeled token requested and
    treats ANY token absent from the returned mapping as unresolved
    (fail-closed, same disposition as an explicit None) -- absence is never
    read as "resolved". Mirrors the reconciliation shape of
    `emit/sections/handoffs.py::_resolve_shipped_in_dates` (prefix-match
    against a `matched` set), adapted here to a batch-check dict lookup
    rather than a prefix-match, since `--batch-check` already returns one
    line per input token in order.

    Returns {sha: True_if_resolves_to_a_commit}. On any resolution failure
    (import/transport), every requested sha resolves to False -- the same
    fail-closed posture `_git_cat_file_e` had on an OSError/RuntimeError.
    """
    if not shas:
        return {}
    tokens = sorted(shas)
    peeled = {sha: f"{sha}^{{commit}}" for sha in tokens}
    try:
        _ensure_claude_klabauter_on_path()
        from coordinator_core.coverage import _batch_check_hex_tokens  # noqa: PLC0415
    except Exception:  # noqa: BLE001 -- fail-closed, mirrors _git_cat_file_e's except clause
        return {sha: False for sha in tokens}
    try:
        raw = _batch_check_hex_tokens(list(peeled.values()), cwd)
    except (OSError, RuntimeError):
        return {sha: False for sha in tokens}
    out: dict[str, bool] = {}
    for sha in tokens:
        token = peeled[sha]
        # § anti-scope 25 reconciliation: an absent key is unresolved, never resolved.
        out[sha] = token in raw and raw[token] is not None
    return out


def _resolve_state_root(repo_root: str) -> str:
    """Resolve per-repo state root via the native coordinator_state_root seam.

    Big-bang cutover: no bash-lib fallback. A resolution failure here means
    a broken install (claude-klabauter is a mandatory dependency) — fail
    loud, matching the campaign posture.
    """
    _ensure_claude_klabauter_on_path()
    from coordinator_core.state_root import coordinator_state_root  # noqa: PLC0415

    return coordinator_state_root()


def _terminal_deployment_states() -> frozenset[str]:
    """DR-084 terminal `deployment_state` selector — the SSOT set.

    Routes through `_ensure_claude_klabauter_on_path()` — the file's one
    path-resolution site — rather than re-deriving or re-inserting the
    claude-klabauter root.
    """
    _ensure_claude_klabauter_on_path()
    from coordinator_core.lifecycle_constants import HANDOFF_TERMINAL_DEPLOYMENT  # noqa: PLC0415

    return HANDOFF_TERMINAL_DEPLOYMENT


def _is_archive_candidate(deployment_state: str, terminal_states: frozenset[str]) -> bool:
    """Pure selector: is this deployment_state an archive candidate?

    Isolated from `main()` so the terminal-set regression can be tested
    without invoking the fleet archival op.
    """
    return deployment_state in terminal_states


def _no_fallback() -> None:
    raise RuntimeError(
        "fleet.archive_completed_handoffs: native seam required (no bash fallback -- big-bang cutover)"
    )


def main(argv: list[str] | None = None) -> int:
    git_repo_root, verdict = resolve_checked_repo_root(explicit_root=None)
    if git_repo_root is None:
        print("sweep-shipped-handoffs.py: not inside a git repo", file=sys.stderr)
        return 2
    if verdict["verdict"] == "MISMATCH":
        # DR-277: this is a READER (no write into resolved root beyond its
        # own archive-completed-handoffs op, gated separately) -- warn and
        # proceed rather than refuse. UNRESOLVED never refuses either (AC4).
        print(verdict["message"], file=sys.stderr)

    try:
        state_root = _resolve_state_root(git_repo_root)
        # Review: code-reviewer — folded into the same try/except as
        # _resolve_state_root() so an import failure on
        # coordinator_core.lifecycle_constants (e.g. a future rename)
        # surfaces via this script's own controlled internal-error path
        # rather than a raw traceback, matching the file's fail-loud-but-
        # clean posture elsewhere.
        terminal_states = _terminal_deployment_states()
    except RuntimeError as exc:
        print(f"sweep-shipped-handoffs.py: cannot resolve per-repo state root: {exc}", file=sys.stderr)
        return 2

    # Review: the Staff Engineer — repo_root MUST be derived from state_root (state_root
    # minus its trailing "/state" segment), matching the retired bash oracle's
    # `repo_root="${_ssh_state_root%/state}"` invariant — never resolved
    # independently via `git rev-parse`. Under the meta-repo central-state
    # redirect (coordinator_state_root() resolves to the state dir under
    # CLAUDE_KLABAUTER_ROOT), git_repo_root
    # and state_root diverge; using git_repo_root here for relativization and
    # for the fleet.archive_completed_handoffs repo_root param would silently
    # break candidate-path relativization (absolute paths passed to the op)
    # AND hand the op a repo_root that disagrees with the state root the
    # candidates were enumerated from -- the exact "already-archived" silent
    # skip the oracle's invariant guards against.
    _state_sep = os.sep + "state"
    if state_root.endswith(_state_sep):
        repo_root = state_root[: -len(_state_sep)]
    else:
        repo_root = state_root

    handoffs_dir = os.path.join(state_root, "handoffs")

    stale_threshold_days = int(os.environ.get("SWEEP_STALE_THRESHOLD_DAYS", "14"))
    stale_threshold_secs = stale_threshold_days * 86400

    archived = 0
    unresolvable = 0
    stale_unresolvable = 0
    escaped = 0
    candidates: list[str] = []

    now_secs = time.time()

    # Two-pass: (1) enumerate + parse frontmatter, collecting every distinct
    # shipped_in SHA that needs a resolvability check; (2) batch-resolve all
    # of them in ONE `git cat-file --batch-check` spawn (C11) rather than one
    # spawn per shipped handoff, then apply the same per-file disposition
    # logic as before against the resolved map.
    scan_results: list[tuple[str, dict[str, str], str]] = []
    shipped_shas: set[str] = set()

    if os.path.isdir(handoffs_dir):
        for name in sorted(os.listdir(handoffs_dir)):
            if not name.endswith(".md"):
                continue
            f = os.path.join(handoffs_dir, name)
            if not os.path.isfile(f):
                # TOCTOU guard — a concurrent /workday-start git mv can vanish
                # the file between enumeration and per-file processing.
                continue

            fields = _parse_frontmatter(f)
            deployment_state = fields.get("deployment_state", "")

            if not _is_archive_candidate(deployment_state, terminal_states):
                continue

            scan_results.append((f, fields, deployment_state))

            if deployment_state == "shipped":
                sha = _strip_quotes(fields.get("shipped_in", ""))
                if sha and sha != "null":
                    shipped_shas.add(sha)

    resolved_shas = _batch_resolve_shipped_shas(shipped_shas, repo_root)

    for f, fields, deployment_state in scan_results:
        if deployment_state == "shipped":
            shipped_in = _strip_quotes(fields.get("shipped_in", ""))
            sha = shipped_in
            if not sha or sha == "null" or not resolved_shas.get(sha, False):
                # Recount-at-apply-time (DR-084 Addendum 2026-07-22(b)):
                # staleness is derived fresh, right here, from THIS
                # file's current on-disk mtime -- never from a count
                # cached earlier in the run -- so the escape decision
                # below always acts on the live state, not a snapshot.
                stale = False
                try:
                    mtime = os.stat(f).st_mtime
                    stale = (now_secs - mtime) >= stale_threshold_secs
                except OSError:
                    pass

                if stale and sha and sha != "null" and _stamp_unresolvable_escape(f, repo_root, sha):
                    # C9/AC15 escape: dead SHA recorded honestly in a
                    # non-discriminant field, shipped_in_kind untouched
                    # -- this handoff now joins the ordinary archive
                    # candidates instead of being retained forever.
                    escaped += 1
                    candidates.append(f)
                    continue

                unresolvable += 1
                if stale:
                    stale_unresolvable += 1
                continue

        candidates.append(f)

    dispatch_failed = False

    if candidates:
        rel_candidates = [
            c[len(repo_root) + 1 :] if c.startswith(repo_root + os.sep) else c
            for c in candidates
        ]
        sweep_params = {"mode": "already-terminal", "dry_run": False, "candidate_ids": rel_candidates}
        try:
            sweep_result = cc_invoke.route(
                "fleet.archive_completed_handoffs", sweep_params, repo_root, _no_fallback
            )
        except RuntimeError as exc:
            print(f"sweep-shipped-handoffs.py: fleet dispatch failed; candidates retained: {exc}", file=sys.stderr)
            dispatch_failed = True
        else:
            acted = sweep_result.get("acted", []) if isinstance(sweep_result, dict) else []
            archived += len(acted) if isinstance(acted, list) else 0
            op_exit = sweep_result.get("exit_code", 0) if isinstance(sweep_result, dict) else 0
            if op_exit == 2:
                print(
                    f"sweep-shipped-handoffs.py: WARN: fleet.archive_completed_handoffs partial "
                    f"(exit_code=2, acted={archived}) -- check claude-klabauter logs",
                    file=sys.stderr,
                )
                dispatch_failed = True

    if archived == 0:
        print("no terminal handoffs archived")
    else:
        print(f"{archived} terminal handoffs archived")

    if unresolvable > 0:
        print(f"{unresolvable} shipped handoffs retained (unresolvable SHA)")

    if stale_unresolvable > 0:
        print(f"WARNING: {stale_unresolvable} shipped handoffs retained -- shipped_in SHA no longer resolves")

    if escaped > 0:
        print(
            f"{escaped} shipped handoffs escaped via unresolvable-shipped_in marker "
            f"(shipped_in_kind unchanged; see shipped_in_unresolvable_sha) -- C9/AC15"
        )

    _stamp_archive_sweeps_liveness(repo_root)
    if dispatch_failed:
        return 1
    return 0


if __name__ == "__main__":
    # DR-276: this script owns its own main() -- it dispatches to the
    # fleet.archive_completed_handoffs op's OWN self-committing contract via
    # cc_invoke.route() (a different op's CLI surface entirely) rather than
    # forwarding argv to a single op's main(argv), so it cannot route through
    # run_op_main. recording_declared_writes() is the sanctioned carve-out for
    # exactly this shape (coordinator_core.cli_entry module docstring), wrapping
    # the region so this file's OWN write (_stamp_unresolvable_escape's
    # locked_rmw stamp) becomes a session scope-touch claim; the SEPARATE
    # fleet.archive_completed_handoffs dispatch already self-commits its own
    # git-mv independently and is unaffected by this wrapper.
    _ensure_claude_klabauter_on_path()
    from coordinator_core.cli_entry import recording_declared_writes

    with recording_declared_writes():
        _exit_code = main()
    sys.exit(_exit_code)
