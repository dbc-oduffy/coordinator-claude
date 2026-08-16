"""x-effective-delivery generator -- the hook-delivery manifest emitter.

Spec: docs/plans/2026-08-13-x-effective-delivery-emitter.md, chunk C2 (the
generator), consuming C1's delivery-graph enumeration and C1b's cross-plane
seam. The one seam this module actually imports is
`coordinator_core.bash_guards.guard_roster`; the advisory carrier's op list is
derived doctrine-plane-locally (see `_advisory_ops_delivered`), so
`coordinator_core.ops.session.guard_roster_ops.list_ported_advisory_ops` — C1b's
other half, renamed from `list_advisory_ops` — has no call site here.

Builds the `x-effective-delivery` block the engine plane's hook-delivery-
duplication detector reads (its own `docs/reference/hook-delivery-manifest.md`).
One carrier (`postuse-stop-family-dispatch.py`) is doctrine-plane-local -- its guard set
comes from this repo's own runner-registry module. Three carriers
(`preuse-write-dispatch.py`, `preuse-bash-dispatch.py`, `postuse-advisory-
dispatch.py`) are cross-plane -- their guard/op sets are read LIVE from
the engine plane's exported seam at generation time, never transcribed from a table,
so a future `dispatch.py` edit cannot silently desync a copied snapshot.
`preuse-write-dispatch.py` additionally carries 7 doctrine-plane-local guards
(`_guard_runner.REAL_GUARD_REGISTRY`) alongside the guards it delivers by
running the engine plane's write-guards engine in-process (see
`preuse-write-dispatch.py`'s own header) -- its manifest entry merges both
sources, it is not purely one or the other.

FAILS CLOSED: this is the deliberate inverse of every carrier's own runtime
fail-OPEN posture (a missing engine must never brick a live tool call). A
manifest generator has no such excuse -- any failure to resolve the
engine-plane-sourced half aborts with a non-zero exit and writes nothing, leaving
the previous block (or `absent`) in place. A stale manifest is worse than an
absent one; the engine plane's reader treats `absent` as honest and `stale` as a
defect.

Negative spec: does not seed `tool_names` uniformly with `["Bash",
"PowerShell"]`, does not assert `tool_names` against the live carrier-level
`matcher` (that check passes green on every `("Bash",)` guard and catches
nothing -- see AC-9's superset check instead), does not transcribe the engine plane's
`list_ported_advisory_ops()` six-name tuple as this carrier's op list (AC-11; only
1 of the 6 is actually delivered here), does not call the private
`_build_guard_chain`, does not re-derive guard identity by filename-globbing,
and never uses the word "filename" for the tail-key join field.

Emission provenance: the block carries three top-level keys
(`PROVENANCE_KEYS`) beside `version` -- `generated_from_sha` (the full
40-char git HEAD SHA of THIS repo at emission time -- i.e. the commit the
emitter ran at, which is by construction the PARENT of whatever commit ends
up carrying the emitted block, since the block is written before that
commit exists), `generated_at` (UTC ISO-8601, second precision,
`Z`-suffixed), and `generated_from_dirty_tree` (bool -- true if tracked
files had uncommitted changes at emission, so a consumer never has to strip
a `-dirty` suffix off the SHA string itself). These answer "when/at what
commit was this actually generated", which a `hooks.json` git-commit-date
alone cannot: a fixed generator whose output was never regenerated still
carries an old commit date on the same line the fix landed on. Any failure
to resolve the SHA (git absent, not a repo, non-zero exit) raises
`EmitterError` -- same fail-closed posture as everything else in this
module.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any, Dict, List, Optional, Set, Tuple

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parents[2]
HOOKS_JSON_PATH = REPO_ROOT / "coordinator" / "hooks" / "hooks.json"

MAX_STRING_LEN = 200

#: The three emission-provenance keys `build_block()` adds beside `version`
#: -- named here as the single source of truth so `render_block`'s
#: content-idempotence contract (AC-8) and this suite's own tests strip
#: exactly this set, never a hand-typed tuple that can silently desync.
PROVENANCE_KEYS = ("generated_from_sha", "generated_at", "generated_from_dirty_tree")

_GIT_TIMEOUT_SECONDS = 10

#: Bootstrap trampoline tails -- present at the tail of every hooks.json
#: `args` array, never a registration in their own right (AC-3's structural
#: partition excludes them explicitly, matching C1's finding).
_TRAMPOLINE_TAILS = frozenset({"scripts/_hook_venv_inject.py", "scripts/_hook_boot.py"})

#: The four carrier tail keys this plan's delivery graph names (C1),
#: expressed as the raw pre-substitution hooks.json token each carrier's
#: OWN top-level entry declares -- fed through `tail_key()` below, never
#: hand-typed as a tail string, so a future rename of any of the four
#: cannot silently desync the constant from the actual join key.
_CARRIER_RAW_TOKENS = {
    "write_dispatch": "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/preuse-write-dispatch.py",
    "stop_family": "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/postuse-stop-family-dispatch.py",
    "bash_dispatch": "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/preuse-bash-dispatch.py",
    "advisory_dispatch": "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/postuse-advisory-dispatch.py",
}

#: The five confirmed retirees (AC-6) -- declared data, not discoverable by
#: scanning hooks.json, since two of the five are fully absent from it (not
#: merely commented) and the other three are comment-only mentions with no
#: live `args` entry. Each `reason` is C1's own finding for that retiree.
_RETIRED = (
    (
        "nudge-foreground-agent-dispatch.py",
        "Deregistered from hooks.json; folded into a pure-Python port inside enforce-agent-dispatch-mode.py that makes no engine-plane call at all.",
    ),
    (
        "runtime-tripwire-stop-watcher.py",
        "Stood down 2026-07-31 per PM ruling; reversible, comment-only mention remains in hooks.json.",
    ),
    (
        "guard-named-dispatch-tool-restriction.py",
        "Deregistered from hooks.json; folded into a pure-Python port inside enforce-agent-dispatch-mode.py.",
    ),
    (
        "track-touched-files.py",
        "Standalone Write|Edit|MultiEdit|NotebookEdit registration folded into postuse-advisory-dispatch.py's hooks.track_touched_files call; fully absent from hooks.json.",
    ),
    (
        "nudge-unauthorized-handoff.py",
        "Its standalone PostToolUse(Write) registration was folded into postuse-advisory-dispatch.py's direct nudge_unauthorized_handoff.advisory_text() call; fully absent from current hooks.json.",
    ),
)



class EmitterError(RuntimeError):
    """Any failure that must abort the write closed (AC-3's fail-loud
    exhaustiveness invariant, AC-4's held-not-blind sourcing, or the
    generator's own string contract, AC-5)."""


def tail_key(raw_token: str) -> str:
    """Two-segment, forward-slash-joined, lower-cased tail key -- matches
    the engine plane's own
    `coordinator_core/ops/session/guard_settings_integrity.py`
    `_tail_key`'s normal form exactly (last two path segments of the RAW
    token, before `${CLAUDE_PLUGIN_ROOT}` substitution or filesystem
    resolution). Reimplemented locally (`_tail_key` is a private helper,
    not an exported seam) rather than imported, per the plan's AC-2 text.

    A one-segment bare basename or a three-plus-segment over-qualified path
    both parse `hooks.json` fine and would join NOTHING against this
    function's output -- see this module's own docstring and the plan's
    anti-scope section. Raising here rather than returning `None` (unlike
    the engine plane's own `_tail_key`, which is a best-effort display helper) is
    deliberate: a token this generator cannot key is a generator defect,
    not a shape to silently skip.
    """
    # `PureWindowsPath` parses BOTH `/` and `\` as segment separators (it is
    # a pure, filesystem-inert path class -- safe to construct on any host
    # regardless of which separator the raw token happens to use), so this
    # sidesteps the hardcoded-separator normalization hack the prior
    # `.replace("\\", "/")` + regex form used.
    parts = PureWindowsPath(raw_token).parts
    if len(parts) < 2:
        raise EmitterError(f"token has no two-segment tail key: {raw_token!r}")
    return "/".join(parts[-2:]).lower()


def _check_string(label: str, value: Any) -> str:
    """AC-5's string contract, enforced at write/emit time -- single-line,
    printable-only, <=200 chars. Not left to the reader."""
    if not isinstance(value, str):
        raise EmitterError(f"{label} is not a string: {value!r}")
    if "\n" in value or "\r" in value:
        raise EmitterError(f"{label} is not single-line: {value!r}")
    if len(value) > MAX_STRING_LEN:
        raise EmitterError(
            f"{label} exceeds {MAX_STRING_LEN} chars ({len(value)}): {value!r}"
        )
    if not value.isprintable():
        raise EmitterError(f"{label} contains non-printable characters: {value!r}")
    return value


def _matcher_tool_names(matcher: str) -> List[str]:
    """A hooks.json `matcher` string ("" == every event of this hook type)
    read as a tool-name list -- `"Bash|PowerShell"` -> `["Bash",
    "PowerShell"]`, `""` -> `[]`. This is a carrier- or direct-registration-
    level READ, not a seed; per-guard values for the cross-plane bash
    carrier come from `guard_roster()` instead (AC-4/AC-10)."""
    return [tok for tok in matcher.split("|") if tok]


def _load_hooks_json() -> Dict[str, Any]:
    try:
        with HOOKS_JSON_PATH.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:  # noqa: BLE001 - fail closed, report why
        raise EmitterError(f"cannot read/parse hooks.json: {exc}") from exc


def _walk_registrations(
    doc: Dict[str, Any],
) -> Tuple[Dict[str, str], Dict[str, Set[str]]]:
    """Structurally partitions every hooks.json `args` array into
    registration tokens (main script token per hook entry) vs the bootstrap
    trampoline (`_hook_venv_inject.py`, `_hook_boot.py` -- always present,
    never a registration). `_comment` prose is never scanned -- only actual
    `args` arrays -- so a comment-only mention (e.g. a retired script) is
    correctly invisible to this walk (AC-3, AC-6).

    Returns `(raw_token_by_tail, matchers_by_tail)`: the first raw token
    seen for each tail key (for error messages / carrier resolution), and
    the union of every hook-block `matcher` string a tail key was
    registered under (a script CAN appear under >1 matcher block -- e.g.
    two distinct PreToolUse entries -- and AC-3's "exactly one" collapses
    those into one manifest entry, not one per hooks.json occurrence).
    """
    raw_token_by_tail: Dict[str, str] = {}
    matchers_by_tail: Dict[str, Set[str]] = {}

    hooks = doc.get("hooks")
    if not isinstance(hooks, dict):
        raise EmitterError("hooks.json has no top-level 'hooks' object")

    for event_name, entries in hooks.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            matcher = entry.get("matcher", "")
            if not isinstance(matcher, str):
                matcher = ""
            hook_list = entry.get("hooks", [])
            if not isinstance(hook_list, list):
                continue
            for hook in hook_list:
                if not isinstance(hook, dict):
                    continue
                args = hook.get("args", [])
                if not isinstance(args, list):
                    continue
                py_tokens = [a for a in args if isinstance(a, str) and a.endswith(".py")]
                for token in py_tokens:
                    key = tail_key(token)
                    if key in _TRAMPOLINE_TAILS:
                        continue
                    raw_token_by_tail.setdefault(key, token)
                    matchers_by_tail.setdefault(key, set()).add(matcher)

    return raw_token_by_tail, matchers_by_tail


def _import_engine_module(module_path: str):
    """Cross-plane read via `_engine_root.resolve_claude_klabauter_root()` -- the
    same fail-closed-here / fail-open-there seam `postuse-advisory-
    dispatch.py` and `preuse-bash-dispatch.py` already use to locate
    the engine plane, kept in lockstep deliberately (see those modules' own headers).
    Any resolution or import failure raises `EmitterError` here (the
    generator's job is to fail CLOSED, the opposite of the carriers'
    runtime fail-open), never falls through to a default value."""
    try:
        sys.path.insert(0, str(SCRIPTS_DIR))
        from _engine_root import resolve_claude_klabauter_root  # noqa: E402  pylint: disable=import-outside-toplevel
    except Exception as exc:  # noqa: BLE001
        raise EmitterError(f"cannot import _engine_root seam: {exc}") from exc

    root = resolve_claude_klabauter_root()
    if not root:
        raise EmitterError(
            "engine root did not resolve -- the engine-plane-sourced half of the "
            "manifest cannot be built; aborting closed rather than emitting "
            "a partial block"
        )
    if root not in sys.path:
        sys.path.insert(0, root)

    import importlib

    try:
        return importlib.import_module(module_path)
    except Exception as exc:  # noqa: BLE001
        raise EmitterError(
            f"cannot import {module_path} from resolved engine root {root!r}: {exc}"
        ) from exc


def _load_doe_local_guard_registry():
    """`_guard_runner.REAL_GUARD_REGISTRY` -- this repo's own module, sibling
    of this generator, no cross-plane read involved."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    import importlib

    module = importlib.import_module("_guard_runner")
    return module.REAL_GUARD_REGISTRY


def _load_engine_write_guard_names() -> List[Tuple[str, str, List[str]]]:
    """Cross-plane read of the write-guards engine's own module roster --
    `coordinator_core.write_guards.engine.discover_guard_names()`, the
    public seam (never the private `_discover_guards`). Returns
    `(guard_name, tail_key, matchers)` triples; a guard's tail is derived
    from the engine package's own dotted module path (`_PKG_NAME`), not by
    filename-globbing this repo's tree -- the two things this module's own
    negative spec rules out.

    `matchers` is each guard module's own public `MATCHERS` constant, read
    verbatim (mirroring how `build_carrier_bash_dispatch` takes its
    per-guard matchers from `guard_roster()` rather than the carrier-level
    hooks.json matcher) -- NOT the carrier matcher seeded uniformly onto
    every guard. A guard whose real `MATCHERS` is a strict subset of the
    carrier's (e.g. `nudge_em_code_dispatch`, deliberately excluding
    NotebookEdit) would otherwise be misreported as reachable on a tool it
    is not, defeating the manifest's own purpose.

    Any import failure reported back by `discover_guard_names()`, or any
    guard module exposing no usable `MATCHERS`, aborts closed: an
    under-reporting or falsely-widened manifest is exactly the failure mode
    this generator exists to prevent, so a partial or malformed result is
    treated the same as a total failure -- held, not silently truncated or
    defaulted.
    """
    module = _import_engine_module("coordinator_core.write_guards.engine")
    discover_guard_names = getattr(module, "discover_guard_names", None)
    if discover_guard_names is None:
        raise EmitterError(
            "coordinator_core.write_guards.engine has no discover_guard_names() "
            "export -- cannot source cross-plane write guards; aborting closed"
        )
    names, import_failed = discover_guard_names()
    if import_failed:
        raise EmitterError(
            "coordinator_core.write_guards.engine reported import_failed "
            f"guard module(s) {sorted(import_failed)!r} -- an under-counted "
            "manifest would be worse than none; aborting closed"
        )
    pkg_name = getattr(module, "_PKG_NAME", None)
    if not pkg_name:
        raise EmitterError(
            "coordinator_core.write_guards.engine has no _PKG_NAME -- cannot "
            "derive a tail key for its guard modules; aborting closed"
        )
    pkg_tail = pkg_name.split(".")[-1]

    import importlib

    result: List[Tuple[str, str, List[str]]] = []
    for name in names:
        try:
            guard_module = importlib.import_module(f"{pkg_name}.{name}")
        except Exception as exc:  # noqa: BLE001
            raise EmitterError(
                f"cannot re-import {pkg_name}.{name} to read its MATCHERS "
                f"constant: {exc}"
            ) from exc
        matchers = getattr(guard_module, "MATCHERS", None)
        if not isinstance(matchers, (list, tuple)) or not matchers:
            raise EmitterError(
                f"{pkg_name}.{name} has no usable MATCHERS constant -- held, "
                "not defaulted to the carrier matcher; aborting closed"
            )
        result.append((name, tail_key(f"{pkg_tail}/{name}.py"), list(matchers)))
    return result


def _load_doe_local_stop_family_registry():
    sys.path.insert(0, str(SCRIPTS_DIR))
    import importlib

    module = importlib.import_module("_stop_family_runner_contract")
    return module.ENROLLED_GUARD_MODULES


def _advisory_ops_delivered() -> List[str]:
    """Parses `postuse-advisory-dispatch.py`'s own `dispatch_message()`
    call sites for their `"method"` values -- AC-11's doctrine-plane-derived op list,
    NOT a transcription of the engine plane's `list_ported_advisory_ops()` six-name tuple
    (C1 proved only 1 of those 6 is actually delivered by this carrier).
    Structural (regex over the literal `"method": "hooks.<name>"` pairs
    this module's own dict-literal source contains, quote-style-tolerant so a
    reformat from double- to single-quoted dict literals doesn't silently
    drop a call site), not an import -- the carrier module fails open on an
    unresolved engine plane and has no listing API of its own to call.

    Residual fragility, stated honestly: this is a structural parse of
    another file's source, not a real parser -- a sufficiently different
    reformat (e.g. a computed `method=` kwarg, or the literal split across
    lines) can still defeat it. The non-empty check below only proves SOME
    match was found, not that ALL call sites were found; this function feeds
    AC-11, where under-reporting the delivered op set is exactly the failure
    mode the manifest exists to prevent."""
    source_path = SCRIPTS_DIR / "postuse-advisory-dispatch.py"
    try:
        text = source_path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        raise EmitterError(f"cannot read {source_path}: {exc}") from exc

    ops = sorted(
        set(re.findall(r'["\']method["\']\s*:\s*["\'](hooks\.[A-Za-z0-9_]+)["\']', text))
    )
    if not ops:
        raise EmitterError(
            f"no dispatch_message 'method' literals found in {source_path} -- "
            "advisory-carrier op list cannot be derived; aborting closed"
        )
    return ops


def build_carrier_write_dispatch(matchers_by_tail: Dict[str, Set[str]]) -> Dict[str, Any]:
    carrier_tail = tail_key(_CARRIER_RAW_TOKENS["write_dispatch"])
    carrier_matcher_tokens = matchers_by_tail.get(carrier_tail, set())
    if len(carrier_matcher_tokens) != 1:
        raise EmitterError(
            f"write_dispatch carrier ({carrier_tail}) matcher is not singular in "
            f"hooks.json: {carrier_matcher_tokens!r}"
        )
    carrier_matcher = next(iter(carrier_matcher_tokens))
    carrier_tool_names = _matcher_tool_names(carrier_matcher)

    registry = _load_doe_local_guard_registry()
    guards = []
    for entry in registry:
        guard_id = _check_string("write_dispatch guard id", entry.module_key)
        guard_tail = tail_key(entry.module_path)
        guards.append(
            {
                "id": guard_id,
                "script": _check_string("write_dispatch guard script", guard_tail),
                "tool_names": [
                    _check_string("write_dispatch guard tool_names[]", t)
                    for t in carrier_tool_names
                ],
            }
        )

    for name, guard_tail, guard_matchers in _load_engine_write_guard_names():
        guards.append(
            {
                "id": _check_string("write_dispatch guard id", name),
                "script": _check_string("write_dispatch guard script", guard_tail),
                "tool_names": [
                    _check_string("write_dispatch guard tool_names[]", t)
                    for t in guard_matchers
                ],
            }
        )
    return {
        "script": carrier_tail,
        "matcher": _check_string("write_dispatch carrier matcher", carrier_matcher),
        "guards": guards,
    }


def build_carrier_stop_family(matchers_by_tail: Dict[str, Set[str]]) -> Dict[str, Any]:
    carrier_tail = tail_key(_CARRIER_RAW_TOKENS["stop_family"])
    carrier_matcher_tokens = matchers_by_tail.get(carrier_tail, set())
    if len(carrier_matcher_tokens) != 1:
        raise EmitterError(
            f"stop_family carrier ({carrier_tail}) matcher is not singular in "
            f"hooks.json: {carrier_matcher_tokens!r}"
        )
    carrier_matcher = next(iter(carrier_matcher_tokens))
    carrier_tool_names = _matcher_tool_names(carrier_matcher)

    filenames = _load_doe_local_stop_family_registry()
    guards = []
    for filename in filenames:
        guard_tail = tail_key(f"hooks/scripts/{filename}")
        guards.append(
            {
                "id": _check_string("stop_family guard id", filename),
                "script": _check_string("stop_family guard script", guard_tail),
                "tool_names": [
                    _check_string("stop_family guard tool_names[]", t)
                    for t in carrier_tool_names
                ],
            }
        )
    return {
        "script": carrier_tail,
        "matcher": _check_string("stop_family carrier matcher", carrier_matcher),
        "guards": guards,
    }


def build_carrier_bash_dispatch(matchers_by_tail: Dict[str, Set[str]]) -> Dict[str, Any]:
    carrier_tail = tail_key(_CARRIER_RAW_TOKENS["bash_dispatch"])
    carrier_matcher_tokens = matchers_by_tail.get(carrier_tail, set())
    if len(carrier_matcher_tokens) != 1:
        raise EmitterError(
            f"bash_dispatch carrier ({carrier_tail}) matcher is not singular in "
            f"hooks.json: {carrier_matcher_tokens!r}"
        )
    carrier_matcher = next(iter(carrier_matcher_tokens))
    carrier_matcher_set = set(_matcher_tool_names(carrier_matcher))

    module = _import_engine_module("coordinator_core.bash_guards")
    guard_roster = getattr(module, "guard_roster", None)
    if guard_roster is None:
        raise EmitterError(
            "coordinator_core.bash_guards has no guard_roster() export -- "
            "cannot source cross-plane guard matchers; aborting closed"
        )
    roster = guard_roster()

    guards = []
    union_tool_names: Set[str] = set()
    for entry in roster:
        matchers = getattr(entry, "matchers", None)
        if not matchers:
            raise EmitterError(
                f"guard_roster() entry {getattr(entry, 'id', '?')!r} has no "
                "readable matchers -- held, not seeded blind; aborting closed"
            )
        guard_id = _check_string("bash_dispatch guard id", entry.id)
        guard_tail = tail_key(entry.script)
        tool_names = [_check_string("bash_dispatch guard tool_names[]", t) for t in matchers]
        union_tool_names.update(tool_names)
        guards.append({"id": guard_id, "script": guard_tail, "tool_names": tool_names})

    if not union_tool_names.issubset(carrier_matcher_set):
        raise EmitterError(
            "bash_dispatch carrier matcher "
            f"{sorted(carrier_matcher_set)} does not cover the union of its "
            f"delivered guards' tool_names {sorted(union_tool_names)} -- AC-9 "
            "violation, a guard is unreachable under a tool name it declares"
        )

    return {
        "script": carrier_tail,
        "matcher": _check_string("bash_dispatch carrier matcher", carrier_matcher),
        "guards": guards,
    }


def build_carrier_advisory_dispatch(matchers_by_tail: Dict[str, Set[str]]) -> Dict[str, Any]:
    carrier_tail = tail_key(_CARRIER_RAW_TOKENS["advisory_dispatch"])
    carrier_matcher_tokens = matchers_by_tail.get(carrier_tail, set())
    if len(carrier_matcher_tokens) != 1:
        raise EmitterError(
            f"advisory_dispatch carrier ({carrier_tail}) matcher is not singular "
            f"in hooks.json: {carrier_matcher_tokens!r}"
        )
    carrier_matcher = next(iter(carrier_matcher_tokens))

    ops = [_check_string("advisory_dispatch op id", op) for op in _advisory_ops_delivered()]

    return {
        "script": carrier_tail,
        "matcher": _check_string("advisory_dispatch carrier matcher", carrier_matcher),
        "guards": [],
        "ops": ops,
    }


def build_direct_entries(
    raw_token_by_tail: Dict[str, str],
    matchers_by_tail: Dict[str, Set[str]],
    carrier_tails: Set[str],
) -> List[Dict[str, Any]]:
    direct = []
    for tail, _raw in sorted(raw_token_by_tail.items()):
        if tail in carrier_tails:
            continue
        tool_names = sorted(
            {t for m in matchers_by_tail.get(tail, set()) for t in _matcher_tool_names(m)}
        )
        direct.append(
            {
                "id": _check_string("direct entry id", tail.split("/")[-1]),
                "script": _check_string("direct entry script", tail),
                "tool_names": [
                    _check_string("direct entry tool_names[]", t) for t in tool_names
                ],
            }
        )
    return direct


def build_retired_entries() -> List[Dict[str, Any]]:
    retired = []
    for filename, reason in _RETIRED:
        tail = tail_key(f"hooks/scripts/{filename}")
        retired.append(
            {
                "id": _check_string("retired entry id", filename),
                "script": _check_string("retired entry script", tail),
                "reason": _check_string("retired entry reason", reason),
            }
        )
    return retired


def _run_git(*args: str) -> str:
    """Runs `git <args>` with `cwd=REPO_ROOT`, an explicit timeout, and
    never `shell=True`. Any non-zero exit, missing `git`, or timeout raises
    `EmitterError` -- resolving emission provenance fails closed like every
    other half of this generator (this module's own docstring)."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise EmitterError(f"cannot run 'git {' '.join(args)}': {exc}") from exc
    if result.returncode != 0:
        raise EmitterError(
            f"'git {' '.join(args)}' exited {result.returncode}: {result.stderr.strip()}"
        )
    return result.stdout


def _emission_provenance() -> Dict[str, Any]:
    """Resolves `PROVENANCE_KEYS` at emission time: the full HEAD SHA, a
    UTC ISO-8601 second-precision `Z`-suffixed timestamp, and whether the
    working tree has uncommitted changes to TRACKED files
    (`--untracked-files=no`, so a peer session's scratch files never flip
    this flag). Fails closed (`EmitterError`) on any git resolution
    failure -- see this module's docstring."""
    sha = _run_git("rev-parse", "HEAD").strip()
    if len(sha) != 40 or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise EmitterError(f"'git rev-parse HEAD' did not return a 40-char hex SHA: {sha!r}")

    status = _run_git("status", "--porcelain", "--untracked-files=no")
    dirty = bool(status.strip())

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "generated_from_sha": sha,
        "generated_at": generated_at,
        "generated_from_dirty_tree": dirty,
    }


def build_block() -> Dict[str, Any]:
    """The manifest block for the current `hooks.json`.

    Returns the block alone. Callers needing the snapshot it was validated
    against -- the write path -- use `build_block_with_doc()`; keeping that
    on a separate name holds this function's single-value contract stable
    for its read-only consumers (the drift test among them)."""
    return build_block_with_doc()[1]


def build_block_with_doc() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Returns `(doc, block)` -- the single `hooks.json` snapshot this build
    validated against, alongside the computed manifest block. `write_block`
    takes this same `doc` rather than re-reading the file, so validation and
    write operate on one snapshot: a second independent read here would let
    a concurrent `hooks.json` edit land between the two reads, producing a
    manifest validated against one snapshot and spliced into another --
    exactly the "stale is worse than absent" state this module's docstring
    says the generator exists to prevent."""
    doc = _load_hooks_json()
    raw_token_by_tail, matchers_by_tail = _walk_registrations(doc)

    carrier_write_dispatch = build_carrier_write_dispatch(matchers_by_tail)
    carrier_stop_family = build_carrier_stop_family(matchers_by_tail)
    carrier_bash_dispatch = build_carrier_bash_dispatch(matchers_by_tail)
    carrier_advisory_dispatch = build_carrier_advisory_dispatch(matchers_by_tail)

    carrier_list = [
        carrier_write_dispatch,
        carrier_stop_family,
        carrier_bash_dispatch,
        carrier_advisory_dispatch,
    ]
    # Map shape, keyed by each carrier's own tail key -- the engine plane's
    # reader (`hook_delivery_manifest.py`) requires `carriers` to be a JSON
    # object keyed by carrier script tail, each value an object carrying a
    # `guards` list. A list here parses but fails the reader's shape check
    # (`carriers field is not an object`) -- see this plan's Problem section.
    # `matcher` stays inside each value: it is load-bearing for our own
    # AC-9 union check and the reader ignores unknown keys in a carrier body.
    carriers = {c["script"]: c for c in carrier_list}
    carrier_tails = set(carriers)

    direct = build_direct_entries(raw_token_by_tail, matchers_by_tail, carrier_tails)
    retired = build_retired_entries()

    # AC-3 exhaustiveness: every registration token discovered by the walk
    # must land in exactly one of carriers[*].guards[*] / direct[*]. The
    # walk and carrier/direct partition are constructed so this is true by
    # construction for every walked token; this pass is the structural
    # PROOF, not a hope -- it recomputes membership counts independently
    # and fails loud on any drift, including a retired tail resurfacing in
    # hooks.json without this generator's retired list being updated.
    seen_tails: Dict[str, int] = {}
    for carrier in carriers.values():
        for guard in carrier["guards"]:
            seen_tails[guard["script"]] = seen_tails.get(guard["script"], 0) + 1
    for entry in direct:
        seen_tails[entry["script"]] = seen_tails.get(entry["script"], 0) + 1

    for tail in raw_token_by_tail:
        count = seen_tails.get(tail, 0)
        if tail in carrier_tails:
            # carrier's own top-level token is not itself a "guard" entry;
            # it is the carrier key. Skip the membership-count check for it.
            continue
        if count != 1:
            raise EmitterError(
                f"AC-3 exhaustiveness violation: tail {tail!r} appears in "
                f"{count} of carriers[*].guards[*]/direct[*] (want exactly 1)"
            )

    retired_tails = {r["script"] for r in retired}
    overlap = retired_tails & set(raw_token_by_tail)
    if overlap:
        raise EmitterError(
            f"AC-3 exhaustiveness violation: retired tail(s) {sorted(overlap)} "
            "are live registrations in hooks.json -- retired list is stale"
        )

    block = {
        "version": 1,
        **_emission_provenance(),
        "carriers": carriers,
        "direct": direct,
        "retired": retired,
    }
    return doc, block


def render_block(block: Dict[str, Any]) -> str:
    """Deterministic serialization (AC-8): stable key order (dicts built in
    fixed field order above; `json.dumps` preserves insertion order), no
    timestamps in the delivery-graph body -- the provenance keys
    (`PROVENANCE_KEYS`) are deliberately exempt and are why the
    idempotence comparison strips them -- and sorted collections wherever
    ordering isn't otherwise load-bearing (direct[] is already tail-sorted;
    guards/ops/retired preserve their natural source order, which is
    itself stable across runs -- registry tuples, `guard_roster()`'s own
    list order, and a fixed retired-tuple literal).

    `ensure_ascii=False` is load-bearing, not cosmetic: the default re-escapes
    every non-ASCII character to `\\uXXXX`. `write_block` re-serializes the whole
    document, so the default turns a purely additive write into one that also
    rewrites unrelated `_comment` prose elsewhere in the file -- collateral hunks
    over a file a concurrent session is editing."""
    return json.dumps(
        {"x-effective-delivery": block},
        indent=2,
        sort_keys=False,
        ensure_ascii=False,
    )


def write_block(doc: Dict[str, Any], block: Dict[str, Any]) -> None:
    """Writes into the SAME `doc` `build_block()` validated against -- never
    a fresh read -- so the write can't land against a `hooks.json` snapshot
    that has moved since exhaustiveness validation ran (see `build_block`'s
    own docstring)."""
    doc["x-effective-delivery"] = block

    tmp_path = HOOKS_JSON_PATH.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=False, ensure_ascii=False)
        fh.write("\n")
    tmp_path.replace(HOOKS_JSON_PATH)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the block into coordinator/hooks/hooks.json in place "
        "(default: print mode, mutates nothing).",
    )
    args = parser.parse_args(argv)

    try:
        doc, block = build_block_with_doc()
    except EmitterError as exc:
        print(f"emit_effective_delivery: FAILED CLOSED: {exc}", file=sys.stderr)
        return 1

    if args.write:
        try:
            write_block(doc, block)
        except EmitterError as exc:
            print(f"emit_effective_delivery: FAILED CLOSED on write: {exc}", file=sys.stderr)
            return 1
        print(f"emit_effective_delivery: wrote block into {HOOKS_JSON_PATH}", file=sys.stderr)
        return 0

    print(render_block(block))
    return 0


if __name__ == "__main__":
    sys.exit(main())
