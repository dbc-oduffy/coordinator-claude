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

Executing this module (via `exec()`, never `import`) resolves the venv injector and hands off
to the target hook script as a side effect of running top to bottom — mirroring the un-escaped
source's own trailing calls. Loaded with a bare `exec(code, <caller's globals>)`, not `import`:
no `__name__`/`__file__` is available in this module's own namespace at exec time, so no
`__main__` guard or `__file__`-relative path logic belongs here.
"""
import runpy


def L():
    j = sys.argv.pop()
    S = lambda m: sys.stderr.write('COORDINATOR HOOK SEAM: ' + m + chr(10))
    if '${' in j:
        S('injector skip -- unexpanded: ' + j)
        return
    if not os.path.isfile(j):
        S('injector skip -- missing: ' + j)
        return
    try:
        # Empty globals deliberately, unlike this file's own inherited-globals exec: the
        # injector does its own imports and mutates sys.path/os.environ via those, so it
        # needs no globals handed down from here.
        exec(compile(open(j, encoding='utf-8').read(), j, 'exec'), {})
    except Exception as x:
        S('injector skip -- raised ' + repr(x) + ': ' + j)


L()
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
