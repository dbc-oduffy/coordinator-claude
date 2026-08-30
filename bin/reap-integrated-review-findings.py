# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""reap-integrated-review-findings.py — reaps integrated review-findings sidecars.

DR-215 strangler-facade for leg (a) of the review-findings sidecar auto-sweep:
enumerates state/review-trail/findings/*.md, and reaps (via git rm, preserving
history) every sidecar the review-integrator has already marked consumed via
a trailing '## Integrator Dispositions' heading. Routes to the native
coordinator_core fleet.reap_integrated_findings op when the claude-klabauter seam is
present on disk, falling back to the legacy self-contained reap body
otherwise.
"""
# reap-integrated-review-findings.sh — sh/python polyglot trampoline. DR-215
# strangler-facade for leg (a) of the review-findings sidecar auto-sweep: reap
# sidecars that have already served their purpose.
#
# Purpose: reviewer findings sidecars accrete under state/review-trail/findings/*.md
# and are never cleaned up on their own. Once the review-integrator has
# consumed a sidecar, it appends a mandatory `## Integrator Dispositions`
# heading to the END of the file — that heading's presence is the definitive
# "this sidecar was integrated -> served its purpose -> reapable" signal.
# This script enumerates state/review-trail/findings/*.md, reaps (via
# `git rm`, never plain `rm`, so history is preserved) every file carrying
# that heading, and leaves everything else untouched.
#
# DR-215: routes to the native coordinator_core fleet.reap_integrated_findings
# op when the coordinator_core.invoke seam is importable on disk (via
# lib/cc_invoke.py's resolver/seam-probe, reused not re-derived — same pattern
# as coordinator-auto-push/handoff-gate-aging), falling back to the legacy
# reap body (_reap_integrated_legacy) verbatim otherwise. Unlike other fleet
# ops, fleet.reap_integrated_findings does NOT use the cockpit mode/candidate_ids
# envelope — it re-scans state/review-trail/findings/ internally, so the
# params JSON carries {"dry_run": <bool>} plus an optional "subject_prefix"
# key (set to "distill: " when DISTILL_RUN_ID is exported by the /distill
# caller, mirroring the legacy path's commit-subject prefix — DR-215
# path-parity fix).
#
# Usage:
#   reap-integrated-review-findings.sh [--dry-run] [--summary] [--summary-limit N]
#
# --dry-run: list what WOULD be reaped, remove nothing, commit nothing, exit 0.
# --summary: print a count + first-N sample instead of the full per-file
#   listing (legacy path) / raw JSON result blob (native path) — added F8:
#   a real dry-run emitted 64KB of single-line JSON (334 verbose candidate
#   rows), engine-friendly but EM-hostile at a PM gate where only the count
#   and a sample matter.
# --summary-limit N: sample size for --summary (default 10).
# --help / -h: argparse-generated usage text, exit 0 (previously treated as
#   an unknown argument -> exit 2 — F8).
#
# Idempotent: a second run with nothing left to reap is a clean exit 0 with a
# "nothing to reap" line — never an error, never an empty commit.
#
# Safe / fail-loud: resolves the repo root via the checked resolver
# (`lib.repo_identity.resolve_checked_repo_root`, memoized, non-spawning);
# if not inside a git repo, or
# state/review-trail/findings/ does not exist under that root, prints a
# message and exits 0 (nothing to do) rather than erroring or operating
# against the wrong tree.
#
# Exit codes:
#   0 — normal (legacy path: clean run, incl. zero sidecars reaped). Native
#       path: ALWAYS 0 regardless of native outcome (transport failure, or a
#       native op partial exit_code=2) — best-effort, non-blocking, matching
#       prune-closed-bugs.sh's posture; inspect stderr/logs for the native
#       partial detail, the process exit code alone does not carry it.
#   2 — CLI usage error (unknown argument, bad --summary-limit value; all via
#       argparse's own error() -> exit 2). ALSO the legacy path's exit code
#       on a genuine `git commit` failure IF that failure's own exit status
#       happens to be 2 (git's exit codes are not namespaced against this
#       script's) — this overload is inherited unchanged from the pre-port
#       bash oracle (see the AC11 test commentary in
#       bin/tests/test-reap-integrated-review-findings.sh), not a new
#       ambiguity introduced by this port.
#   N — legacy path only: any other nonzero exit status a `git commit`
#       failure (after `git rm` staged deletions) returns, propagated
#       verbatim; a `git rm` failure similarly propagates git's own rc.
#
# Untracked marker-bearing sidecars (never `git add`ed) are removed via plain
# `os.remove` (nothing in git history to preserve); tracked ones go through
# `git rm` + one scoped `git commit`. This split is legacy-path-only — the
# native op (coordinator_core.ops.fleet.reap_integrated_findings, via
# rm_and_commit) implements the equivalent split op-side.
#
# Spec backlinks:
#   leg (a) of review-findings sidecar auto-sweep — reap integrated
#   (## Integrator Dispositions) findings sidecars; PM-directed 2026-07-14
#   docs/plans/2026-07-06-dr215-fleet-ops-ceremony-wiring.md (DR-215: this
#   facade's own DoE-resident sanction)
#   claude-klabauter tree: docs/decisions/DR-218-review-trail-aged-unintegrated-reap-boundary.md
#   (C0-amended entry sanctioning fleet.reap_integrated_findings op-side;
#   lives ONLY in claude-klabauter's docs/decisions/, not in this repo — context
#   for why the underlying native op is allowed to delete, not this facade's
#   own sanction, which is DR-215 above)
#   tasks/2026-07-16-clean-slate-recon/r1-doe-port-template.md (polyglot
#   trampoline template, variant #1 direct-import shape adapted here for a
#   registered/mutating op — see note below on why route()-by-hand rather
#   than a plain direct import)
#
# Negative-spec (deliberate scope drops vs the pre-port bash oracle):
#   - The bash>=4-version guard is dropped — Python has no bash-3.2-class
#     interpreter fragmentation to guard against; this guard existed only to
#     protect bash-4 syntax (arrays, [[ ]]) used later in that script.
#   - The PLUGIN_ROOT / ~/.claude/.doe-root resolution block (and its
#     "exit 0 if unresolvable" gate) is dropped. In the bash oracle this
#     machinery existed SOLELY to compute `_CSR_LIB_DIR` and source
#     coordinator-state-root.sh — a source whose functions the script never
#     actually calls (grepped: zero call sites of any coordinator_state_root
#     function in the pre-port body). It was dead weight: a machine missing
#     ~/.claude/.doe-root would no-op the ENTIRE reap even though the actual
#     reap logic never touched anything PLUGIN_ROOT-derived. This is not a
#     functional regression (nothing observable depended on it; no AC in
#     test-reap-integrated-review-findings.sh exercises this path) — dropping
#     it is confirmed-dead-code removal, not a silent behavior drop.
#   - COORDINATOR_FORCE_LEGACY and the seam-presence check are reimplemented
#     locally (see _reap_seam_present below) rather than via
#     lib/cc_invoke.py's route() directly, because route() does not support
#     COORDINATOR_FORCE_LEGACY (a testing/parity lever the bash
#     strangler-facade.sh DOES support and this script's own test harness
#     relies on for every AC). cc_invoke.py is a shared lib used by other
#     landed trampolines (coordinator-auto-push, handoff-gate-aging) and is
#     out of this port's file scope — reused (resolve_engine_root,
#     _seam_present), not modified, not re-derived. resolve_engine_root adds
#     a self-location rung ahead of the pointer-file/registry ladder (Review:
#     code-reviewer — comment previously undersold this as a bare rename from
#     _resolve_claude_klabauter_root; the rung order changed too), but the site here is
#     still wrapped by `except RuntimeError`, so bash-oracle failure-mode
#     parity is unaffected.
#
# Review: code-reviewer — Finding 6 (pre-port bash oracle): DR-218 is a
# claude-klabauter-tree citation, not a DoE-relative path; qualified above per
# cross-repo-citation-conventions.md.
# Portability (DR-148): pure Python + subprocess git calls; no shell-only
# constructs. sys.executable used for the CC_INVOKE spawn (via cc_invoke.py),
# never a hardcoded "python3". CREATE_NO_WINDOW applied to every subprocess.run.

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

_PROG = "reap-integrated-review-findings.sh"

_BOOTSTRAP_NAMES = (
    "cc_invoke",
    "coordinator_engine_root_env",
    "no_console_creationflags",
    "resolve_checked_repo_root",
)


def __getattr__(name: str):
    """PEP 562 module `__getattr__` -- lets a caller that reaches for one of
    the bootstrap-deferred names (e.g. this file's own test suite, which
    monkeypatches `_mod.cc_invoke` ahead of calling `_mod.main()`) trigger
    `_bootstrap_imports()` lazily on first access, instead of requiring the
    name to already be a module global at import time. Only fires when the
    name is NOT already present in this module's `__dict__` -- once
    `_bootstrap_imports()` has run once (via this hook or via `main()`), the
    plain global wins on every later lookup and this function is not called
    again for that name.

    NEGATIVE SPEC -- the bootstrap guard checks ALL of `_BOOTSTRAP_NAMES`,
    not a single sentinel: `mock.patch.object` reading one name through this
    hook and `delattr`ing it on exit (rather than restoring it) is exactly
    the case the all-names guard covers -- a name absent from `__dict__`
    means `_bootstrap_imports()` re-runs. The re-run publishes each
    freshly-imported name via `globals().setdefault(...)`, so it rebinds
    exactly what is missing and leaves any OTHER already-present
    bootstrapped name (e.g. one a test patched) untouched. No pop/restore
    snapshot is needed because a partially-bound state is never mistaken
    for a fully-bound one."""
    if name in _BOOTSTRAP_NAMES:
        _bootstrap_imports()
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r}"
            ) from None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _bootstrap_imports() -> None:
    """Import every non-stdlib dependency this module needs and bind it at
    module scope, called from main() (C6k import-motion: module bodies stay
    inert on both the warm door and the un-bootstrapped settings-home
    forwarder load routes). Order is load-bearing — preserved verbatim from
    the former module-scope sequence. Idempotent by construction (see the
    `__getattr__` hook above, which may trigger this ahead of `main()`).
    """
    if all(n in globals() for n in _BOOTSTRAP_NAMES):
        return

    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke as _cc_invoke

    _cc_invoke.ensure_engine_on_path(__file__)

    from coordinator_core.engine_root import (
        coordinator_engine_root_env as _coordinator_engine_root_env,
    )
    from coordinator_core.win_portability import (
        no_console_creationflags as _no_console_creationflags,
    )
    from repo_identity import resolve_checked_repo_root as _rccr

    for _name, _value in (
        ("cc_invoke", _cc_invoke),
        ("coordinator_engine_root_env", _coordinator_engine_root_env),
        ("no_console_creationflags", _no_console_creationflags),
        ("resolve_checked_repo_root", _rccr),
    ):
        globals().setdefault(_name, _value)

# --summary sample size (F8 — a 64KB single-line JSON dump of 334 verbose
# candidate rows is engine-friendly but EM-hostile at a PM dry-run gate,
# where only the count and a sample matter). --summary-limit overrides it.
_DEFAULT_SUMMARY_LIMIT = 10

# Anchored heading match — "## Integrated Dispositions" as its own line, not a
# substring match anywhere in the body (mirrors the bash oracle's
# `grep -qE '^## Integrator Dispositions[[:space:]]*$'` exactly, including its
# accepted false-positive limitation on a flush-left fenced quote of the
# heading — see the native op's own negative-spec for the shared rationale).
_MARKER_RE = re.compile(r"^## Integrator Dispositions[ \t]*$", re.MULTILINE)

_GIT_TIMEOUT_SECS = 30


def _git(args: List[str], cwd: Optional[str] = None) -> "subprocess.CompletedProcess[str]":
    """Run a git subcommand with a bounded timeout and no stdin inheritance.

    Addendum rule 2: every subprocess.run over external/looping input carries
    timeout= and stdin=DEVNULL (git commit can otherwise wait on an editor or
    a hook prompting for input).
    """
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT_SECS,
        stdin=subprocess.DEVNULL,
        **no_console_creationflags(),
    )


# ---------------------------------------------------------------------------
# --summary shaping (F8) — caps the number of per-file lines printed to a
# sample, with a trailing "... and N more" elision line. summary=False (the
# default, and every pre-existing call site) prints every line, matching
# behavior byte-for-byte with the pre-F8 output.
# ---------------------------------------------------------------------------


class _SummaryPrinter:
    def __init__(self, summary: bool, limit: int) -> None:
        self._summary = summary
        self._limit = max(1, limit)
        self._shown = 0
        self._total = 0

    def emit(self, line: str) -> None:
        self._total += 1
        if not self._summary or self._shown < self._limit:
            print(line)
            self._shown += 1

    def elided(self) -> int:
        return max(0, self._total - self._shown)

    def print_elision_note(self) -> None:
        n = self.elided()
        if n:
            print(f"{_PROG}: ... and {n} more (omitted by --summary)")


# ---------------------------------------------------------------------------
# Legacy path — original self-contained reap body (pre-DR-215 bash logic,
# ported), preserved semantically as the fallback for State 1
# (coordinator_core.invoke seam absent on disk, or COORDINATOR_FORCE_LEGACY=1).
# ---------------------------------------------------------------------------


def _reap_integrated_legacy(
    dry_run: bool,
    commit_prefix: str,
    *,
    summary: bool = False,
    summary_limit: int = _DEFAULT_SUMMARY_LIMIT,
) -> int:
    _bootstrap_imports()
    # -------------------------------------------------------------------
    # Repo root / findings dir resolution — cwd-scope guard: only operate
    # on the repo that actually contains state/review-trail/findings/. Not-
    # a-git-repo and no-findings-dir are both "nothing to do" (exit 0), not
    # errors.
    # -------------------------------------------------------------------
    repo_root, verdict = resolve_checked_repo_root(explicit_root=None)
    if not repo_root:
        print(f"{_PROG}: not inside a git repo; nothing to do")
        return 0
    if verdict["verdict"] == "MISMATCH":
        # DR-277: this is a READER (no write into resolved root) -- warn
        # and proceed. UNRESOLVED never refuses either (AC4).
        print(verdict["message"], file=sys.stderr)

    findings_dir = Path(repo_root) / "state" / "review-trail" / "findings"
    if not findings_dir.is_dir():
        print(f"{_PROG}: {findings_dir} does not exist; nothing to do")
        return 0

    # -------------------------------------------------------------------
    # Enumerate + classify. Sorted for deterministic output across
    # platforms — bash's own glob order was never guaranteed either;
    # sorting is a stability improvement, not an observable behavior
    # change any AC depends on.
    # -------------------------------------------------------------------
    to_reap: List[Path] = []
    for f in sorted(findings_dir.glob("*.md")):
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _MARKER_RE.search(text):
            to_reap.append(f)

    if not to_reap:
        print("nothing to reap")
        return 0

    # -------------------------------------------------------------------
    # A marker-bearing sidecar that was never `git add`ed (findings self-
    # persist via Edit; commit timing is a separate EM-side step) makes
    # `git rm` fail. Split into tracked (reap via `git rm`, history-
    # preserving) vs untracked (already served their purpose, nothing in
    # history to preserve -> plain remove).
    # -------------------------------------------------------------------
    # Batched tracked/untracked split: one `git ls-files -z --` call over the
    # whole `to_reap` set instead of one `--error-unmatch` spawn per file.
    # `git ls-files` (no --error-unmatch) prints only the pathspecs that ARE
    # tracked; anything requested but absent from that output is untracked —
    # the same classification, one spawn instead of N.
    rel_paths = [os.path.relpath(str(f), repo_root) for f in to_reap]
    ls = _git(["ls-files", "-z", "--", *rel_paths], cwd=repo_root)
    # git always emits forward-slash paths regardless of platform; normalize
    # our own relpaths (backslash on Windows) the same way before comparing.
    tracked_rels = {p for p in ls.stdout.split("\0") if p}
    tracked_to_reap: List[Path] = []
    untracked_to_reap: List[Path] = []
    for f, rel in zip(to_reap, rel_paths):
        if rel.replace(os.sep, "/") in tracked_rels:
            tracked_to_reap.append(f)
        else:
            untracked_to_reap.append(f)

    if dry_run:
        printer = _SummaryPrinter(summary, summary_limit)
        for f in tracked_to_reap:
            printer.emit(f"{_PROG}: [dry-run] would reap {f}")
        for f in untracked_to_reap:
            printer.emit(f"{_PROG}: [dry-run] would reap {f} (untracked; plain rm, no history to preserve)")
        printer.print_elision_note()
        print(f"{len(to_reap)} integrated review-findings sidecars would be reaped (dry-run)")
        return 0

    # -------------------------------------------------------------------
    # Reap untracked marker-bearing sidecars first (plain remove — nothing
    # in git history to preserve; these never made it into a commit).
    # -------------------------------------------------------------------
    printer = _SummaryPrinter(summary, summary_limit)
    for f in untracked_to_reap:
        try:
            os.remove(f)
        except OSError:
            pass
        printer.emit(f"reaped {f} (untracked, plain rm)")

    if not tracked_to_reap:
        printer.print_elision_note()
        print(f"{len(to_reap)} integrated review-findings sidecars reaped")
        return 0

    # -------------------------------------------------------------------
    # Reap: git rm (preserves history) + ONE scoped commit of exactly the
    # reaped paths. Never a blanket add — explicit pathspecs only.
    #
    # `git rm` and `git commit` are two separate steps. If `git rm` stages
    # the deletions but `git commit` then fails (hook rejection, gpgsign
    # failure, disk full, etc.), the repo is left with staged-but-
    # uncommitted deletions on a shared branch (concurrent-EM hazard).
    # Leave-in-place and report loudly (not auto-revert) on that failure
    # path, with a diagnostic distinct from git's raw stderr so a sibling
    # session isn't left silently tripping over half-applied state.
    # -------------------------------------------------------------------
    tracked_rel = [os.path.relpath(str(f), repo_root) for f in tracked_to_reap]

    rm_res = _git(["rm", "-q", "--", *tracked_rel], cwd=repo_root)
    if rm_res.returncode != 0:
        sys.stderr.write(rm_res.stderr)
        return rm_res.returncode

    for f in tracked_to_reap:
        printer.emit(f"reaped {f}")
    printer.print_elision_note()

    count = len(to_reap)
    tracked_count = len(tracked_to_reap)
    commit_msg = f"{commit_prefix}reap {tracked_count} integrated review-findings sidecars"
    commit_res = _git(["commit", "-q", "-m", commit_msg, "--", *tracked_rel], cwd=repo_root)

    if commit_res.returncode == 0:
        print(f"{count} integrated review-findings sidecars reaped")
        return 0

    rc = commit_res.returncode
    lines = [
        f"{_PROG}: git commit failed after git rm — {tracked_count} sidecar(s) staged for deletion, not committed:",
    ]
    for f in tracked_to_reap:
        lines.append(f"{_PROG}:   {f}")
    lines.append(
        f"{_PROG}: reap partially applied; inspect with 'git status' / 'git diff --cached' and "
        "either commit or 'git reset -- <paths>' to undo staging"
    )
    sys.stderr.write("\n".join(lines) + "\n")
    return rc


# ---------------------------------------------------------------------------
# DR-215 seam-presence decision — reuses lib/cc_invoke.py's resolver + seam
# probe (not re-derived), but layers COORDINATOR_FORCE_LEGACY on top since
# cc_invoke.route() does not support that testing/parity lever (see
# negative-spec above). Mirrors strangler-facade.sh's strangle_route gate
# exactly, including the FORCE_LEGACY opt-in bypass.
# ---------------------------------------------------------------------------


def _reap_seam_present() -> Tuple[bool, str]:
    """Returns (seam_present, claude_klabauter_root). claude_klabauter_root is '' if unresolvable.

    Two resolvers answer "which engine" on this path and they do NOT agree on
    one input: an engine-root env var that is SET but names no valid checkout.
    ``resolve_engine_root``'s rung 1 is isdir-gated, so it steps over the bad
    value and returns self-location's answer; the transport's own resolution
    inside ``cc_invoke.cc_invoke`` treats an explicit override as binding and
    fails loud on it. Judging seam presence by the first and then dispatching
    through the second turns a misconfigured override into a transport error
    on a best-effort path — which this script reports as a WARN and a skip, so
    nothing gets reaped at all and the legacy body never runs.

    Screen for that disagreement here: an override the transport will refuse
    means the native seam is not usable, whichever tree happens to sit around
    this script. Legacy reaps the same sidecars, so routing there is strictly
    better than skipping. This is the check the reserved ``_claude_klabauter_root=``
    kwarg used to make unnecessary by pinning the transport to THIS resolver's
    answer (dropped by C16/C28 --
    docs/plans/2026-08-20-a-refusal-cannot-exit-zero.md).

    C23: the override check reads through the C10/C14 accessor instead of the
    two engine-root env var names directly -- the retired ``CLAUDE_KLABAUTER_ROOT`` no
    longer answers there (C14 closed the dual-read window), so a second,
    separate check of it here would only ever screen a value the transport's
    own resolution (``cc_invoke``'s rung 1) already ignores.
    """
    _bootstrap_imports()
    if os.environ.get("COORDINATOR_FORCE_LEGACY", "") == "1":
        return False, ""
    _override = coordinator_engine_root_env(__name__) or ""
    if _override and not cc_invoke._seam_present(_override):
        return False, ""
    try:
        claude_klabauter_root = cc_invoke.resolve_engine_root(__file__)
    except RuntimeError:
        return False, ""
    if not cc_invoke._seam_present(claude_klabauter_root):
        return False, ""
    return True, claude_klabauter_root


# ---------------------------------------------------------------------------
# Native fleet dispatch — builds params, calls cc_invoke() directly (seam
# already confirmed present by _reap_seam_present above), and best-effort
# logs a summary. TWO-SIGNAL contract preserved from the bash oracle:
#   (1) A transport failure (cc_invoke() raises RuntimeError) is caught here
#       and squashed to exit 0 (best-effort, non-blocking — matches
#       prune-closed-bugs.sh's posture; never silently routes back to
#       legacy after the native path was attempted, per DR-215 anti-scope).
#   (2) On success, the bare result dict's top-level .exit_code carries the
#       op verdict (0 clean, 1 setup-error, 2 determinate-partial with
#       .reaped/.failed detail) — logged, not hard-propagated.
# Parses TOP-LEVEL keys only (.exit_code, .candidates[], .reaped[],
# .failed[]) — never nested under a .result wrapper (cc_invoke() already
# strips that envelope).
# ---------------------------------------------------------------------------


def _print_native_summary_sample(result: dict, dry_run: bool, summary_limit: int) -> None:
    """--summary mode: print a capped per-item sample instead of the raw JSON
    blob (F8). Reads whichever list the op actually returned — if the op
    itself already truncated the list server-side (params.summary_limit was
    honored), this only re-caps client-side as a no-op safety net."""
    if dry_run:
        items = result.get("candidates", []) or []
        total = result.get("candidates_total", len(items))
        label = "candidate"
    else:
        items = result.get("reaped", []) or []
        total = result.get("reaped_total", len(items))
        label = "reaped"

    sample = items[:summary_limit]
    for item in sample:
        ident = item.get("id", item) if isinstance(item, dict) else item
        print(f"{_PROG}: [summary] {label}: {ident}")

    elided = total - len(sample)
    if elided > 0:
        print(f"{_PROG}: ... and {elided} more {label}(s) (omitted by --summary)")


def _reap_native(
    dry_run: bool,
    commit_prefix: str,
    *,
    summary: bool = False,
    summary_limit: int = _DEFAULT_SUMMARY_LIMIT,
) -> int:
    _bootstrap_imports()
    # No `claude_klabauter_root` parameter: C28 dropped the reserved `_claude_klabauter_root=` kwarg from
    # the cc_invoke call below, which was its only reader, and a parameter nothing
    # reads is a standing invitation to re-wire the transport through it. The engine
    # this dispatches to is resolved by cc_invoke itself; `_reap_seam_present` still
    # resolves a root of its own, for the seam-presence question only.
    params: dict = {"dry_run": dry_run}
    if commit_prefix:
        params["subject_prefix"] = commit_prefix
    if summary:
        params["summary_limit"] = summary_limit

    repo_root, verdict = resolve_checked_repo_root(explicit_root=None)
    if not repo_root:
        print(
            f"{_PROG}: WARN: fleet.reap_integrated_findings transport error "
            "(cannot resolve git repo root) — skipping (non-blocking)",
            file=sys.stderr,
        )
        return 0
    if verdict["verdict"] == "MISMATCH":
        # DR-277: this is a READER (no write into resolved root) -- warn
        # and proceed. UNRESOLVED never refuses either (AC4).
        print(verdict["message"], file=sys.stderr)

    try:
        result = cc_invoke.cc_invoke("fleet.reap_integrated_findings", params, repo_root)
    except RuntimeError as exc:
        print(
            f"{_PROG}: WARN: fleet.reap_integrated_findings transport error ({exc}) — "
            "skipping (non-blocking)",
            file=sys.stderr,
        )
        return 0

    if not isinstance(result, dict):
        print(
            f"{_PROG}: WARN: fleet.reap_integrated_findings malformed result: not a dict ({result!r}) — "
            "skipping (non-blocking)",
            file=sys.stderr,
        )
        return 0

    # Captured native result is re-emitted verbatim so callers (including
    # this script's own test harness) see it, matching the bash oracle's
    # `printf '%s\n' "$_reap_result"` passthrough — suppressed under
    # --summary (F8: a full JSON dump is exactly the EM-hostile output
    # --summary exists to replace).
    if summary:
        _print_native_summary_sample(result, dry_run, summary_limit)
    else:
        print(json.dumps(result, separators=(",", ":")))

    op_exit = result.get("exit_code", "?")

    if dry_run:
        candidate_count = result.get("candidates_total", len(result.get("candidates", []) or []))
        print(
            f"{_PROG}: fleet.reap_integrated_findings: {candidate_count} integrated "
            "review-findings sidecar(s) would be reaped (dry-run)"
        )
        return 0

    reaped_count = result.get("reaped_total", len(result.get("reaped", []) or []))
    failed_count = result.get("failed_total", len(result.get("failed", []) or []))

    if op_exit == 0:
        print(f"{_PROG}: fleet.reap_integrated_findings completed — {reaped_count} sidecar(s) reaped")
    elif op_exit == 2:
        print(
            f"{_PROG}: WARN: fleet.reap_integrated_findings partial (exit_code=2, "
            f"reaped={reaped_count}, failed={failed_count}) — check claude-klabauter logs",
            file=sys.stderr,
        )
    else:
        print(f"{_PROG}: fleet.reap_integrated_findings exit_code={op_exit} (reaped={reaped_count})")

    return 0


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=_PROG,
        description=(
            "Reap integrated ('## Integrator Dispositions' marker-bearing) "
            "review-findings sidecars from state/review-trail/findings/."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="list what would be reaped; remove and commit nothing",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help=(
            "print a count + first-N sample instead of the full per-file "
            f"listing / raw JSON blob (default N: {_DEFAULT_SUMMARY_LIMIT}, "
            "see --summary-limit)"
        ),
    )
    parser.add_argument(
        "--summary-limit",
        type=int,
        default=_DEFAULT_SUMMARY_LIMIT,
        metavar="N",
        help=f"sample size for --summary (default: {_DEFAULT_SUMMARY_LIMIT})",
    )
    return parser


def main(argv: List[str]) -> int:
    _bootstrap_imports()
    parser = _build_arg_parser()
    # argparse handles --help itself (prints usage, exits 0) and unknown
    # arguments (prints an error, exits 2) — both were F8 gaps in the
    # hand-rolled arg loop this replaces.
    args = parser.parse_args(argv)

    if args.summary_limit < 1:
        parser.error("--summary-limit must be a positive integer")

    dry_run: bool = args.dry_run
    summary: bool = args.summary
    summary_limit: int = args.summary_limit

    commit_prefix = "distill: " if os.environ.get("DISTILL_RUN_ID") else ""

    seam_present, claude_klabauter_root = _reap_seam_present()

    if not seam_present:
        # State 1 — legacy path. rc IS the reap's real business-logic exit
        # status (0 normal, nonzero on a genuine git-commit/git-rm failure).
        # Propagate verbatim; do not squash to 0.
        return _reap_integrated_legacy(
            dry_run, commit_prefix, summary=summary, summary_limit=summary_limit
        )

    return _reap_native(
        dry_run, commit_prefix, summary=summary, summary_limit=summary_limit
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
