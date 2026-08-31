#!/usr/bin/env python3
"""SessionStart hook: assert EM identity to the main coordinator session.

Separate from project-orientation.py on purpose (design decision, not a
re-litigable choice): orientation content is staleness-nudged and
suppressible (`COORDINATOR_REPOMAP_STATUS_OFF` et al., and the whole banner
degrades quietly on a missing cache) — a role assertion riding the same
channel would inherit that suppressibility, and a role assertion that can be
silently switched off is worse than none at all. This hook has exactly one
job, unconditionally: tell the main session it is the EM.

Why this needs to exist at all: the always-loaded doctrine corpus
(formerly `coordinator/CLAUDE.md`, retired 2026-07-27 and split into
`global-doctrine/CLAUDE.md` (all-agents) and `coordinator/snippets/
em-operating-doctrine.md` (EM-only)) was rewritten into role-neutral
system terms as part of the computed-skills frontage work, so it no
longer itself tells the reader "you are the EM". `snippets/agent-role-em.md`
is the single source of truth for that assertion — this hook's only
responsibility is delivering it into the main session's context via its
SessionStart stdout, unconditionally, every session. There is no
`additionalContext` channel in play here -- this hook writes raw bytes to
stdout (see `_w()` below), which the harness folds into session context by
its own SessionStart stdout convention, not by any structured
`hookSpecificOutput.additionalContext` field.

Delivery is by an ORDERED MANIFEST of EM-only snippets (`_EM_SNIPPET_MANIFEST`
below), not a single hardcoded path — `agent-role-em.md` is the resident
role-assertion core, budgeted under the 2KB-First Rule
(`coordinator/docs/wiki/doctrine-channel-purposes.md:175`). Fuller
EM-addressed operating doctrine (`em-operating-doctrine.md`) is deliberately
NOT a manifest entry: it fires at a moment that names itself (the EM's own
first dispatch), so it is read via the resident core's trigger-named pointer
rather than paid for on every boot. Snippets are concatenated in manifest
order into this hook's stdout emission. The manifest is the extension point
for future EM-only channels that must be resident at boot — add an entry
here, not a second hook.

Manifest entries resolve against one of two roots, named per entry:

- `PLUGIN` — relative to `<plugin_root>/snippets/`. Fleet-wide doctrine
  shipped by coordinator itself; the same bytes reach every repo.
- `REPO` — relative to the CONSUMER REPO's root. This is the slot a
  consumer repo uses to put its own EM-only content into this channel
  without forking the hook: drop a file at the declared path and it is
  delivered, last, into the same emission.

Why the REPO slot exists at all: audience-narrowing beats stating content
in full, and stating it in full beats relocating it to a wiki nobody
reloads. Without a consumer-repo slot, a repo trying to move EM-only
content OUT of its always-loaded `CLAUDE.md` had no narrower channel to
move it INTO, and the only remaining move was relocation — the weakest
option — dressed up as a discharge. This slot is the missing rung.

Trust boundary: the REPO slot's file is repo-local content delivered into
the repo's own main session, exactly like that repo's `CLAUDE.md`. It
introduces no trust level the session did not already have.

Degradation is deliberately ASYMMETRIC by root. A missing PLUGIN entry is
a broken install and emits a loud per-entry banner. A missing REPO entry
is the overwhelmingly common case — most repos will never define one — so
absence is silent and the emission is byte-identical to a build without
the slot. A REPO file that EXISTS but cannot be read is not absence; that
is a real defect and banners loudly.

Main-session-only by construction: SessionStart-class hooks fire only for
the main session, never for an `Agent`-tool dispatch (that's the harness
property this hook relies on, not something it re-checks — see hooks.json's
registration comment for this entry, whose matcher enumerates every
SessionStart source the harness emits, so the channel re-fires at every
fresh-context boundary rather than only at cold start). No additional
is-main-session guard is layered on top here.

Path resolution mirrors project-orientation.py: this file's own location
(`Path(__file__)`), never cwd, never a hardcoded absolute path — must work
on a machine this was never authored on.

Contract: SessionStart hooks MUST exit 0 unconditionally (harness contract,
same as project-orientation.py). A missing manifest entry degrades to a
loud, visible per-entry error banner emitted on the same stdout channel (so
the gap is diagnosable in-session) rather than a silent empty emission or a
non-zero exit that could wedge session boot -- the OTHER manifest entries
still deliver; one missing snippet must not silently swallow the rest.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths: this file is at <plugin_root>/hooks/scripts/assert-em-role.py
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parent
_HOOKS_DIR = _SCRIPTS_DIR.parent
_PLUGIN_ROOT = _HOOKS_DIR.parent  # <plugin_root>/coordinator
_SNIPPETS_DIR = _PLUGIN_ROOT / "snippets"

# Ordered manifest of EM-only snippets delivered into the main session's
# SessionStart additionalContext, concatenated in this order. Each entry is
# (root, relative_path) where root is _ROOT_PLUGIN (resolved under
# _SNIPPETS_DIR) or _ROOT_REPO (resolved under the consumer repo root). See
# module docstring for why this is a manifest rather than a single hardcoded
# path, why agent-role-em.md is not grown to carry the second entry's
# content, and why the two roots degrade differently on a missing file.
_ROOT_PLUGIN = "PLUGIN"
_ROOT_REPO = "REPO"

_EM_SNIPPET_MANIFEST = [
    (_ROOT_PLUGIN, "agent-role-em.md"),
    (_ROOT_REPO, ".claude/em-context.md"),
]

# A consumer-repo EM-context file this large is a signal the repo is using
# the channel as a dumping ground rather than as the narrow EM-only surface
# it is for. Oversize content is still delivered in full -- silently
# truncating a repo's doctrine would be worse than the bloat -- but it
# banners so the growth is visible to the session it is costing. 815 B is
# this leg's budgeted share of the whole-payload delivered-bytes ceiling
# (coordinator/tests/baselines/em-payload-budget.json, legs.em_context),
# not an arbitrary round number -- see the oversize banner below for the
# ceiling this guards. It covers the RENDERED file: the largest posture
# anchor plus the 66 B coordinator:posture managed-anchor wrapper that
# render-posture-overlay adds. The earlier 200 B share assumed this slot
# stayed near-empty, which was true only in the plugin's own checkout --
# every real install rendered a full posture template here. The gate that
# holds it now is coordinator/tests/test_em_payload_install_ceiling.py,
# which measures the template on disk rather than this tree's instance.
# 815 B, not 850 -- re-derived after the default anchor was cut to an
# override-slot pointer (it no longer re-states the coordinator:posture
# managed block the operator already gets from installed CLAUDE.md), which
# leaves substrate-free.md (749 B) the largest anchor: 749 + 66 = 815.
_REPO_SNIPPET_SOFT_CAP_BYTES = 815


def _consumer_repo_root(payload: dict) -> Path | None:
    """Resolve the CONSUMER repo's root -- the anchor for _ROOT_REPO entries.

    Deliberately NOT Path(__file__)-based: that resolves the plugin tree,
    which for an installed plugin is a different repo entirely (and for the
    plugin's own dev checkout is only coincidentally the same one). The
    consumer root is whatever repo this main session actually opened in.

    Order: the harness's own project-dir env var, then the session payload's
    cwd, then the process cwd; from that starting point, walk up to the
    nearest ancestor containing .git so a session opened in a subdirectory
    still resolves the repo root. Returns None if nothing resolves -- an
    unresolvable root is treated as "no repo entry", never as an error.
    """
    candidates = [
        os.environ.get("CLAUDE_PROJECT_DIR"),
        payload.get("cwd"),
    ]
    start = None
    for candidate in candidates:
        if candidate:
            try:
                start = Path(candidate).resolve()
            except OSError:
                continue
            break
    if start is None:
        try:
            start = Path.cwd().resolve()
        except OSError:
            return None

    for directory in (start, *start.parents):
        if (directory / ".git").exists():
            return directory
    return start


def _read_stdin(timeout: float = 2.0) -> str:
    """Bounded stdin read -- mirrors project-orientation.py::_read_stdin()
    (a bare sys.stdin.read() has no timeout and can hang this SessionStart
    hook indefinitely on Windows)."""
    box = {"data": ""}

    def _read() -> None:
        try:
            box["data"] = sys.stdin.read()
        except Exception:
            box["data"] = ""

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout)
    return box["data"]


def _resolve_claude_config_dir() -> Path | None:
    """Resolve `<claude-config>` -- the harness's own session-registry root.

    Deliberately NOT an import of the fleet's control-plane engine module
    (this hook must degrade cleanly even when that engine is entirely
    absent from the machine): a minimal, self-contained mirror of that
    engine's own `claude_config_dir()` precedence (`CLAUDE_CONFIG_DIR` env
    override, else `CLAUDE_HOME`-or-home / ".claude"). Returns None on any
    resolution failure -- caller degrades to omitting the contention line,
    never to an error.
    """
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    if override:
        try:
            return Path(override).resolve()
        except OSError:
            return None
    home_override = os.environ.get("CLAUDE_HOME")
    try:
        home = Path(home_override).resolve() if home_override else Path.home()
    except OSError:
        return None
    return home / ".claude"


def _compute_contention(repo_root: Path | None, session_id: str | None, timeout: float = 0.3):
    """Best-effort, bounded (repo_count, box_count) of *registered sessions*
    -- never a claim about what they are doing (brief: tasks/2026-08-13-
    addressability-retraction/briefs/C4.md "no claim about peer internal
    state" -- the harness registry's own `status` field is never read here).

    Source: the harness's own session registry,
    `<claude-config>/sessions/*.json` -- one file per registered session
    process, box-wide, written by the harness itself (not by coordinator).
    Reading it directly as plain JSON keeps this hook independent of any
    other engine module being installed at all. `repo_root` (already
    resolved by `_consumer_repo_root`) is matched against each record's
    `cwd` field walked up to its nearest `.git` ancestor, so a peer opened
    in a subdirectory still counts. The current session (by `sessionId`) is
    excluded from both counts via `exclude_session_id`.

    NEVER PERSISTED: computed fresh, nothing written to disk. Runs inside a
    daemon thread with a hard `join` timeout -- mirrors `_read_stdin`'s
    bounded-read shape above -- so a slow or huge registry directory cannot
    hang this SessionStart hook. Returns None on ANY failure or timeout;
    caller MUST degrade to omitting the contention line entirely, never to
    a boot error, hang, or partial payload.

    `timeout` default is deliberately 0.3s, not the ~2ms typical-case cost
    measured in normal operation: this timeout STACKS on top of `main()`'s
    pre-existing `_read_stdin(2.0)` bound in the same synchronous call
    path, so the combined worst-case hook latency is `_read_stdin`'s bound
    plus this one -- a future edit raising this default quietly doubles
    (or worse) that combined bound. This is best-effort, existence-only
    peer data that degrades to omitting a line on timeout; it has no claim
    on the boot path's latency budget, so keep this value small. Do not
    raise it without re-deriving the combined worst-case bound.

    Nested-`.git` note: a peer whose `cwd` resolves to a subdirectory of a
    NESTED git repo (e.g. a submodule) under `repo_root` is deliberately
    NOT counted into `repo_count` -- the ancestor walk below breaks at the
    first `.git`-bearing directory it meets, before ever reaching
    `repo_root`, so a submodule-nested peer reads as "a different repo"
    rather than as part of this one. This is intentional, not an
    accidental side effect of loop order: a nested repo genuinely is a
    distinct repo for this count's purposes.
    """
    if repo_root is None:
        return None

    box = {"result": None}

    def _work(exclude_session_id: str | None) -> None:
        try:
            config_dir = _resolve_claude_config_dir()
            if config_dir is None:
                return
            sessions_dir = config_dir / "sessions"
            if not sessions_dir.is_dir():
                return
            repo_count = 0
            box_count = 0
            for entry in sessions_dir.glob("*.json"):
                try:
                    record = json.loads(entry.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if not isinstance(record, dict):
                    continue
                if exclude_session_id and record.get("sessionId") == exclude_session_id:
                    continue
                box_count += 1
                raw_cwd = record.get("cwd")
                if not isinstance(raw_cwd, str) or not raw_cwd:
                    continue
                try:
                    cwd_path = Path(raw_cwd).resolve()
                except OSError:
                    continue
                for directory in (cwd_path, *cwd_path.parents):
                    if directory == repo_root:
                        repo_count += 1
                        break
                    if (directory / ".git").exists():
                        break
            box["result"] = (repo_count, box_count)
        except Exception:
            box["result"] = None

    t = threading.Thread(target=_work, args=(session_id,), daemon=True)
    t.start()
    t.join(timeout)
    return box["result"]


_PEER_READ_POINTER = (
    "assert-em-role: {repo_count} peer session(s) in this repo, {box_count} "
    "on this machine -- existence only. A count is not a stand-down signal "
    "and not permission to send.\n"
)

# Bounds that make the Group EM clause's worst case a FIXED, measurable
# number rather than a function of whatever a peer happened to name itself.
# Without them the leg's budget entry could not be derived at all: peer
# names are free-form, and a long one would silently push the whole boot
# payload past the 2,048 B preview window it must fit inside WHOLE
# (coordinator/tests/test_em_payload_budget.py, PEEK leg).
_GEM_NAME_MAX_CHARS = 32
_GEM_SESSION_PREFIX_CHARS = 8

# Identity and a pointer, nothing else. What the role IS, and the standing
# it does and does not carry over a peer, lives in the wiki page named here
# -- restating any of it on the boot path would spend the payload's whole
# remaining headroom on prose every session, to say what one lookup says
# once. The page is cited by bare filename because that is the greppable
# form; it resolves under coordinator/docs/wiki/ in the source repo only.
_GEM_CLAUSE = "G-EM active: {name} ({session}) -- see wiki group-em-standing.md\n\n"


def _group_em_nomination_module():
    """Load group-em-nomination.py by path -- hyphens make its filename
    unimportable. Same loader as coordinator/bin/statusline.py::
    _group_em_nomination_module. Best-effort by contract: ANY failure
    returns None and the caller omits the clause; a broken nomination
    module must never cost this hook its one job.
    """
    try:
        import importlib.util

        path = _PLUGIN_ROOT / "bin" / "group-em-nomination.py"
        spec = importlib.util.spec_from_file_location("_assert_em_gem_nomination", path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


def _group_em_clause(repo_root, timeout: float = 0.3) -> str:
    """One terse line naming the session that currently holds this repo's Group
    EM nomination, or "" -- WHICH IS THE COMMON CASE AND NOT A FAILURE.

    Emitted iff a nomination record exists AND its holder is live. No line is
    emitted for the no-nomination case, and none for a lapsed one: most repos
    never nominate, and a standing "no Group EM here" line would spend the boot
    payload's scarcest resource, fleet-wide and every session, to say nothing
    happened.

    NEVER CACHED, AT ANY LAYER -- resolved fresh every boot, nothing written to
    disk. ``group-em-nomination.py``'s module docstring sets the rule this
    obeys: a cached "who is the Group EM" answer that survives a stand-down is
    a wrong address that looks authoritative, strictly worse than no answer.

    Liveness is the registry join, never the record alone. A nomination whose
    session is gone renders as no line, because a lapsed holder and no holder
    authorize precisely the same thing.

    THIS REPO ONLY, AND NEVER A SCAN. ``read_record(repo_root)`` resolves one
    deterministic path from the repo root and rejects a record whose own
    `repo_root` disagrees, so a Group EM sitting in some OTHER repo on this
    machine cannot surface here. If a future pass wants the fleet view, it
    belongs behind a verb the operator invokes, never here.

    `peer_name` is an advisory snapshot a rename voids; the session prefix is
    what joins. Both bounded -- see the constants above.

    Bounded like ``_compute_contention`` and for its reason: ``is_live`` scans
    the harness session registry, and that cost STACKS on that function's own
    bound plus ``_read_stdin``'s inside one synchronous boot path. Returns ""
    on any failure or timeout -- the caller degrades to omitting the line,
    never to a boot error or a partial payload.
    """
    if repo_root is None:
        return ""

    box = {"result": ""}

    def _work() -> None:
        try:
            gem = _group_em_nomination_module()
            if gem is None:
                return
            record = gem.read_record(str(repo_root))
            if not isinstance(record, dict):
                return
            live, _row = gem.is_live(record)
            if not live:
                return
            holder = str(record.get("session_id") or "")
            name = str(record.get("peer_name") or "").strip() or "unnamed"
            box["result"] = _GEM_CLAUSE.format(
                name=name[:_GEM_NAME_MAX_CHARS],
                session=holder[:_GEM_SESSION_PREFIX_CHARS] or "unknown",
            )
        except Exception:
            box["result"] = ""

    t = threading.Thread(target=_work, daemon=True)
    t.start()
    t.join(timeout)
    return box["result"]


def _w(text: str) -> None:
    """Write raw UTF-8 bytes to stdout -- NOT print()/sys.stdout.write().

    Windows text-mode stdout translates LF to CRLF; mirrors
    project-orientation.py::_w()'s byte-parity convention.
    """
    sys.stdout.buffer.write(text.encode("utf-8"))


def _exc_reason(exc: Exception) -> str:
    """The WHY of an OSError without the WHERE.

    `del snippet_path` in the composer below drops the absolute path from that
    banner deliberately -- and `str(OSError)` puts it straight back, because
    `OSError.__str__` appends the filename it failed on. A session in a third
    repo then reads a DoE-claude snippets path out of a plugin it never
    invoked: the exact leak class this surface exists to close, arriving
    through an exception rather than an f-string.

    `strerror` alone ("No such file or directory") is the part an operator can
    act on, and `rel_path` is already in the message saying which entry. Falls
    back to the exception TYPE NAME rather than `str(exc)`, so a non-OSError
    cannot reintroduce a path through this path either.
    """
    strerror = getattr(exc, "strerror", None)
    if strerror:
        return str(strerror)
    return type(exc).__name__



def _compose_missing_snippet_banner(rel_path: str, snippet_path: Path, exc: Exception, root: str) -> str:
    """One of the two manifest-entry error banners (module docstring's
    "loud, visible per-entry error banner"): the snippet file is absent or
    unreadable. `root` is `_ROOT_PLUGIN`/`_ROOT_REPO` and selects which of
    the two closing sentences applies -- extracted as a pure, separately-
    named function (not inline in `main()`) so a measurement harness can
    call it directly without going through `main()`'s stdin/exit-code
    plumbing; see docs/plans/2026-08-02-guard-message-character-cap.md,
    chunk C1's "Measurement mechanism" section."""
    del snippet_path  # already implied by rel_path; not repeated in the tightened prose
    reason = _exc_reason(exc)
    if root == _ROOT_PLUGIN:
        return (
            f"assert-em-role: {rel_path} MISSING ({reason}) -- EM role not "
            f"fully asserted; restore coordinator/snippets/{rel_path}.\n\n"
        )
    return (
        f"assert-em-role: {rel_path} unreadable ({reason}) -- its content was "
        f"not delivered this session.\n\n"
    )


def _compose_oversize_repo_banner(rel_path: str, byte_len: int) -> str:
    """The third manifest-entry error banner: a REPO-slot snippet that
    exceeds `_REPO_SNIPPET_SOFT_CAP_BYTES`. Delivered in full regardless
    (module docstring: "silently truncating a repo's doctrine would be
    worse than the bloat"); this banner only makes the growth visible.
    Extracted as a pure function for the same reason as
    `_compose_missing_snippet_banner` above."""
    return (
        f"assert-em-role: {rel_path} is {byte_len}B, over its "
        f"{_REPO_SNIPPET_SOFT_CAP_BYTES}B share of the 1,700B ceiling "
        f"(2KB-First Rule, doctrine-channel-purposes.md:175). Delivered "
        f"anyway -- consider a wiki.\n\n"
    )


def main(argv: list) -> int:
    del argv  # no flags -- this hook takes no arguments

    payload = {}
    try:
        raw = _read_stdin(2.0)
        if raw:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                payload = parsed
    except Exception:
        pass  # a malformed payload only costs the REPO slot, never the PLUGIN ones

    repo_root = _consumer_repo_root(payload)

    _w("\n")
    for root, rel_path in _EM_SNIPPET_MANIFEST:
        if root == _ROOT_PLUGIN:
            snippet_path = _SNIPPETS_DIR / rel_path
        else:
            if repo_root is None:
                continue  # unresolvable consumer root == no repo entry, silently
            snippet_path = repo_root / rel_path
            # Absence is the common case for the repo slot and must stay
            # silent; only an existing-but-unreadable file is a defect.
            if not snippet_path.exists():
                continue

        try:
            snippet_text = snippet_path.read_text(encoding="utf-8")
        except OSError as exc:
            _w(_compose_missing_snippet_banner(rel_path, snippet_path, exc, root))
            continue  # one missing manifest entry must not swallow the rest

        if root == _ROOT_REPO and len(snippet_text.encode("utf-8")) > _REPO_SNIPPET_SOFT_CAP_BYTES:
            _w(_compose_oversize_repo_banner(rel_path, len(snippet_text.encode("utf-8"))))

        _w(snippet_text)
        _w("\n")

    session_id = payload.get("session_id") if isinstance(payload.get("session_id"), str) else None
    contention = _compute_contention(repo_root, session_id)
    if contention is not None and any(contention):
        repo_count, box_count = contention
        try:
            _w(_PEER_READ_POINTER.format(repo_count=repo_count, box_count=box_count))
        except Exception:
            pass  # degrade-and-continue -- a future stray brace in the
            # literal prose must not abort the whole hook
        # Gated on the SAME contention check: with no peers there is no rando
        # to inoculate against, and a quiet single-session machine stays
        # byte-identical to a build without this clause.
        try:
            gem_clause = _group_em_clause(repo_root)
            if gem_clause:
                _w(gem_clause)
        except Exception:
            pass  # same degrade-and-continue contract as the pointer above

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
