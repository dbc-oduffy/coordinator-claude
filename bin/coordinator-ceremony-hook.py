# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""coordinator-ceremony-hook.py <canonical-ceremony-name>

Generic per-repo post-ceremony command hook. Any of the
four cadence ceremonies (/workday-start, /workday-complete, /workweek-start,
/workweek-complete) calls this shared helper at its terminal step so a
consumer repo can register its own opt-in advisory command (e.g. "publish
settled end-of-day state to an external store or dashboard") without a
bespoke terminal step per ceremony.

Spec backlink: DoE-claude:pln-generic-per-repo-post-ceremony-25af09
  § "The seam (contract pinned in C1)", § "Helper shape (C1)"
Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md (Wave E3-c)

Contract (unchanged from the bash oracle, except `main(argv)`'s own indexing
— see the 2026-07-26 note below):
  Arg 0 — canonical dashed ceremony name (workday-start | workday-complete |
          workweek-start | workweek-complete). Dashes map to underscores and
          `_post_command` is appended to derive the coordinator.local.md key
          (e.g. workday-complete -> workday_complete_post_command).
  Key lookup — `coordinator_resolve_validation_cmd.read_local_md_key`
          (bin/coordinator-resolve-validation-cmd.py), loaded under a guard
          (see § Guarded import below).
          Empty/absent key -> silent no-op, exit 0, NO output.
  Repo root — resolved via `lib.repo_identity.resolve_checked_repo_root`
          (memoized, non-spawning), falling back to cwd on UNRESOLVED.
  Execution — ARGV-ONLY (breaking change, PM-ruled 2026-08-06: full argv-mode,
          no compatibility path, no per-key opt-in). The configured value is
          parsed with `shlex.split` and exec'd directly — no `shell=True`, no
          host shell in the loop. Pipes, `&&`/`||`, redirects, globs, and
          `VAR=value` prefixes are NOT supported: a value using any of those
          either fails to parse (a clear WARN naming the argv-only contract,
          no command runs) or execs with its first token as the literal
          program name (which fails with ENOENT if that token is not an
          executable, e.g. a `VAR=value` prefix). A wrapper script is the
          supported way to get shell semantics — write the shell logic in a
          script file and point the config key at that script.
  Windows note — parsing uses `win_argv.win_safe_shlex_split`, not bare
          `shlex.split` or `posix=False` (`posix=False` is still never used
          — that would be a shell-mode fallback the argv-only ruling
          forbids, and it also regresses quoted-token handling).
          `win_argv.win_safe_shlex_split` keeps
          POSIX-mode quote-stripping/whitespace-splitting but disables
          backslash-escape processing, so a configured value with native
          backslash path separators survives intact instead of being
          mis-tokenized and then echoed back mangled in this hook's own
          diagnostics. See that helper's docstring for the prior bug.
  Redaction — the command is NEVER echoed raw. `_redact_for_diag` redacts it
          in the summary line and any WARN; `_metachar_warn` fires a light
          advisory tripwire on shell-metacharacter shapes.

Output contract (stdout):
  Exactly one line when a command was configured+run:
    Post-<ceremony> hook: ran <redacted-cmd> (exit <rc>)
  Empty stdout when no command was configured (opt-in no-op).
  All human-readable detail (the command's own stdout/stderr, WARN lines)
  streams to stderr uncaptured — never mixed into the one-line stdout contract.

Exit codes: ALWAYS 0. A non-zero command exit, a missing command, or an
  unknown ceremony arg all WARN to stderr and still exit 0 — the hook must
  NEVER fail or block the calling ceremony.

Security posture: the command is sourced ONLY from committed repo config
(coordinator.local.md) — the repo owner's own declared command, running with
full agent-shell privileges. Deliberately NO env-var override (unlike
fast_test_cmd) — a per-repo ceremony command has no legitimate env-var source
and an override would be a subprocess-injectable surface.

Guarded import: `coordinator_resolve_validation_cmd` is loaded lazily
inside `main()` under a try/except — an unimportable module (path drift,
partial live-install mirror) WARNs to stderr and returns 0, mirroring the
bash oracle's guarded `source "$_LIB" || { WARN; exit 0; }` (AC13). A
module-level unguarded import would instead crash this helper with a
traceback and non-zero exit, violating the exit-0-always contract below.
Loaded by explicit file path (`importlib.util.spec_from_file_location`), not
a bareword `import` statement — the resolver's on-disk filename is
hyphenated (`coordinator-resolve-validation-cmd.py`, a bin/-resident CLI),
and a hyphen is not a valid Python identifier character.

The `bin/lib` imports (`cc_invoke`, `win_argv.win_safe_shlex_split`), the
late `coordinator_core.win_portability.no_console_creationflags` import, and
the `repo_identity.resolve_checked_repo_root` import are loaded the same
lazy-and-guarded way, each inside its own try/except, for the identical
AC13 reason — a missing/unimportable sibling module must degrade to a
WARN+exit-0 path naming that sibling, not crash this helper at import time.
Each guard's WARN names the dependency that actually failed (bin/lib,
resolver, coordinator_core, or repo_identity) — do not collapse the wording
back to one shared string; see the inline comments at each guard.

Structural floor: the `if __name__ == "__main__":` block additionally wraps
`main()` in a broad `except Exception` that WARNs to stderr and exits 0 —
a backstop for an UNANTICIPATED escape (this session found three separate
ImportError escapes from per-import guards before this floor existed). It
does not replace the per-import guards, which produce specific, actionable
diagnostics the floor cannot.

Negative-spec: do NOT add a COORDINATOR_*_POST_COMMAND env override, do NOT
read the command from a memo/handoff/work-branch baton, and do NOT let any
error path exit non-zero — every branch below terminates via `return 0`.

2026-07-26 (arg-mismatch audit, class (c)): `main(argv)` used to read the
ceremony name from `argv[1]`, matching an `if __name__ == "__main__":
sys.exit(main(sys.argv))` guard that passed the real `sys.argv` (program
name included) straight through. Every OTHER consumes-manifest CLI's
`main(argv)` instead treats `argv` as args-only (no leading program-name
token) and strips at the `__main__`-guard call site
(`main(sys.argv[1:])`) — the convention `workday_complete.apply`/
`workweek_complete.apply`'s `_invoke_cli_main` relies on when it calls
`main_fn(list(directive_args))` in-process. Under that call, `argv[1]` was
always out of range, so `d_step10_5_post_command_hook`/
`d_step13_5_post_command_hook` (empty `args=[]`) silently resolved
`ceremony = ""`, hit `_KNOWN_CEREMONIES`'s `unknown ceremony ''` WARN
branch, and always no-opped regardless of which ceremony ran it. Reindexed
to `argv[0]` to match every sibling; `build_ceremony_close_tail` now emits
the ceremony name as the directive's one positional arg.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys

_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RVC_PATH = os.path.join(_PLUGIN_ROOT, "bin", "coordinator-resolve-validation-cmd.py")

_LIB_DIR = os.path.join(_PLUGIN_ROOT, "bin", "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

_KNOWN_CEREMONIES = (
    "workday-start",
    "workday-complete",
    "workweek-start",
    "workweek-complete",
)

# Read/redact/warn primitives now live in coordinator_resolve_validation_cmd
# — the naked-python port of the former lib/coordinator-resolve-validation-cmd.sh
# (DoE c187f5b9, 2026-07-21) this hook used to source for
# cs_read_local_md_key / _cs_metachar_warn / _cs_redact_for_diag. See
# that module's read_local_md_key / _metachar_warn / _redact_for_diag.


def main(argv: list[str]) -> int:
    ceremony = argv[0] if argv else ""

    if ceremony not in _KNOWN_CEREMONIES:
        print(
            f"[coordinator-ceremony-hook] WARN: unknown ceremony '{ceremony}' — "
            "expected one of workday-start, workday-complete, workweek-start, "
            "workweek-complete",
            file=sys.stderr,
        )
        return 0

    key = ceremony.replace("-", "_") + "_post_command"

    # Guarded import (AC13) — see module docstring § "Guarded import". Do not
    # re-flatten this back to an unguarded import.
    try:
        import cc_invoke
        from win_argv import win_safe_shlex_split

        cc_invoke.ensure_engine_on_path(__file__)
    except ImportError as exc:
        # Review: distinct message from the resolver guard below — this one
        # names the bin/lib sibling (cc_invoke/win_argv), not the resolver.
        print(
            f"[coordinator-ceremony-hook] WARN: bin/lib module unavailable "
            f"({exc}) — skipping hook",
            file=sys.stderr,
        )
        return 0

    # Guarded import (AC13) — see module docstring § "Guarded import".
    try:
        if not os.path.isfile(_RVC_PATH):
            raise ImportError(f"resolver not found at {_RVC_PATH}")
        _spec = importlib.util.spec_from_file_location(
            "coordinator_resolve_validation_cmd", _RVC_PATH
        )
        if _spec is None or _spec.loader is None:
            raise ImportError(f"could not build a module spec for {_RVC_PATH}")
        rvc = importlib.util.module_from_spec(_spec)
        # Registered before exec_module: the resolver module uses @dataclass
        # at module scope, which resolves annotation types via
        # sys.modules.get(cls.__module__) during exec — mirrors
        # coordinator_core/bash_guards/check_test_suite_invocation.py's
        # identical by-path load of this same resolver.
        sys.modules[_spec.name] = rvc
        _spec.loader.exec_module(rvc)
    except ImportError as exc:
        print(
            f"[coordinator-ceremony-hook] WARN: resolver module unavailable "
            f"({exc}) — skipping hook",
            file=sys.stderr,
        )
        return 0

    # Guarded import (AC13) — see module docstring § "Guarded import".
    try:
        from repo_identity import resolve_checked_repo_root
    except ImportError as exc:
        print(
            f"[coordinator-ceremony-hook] WARN: repo_identity module unavailable "
            f"({exc}) — skipping hook",
            file=sys.stderr,
        )
        return 0

    repo_root, verdict = resolve_checked_repo_root(explicit_root=None)
    if repo_root is None:
        repo_root = os.getcwd()
    elif verdict["verdict"] == "MISMATCH":
        # DR-277: this hook DISPATCHES a configured post-command, it does not
        # itself write into the resolved root -- warn and proceed rather than
        # refuse. UNRESOLVED never refuses either (AC4).
        print(verdict["message"], file=sys.stderr)

    cmd = rvc.read_local_md_key(repo_root, key)

    # Opt-in: key absent or empty -> silent no-op, no output.
    if not cmd:
        return 0

    rvc._metachar_warn(cmd, f"ceremony-hook:{ceremony}", caller="coordinator-ceremony-hook")
    redacted = rvc._redact_for_diag(cmd)

    # Argv-only contract (PM-ruled 2026-08-06, breaking change): no shell=True,
    # no compatibility path. win_argv.win_safe_shlex_split failure (e.g. an
    # unterminated quote) is a hard, clearly-diagnosed skip — not a crash,
    # not a silent no-op, and NOT a fallback to shell execution.
    # Review: renamed from `argv` (shadowed the function parameter of the same
    # name, a readability trap for anyone tracing argv through this function).
    # Review: switched from bare `shlex.split` to `win_argv.win_safe_shlex_split`
    # — the former silently stripped backslashes from a Windows-authored path,
    # then echoed the mangled result back in this hook's own diagnostics.
    try:
        post_argv = win_safe_shlex_split(cmd)
    except ValueError as exc:
        print(
            f"[coordinator-ceremony-hook] WARN: {ceremony} post-command ('{key}') "
            f"could not be parsed as an argv-only command ({exc}) — {key} must be a "
            "single argv-shaped command (shlex-style tokens only: no pipes, &&/||, "
            "redirects, globs, or VAR=value prefixes); use a wrapper script for "
            "shell semantics. Skipping.",
            file=sys.stderr,
        )
        return 0

    if not post_argv:
        print(
            f"[coordinator-ceremony-hook] WARN: {ceremony} post-command ('{key}') "
            f"parsed to an empty argv — {key} must be a single argv-shaped command. "
            "Skipping.",
            file=sys.stderr,
        )
        return 0

    print(f"[coordinator-ceremony-hook] {ceremony}: running: {redacted}", file=sys.stderr)

    try:
        from coordinator_core.win_portability import no_console_creationflags, run_forwarding

        # PWD env override: subprocess.run(cwd=...) chdir()s the child before
        # exec, but does NOT update an inherited $PWD env var. A shell's `pwd`
        # builtin trusts a stale-but-device/inode-matching $PWD over its own
        # getcwd() (POSIX logical-pwd semantics), so a configured command that
        # itself runs `pwd` would echo back a inherited, possibly-unresolved
        # ancestor path (e.g. a macOS /var/folders symlink source, not the
        # /private/var/folders physical target) instead of repo_root. Setting
        # $PWD explicitly closes that staleness gap.
        child_env = dict(os.environ)
        child_env["PWD"] = repo_root
        # run_forwarding, not subprocess.run: this hook is latent-reachable
        # in-process through an assembler directive whose sys.stderr is an
        # io.StringIO capture buffer with no fileno() — see
        # coordinator_core.win_portability.run_forwarding's own docstring.
        proc = run_forwarding(
            post_argv,
            cwd=repo_root,
            env=child_env,
            stdout=sys.stderr,
            stderr=sys.stderr,
            **no_console_creationflags(),
        )
        rc = proc.returncode
    except ImportError as exc:
        # Review: widened alongside the bin/lib and resolver guards above —
        # an unimportable coordinator_core (partial live-install mirror) is
        # the identical failure mode; it must degrade to WARN+0, not escape
        # main()'s ALWAYS-0 contract.
        print(
            f"[coordinator-ceremony-hook] WARN: coordinator_core module unavailable "
            f"({exc}) — skipping {ceremony} post-command: {redacted}",
            file=sys.stderr,
        )
        return 0
    except OSError as exc:
        print(
            f"[coordinator-ceremony-hook] WARN: {ceremony} post-command failed to "
            f"launch (non-fatal): {redacted} ({exc}) — {key} is argv-only: its first "
            "token must be an executable on PATH (or an absolute/relative path to "
            "one); pipes, &&/||, redirects, globs, and VAR=value prefixes are not "
            "supported. Use a wrapper script for shell semantics.",
            file=sys.stderr,
        )
        rc = 1

    if rc != 0:
        print(
            f"[coordinator-ceremony-hook] WARN: {ceremony} post-command exited "
            f"{rc} (non-fatal): {redacted}",
            file=sys.stderr,
        )

    print(f"Post-{ceremony} hook: ran {redacted} (exit {rc})")
    return 0


if __name__ == "__main__":
    # Structural floor (negative-spec): this session found THREE separate
    # ImportError escapes from main()'s per-import guards (cc_invoke/win_argv,
    # no_console_creationflags, repo_identity) before this floor existed —
    # each fixed individually, whack-a-mole. This is the backstop so a
    # fourth unanticipated escape (any exception, not just ImportError)
    # still honors the docstring's "Exit codes: ALWAYS 0" contract instead
    # of crashing the calling ceremony. It does NOT replace the per-import
    # guards above — those name the specific missing module; this can only
    # say "something failed." Do not remove the per-import guards on the
    # assumption this floor makes them redundant.
    try:
        sys.exit(main(sys.argv[1:]))
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as exc:  # noqa: BLE001 — structural floor, see comment above
        print(
            f"[coordinator-ceremony-hook] WARN: unhandled {type(exc).__name__}: {exc} "
            "— skipping hook",
            file=sys.stderr,
        )
        sys.exit(0)
