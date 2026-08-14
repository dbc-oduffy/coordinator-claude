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
internally (the engine repo's auto_push.py: os.fork() on POSIX, detached Popen respawn on
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
in its appended `_T="..."` line) while never carrying whatever marks a
whole-file shim of ours — the hand-listed `current_predicates` substrings at
the time, `_hook_gen_stamp_line()` since — so a SECOND install call on an
append-form hook was
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
from coordinator_core.win_portability import is_executable, no_console_creationflags
from coordinator_core.py_probe_sh import python_probe_lines
from coordinator_core.launchable import resolve_launchable

GENERATES = []  # installs/repairs hook bodies only under .git/hooks/, which is untracked

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
    on any failure (missing binary, missing key, timeout, non-zero exit).

    `ml_bin` (from `_resolve_machine_local_bin`) is the extensionless
    `machine-local` shebang script — `CreateProcess` cannot exec it directly
    on Windows (`OSError [WinError 193] %1 is not a valid Win32 application`).
    `resolve_launchable` resolves the actually-invocable argv prefix for this
    OS (the `.cmd` twin on Windows, a bare path on POSIX where the shebang is
    authoritative) — see `coordinator_core.launchable` module docstring.

    A resolver-exec failure (OSError — could not even launch the resolver) is
    NOT the same fact as "key genuinely unset" (clean non-zero exit / empty
    stdout): the former is loudly warned to stderr so a broken machine-local
    install is distinguishable from an unset key, without raising — this sits
    on the session-boot / hook-install path and must never block."""
    if not ml_bin:
        return None
    try:
        out = subprocess.run(
            [*resolve_launchable(ml_bin), "get", key],
            capture_output=True,
            text=True,
            timeout=15,
            **no_console_creationflags(),
        )
        val = (out.stdout or "").strip()
        return val or None
    except OSError as exc:
        print(
            f"[git_hook_install] WARNING: could not execute machine-local "
            f"resolver '{ml_bin}' for key '{key}': {exc}",
            file=sys.stderr,
        )
        return None
    except Exception:
        return None


def _helper_present(dir_path: str, script_name: str) -> bool:
    """True iff `dir_path` holds an executable target for `script_name` —
    either the bare extensionless form OR its `<script_name>.py` sibling.

    Shared by every `_resolve_coord_bin` rung's isfile probe and by
    `_ensure_hook`'s helper gate, so "accept either filename form" is
    expressed once rather than copy-pasted as an `or` at each call site. A
    bin/ rename wave (2026-08) retired several extensionless scripts in
    favor of their `.py` twin — `coordinator-auto-push` is the case that
    surfaced this: only the `.py` sibling exists on disk now, so a probe
    that checks only the bare name never finds it and every rung falls
    through to the marketplace backstop.

    Still an `isfile`-only check on the TARGET, never an `isdir` on the
    containing directory — see `_resolve_coord_bin`'s docstring for why that
    distinction is load-bearing.
    """
    return os.path.isfile(os.path.join(dir_path, script_name)) or os.path.isfile(
        os.path.join(dir_path, f"{script_name}.py")
    )


def _resolve_coord_bin(bin_dir: str, script_name: str) -> str:
    """Resolve the coordinator bin dir to bake into the installed hook body.

    Post-2026-07 executable-surface migration (DoE commit b644d5a9), the
    coordinator-claude *executables* (`coordinator-auto-push`,
    `coordinator-prepare-commit-msg`, ...) live under the engine repo's
    `coordinator/bin/`, while `plugin.mirrors.coordinator-claude.source_path`
    (DoE-claude) still correctly means "where is coordinator-claude SOURCE" —
    it is consumed by the OSS-publish target resolution and must NOT be
    repointed at the engine repo. Executable resolution is a genuinely separate
    concern from source resolution, hence the dedicated rung below.

    Every rung validates the TARGET EXECUTABLE via `_helper_present`
    (`os.path.isfile` on `script_name` OR `<script_name>.py`), never just the
    directory — a rung whose directory exists but lacks BOTH forms falls
    through rather than returning a bin dir with nothing runnable in it.
    This is the fix for the 2026-07 silent-breakage: the prior isdir-only
    guards passed against an emptied-out DoE bin dir and reproduced the dead
    hook on every regeneration. The `.py`-sibling acceptance (2026-08) closes
    a second, narrower gap: a bin/ rename wave retired several extensionless
    scripts in favor of their `.py` twin, and a bare-name-only probe never
    finds the survivor, so every rung fell through to the marketplace
    backstop even though a perfectly good `.py` helper sat right there.

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
        if _helper_present(cand_bin, script_name):
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
            if _helper_present(cand_bin, script_name):
                return cand_bin

    # Rung 3: machine-local registry — engine-repo path (the
    # executable surface's post-migration home).
    claude_klabauter_root = _ml_get(ml_bin, "repos.claude_klabauter")
    if claude_klabauter_root:
        cand_bin = os.path.join(claude_klabauter_root, "coordinator", "bin")
        if _helper_present(cand_bin, script_name):
            return cand_bin

    # Rung 4: marketplace fallback (unconditional — last resort).
    return os.path.join(home, _MARKETPLACE_SUFFIX)


# ---------------------------------------------------------------------------
# Hook-body templates (bash-free: probe python3||python||py, invoke the target).
# ---------------------------------------------------------------------------

def _resolve_claude_klabauter_bin_sh(bin_dir: str, script_name: str) -> Optional[str]:
    """Best-effort, install-time-only read of `repos.claude_klabauter` for baking
    an engine-repo-bin candidate into the shell fallback chain. Returns a forward-slash
    `sh`-literal path (`<claude-klabauter>/coordinator/bin/<script_name>`) or None if the
    key is unresolvable right now — the emitted shim still probes `[ -f ... ]`
    at hook-run time regardless, so a stale/absent bake-time value only means
    that one candidate is a dead literal, not a shim that fails to run."""
    ml_bin = _resolve_machine_local_bin(bin_dir)
    claude_klabauter_root = _ml_get(ml_bin, "repos.claude_klabauter")
    if not claude_klabauter_root:
        return None
    return _sh_path(os.path.join(claude_klabauter_root, "coordinator", "bin", script_name))


# ---------------------------------------------------------------------------
# Generation stamp — currency is decided by reading this stamp back out of an
# installed body, not by matching a hand-listed set of body substrings.
#
# Prior shape (retired here): `_ensure_hook` judged an installed hook
# "already-current" by testing a hand-maintained `current_predicates` list
# (e.g. `SCRIPT="<bin>/<script>"`, `exec "$_PY"`, `_py_resolve() {`) against
# the body on disk. That test is only ever as complete as whatever a human
# remembered to add the LAST time `_shim_body` grew a new rung — and when
# they forget, an installed-but-stale hook is certified current and skipped
# forever, not merely once. Fired twice: first when the `.py`-rung predicate
# below was needed but `current_predicates` had no entry naming it at all
# (the marker comment this stamp's own history carries forward, one
# paragraph down), and again in the session that produced THIS fix, when
# 9f14ccc3d taught `_shim_body` to probe `<name>.py` at every rung without
# touching `current_predicates`, so `heal_fleet_hooks` certified all 13 stale
# fleet `post-commit` hooks "already-current" while the fleet's auto-push sat
# inert.
#
# Fix (mirrors `coordinator_core.ops.install_meta_repo_precommit_hook`'s
# `_gate_version_line()` / `_gate_is_current()`, the proven in-repo pattern
# for exactly this problem): `_shim_body` emits a single generation-stamp
# comment line, `_hook_gen_stamp_line()`. Currency is then "does the body on
# disk carry TODAY's stamp line", not "does it contain N substrings a human
# hand-listed". Bumping `_HOOK_GEN_STAMP` is now the ONLY thing a future
# `_shim_body` change needs to do for `_ensure_hook` to stop certifying the
# old shape current — see `test_git_hook_install.py`'s checksum coupling
# test, which fails if the emitted body shape changes without the bump.
#
# AC-5 history this stamp's comment carries forward (the FIRST occurrence of
# this failure class, previously recorded inline in `current_predicates`
# itself): a body generated before `_py_resolve()` existed (the old
# single-line `_PY="$(command -v python3 ...)"` probe, predating the
# WindowsApps-stub-skipping fix, 98f604a7) was certified current forever
# under a marker-substring test that never distinguished the two probe
# shapes. The stamp closes that the same way it closes the `.py`-rung gap:
# neither probe shape nor rung count is inspected directly any more, only
# whether the body carries the CURRENT stamp.
#
# Starts at 2, not 1: generation 1 is the implicit pre-stamp era above, never
# itself stamped, so no `_HOOK_GEN_STAMP = 1` exists in history to find.
_HOOK_GEN_STAMP = 2


def _hook_gen_stamp_line() -> str:
    return f"# coordinator-hook-gen: {_HOOK_GEN_STAMP}"


def _shim_body(coord_bin: str, script_name: str, invoke_line: str, bin_dir: str = "") -> str:
    """Canonical fresh-install / self-heal shim body for a hook that runs one target.

    `invoke_line` is the final line that runs the resolved target via "$_PY" —
    both hooks now `exec` synchronously at the shell level; any async self-detach
    (post-commit's coordinator-auto-push) is owned by the invoked Python, not the shim.

    The shell fallback chain (baked SCRIPT → .doe-root pointer →
    settings-home forwarder → engine-repo-bin candidate → marketplace) means
    an already-installed hook can recover a dead baked path WITHOUT waiting
    for the next `_resolve_coord_bin` regeneration — self-healing at
    hook-run time, not only at install time.

    Carries `_hook_gen_stamp_line()` immediately after the header comment
    block — see that function's own comment for why currency is decided by
    reading this stamp back, not by matching body substrings.
    """
    fallback = _sh_path(os.path.join("$HOME", _MARKETPLACE_SUFFIX, script_name))
    coord_bin_sh = _sh_path(coord_bin)
    # Settings-home forwarder rung: `${COORDINATOR_SETTINGS_HOME:-...}/bin/<name>`
    # is a generated forwarder that calls `_resolve_claude_klabauter.exec_cli("<name>")`,
    # and `exec_cli` itself probes `<target>.py` when the bare name is absent —
    # so one rung here resolves correctly across a bin/ rename without a
    # second `.py`-suffixed probe line. Placed after the .doe-root pointer
    # (an explicit, durable, install-scoped signal) and before the
    # machine-local-registry-dependent engine-repo-bin candidate: the
    # forwarder is a plain generated file present on any machine with
    # coordinator-claude installed, so it does not depend on `machine-local`
    # being resolvable at hook-run time the way the next rung does.
    settings_home_script = (
        '${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/'
        f'{script_name}'
    )
    claude_klabauter_cand = _resolve_claude_klabauter_bin_sh(bin_dir, script_name) if bin_dir else None
    claude_klabauter_probe = (
        f'[ -f "$SCRIPT" ] || SCRIPT="{claude_klabauter_cand}"\n'
        f'[ -f "$SCRIPT" ] || SCRIPT="{claude_klabauter_cand}.py"\n'
        if claude_klabauter_cand
        else ""
    )
    return (
        "#!/bin/sh\n"
        f"# coordinator {script_name} hook — installed by git_hook_install.\n"
        "# Bash-free / Windows-invocable: needs only sh (git provides it) + python — NOT bash.\n"
        "# MinGit (GitHub Desktop) ships sh + python but not bash; the python-probe skips cleanly.\n"
        "# Skips Microsoft Store App Execution Alias stubs under WindowsApps (case-\n"
        "# insensitive) -- shared with coordinator_core.ops's two precommit-hook\n"
        "# installers; see coordinator_core.py_probe_sh's module docstring.\n"
        "# Each SCRIPT rung probes the extensionless name, then <name>.py, so an\n"
        "# already-installed hook survives a bin/ rename without reinstalling.\n"
        f"{_hook_gen_stamp_line()}\n"
        f"{python_probe_lines('_PY')}\n"
        '[ -n "$_PY" ] || { echo "[coordinator] WARNING: hook installed but no '
        'python3/python/py interpreter found on PATH — commits are NOT being '
        'auto-pushed / annotated by this hook" 1>&2; exit 0; }\n'
        f'SCRIPT="{coord_bin_sh}/{script_name}"\n'
        f'[ -f "$SCRIPT" ] || SCRIPT="{coord_bin_sh}/{script_name}.py"\n'
        '[ -f "$SCRIPT" ] || { _dr="$(cat "' + _DOE_ROOT_DURABLE_SH + '" 2>/dev/null || '
        'cat "' + _DOE_ROOT_LEGACY_SH + '" 2>/dev/null)"; '
        f'[ -n "$_dr" ] && [ -f "$_dr/coordinator/bin/{script_name}" ] && '
        f'SCRIPT="$_dr/coordinator/bin/{script_name}"; '
        f'[ -n "$_dr" ] && [ ! -f "$SCRIPT" ] && [ -f "$_dr/coordinator/bin/{script_name}.py" ] && '
        f'SCRIPT="$_dr/coordinator/bin/{script_name}.py"; }}\n'
        f'[ -f "$SCRIPT" ] || SCRIPT="{settings_home_script}"\n'
        f"{claude_klabauter_probe}"
        f'[ -f "$SCRIPT" ] || SCRIPT="{fallback}"\n'
        f'[ -f "$SCRIPT" ] || SCRIPT="{fallback}.py"\n'
        '[ -f "$SCRIPT" ] || { echo "[coordinator] WARNING: hook installed but '
        f'{script_name} not found (looked in baked path, .doe-root, settings-home '
        'forwarder, machine-local repos.claude_klabauter, and marketplace) — commits '
        'are NOT being auto-pushed / annotated by this hook" 1>&2; exit 0; }\n'
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

    Same engine-repo-bin self-heal candidate + loud-exhaustion stderr warning as
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
    # Settings-home forwarder rung — matches _shim_body's chain (see that
    # function's docstring for why this rung is placed here: after the
    # .doe-root pointer, before the machine-local-registry-dependent
    # engine-repo-bin candidate).
    settings_home_script = (
        '${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/'
        f'{script_name}'
    )
    claude_klabauter_cand = _resolve_claude_klabauter_bin_sh(bin_dir, script_name) if bin_dir else None
    claude_klabauter_probe = (
        f'[ -f "$_T" ] || _T="{claude_klabauter_cand}"; [ -f "$_T" ] || _T="{claude_klabauter_cand}.py"; '
        if claude_klabauter_cand
        else ""
    )
    start_marker, _end_marker = _append_markers(header)
    return (
        f"\n{start_marker}\n"
        "{ " + python_probe_lines("_PY") + "\n"
        f'_T="{coord_bin_sh}/{script_name}"; '
        f'[ -f "$_T" ] || _T="{coord_bin_sh}/{script_name}.py"; '
        '[ -f "$_T" ] || { _dr="$(cat "' + _DOE_ROOT_DURABLE_SH + '" 2>/dev/null || '
        'cat "' + _DOE_ROOT_LEGACY_SH + '" 2>/dev/null)"; '
        f'[ -n "$_dr" ] && [ -f "$_dr/coordinator/bin/{script_name}" ] && '
        f'_T="$_dr/coordinator/bin/{script_name}"; '
        f'[ -n "$_dr" ] && [ ! -f "$_T" ] && [ -f "$_dr/coordinator/bin/{script_name}.py" ] && '
        f'_T="$_dr/coordinator/bin/{script_name}.py"; }}; '
        f'[ -f "$_T" ] || _T="{settings_home_script}"; '
        f"{claude_klabauter_probe}"
        f'[ -f "$_T" ] || _T="{fallback}"; '
        f'[ -f "$_T" ] || _T="{fallback}.py"; '
        f'[ -f "$_T" ] || echo "[coordinator] WARNING: hook installed but {script_name} '
        'not found (looked in baked path, .doe-root, settings-home forwarder, '
        'machine-local repos.claude_klabauter, and marketplace) — commits are NOT being '
        'auto-pushed / annotated by this hook" 1>&2; '
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
    """Resolve the cwd's repo root via the checked resolver
    (`repo_identity.resolve_checked_repo_root`).

    Classification: READER (AC10). This is a self-heal default (`root=None`
    in `ensure_post_commit_hook`/`ensure_prepare_commit_msg_hook`/`_ensure_hook`)
    that installs/repairs a hook into whichever repo the resolved root names —
    a hook installer "must never fail loudly enough to block a commit" (see
    this module's own docstring), so on MISMATCH — positive evidence the cwd
    names a DIFFERENT real repo than the harness anchor — this warns to
    stderr and proceeds with the resolved root anyway, per DR-277
    (docs/decisions/DR-277-guards-are-advisory-by-default-two-named.md).
    UNRESOLVED never refuses either; it just yields None, exactly as the
    predecessor's git-failure branch did.
    """
    from repo_identity import resolve_checked_repo_root

    root, verdict = resolve_checked_repo_root(explicit_root=None)
    if verdict.get("verdict") == "MISMATCH":
        print(verdict.get("message", "git_hook_install: repo-identity MISMATCH"), file=sys.stderr)
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
    header: str,
    root: Optional[str] = None,
    outcome: Optional[List[str]] = None,
) -> int:
    """Idempotent install/repair of a single git hook. Always returns 0.

    `root`: the worktree to install into. Defaults to `_git_root()` (the
    process's own cwd) — the only behaviour this function had before the
    fleet path existed, and byte-identical when the argument is omitted.
    Passing it explicitly is what lets one invocation heal a repo other than
    the one it is running inside; see `ensure_hooks_fleet` for why that
    matters.

    `outcome`: optional out-param. When supplied, exactly one classification
    string is appended describing what this call actually DID —
    `installed-absent`, `rewritten-stale`, `appended`, `already-current`,
    `left-append-form`, `left-legacy-append-form`, `skipped-no-root`, or
    `skipped-no-helper`. Deliberately an out-param rather than a changed
    return type: this function's `-> int` is a process exit code consumed by
    two entrypoints and a hook installer must never fail loudly enough to
    block a commit, so the exit-code contract stays exactly as it was.

    Why the classification exists at all (2026-08-08): a fleet audit found 12
    of 13 registered repos carrying a wrong hook — six a stale generation
    baked to a script path deleted when it moved into the engine repo, six with no
    hook at all — and NOTHING reported it, because the only signal this
    function ever emitted was "0". A caller could not distinguish "already
    correct" from "just repaired a three-week-old silent breakage", so the
    daily self-heal healed one repo and said the same nothing either way.
    Detection is the actual defect; the install was never the hard part.

    Currency is decided by the generation stamp (`_hook_gen_stamp_line()`),
    not by matching a hand-listed set of body substrings — see that
    function's own comment for the two occurrences of the substring-list
    failure class this replaces (the AC-5 stale-probe case, and the
    fleet-wide `.py`-rung miss that motivated this fix).

    Refuse to guess (the fix for the silent-deletion defect this function used
    to have): the "stale routed form" `_atomic_write(hook_path, fresh_body)`
    branch — a WHOLE-FILE rewrite — may fire ONLY once an append-form body has
    been positively RULED OUT via `_append_markers(header)`. Before this fix,
    `_marker_in_noncomment(body, marker)` alone gated the rewrite branch, and
    an append-form body (ours OR the user's own hook chain with our block
    spliced on) satisfies that check too — the marker is right there in the
    appended `_T="..."` line — while never carrying `_hook_gen_stamp_line()`
    (that stamp is only ever emitted into the whole-file SHIM shape, never
    into an append block). So a SECOND
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
    def _note(state: str) -> int:
        if outcome is not None:
            outcome.append(state)
        return 0

    if root is None:
        root = _git_root()
    if not root:
        return _note("skipped-no-root")

    coord_bin = _resolve_coord_bin(bin_dir, script_name)
    if not _helper_present(coord_bin, script_name):
        # Broken coordinator install — not this helper's to diagnose. Still
        # classified rather than silently 0: on the fleet path this is the
        # difference between "that repo is fine" and "we could not even try".
        return _note("skipped-no-helper")

    hook_path = os.path.join(root, ".git", "hooks", hook_name)

    # Hook absent → install canonical bash-free shim.
    if not os.path.exists(hook_path):
        os.makedirs(os.path.dirname(hook_path), exist_ok=True)
        _atomic_write(hook_path, fresh_body)
        _chmod_x(hook_path)
        return _note("installed-absent")

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
            return _note("left-legacy-append-form")
        _chmod_x(hook_path)
        return _note("left-append-form")

    if _marker_in_noncomment(body, marker):
        # Whole-file shim host (current, or a historical stale shape —
        # `#!/usr/bin/env bash` + bare exec, `nohup bash`, `nohup "$_PY" ...
        # &`, stale baked path). Positively ruled OUT of being an
        # append-form/foreign chain by the start-marker check above, so a
        # wholesale rewrite here can only ever replace content WE generated.
        first_line = body.splitlines()[0] if body else ""
        if first_line == "#!/bin/sh" and _has_line(body, _hook_gen_stamp_line()):
            _chmod_x(hook_path)
            return _note("already-current")
        # Stale shim form → rewrite atomically to current bash-free form.
        _atomic_write(hook_path, fresh_body)
        _chmod_x(hook_path)
        return _note("rewritten-stale")

    # Marker absent (or only in a comment) → append, preserving the existing chain.
    _atomic_write(hook_path, body + append_block + "\n")
    _chmod_x(hook_path)
    return _note("appended")


# ---------------------------------------------------------------------------
# Public entrypoints.
# ---------------------------------------------------------------------------

def ensure_post_commit_hook(
    bin_dir: str,
    root: Optional[str] = None,
    outcome: Optional[List[str]] = None,
) -> int:
    """Install/repair .git/hooks/post-commit → execs coordinator-auto-push directly.

    Synchronous exec, not backgrounded at the shell level: coordinator-auto-push
    (the Python trampoline into the engine repo's auto_push.py) self-detaches internally
    (os.fork() on POSIX, detached Popen respawn on Windows) when async is wanted,
    so the shim never needs shell-level `nohup … &`.

    `root`/`outcome` are pass-throughs to `_ensure_hook` — see its docstring.
    Both default to the pre-fleet behaviour (install into cwd's repo, report
    nothing but an exit code).
    """
    if root is None:
        root = _git_root()
    if not root:
        if outcome is not None:
            outcome.append("skipped-no-root")
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
    return _ensure_hook(
        bin_dir,
        hook_name="post-commit",
        script_name=script,
        marker=script,
        fresh_body=fresh,
        append_block=append,
        header=header,
        root=root,
        outcome=outcome,
    )


def ensure_prepare_commit_msg_hook(
    bin_dir: str,
    root: Optional[str] = None,
    outcome: Optional[List[str]] = None,
) -> int:
    """Install/repair .git/hooks/prepare-commit-msg → synchronous coordinator-prepare-commit-msg.

    `root`/`outcome` are pass-throughs to `_ensure_hook` — see its docstring.
    """
    if root is None:
        root = _git_root()
    if not root:
        if outcome is not None:
            outcome.append("skipped-no-root")
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
    return _ensure_hook(
        bin_dir,
        hook_name="prepare-commit-msg",
        script_name=script,
        marker=script,
        fresh_body=fresh,
        append_block=append,
        header=header,
        root=root,
        outcome=outcome,
    )


# ---------------------------------------------------------------------------
# Fleet driver.
# ---------------------------------------------------------------------------

#: Outcomes that mean "this repo was WRONG and we just changed it" — the set
#: the fleet report must never swallow. `already-current` is the silent case;
#: the two `left-*-append-form` states are neither drift nor repair (a foreign
#: hook chain we deliberately refuse to touch) and are reported separately.
_HEALED_OUTCOMES = frozenset({"installed-absent", "rewritten-stale", "appended"})


def _registry_repo_roots(bin_dir: str) -> List[tuple]:
    """Enumerate `(key, path)` for every `repos.*` entry set on this machine.

    Goes through the sanctioned `machine-local` CLI (`keys --prefix repos`,
    then `get` per key) rather than parsing registry TOML directly — the value
    layer is split across a tracked declarations file and a gitignored
    per-machine file, and only the CLI knows how they compose. Best-effort:
    any failure yields an empty list, because a hook installer must degrade to
    "healed nothing" rather than raise on a session-boot path.
    """
    ml_bin = _resolve_machine_local_bin(bin_dir)
    if not ml_bin:
        return []
    try:
        out = subprocess.run(
            [*resolve_launchable(ml_bin), "keys", "--prefix", "repos"],
            capture_output=True,
            text=True,
            timeout=15,
            **no_console_creationflags(),
        )
    except Exception:
        return []
    roots = []
    for line in (out.stdout or "").splitlines():
        key = line.strip()
        # `keys` prefixes advisory notes (e.g. declared-but-unset keys) to
        # stdout; only lines that are literally a repos.* key are candidates.
        if not key.startswith("repos.") or " " in key:
            continue
        val = _ml_get(ml_bin, key)
        if val:
            roots.append((key, val))
    return roots


def _classify_target(root: str) -> str:
    """Classify a registered `repos.*` path: `worktree` | `mirror` | `missing`.

    Three-way rather than the obvious boolean, because the two non-worktree
    cases deserve opposite reporting. A `mirror` (git repo, no coordinator
    surface) is a permanent, correct, expected exclusion — reporting it on a
    DAILY ceremony would print the same line every day forever, which is how
    an operator learns to scroll past the output, and this whole fix exists
    because drift hid inside output nobody read. A `missing` target (path
    gone, or never a git repo) is a broken registry entry: indistinguishable
    from a mirror under a boolean, silently never healed, and exactly the
    failure class being closed here. So: mirrors are silent, missing targets
    speak up.
    """
    if not os.path.isdir(os.path.join(root, ".git")):
        return "missing"
    return "worktree" if _is_coordinator_worktree(root) else "mirror"


def _is_coordinator_worktree(root: str) -> bool:
    """True iff `root` is a git worktree that coordinator actually commits into.

    Deliberately excludes publish-target mirrors: `repos.*` also registers
    outward OSS distribution mirrors (e.g. Claude-klabauter), which are push
    destinations, not EM working trees — installing a session-attribution hook
    into one would stamp trailers onto release commits that have no session
    behind them. The discriminator is the presence of a coordinator working
    surface (`CLAUDE.md` or `cross-repo/`), which every EM tree carries and no
    mirror does; verified against this machine's 15 registered repos, where it
    correctly admits 14 and rejects claude-klabauter alone.
    """
    if not os.path.isdir(os.path.join(root, ".git")):
        return False
    return os.path.exists(os.path.join(root, "CLAUDE.md")) or os.path.isdir(
        os.path.join(root, "cross-repo")
    )


def ensure_hooks_fleet(bin_dir: str) -> int:
    """Install/repair both coordinator hooks in EVERY registered repo, and say
    what changed. Always returns 0.

    The defect this closes (2026-08-08): the per-day self-heal added to
    `/workday-start` — itself the replacement for the boot hook killed by the
    2026-07-15 directive — calls the two `ensure_*` entrypoints once, in the
    process's own cwd. That heals whichever single repo the operator started
    the day in and no other. On a 15-repo fleet the other 14 drift
    indefinitely, and because the pre-fix installers returned a bare 0 either
    way, the heal reported success while doing nothing for them. Measured
    before this fix: 12 of 13 repos on the primary drive were wrong (six a
    stale generation baked to a script path deleted when it moved into
    the engine repo, six never installed at all), the oldest roughly three weeks
    silent.

    Why detection is the load-bearing half, not the install: every wrong repo
    HAD a plausible-looking state. A file-existence check passes on all six
    stale clones — the file was right there. A "do recent commits carry
    trailers?" check passes on all six never-installed ones, because the
    engine commit path (`commit_trailers`) stamps trailers programmatically
    and independently of the hook, leaving partial coverage that reads as
    healthy on any spot check. Only comparing installed hook CONTENT against
    the generation this installer would write distinguishes the two failure
    modes from health — which is exactly what `_ensure_hook`'s currency
    check (`_hook_gen_stamp_line()`) already computed and then threw away.
    """
    roots = _registry_repo_roots(bin_dir)
    if not roots:
        print(
            "[git_hook_install] WARNING: fleet heal found no registered repos "
            "(machine-local unavailable, or no repos.* keys set on this "
            "machine) — healed nothing. This is not the same fact as "
            "'every repo is current'.",
            file=sys.stderr,
        )
        return 0

    healed, missing = [], []
    for key, root in sorted(roots):
        kind = _classify_target(root)
        if kind == "missing":
            missing.append(f"{key} -> {root}")
            continue
        if kind == "mirror":
            continue
        for label, fn in (
            ("prepare-commit-msg", ensure_prepare_commit_msg_hook),
            ("post-commit", ensure_post_commit_hook),
        ):
            states: List[str] = []
            fn(bin_dir, root=root, outcome=states)
            state = states[0] if states else "unknown"
            if state in _HEALED_OUTCOMES:
                healed.append(f"{key} {label}: {state}")
            elif state.startswith("skipped-") or state.startswith("left-"):
                healed.append(f"{key} {label}: {state}")

    # The common case is silent — an all-current fleet prints nothing, so this
    # can sit on a daily ceremony without becoming noise the operator learns
    # to scroll past. Drift is the only thing that speaks.
    if healed:
        print(
            f"[git_hook_install] fleet heal repaired or flagged "
            f"{len(healed)} hook(s) across {len(roots)} registered repo(s):",
            file=sys.stderr,
        )
        for line in healed:
            print(f"  {line}", file=sys.stderr)
    if missing:
        print(
            f"[git_hook_install] fleet heal could not reach "
            f"{len(missing)} registered target(s) — path absent or not a git "
            f"repo, so they are silently never healed. Fix or remove the "
            f"registry entry:",
            file=sys.stderr,
        )
        for line in missing:
            print(f"  {line}", file=sys.stderr)
    return 0
