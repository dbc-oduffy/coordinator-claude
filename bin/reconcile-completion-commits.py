#!/usr/bin/env python3
# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""reconcile-completion-commits.py — completion.reconcile_commits native trampoline.

Purpose: closes the post-summary accounting gap when work continues after
/workstream-complete Step 4 prints its summary, producing commits the entry
never accounts for. Windows de-bash campaign, F1-d-reconcile chunk
(2026-07-21): FULL FACADE COLLAPSE of reconcile-completion-commits.sh onto
the native claude-klabauter op `completion.reconcile_commits`, now that its `dry_run`
(read-only) mode exists (claude-klabauter coordinator_core/ops/completion_ops.py
`reconcile_completion_commits` / `_reconcile_commits_handler`). Both
--append (write) AND detect-only (no --append) modes route through the SAME
op call now — dry_run=False for --append, dry_run=True for detect-only. The
prior Zone-A/Zone-B split (facade-side git resolution for detect-only,
because the op used to be mutating-only) is retired: the op resolves the
FULL delta (merge-base, chain-slug expansion, multi-session git-log
collection, SHA canonicalization) internally on both paths now.

No shell is spawned by this module for its own logic (`git rev-parse` runs
via subprocess.run() with an argv list, never through a shell string);
cc_invoke.route_mutation() spawns `python3 -m coordinator_core.invoke`
per-call (DR-215 transport), same as every other op-family trampoline.

Two-state routing model (inherited from cc_invoke.route()/route_mutation()):
  State 2 (seam present + invoke succeeds) -> native op ran (write or
           read-only depending on dry_run).
  State 3 (seam absent, or seam present + cc_invoke fails, or op-level
           refusal) -> fail-loud, non-zero exit, NEVER falls back to a
           legacy body — legacy_reconcile_commits() below only ever raises
           (T2-g1 finish-strangler; the bash awk/mv write body this used to
           hold was deleted long before this port).

Client-side validation retained ahead of the op call (these guards fire
BEFORE any native dispatch, matching the bash oracle's step ordering):
  Step 1: entry-path existence/readability (exit 2).
  Step 2: frontmatter `status:` parse + `pending-release`-only gate (exit 1
          on unparseable; SKIP + exit 0 on any other status value).
  Step 3: session-id resolution + allowlist/"null" guard (exit 1). Tiers
          1-3 of the 4-tier chain are ported (COORDINATOR_SESSION_ID >
          CLAUDE_SESSION_ID > CLAUDE_CODE_SESSION_ID); tier 4 (the
          `.git/coordinator-sessions/.current-session-id` sentinel +
          live-session ambiguity guard) is intentionally NOT ported — same
          documented carve-out as append-plan-session.py's `_resolve_session_id`
          (modern Claude Code always sets CLAUDE_CODE_SESSION_ID; every known
          production caller — workday-complete.md, workday-start.md,
          workweek-complete.md, merging-to-main/SKILL.md — passes
          --session-id explicitly, so tier 4 is unreached in the steady
          state). A manual invocation relying on the bare sentinel file with
          no env var and no --session-id flag will get an empty-session-id
          exit 1 here instead of falling through to the sentinel — this is
          a deliberate, narrower contract than the retired bash oracle.
  Step 5 (detect-only only): `commits:` frontmatter key MUST be structurally
          present — this is a pre-op guard, independent of what the op
          would have computed, because the op's own `_parse_existing_commits`
          silently treats an absent key as an empty set (no error). Applied
          ONLY to the detect-only path (mirrors the bash oracle exactly:
          Step 5 lived after the --append branch's early return, so
          --append mode never ran this check either).

Everything else (chain-slug derivation/allowlist, merge-base resolution,
multi-session commit collection, short-vs-full SHA canonicalization, delta
computation) is now the op's job — see `resolve_chain_commits` /
`reconcile_completion_commits` in claude-klabauter's completion_ops.py.

Spec backlink: docs/plans/2026-06-27-post-summary-completion-loop-closure.md § C1
Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md (Wave F1-d)
Frontier note: tasks/debash-consolidated/frontier-2026-07-21.md (F1-d-reconcile)
Session-scope pattern: docs/wiki/workstream-complete-review.md § Session-scoped diff via --session-id

Usage (unchanged from the bash facade — zero caller-arg repoints beyond the
`.sh` -> `.py` filename swap):
    python coordinator/bin/reconcile-completion-commits.py [--append] [--allow-released] [--session-id <id>] <entry-path>

`--allow-released` — escape hatch for a commit discovered AFTER an entry's
`status:` flipped to `released` (2026-07-27, C4 pending-release escape hatch).
Removing the `status: pending-release` gate outright was rejected: `released`
means "this `commits:` list is a closed historical record," and a late commit
silently mutating a released version's frontmatter would corrupt the exact
audit trail the freeze protects. `--allow-released` does NOT lift that freeze
— it only unlocks a SEPARATE, NEW `late_commits:` YAML list for
coverage-accounting attribution. Without the flag, a `released` entry is
skipped exactly as before (`status=released SKIP`, exit 0, file untouched).
With it, on a `released` entry only:
  - the underlying `completion.reconcile_commits` op is ALWAYS invoked with
    `dry_run=True` (never write-mode) — the op's own commits:-mutating write
    path is never reached for a released entry, regardless of `--append`.
  - `--append` then folds the op's computed delta into `late_commits:`
    CLIENT-SIDE, in this facade (`_apply_late_commits_fold` below) — `commits:`
    itself is never read for a write nor rewritten. Idempotent against repeat
    runs: SHAs already present in `late_commits:` are filtered out of the
    delta before folding (`_parse_frontmatter_list`), independent of the op's
    own `commits:`-only idempotency check.
  - without `--append`, behaves like today's detect-only mode: prints the
    delta, writes nothing.
A `pending-release` entry's behavior is completely unchanged by this flag —
it always goes through the op's normal commits: write path.

Exit codes (preserved from the retired bash oracle's contract):
  0  — normal exit: no-op skip (released entry), delta=0 OK, delta printed,
       merge-base unresolved (non-blocking), or appended (to `commits:`, or
       to `late_commits:` under `--allow-released` on a released entry).
  1  — argument / validation error (bad session-id, malformed frontmatter,
       missing/too-many positional args, etc.)
  2  — entry-path absent/unreadable, OR native-transport failure (seam
       absent / cc_invoke fails / git-repo-root unresolvable).

NEVER commits or stages files. NEVER writes the prose body. Writes ONLY the
`commits:` YAML list (via the op's own `_apply_commits_fold`, `pending-release`
entries) OR, under `--allow-released` on a `released` entry, ONLY the separate
`late_commits:` YAML list (via this facade's own `_apply_late_commits_fold`)
— `commits:` on a `released` entry is NEVER touched by this script, by either
code path. Caller owns all git operations after --append mode mutates the
entry file.

Negative-spec (retired transport patterns — DO NOT reintroduce):
    - No `#!/bin/sh` polyglot header — pure Python entrypoint. Windows
      bare-name invocation is covered by the generated
      reconcile-completion-commits.cmd launcher (gen-launcher-shim.py), not
      a shell shebang trick.
    - Does NOT source coordinator/lib/strangler-facade.sh or
      coordinator-session.sh — cc_invoke.route_mutation() is the sole
      transport; `_resolve_session_id()` below is the sole (partial,
      tiers-1-3-only) session-id resolver.
    - Does NOT run any local git merge-base / git-log / rev-parse
      resolution for the detect-only (no-`--append`) path any more — that
      whole Zone-A block is retired now that the op's `dry_run=True` mode
      performs the identical resolution server-side. Reintroducing a local
      git-log scan here would silently diverge from the op's canonical
      resolution the moment either side's logic drifts.
    - Does NOT fall back to a direct-write/legacy body on any State-1/2/3
      outcome — legacy_reconcile_commits() below only ever raises.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_BIN_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import cc_invoke  # noqa: E402

# Windows: suppresses the console popup a subprocess.run(...) would otherwise
# trigger under the headless Claude Code Bash-tool parent. No-op (0) elsewhere.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_SESSION_ID_ENV_TIERS = (
    "COORDINATOR_SESSION_ID",
    "CLAUDE_SESSION_ID",
    "CLAUDE_CODE_SESSION_ID",
)

_ID_ALLOWLIST_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")

_USAGE = "Usage: reconcile-completion-commits.py [--append] [--session-id <id>] <entry-path>"


def _resolve_session_id_env() -> str:
    """Tiers 1-3 of the 4-tier chain — see module docstring for the tier-4 carve-out."""
    for var in _SESSION_ID_ENV_TIERS:
        val = os.environ.get(var, "")
        if val:
            return val
    return ""


def _resolve_repo_root() -> str | None:
    """Resolve the current git worktree root from PWD.

    Mirrors strangler-facade.sh's `git -C "$PWD" rev-parse --show-toplevel`
    (standalone-repo assumption; no explicit repo-root positional arg).
    Returns None on failure.
    """
    try:
        result = subprocess.run(
            ["git", "-C", os.getcwd(), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            creationflags=_NO_WINDOW,
        )
    except OSError:
        return None
    root = result.stdout.strip()
    if result.returncode != 0 or not root:
        return None
    return root


def legacy_reconcile_commits() -> None:
    """Fail-loud stand-in for the deleted legacy body (T2-g1 finish-strangler).

    Only reached when coordinator_core.invoke is NOT importable on disk
    (State-1 dispatch target) — route_mutation still requires a legacy_fn
    argument, but the pre-facade bash implementation (the awk/mv write body,
    plus the local Zone-A git resolution the detect-only path used before
    this facade collapse) is gone, so a genuinely-absent seam is now a hard
    error on BOTH --append and detect-only paths, not a legacy fallback.
    """
    raise RuntimeError(
        "reconcile-completion-commits.py: coordinator_core.invoke seam absent — "
        "legacy path removed (T2-g1 finish-strangler / F1-d facade collapse); "
        "cannot dispatch completion.reconcile_commits"
    )


def _frontmatter_field(content: str, key: str) -> str | None:
    """Mirror the oracle's awk frontmatter scan for a single top-level key.

    Scans only within the first `---`...`---` fence block (n==1 in awk terms);
    returns the first matching `^{key}:` line's value with the `{key}:` prefix
    and any immediately-following whitespace stripped (mirrors
    `sub(/^{key}:[[:space:]]*/, "")`). Returns None if the fence block never
    closes or the key is never found.
    """
    n = 0
    prefix_re = re.compile(rf"^{re.escape(key)}:[ \t]*")
    for line in content.splitlines():
        if line == "---":
            n += 1
            if n == 2:
                return None
            continue
        if n == 1:
            m = prefix_re.match(line)
            if m:
                return line[m.end():]
    return None


def _has_top_level_key(content: str, key: str) -> bool:
    """True iff a `^{key}:` line exists within the first frontmatter fence block."""
    n = 0
    prefix = f"{key}:"
    for line in content.splitlines():
        if line == "---":
            n += 1
            if n == 2:
                return False
            continue
        if n == 1 and line.startswith(prefix):
            return True
    return False


def _parse_frontmatter_list(content: str, key: str) -> set[str]:
    """Collect values already present in a top-level block-style YAML list.

    Used ONLY for this facade's own `late_commits:` idempotency check (never
    for `commits:`, which the native op owns). Best-effort: recognizes only
    the block form this facade itself writes (`key:` on its own line,
    followed by `  - "value"` items) — a pre-existing `late_commits:` in some
    other shape (e.g. inline flow-style) is not expected, since this facade
    is the sole writer of the key, but is handled by simply returning
    whatever block-style items ARE parseable rather than raising (this is a
    dedup aid, not a structural validator — `_apply_late_commits_fold` below
    is the one place that must not silently corrupt the field).
    """
    values: set[str] = set()
    fm_n = 0
    in_key = False
    key_line_re = re.compile(rf"^{re.escape(key)}:\s*$")
    for line in content.splitlines():
        if line == "---":
            fm_n += 1
            if fm_n == 2:
                break
            continue
        if fm_n != 1:
            continue
        if key_line_re.match(line):
            in_key = True
            continue
        if in_key:
            if re.match(r"^\s+-\s", line):
                val = re.sub(r"^\s*-\s*", "", line).strip().strip('"').strip("'")
                if val:
                    values.add(val)
                continue
            in_key = False
    return values


def _has_non_block_key(content: str, key: str) -> bool:
    """True iff `{key}:` is present in the first frontmatter fence in any
    non-block-list form (e.g. flow-style `key: []`, or a scalar value).

    Review: code-reviewer — F7. `_apply_late_commits_fold`'s `key_line_re`
    only recognizes a bare block-style `late_commits:` key; a pre-existing
    flow-style or scalar declaration would silently fail that match and get
    a second, block-style key inserted right before it — a duplicate key
    that most YAML parsers resolve unpredictably. This is the detect half
    of a detect-then-fail-loud guard, called by `main()` before folding.
    """
    n = 0
    non_block_re = re.compile(rf"^{re.escape(key)}:\s*\S")
    for line in content.splitlines():
        if line == "---":
            n += 1
            if n == 2:
                return False
            continue
        if n == 1 and non_block_re.match(line):
            return True
    return False


def _apply_late_commits_fold(content: str, new_shas: list[str]) -> str:
    """Fold `new_shas` into a NEW/existing `late_commits:` block-style YAML list.

    Client-side counterpart (owned by this facade, not the op) to the op's
    `_apply_commits_fold` — deliberately scoped down to the one shape this
    facade itself ever writes:
      - `late_commits:` absent -> inserted as a new block-style key, right
        before the frontmatter's closing `---` fence (append-only placement;
        never reorders or rewrites any existing key).
      - `late_commits:` present as a block list -> new items appended
        immediately after the last existing item.
      - SHA line format matches `_apply_commits_fold`: `  - "<sha>"`.
    `commits:` is never read or written here — this function does not know
    the key exists. Caller (`main()`) is responsible for the `--allow-released`
    idempotency filter (`_parse_frontmatter_list`) before calling this.
    """
    if not new_shas:
        return content

    new_lines = [f'  - "{sha}"' for sha in new_shas]
    lines = content.splitlines(keepends=False)
    result_lines: list[str] = []
    fm_n = 0
    in_late = False
    key_found = False
    key_line_re = re.compile(r"^late_commits:\s*$")

    for line in lines:
        if line == "---":
            fm_n += 1
            if fm_n == 2:
                if in_late:
                    result_lines.extend(new_lines)
                    in_late = False
                elif not key_found:
                    result_lines.append("late_commits:")
                    result_lines.extend(new_lines)
            result_lines.append(line)
            continue

        if fm_n == 1:
            if key_line_re.match(line):
                key_found = True
                in_late = True
                result_lines.append(line)
                continue

            if in_late:
                if re.match(r"^\s+-\s", line):
                    result_lines.append(line)
                    continue
                result_lines.extend(new_lines)
                in_late = False
                result_lines.append(line)
                continue

        result_lines.append(line)

    if in_late:
        result_lines.extend(new_lines)

    return "\n".join(result_lines) + "\n"


def _atomic_write(path: str, content: str) -> None:
    """Content-additive write via temp file + `os.replace` (never a partial write)."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".reconcile-tmp-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def main(argv: list[str]) -> int:
    # `argv` is args-only (no leading program-name token) -- the convention
    # every sibling consumes-manifest CLI's `main(argv)` follows (see e.g.
    # `workday-complete-reconcile.py`'s identical comment, and
    # `workday_complete.apply._invoke_cli_main` / `workstream_complete.apply.
    # _invoke_cli_main`, which both call `main_fn(list(directive_args))`
    # in-process with no argv[0] placeholder). This function previously did
    # `argv[1:]` here, an off-by-one relative to every sibling that silently
    # ate the first real flag under in-process apply dispatch (2026-07-27
    # arg-mismatch audit — mirrors the 2026-07-26 fix to
    # `workday-complete-reconcile.py`'s identical defect).
    args = argv

    append_mode = False
    allow_released_flag = False
    session_id_flag = ""
    positional: list[str] = []

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--append":
            append_mode = True
            i += 1
        elif arg == "--allow-released":
            allow_released_flag = True
            i += 1
        elif arg == "--session-id":
            if i + 1 >= len(args) or args[i + 1] == "":
                print(
                    "reconcile-completion-commits.py: --session-id requires an argument",
                    file=sys.stderr,
                )
                return 1
            session_id_flag = args[i + 1]
            i += 2
        elif arg == "--":
            positional.extend(args[i + 1:])
            i = len(args)
        elif arg.startswith("-"):
            print(
                f"reconcile-completion-commits.py: unknown flag: {arg}",
                file=sys.stderr,
            )
            return 1
        else:
            positional.extend(args[i:])
            i = len(args)

    if not positional:
        print(
            "reconcile-completion-commits.py: missing required <entry-path>",
            file=sys.stderr,
        )
        print(_USAGE, file=sys.stderr)
        return 1
    if len(positional) != 1:
        print(
            "reconcile-completion-commits.py: too many positional args "
            "(expected exactly one <entry-path>)",
            file=sys.stderr,
        )
        print(_USAGE, file=sys.stderr)
        return 1

    entry_path = positional[0]

    # ---------------------------------------------------------------------
    # Step 1: resolve entry-path; fail loud (exit 2) if absent or unreadable
    # ---------------------------------------------------------------------
    if not os.path.isfile(entry_path) or not os.access(entry_path, os.R_OK):
        print(
            f"reconcile-completion-commits.py: entry not found or unreadable: {entry_path}",
            file=sys.stderr,
        )
        return 2

    try:
        entry_content = open(entry_path, "r", encoding="utf-8").read()
    except OSError as exc:
        print(
            f"reconcile-completion-commits.py: entry not found or unreadable: {entry_path} ({exc})",
            file=sys.stderr,
        )
        return 2

    # ---------------------------------------------------------------------
    # Step 2: released-entry guard — parse frontmatter status:
    # ---------------------------------------------------------------------
    status_val = _frontmatter_field(entry_content, "status")
    if not status_val:
        print(
            f"reconcile-completion-commits.py: cannot parse status: from frontmatter in {entry_path}",
            file=sys.stderr,
        )
        return 1

    if status_val == "released":
        if not allow_released_flag:
            print(f"status={status_val} SKIP", file=sys.stderr)
            return 0
        # --allow-released: the freeze on `commits:` stays intact (see module
        # docstring) — this only unlocks the separate `late_commits:` fold
        # below. released_late_mode forces dry_run=True on the op call
        # (never the op's write path) regardless of --append.
        released_late_mode = True
    elif status_val == "pending-release":
        released_late_mode = False
    else:
        print(f"status={status_val} SKIP", file=sys.stderr)
        return 0

    # ---------------------------------------------------------------------
    # Step 3: resolve session-id (tiers 1-3 only — see module docstring)
    # ---------------------------------------------------------------------
    sid = session_id_flag
    if not sid:
        sid = _resolve_session_id_env()

    if not sid or sid == "null":
        print(
            "reconcile-completion-commits.py: session-id is empty or null — pass "
            "--session-id explicitly, or run: export CLAUDE_SESSION_ID=<harness-id>",
            file=sys.stderr,
        )
        return 1

    if not _ID_ALLOWLIST_RE.match(sid):
        print(
            f"reconcile-completion-commits.py: session-id must match "
            f"{_ID_ALLOWLIST_RE.pattern}: {sid}",
            file=sys.stderr,
        )
        return 1

    repo_root = _resolve_repo_root()
    if repo_root is None:
        print(
            f"reconcile-completion-commits.py: cannot resolve git repo root from {os.getcwd()}",
            file=sys.stderr,
        )
        return 2

    # ---------------------------------------------------------------------
    # Step 5 (detect-only only): malformed-frontmatter guard — commits: key
    # must be structurally present. Mirrors the bash oracle's exact
    # positioning: --append mode never ran this check (it returned earlier).
    # ---------------------------------------------------------------------
    if not append_mode and not _has_top_level_key(entry_content, "commits"):
        print(
            f"reconcile-completion-commits.py: malformed frontmatter — commits: "
            f"key absent in {entry_path}",
            file=sys.stderr,
        )
        return 1

    params = {
        "plan_path": entry_path,
        "session_id": sid,
        # released_late_mode: ALWAYS dry_run — the op's commits:-mutating
        # write path must never be reached for a released entry, regardless
        # of --append. The --append write (to late_commits: only) happens
        # client-side below, after this call returns.
        "dry_run": (not append_mode) or released_late_mode,
    }

    try:
        result = cc_invoke.route_mutation(
            "completion.reconcile_commits", params, repo_root, legacy_reconcile_commits
        )
    except cc_invoke.RouteMutationError as exc:
        result_dict = exc.result if isinstance(exc.result, dict) else {}
        raw_exit_code = result_dict.get("exit_code")
        try:
            exit_code = int(raw_exit_code) if raw_exit_code is not None else 1
        except (TypeError, ValueError):
            exit_code = 1
        if exit_code == 0:
            exit_code = 1
        print(f"reconcile-completion-commits.py: {exc}", file=sys.stderr)
        return exit_code
    except RuntimeError as exc:
        # Transport failure (State-3) or legacy-seam-absent raise (State-1) —
        # both converge on rc=2, mirroring the retired bash facade's exit-2
        # contract for seam-absent / cc_invoke transport failure.
        print(f"reconcile-completion-commits.py: {exc}", file=sys.stderr)
        return 2

    if not isinstance(result, dict):
        print(
            f"reconcile-completion-commits.py: unexpected non-dict result from "
            f"completion.reconcile_commits: {result!r}",
            file=sys.stderr,
        )
        return 2

    if result.get("merge_base_unresolved"):
        print("merge-base unresolved — reconcile skipped", file=sys.stderr)
        return 0

    for warning in result.get("resolution_warnings") or []:
        if warning:
            print(f"WARN: {warning}", file=sys.stderr)

    no_op = bool(result.get("no_op", False))
    delta_shorts = result.get("delta_shorts") or []

    if no_op:
        provenance_warning = result.get("provenance_warning")
        if provenance_warning:
            print(f"WARN: {provenance_warning}", file=sys.stderr)
        print("delta=0 OK")
        return 0

    if released_late_mode:
        if not append_mode:
            print(f"delta={len(delta_shorts)}")
            for sha in delta_shorts:
                print(sha)
            return 0

        # --append on a released entry: fold ONLY into late_commits:,
        # filtering out SHAs this facade already folded on a prior run
        # (the op's own idempotency check only ever looks at commits:,
        # which released_late_mode never touches).
        try:
            current_content = open(entry_path, "r", encoding="utf-8").read()
        except OSError as exc:
            print(
                f"reconcile-completion-commits.py: entry not found or unreadable: {entry_path} ({exc})",
                file=sys.stderr,
            )
            return 2

        already_late = _parse_frontmatter_list(current_content, "late_commits")
        new_shas = [sha for sha in delta_shorts if sha not in already_late]

        if not new_shas:
            print("delta=0 OK")
            return 0

        # Review: code-reviewer — F7. Detect-then-fail-loud: a pre-existing
        # `late_commits:` key in a non-block form (flow-style, scalar, etc.)
        # would silently escape `_apply_late_commits_fold`'s key detection
        # and produce a duplicate key on write. Refuse before any write.
        if _has_non_block_key(current_content, "late_commits"):
            print(
                f"reconcile-completion-commits.py: late_commits: key present "
                f"in {entry_path} in a non-block-list form — refusing to "
                f"fold; this facade only ever writes block-style lists",
                file=sys.stderr,
            )
            return 2

        commits_before = _has_top_level_key(current_content, "commits")
        updated_content = _apply_late_commits_fold(current_content, new_shas)

        # Review: code-reviewer — F1. Invariant check (module docstring /
        # negative-spec: commits: presence must be unchanged by a
        # late_commits:-only fold) must run BEFORE any bytes land on disk —
        # a check evaluated after _atomic_write only detects corruption
        # post-hoc, and a bare `assert` is stripped entirely under
        # `python -O`/PYTHONOPTIMIZE=1. Fail loud via the documented
        # exit-code contract (rc=2) instead, before the write.
        if _has_top_level_key(updated_content, "commits") != commits_before:
            print(
                "reconcile-completion-commits.py: released_late_mode fold "
                "touched commits: presence — refusing to write; this is a "
                "bug in _apply_late_commits_fold",
                file=sys.stderr,
            )
            return 2

        try:
            _atomic_write(entry_path, updated_content)
        except OSError as exc:
            print(
                f"reconcile-completion-commits.py: failed writing {entry_path}: {exc}",
                file=sys.stderr,
            )
            return 2

        print(f"appended={len(new_shas)} late_commits")
        return 0

    if append_mode:
        appended = result.get("appended", 0)
        print(f"appended={appended}")
        return 0

    print(f"delta={len(delta_shorts)}")
    for sha in delta_shorts:
        print(sha)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
