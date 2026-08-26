"""The fail-open trampoline body, loaded by `fail_open_launcher.LOADER` (Chunk A, `docs/plans/
2026-08-11-stop-the-guard-splat.md`).

Formerly lived inline inside the `-c` payload every hook registration carried (as `BOOTSTRAP`,
escaped into a single-line `exec("...")` string so it could survive `python -c` and a JSON
round-trip). Moved here as ordinary multi-line Python once `LOADER` (see
`fail_open_launcher.py`) took over the registration payload: `LOADER` pops the last `argv`
element, treats it as this file's path, and `exec()`s its text into its own globals if the file
resolves. `os` and `sys` are therefore already bound in this file's execution namespace before a
single line here runs; only `runpy`, used below, needs importing.

THE ACCEPTED REGRESSION, NAMED NOT BURIED. Today a missing *target* script fails open alone;
with this file in the seam, a missing `_hook_boot.py` itself fails EVERY hook open at once,
where before only the individually-missing script did. Taken deliberately: `LOADER`'s own
`os.path.isfile` guard still banners loudly under the same `COORDINATOR HOOK SEAM` marker
(`"bootstrap missing, hooks fail OPEN: "+path`) rather than degrading silently; this file is
infrastructure regenerated alongside every registration, not a per-guard edit surface any
individual guard change touches; and the trade buys back roughly eight display lines of
argv-echoed source ahead of every guard message in every session that trips one. A missing
`_hook_boot.py` is exactly as loud, and easier to notice precisely because it now takes every
hook down at once instead of one quiet script at a time.

Executing this module (via `exec()`, never `import`) hands off to the target hook script as a
side effect of running top to bottom. Loaded with a bare `exec(code, <caller's globals>)`, not
`import`: no `__name__`/`__file__` is available in this module's own namespace at exec time, so
no `__main__` guard or `__file__`-relative path logic belongs here.

NEGATIVE SPEC — THIS SEAM DOES NOT INJECT SITE-PACKAGES, AND MUST NOT AGAIN. Hook-path
third-party imports resolve from whichever interpreter `hooks.json`'s bare `python3` lands on;
the coordinator venv and the injector that prepended it to `sys.path` are retired. Anything a
hook needs — PyYAML transitively via `coordinator_core`, `tree_sitter` + `tree_sitter_pwsh` via
the PowerShell dialect guard — is a machine-interpreter dependency, and a missing one is an
install-surface defect to fix there, never a reason to re-add a path-mutating step here.

LEGACY REGISTRATION DRAIN. Sessions snapshot their hook registrations at startup, so a session
that booted before the injector's retirement keeps invoking registrations carrying a trailing
`_hook_venv_inject.py` argv element that no longer names a file. `LOADER` pops this file's own
path; without the drain below, that stale element would reach the target script as a spurious
argument. The drain is keyed on the filename, not on position, so it is inert for a
current-generation registration and self-retires once no pre-retirement session is left alive.

REGISTRATION-STALENESS DETECTOR, REHOMED HERE. `_detect_hook_seam_drift()` below compares this
process's snapshotted `-c` payload against the on-disk `LOADER` and banners once per session
when they differ. It carries no correctness stake of its own and it is not a guard: every
failure path is a silent no-op, deliberately inverting this seam's fail-soft-but-never-silent
rule, because a broken diagnostic must never cost a hook fire or add banner noise. Do not
"fix" its blanket `except Exception: return` into a loud failure.

COVERAGE TRADE, NAMED NOT BURIED. The detector used to live in `_hook_venv_inject.py`, chosen
because that file was the one thing every payload generation loaded — including the older
"792-byte shim" generation, whose inline payload never loads this file. Retiring the injector
retires that reach: a still-live pre-`LOADER` session no longer gets the once-per-session drift
banner. Accepted, because such a session now banners `injector skip -- missing` on EVERY hook
fire instead — strictly louder than the thing it lost, and pointing at the same fix (restart
the session). Nothing on disk can reach those sessions retroactively either way.
"""
import runpy

_LEGACY_INJECTOR_TAIL = '_hook_venv_inject.py'
if sys.argv and sys.argv[-1].endswith(_LEGACY_INJECTOR_TAIL):
    sys.argv.pop()


def _detect_hook_seam_drift():
    """Banner once per session if this process's snapshotted `-c` payload no longer matches the
    current on-disk `fail_open_launcher.LOADER`.

    NEVER RAISES. NEVER TOUCHES `sys.argv`. NEVER CHANGES THE TARGET HOOK'S EXIT CODE OR OUTPUT.
    The whole body is one `try/except Exception: return` for exactly that reason -- an unreadable
    launcher file, an unexpected `sys.orig_argv` shape, or a permission error on the sentinel must
    degrade to "did not check" rather than to a broken hook fire.
    """
    try:
        orig_argv = getattr(sys, 'orig_argv', None)
        if not orig_argv or len(orig_argv) < 4:
            return  # too old for sys.orig_argv (< 3.10), or a shape we don't recognize
        snapshotted_loader = orig_argv[2]
        script_arg = orig_argv[3]
        if not isinstance(snapshotted_loader, str) or not isinstance(script_arg, str):
            return
        if '${' in script_arg:
            return  # an unexpanded PATH token means "cannot determine", not drift.
        # NOT applied to `snapshotted_loader`: that text is the `-c` payload's own SOURCE, not a
        # path -- an older generation's real payload legitimately contains the literal substring
        # '${' as part of its own inline unexpanded-token check. Guarding on it here made the
        # detector bail before the comparison ever ran (found live). Do not re-broaden it.

        # `script_arg` is always `<plugin_root>/hooks/scripts/<script>.py` -- the one argv
        # position with production evidence of `${CLAUDE_PLUGIN_ROOT}` expansion across every
        # generation of this trampoline. Its grandparent directory is `<plugin_root>/hooks`,
        # where fail_open_launcher.py lives.
        hooks_dir = os.path.dirname(os.path.dirname(os.path.abspath(script_arg)))
        launcher_path = os.path.join(hooks_dir, 'fail_open_launcher.py')
        if not os.path.isfile(launcher_path):
            return

        import importlib.util
        spec = importlib.util.spec_from_file_location('_coord_seam_drift_probe', launcher_path)
        if spec is None or spec.loader is None:
            return
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        current_loader = getattr(mod, 'LOADER', None)
        if not isinstance(current_loader, str) or current_loader == snapshotted_loader:
            return  # current, or the source no longer defines LOADER at all -- not our call

        session_id = os.environ.get('CLAUDE_CODE_SESSION_ID')
        if not session_id:
            return  # no session key to suppress on -- skip rather than risk repeating

        # WS-2 home-resolution shape: `Path.home()` as the terminal rung, never a bare
        # `expanduser('~')`. This ladder feeds a sentinel-file WRITE, so a rung that silently
        # yields the literal '~' does not merely misreport -- it creates a stray `~` tree
        # wherever the hook happens to be cwd'd. `Path.home()` raises instead, and the
        # enclosing try/except turns that into "no banner this session", which is the correct
        # degradation for a best-effort notice.
        settings_home = os.environ.get('COORDINATOR_SETTINGS_HOME')
        if settings_home:
            home = settings_home
        else:
            from pathlib import Path
            claude_home = os.environ.get('CLAUDE_HOME') or Path.home()
            home = os.path.join(claude_home, '.coordinator-claude-settings')
        sentinel_dir = os.path.join(home, 'hook-seam-drift-notified')
        sentinel = os.path.join(sentinel_dir, session_id + '.flag')
        if os.path.isfile(sentinel):
            return  # already bannered once this session

        sys.stderr.write(
            'COORDINATOR HOOK SEAM: this session snapshotted its hook registration payload '
            'before the current fix landed -- every guard in this session is running a STALE '
            'bootstrap, not the one on disk now. Disk is already correct; this is fixed by '
            'restarting the session, not by editing anything. (Detected once per session; this '
            'banner will not repeat.)\n'
        )
        os.makedirs(sentinel_dir, exist_ok=True)
        with open(sentinel, 'w', encoding='utf-8') as _fh:
            _fh.write('1')
    except Exception:
        return


_detect_hook_seam_drift()
p = sys.argv[1]
sys.argv = sys.argv[1:]
if os.path.isfile(p):
    runpy.run_path(p, run_name='__main__')
else:
    sys.stderr.write(
        'COORDINATOR HOOK SEAM: registered hook script unreachable -- '
        'failing OPEN so tool calls keep working. missing: ' + p + ' | This is a defect, not a '
        'normal state: the registration and the script have drifted apart (deleted script, '
        'or a path that does not resolve on this host).'
    )
