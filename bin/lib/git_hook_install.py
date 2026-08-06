"""git_hook_install — native-Python installer/repair for the coordinator git hooks.

Native-Python port (DR-059 de-bash, Windows-first) of the retired bash installer
pair coordinator-ensure-post-commit-hook / coordinator-ensure-prepare-commit-msg-hook.
Exposes two entrypoint functions, each idempotent, self-healing, and always
returning 0 (a session-boot / commit-time helper must never block).

Load-bearing Windows change vs. the bash predecessors: the INSTALLED hook bodies
these write into .git/hooks/ no longer depend on `bash`. A Windows box running git
always has `sh` (Git-for-Windows / MinGit ship it — git itself runs hooks through
it) but frequently lacks `bash` (GitHub Desktop's MinGit is the canonical case).
The old hook bodies did `command -v bash … || exit 0` then `nohup bash "$SCRIPT"`,
so on a bash-less box the hook silently no-op'd — auto-push and the Session-Id
trailer never fired. The new bodies probe `python3 || python || py` and invoke the
(polyglot) target directly, so they work with only sh + python — never bash.

The hook FILE still carries a `#!/bin/sh` shebang: git's hook-execution model runs
the hook file through its bundled shell regardless of shebang, so a shell shebang is
unavoidable — but the body is bash-free. "Shell-free" in the de-bash mandate means
"needs nothing beyond what git already provides (sh) + python" — i.e. bash-free.

Both installed hook shims `exec` their target synchronously at the shell level —
there is no shell-level backgrounding (`nohup … &`) anywhere in this module.
post-commit's target (coordinator-auto-push) owns its own async self-detach
internally (claude-klabauter's auto_push.py: os.fork() on POSIX, detached Popen respawn on
Windows) when async is wanted; the shim's job is only to resolve python + exec.

Behavior (per hook), mirroring the bash oracle:
  - hook absent          → install canonical bash-free shim + chmod +x (atomic write).
  - hook present + our append-form START marker (`# === {header} ===`, see
    `_append_markers`) → NEVER the whole-file rewrite branch (see "Refuse to
    guess" below). If the matching END marker is also present: already
    installed, idempotent no-op (chmod +x only). If the END marker is
    missing (a legacy append block, pre-dating that convention): left
    completely untouched, one loud stderr warning, chmod +x, still exit 0.
  - hook present + marker (non-comment), NOT an append-form body
      ├─ current form (bash-free, correct baked path, current interpreter
      │    probe) → exec-bit repair only.
      └─ stale form (old bash-shebang exec / `nohup bash` / `nohup "$_PY"` /
           `exec bash` / stale path / stale single-line interpreter probe
           predating `_py_resolve()`) → rewrite atomically to current
           bash-free form + chmod +x.
  - hook present + marker absent (or marker only in a comment) → append a bash-free
    invocation, bounded by fresh start/end markers (preserves an existing
    custom hook chain), then chmod +x.
  - helper (the invoked target script) missing → skip (exit 0), but LOUDLY: a
    stderr WARNING names the hook and says commits are not being auto-pushed /
    annotated — never a silent no-op.
  - no python3/python/py interpreter resolvable on PATH → same treatment as the
    missing-helper case above (loud stderr WARNING, exit 0, never fail-closed —
    a push helper must never block a commit). Fixed 2026-07-28 (D3): this used
    to be `[ -n "$_PY" ] || exit 0` with zero output, asymmetric with the
    already-loud missing-script branch two lines below it.

Marker match strips comment lines before scanning, so a stray
"# TODO: replace with coordinator-auto-push" cannot false-positive as routed.

Refuse to guess, don't guess and destroy: `_ensure_hook`'s "stale routed
form → wholesale rewrite" branch used to be gated on `marker`-presence
alone, which an append-form body also satisfies (the marker is right there
in its appended `_T="..."` line) while never satisfying the shim-shape
`current_predicates` — so a SECOND install call on an append-form hook was
misclassified as "stale shim" and the whole file (foreign prefix included)
was clobbered on the atomic-write branch. Fixed by positively ruling OUT
append-form via `_append_markers(header)` BEFORE the rewrite branch is
reachable at all — same principle as the sibling installer's b4b6e984
review (raise/refuse rather than guess-and-destroy when a body's shape
can't be told apart), and the same principle again for a legacy
(end-marker-less) append block: never scanned for a heuristic end, always
left alone with a loud warning. See `_ensure_hook`'s own docstring for the
full account.

Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md § git-hook-installers-port
Prior bash implementations: see git log (coordinator-ensure-post-commit-hook,
coordinator-ensure-prepare-commit-msg-hook — retired on this cutover).
"""
from __future__ import annotations

import os
import subprocess
import sys
from typing import List, Optional
from coordinator_core.win_portability import is_executable
from coordinator_core.py_probe_sh import python_probe_lines

_MARKETPLACE_SUFFIX = ".claude/plugins/coordinator/bin"

# DR-072: durable-first .doe-root pointer read, cold shape (no lib-sourcing —
# these are POSIX-`sh` string literals baked into installed git hooks, which
# cannot source a coordinator lib). Settings-home first, legacy ~/.claude
# fallback during the transition window (see C1/C2/C3 of
# docs/plans/2026-07-21-durable-coordinator-root-pointer.md).
_DOE_ROOT_DURABLE_SH = '${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/machine-local/.doe-root'
_DOE_ROOT_LEGACY_SH = '$HOME/.claude/.doe-root'


def _sh_path(p: str) -> str:
    """Normalize a path to forward slashes for interpolation into a POSIX-`sh`
    hook body. The hook FILE is always run through `sh` (git's hook-execution
    model), so an emitted path literal must be forward-slash even when the
    Python-side value was produced by `os.path.join`/`os.path.expanduser`
    (native-separator, i.e. backslash, on Windows). A backslash inside a
    double-quoted `sh` string is an escape character — do not rely on the
    tolerance of any particular shell's path mangling.

    Only apply at the boundary where a path enters emitted SHELL TEXT. Paths
    used for actual Python filesystem operations (`os.path.isfile`, `open`,
    `_atomic_write`, `hook_path`, `helper`) must stay native — do not normalize
    those.
    """
    return p.replace("\\", "/")


# ---------------------------------------------------------------------------
# COORD_BIN resolution — machine-local registry → .doe-root pointer → marketplace.
# Faithful port of the bash ladder; every rung is best-effort (any failure falls
# through), so the marketplace default is always a valid backstop.
# ---------------------------------------------------------------------------

def _resolve_machine_local_bin(bin_dir: str) -> Optional[str]:
    """Locate the `machine-local` executable: sibling of `bin_dir`, or on PATH.

    Shared by every rung in `_resolve_coord_bin` that consults the machine-local
    registry — best-effort, never raises.
    """
    cand = os.path.join(bin_dir, "machine-local")
    if is_executable(cand):
        return cand
    from shutil import which

    return which("machine-local")


def _ml_get(ml_bin: Optional[str], key: str) -> Optional[str]:
    """Best-effort `machine-local get <key>` — returns stripped stdout, or None
    on any failure (missing binary, missing key, timeout, non-zero exit)."""
    if not ml_bin:
        return None
    try:
        out = subprocess.run(
            [ml_bin, "get", key],
            capture_output=True,
            text=True,
            timeout=15,
        )
        val = (out.stdout or "").strip()
        return val or None
    except Exception:
        return None


def _resolve_coord_bin(bin_dir: str, script_name: str) -> str:
    """Resolve the coordinator bin dir to bake into the installed hook body.

    Post-2026-07 executable-surface migration (DoE commit b644d5a9), the
    coordinator-claude *executables* (`coordinator-auto-push`,
    `coordinator-prepare-commit-msg`, ...) live under `claude-klabauter`'s
    `coordinator/bin/`, while `plugin.mirrors.coordinator-claude.source_path`
    (DoE-claude) still correctly means "where is coordinator-claude SOURCE" —
    it is consumed by the OSS-publish target resolution and must NOT be
    repointed at claude-klabauter. Executable resolution is a genuinely separate
    concern from source resolution, hence the dedicated rung below.

    Every rung validates the TARGET EXECUTABLE (`os.path.isfile`), never just
    the directory — a rung whose directory exists but lacks `script_name`
    falls through rather than returning a bin dir with nothing runnable in
    it. This is the fix for the 2026-07 silent-breakage: the prior isdir-only
    guards passed against an emptied-out DoE bin dir and reproduced the dead
    hook on every regeneration.

    Rung 1: `<bin_dir>/machine-local get plugin.mirrors.coordinator-claude.source_path`
            (or `machine-local` on PATH) → `<source_path>/bin/<script_name>`.
    Rung 2: `.doe-root` pointer, durable-first — settings-home
            (`$HOME/.coordinator-claude-settings/machine-local/.doe-root`, DR-072),
            falling back to the legacy `$HOME/.claude/.doe-root` —
            → `<doe>/coordinator/bin/<script_name>`.
    Rung 3: `machine-local get repos.claude_klabauter` →
            `<claude_klabauter>/coordinator/bin/<script_name>` — the executable
            surface's actual current home on a migrated machine.
    Rung 4: marketplace path
            `$HOME/.claude/plugins/coordinator/bin` —
            unconditional backstop, no isfile probe (matches prior behavior;
            this is the last resort, not a candidate to skip past).
    """
    home = os.path.expanduser("~")
    ml_bin = _resolve_machine_local_bin(bin_dir)

    # Rung 1: machine-local registry — coordinator-claude SOURCE path.
    coord_src = _ml_get(ml_bin, "plugin.mirrors.coordinator-claude.source_path")
    if coord_src:
        cand_bin = os.path.join(coord_src, "bin")
        if os.path.isfile(os.path.join(cand_bin, script_name)):
            return cand_bin
        if not os.path.isdir(coord_src):
            print(
                "[git_hook_install] WARNING: plugin.mirrors.coordinator-claude."
                f"source_path='{coord_src}' is not a directory; using fallback",
                file=sys.stderr,
            )

    # Rung 2: .doe-root cold-readable pointer (Windows-clean plain file read).
    # Durable-first (DR-072): settings-home pointer, falling back to the
    # legacy ~/.claude pointer during the transition window. No lib-sourcing
    # here — this is a cold Python read, mirroring the cold shell literal.
    settings_home = os.environ.get("COORDINATOR_SETTINGS_HOME") or os.path.join(
        home, ".coordinator-claude-settings"
    )
    for doe_root_ptr in (
        os.path.join(settings_home, "machine-local", ".doe-root"),
        os.path.join(home, ".claude", ".doe-root"),
    ):
        try:
            with open(doe_root_ptr, encoding="utf-8") as fh:
                doe_root = fh.read().strip()
        except OSError:
            continue
        if doe_root:
            cand_bin = os.path.join(doe_root, "coordinator", "bin")
            if os.path.isfile(os.path.join(cand_bin, script_name)):
                return cand_bin

    # Rung 3: machine-local registry — claude-klabauter repo path (the
    # executable surface's post-migration home).
    claude_klabauter_root = _ml_get(ml_bin, "repos.claude_klabauter")
    if claude_klabauter_root:
        cand_bin = os.path.join(claude_klabauter_root, "coordinator", "bin")
        if os.path.isfile(os.path.join(cand_bin, script_name)):
            return cand_bin

    # Rung 4: marketplace fallback (unconditional — last resort).
    return os.path.join(home, _MARKETPLACE_SUFFIX)


# ---------------------------------------------------------------------------
# Hook-body templates (bash-free: probe python3||python||py, invoke the target).
# ---------------------------------------------------------------------------

def _resolve_claude_klabauter_bin_sh(bin_dir: str, script_name: str) -> Optional[str]:
    """Best-effort, install-time-only read of `repos.claude_klabauter` for baking
    a claude-klabauter-bin candidate into the shell fallback chain. Returns a forward-slash
    `sh`-literal path (`<claude-klabauter>/coordinator/bin/<script_name>`) or None if the
    key is unresolvable right now — the emitted shim still probes `[ -f ... ]`
    at hook-run time regardless, so a stale/absent bake-time value only means
    that one candidate is a dead literal, not a shim that fails to run."""
    ml_bin = _resolve_machine_local_bin(bin_dir)
    claude_klabauter_root = _ml_get(ml_bin, "repos.claude_klabauter")
    if not claude_klabauter_root:
        return None
    return _sh_path(os.path.join(claude_klabauter_root, "coordinator", "bin", script_name))


def _shim_body(coord_bin: str, script_name: str, invoke_line: str, bin_dir: str = "") -> str:
    """Canonical fresh-install / self-heal shim body for a hook that runs one target.

    `invoke_line` is the final line that runs the resolved target via "$_PY" —
    both hooks now `exec` synchronously at the shell level; any async self-detach
    (post-commit's coordinator-auto-push) is owned by the invoked Python, not the shim.

    The shell fallback chain (baked SCRIPT → .doe-root pointer → claude-klabauter-bin
    candidate → marketplace) means an already-installed hook can recover a dead
    baked path WITHOUT waiting for the next `_resolve_coord_bin` regeneration —
    self-healing at hook-run time, not only at install time.
    """
    fallback = _sh_path(os.path.join("$HOME", _MARKETPLACE_SUFFIX, script_name))
    coord_bin_sh = _sh_path(coord_bin)
    claude_klabauter_cand = _resolve_claude_klabauter_bin_sh(bin_dir, script_name) if bin_dir else None
    claude_klabauter_probe = (
        f'[ -f "$SCRIPT" ] || SCRIPT="{claude_klabauter_cand}"\n' if claude_klabauter_cand else ""
    )
    return (
        "#!/bin/sh\n"
        f"# coordinator {script_name} hook — installed by git_hook_install.\n"
        "# Bash-free / Windows-invocable: needs only sh (git provides it) + python — NOT bash.\n"
        "# MinGit (GitHub Desktop) ships sh + python but not bash; the python-probe skips cleanly.\n"
        "# Skips Microsoft Store App Execution Alias stubs under WindowsApps (case-\n"
        "# insensitive) -- shared with coordinator_core.ops's two precommit-hook\n"
        "# installers; see coordinator_core.py_probe_sh's module docstring.\n"
        f"{python_probe_lines('_PY')}\n"
        '[ -n "$_PY" ] || { echo "[coordinator] WARNING: hook installed but no '
        'python3/python/py interpreter found on PATH — commits are NOT being '
        'auto-pushed / annotated by this hook" 1>&2; exit 0; }\n'
        f'SCRIPT="{coord_bin_sh}/{script_name}"\n'
        '[ -f "$SCRIPT" ] || { _dr="$(cat "' + _DOE_ROOT_DURABLE_SH + '" 2>/dev/null || '
        'cat "' + _DOE_ROOT_LEGACY_SH + '" 2>/dev/null)"; '
        f'[ -n "$_dr" ] && [ -f "$_dr/coordinator/bin/{script_name}" ] && '
        f'SCRIPT="$_dr/coordinator/bin/{script_name}"; }}\n'
        f"{claude_klabauter_probe}"
        f'[ -f "$SCRIPT" ] || SCRIPT="{fallback}"\n'
        '[ -f "$SCRIPT" ] || { echo "[coordinator] WARNING: hook installed but '
        f'{script_name} not found (looked in baked path, .doe-root, machine-local '
        'repos.claude_klabauter, and marketplace) — commits are NOT being auto-pushed / '
        'annotated by this hook" 1>&2; exit 0; }\n'
        f"{invoke_line}\n"
    )


def _append_block(
    coord_bin: str, script_name: str, header: str, invoke_expr: str, bin_dir: str = ""
) -> str:
    """Marker-absent append block — self-contained resolution + guarded invoke.

    `invoke_expr` runs the resolved target `$_T` via `$_PY` (e.g.
    `"$_PY" "$_T" "$@"`). Never `exec` here — an append block runs after an
    existing custom hook chain, and `exec` would replace the parent process,
    killing any hook entries that follow. Wrapped so it never disturbs the
    parent hook's exit status.

    Same claude-klabauter-bin self-heal candidate + loud-exhaustion stderr warning as
    `_shim_body` — see that function's docstring.

    The returned text starts with the START marker (`# === {header} ===`,
    from `_append_markers`) but deliberately does NOT append the `|| true`
    exit-status guard or the matching END marker itself — callers own both,
    since both must land at the very tail of the FULL appended text (guard,
    then END marker on its own line after it), and `_append_block`'s return
    value is also consumed directly (unadorned) by existing unit coverage
    that hand-appends its own `" || true"` for a standalone runtime check.
    See `_append_markers`'s docstring for why the END marker exists (AC-3:
    a future `_ensure_hook` run must be able to recognize "this is our own
    block, already installed" without guessing at its extent).
    """
    fallback = _sh_path(os.path.join("$HOME", _MARKETPLACE_SUFFIX, script_name))
    coord_bin_sh = _sh_path(coord_bin)
    claude_klabauter_cand = _resolve_claude_klabauter_bin_sh(bin_dir, script_name) if bin_dir else None
    claude_klabauter_probe = (
        f'[ -f "$_T" ] || _T="{claude_klabauter_cand}"; ' if claude_klabauter_cand else ""
    )
    start_marker, _end_marker = _append_markers(header)
    return (
        f"\n{start_marker}\n"
        "{ " + python_probe_lines("_PY") + "\n"
        f'_T="{coord_bin_sh}/{script_name}"; '
        '[ -f "$_T" ] || { _dr="$(cat "' + _DOE_ROOT_DURABLE_SH + '" 2>/dev/null || '
        'cat "' + _DOE_ROOT_LEGACY_SH + '" 2>/dev/null)"; '
        f'[ -n "$_dr" ] && [ -f "$_dr/coordinator/bin/{script_name}" ] && '
        f'_T="$_dr/coordinator/bin/{script_name}"; }}; '
        f"{claude_klabauter_probe}"
        f'[ -f "$_T" ] || _T="{fallback}"; '
        f'[ -f "$_T" ] || echo "[coordinator] WARNING: hook installed but {script_name} '
        'not found (looked in baked path, .doe-root, machine-local repos.claude_klabauter, '
        'and marketplace) — commits are NOT being auto-pushed / annotated by this hook" 1>&2; '
        '[ -n "$_PY" ] || echo "[coordinator] WARNING: hook installed but no '
        'python3/python/py interpreter found on PATH — commits are NOT being '
        'auto-pushed / annotated by this hook" 1>&2; '
        f'[ -n "$_PY" ] && [ -f "$_T" ] && {invoke_expr}; }}'
    )


# ---------------------------------------------------------------------------
# Shared file helpers.
# ---------------------------------------------------------------------------

def _atomic_write(path: str, content: str) -> None:
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    os.replace(tmp, path)


def _chmod_x(path: str) -> None:
    try:
        st = os.stat(path)
        os.chmod(path, st.st_mode | 0o111)
    except OSError:
        pass


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def _marker_in_noncomment(text: str, marker: str) -> bool:
    """True if `marker` appears on any line that is not a (whitespace-stripped) comment."""
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        if marker in line:
            return True
    return False


def _append_markers(header: str) -> "tuple[str, str]":
    """The exact start/end comment lines that bound one of OUR append blocks.

    `header` is the per-hook label ("coordinator auto-push (crash insurance)",
    "coordinator Session-Id trailer injection") — the two hooks never collide
    on this pair. The END marker is the AC-3 fix: pre-fix, an appended block
    had a start marker and no matching end marker, so a later run had no way
    to know where its OWN block stopped and a foreign hook's trailing content
    began. See `_ensure_hook`'s docstring for how both markers are used.
    """
    return f"# === {header} ===", f"# === END {header} ==="


def _has_line(text: str, exact_line: str) -> bool:
    """True if `exact_line` appears verbatim (after per-line strip) in `text`."""
    return any(line.strip() == exact_line for line in text.splitlines())


def _git_root() -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception:
        return None
    root = (out.stdout or "").strip()
    return root or None


# ---------------------------------------------------------------------------
# Generic install/repair driver.
# ---------------------------------------------------------------------------

def _ensure_hook(
    bin_dir: str,
    hook_name: str,
    script_name: str,
    marker: str,
    fresh_body: str,
    append_block: str,
    current_predicates: List[str],
    header: str,
) -> int:
    """Idempotent install/repair of a single git hook. Always returns 0.

    current_predicates: substrings that MUST all be present for the hook to be
    judged already-current (bash-free form + correct baked path + right invoke
    shape + a current interpreter probe — see AC-5 note below).

    Refuse to guess (the fix for the silent-deletion defect this function used
    to have): the "stale routed form" `_atomic_write(hook_path, fresh_body)`
    branch — a WHOLE-FILE rewrite — may fire ONLY once an append-form body has
    been positively RULED OUT via `_append_markers(header)`. Before this fix,
    `_marker_in_noncomment(body, marker)` alone gated the rewrite branch, and
    an append-form body (ours OR the user's own hook chain with our block
    spliced on) satisfies that check too — the marker is right there in the
    appended `_T="..."` line — while never satisfying `current_predicates`
    (those describe the whole-file SHIM shape: `SCRIPT="..."` + `exec
    "$_PY"`, substrings an append-form block never contains). So a SECOND
    install call on an append-form hook mis-classified it as "stale routed
    shim form" and clobbered the whole file, silently deleting a foreign
    hook chain the FIRST call had correctly preserved. Same principle as the
    sibling installer's b4b6e984 review: when the code cannot tell what shape
    it is looking at, raise/refuse rather than guess and destroy — here
    "refuse" means "chmod +x and leave the body untouched", since a hook
    installer must never fail loudly enough to block a commit.

    A LEGACY append block — our start marker present, no matching END marker
    (installed before the END-marker convention existed) — is left
    COMPLETELY alone rather than scanned for a heuristic end (blank line /
    EOF / brace-matching): guessing at a block's extent from indirect cues is
    the exact "gate-region finder" defect class the sibling review flagged,
    only in a text-splicing costume instead of a config-merging one. One loud
    stderr warning names the hook path and tells the operator to remove the
    stale block by hand; the function still returns 0.
    """
    root = _git_root()
    if not root:
        return 0

    coord_bin = _resolve_coord_bin(bin_dir, script_name)
    helper = os.path.join(coord_bin, script_name)
    if not os.path.isfile(helper):
        return 0  # broken coordinator install — not this helper's to diagnose.

    hook_path = os.path.join(root, ".git", "hooks", hook_name)

    # Hook absent → install canonical bash-free shim.
    if not os.path.exists(hook_path):
        os.makedirs(os.path.dirname(hook_path), exist_ok=True)
        _atomic_write(hook_path, fresh_body)
        _chmod_x(hook_path)
        return 0

    body = _read(hook_path)
    start_marker, end_marker = _append_markers(header)

    if _has_line(body, start_marker):
        # Append-form body (ours, possibly spliced onto a foreign chain).
        # Never eligible for the whole-file rewrite branch below — see
        # "Refuse to guess" in this function's own docstring.
        if not _has_line(body, end_marker):
            print(
                f"[git_hook_install] WARNING: {hook_path} carries a coordinator "
                f"append block ('{start_marker}') installed before the "
                "end-marker convention existed, so its extent cannot be "
                "identified safely — leaving it untouched. Remove the stale "
                "block by hand to pick up current fixes.",
                file=sys.stderr,
            )
        _chmod_x(hook_path)
        return 0

    if _marker_in_noncomment(body, marker):
        # Whole-file shim host (current, or a historical stale shape —
        # `#!/usr/bin/env bash` + bare exec, `nohup bash`, `nohup "$_PY" ...
        # &`, stale baked path). Positively ruled OUT of being an
        # append-form/foreign chain by the start-marker check above, so a
        # wholesale rewrite here can only ever replace content WE generated.
        first_line = body.splitlines()[0] if body else ""
        if first_line == "#!/bin/sh" and all(p in body for p in current_predicates):
            _chmod_x(hook_path)
            return 0
        # Stale shim form → rewrite atomically to current bash-free form.
        _atomic_write(hook_path, fresh_body)
        _chmod_x(hook_path)
        return 0

    # Marker absent (or only in a comment) → append, preserving the existing chain.
    _atomic_write(hook_path, body + append_block + "\n")
    _chmod_x(hook_path)
    return 0


# ---------------------------------------------------------------------------
# Public entrypoints.
# ---------------------------------------------------------------------------

def ensure_post_commit_hook(bin_dir: str) -> int:
    """Install/repair .git/hooks/post-commit → execs coordinator-auto-push directly.

    Synchronous exec, not backgrounded at the shell level: coordinator-auto-push
    (the Python trampoline into claude-klabauter's auto_push.py) self-detaches internally
    (os.fork() on POSIX, detached Popen respawn on Windows) when async is wanted,
    so the shim never needs shell-level `nohup … &`.
    """
    root = _git_root()
    if not root:
        return 0
    coord_bin = _resolve_coord_bin(bin_dir, "coordinator-auto-push")
    script = "coordinator-auto-push"
    header = "coordinator auto-push (crash insurance)"
    invoke = 'exec "$_PY" "$SCRIPT" "$@"'
    fresh = _shim_body(coord_bin, script, invoke, bin_dir=bin_dir)
    _start_marker, end_marker = _append_markers(header)
    append = _append_block(
        coord_bin,
        script,
        header,
        '"$_PY" "$_T" "$@"',
        bin_dir=bin_dir,
    ) + f" || true\n{end_marker}"
    current = [
        f'SCRIPT="{_sh_path(coord_bin)}/{script}"',
        'exec "$_PY"',
        "_py_resolve() {",  # AC-5: a body with the old single-line _PY= probe
        # (pre-py_probe_sh.py, no WindowsApps-stub filtering) must never be
        # certified current forever — it lacks this function entirely.
    ]
    return _ensure_hook(
        bin_dir,
        hook_name="post-commit",
        script_name=script,
        marker=script,
        fresh_body=fresh,
        append_block=append,
        current_predicates=current,
        header=header,
    )


def ensure_prepare_commit_msg_hook(bin_dir: str) -> int:
    """Install/repair .git/hooks/prepare-commit-msg → synchronous coordinator-prepare-commit-msg."""
    root = _git_root()
    if not root:
        return 0
    coord_bin = _resolve_coord_bin(bin_dir, "coordinator-prepare-commit-msg")
    script = "coordinator-prepare-commit-msg"
    header = "coordinator Session-Id trailer injection"
    invoke = 'exec "$_PY" "$SCRIPT" "$@"'
    fresh = _shim_body(coord_bin, script, invoke, bin_dir=bin_dir)
    _start_marker, end_marker = _append_markers(header)
    append = _append_block(
        coord_bin,
        script,
        header,
        '"$_PY" "$_T" "$@"',
        bin_dir=bin_dir,
    ) + f" || true\n{end_marker}"
    current = [
        f'SCRIPT="{_sh_path(coord_bin)}/{script}"',
        'exec "$_PY"',
        "_py_resolve() {",  # AC-5 — see ensure_post_commit_hook's matching note.
    ]
    return _ensure_hook(
        bin_dir,
        hook_name="prepare-commit-msg",
        script_name=script,
        marker=script,
        fresh_body=fresh,
        append_block=append,
        current_predicates=current,
        header=header,
    )
