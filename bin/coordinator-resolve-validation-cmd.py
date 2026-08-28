# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""coordinator-resolve-validation-cmd.py — Resolver for the per-project test commands.

Purpose: resolve which shell command to use for test validation. Two tiers:
  - resolve_fast_test_cmd — the FAST-tier gate for /workday-complete Step 1,
    /workweek-complete Step 2, and the /validate skill (three-step resolution).
  - resolve_full_test_cmd — the FULL suite for /bug-blitz, which chases every
    failing test (four-step resolution; falls back to the fast tier with a caveat
    rather than skipping, so a repo with no full_test_cmd still gets coverage).
Encapsulates the resolution order so call sites stay one-liners and the two tiers
can never diverge into hand-rolled per-skill test surfaces.

Spec backlink: archive/specs/2026-05-28-workday-complete-fast-test-resolution.md § 3.4

Fast-tier resolution order (resolve_fast_test_cmd — three steps, no
conventional fallback — the Staff Engineer F1):
  1. COORDINATOR_FAST_TEST_CMD env var — if set and non-empty, use verbatim.
  2. coordinator.local.md at repo root — flat top-level fast_test_cmd: key.
  3. Skip-with-notice — stderr names both remediation paths; exit 2.
Full-tier resolution order (resolve_full_test_cmd — four steps, falls back
to fast rather than skipping): COORDINATOR_FULL_TEST_CMD -> full_test_cmd: key ->
fast-tier fallback (exit 3) -> unconfigured (exit 2). See its docstring below.

Output contract (both CLI and library ResolveResult):
  stdout — resolved command string (only on exit 0, or exit 3 for the full tier)
  stderr — diagnostic prose (step=env-var | step=local-md | step=skipped on exit 2)
  exit 0 — command resolved; caller should execute it and capture its exit code
  exit 2 — no command configured; caller should treat validation as skipped
  exit 126 — the configured value carries an un-interpretable backslash-escaped
             quote (`\"` / `\'`) that survived scalar unquoting. A HARD config
             failure, NOT a skip: an un-normalized escaped quote re-splits the
             quoted sub-argument into separate argv tokens no matter how the
             resolved string is later parsed (`bash -c`'s re-splitting, or a
             caller's own `shlex.split`) and the gate reports a build/test
             failure that is really a config defect (project-rag, 2026-07-22 —
             a day of unnoticed red). Callers MUST surface it as blocking.
  exit 127 — command resolved to a bare `python` token but NEITHER python3 nor
             python is on PATH. A HARD environment failure, NOT a skip — callers
             MUST surface this as a blocking validation failure (distinguish from
             exit 2). This closes the silent-127 swallow (a python3-only machine
             previously skipped validation entirely). A leading `python ` token is
             normalized to a repo-local `.venv` interpreter (when one exists) or
             python3-first at resolution time, so this fires only when no Python
             interpreter exists at all.

Trust model: COORDINATOR_FAST_TEST_CMD is an escape hatch for trusted contexts
(local shell, CI-managed env). It is not safe to accept from untrusted sources
(memo bodies, webhook payloads, third-party files, untrusted hook input).
Executor agents (coordinator subagents) MUST NOT set this from any prompt-derived
input. The env var feeds directly into process execution; this resolver's two
current callers (coordinator/bin/workday-complete-step1-validate.py and
coordinator/bin/validate-fast-and-packageability.py) run the resolved string
via `shlex.split` + a direct (no-shell) subprocess exec as of the 2026-07-29
debash pass — there is no longer a child shell in that path. Each of those
callers additionally REFUSES (fail-loud, before executing) any resolved value
containing a shell metacharacter that implies real shell semantics
(pipe/chain/redirect/substitution) — that value cannot be honored without a
shell, so silently running it as a literal argv token would be the same
quiet-corruption shape this module's own exit-126 escaped-quote guard exists
to prevent. See each caller's `_fail_on_ambiguous_shell_syntax`.

No sanitization of shell metacharacters is performed BY THIS RESOLVER, by
design — the configured command is trusted, matching how python
.github/scripts/run-all-checks.py behaved previously; the refusal described
above lives in the callers because it is a consequence of how each caller
executes the string, not of resolving it. A LIGHT advisory tripwire fires on
stderr when the resolved value contains $( ` or `; ` — visible signal only,
not a block; suppress via COORDINATOR_FAST_TEST_CMD_SUPPRESS_METACHAR_WARN=1.

No first-token heuristic (the Staff Engineer F5): the resolver does NOT pre-parse, probe,
or validate the command string. Runtime exit-code from the configured command
is the safety net. A configured command that fails to invoke returns non-zero
and surfaces as a normal Validation failure.

Consumers:
  - DoE-claude coordinator/skills/validate/SKILL.md (single owner of FAST-tier
    resolver invocation, via the settings-home forwarder — this bin/ CLI)
  - DoE-claude coordinator/commands/bug-blitz.md (single owner of FULL-tier
    resolver invocation, Phase 0.7, via the settings-home forwarder)
  - coordinator/bin/coordinator-ceremony-hook.py (read_local_md_key — per-repo
    ceremony post-command key lookup, imported in-process by file path —
    hyphenated filenames are not importable via a bareword `import`)
  - coordinator/bin/workday-complete-step1-validate.py (resolve_fast_test_cmd,
    imported in-process by file path)
  - coordinator/bin/validate-fast-and-packageability.py (resolve_fast_test_cmd,
    imported in-process by file path)

CLI (for bash callers that cannot import a Python module in-process):
  coordinator-resolve-validation-cmd.py --fast [repo_root]
  coordinator-resolve-validation-cmd.py --full [repo_root]
  coordinator-resolve-validation-cmd.py --read-key <repo_root> <key>
Prints stdout/stderr and exits with the same contract as the library functions.
"""

from __future__ import annotations

import contextlib
import io
import os
import re
import shlex
import shutil
import sys
from dataclasses import dataclass

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_BOOTSTRAP_DONE = False


def _bootstrap_engine() -> None:
    """Put the repo root on ``sys.path`` before ``coordinator_core`` is
    imported.

    coordinator_core is co-located in this same repo (claude-klabauter) --
    resolvable only from the repo root, which is NOT on sys.path when this
    file is run directly (its own dir is) or loaded via
    importlib.util.spec_from_file_location by a sibling script (e.g.
    workday-complete-step1-validate.py). Bootstrap it so the import in
    `_venv_interp` doesn't raise ModuleNotFoundError in either shape.

    Idempotent; safe to call more than once. Moved out of module scope
    (2026-08-28) -- unconditionally mutating `sys.path` at import time made
    every import of this file mutate the `sys.path` of a warm server ~50
    sessions share. Only the trigger moved; the effect is byte-for-byte the
    same.
    """
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)
    _BOOTSTRAP_DONE = True

_METACHAR_RE = re.compile(r"\$\(|`|; ")
_ESCAPED_QUOTE_RE = re.compile(r"\\[\"']")


class InterpreterMissing(Exception):
    """Raised when a bare `python` token needs normalizing but no interpreter exists."""


class MalformedValue(Exception):
    """Raised when a resolved value carries an un-interpretable escaped quote."""


@dataclass
class ResolveResult:
    stdout: str  # resolved command string, "" when not resolved
    returncode: int
    stderr: str = ""  # accumulated diagnostic prose (already also printed live)


def _redact_for_diag(s: str) -> str:
    """Truncate a command string for stderr diagnostic display.

    Prevents secret leakage when the configured command embeds tokens (e.g.
    `MY_TOKEN=abc python run.py`). Diagnostic stderr is captured into review
    trail JSON and session transcripts; truncating past 60 chars keeps the
    resolver step legible while bounding leakage surface.
    """
    if len(s) > 60:
        return f"{s[:60]}…(truncated; {len(s)} chars total)"
    return s


def _metachar_warn(s: str, step: str, caller: str = "cs_resolve_fast_test_cmd") -> str:
    """Light advisory tripwire on shell-metacharacter shapes. Visible-signal-only.

    Suppressible via COORDINATOR_FAST_TEST_CMD_SUPPRESS_METACHAR_WARN=1 for
    known-safe configurations that legitimately use these shapes (e.g.
    `python foo.py && python bar.py`). Returns the warning text printed (empty
    string when not fired) so CLI callers can accumulate it into ResolveResult.stderr.
    """
    if os.environ.get("COORDINATOR_FAST_TEST_CMD_SUPPRESS_METACHAR_WARN", "0") == "1":
        return ""
    if _METACHAR_RE.search(s):
        msg = (
            f"[{caller}] WARN (step={step}): resolved value contains shell metacharacters "
            "($( or backtick or ;) — confirm this is intended; set "
            "COORDINATOR_FAST_TEST_CMD_SUPPRESS_METACHAR_WARN=1 to silence this warning for "
            "this and other callers."
        )
        print(msg, file=sys.stderr)
        return msg + "\n"
    return ""


def _venv_interp(repo_root: str | None) -> str | None:
    """Repo-local virtualenv interpreter, when the repo has one.

    A bare `python` token means the config declined to name an interpreter, so
    the resolver picks — and for a venv-primary repo the ambient system python3
    is the wrong pick: it has none of the runtime deps, so the gate reports a
    wall of collection errors that read as test failures rather than as an
    environment mismatch (project-rag saw 314 of them, 2026-07-22). A `.venv`
    sitting in the repo root is an unambiguous declaration of which interpreter
    that repo's tests expect. Returns None when there is no repo root or no
    `.venv` — the ambient python3-first path then applies unchanged.
    """
    if not repo_root:
        return None
    _bootstrap_engine()
    from coordinator_core.win_portability import is_executable

    for rel in ("bin/python", "Scripts/python.exe"):
        cand = os.path.join(repo_root, ".venv", *rel.split("/"))
        if os.path.isfile(cand) and is_executable(cand):
            return cand
    return None


def _resolve_python_interp(repo_root: str | None = None) -> str | None:
    """venv-first, then platform-appropriate interpreter resolution.

    Returns the repo-local `.venv` interpreter when present. Otherwise, on
    Windows (`os.name == "nt"`), prefers `sys.executable` — the real,
    currently-running interpreter — over probing `python3` on PATH, because
    `shutil.which("python3")` commonly resolves to the Microsoft Store App
    Execution Alias stub (`%LOCALAPPDATA%/Microsoft/WindowsApps/python3.exe`)
    on a clean Windows install, which either opens the Store or exits
    nonzero with no useful diagnostic. Falls back to `python3`/`python` on
    PATH if `sys.executable` is unset. POSIX behavior is unchanged: `python3`
    is still probed first there. Returns None when nothing resolves.

    # Review: code-reviewer — mirrors coordinator/lib/register-coordinator-mirror.py's
    # _python_argv Windows-first-`sys.executable` fix for the identical hazard.
    """
    venv = _venv_interp(repo_root)
    if venv:
        return venv
    if os.name == "nt" and sys.executable:
        return sys.executable
    if shutil.which("python3"):
        return "python3"
    if shutil.which("python"):
        return "python"
    return None


def _normalize_python_token(cmd: str, repo_root: str | None = None) -> str:
    """Interpreter-portability normalization.

    When <cmd>'s first whitespace-delimited token is the BARE interpreter
    `python` (not python3, not an explicit path, not VAR=x env-prefixed),
    rewrite it to a repo-`.venv`-first, then python3-first resolved interpreter.
    Returns the (possibly rewritten) command. Raises InterpreterMissing when the
    token is bare `python` and NO interpreter exists — callers must map this to
    exit 127 (a HARD environment failure, NOT a skip).

    Which interpreter was chosen is announced on stderr: the resolved command is
    executed directly (no shell — see the module docstring's Trust model note),
    so the substituted interpreter is otherwise invisible in the failure output,
    and "wrong interpreter" and "broken tests" produce the same-looking red.

    Matching contract: matches the bare interpreter `python` with OR without
    arguments (`python` and `python <args>`); does NOT match `python2`,
    `python3`, or path forms.
    """
    if cmd == "python" or cmd.startswith("python "):
        interp = _resolve_python_interp(repo_root)
        if interp is None:
            print(
                f"[cs_resolve] no python3/python on PATH — cannot run '{cmd}' (refusing to skip; fail loud)",
                file=sys.stderr,
            )
            raise InterpreterMissing(cmd)
        print(f"[cs_resolve] step=interp bare `python` token -> {interp}", file=sys.stderr)
        # shlex.quote: a venv path can contain spaces, and the resolved string is
        # later re-split with `shlex.split` by the caller (no shell) — the same
        # quoting convention keeps that round-trip lossless.
        return shlex.quote(interp) + cmd[len("python"):]
    return cmd


def _read_frontmatter(local_md: str) -> list[str]:
    """Read the YAML frontmatter block (between the first and second `---`
    markers) of a coordinator.local.md file. Returns the body lines (without
    the marker lines themselves); [] if the file is unreadable or has fewer
    than two markers.
    """
    lines: list[str] = []
    n = 0
    try:
        with open(local_md, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.rstrip("\n")
                if line == "---":
                    n += 1
                    if n == 2:
                        break
                    continue
                if n == 1:
                    lines.append(line)
    except OSError:
        return []
    return lines


def _strip_wrapping_quotes(val: str) -> str:
    """Unquote ONE wrapping YAML scalar pair, preserving interior quotes.

    Interior quotes are load-bearing: a configured command routinely contains a
    quoted sub-argument (`-m "not slow and not integration"`, `--filter 'a b'`).
    Stripping every quote character — the transform the retired bash oracle's
    `tr -d '"' | tr -d "'"` pipeline performed, and which the Python port
    inherited — silently shell-splits such a value into separate argv tokens
    (pytest exits 4 with `file or directory not found: and`). Only the outermost
    matched pair, which is YAML scalar syntax rather than shell syntax, is ours
    to remove.

    Removing the pair is not sufficient on its own: inside a YAML double-quoted
    scalar the interior quotes are themselves escaped (`"… -m \\"a and b\\" …"`),
    and leaving those backslashes in place hands a caller's `shlex.split` a
    value it re-splits exactly as the old `tr -d` transform did — the same
    silent corruption wearing a different costume. So a double-quoted scalar
    additionally resolves its `\\"`
    and `\\\\` escapes, and a single-quoted scalar its doubled-`''` escape, in one
    left-to-right pass (no other YAML escape is interpreted — see
    _check_escape_residue for what happens to the rest).
    """
    if len(val) >= 2 and val.startswith('"') and val.endswith('"'):
        return _unescape_double_quoted(val[1:-1])
    if len(val) >= 2 and val.startswith("'") and val.endswith("'"):
        return val[1:-1].replace("''", "'")
    return val


def _unescape_double_quoted(body: str) -> str:
    """Resolve the `\\"` and `\\\\` escapes of a YAML double-quoted scalar body.

    Single left-to-right pass so `\\\\"` reads as backslash-then-quote-delimiter
    rather than being double-processed. Every other backslash sequence is passed
    through verbatim — Windows paths (`C:\\tools\\py`) must survive untouched, and
    an escape this function does not claim to understand is caught downstream by
    _check_escape_residue rather than silently mangled here.
    """
    out: list[str] = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body) and body[i + 1] in ('"', "\\"):
            out.append(body[i + 1])
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _check_escape_residue(val: str, step: str, caller: str) -> None:
    """Fail loud when an un-interpretable escaped quote survives unquoting.

    This resolver is a flat-key frontmatter reader, not a YAML parser: it claims
    only the escapes _strip_wrapping_quotes resolves. Anything else carrying a
    `\\"` or `\\'` — an unquoted scalar written with shell-style escaping, a
    partially-quoted value, a hand-edited frontmatter line — cannot be handed
    to a caller's `shlex.split` (or, historically, `bash -c`) intact, because
    both drop the backslash and promote the quote to a real delimiter,
    re-splitting the sub-argument. Refusing is the whole point of the memo
    that prompted this: silently passing a corrupted command to a gate that
    then reports "build failure" cost project-rag a day of unnoticed red
    (2026-07-22). Raises MalformedValue; callers map it to exit 126.
    """
    if _ESCAPED_QUOTE_RE.search(val):
        print(
            f"[{caller}] FAIL (step={step}): resolved value carries an escaped quote "
            f"this resolver cannot interpret: {_redact_for_diag(val)}\n"
            f"[{caller}] Passing it to a caller's `shlex.split` would re-split the "
            "quoted argument. Wrap the whole value in single quotes and use plain "
            "double quotes inside (fast_test_cmd: 'pytest -m \"a and b\"'), or drop "
            "the backslashes.",
            file=sys.stderr,
        )
        raise MalformedValue(val)


def _read_frontmatter_key(local_md: str, key: str) -> str:
    """Extract a flat top-level frontmatter key from an open-able local.md path.

    Shared parser for read_local_md_key and _read_fast_test_cmd_key: matches the
    `<key>:` label at line start, strips the label + immediate whitespace, trims,
    then removes one wrapping quote pair. `key` is matched as a LITERAL prefix
    (never a regex) — a caller passing a key with regex metacharacters
    (., *, [, ^) does not corrupt the match. Empty string when absent.
    """
    needle = f"{key}:"
    for line in _read_frontmatter(local_md):
        if line.startswith(needle):
            return _strip_wrapping_quotes(line[len(needle):].strip())
    return ""


def read_local_md_key(repo_root: str, key: str) -> str:
    """Extract a flat top-level frontmatter key from coordinator.local.md.

    Applies the same quote-strip / whitespace-trim discipline as
    resolve_fast_test_cmd's parser (preserves internal whitespace AND internal
    quotes). Always succeeds (empty string means the file or key is absent).
    """
    local_md = os.path.join(repo_root, "coordinator.local.md")
    if not os.path.isfile(local_md):
        return ""
    return _read_frontmatter_key(local_md, key)


def _read_fast_test_cmd_key(local_md: str) -> str:
    """Extract the flat top-level `fast_test_cmd:` key (path-taking variant)."""
    return _read_frontmatter_key(local_md, "fast_test_cmd")


def resolve_fast_test_cmd(repo_root: str | None = None) -> ResolveResult:
    """Resolve the fast-test command for the given repo root (default: cwd)."""
    repo_root = repo_root or os.getcwd()
    stderr_acc = []

    def _say(msg: str) -> None:
        print(msg, file=sys.stderr)
        stderr_acc.append(msg + "\n")

    # Step 1 — COORDINATOR_FAST_TEST_CMD env var
    env_val = os.environ.get("COORDINATOR_FAST_TEST_CMD", "")
    if env_val:
        _say(f"[cs_resolve_fast_test_cmd] step=env-var resolved: {_redact_for_diag(env_val)}")
        stderr_acc.append(_metachar_warn(env_val, "env-var"))
        try:
            _check_escape_residue(env_val, "env-var", "cs_resolve_fast_test_cmd")
            norm = _normalize_python_token(env_val, repo_root)
        except MalformedValue:
            return ResolveResult("", 126, "".join(stderr_acc))
        except InterpreterMissing:
            return ResolveResult("", 127, "".join(stderr_acc))
        return ResolveResult(norm + "\n", 0, "".join(stderr_acc))

    # Step 2 — coordinator.local.md flat top-level fast_test_cmd: key
    local_md = os.path.join(repo_root, "coordinator.local.md")
    if os.path.isfile(local_md):
        fast_test_cmd = _read_fast_test_cmd_key(local_md)
        if fast_test_cmd:
            _say(f"[cs_resolve_fast_test_cmd] step=local-md resolved: {_redact_for_diag(fast_test_cmd)}")
            stderr_acc.append(_metachar_warn(fast_test_cmd, "local-md"))
            try:
                _check_escape_residue(fast_test_cmd, "local-md", "cs_resolve_fast_test_cmd")
                norm = _normalize_python_token(fast_test_cmd, repo_root)
            except MalformedValue:
                return ResolveResult("", 126, "".join(stderr_acc))
            except InterpreterMissing:
                return ResolveResult("", 127, "".join(stderr_acc))
            return ResolveResult(norm + "\n", 0, "".join(stderr_acc))

    # Step 3 — skip-with-notice (no conventional fallback — the Staff Engineer F1)
    _say("[cs_resolve_fast_test_cmd] step=skipped — no fast-test command configured.")
    _say("[cs_resolve_fast_test_cmd] To configure, choose one of:")
    _say('  a) Set env var: export COORDINATOR_FAST_TEST_CMD="<your-command>"')
    _say('  b) Add to coordinator.local.md frontmatter: fast_test_cmd: "<your-command>"')
    return ResolveResult("", 2, "".join(stderr_acc))


def resolve_full_test_cmd(repo_root: str | None = None) -> ResolveResult:
    """Resolve the FULL test suite command — the heavier tier bug-blitz runs to
    chase every failing test (distinct from the fast-tier gate the /validate
    skill runs).

    Resolution order (four steps — falls back to fast, NOT to skip):
      1. COORDINATOR_FULL_TEST_CMD env var — if set and non-empty, use verbatim.
      2. coordinator.local.md flat top-level full_test_cmd: key.
      3. FALL BACK to resolve_fast_test_cmd, with a caveat on stderr — a repo
         that has not declared a full suite still gets coverage (the fast
         tier), and the caller is told the coverage is fast-tier-only.
      4. If even the fast resolver skips (exit 2), propagate exit 2.

    Output contract:
      stdout — resolved command string (only on exit 0 or exit 3)
      exit 0 — a FULL command resolved (env or local.md); coverage is full-suite.
      exit 3 — resolved by fast-tier FALLBACK; stdout is the fast command, and
               the caller MUST report coverage as fast-tier-only.
      exit 2 — nothing configured at either tier.
    """
    repo_root = repo_root or os.getcwd()
    stderr_acc = []

    def _say(msg: str) -> None:
        print(msg, file=sys.stderr)
        stderr_acc.append(msg + "\n")

    # Step 1 — COORDINATOR_FULL_TEST_CMD env var
    env_val = os.environ.get("COORDINATOR_FULL_TEST_CMD", "")
    if env_val:
        _say(f"[cs_resolve_full_test_cmd] step=env-var resolved: {_redact_for_diag(env_val)}")
        stderr_acc.append(_metachar_warn(env_val, "env-var", "cs_resolve_full_test_cmd"))
        try:
            _check_escape_residue(env_val, "env-var", "cs_resolve_full_test_cmd")
            norm = _normalize_python_token(env_val, repo_root)
        except MalformedValue:
            return ResolveResult("", 126, "".join(stderr_acc))
        except InterpreterMissing:
            return ResolveResult("", 127, "".join(stderr_acc))
        return ResolveResult(norm + "\n", 0, "".join(stderr_acc))

    # Step 2 — coordinator.local.md flat top-level full_test_cmd: key
    full_test_cmd = read_local_md_key(repo_root, "full_test_cmd")
    if full_test_cmd:
        _say(f"[cs_resolve_full_test_cmd] step=local-md resolved: {_redact_for_diag(full_test_cmd)}")
        stderr_acc.append(_metachar_warn(full_test_cmd, "local-md", "cs_resolve_full_test_cmd"))
        try:
            _check_escape_residue(full_test_cmd, "local-md", "cs_resolve_full_test_cmd")
            norm = _normalize_python_token(full_test_cmd, repo_root)
        except MalformedValue:
            return ResolveResult("", 126, "".join(stderr_acc))
        except InterpreterMissing:
            return ResolveResult("", 127, "".join(stderr_acc))
        return ResolveResult(norm + "\n", 0, "".join(stderr_acc))

    # Step 3 — FALL BACK to the fast tier (not skip). fast-tier diags are
    # suppressed from stderr (matches bash oracle's `2>/dev/null` on the
    # fallback call) so they don't bleed into full-tier output.
    with contextlib.redirect_stderr(io.StringIO()):
        fast = resolve_fast_test_cmd(repo_root)
    if fast.returncode == 0:
        _say(
            "[cs_resolve_full_test_cmd] step=fast-fallback — no full_test_cmd configured; "
            "running the FAST tier. Coverage is fast-tier-only. To run the full suite, set "
            "full_test_cmd: in coordinator.local.md or $COORDINATOR_FULL_TEST_CMD."
        )
        return ResolveResult(fast.stdout, 3, "".join(stderr_acc))
    if fast.returncode != 2:
        # Exit 2 is the fast tier's "unconfigured" signal (handled at Step 4).
        # ANY OTHER non-zero — canonically 127 (bare `python` token, no
        # interpreter) — is a HARD environment failure; propagate it.
        _say(
            f"[cs_resolve_full_test_cmd] step=fast-fallback — fast resolver hard-failed "
            f"(rc={fast.returncode}); propagating (NOT a skip)."
        )
        return ResolveResult("", fast.returncode, "".join(stderr_acc))

    # Step 4 — neither tier configured (fast.returncode == 2)
    _say("[cs_resolve_full_test_cmd] step=skipped — no full or fast test command configured.")
    return ResolveResult("", 2, "".join(stderr_acc))


def main(argv: list[str]) -> int:
    # Named `main` (not `_cli`) so this CLI exposes the entrypoint every
    # CONSUMES_MANIFEST member's in-process dispatch (`workweek_complete.
    # apply._invoke_cli_main`, via `getattr(module, "main", None)`) requires
    # — this module previously had no `main` at all, so
    # `d_step2_resolve_validation_cmd` (workweek_complete/brief.py,
    # ungated — fires on every `/workweek-complete apply` run) always
    # raised `UnrecognizedDirective` before ever reaching this logic
    # (2026-07-27 arg-mismatch audit). `argv` is args-only, matching every
    # sibling consumes-manifest CLI's convention (see e.g.
    # `workday-complete-reconcile.py`'s identical comment) — `mode =
    # argv[0]` below already treated index 0 as real data, so no internal
    # change to this function's argument handling was needed, only the name.
    _bootstrap_engine()
    if not argv:
        print("usage: coordinator_resolve_validation_cmd.py --fast|--full [repo_root] | --read-key <repo_root> <key>", file=sys.stderr)
        return 1

    mode = argv[0]
    if mode == "--fast":
        repo_root = argv[1] if len(argv) > 1 else None
        result = resolve_fast_test_cmd(repo_root)
    elif mode == "--full":
        repo_root = argv[1] if len(argv) > 1 else None
        result = resolve_full_test_cmd(repo_root)
    elif mode == "--read-key":
        if len(argv) < 3:
            print("usage: coordinator_resolve_validation_cmd.py --read-key <repo_root> <key>", file=sys.stderr)
            return 1
        val = read_local_md_key(argv[1], argv[2])
        print(val)
        return 0
    else:
        print(f"unknown mode: {mode}", file=sys.stderr)
        return 1

    if result.stdout:
        sys.stdout.write(result.stdout)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
