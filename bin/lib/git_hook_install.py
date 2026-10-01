"""git_hook_install — native-Python installer/repair for the coordinator git hooks.

Native-Python port (DR-059 de-bash, Windows-first) of the retired bash installer
pair coordinator-ensure-post-commit-hook / coordinator-ensure-prepare-commit-msg-hook.
Exposes two entrypoint functions, each idempotent, self-healing, and always
returning 0 (a session-boot / commit-time helper must never block).

POST-COMMIT INSTALLER REMOVED (2026-08-30, C7 of docs/plans/2026-08-30-the-
Cockpit-publish-rejoins-the-push-that-survived.md). `ensure_post_commit_hook`
and its no-op-body machinery are gone — see the gravestone comment at their
former location, above `ensure_prepare_commit_msg_hook`. The "via python,
NEVER via bash" invariant below binds `ensure_prepare_commit_msg_hook` only.

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
from coordinator_core.session.core import SESSION_ENV_PRECEDENCE
from coordinator_core.py_probe_sh import baked_python_lines
from coordinator_core.launchable import resolve_launchable
from coordinator_core.machine_resolver import merged_flat_registry as _merged_flat_registry

GENERATES = []

_MARKETPLACE_SUFFIX = ".claude/plugins/coordinator-claude/coordinator/bin"

_CONTENT_ROOT_DURABLE_SH = '${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/machine-local/.content-root'
_CONTENT_ROOT_LEGACY_SH = '$HOME/.claude/.content-root'


def _sh_path(p: str) -> str:
    return p.replace("\\", "/")


# ---------------------------------------------------------------------------
# COORD_BIN resolution — machine-local registry → .content-root pointer → marketplace.
# Faithful port of the bash ladder; every rung is best-effort (any failure falls
# through), so the marketplace default is always a valid backstop.
# ---------------------------------------------------------------------------

def _resolve_machine_local_bin(bin_dir: str) -> Optional[str]:
    cand = os.path.join(bin_dir, "machine-local")
    if is_executable(cand):
        return cand
    from shutil import which

    return which("machine-local")


#: Machine-local registry answers already read this process, keyed
#: `(ml_bin, key)`. Holds negative results too — an unset key is an answer,
#: and re-spawning to be told "unset" again costs the same as being told a
#: value.
#:
#: Why a cache and not just a hoist: the reads are loop-invariant but the loop
#: is a FLEET WALK, and the call sites are scattered across body generation
#: (`_shim_body`, `_append_block`) and resolution (`_resolve_coord_bin`,
#: `_resolve_claude_klabauter_bin_sh`) rather than gathered at the top. Hoisting would
#: mean threading a resolved value through two public entrypoints and every
#: body-template helper; caching the one primitive they all funnel through
#: covers present and future callers alike.
#:
#: Measured 2026-08-31, `_read_hook_currency` over 19 registered repos:
#: 36 spawns, 1.906s process time. One `machine-local get` is 0.606s wall /
#: 0.172s cpu, and 35 of the 36 asked for `repos.claude_klabauter` — the same
#: key, the same answer, 35 times. This is what kept `orient-assemble brief`
#: over the door's 40s ceiling; removing the fleet REPAIR did not touch it,
#: because the cost was always the walk rather than the write.
#:
#: Staleness, named rather than hidden: process-lifetime, and the warm engine
#: is long-lived, so a registry edit made after a read is not seen until the
#: engine restarts. Accepted because the registry is install-time
#: configuration and because `_ml_get` is already best-effort by contract
#: (15s timeout, any failure yields None, callers must handle None). Bust it
#: with `_ML_GET_CACHE.clear()` if a caller ever re-points the registry
#: in-process; nothing does today.
_ML_GET_CACHE: dict = {}


def _ml_get(ml_bin: Optional[str], key: str) -> Optional[str]:
    if not ml_bin:
        return None
    cache_key = (ml_bin, key)
    if cache_key in _ML_GET_CACHE:
        return _ML_GET_CACHE[cache_key]
    try:
        out = subprocess.run(
            [*resolve_launchable(ml_bin), "get", key],
            capture_output=True,
            text=True,
            timeout=15,
            **no_console_creationflags(),
        )
        val = (out.stdout or "").strip()
        # Cached on the CLEAN-EXIT path only. A failure below is a broken
        # resolver or a timeout, not an answer about the key, and caching it
        # would pin one bad moment for the life of the process.
        _ML_GET_CACHE[cache_key] = val or None
        return _ML_GET_CACHE[cache_key]
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
    return os.path.isfile(os.path.join(dir_path, script_name)) or os.path.isfile(
        os.path.join(dir_path, f"{script_name}.py")
    )


def _resolve_coord_bin(bin_dir: str, script_name: str) -> str:
    """Resolve the coordinator bin dir to bake into the installed hook body.

    Post-2026-07 executable-surface migration (doctrine-repo commit b644d5a9), the
    coordinator-claude *executables* (`coordinator-auto-push`,
    `coordinator-prepare-commit-msg`, ...) live under the engine repo's
    `coordinator/bin/`, while `plugin.mirrors.coordinator-claude.source_path`
    (the doctrine repo) still correctly means "where is coordinator-claude SOURCE" —
    it is consumed by the OSS-publish target resolution and must NOT be
    repointed at the engine repo. Executable resolution is a genuinely separate
    concern from source resolution, hence the dedicated rung below.

    Every rung validates the TARGET EXECUTABLE via `_helper_present`
    (`os.path.isfile` on `script_name` OR `<script_name>.py`), never just the
    directory — a rung whose directory exists but lacks BOTH forms falls
    through rather than returning a bin dir with nothing runnable in it.
    This is the fix for the 2026-07 silent-breakage: the prior isdir-only
    guards passed against an emptied-out doctrine-repo bin dir and reproduced the dead
    hook on every regeneration. The `.py`-sibling acceptance (2026-08) closes
    a second, narrower gap: a bin/ rename wave retired several extensionless
    scripts in favor of their `.py` twin, and a bare-name-only probe never
    finds the survivor, so every rung fell through to the marketplace
    backstop even though a perfectly good `.py` helper sat right there.

    Rung 1: `<bin_dir>/machine-local get plugin.mirrors.coordinator-claude.source_path`
            (or `machine-local` on PATH) → `<source_path>/bin/<script_name>`.
    Rung 2: `.content-root` pointer, durable-first — settings-home
            (`$HOME/.coordinator-claude-settings/machine-local/.content-root`, DR-072),
            falling back to the legacy `$HOME/.claude/.content-root` —
            → `<doe>/coordinator/bin/<script_name>`.
    Rung 3: `machine-local get repos.claude_klabauter` →
            `<claude_klabauter>/coordinator/bin/<script_name>` — the executable
            surface's actual current home on a migrated machine.
    Rung 4: the published engine mirror, resolved via
            `coordinator_core.engine_root.published_engine_mirror_path()` —
            the same shim-backed seam `resolve_claude_klabauter_root_with_class()`
            uses (`coordinator/lib/resolve-claude-klabauter/_resolve_claude_klabauter.py ::
            _resolve_published_engine`), rather than a hand-rolled
            env-then-registry read. Validates directory existence,
            `<root>/coordinator_core` presence, and a valid engine build
            stamp (C5: "no stamp, no engine") — strictly more than the
            prior hand-rolled rung validated
            (code-review 2026-09-17-codereview-sliceD-claude-klabauter-hook-resolution.md,
            F1/F2) → `<klabauter>/coordinator/bin/<script_name>`. This is
            the DISPATCH axis (DR-326: "which engine should execute?"),
            which defaults to the published mirror by ruling — see this
            function's own docstring, DR-326 axis note, below.
    Rung 5: marketplace path
            `$HOME/.claude/plugins/coordinator-claude/coordinator/bin` —
            unconditional backstop, no isfile probe (matches prior behavior;
            this is the last resort, not a candidate to skip past).

    RUNG 4 EXISTS BECAUSE RUNGS 1-3 ALL NAME AUTHORING TREES. This repo
    is where the executable surface is *authored*; the published
    `claude-klabauter` mirror is the resolved engine root on every box, and in
    an ephemeral container it is the ONLY one of the four present — there is no
    doctrine clone, no `.content-root`, no `repos.claude_klabauter`, and
    `$HOME/.claude/plugins/` is never populated because the plugin is resolved
    via `--plugin-dir`. Without this rung the ladder exhausts to a rung-5 path
    that does not exist, `_ensure_hook` finds no target and skips fail-open, and
    NOTHING stamps `Session-Id:` on a plain `git commit` for the life of that
    machine. That silence is not cosmetic: it is what makes the brightline gate
    match zero commits and report `indeterminate`, and it equally defeats
    `review_trail.write`'s foreign-session guard and `close-out-and-stamp`'s
    join — the same three consumers
    `session-start-repair-prepare-commit-msg-hook.py` names for the stale-path
    form of this failure. That repair hook cannot cover this case: it repairs a
    shim that exists, and here none was ever installed.

    DR-326 axis note. DR-326 splits "where is the engine repo?" (the
    LOCATOR axis, deliberately live-tree-only — `resolve_claude_klabauter_bin_dir()`
    is the function that answers it and correctly stays un-flipped) from
    "which engine should execute?" (the DISPATCH axis, which DR-326 rules
    defaults to the published engine mirror rather than the authoring tree
    — PM, 2026-08-19). Rung 4 answers the DISPATCH question — which coordinator
    executable a hook execs — and writes nothing into the resolved tree, so
    it takes DR-326's published-mirror-default rather than deviating from
    it; it is not the locator DR-326 keeps un-flipped, and no ratification
    is needed here. Rung 4 also has no direct `COORDINATOR_ENGINE_ROOT`
    read (unlike an earlier version of this rung): DR-326's 2026-08-19
    refinement holds that on the dispatch axis an ambient env var every
    fired session inherits is "exactly the 'oops, wrong var set' hole the
    PM vetoed", so a dispatch-axis caller does not honour it — the
    registry-backed `_resolve_published_engine()` seam is dispatch's
    correct opt-out-of-ambient-env answer instead.
    """
    home = os.path.expanduser("~")
    ml_bin = _resolve_machine_local_bin(bin_dir)

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

    settings_home = os.environ.get("COORDINATOR_SETTINGS_HOME") or os.path.join(
        home, ".coordinator-claude-settings"
    )
    for content_root_ptr in (
        os.path.join(settings_home, "machine-local", ".content-root"),
        os.path.join(home, ".claude", ".content-root"),
    ):
        try:
            with open(content_root_ptr, encoding="utf-8") as fh:
                content_root = fh.read().strip()
        except OSError:
            continue
        if content_root:
            from coordinator_data_root import content_root_for

            content = content_root_for(content_root)
            if content is not None:
                cand_bin = os.path.join(str(content), "bin")
                if _helper_present(cand_bin, script_name):
                    return cand_bin

    claude_klabauter_root = _ml_get(ml_bin, "repos.claude_klabauter")
    if claude_klabauter_root:
        cand_bin = os.path.join(claude_klabauter_root, "coordinator", "bin")
        if _helper_present(cand_bin, script_name):
            return cand_bin

    # Rung 4: the PUBLISHED engine mirror — reuses the registry-backed,
    # stamp-validated seam (`_resolve_published_engine`) rather than a
    # hand-rolled env+registry read (code-review F1/F2). No direct
    # `COORDINATOR_ENGINE_ROOT` read here: that also removes the precedence
    # self-contradiction F3 named (this rung previously ranked
    # `COORDINATOR_ENGINE_ROOT` below rungs 1-3 while every other resolver
    # in the codebase treats it as the highest rung — with the read gone,
    # this rung has no precedence opinion left to be wrong about).
    from coordinator_core.engine_root import published_engine_mirror_path

    klabauter_root = published_engine_mirror_path()
    if klabauter_root:
        cand_bin = os.path.join(klabauter_root, "coordinator", "bin")
        if _helper_present(cand_bin, script_name):
            return cand_bin

    return os.path.join(home, _MARKETPLACE_SUFFIX)


def _resolve_claude_klabauter_bin_sh(bin_dir: str, script_name: str) -> Optional[str]:
    ml_bin = _resolve_machine_local_bin(bin_dir)
    claude_klabauter_root = _ml_get(ml_bin, "repos.claude_klabauter")
    if not claude_klabauter_root:
        return None
    return _sh_path(os.path.join(claude_klabauter_root, "coordinator", "bin", script_name))


def _resolve_klabauter_bin_sh(script_name: str) -> Optional[str]:
    from coordinator_core.engine_root import published_engine_mirror_path

    klabauter_root = published_engine_mirror_path()
    if not klabauter_root:
        return None
    return _sh_path(os.path.join(klabauter_root, "coordinator", "bin", script_name))


# ---------------------------------------------------------------------------
# Generation stamp — currency is decided by reading this stamp back out of an
# installed body, not by matching a hand-listed set of body substrings.
#
# Prior shape (retired here): `_ensure_hook` judged an installed hook
# "already-current" by testing a hand-maintained `current_predicates` list
# (e.g. `SCRIPT="<bin>/<script>"`, `exec "$_PY"`, `_py_resolve() {`) against
# shell-doc-ok: those fragments are the generated sh hook's own text, matched literally.
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
#
# Bumped to 3 (2026-08-19, C7 of docs/plans/2026-08-16-one-engine-for-the-whole-box.md):
# the shell fallback chain's rung ORDER changed (settings-home forwarder now
# resolves before the baked absolute path, not after it — see `_shim_body`'s
# docstring), so a body generated under the old order must be recognized as
# stale and regenerated, not certified current by substring match alone.
#
# Bumped to 5 (2026-08-25): the interpreter rung changed shape. `_shim_body`
# and `_append_block` now interpolate `py_probe_sh.baked_python_lines` (a
# baked `sys.executable` plus an `[ -x ]` self-heal) instead of
# `python_probe_lines` (a `$PATH`-walking `_py_resolve()` inside a command
# substitution). That removes one SUBSHELL — one process — from every fire of
# `prepare-commit-msg` and `post-commit`, on the non-engine commit path where
# those hooks still run. A body generated under the walking probe must be
# recognized as stale and regenerated; a substring match cannot tell the two
# probe shapes apart, which is the gap this stamp exists to close.
#
# Bumped to 6 (2026-08-25, C1 of
# docs/plans/2026-08-25-the-engine-commits-without-re-entering-itself.md):
# `_shim_body` gained the optional `skip_env` sentinel-exit guard (post-commit
# only, ahead of the interpreter probe) — an already-installed post-commit
# hook from generation 5 has no sentinel line at all and must be recognized
# as stale so the self-heal path picks up the guard, not certified current by
# a stamp number that predates the guard's existence.
#
# Bumped to 7 (2026-08-25, C2 of the same plan): `ensure_prepare_commit_msg_
# hook` now passes its OWN `skip_env` (`COORDINATOR_TRAILERS_ALREADY_
# APPLIED`, distinct from post-commit's) -- an already-installed
# prepare-commit-msg hook from generation 6 has no sentinel line at all and
# must be recognized as stale for the same reason generation 5 was.
#
# Bumped to 11 (2026-08-30, C7 of docs/plans/2026-08-30-who-pushes-and-
# when.md): `ensure_post_commit_hook` no longer bakes an invocation of
# `coordinator-auto-push` at all -- see that function's own docstring. Every
# installed post-commit hook body predates this change and still `exec`s a
# Python interpreter to push; without the bump `_ensure_hook`'s currency
# check would certify those bodies "already-current" forever (same failure
# class the stamp itself exists to close, see the paragraph above), leaving
# the fleet pushing indefinitely. The bump forces one rewrite pass over
# every installed repo, on the next self-heal or session-boot install call,
# to the new no-op body.
#
# Gen 12 (2026-09-02): the `.exe`-only forwarder probe was a Windows-shaped
# read of a platform-neutral cutover. `forwarder_self_heal`'s
# `_cut_over_to_native_door` writes the native door image at the BARE name on
# POSIX -- there is no `.exe` sibling to find and no `-ef` pair for `_have_py`
# to discriminate on -- so the settings-home rung passed its own existence
# test and handed a Mach-O binary to `exec "$_PY"`. Every commit in every repo
# on this box died with `SyntaxError: Non-UTF-8 code starting with '\xcf'` from
# 01:57 on 2026-09-02, the moment the bin cutover landed under running
# sessions. `_NATIVE_PROBE_DEF` closes the POSIX half; the bump forces
# every installed body to be rewritten.
#
# Bumped to 15 (2026-10-01): a hook resolving past rung 1 (settings-home) now
# prints a one-line stderr NOTICE naming the winning path. Before this, only a
# total miss warned, so a hook running off rung 2-6 was indistinguishable from a
# healthy one until the last fallback also died and it failed open. Installed
# bodies carry no notice and must be rewritten to gain it.
_HOOK_GEN_STAMP = 15


def _hook_gen_stamp_line() -> str:
    return f"# coordinator-hook-gen: {_HOOK_GEN_STAMP}"


# The `.exe` probe answers the Windows half of "is the settings-home entry a
# native forwarder rather than Python source". POSIX has no extension to test:
# the door image occupies the bare name itself. Discriminate on content, since
# a coordinator-written Python CLI always opens `#!`, and a Mach-O/ELF image
# never does. `read` is a shell builtin -- no spawn, so this stays inside the
# DR-344 budget the hook pays on every commit. A file that is unreadable or
# empty answers "not native" and falls through to the interpreter chain, which
# is the pre-cutover behaviour.
#
# KNOWN RESIDUAL, ACCEPTED IN WRITING (code-review finding, 2026-09-02): the
# probe's `[ -x "$1" ]` gate is a pre-filter resting on an invariant enforced
# elsewhere (the install chain strips the exec bit from installed `.py`
# sources), not a positive test for a native image. An executable,
# shebang-less file at this name -- exec-bit set for any reason other than
# the door cutover -- is classified `_native` and `exec`'d, which fails
# ENOEXEC and can abort the commit. Two alternatives were weighed and
# rejected for this pass: (1) treating an ENOEXEC-shaped failure of the
# forwarder as "not actually native" and falling through to the interpreter
# chain conflates two different failure modes -- a real native forwarder
# that legitimately exits non-zero would ALSO fall through, silently
# resolving and running a different (possibly stale) script instead of
# surfacing the real error, and the exact non-zero-status convention for
# "wrong binary format" is not portable across dash/macOS-bash-as-sh/MSYS sh
# without an execution probe this suite cannot run; (2) a positive magic-byte
# test (Mach-O/ELF/FAT header) cannot be spelled in POSIX `sh` using only
# builtins -- `read` is line/newline-oriented and its handling of embedded
# NUL and non-text bytes is shell-dependent, so it cannot reliably assert
# specific magic bytes without a spawn (`od`/`head -c`), which the DR-344
# per-commit budget forbids on this path (called on up to eight rungs per
# hook invocation). The `[ -x ]`-plus-missing-`#!` heuristic therefore stays
# as the least-bad option; the misfire is a hard commit-block, not silent
# code execution, and is covered by
# `test_native_probe_misclassifies_an_executable_shebangless_non_native_file`
# below, which pins the accepted behaviour rather than leaving it unasserted.
_NATIVE_PROBE_DEF = (
    '_native() { [ -x "$1" ] || return 1; IFS= read -r _n1 < "$1" 2>/dev/null '
    '|| return 1; case "$_n1" in "#!"*) return 1 ;; esac; return 0; }\n'
)


_CACHE_ROOT_PROBE = (
    '_cb=""; for _d in "$HOME"/.claude/plugins/cache/coordinator-claude/coordinator/*/bin; '
    'do [ -d "$_d" ] && _cb="$_d"; done\n'
)


def _shim_body(
    coord_bin: str,
    script_name: str,
    invoke_line: str,
    bin_dir: str = "",
    skip_env: Optional[str] = None,
    skip_if_all_unset: tuple = (),
) -> str:
    """Canonical fresh-install / self-heal shim body for a hook that runs one target.

    `skip_if_all_unset` is `skip_env`'s OPPOSITE POLARITY and exists for the
    no-session backstop: presence of the named vars means there IS work to do,
    so the shim exits 0 when EVERY one of them is unset or empty. Same position
    as `skip_env` -- ahead of any interpreter resolution, `$PATH` walk, command
    substitution or subshell -- so it honours the same ordering invariant.

    GENERATED, NEVER HAND-COPIED, and that distinction is the whole reason this
    parameter is allowed to exist. `coordinator-prepare-commit-msg.py ::
    _resolve_session_id` is already a hand-mirrored copy of
    `coordinator_core.session.core.resolve_session_id`, and its docstring cites
    a prior break-class defect caused by two copies of that ladder disagreeing.
    A THIRD copy, hand-written into shell -- the one language that cannot import
    the source of truth -- was proposed and correctly REFUSED by
    claude-klabauter-59 on 2026-08-25. This is not that: the caller passes
    `SESSION_ENV_PRECEDENCE` itself, so the emitted line is a projection of the
    constant regenerated at every install, never a second statement of it. Only
    MEMBERSHIP is projected, never the ladder's precedence logic, because a
    presence test has no precedence to get wrong.

    The residual risk is staleness, not divergence: an installed body predating
    a ladder that later gains a tier. `test_session_gate_is_generated_from_the_ladder`
    converts that from silent runtime drift into a red suite, which is the
    artifact that discharges it -- the gen stamp alone would not, since
    forgetting the stamp bump is the same forgetting.

    BEHAVIOUR CHANGE, named because it is real: on a no-session commit the
    Python entrypoint used to run `_warn_hyphen_range_subject` (a pure-string
    chunk-id-subject advisory) BEFORE its own session gate. Exiting in shell
    drops that advisory there. Accepted: only a coordinator session writes a
    chunk-id subject, and such a session sets one of these vars by definition.

    `invoke_line` is the final line that runs the resolved target via "$_PY" —
    the hook `exec`s synchronously at the shell level.

    `skip_env`, when supplied, names an environment variable whose presence
    (set AND non-empty) means the caller is publishing this commit itself —
    the shim exits 0 immediately, AHEAD of `baked_python_lines`' interpreter
    probe, so a sole-publisher commit pays zero interpreter-resolution cost.
    Per-hook, not global: `ensure_prepare_commit_msg_hook` passes its own
    (`COORDINATOR_TRAILERS_ALREADY_APPLIED`). Fail-open (the whole safety
    story): absent or empty, the guard line is not even emitted, and the
    full body runs unchanged. Never generalize this into a "skip all hooks"
    flag — that is the hooksPath redirect wearing a disguise.

    The shell fallback chain (settings-home forwarder → baked SCRIPT →
    .content-root pointer → engine-repo-bin candidate → published-mirror
    candidate (F4) → marketplace) means
    an already-installed hook can recover a dead baked path WITHOUT waiting
    for the next `_resolve_coord_bin` regeneration — self-healing at
    hook-run time, not only at install time. The settings-home rung is
    checked FIRST, ahead of the baked absolute path: a baked literal
    absolute path is only ever correct on the box it was generated on,
    while the settings-home forwarder resolves via
    `$COORDINATOR_SETTINGS_HOME` (or its `$HOME` default) on any machine —
    strictly more correct wherever a checkout has moved, and no worse where
    it hasn't. Reordered 2026-08-19 (gen 3): the baked-first order left
    rungs 2+ dead code on any box where the bake-time path still happened to
    exist, masking their own staleness.

    Carries `_hook_gen_stamp_line()` immediately after the header comment
    block — see that function's own comment for why currency is decided by
    reading this stamp back, not by matching body substrings.
    """
    fallback = _sh_path(os.path.join("$HOME", _MARKETPLACE_SUFFIX, script_name))
    coord_bin_sh = _sh_path(coord_bin)
    # Settings-home forwarder rung: `${COORDINATOR_SETTINGS_HOME:-...}/bin/<name>`
    # shell-doc-ok: that rung is the generated forwarder's own parameter expansion.
    # is a generated forwarder that calls `_resolve_claude_klabauter.exec_cli("<name>")`,
    # and `exec_cli` itself probes `<target>.py` when the bare name is absent —
    # so one rung here resolves correctly across a bin/ rename without a
    # second `.py`-suffixed probe line. Placed FIRST, ahead of the baked
    # absolute path: the forwarder is a plain generated file present on any
    # machine with coordinator-claude installed and resolves via
    # `$COORDINATOR_SETTINGS_HOME` (or its `$HOME` default), so it is
    # correct on every machine a checkout might move to — unlike the baked
    # SCRIPT literal below it, which is only ever correct on the box it was
    # generated on. Reordered 2026-08-19 (gen 3) — see `_shim_body`'s own
    # docstring for why the prior baked-first order left this rung dead.
    settings_home_script = (
        '${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/'
        f'{script_name}'
    )
    claude_klabauter_cand = _resolve_claude_klabauter_bin_sh(bin_dir, script_name) if bin_dir else None
    klabauter_cand = _resolve_klabauter_bin_sh(script_name)
    claude_klabauter_probe = (
        f'_have_py "$SCRIPT" || SCRIPT="{claude_klabauter_cand}"\n'
        f'_have_py "$SCRIPT" || SCRIPT="{claude_klabauter_cand}.py"\n'
        if claude_klabauter_cand
        else ""
    ) + (
        f'_have_py "$SCRIPT" || SCRIPT="{klabauter_cand}"\n'
        f'_have_py "$SCRIPT" || SCRIPT="{klabauter_cand}.py"\n'
        if klabauter_cand
        else ""
    )
    skip_guard = (
        f'[ -n "${skip_env}" ] && exit 0\n' if skip_env else ""
    )
    session_guard = (
        '[ -z "' + "".join(f"${v}" for v in skip_if_all_unset) + '" ] && exit 0\n'
        if skip_if_all_unset
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
        "# An installed <name>.exe forwarder is exec'd DIRECTLY, before the\n"
        "# interpreter chain. Each remaining rung probes the extensionless name via\n"
        "# _have_py (never [ -f ] -- see its comment), then <name>.py, so an\n"
        "# already-installed hook survives a bin/ rename without reinstalling.\n"
        f"{_hook_gen_stamp_line()}\n"
        f"{skip_guard}"
        f"{session_guard}"
        f"{baked_python_lines('_PY')}\n"
        '[ -n "$_PY" ] || { echo "[coordinator] WARNING: hook installed but no '
        'python3/python/py interpreter found on PATH — commits are NOT being '
        'auto-pushed / annotated by this hook" 1>&2; exit 0; }\n'
        # WINDOWS TRAP, and the reason `[ -f ]` is not used below. Under git's
        # MSYS `sh`, EVERY stat predicate resolves a `.exe` sibling: with only
        # `foo.exe` on disk, `[ -f foo ]`, `-e`, `-s`, `-r`, `-x`, `ls foo` and
        # even `[ foo -ef foo.exe ]` all succeed for the bare name `foo`
        # (measured 2026-08-29). A rung guarded by `[ -f ]` therefore CLAIMS the
        # extensionless settings-home path exists the moment door_install
        # replaces those scripts with `.exe` forwarders -- the chain
        # short-circuits on a path that is not a Python file, never reaches the
        # working rungs below it, and `exec "$_PY" "$SCRIPT"` dies with
        # "can't open file". That broke prepare-commit-msg and post-commit in
        # every repo on a box after an install run; the repos that kept working
        # did so only because their FIRST rung happened to be a real `.py`.
        # `_have_py` is the same stat test plus the one discriminator that
        # survives: `-ef` is TRUE for `foo` vs `foo.exe` exactly when the bare
        # name IS the forwarder, and FALSE for a genuine extensionless script
        # (whose `.exe` does not exist). Never replace this with `[ -f ]`.
        #
        # The shebang read is the POSIX half of the same guard, and it is
        # load-bearing rather than belt-and-braces. `-ef` discriminates only
        # where a `.exe` sibling exists, so on macOS and Linux a native
        # extensionless forwarder passes every test above and the chain hands
        # a Mach-O/ELF image to `exec "$_PY" "$SCRIPT"`. The interpreter dies
        # on a SyntaxError and the hook's non-zero exit ABORTS THE COMMIT --
        # machine-wide, in every repo the fleet heal touched, reported from
        # 13 repos on one box (example-cockpit-repo-em, 2026-09-02). `_native`
        # above is not the backstop for this: it gates on `[ -x ]`, so a
        # forwarder whose executable bit is missing falls straight through to
        # here. Reading the first line with the `read` BUILTIN, never
        # `head`/`grep`, keeps this inside the DR-344 per-commit budget --
        # this function is called on up to eight rungs per hook invocation,
        # and a two-spawn body would put sixteen processes on the commit
        # path. A file that is unreadable or empty answers "not a script",
        # matching `_NATIVE_PROBE_DEF`'s own fall-through.
        '_have_py() { [ -f "$1" ] && ! [ "$1" -ef "$1.exe" ] && { IFS= read -r _h1 < "$1" 2>/dev/null || return 1; case "$_h1" in "#!"*) return 0 ;; *) return 1 ;; esac; }; }\n'
        # An installed `.exe` forwarder is the INTENDED post-install artifact.
        # Running it through an interpreter is a category error, so exec it
        # directly and never enter the interpreter chain at all.
        f'_fwd="{settings_home_script}.exe"\n'
        '[ -f "$_fwd" ] && exec "$_fwd" "$@"\n'
        # name, with no extension to test. See `_NATIVE_PROBE_DEF`.
        + _NATIVE_PROBE_DEF
        + f'_fwd="{settings_home_script}"\n'
        '_native "$_fwd" && exec "$_fwd" "$@"\n'
        f'SCRIPT="{settings_home_script}"\n'
        '_s0="$SCRIPT"\n'
        + _CACHE_ROOT_PROBE
        + f'_have_py "$SCRIPT" || SCRIPT="$_cb/{script_name}"\n'
        f'_have_py "$SCRIPT" || SCRIPT="$_cb/{script_name}.py"\n'
        f'_have_py "$SCRIPT" || SCRIPT="{coord_bin_sh}/{script_name}"\n'
        f'_have_py "$SCRIPT" || SCRIPT="{coord_bin_sh}/{script_name}.py"\n'
        '_have_py "$SCRIPT" || { _dr="$(cat "' + _CONTENT_ROOT_DURABLE_SH + '" 2>/dev/null || '
        'cat "' + _CONTENT_ROOT_LEGACY_SH + '" 2>/dev/null)"; '
        f'[ -n "$_dr" ] && _have_py "$_dr/coordinator/bin/{script_name}" && '
        f'SCRIPT="$_dr/coordinator/bin/{script_name}"; '
        f'[ -n "$_dr" ] && ! _have_py "$SCRIPT" && _have_py "$_dr/coordinator/bin/{script_name}.py" && '
        f'SCRIPT="$_dr/coordinator/bin/{script_name}.py"; }}\n'
        f"{claude_klabauter_probe}"
        f'_have_py "$SCRIPT" || SCRIPT="{fallback}"\n'
        f'_have_py "$SCRIPT" || SCRIPT="{fallback}.py"\n'
        '_have_py "$SCRIPT" || { echo "[coordinator] WARNING: hook installed but '
        f'{script_name} not found (looked in settings-home forwarder, baked path, '
        '.content-root, machine-local repos.claude_klabauter, and marketplace) — commits '
        'are NOT being auto-pushed / annotated by this hook" 1>&2; exit 0; }\n'
        # A hook that resolved past rung 1 works today and is one rename from
        # silence: the only terminal signal is the not-found WARNING above, after
        # every fallback is already dead. Name the winner instead, while it still
        # works. `echo` is a builtin -- no spawn on the commit path (DR-344).
        # Compared against the value rung 1 assigned, never against a re-expanded
        # copy of its text, so the test cannot drift from the rung it audits.
        f'[ "$SCRIPT" = "$_s0" ] || echo "[coordinator] NOTICE: {script_name} hook '
        'resolved via fallback $SCRIPT, not settings-home — install has drifted; '
        'run scripts/setup.py" 1>&2\n'
        # Every rung above tests $SCRIPT with `[ -f ]` under git's MSYS `sh`,
        # which resolves a POSIX-absolute path like /c/Users/... happily. The
        # invoke line then hands that same string to a NATIVE python.exe, which
        # has no /c mount and reads a leading slash as repo-relative, so the
        # settings-home rung can pass its own existence test and still exec a
        # path rooted at the repo drive. The two halves disagree only when
        # $HOME or $COORDINATOR_SETTINGS_HOME is itself POSIX-style, i.e. when a
        # ceremony CLI is launched from Git Bash rather than PowerShell, which
        # is why hook-annotated commits work all day and then fail inside
        # `baton-assemble apply`.
        # Pure parameter expansion, never `cygpath` in a subshell: this runs on
        # every commit, and a spawn here is a DR-344 cost the hook must not pay.
        # `/<drive>/Users/...` -> `<drive>:/Users/...` ; the MSYS single-letter
        # drive form is the only shape $HOME or $COORDINATOR_SETTINGS_HOME ever
        # takes here. The relocated drive letter stays LOWERCASE -- this line
        # spelled it uppercase until 2026-08-31 and was wrong. The expansion
        # relocates the drive letter, it does not upcase it. Harmless (Windows
        # drive letters are case-insensitive, so the native python.exe resolves
        # either), but corrected because a reader who trusts the wording writes
        # a test asserting an uppercase drive letter and
        # watches it fail against a fix that works -- which is exactly what
        # happened while `test_append_block_msys_normalisation_actually_
        # transforms_the_path` was being written.
        'case "$SCRIPT" in /?/*) _sd="${SCRIPT#/}"; '
        'SCRIPT="${_sd%%/*}:/${_sd#*/}" ;; esac\n'
        f"{invoke_line}\n"
    )


def _append_block(
    coord_bin: str, script_name: str, header: str, invoke_expr: str, bin_dir: str = ""
) -> str:
    fallback = _sh_path(os.path.join("$HOME", _MARKETPLACE_SUFFIX, script_name))
    coord_bin_sh = _sh_path(coord_bin)
    # Settings-home forwarder rung — matches `_shim_body`'s chain (see that
    # function's docstring): placed FIRST, ahead of the baked absolute path,
    # since it resolves via `$COORDINATOR_SETTINGS_HOME` and is therefore
    # correct on any machine a checkout has moved to. Reordered 2026-08-19
    # (gen 3).
    settings_home_script = (
        '${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/'
        f'{script_name}'
    )
    claude_klabauter_cand = _resolve_claude_klabauter_bin_sh(bin_dir, script_name) if bin_dir else None
    klabauter_cand = _resolve_klabauter_bin_sh(script_name)
    claude_klabauter_probe = (
        f'_have_py "$_T" || _T="{claude_klabauter_cand}"; _have_py "$_T" || _T="{claude_klabauter_cand}.py"; '
        if claude_klabauter_cand
        else ""
    ) + (
        f'_have_py "$_T" || _T="{klabauter_cand}"; _have_py "$_T" || _T="{klabauter_cand}.py"; '
        if klabauter_cand
        else ""
    )
    start_marker, _end_marker = _append_markers(header)
    return (
        f"\n{start_marker}\n"
        # CURRENCY STAMP, inside our own markers. Without it, an installed
        # append block was never refreshed: `_ensure_hook` saw both markers and
        # returned `left-append-form` unconditionally, so a repo on the append
        # path kept whatever body it was installed with forever and every later
        # fix reached only repos that had no block yet. The whole-file branch has
        # had this predicate all along; this leg simply never grew one. Emitted
        # as a `#` comment so it is inert to `sh` inside a foreign hook, and
        # compared -- never parsed -- by `_ensure_hook`.
        f"{_hook_gen_stamp_line()}\n"
        '{ _have_py() { [ -f "$1" ] && ! [ "$1" -ef "$1.exe" ] && { IFS= read -r _h1 < "$1" 2>/dev/null || return 1; case "$_h1" in "#!"*) return 0 ;; *) return 1 ;; esac; }; }\n'
        # name, with no extension to test. See `_NATIVE_PROBE_DEF`.
        + _NATIVE_PROBE_DEF
        + f'_fwd="{settings_home_script}.exe"\n'
        f'[ -f "$_fwd" ] || {{ _native "{settings_home_script}" && '
        f'_fwd="{settings_home_script}"; }}\n'
        'if [ -f "$_fwd" ]; then "$_fwd" "$@"; else\n'
        + baked_python_lines("_PY") + "\n"
        f'_T="{settings_home_script}"\n'
        '_t0="$_T"\n'
        + _CACHE_ROOT_PROBE
        + f'_have_py "$_T" || _T="$_cb/{script_name}"; '
        f'_have_py "$_T" || _T="$_cb/{script_name}.py"; '
        f'_have_py "$_T" || _T="{coord_bin_sh}/{script_name}"; '
        f'_have_py "$_T" || _T="{coord_bin_sh}/{script_name}.py"; '
        '_have_py "$_T" || { _dr="$(cat "' + _CONTENT_ROOT_DURABLE_SH + '" 2>/dev/null || '
        'cat "' + _CONTENT_ROOT_LEGACY_SH + '" 2>/dev/null)"; '
        f'[ -n "$_dr" ] && _have_py "$_dr/coordinator/bin/{script_name}" && '
        f'_T="$_dr/coordinator/bin/{script_name}"; '
        f'[ -n "$_dr" ] && ! _have_py "$_T" && _have_py "$_dr/coordinator/bin/{script_name}.py" && '
        f'_T="$_dr/coordinator/bin/{script_name}.py"; }}; '
        f"{claude_klabauter_probe}"
        f'_have_py "$_T" || _T="{fallback}"; '
        f'_have_py "$_T" || _T="{fallback}.py"; '
        f'_have_py "$_T" || echo "[coordinator] WARNING: hook installed but {script_name} '
        'not found (looked in settings-home forwarder, baked path, .content-root, '
        'machine-local repos.claude_klabauter, and marketplace) — commits are NOT being '
        'auto-pushed / annotated by this hook" 1>&2; '
        '[ -n "$_PY" ] || echo "[coordinator] WARNING: hook installed but no '
        'python3/python/py interpreter found on PATH — commits are NOT being '
        'auto-pushed / annotated by this hook" 1>&2; '
        # Same fallback notice as `_shim_body`; see the comment there. Gated on
        # `_have_py` so a total miss emits only the WARNING above, never both.
        f'_have_py "$_T" && [ "$_T" != "$_t0" ] && echo "[coordinator] NOTICE: '
        f'{script_name} hook resolved via fallback $_T, not settings-home — install '
        'has drifted; run scripts/setup.py" 1>&2; '
        'case "$_T" in /?/*) _td="${_T#/}"; '
        '_T="${_td%%/*}:/${_td#*/}" ;; esac; '
        f'[ -n "$_PY" ] && _have_py "$_T" && {invoke_expr}; fi; }}'
    )


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
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        if marker in line:
            return True
    return False


def _append_markers(header: str) -> "tuple[str, str]":
    return f"# === {header} ===", f"# === END {header} ==="


def _has_line(text: str, exact_line: str) -> bool:
    return any(line.strip() == exact_line for line in text.splitlines())


def _block_extent(text: str, start_marker: str, end_marker: str):
    """Line indices `(start, end)` of the marker-delimited block, or None.

    Exact-line matching, same predicate as `_has_line` -- a marker mentioned
    inside a string or a longer comment is not a marker.

    Returns None on every shape this cannot identify UNAMBIGUOUSLY, and that is
    the point rather than a limitation: this function's caller is about to
    rewrite bytes inside a hook file somebody else owns, and `_ensure_hook`'s
    own docstring is emphatic about refusing rather than guessing. A repeated
    start marker (two installs racing, or a hand-edit), an end marker that
    precedes its start, or either marker missing all yield None, and the caller
    leaves the file untouched and says so.
    """
    lines = text.splitlines()
    starts = [i for i, ln in enumerate(lines) if ln.strip() == start_marker]
    ends = [i for i, ln in enumerate(lines) if ln.strip() == end_marker]
    if len(starts) != 1 or len(ends) != 1:
        return None
    if ends[0] < starts[0]:
        return None
    return starts[0], ends[0]


def _replace_block(text: str, start: int, end: int, block: str) -> str:
    lines = text.splitlines(keepends=True)
    trailing_newline = text.endswith("\n")
    replacement = block.lstrip("\n").rstrip("\n") + "\n"
    out = "".join(lines[:start]) + replacement + "".join(lines[end + 1:])
    if trailing_newline and not out.endswith("\n"):
        out += "\n"
    return out


#: Stderr WARNING for the UNRESOLVED-repo-root branch, shared by `_ensure_hook`
#: and `ensure_prepare_commit_msg_hook` — both short-circuit on the same verdict
#: and owe the operator the same line. Format with `hook_name`.
#:
#: Why it is printed at all (state/bug-backlog/2026-08-25-hook-emitters-exit-0-
#: having-installed-no-*.yaml): UNRESOLVED is genuinely non-fatal on the
#: session-boot path — this module's always-returns-0 contract is unchanged, and
#: this text is diagnostics only, never part of an installed hook body — but an
#: installer that writes nothing and says nothing is indistinguishable from one
#: that succeeded. NOT the same disposition as DR-277 MISMATCH (a *different*
#: verdict, carrying `_git_root()`'s own stderr line): UNRESOLVED means the
#: checked resolver found no repo identity to gate at all, not "found one that
#: disagrees".
#:
#: Review: Kira (overengineering, F5) — was pasted verbatim into both sites.
_UNRESOLVED_ROOT_WARNING = (
    "[git_hook_install] WARNING: {hook_name} install/repair "
    "skipped this run -- the checked repo-root resolver came back "
    "UNRESOLVED (no git root at this cwd) -- no hook was written. "
    "Run this from inside the target git clone to install it."
)


def _git_root() -> Optional[str]:
    """Resolve the cwd's repo root via the checked resolver
    (`repo_identity.resolve_checked_repo_root`).

    Classification: READER (AC10). This is a self-heal default (`root=None`
    in `ensure_prepare_commit_msg_hook`/`_ensure_hook`)
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
    *,
    check_only: bool = False,
) -> int:
    """Idempotent install/repair of a single git hook. Always returns 0.

    `root`: the worktree to install into. Defaults to `_git_root()` (the
    process's own cwd) — the only behaviour this function had before the
    fleet path existed, and byte-identical when the argument is omitted.
    Passing it explicitly is what lets one invocation heal a repo other than
    the one it is running inside; see `ensure_hooks_fleet` for why that
    matters.

    `check_only`: keyword-only, default False (byte-identical behaviour to
    every existing caller). When True, this function reaches the SAME
    classification via the SAME code path (`_hook_gen_stamp_line()`, the one
    currency predicate) and returns it via `outcome` without performing the
    write (`_atomic_write`/`_chmod_x`) that classification would otherwise
    trigger. One predicate, two behaviours — see C1 of
    docs/plans/2026-08-31-orient-assemble-stops-running-a-fleet-re.md.

    `outcome`: optional out-param. When supplied, exactly one classification
    string is appended describing what this call actually DID —
    `installed-absent`, `rewritten-stale`, `appended`, `already-current`,
    `refreshed-append-form`, `left-append-form`, `left-legacy-append-form`,
    `skipped-no-root`, or
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
        # Printed independently of whether the caller collects `outcome` --
        # the same fix `skipped-no-helper` already has a few lines below; this
        # branch predates that one and never got it. Rationale and the DR-277
        # distinction live on `_UNRESOLVED_ROOT_WARNING`.
        print(
            _UNRESOLVED_ROOT_WARNING.format(hook_name=hook_name),
            file=sys.stderr,
        )
        return _note("skipped-no-root")

    coord_bin = _resolve_coord_bin(bin_dir, script_name)
    if not _helper_present(coord_bin, script_name):
        print(
            f"[git_hook_install] WARNING: {hook_name} target '{script_name}' "
            f"not found under resolved bin dir '{coord_bin}' — hook "
            "install/repair skipped this run. If a hook is already installed "
            "here, it is UNCHANGED and may still be pointing at a script "
            "that no longer exists on disk; commits may silently stop being "
            "pushed / annotated until the target is restored.",
            file=sys.stderr,
        )
        return _note("skipped-no-helper")

    git_dir = _resolve_git_hooks_dir(root)
    if git_dir is None:
        # `root` looked like a repo to whatever caller resolved it (or its
        # `.git` vanished between classification and this call) but no hooks
        # dir can be found — refuse rather than write into a path `os.path.
        # join` would happily construct under a NON-EXISTENT `.git`.
        print(
            f"[git_hook_install] WARNING: {hook_name} install/repair skipped "
            f"— no resolvable git dir under {root!r} (missing or unreadable "
            "'.git').",
            file=sys.stderr,
        )
        return _note("skipped-no-root")
    hook_path = os.path.join(git_dir, "hooks", hook_name)

    if not os.path.exists(hook_path):
        if not check_only:
            os.makedirs(os.path.dirname(hook_path), exist_ok=True)
            _atomic_write(hook_path, fresh_body)
            _chmod_x(hook_path)
        return _note("installed-absent")

    body = _read(hook_path)
    start_marker, end_marker = _append_markers(header)

    if _has_line(body, start_marker):
        if not _has_line(body, end_marker):
            print(
                f"[git_hook_install] WARNING: {hook_path} carries a coordinator "
                f"append block ('{start_marker}') installed before the "
                "end-marker convention existed, so its extent cannot be "
                "identified safely — leaving it untouched. Remove the stale "
                "block by hand to pick up current fixes.",
                file=sys.stderr,
            )
            if not check_only:
                _chmod_x(hook_path)
            return _note("left-legacy-append-form")
        extent = _block_extent(body, start_marker, end_marker)
        if extent is None:
            print(
                f"[git_hook_install] WARNING: {hook_path} carries a coordinator "
                f"append block whose extent is ambiguous (repeated or "
                f"out-of-order '{start_marker}' / '{end_marker}' lines) — "
                "leaving it untouched. Repair the markers by hand to pick up "
                "current fixes.",
                file=sys.stderr,
            )
            if not check_only:
                _chmod_x(hook_path)
            return _note("left-append-form")
        start_idx, end_idx = extent
        installed = "".join(body.splitlines(keepends=True)[start_idx:end_idx + 1])
        if _has_line(installed, _hook_gen_stamp_line()):
            if not check_only:
                _chmod_x(hook_path)
            return _note("already-current")
        if not check_only:
            _atomic_write(
                hook_path, _replace_block(body, start_idx, end_idx, append_block)
            )
            _chmod_x(hook_path)
        return _note("refreshed-append-form")

    if _marker_in_noncomment(body, marker):
        first_line = body.splitlines()[0] if body else ""
        if first_line == "#!/bin/sh" and _has_line(body, _hook_gen_stamp_line()):
            if not check_only:
                _chmod_x(hook_path)
            return _note("already-current")
        if not check_only:
            _atomic_write(hook_path, fresh_body)
            _chmod_x(hook_path)
        return _note("rewritten-stale")

    if not check_only:
        if not body.startswith("#!"):
            body = "#!/bin/sh\n" + body
        _atomic_write(hook_path, body + append_block + "\n")
        _chmod_x(hook_path)
    return _note("appended")


# GRAVESTONE (2026-08-30, C7 of docs/plans/2026-08-30-the-cockpit-publish-
# rejoins-the-push-that-survived.md): `ensure_post_commit_hook`,
# `_post_commit_noop_body`, `_post_commit_append_block`, and
# `_POST_COMMIT_NOOP_MARKER` (plus the fleet-driver row that called the
# installer) are deleted. They existed only to install/self-heal a
# permanent `#!/bin/sh` no-op body whose sole job was overwriting any
# still-pushing shim installed on a box that had not yet turned over. PM
# ruling on that date: this is the only box, and a direct check found no
# installed post-commit hook anywhere left in the pushing form — the
# overwrite target no longer exists, so the horizon is zero.
#
# CORRECTION (2026-09-01): that premise did not hold, and the two claims
# built on it were both false. A census of all 13 repos under `~/X` on this
# box found EVERY `.git/hooks/post-commit` still stamped
# `coordinator-hook-gen: 2` and still in the pushing form — none inert, none
# `exit 0`, every one of them ending `exec "$_PY" "$SCRIPT" "$@"`. The
# generation stamp was bumped to 11 precisely to force one rewrite pass over
# the fleet (see `_HOOK_GEN_STAMP`'s own note), but the installer that would
# have performed it was deleted before any session ran it, so the bump could
# never be honoured — nothing left on this box can rewrite those bodies.
#
# What the surviving hooks do now: rung 4 of their SCRIPT cascade resolves
# `${COORDINATOR_SETTINGS_HOME}/bin/coordinator-auto-push`, a forwarder that
# outlived the `coordinator-auto-push.py` C8 deleted, so every commit in
# every repo on this box exits 127 with a "missing under the resolved live-
# working-tree root — run scripts/setup.py to repair" line whose advice
# cannot work. Reported from example-cockpit-repo 2026-09-01. The forwarder half
# is retired by `install.substrate._KILLED_OP_ORPHAN_NAMES` (see that set's
# own note); the 13 installed hook bodies are UNFIXED here — they are each
# repo's own local `.git/` state, not this repo's, and rewriting a peer's hooks
# mid-commit on a box running ~50 concurrent sessions is not a change to make
# from a commit path. The rule: identified bodies are removed (with a backup)
# by `ensure_hooks_fleet`'s repairing walk via `hook_dispositions`, and never
# from a commit-path hook or an install self-heal. Do not re-derive "the
# horizon is zero" from this gravestone: measure the fleet first.


def ensure_prepare_commit_msg_hook(
    bin_dir: str,
    root: Optional[str] = None,
    outcome: Optional[List[str]] = None,
    *,
    check_only: bool = False,
) -> int:
    if root is None:
        root = _git_root()
    if not root:
        # This early return short-circuits BEFORE `_ensure_hook` is ever
        # called, so its stderr line never fires for this path; the resolver's
        # `root` classifies this as UNRESOLVED.
        print(
            _UNRESOLVED_ROOT_WARNING.format(hook_name="prepare-commit-msg"),
            file=sys.stderr,
        )
        if outcome is not None:
            outcome.append("skipped-no-root")
        return 0
    coord_bin = _resolve_coord_bin(bin_dir, "coordinator-prepare-commit-msg")
    script = "coordinator-prepare-commit-msg"
    header = "coordinator Session-Id trailer injection"
    invoke = 'exec "$_PY" "$SCRIPT" "$@"'
    fresh = _shim_body(
        coord_bin,
        script,
        invoke,
        bin_dir=bin_dir,
        skip_env="COORDINATOR_TRAILERS_ALREADY_APPLIED",
        skip_if_all_unset=SESSION_ENV_PRECEDENCE,
    )
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
        check_only=check_only,
    )


_HEALED_OUTCOMES = frozenset(
    {"installed-absent", "rewritten-stale", "appended", "refreshed-append-form"}
)

#: `repos.*` keys whose value is a CONTAINER of repos rather than a repo. They
#: share the `repos.` prefix but not its semantics, so the heal sweep must not
#: treat them as targets: `_classify_target` finds no `.git` at the container
#: path and reports `missing`, i.e. a broken registry entry, on a daily
#: ceremony -- for an entry that is correct and that no fix could ever satisfy.
#: That is the exact failure the three-way classification exists to avoid
#: (see `_classify_target`), reintroduced through the enumeration instead.
#: Excluded here rather than in `_classify_target` because these are not
#: unclassifiable repos; they are not repos at all, and never reach a verdict.
_CONTAINER_REGISTRY_KEYS = frozenset({"repos.fleet_root"})


def _registry_repo_roots(bin_dir: str) -> List[tuple]:
    """Enumerate `(key, path)` for every `repos.*` entry set on this machine.

    Zero-spawn: reads `registry.local.toml` over `registry.toml` directly
    via `coordinator_core.machine_resolver.merged_flat_registry` rather than
    a `machine-local keys --prefix repos` + one `machine-local get` per key
    CLI round-trip. `repos.*` is a confirmed root-namespace-only key (never
    a promoted concern-file namespace — see `merged_flat_registry`'s own
    docstring), so that same two-file precedence chain is sound here without
    a concern-file layer; the `MACHINE_LOCAL_<KEY>` env-override rung is not
    consulted per-key, matching the CLI's own `keys` enumeration (which
    lists declared registry keys, not env overrides — a repo can only be
    *registered* through the TOML files this reads). `bin_dir` is unused —
    kept for call-site compatibility; the prior CLI-based implementation
    needed it to locate the `machine-local` binary, this one no longer
    shells out to a binary at all. Container keys
    (`_CONTAINER_REGISTRY_KEYS`) are skipped: they carry the `repos.` prefix
    but name a directory repos live UNDER, not a repo. Best-effort: any
    failure (unreadable registry) yields an empty list, because a hook
    installer must degrade to "healed nothing" rather than raise on a
    session-boot path.
    """
    del bin_dir
    flat = _merged_flat_registry()
    roots = []
    for key, val in flat.items():
        if not key.startswith("repos."):
            continue
        if key in _CONTAINER_REGISTRY_KEYS:
            continue
        s = ("" if val is None else str(val)).strip()
        if s:
            roots.append((key, s))
    return roots


def _resolve_git_hooks_dir(root: str) -> Optional[str]:
    """The directory git actually consults for hooks in `root`, or None if
    `root` is not (or does not resolve to) a git repo.

    `root/.git` is a directory for an ordinary clone (the common case this
    function used to be the only shape of), but a `git worktree add`
    checkout — or any registry entry pointing at one — has `.git` as a FILE
    containing `gitdir: <path>`, one level of indirection `os.path.join(root,
    ".git", "hooks", ...)` cannot see through. `_classify_target` used to
    treat that shape as `missing` (an `isdir` check on `.git` fails on a
    file), silently EXCLUDING such a repo from the fleet enumeration
    entirely — one of the three candidate causes named for claude-klabauter
    coordinator-content-repo#85 row 9 ("a repo skipped by the fleet enumeration").

    Hooks are not per-worktree: git stores them in the repository's COMMON
    dir (shared across every worktree), found by following the worktree
    gitdir's own `commondir` file (relative to that worktree gitdir) when
    present. Absent `commondir`, the worktree gitdir IS already the common
    dir (matches an ordinary non-worktree clone, where `root/.git` plays
    both roles).
    """
    git_entry = os.path.join(root, ".git")
    if os.path.isdir(git_entry):
        return git_entry
    if not os.path.isfile(git_entry):
        return None
    text = _read(git_entry).strip()
    if not text.startswith("gitdir:"):
        return None
    gitdir = text[len("gitdir:"):].strip()
    if not os.path.isabs(gitdir):
        gitdir = os.path.normpath(os.path.join(root, gitdir))
    commondir_file = os.path.join(gitdir, "commondir")
    if os.path.isfile(commondir_file):
        commondir = _read(commondir_file).strip()
        if commondir:
            if not os.path.isabs(commondir):
                commondir = os.path.normpath(os.path.join(gitdir, commondir))
            return commondir
    return gitdir


def _classify_target(root: str) -> str:
    if _resolve_git_hooks_dir(root) is None:
        return "missing"
    return "worktree" if _is_coordinator_worktree(root) else "mirror"


def _is_coordinator_worktree(root: str) -> bool:
    if _resolve_git_hooks_dir(root) is None:
        return False
    return (
        os.path.exists(os.path.join(root, "CLAUDE.md"))
        or os.path.isdir(os.path.join(root, "state", "cross-repo"))
        or os.path.isdir(os.path.join(root, "cross-repo"))
    )


_COORDINATOR_HOOK_MARKERS = ("coordinator-prepare-commit-msg", "coordinator-hook-gen", "coordinator-claude")


def _hook_points_at_coordinator(root: str, hook_name: str) -> bool:
    """Whether ``root``'s installed ``hook_name`` body names a coordinator path."""
    git_dir = _resolve_git_hooks_dir(root)
    if git_dir is None:
        return False
    hook_path = os.path.join(git_dir, "hooks", hook_name)
    if not os.path.isfile(hook_path):
        return False
    body = _read(hook_path)
    return any(m in body for m in _COORDINATOR_HOOK_MARKERS)


def _scan_dirs() -> List[str]:
    """Directories whose immediate children are candidate repos: each
    ``repos.*`` container key's value, plus the parent of every registered repo."""
    flat = _merged_flat_registry()
    dirs = []
    for key in _CONTAINER_REGISTRY_KEYS:
        val = ("" if flat.get(key) is None else str(flat.get(key))).strip()
        if val:
            dirs.append(val)
    return dirs


def _unregistered_hooked_repos(registered: "set[str]") -> List[tuple]:
    """Repos outside the registry whose prepare-commit-msg hook names a
    coordinator path: children of the container dirs and siblings of registered
    repos. Bounded to one directory level."""
    parents = {os.path.dirname(os.path.normpath(r)) for r in registered} | set(_scan_dirs())
    seen = {os.path.normpath(r) for r in registered}
    found: List[tuple] = []
    for parent in sorted(p for p in parents if p and os.path.isdir(p)):
        try:
            names = sorted(os.listdir(parent))
        except OSError:
            continue
        for name in names:
            child = os.path.normpath(os.path.join(parent, name))
            if child in seen:
                continue
            seen.add(child)
            if _hook_points_at_coordinator(child, "prepare-commit-msg"):
                found.append((f"scan:{name}", child))
    return found


def _apply_dispositions(
    key: str,
    root: str,
    check_only: bool,
    stale: List[str],
    healed: List[str],
    errored: List[str],
) -> None:
    """Run the hook disposition table over one clone. Repairing-walk only
    (`check_only=False`) ever mutates; one bad clone never aborts the walk."""
    try:
        from coordinator_core.git import hook_dispositions  # noqa: PLC0415

        verdicts = hook_dispositions.apply_repo(root, check_only=check_only)
    except Exception as exc:  # noqa: BLE001
        errored.append(f"{key} hook-disposition: {type(exc).__name__}: {exc}")
        return
    for entry_id, hook_name, verdict in verdicts:
        if verdict == "stale":
            stale.append(
                f"coordinator-hook-disposition: stale {key} {hook_name} {entry_id}"
            )
        elif verdict in ("removed", "block-excised", "replaced"):
            healed.append(f"{key} {hook_name}: {verdict} ({entry_id})")
        elif verdict in ("busy", "refused-no-backup"):
            errored.append(f"{key} {hook_name}: {verdict} ({entry_id})")


def ensure_hooks_fleet(
    bin_dir: str, *, check_only: bool = False, strict: bool = False
) -> int:
    roots = _registry_repo_roots(bin_dir)
    roots = roots + _unregistered_hooked_repos({r for _, r in roots})
    if not roots:
        print(
            "[git_hook_install] WARNING: fleet heal found no registered repos "
            "(machine-local registry unreadable, or no repos.* keys set on "
            "this machine) — healed nothing. This is not the same fact as "
            "'every repo is current'.",
            file=sys.stderr,
        )
        return 0

    healed, missing, errored = [], [], []
    stale: list[str] = []
    owned_missing: list[str] = []
    for key, root in sorted(roots):
        kind = _classify_target(root)
        if kind == "missing":
            missing.append(f"{key} -> {root}")
            continue
        _apply_dispositions(key, root, check_only, stale, healed, errored)
        if kind == "mirror" and not _hook_points_at_coordinator(root, "prepare-commit-msg"):
            continue
        for label, fn in (
            ("prepare-commit-msg", ensure_prepare_commit_msg_hook),
        ):
            states: List[str] = []
            try:
                fn(bin_dir, root=root, outcome=states, check_only=check_only)
            except Exception as exc:  # noqa: BLE001 - one bad repo must not
                errored.append(f"{key} {label}: {type(exc).__name__}: {exc}")
                if not check_only:
                    owned_missing.append(f"{key} {label}: install raised ({exc})")
                continue
            state = states[0] if states else "unknown"
            if state in _HEALED_OUTCOMES:
                healed.append(f"{key} {label}: {state}")
            elif state.startswith("skipped-") or state.startswith("left-"):
                healed.append(f"{key} {label}: {state}")
            if not check_only:
                git_dir = _resolve_git_hooks_dir(root)
                hook_path = os.path.join(git_dir, "hooks", label) if git_dir else None
                # `os.access(..., X_OK)`, NOT `win_portability.is_executable`:
                # that helper's Windows rung answers "would CreateProcess
                # launch this directly" (PATHEXT-suffixed-sibling test for an
                landed = bool(hook_path and os.path.isfile(hook_path))
                if os.name != "nt":
                    landed = landed and os.access(hook_path, os.X_OK)
                if not landed:
                    owned_missing.append(f"{key} {label}: not present/executable after install")

    for line in stale:
        print(line, file=sys.stderr)
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
    if errored:
        print(
            f"[git_hook_install] fleet heal hit {len(errored)} unexpected "
            "error(s) installing a hook — that repo's hook state is "
            "UNKNOWN, not healed:",
            file=sys.stderr,
        )
        for line in errored:
            print(f"  {line}", file=sys.stderr)
    if owned_missing:
        print(
            f"[git_hook_install] fleet heal owns {len(owned_missing)} hook(s) "
            "that are still absent or non-executable after the attempt "
            "(worktree-classified repos only — a mirror's absence is by "
            "design, not counted here):",
            file=sys.stderr,
        )
        for line in owned_missing:
            print(f"  {line}", file=sys.stderr)
        if strict:
            return 1
    return 0
