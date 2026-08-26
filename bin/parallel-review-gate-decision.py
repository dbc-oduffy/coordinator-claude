# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""parallel-review-gate-decision.py — gate-decision assembler for the weekly
parallel-code-review gate (DoE-claude coordinator/skills/parallel-code-review/
SKILL.md).

Spec backlink: DoE-claude:pln-computed-skills-b8-review-ci-c-ffa5ad
chunk C3 ("Extract parallel-code-review's gating Rules 1-4 (mechanical) +
chunking algorithm into a gate-decision assembler; surface Rule 5's inputs
without deciding it") and chunk C3b ("Upgrade C3's gate-decision assembler
from plain JSON to the 8-key envelope").

Ports three mechanical pieces the skill currently narrates as reader-
performed `grep -E` / `git diff --shortstat` comparisons and a reader-
resolved branch table, into one naked-Python, self-locating, read-only CLI:

  (a) Gating Rules 1-4 (SKILL.md § Gating Rules, L59-67) — the mechanical
      skip/bypass predicates: Rule 1 (skip-all-tiny-or-internal), Rule 2
      (skip-code-semantics-on-doc-only), Rule 3 (skip-entire-gate-on-plan-
      only), Rule 4 (the `--force` escape). **Rule 5 (narrow-or-skip-on-
      already-reviewed-span, L69-73) is explicitly EM-judgment, not a
      mechanical predicate — this tool never decides it.** The `rule5-inputs`
      subcommand MAY compute and surface Rule 5's INPUTS (unreviewed SHA
      set, seam SHA set, commit/seam-file counts) as informational data; the
      skip-vs-narrow call stays skill-resident per DR-090.
  (b) The seam-nuclei / overflow / fill / disjoint-by-file-scope chunking
      algorithm (SKILL.md § Chunking, L128-149), including TSV chunk-
      manifest emission (previously a fenced command block the reader typed
      by hand).
  (c) The `$RESOLVER_EXIT` reader-resolved branch table (SKILL.md L118) for
      the full-suite-vs-fast-fallback-vs-skip test-command decision.

Read-only / no mutation. Every subcommand's stdout is now the canonical
8-key decision-object envelope (`build_envelope`/`emit` from
`coordinator_core.contract.decision_object` — imported, never re-derived
per the pickup_assemble CONSUME-DON'T-RE-DERIVE hazard, see C3b's chunk
body). Rules 1-4 and the chunking/resolver-branch outputs are fully
mechanical and auto-fired, so they land in the envelope's `decisions`/
`gates` fields with an empty `judgment_points[]`; Rule 5 is EM-judgment
(never auto-decided by this tool) and is the one surface that emits a real
`judgment_points[]` entry via `build_untrusted_gate_judgment_point` — no
`recommendation` parameter exists on that constructor, so it is
structurally impossible for this assembler to smuggle a skip-vs-narrow
verdict into its output (DR-090's judgment-residue line).

Subcommands:
  gate --range <RANGE> [--repo-root PATH] [--force]
      Computes Rules 1-4 over `git diff <RANGE> --shortstat` / `--name-only`.
      Prints the 8-key envelope: `gates` = {"rule", "action"},
      `decisions` = {"gate": {"rule", "action", "reason", "changed_lines",
      "changed_files"}}, `narration` = the rule's reason string,
      `next_move` = the action-derived next step. `judgment_points` is
      always `[]` (Rules 1-4 are mechanical, never paused for judgment).
      Exits 0 always (a computed decision is not a tool failure) — the
      caller branches on `decisions.gate.action`, never on exit code.

  rule5-inputs --scope-shas-file PATH --seam-files-file PATH
               --review-trail-dir PATH [--repo-root PATH]
      Computes Rule 5's INPUTS only (never the skip-vs-narrow decision):
      unreviewed_set (scope SHAs with no `state/review-trail/*.json` record),
      seam_shas (scope SHAs touching a file listed in --seam-files-file),
      commit_count, seam_file_count, and per-workstream review-trail
      coverage (workstream id -> bool covered, read from each trail record's
      `workstream` field when present). Prints the 8-key envelope with the
      inputs under `preflight.rule5_inputs` and exactly one
      `build_untrusted_gate_judgment_point` entry
      (`id="jp_rule5_skip_vs_narrow"`, dispositions `narrow`/`skip`, no
      `recommendation` — the constructor has no such parameter) in
      `judgment_points`; the skill body still makes the skip-vs-narrow call.

  chunk --scope-files-file PATH --seam-manifest-file PATH
        [--target-size N] [--out PATH]
      Seam-nuclei/overflow/fill/disjoint chunking (SKILL.md § Chunking).
      --seam-manifest-file is a TSV of `<file>\\t<session_id>` rows — a file
      with >=2 distinct session_id rows is a seam nucleus; a file sharing a
      session_id with a seam file is co-touching context for its nucleus.
      --scope-files-file is a newline list of the full narrowed code-
      semantics scope (staff_eng SHA set's touched files UNION
      staff_eng_seam_files). Prints the 8-key envelope with
      `decisions.chunk` = {"chunks": {"chunk-1": [...], ...}, "chunk_count":
      N, "seam_nucleus_count": N} and, when --out is given, also writes the
      TSV manifest (`chunk-<k>\\t<relpath>` per line, disjoint by
      construction) to that path.

  resolver-branch --resolver-exit {0,2,3} [--test-cmd STR]
      Replaces the `$RESOLVER_EXIT` reader-resolved branch table (L118).
      Prints the 8-key envelope with `decisions.resolver_branch` =
      {"action": "run_full"|"run_fast_fallback"|"skip", "test_cmd":
      <str-or-null>, "note": <str>}. Exit 0 on a recognized code, 1 on an
      unrecognized one (a tool-usage failure, unlike `gate` — no envelope
      is printed on that path).

Negative-spec:
    - Does NOT re-derive `build_envelope`/`emit`/`build_judgment_point`/
      `build_untrusted_gate_judgment_point` — imported from the shipped
      canonical `coordinator_core.contract.decision_object` package, never
      copied per pickup_assemble's divergent (positional-arg,
      `revalidate_at_dispatch=False`-default) re-derived constructors.
    - Does NOT decide Rule 5's skip-vs-narrow call — `rule5-inputs` surfaces
      data + an un-recommended judgment point only; the constructor used
      (`build_untrusted_gate_judgment_point`) structurally has no
      `recommendation` parameter, so a decision cannot be smuggled in (see
      AC-5 of the C3 plan chunk / DR-090).
    - `gate`/`chunk`/`resolver-branch` use `build_judgment_point`'s sibling
      shape (a `decisions` entry, not a judgment point) because Rules 1-4
      and the chunking/resolver-branch table are fully mechanical and
      auto-fired — no open question is being surfaced there, so an empty
      `judgment_points: []` is correct, not an omission.
    - `chunk`'s nucleus/co-touching grouping is FILE-level (via the seam
      manifest's session_id rows), not hunk-level — the skill's stricter
      "minimal both-sides hunk context stays whole" guarantee is honored at
      file granularity here; a future hunk-aware pass is a separate chunk,
      not silently assumed by this tool.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

_BIN_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BIN_DIR.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_LIB_DIR = str(_BIN_DIR / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from coordinator_core.contract.decision_object import (  # noqa: E402
    build_envelope,
    build_untrusted_gate_judgment_point,
    emit,
)
from coordinator_core.contract.decision_object.judgment import build_disposition  # noqa: E402
from coordinator_core.win_portability import no_console_creationflags  # noqa: E402
from raw_cmdline_recovery import UnsoundRawCmdlineTransport, recover_windows_argv  # noqa: E402

#: The .cmd launcher's own basename — used by `recover_windows_argv` to locate
#: where this invocation's own arguments begin within the raw `%CMDCMDLINE%`
#: capture. `gate --range` takes a git rev/range typed directly at the CLI
#: (e.g. the `sha^..sha` predecessor-range shape), which cmd.exe's `%*`
#: batch-parameter population silently strips a literal `^` from — see
#: `coordinator/bin/lib/raw_cmdline_recovery.py`'s module docstring. Refuses
#: on an unvouchable capture (coordinator-write-review-trail.py's C2
#: posture — this is a low-traffic weekly-gate CLI, not scoped-git-commit's
#: ~40-concurrent-session hot path).
_LAUNCHER_CMD_NAME = "parallel-review-gate-decision.cmd"

# build_judgment_point is intentionally NOT imported: every judgment point
# this assembler emits is untrusted-gate-shaped (Rule 5's skip-vs-narrow
# call is EM-judgment, never this tool's recommendation) — see the module
# negative-spec. Importing the trusted-recommendation constructor with no
# call site would be dead weight, not conformance.

GENERATES = []  # read-only gate-decision assembler; every subcommand only prints an envelope to stdout (emit()/print()), no file writes anywhere in this module

_PROG = "parallel-review-gate-decision.py"
_GIT_TIMEOUT_SECS = 60

_INTERNAL_ONLY_RE = r"^(tasks/|tmp/|archive/|\.claude/scheduled_tasks)"
_DOC_RE = r"\.(md|rst|txt)$"
_CODE_RE = r"\.(py|js|ts|sh|c|cpp|h|hpp|rs|go|java|cs)$"
_PLAN_ONLY_RE = r"^docs/plans/"


def _run_git(args: list[str], repo_root: Path | None = None, timeout: int = _GIT_TIMEOUT_SECS):
    argv = ["git"]
    if repo_root is not None:
        argv += ["-C", str(repo_root)]
    argv += args
    try:
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            **no_console_creationflags(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"{_PROG}: failed to run `git {' '.join(args)}`: {exc}", file=sys.stderr)
        return None


def _resolve_repo_root(explicit: str) -> Path | None:
    if explicit:
        return Path(explicit)
    proc = _run_git(["-C", os.getcwd(), "rev-parse", "--show-toplevel"], repo_root=None, timeout=10)
    if proc is None or proc.returncode != 0 or not proc.stdout.strip():
        print(f"{_PROG}: cannot resolve git repo root from {os.getcwd()}", file=sys.stderr)
        return None
    return Path(proc.stdout.strip())


def _matches(path: str, pattern: str) -> bool:
    import re

    return re.search(pattern, path) is not None


def compute_gate_decision(changed_files: list[str], changed_lines: int, force: bool) -> dict:
    """Pure function over already-computed git output — the seam this tool's
    tests exercise directly, independent of a real git checkout."""
    if force:
        return {
            "rule": "4",
            "action": "bypass",
            "reason": "Code-review gate: BYPASSED via --force.",
            "changed_lines": changed_lines,
            "changed_files": changed_files,
        }

    all_internal_or_tiny = changed_lines < 10 or (
        bool(changed_files) and all(_matches(f, _INTERNAL_ONLY_RE) for f in changed_files)
    )
    if all_internal_or_tiny:
        return {
            "rule": "1",
            "action": "skip_gate",
            "reason": "Code-review gate: SKIPPED (rule 1 — diff <10 lines or internal-only paths).",
            "changed_lines": changed_lines,
            "changed_files": changed_files,
        }

    if changed_files and all(_matches(f, _PLAN_ONLY_RE) for f in changed_files):
        return {
            "rule": "3",
            "action": "skip_gate",
            "reason": "Code-review gate: SKIPPED (rule 3 — plan-only diff; staff-eng review on plans goes through /review).",
            "changed_lines": changed_lines,
            "changed_files": changed_files,
        }

    if changed_files and all(_matches(f, _DOC_RE) for f in changed_files) and not any(
        _matches(f, _CODE_RE) for f in changed_files
    ):
        return {
            "rule": "2",
            "action": "skip_code_semantics",
            "reason": "doc-only diff — SKIP_CODE_SEMANTICS=1, run the 3 mechanical specialist workers only.",
            "changed_lines": changed_lines,
            "changed_files": changed_files,
        }

    return {
        "rule": "default",
        "action": "run_default",
        "reason": "N code-semantics chunks + 3 specialists run.",
        "changed_lines": changed_lines,
        "changed_files": changed_files,
    }


def _cmd_gate(args: argparse.Namespace) -> int:
    if not args.range_:
        print(f"{_PROG}: --range is required", file=sys.stderr)
        return 1
    repo_root = _resolve_repo_root(args.repo_root)
    if repo_root is None:
        return 1

    shortstat = _run_git(["diff", "--shortstat", args.range_], repo_root=repo_root)
    if shortstat is None or shortstat.returncode != 0:
        print(f"{_PROG}: git diff --shortstat failed: {shortstat.stderr if shortstat else ''}", file=sys.stderr)
        return 1
    changed_lines = 0
    for token in shortstat.stdout.split(","):
        token = token.strip()
        if "insertion" in token or "deletion" in token:
            digits = "".join(c for c in token if c.isdigit())
            if digits:
                changed_lines += int(digits)

    name_only = _run_git(["diff", "--name-only", args.range_], repo_root=repo_root)
    if name_only is None or name_only.returncode != 0:
        print(f"{_PROG}: git diff --name-only failed: {name_only.stderr if name_only else ''}", file=sys.stderr)
        return 1
    changed_files = [line for line in name_only.stdout.splitlines() if line.strip()]

    decision = compute_gate_decision(changed_files, changed_lines, bool(args.force))
    envelope = build_envelope(
        artifact={"kind": "skill-step", "name": "parallel-review-gate-decision.gate"},
        gates={"rule": decision["rule"], "action": decision["action"]},
        decisions={"gate": decision},
        narration=decision["reason"],
        next_move=_gate_next_move(decision["action"]),
    )
    emit(envelope)
    print(json.dumps(envelope))
    return 0


def _gate_next_move(action: str) -> str:
    return {
        "skip_gate": "skip the code-review gate entirely",
        "skip_code_semantics": "SKIP_CODE_SEMANTICS=1; run the 3 mechanical specialists only",
        "bypass": "gate bypassed via --force; proceed without gating",
        "run_default": "run the N code-semantics chunks + 3 specialists",
    }.get(action, "proceed per decisions.gate.action")


def compute_rule5_inputs(
    scope_shas: list[str],
    seam_files: list[str],
    trail_records: list[dict],
) -> dict:
    reviewed_shas = set()
    workstream_coverage: dict[str, bool] = {}
    for rec in trail_records:
        sha = rec.get("sha") or rec.get("head_sha")
        if sha:
            reviewed_shas.add(sha)
        ws = rec.get("workstream")
        if ws:
            workstream_coverage[ws] = True

    unreviewed_set = [s for s in scope_shas if s not in reviewed_shas]
    return {
        "unreviewed_set": unreviewed_set,
        "unreviewed_count": len(unreviewed_set),
        "commit_count": len(scope_shas),
        "seam_file_count": len(seam_files),
        "workstream_coverage": workstream_coverage,
    }


def _cmd_rule5_inputs(args: argparse.Namespace) -> int:
    scope_shas_path = Path(args.scope_shas_file)
    seam_files_path = Path(args.seam_files_file)
    trail_dir = Path(args.review_trail_dir)
    if not scope_shas_path.is_file():
        print(f"{_PROG}: --scope-shas-file not found: {scope_shas_path}", file=sys.stderr)
        return 1
    if not seam_files_path.is_file():
        print(f"{_PROG}: --seam-files-file not found: {seam_files_path}", file=sys.stderr)
        return 1

    scope_shas = [ln.strip() for ln in scope_shas_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    seam_files = [ln.strip() for ln in seam_files_path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    trail_records: list[dict] = []
    if trail_dir.is_dir():
        for p in sorted(trail_dir.glob("*.json")):
            try:
                trail_records.append(json.loads(p.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue

    result = compute_rule5_inputs(scope_shas, seam_files, trail_records)
    judgment_point = build_untrusted_gate_judgment_point(
        id="jp_rule5_skip_vs_narrow",
        question=(
            "Rule 5: narrow the code-semantics scope to only the unreviewed "
            "span, or skip it entirely since prior review already covered it?"
        ),
        dispositions=[
            build_disposition("narrow"),
            build_disposition("skip"),
        ],
        evidence=json.dumps(result),
        reason="already-reviewed-span judgment (SKILL.md Rule 5) — inputs only, per DR-090",
    )
    envelope = build_envelope(
        artifact={"kind": "skill-step", "name": "parallel-review-gate-decision.rule5-inputs"},
        preflight={"rule5_inputs": result},
        judgment_points=[judgment_point],
        narration="Rule 5 inputs computed; skip-vs-narrow decision deferred to the skill body.",
        next_move="EM resolves jp_rule5_skip_vs_narrow using judgment_points[0]",
    )
    emit(envelope)
    print(json.dumps(envelope))
    return 0


def compute_chunks(
    scope_files: list[str],
    seam_manifest: list[tuple[str, str]],
    target_size: int,
) -> dict:
    """Seam-nuclei-first chunking (SKILL.md § Chunking). File-level, not
    hunk-level (see module negative-spec)."""
    sessions_by_file: dict[str, set[str]] = defaultdict(set)
    for f, session in seam_manifest:
        sessions_by_file[f].add(session)

    seam_files = {f for f, sessions in sessions_by_file.items() if len(sessions) >= 2}
    scope_set = list(dict.fromkeys(scope_files))  # de-dup, preserve order
    assigned: set[str] = set()
    chunks: dict[str, list[str]] = {}
    chunk_idx = 0

    # 1+2: seam nuclei first, with overflow spilling non-seam co-touchers.
    for seam_file in [f for f in scope_set if f in seam_files]:
        if seam_file in assigned:
            continue
        chunk_idx += 1
        chunk_name = f"chunk-{chunk_idx}"
        nucleus = [seam_file]
        assigned.add(seam_file)
        seam_sessions = sessions_by_file.get(seam_file, set())
        co_touchers = [
            f
            for f in scope_set
            if f not in assigned
            and f not in seam_files
            and sessions_by_file.get(f, set()) & seam_sessions
        ]
        if len(nucleus) + len(co_touchers) > target_size:
            # Overflow: seam file stays; spill co-touchers to fill pass below.
            chunks[chunk_name] = nucleus
        else:
            chunks[chunk_name] = nucleus + co_touchers
            assigned.update(co_touchers)

    # 3: fill with remaining narrowed-scope files, grouped by top-level dir.
    remaining = [f for f in scope_set if f not in assigned]
    by_dir: dict[str, list[str]] = defaultdict(list)
    for f in remaining:
        top = f.split("/", 1)[0] if "/" in f else f
        by_dir[top].append(f)

    for _dirname, files in sorted(by_dir.items()):
        for i in range(0, len(files), target_size):
            chunk_idx += 1
            group = files[i : i + target_size]
            chunks[f"chunk-{chunk_idx}"] = group
            assigned.update(group)

    return {
        "chunks": chunks,
        "chunk_count": len(chunks),
        "seam_nucleus_count": len(seam_files),
    }


def _write_manifest_tsv(chunks: dict[str, list[str]], out_path: Path) -> None:
    lines = []
    for chunk_name, files in chunks.items():
        for f in files:
            lines.append(f"{chunk_name}\t{f}")
    out_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8", newline="\n")


def _cmd_chunk(args: argparse.Namespace) -> int:
    scope_path = Path(args.scope_files_file)
    manifest_path = Path(args.seam_manifest_file)
    if not scope_path.is_file():
        print(f"{_PROG}: --scope-files-file not found: {scope_path}", file=sys.stderr)
        return 1
    if not manifest_path.is_file():
        print(f"{_PROG}: --seam-manifest-file not found: {manifest_path}", file=sys.stderr)
        return 1

    scope_files = [ln.strip() for ln in scope_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    seam_manifest: list[tuple[str, str]] = []
    for ln in manifest_path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        parts = ln.split("\t")
        if len(parts) != 2:
            print(f"{_PROG}: malformed seam-manifest row (expected 2 TAB-separated fields): {ln!r}", file=sys.stderr)
            return 1
        seam_manifest.append((parts[0], parts[1]))

    result = compute_chunks(scope_files, seam_manifest, args.target_size)
    if args.out:
        _write_manifest_tsv(result["chunks"], Path(args.out))
    envelope = build_envelope(
        artifact={"kind": "skill-step", "name": "parallel-review-gate-decision.chunk"},
        gates={"seam_nucleus_count": result["seam_nucleus_count"]},
        decisions={"chunk": result},
        narration=(
            f"{result['chunk_count']} chunk(s) computed "
            f"({result['seam_nucleus_count']} seam nucleus/nuclei)."
        ),
        next_move="dispatch chunk-1..N per decisions.chunk.chunks (or the written --out manifest)",
    )
    emit(envelope)
    print(json.dumps(envelope))
    return 0


_RESOLVER_BRANCH_TABLE = {
    0: ("run_full", "full suite resolved, run $TEST_CMD"),
    3: (
        "run_fast_fallback",
        "fast-tier fallback (no full_test_cmd configured); run it anyway and note "
        "the narrower coverage honestly in the eventual verdict",
    ),
    2: ("skip", "unconfigured — do not fabricate a command, skip running the suite this week"),
}


def _cmd_resolver_branch(args: argparse.Namespace) -> int:
    entry = _RESOLVER_BRANCH_TABLE.get(args.resolver_exit)
    if entry is None:
        print(
            f"{_PROG}: unrecognized --resolver-exit {args.resolver_exit} "
            "(expected 0, 2, or 3 per coordinator_resolve_validation_cmd.py's contract)",
            file=sys.stderr,
        )
        return 1
    action, note = entry
    test_cmd = args.test_cmd if action in ("run_full", "run_fast_fallback") else None
    result = {"action": action, "test_cmd": test_cmd, "note": note}
    envelope = build_envelope(
        artifact={"kind": "skill-step", "name": "parallel-review-gate-decision.resolver-branch"},
        gates={"action": action},
        decisions={"resolver_branch": result},
        narration=note,
        next_move=(
            f"run `{test_cmd}`" if test_cmd else "do not run the suite this week"
        ),
    )
    emit(envelope)
    print(json.dumps(envelope))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=_PROG, description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="command", required=True)

    gate = sub.add_parser("gate", help="Compute gating Rules 1-4")
    gate.add_argument("--range", dest="range_", default="")
    gate.add_argument("--repo-root", dest="repo_root", default="")
    gate.add_argument("--force", action="store_true")
    gate.set_defaults(func=_cmd_gate)

    r5 = sub.add_parser("rule5-inputs", help="Surface Rule 5's inputs (never its decision)")
    r5.add_argument("--scope-shas-file", required=True)
    r5.add_argument("--seam-files-file", required=True)
    r5.add_argument("--review-trail-dir", required=True)
    r5.set_defaults(func=_cmd_rule5_inputs)

    chunk = sub.add_parser("chunk", help="Seam-first chunking + TSV manifest emission")
    chunk.add_argument("--scope-files-file", required=True)
    chunk.add_argument("--seam-manifest-file", required=True)
    chunk.add_argument("--target-size", type=int, default=25)
    chunk.add_argument("--out", default="")
    chunk.set_defaults(func=_cmd_chunk)

    rb = sub.add_parser("resolver-branch", help="Replace the $RESOLVER_EXIT branch table")
    rb.add_argument("--resolver-exit", type=int, required=True)
    rb.add_argument("--test-cmd", default=None)
    rb.set_defaults(func=_cmd_resolver_branch)

    return p


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    try:
        _argv = recover_windows_argv(sys.argv[1:], _LAUNCHER_CMD_NAME)
    except UnsoundRawCmdlineTransport:
        print(
            "parallel-review-gate-decision.py: the invoking shell stripped "
            "characters from this command line before this process started — "
            f'run `python "{_BIN_DIR / "parallel-review-gate-decision.py"}" '
            "...` instead.",
            file=sys.stderr,
        )
        sys.exit(1)
    sys.exit(main(_argv))
