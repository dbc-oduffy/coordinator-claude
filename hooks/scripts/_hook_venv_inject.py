"""Venv site-packages injector body, loaded by `fail_open_launcher.BOOTSTRAP` (C1).

Formerly lived inside `BOOTSTRAP` itself as an escaped `exec("...")` string; moved here as
ordinary Python source so the 6819-byte payload no longer travels inline in every
`hooks.json` registration (spike verdict: `docs/research/spike-verdicts/2026-08-11-hook-
bootstrap-file-loaded-injector.md`, AST-diff clean, zero semantic divergence from
un-escaping). `BOOTSTRAP` reads this file's path from its own last `argv` slot, `exec()`s
its text inside a bare `try/except`, and treats "file missing", "raised", or "path arrived
with an unexpanded `${` token" identically to today's "no ladder rung resolved": a
`COORDINATOR HOOK SEAM` banner naming the cause, never silent, and the hook still runs.

Executing this module (via `exec(compile(...), ...)`, never `import`) resolves and injects
the coordinator venv's `site-packages` immediately, as a side effect of the final
`_coord_hook_inject()` call at the bottom of this file — mirroring the un-escaped source's
own trailing `_coord_hook_inject()` call.

SITE-PACKAGES INJECTION (A5, A15, A16). Before the target script's own imports run,
BOOTSTRAP resolves the coordinator venv's `site-packages` via a three-rung ladder --
`COORDINATOR_HOOK_SITE_PACKAGES` env, then an installer-written pointer file under
`<settings-home>/bin/hook-sitepackages.txt`, then a layout-derived path under `<settings-
home>/.coordinator-venv` -- version-gates it against `pyvenv.cfg`'s `version` key (declining
on a `(major, minor)` mismatch, since three of the venv's distributions are C-extension-only
and raise ImportError on an ABI-tagged mismatch rather than degrading gracefully), and
injects it via `site.addsitedir`, promoting the venv ahead of the host on `sys.path`.
`site.addsitedir`, never raw `sys.path.insert`: the venv carries a live
`__editable__.coordinator_whoami-0.1.0.pth`, and raw insertion does not process `.pth` files
-- `coordinator_whoami` fails to import under raw insertion while it succeeds under
`addsitedir` (verified live on this host: see the C0 chunk's dispatch record). A prior spike
record's Q3 finding -- "raw `sys.path` insertion is the only mechanism available" -- is
WRONG; that inference skipped `site.addsitedir` and the spike's own probe only passed
because it called `site.main()`, which masked the `.pth` gap. `site.addsitedir` deliberately
does NOT change `sys.prefix`, so no code here or elsewhere may assert `sys.prefix == venv`
-- that is by design, not a bug to fix. No `PYTHONPATH` arm: an env var is inherited
transitively by every Python grandchild of every hook fire, outside the reach of the
`pyvenv.cfg` version gate, and it cannot carry a `.pth`-delivered editable install any more
than raw `sys.path` insertion can -- rejected deliberately, not an oversight to "fix" by
adding one back. PRECEDENCE. `site.addsitedir` is a no-op for a directory already present on
`sys.path`, so hoisting only the newly-added entries leaves the venv behind the host in
exactly that case -- the resolved directory was already on `sys.path` (e.g. via a stray
`PYTHONPATH` or an earlier `site` pass) but at the wrong position. BOOTSTRAP promotes the
resolved `site-packages` path itself to the front alongside the newly-added entries when it
was already present in `sys.path` before injection, preserving the relative order of the
promoted set and of the untouched remainder -- a reorder after `addsitedir` runs, not a
replacement of the injection mechanism. The membership test normalizes both sides
(`os.path.normcase(os.path.normpath(...))`) rather than comparing raw strings, so a
differently-spelled duplicate already on `sys.path` (trailing separator, a `..`-relative
segment, or case on a case-insensitive filesystem) still counts as "already present" and
still gets promoted, and the un-normalized duplicate left behind is dropped from the
remainder rather than trailing the promoted copy. TOCTOU. `_validate_pointer` checks the
pointer target once and returns a boolean; the caller then uses the original (unvalidated-
at-use-time) string as `sp` later, when `site.addsitedir(sp)` actually runs. Between those
two points the directory -- or a symlink/junction component of its path -- could be swapped
for one that no longer satisfies containment or writability. This check-then-use race is
accepted, not closed: the window is narrow (requires write access inside settings home
between two syscalls of a single hook fire) and closing it is not worth the complexity given
this module's fail-soft ethos. `_validate_pointer`'s `True` is a point-in-time result, not a
persisted guarantee. POINTER-FILE TRUST BOUNDARY. `hook-sitepackages.txt` is not trusted
content merely because it is installer-written: a `.pth` file's `import` lines execute
arbitrary code at interpreter startup, so whatever this pointer resolves to gets code-
execution rights at every hook fire. Before `addsitedir` ever sees the pointer's value,
BOOTSTRAP requires it to be absolute, to exist as a directory, to resolve (via
`os.path.realpath`, case-folded on `win32`) as a true path-segment under the settings home
-- prefix-plus-separator containment, not a bare string `startswith` -- and, on POSIX only,
to be free of group/world-write bits (`st_mode & 0o022`); the writability leg is skipped on
`win32`, where the whole settings home is owned and writable by the invoking user by
construction, so the check would reject every valid path rather than catch anything -- on
`win32` this boundary therefore distinguishes in-tree from out-of-tree only, never attacker-
writable from owner-writable. A pointer failing any leg is not trusted silently and does not
abort resolution either: it is named in a `_seam` banner (which check failed, and the
resolved path) and resolution falls through to the layout rung. The
`COORDINATOR_HOOK_SITE_PACKAGES` env rung gets only an absolute/isdir sanity check, never
the root-containment or writability legs -- but this is NOT a meaningfully weaker gate,
because rung 2's containment check is validated against `home`, and `home` itself comes from
`COORDINATOR_SETTINGS_HOME`, read unvalidated from the same environment. Rung 2 therefore
checks an attacker-supplied path against an attacker-supplied root: anyone who can set one
env var can set the other, point `COORDINATOR_SETTINGS_HOME` at a directory they control,
and get the identical `addsitedir` + `sys.executable` repoint through rung 2 instead of rung
1. Hardening rung 1 alone buys nothing against that actor. The real fix is anchoring
containment to a non-env root (an install receipt, e.g.) rather than
`COORDINATOR_SETTINGS_HOME` -- recorded as unbuilt option (d) in state/bug-
backlog/2026-08-11-hook-venv-env-rung-skips-the-trust-boundary.yaml, not yet built because
it collides with `COORDINATOR_SETTINGS_HOME`'s documented role as the sanctioned
XDG/sandbox/CI escape hatch (`coordinator/docs/wiki/machine-local-registry.md`). Once
resolved and version-checked, BOOTSTRAP also repoints `sys.executable` at the venv
interpreter (gated independently on `os.path.isfile`, since a resolved site-packages path
does not prove the interpreter file still exists), exporting the pre-mutation value as
`COORDINATOR_HOST_PYTHON` and the resolved interpreter as `COORDINATOR_HOOK_PYTHON` so
non-`sys.executable` descendants can still reach it. Every failure mode here fails soft
(never raises) but never silent: a `COORDINATOR HOOK SEAM` banner to stderr distinguishes
"missing" (no ladder rung resolved), "rejected" (a pointer-file or env value that failed
validation), "stale/incompatible" (a path resolved but the version check declined it), and
"resolved-but-interpreter-missing" (site-packages injection succeeded but no candidate
interpreter file exists on disk). Successful injection (packages AND interpreter both
resolved) is silent, matching the banner-free-success discipline of the rest of this module.

Loaded via a bare `exec(code, {})`, not `import` — no `__name__`/`__file__` available in this
module's namespace; do not add a `__main__` guard or `__file__`-relative path logic here.

REGISTRATION-STALENESS DETECTOR (rides here, not in `_hook_boot.py`). The harness snapshots a
session's hook registrations at startup; a session that booted before `fail_open_launcher.LOADER`
last changed keeps executing whatever `-c` payload it snapshotted for its whole life, even after
the on-disk source is fixed. `_detect_hook_seam_drift()` below compares that snapshotted payload
against the current on-disk `LOADER` and banners once if they differ. OFF-PURPOSE PLACEMENT,
DELIBERATE: this file's job is venv injection, not registration bookkeeping, but it is the ONE
file loaded by every generation of the trampoline that loads any file at all from the `-c`
payload -- both the pre-`LOADER` "792-byte shim" generation (`BOOTSTRAP`, ending
`..., INJECTOR_TOKEN]`) and the current `LOADER` generation (ending `..., INJECTOR_TOKEN,
BOOTSTRAP_PATH]`) `exec()` this file by name. `_hook_boot.py` is newer than both and is only
reachable from the current generation, so a detector placed there would miss the shim generation
entirely -- the whole point of this detector is to reach sessions that are ALREADY stale.

COVERAGE, STATED EXACTLY, NOT ROUNDED UP. Of the three payload generations that have existed:
the "792-byte shim" (`BOOTSTRAP`, gen2, `596e32b78`..`5545a7d93`) is the one this detector
actually protects TODAY -- any live session still on it will banner on its next hook fire. The
current `LOADER` generation (gen3) is, by definition, not stale against itself right now; this
same mechanism is what will catch IT going stale the next time `LOADER` changes and a gen3
session outlives that change. The oldest, fully-inline `BOOTSTRAP` generation (gen1, predates
`596e32b78`, predates this file's own existence as a split-out module) is unreachable by ANY
placement: its payload never loads a second file at all, so there is no seam here or anywhere
else to hang a detector on. That gap is accepted, not solved -- see the module-level docstring's
own "nothing on disk can be edited to reach them retroactively" framing. Do not describe this as
"two of three generations covered" -- gen3 self-comparing to itself is not coverage of a stale
gen3, it is the trivial not-yet-stale case; only gen2 is presently, actually protected.

THIS IS THE ONE PLACE THIS MODULE'S FAIL-SOFT-NEVER-SILENT RULE INVERTS. Every other failure
path in this file banners loudly because a silently-skipped venv injection is a real defect
worth seeing. `_detect_hook_seam_drift()` is not a guard and carries no correctness stake of its
own -- it is a cosmetic/diagnostic leg riding inside the injection path purely for placement
convenience. A later reader must not "fix" its blanket `except Exception: return` into a loud
failure to match the rest of the file: doing so would risk banner noise or a delayed/broken hook
fire over a detector whose only job is to be informative when it can cheaply be, and invisible
otherwise.
"""
import glob
import os
import site
import sys


def _coord_hook_inject():
    def _seam(msg):
        sys.stderr.write('COORDINATOR HOOK SEAM: ' + msg + chr(10))

    def _settings_home():
        v = os.environ.get('COORDINATOR_SETTINGS_HOME')
        if v:
            return v
        claude_home = os.environ.get('CLAUDE_HOME')
        if claude_home and os.path.isabs(claude_home):
            base = claude_home
        else:
            home = os.environ.get('HOME')
            if home and os.path.isabs(home):
                base = home
            else:
                userprofile = os.environ.get('USERPROFILE')
                if userprofile and os.path.isabs(userprofile):
                    base = userprofile
                else:
                    base = os.path.expanduser('~')
        return os.path.join(base, '.coordinator-claude-settings')

    def _validate_pointer(v, home):
        if not os.path.isabs(v):
            return False, 'not an absolute path'
        if not os.path.isdir(v):
            return False, 'does not exist / not a directory'
        rv = os.path.realpath(v)
        rh = os.path.realpath(home)
        rv_c = rv.lower() if sys.platform == 'win32' else rv
        rh_c = rh.lower() if sys.platform == 'win32' else rh
        if rv_c != rh_c and not rv_c.startswith(rh_c + os.sep):
            return False, 'not a path-segment under the settings home ' + rh
        if sys.platform != 'win32':
            try:
                mode = os.stat(rv).st_mode
            except Exception:
                return False, 'could not stat for writability check'
            if mode & 0o022:
                return False, 'directory is group- or world-writable'
        return True, None

    def _resolve_site_packages():
        v = os.environ.get('COORDINATOR_HOOK_SITE_PACKAGES')
        if v != '' and v is not None:
            if os.path.isabs(v) and os.path.isdir(v):
                return v, 'env'
            _seam(
                'COORDINATOR_HOOK_SITE_PACKAGES rejected -- ' + v + ' is not an absolute, '
                'existing directory; falling through to the pointer-file rung.'
            )
        home = _settings_home()
        ptr = os.path.join(home, 'bin', 'hook-sitepackages.txt')
        ptr_mode_ok = True
        if sys.platform != 'win32' and os.path.isfile(ptr):
            try:
                ptr_mode_ok = not (os.stat(ptr).st_mode & 0o022)
            except Exception:
                ptr_mode_ok = False
            if not ptr_mode_ok:
                _seam(
                    'pointer-file rejected -- ' + ptr + ' failed trust-boundary validation '
                    '(pointer file itself is group- or world-writable); a .pth import line '
                    'reached through it executes at interpreter startup, so this rung is '
                    'skipped and resolution falls through to the layout rung.'
                )
        if ptr_mode_ok and os.path.isfile(ptr):
            v = ''
            try:
                v = open(ptr, encoding='utf-8').read().strip()
            except Exception:
                v = ''
            if v != '':
                ok, reason = _validate_pointer(v, home)
                if ok:
                    return v, 'pointer-file'
                _seam(
                    'pointer-file rejected -- ' + ptr + ' resolved to ' + v + ' but failed '
                    'trust-boundary validation (' + str(reason) + '); a .pth import line in '
                    'an untrusted directory executes at interpreter startup, so this rung is '
                    'skipped and resolution falls through to the layout rung.'
                )
        venv = os.path.join(home, '.coordinator-venv')
        if sys.platform == 'win32':
            cand = os.path.join(venv, 'Lib', 'site-packages')
            if os.path.isdir(cand):
                return cand, 'layout'
        else:
            cand = os.path.join(venv, 'lib', 'python%d.%d' % sys.version_info[:2], 'site-packages')
            if os.path.isdir(cand):
                return cand, 'layout'
            hits = glob.glob(os.path.join(venv, 'lib', 'python3.*', 'site-packages'))
            own = [h for h in hits if os.path.basename(os.path.dirname(h)) == 'python%d.%d' % sys.version_info[:2]]
            if own:
                return own[0], 'layout'

            def _pyver(h):
                seg = os.path.basename(os.path.dirname(h))
                try:
                    return tuple(int(x) for x in seg[len('python'):].split('.'))
                except Exception:
                    return (-1, -1)

            hits = sorted(hits, key=_pyver)
            if hits:
                return hits[-1], 'layout'
        return None, None

    def _find_venv_root(sp):
        d = sp
        i = 0
        while i < 6:
            cfg = os.path.join(d, 'pyvenv.cfg')
            if os.path.isfile(cfg):
                return d, cfg
            parent = os.path.dirname(d)
            if parent == d or parent == '':
                return None, None
            d = parent
            i = i + 1
        return None, None

    def _version_ok(cfg_path):
        try:
            text = open(cfg_path, encoding='utf-8').read()
        except Exception:
            return False
        for line in text.split(chr(10)):
            line = line.strip()
            parts = line.split('=', 1)
            if len(parts) != 2:
                continue
            key = parts[0].strip()
            if key == 'version':
                ver = parts[1].strip().split('.')
                try:
                    major, minor = int(ver[0]), int(ver[1])
                except Exception:
                    return False
                return (major, minor) == sys.version_info[:2]
        return False

    sp, rung = _resolve_site_packages()
    if sp is None:
        _seam(
            'site-packages injection skipped -- missing (no ladder rung resolved: '
            'COORDINATOR_HOOK_SITE_PACKAGES unset, no installer pointer file, no '
            'layout-derived venv under settings home). sys.executable: left untouched.'
        )
        return
    venv_root, cfg = _find_venv_root(sp)
    if cfg is None or not _version_ok(cfg):
        _seam(
            'site-packages injection skipped -- stale/incompatible (resolved via ' + rung +
            ' rung: ' + sp + ' but pyvenv.cfg version does not match the running interpreter '
            + str(sys.version_info[0]) + '.' + str(sys.version_info[1]) + ', or pyvenv.cfg '
            'was unreadable). sys.executable: left untouched.'
        )
        return

    def _norm(p):
        return os.path.normcase(os.path.normpath(p))

    before = list(sys.path)
    before_norm = set(_norm(p) for p in before)
    site.addsitedir(sp)
    added = [p for p in sys.path if _norm(p) not in before_norm]
    added_norm = set(_norm(p) for p in added)
    sp_norm = _norm(sp)
    promoted = added + ([sp] if sp_norm in before_norm and sp_norm not in added_norm else [])
    promoted_norm = set(_norm(p) for p in promoted)
    rest = [p for p in sys.path if _norm(p) not in promoted_norm and _norm(p) != sp_norm]
    sys.path[:] = promoted + rest
    if sys.platform == 'win32':
        candidates = [os.path.join(venv_root, 'Scripts', 'python.exe')]
    else:
        candidates = [
            os.path.join(venv_root, 'bin', 'python'),
            os.path.join(venv_root, 'bin', 'python3'),
            os.path.join(venv_root, 'bin', 'python3.' + str(sys.version_info[1])),
        ]
    resolved_exe = None
    for c in candidates:
        if os.path.isfile(c):
            resolved_exe = c
            break
    if resolved_exe is not None:
        os.environ['COORDINATOR_HOST_PYTHON'] = sys.executable
        sys.executable = resolved_exe
        os.environ['COORDINATOR_HOOK_PYTHON'] = resolved_exe
    else:
        os.environ['COORDINATOR_HOOK_PYTHON'] = sys.executable
        _seam(
            'site-packages injected via ' + rung + ' rung (' + sp + ') but sys.executable '
            'was left untouched -- resolved-but-interpreter-missing: none of the candidate '
            'venv interpreter paths exist on disk.'
        )


def _detect_hook_seam_drift():
    """Banner once per session if this process's snapshotted `-c` payload no longer matches
    the current on-disk `fail_open_launcher.LOADER`. See this module's docstring
    ("REGISTRATION-STALENESS DETECTOR" / "THIS IS THE ONE PLACE ... INVERTS") for why this
    lives here and why every failure path below is a silent no-op rather than a banner.

    NEVER RAISES. NEVER TOUCHES `sys.argv`. NEVER CHANGES THE TARGET HOOK'S EXIT CODE OR
    OUTPUT. The whole body is one `try/except Exception: return` for exactly that reason --
    an unreadable launcher file, an unexpected `sys.orig_argv` shape, or a permission error on
    the sentinel must degrade to "did not check" rather than to a broken hook fire.
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
            return  # AC5: an unexpanded PATH token means "cannot determine", not drift.
        # NOT applied to `snapshotted_loader`: that text is the `-c` payload's own SOURCE, not
        # a path -- gen2's real BOOTSTRAP legitimately contains the literal substring '${' as
        # part of its own inline unexpanded-token check ("if '${' in j: ..."). Guarding on it
        # here made the detector bail on every real gen2 payload before the comparison ever
        # ran (found live: a probe against the actual 596e32b78 BOOTSTRAP never bannered).
        # Do not re-broaden this to `snapshotted_loader` again -- that is the exact regression.

        # `script_arg` is always `<plugin_root>/hooks/scripts/<script>.py` -- the one argv
        # position with production evidence of `${CLAUDE_PLUGIN_ROOT}` expansion across every
        # generation of this trampoline (see fail_open_launcher.py's own docstring). Its
        # grandparent directory is `<plugin_root>/hooks`, where fail_open_launcher.py lives.
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
            return  # AC3: no session key to suppress on -- skip rather than risk repeating

        # Inlined rather than calling `_coord_hook_inject`'s nested `_settings_home` -- that
        # helper is a local of another function, out of scope here by construction. Kept as a
        # literal duplicate of its two-line body rather than hoisting it to module scope,
        # since hoisting would change `_coord_hook_inject`'s own closure for a caller (this
        # detector) that AC7 already documents as off-purpose riding in this file.
        home = os.environ.get('COORDINATOR_SETTINGS_HOME') or os.path.join(
            os.environ.get('CLAUDE_HOME') or os.path.expanduser('~'), '.coordinator-claude-settings'
        )
        sentinel_dir = os.path.join(home, 'hook-seam-drift-notified')
        sentinel = os.path.join(sentinel_dir, session_id + '.flag')
        if os.path.isfile(sentinel):
            return  # AC3: already bannered once this session

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


_coord_hook_inject()
_detect_hook_seam_drift()
