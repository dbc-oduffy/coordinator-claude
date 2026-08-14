"""PostToolUse(Write) advisory nudge: warns, at write time, when a
brand-NEW file lands carrying a violation that TWO existing shrink-only
ratchets hold new files to a ZERO budget for — a defect an author copying
an adjacent file's idiom reliably reintroduces, and that today only a full
test-tier run (minutes to hours later) catches.

Why this exists (three real incidents, one session, 2026-07-31)
------------------------------------------------------------------
1. `coordinator/bin/check-auto-memory-drained.py` (engine plane) copied
   its docstring wording from `check-harvest-debt.py` and inherited three
   sibling-repo-name mentions — `test_oss_payload_locality.py` red
   (engine-plane commit `ee631dae`).
2. `coordinator/bin/safe-commit-offer.py` (engine plane) did the same an
   hour later, in a session that had the rule stated explicitly in its
   brief (engine-plane commit `1e933eac`).
3. `coordinator/hooks/scripts/sessionend-auto-commit.py` (this repo)
   carried a `#!/usr/bin/env python3` shebang copied from its sibling
   `sessionend-archive-session.py`, whose identical line is baselined —
   `test_posix_exec_assumptions_baseline.py` red (this repo's commit
   `013c2040b`).

Every one was caught only by a full test-tier run. The rule (both
ratchets) is correct; the FEEDBACK TIMING is the defect this hook closes.
Per this repo's own discharge test (`docs/wiki/invisible-doctrine.md`): if
the discharge is "the author remembers to check", the work is not
finished.

Design: OFFER, not BLOCK
-------------------------
Advisory only (PostToolUse exit 2 + stderr, matching
`nudge-initiative-goals-ladder.py`'s contract) — never denies. The author
is doing something reasonable (copying a neighbour's idiom); a hard block
here would fight that, not correct it. A DIFFERENT, pre-existing hook
(`guard-oss-payload-locality.py`) already hard-denies the SAME locality
defect class, but only within this clone's own local OSS payload
(`hooks/`, `skills/`, `agents/`, `commands/`, `snippets/`) — see
`_oss_payload.py`'s own coverage-asymmetry note. This hook is
DELIBERATELY advisory rather than a second hard-deny layer over that same
local slice, and it reaches further: it also covers the two engine-plane-resident
payload legs (`coordinator/bin`, `coordinator/lib`, via `source_map`) that
a write-time hard-deny guard rooted in this repo
structurally cannot reach (a write to those paths happens in the sibling
repo's own tree — but this session's Write tool call still carries an
absolute path there, which this hook can inspect regardless of which
repo's tree it lands in).

Reuses the existing detectors, does not re-derive them
---------------------------------------------------------
  - Locality: `_prompt_surface_locality.iter_violations` (this repo). A
    brand-new file's "before" is empty, so every violation `iter_violations`
    finds against the just-written text is, by construction, a NEW one —
    no need for the before/after diff machinery `new_violations` provides
    for the edit-to-existing-file case.
  - POSIX-exec: `coordinator_core.ops.check_posix_exec_assumptions`
    (engine plane), imported in-process via `_engine_root`. Only the
    byte-level `env_shebang`/`extensionless_exec` classes are checked here
    (mirroring `scan()`'s own two-line byte tests exactly — see
    `_ENV_SHEBANG_PREFIX` below) plus the AST-based `path_separator` /
    `posix_mode_bits` / `implicit_encoding` classes via that module's own
    per-file `_scan_python_file` helper, reused directly rather than
    copied. `EXEMPTIONS` is consulted for every class so a genuine,
    already-ratified carve-out never nudges. `mode_100755` is NOT covered
    — it is a git INDEX fact that does not exist until `git add` runs, and
    approximating it from the OS executable bit was judged not
    "structurally the same" (Write-tool-created files are never
    OS-executable at write time, so the proxy would essentially never
    fire) — named here rather than silently absent.

Scope test — payload-shaped, not git-tracked
------------------------------------------------
Both existing ratchets test membership via `git ls-files` (a file must
already be TRACKED to count) — useless for a hook that must fire on the
very first `Write` of a brand-new, as-yet-untracked file. `_payload_shaped`
below instead tests the same ADMISSION DATA those detectors read
(`setup/publish-targets.portable`'s mirror-row allowlist/source_map, and
`coordinator/.percolate-ignore`'s exclusion patterns, both via
`_oss_payload.py`'s own parsing functions) against the candidate path's
SHAPE alone — no git-tracked-ness required. This is not a second
allowlist: it is the same ratified data, read the same way, just not
gated on the file already being in the index.

Newness test — git, not mtime
----------------------------------
`git ls-files --error-unmatch -- <relpath>` against the target's own repo
index: nonzero (not tracked) means new. An Edit/MultiEdit to an existing
(even untracked-but-already-nudged-once) file never reaches this check at
all — only `Write` is a guarded tool, matching "NEW FILES ONLY" (an Edit
to an existing tracked file is exactly the grandfathering the ratchets'
baselines exist to express, and firing there would be pure noise).

Contract (mirrors `nudge-initiative-goals-ladder.py`):
  stdin   -- PostToolUse JSON (tool_name, tool_input, cwd, ...)
  stdout  -- nothing on suppress
  stderr  -- an envelope-composed advisory message when firing (see
            `_message_envelope.py` and `_WIKI_ANCHOR` below)
  exit 0  -- silent suppression / no-op (fail-open at every uncertain step)
  exit 2  -- advisory nudge fired (stderr reaches the model's next turn)

Escape hatch: COORDINATOR_NEW_FILE_RATCHET_NUDGE_OFF=1 (autonomous runs).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

import _message_envelope as _envelope  # noqa: E402
import _oss_payload  # noqa: E402
import _prompt_surface_locality as _locality  # noqa: E402
from _engine_root import resolve_claude_klabauter_root as _resolve_claude_klabauter_root  # noqa: E402

#: Wiki section carrying the full remedy explanations and the escape hatch
#: (COORDINATOR_NEW_FILE_RATCHET_NUDGE_OFF=1) this hook's message used to
#: state inline -- see docs/plans/2026-08-02-guard-message-character-cap.md
#: § C6 and state/relocations/guard-message-cap/
#: nudge-new-file-zero-budget-ratchets.py.md.
_WIKI_ANCHOR = (
    # Review: code-reviewer -- bare fragment produced an unresolvable
    # `render()` citation. Full path matches every other converted hook.
    "coordinator/docs/wiki/guard-message-concision.md"
    "#new-file-zero-budget-ratchet-remedies"
)

#: Mirrors `_oss_payload.py::_oss_payload.py`'s own module-level constant
#: shape: resolved once, degrades to a no-op on any load failure rather
#: than raising, matching every other carve-out loader in this tree.
_LOCAL_ROOT = _oss_payload.REPO_ROOT.resolve()

#: Byte-for-byte the same test `check_posix_exec_assumptions.scan()` runs
#: (`head.startswith(b"#!/usr/bin/env")`) -- a fixed byte literal, not a
#: re-derivation of any classification logic, so there is nothing here to
#: drift out of sync with the gate it predicts.
_ENV_SHEBANG_PREFIX = b"#!/usr/bin/env"


def _git_ls_files_error_unmatch(repo_root: str, relpath: str) -> bool:
    """True iff `relpath` is already tracked in `repo_root`'s git index."""
    try:
        proc = subprocess.run(
            ["git", "-C", repo_root, "ls-files", "--error-unmatch", "--", relpath],
            capture_output=True,
            text=True,
            timeout=5.0,
            creationflags=_NO_WINDOW,
        )
    except Exception:
        # Fail open toward "treat as new" -- an unresolvable git call means
        # we cannot prove this file is a pre-existing, already-baselined
        # one, and a false-positive nudge is far cheaper than a missed one.
        return False
    return proc.returncode == 0


def _classify_leg(candidate: Path):
    """`(leg, root, rel)` for `candidate` if it resolves inside this
    repo's own tree ("local") or a resolvable engine-plane checkout
    ("engine"); `None` if neither -- fail-open, no nudge for a path this
    hook can't place."""
    try:
        rel_local = candidate.relative_to(_LOCAL_ROOT)
        return "local", _LOCAL_ROOT, rel_local
    except ValueError:
        pass

    engine_root_str = _resolve_claude_klabauter_root()
    if engine_root_str:
        try:
            engine_root = Path(engine_root_str).resolve()
            rel_engine = candidate.relative_to(engine_root)
            return "engine", engine_root, rel_engine
        except Exception:
            pass

    return None


def _payload_shaped(leg: str, rel: Path) -> "str | None":
    """The `coordinator/...`-rooted relpath (string, POSIX form) the file
    would occupy in ITS OWN repo's payload accounting if `candidate` is
    shaped like an admitted OSS-payload entry -- the same
    `setup/publish-targets.portable` allowlist/source_map and
    `coordinator/.percolate-ignore` exclusions `_oss_payload.py` already
    parses, just tested against the candidate's PATH SHAPE rather than its
    git-tracked status (see module docstring). `None` if not payload-shaped
    or on any parse failure (fail-open)."""
    try:
        row = _oss_payload.parse_mirror_row()
        patterns = _oss_payload.excluded_patterns()
    except Exception:
        return None

    parts = rel.as_posix().split("/")

    if leg == "local":
        if len(parts) < 2 or parts[0] != "coordinator":
            return None
        entry = parts[1]
        routed = _oss_payload._routed_entries(row.source_map)
        if entry not in row.allowlist or entry in routed:
            return None
        rel_to_coordinator = "/".join(parts[1:])
        if _oss_payload._is_excluded(rel_to_coordinator, patterns):
            return None
        return "coordinator/" + rel_to_coordinator

    if leg == "engine":
        for token, entries in row.source_map.items():
            try:
                _repo_name, subpath = _oss_payload._parse_source_map_token(token)
            except Exception:
                continue
            subparts = subpath.split("/")
            if parts[: len(subparts)] != subparts:
                continue
            rest = parts[len(subparts):]
            if not rest or rest[0] not in entries:
                continue
            rel_to_coordinator = "/".join(rest)
            if _oss_payload._is_excluded(rel_to_coordinator, patterns):
                return None
            return "coordinator/" + rel_to_coordinator

    return None


def _locality_findings(text: str, candidate: Path) -> list:
    if candidate.suffix not in (".py", ".md"):
        return []
    try:
        return _locality.iter_violations(text, path=candidate)
    except Exception:
        return []


def _posix_exec_findings(repo_root: Path, relpath_str: str, candidate: Path) -> list:
    """`[(class_name, detail), ...]` for every zero-budget POSIX-exec-
    assumption class the new file's content trips, EXEMPTIONS-filtered.
    Fail-open (`[]`) if the engine module can't be imported."""
    engine_root_str = _resolve_claude_klabauter_root()
    if not engine_root_str:
        return []
    # STOP-FAMILY-RUNNER-CONTRACT clause 8 (sys.path ordering, mirroring
    # GUARD-ON-RUNNER-CONTRACT's identical clause): append, never insert at
    # index 0 -- the hooks dir (inserted at the top of this module, before
    # this point) must stay AHEAD of the sibling engine root on sys.path,
    # so a module-name collision resolves toward the doctrine-plane-local helper.
    if engine_root_str not in sys.path:
        sys.path.append(engine_root_str)
    try:
        import coordinator_core.ops.check_posix_exec_assumptions as posix_check
    except Exception:
        return []

    def _exempt(cls: str) -> bool:
        try:
            return relpath_str in posix_check.EXEMPTIONS.get(cls, {})
        except Exception:
            return False

    findings: list = []

    try:
        head = candidate.read_bytes()[:64]
    except OSError:
        head = b""

    if head.startswith(_ENV_SHEBANG_PREFIX) and not _exempt("env_shebang"):
        findings.append(("env_shebang", "first line is a `#!/usr/bin/env ...` shebang"))

    base = os.path.basename(relpath_str)
    if "." not in base and head.startswith(b"#!") and not _exempt("extensionless_exec"):
        findings.append(("extensionless_exec", "no file extension, but starts with `#!`"))

    if candidate.suffix == ".py":
        try:
            hits: dict = {
                "path_separator": set(),
                "posix_mode_bits": set(),
                "unresolved_cross_path": set(),
                "unclassified": set(),
                "implicit_encoding": set(),
            }
            posix_check._scan_python_file(relpath_str, candidate, hits)
            for cls in ("path_separator", "posix_mode_bits", "implicit_encoding"):
                if relpath_str in hits.get(cls, ()) and not _exempt(cls):
                    findings.append((cls, "see " + relpath_str))
        except Exception:
            pass

    return findings


#: Short remedy PROSE for the first locality violation kind found -- the
#: full explanation (why, and the DR-047 rationale) relocates to
#: `_WIKI_ANCHOR`, per state/relocations/guard-message-cap/
#: nudge-new-file-zero-budget-ratchets.py.md.
#:
#: Review: code-reviewer, Finding 3 -- these are noun-phrase remedy
#: descriptions, not runnable commands or paths, so they belong in the
#: counted `prose`, not the char-cap-EXEMPT `alternative` slot (that slot
#: is reserved for a copy-pasteable command/diff/path; some of these
#: strings only dodged `validate_alternative_shape`'s cheap heuristic by
#: accident -- see the sibling `_message_envelope.py` fix for the
#: heuristic gap itself). Folded into prose here rather than reshaped into
#: fake commands.
_LOCALITY_SHORT_ALT = {
    "private sibling-repo-name attribution": "use IRREDUCIBLE_LITERALS in _oss_operative_strings.py",
    "drive-rooted windows path": "use pathlib.Path instead of a raw backslash path",
}

#: Short remedy PROSE for the first POSIX-exec-assumption class found --
#: the full explanation (including the EXEMPTIONS-file escape hatch for a
#: genuine direct-exec entrypoint) relocates to `_WIKI_ANCHOR`. See the
#: Finding-3 note above `_LOCALITY_SHORT_ALT` -- same reasoning applies.
_POSIX_SHORT_ALT = {
    "env_shebang": "delete the shebang line",
    "extensionless_exec": "add a .py extension",
    "path_separator": "use os.path.join or pathlib",
    "posix_mode_bits": "avoid os.chmod exec-bit checks",
    "implicit_encoding": 'add encoding="utf-8" to open()',
}


def _compose_nudge_message(relpath_str: str, locality: list, posix_hits: list) -> "_envelope.Message":
    """Pure composer for the zero-budget-ratchet nudge -- separated from
    `main()`'s stdin plumbing so C1b's in-process measurement harness can
    call it directly across a sweep of (locality-only, posix-only, both)
    branches, per the plan's Measurement mechanism section. Routes through
    `_message_envelope.compose` (docs/plans/2026-08-02-guard-message-
    character-cap.md § C6): the diagnosis names the violated kinds, one
    short remedy for the first kind found rides in the counted `prose`
    (not the exempt `alternative` slot -- see Finding 3 note above), and
    the rest of the explanation (including every remedy this hook used to
    spell out in full, and the COORDINATOR_NEW_FILE_RATCHET_NUDGE_OFF=1
    escape hatch) relocates to `_WIKI_ANCHOR`."""
    kinds = [v.kind for v in locality] + [cls for cls, _detail in posix_hits]
    count = len(kinds)
    shown = kinds[:3]
    kinds_text = ", ".join(shown)
    if count > len(shown):
        kinds_text += ", +{} more".format(count - len(shown))

    remedy = None
    if locality:
        remedy = _LOCALITY_SHORT_ALT.get(locality[0].kind)
    elif posix_hits:
        remedy = _POSIX_SHORT_ALT.get(posix_hits[0][0])

    prose = (
        "{}: {} zero-budget violation(s) absent from baseline: {}.".format(
            relpath_str, count, kinds_text
        )
    )
    if remedy:
        prose += " Fix: {}.".format(remedy)

    return _envelope.compose(prose, anchor=_WIKI_ANCHOR)


def main() -> int:
    if os.environ.get("COORDINATOR_NEW_FILE_RATCHET_NUDGE_OFF", "0") == "1":
        return 0

    try:
        raw = sys.stdin.read()
    except Exception:
        return 0
    if not raw:
        return 0

    try:
        payload = json.loads(raw)
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0

    if payload.get("tool_name") != "Write":
        return 0

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0

    file_path = tool_input.get("file_path")
    content = tool_input.get("content")
    if not isinstance(file_path, str) or not file_path:
        return 0
    if not isinstance(content, str):
        return 0

    try:
        candidate = Path(file_path).resolve()
    except Exception:
        return 0

    leg_info = _classify_leg(candidate)
    if leg_info is None:
        return 0
    leg, repo_root, rel = leg_info

    relpath_str = _payload_shaped(leg, rel)
    if relpath_str is None:
        return 0

    if _git_ls_files_error_unmatch(str(repo_root), relpath_str):
        return 0  # already tracked -- not a new file, out of scope

    locality = _locality_findings(content, candidate)
    posix_hits = _posix_exec_findings(repo_root, relpath_str, candidate)

    if not locality and not posix_hits:
        return 0

    message = _compose_nudge_message(relpath_str, locality, posix_hits)
    rc = _envelope.emit(message, _envelope.CHANNEL_STOP)
    return rc if rc is not None else 0


if __name__ == "__main__":
    sys.exit(main())
