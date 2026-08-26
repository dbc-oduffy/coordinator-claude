"""
coordinator-prepare-commit-msg — append Session-Id and Deliverable-Id trailers
to every commit made inside an active coordinator session.

Native-Python port (DR-059 de-bash, Windows-first) of the retired bash hook.

Git hook signature (prepare-commit-msg):
  argv[1]  COMMIT_MSG_FILE path (required)
  argv[2]  commit source (optional: message, template, merge, squash, commit)
  argv[3]  SHA1          (optional: present only for --amend / squash)

Behaviour:
  1. Resolve the git dir once (``git rev-parse --git-dir``, ONE subprocess —
     needed for locating ``session-shape.json``) and the current session-id
     via the three-tier env ladder (KS-6, 2026-08-07 — widened to match
     ``coordinator_core.session.core.SESSION_ENV_PRECEDENCE``, the canonical
     reference; this hook cannot cheaply import ``coordinator_core`` on its
     hot commit-hook path, so this ladder is a hand-mirrored copy of that
     module's — a change to one must be mirrored in the other):
       (1) $COORDINATOR_SESSION_ID                              (explicit test override)
       (2) $CLAUDE_SESSION_ID                                   (legacy var)
       (3) $CLAUDE_CODE_SESSION_ID                               (platform-injected)
     A former tier-4 ``<git-dir>/coordinator-sessions/.current-session-id`` sentinel
     fallback (liveness-gated as of 2026-08-07) was REMOVED entirely on
     2026-08-07 (KS-1) — unsound by construction under this fleet's
     concurrency (documented last-writer-wins,
     ``coordinator_core/bash_guards/guard_inprocess_search.py`` ~L84) and its
     writer (``session-init.py``) was deleted 2026-07-15. See
     ``_resolve_session_id``'s own docstring for the full rationale.
  2. Empty session-id → exit 0 silently (non-coordinator commit; unaffected).
  3. Fail-safe UUID validation — a resolved session-id that is not UUID-shaped
     (e.g. a poisoned sentinel or a stray profiling-run env override) → exit 0,
     Session-Id trailer OMITTED (and, since deliverable-id resolution is keyed
     off the same session-id, Deliverable-Id is skipped too). A missing
     trailer is coverage-neutral; a wrong one mis-attributes session scope.
     Validated once at the resolved value, so it covers all three ladder
     tiers uniformly.
  3a. Deliverable-Id tier 0 (artifact-first, 2026-08-04): before any
     session-keyed tier below, derive this commit's own staged pathspec
     (``git diff --cached --name-only``, ONE subprocess, only spawned when a
     Deliverable-Id trailer is actually missing) and check whether any
     staged artifact carries its own ``deliverable_id`` frontmatter — see
     ``_resolve_deliverable_id_from_paths`` below for the multi-baton-session
     defect this closes (2026-08-04 cross-repo memo, example-market-data-repo-em
     -> claude-klabauter-em, defect 2) and why it wins over every tier below.
     Fails SOFT on the hot path: staged-set derivation errors (not a repo,
     git unavailable, timeout, empty stage) and a multi-artifact commit
     whose artifacts name different deliverables both degrade to "tier 0 has
     nothing to say", silently, rather than blocking or erroring the commit.
     DR-328 retired ``DivergentDeliverableIdError`` as a commit gate — two
     deliverables in one commit is ordinary, not ambiguous — so the second
     case is an omit here and in the engine twin alike, with no stderr note
     in either. Gated (2026-08-07, DR-207)
     on ``coordinator_core.claim_state.resolve_claim_state``: a staged
     artifact claimed by a DIFFERENT live session is excluded from tier 0's
     consideration (falls through to the session-keyed tiers below) rather
     than stamping the peer's deliverable onto this commit — see
     ``_resolve_deliverable_id_from_paths``'s own docstring for the
     memo-write-through defect this closes. This mirrors
     ``coordinator_core.git.commit_trailers.compute_missing_trailer_args``'s
     own tier 0 for a caller (``git commit-tree`` et al.) that hooks never
     fire for; post-DR-328 that sibling omits on divergence exactly as this
     copy does, and neither raises. This hook could not have kept a raising
     posture in any case: a failed hook still lets the underlying ``git
     commit`` land with a wrong/no trailer rather than blocking, and
     blocking would be strictly worse than that.
  4. Deliverable-Id (session-keyed fallback, reached only when tier 0 above
     yields nothing): read
     ``<git-dir>/coordinator-sessions/<sid>/session-shape.json``
     (ONE file read, no additional subprocess) and extract
     ``pickup.deliverable_id`` — the deliverable-spine id of the handoff this
     session claimed via ``/pickup`` (coordinator_core.ops.session.record_pickup).
     Mirrors the Session-Id discipline exactly, more strongly: a missing file,
     unreadable file, corrupt JSON, absent ``pickup`` key, or absent/blank
     ``deliverable_id`` all OMIT the trailer — never stamp a guessed or
     placeholder value. No env-var bypass, no config flag, no fallback that
     invents an id.
  4a. Cross-repo fallback (2026-07-27): ``session-shape.json`` is written into
     the git-dir of whichever repo was ``cwd`` when ``/pickup`` ran — almost
     always DoE-claude, since EM sessions operate from there (DoE-claude
     ``CLAUDE.md`` § "Who you are when working in DoE-claude"). A commit
     landed DIRECTLY into claude-klabauter under the standing cross-repo
     write grant (DoE-claude ``CLAUDE.md`` § "Cross-repo write discipline")
     runs this SAME hook script but with ``git_dir`` pointed at claude-klabauter's own
     ``.git``, which never receives that write — so step 4's lookup always
     misses for a cross-repo commit, not merely on rare occasion. When step 4
     resolves nothing, re-resolve against DoE-claude's own git-dir, located
     via the identical ``.doe-root`` pointer convention already used above
     (step "SCRIPT" fallback) to locate this very script — no new resolution
     mechanism introduced, no subprocess spawn (two plain file reads at
     most). Same omit-rather-than-guess contract: no match there either →
     Deliverable-Id stays omitted.
     Spec: cross-repo dispatch 2026-07-27 (`Deliverable-Id trailer never
     lands on cross-repo claude-klabauter commits` investigation).
  3b. Scope-match tier + ambiguity gate (C4, importing C2's landed seam,
     2026-08-10): between tier 0 (artifact-first) and step 4
     (session-shape.json pickup) below, resolve this session's held plan
     claims (``coordinator_core.session.claimed_plan.list_held_plan_claims``,
     C1a's ``[(plan_path, claimed_at), ...]`` shape) and try
     ``coordinator_core.git.commit_trailers.resolve_deliverable_id_from_scope_match``
     — a code-only commit whose staged pathspec is strictly covered by
     exactly ONE claimed plan's ``scope:`` frontmatter resolves to that
     plan's ``deliverable_id``. Both this tier AND the ambiguity gate
     (``session_holds_multiple_plan_claims`` — a session holding 2+ plan
     claims with neither tier 0 nor this scope-match tier disambiguating
     OMITS rather than guesses, since every tier below is session-keyed and
     cannot tell which held claim a given commit is actually for) are IMPORTED, not
     re-mirrored, from ``coordinator_core.git.commit_trailers`` — C2's
     REQUIRED INTERFACE, its sole two new exports. Verified live at C4 time:
     importing them triggers ZERO ``coordinator_core.ops`` module imports
     (op registration is lazy, unconditionally, so the eager ~161-module
     sweep never fires), so this import is as cheap on the hot commit-hook
     path as the pre-existing claimed-plan import in step 4b below. Lazily
     imported the same way, via ``_ensure_claude_klabauter_on_syspath()`` /
     ``cc_invoke.require_colocated_engine_on_path`` (self-location-first,
     wrapping ``resolve_colocated_claude_klabauter_root``).
     Mirrored-pair maintenance note (module docstring, above): this tier is
     the ONE exception to "hand-mirrored, changed in both by hand" — C2's
     scope-match tier and ambiguity predicate are IMPORTED here verbatim, so
     a change to either lives in exactly one place
     (``coordinator_core/git/commit_trailers.py``) and this hook picks it up
     automatically; do not hand-roll a second implementation of either.
  4b. Claimed-plan fallback (2026-08-01): steps 4/4a both key off
     ``pickup.deliverable_id``, populated ONLY by ``record_pickup`` on a
     ``/pickup`` of a HANDOFF. A session that claims a PLAN directly and
     executes it — no handoff ever authored — never writes that key, so
     every chunk commit that session makes misses both tiers above. When
     they both miss, resolve the session's claimed plan (the SAME
     ``resolve_claimed_plan_path()`` helper ``coordinator_core`` uses —
     lazily imported here, off this hook's hot path, only once 4/4a have
     already missed) and read ``deliverable_id`` straight out of that
     plan's own frontmatter. Same omit-rather-than-guess contract
     throughout.
     ``archive/specs/2026-08/2026-08-01-deliverable-id-carry-onto-executing-
     handoff.md``'s execution note names this residual explicitly and
     records its own Anti-scope ("do NOT change the commit-trailer
     resolvers") as reasoning that assumed every execution is
     handoff-mediated — an assumption that note itself calls incomplete.
     This step is the deliberate, documented reversal of that anti-scope
     for the same-session case. Spec backlink: DR-207 DD#1.
  5. Session-Id and Deliverable-Id have INDEPENDENT idempotency checks — a
     message may legitimately carry one trailer without the other (e.g. an
     amended commit, or session-shape written after an earlier commit in the
     same session). Each trailer is added iff its own line is not already
     present in the message; both may be added in the SAME
     ``git interpret-trailers --in-place`` call (a second ``--trailer`` arg),
     never a second subprocess call.
  6. Otherwise inject via `git interpret-trailers --in-place --trailer` (one
     call, carrying whichever trailer(s) are missing).

NEVER blocks a commit — always exits 0. `git interpret-trailers` is core git ≥ 1.8.

Sole implementation (C14, 2026-08-21): the extensionless sibling in this same
directory, `coordinator-prepare-commit-msg` (no `.py` suffix), is a thin
in-process delegate onto THIS file's `main()` — it carries no independent
logic. Both names must keep resolving to the SAME behaviour by construction
now (see that file's own module docstring for the divergence defect this
replaced), not by hand-mirroring two copies in sync.

Also emits ONE write-time advisory, unrelated to trailers and equally
non-blocking: a subject shaped as a chunk-id RANGE (`C1-C5: ...`) is named on
stderr with its enumerated form (`C1,C2,C3,C4,C5: ...`) attached — see
`_warn_hyphen_range_subject`. Fires ahead of the session-id gate, adds no
subprocess, and never rewrites the message.

Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md § git-hook-installers-port
Prior spec: docs/plans/2026-06-15-brightline-session-scope-fix.md § C1
Spec: cross-repo/inbox/2026-07-21-claude-klabauter-em-claude-klabauter-session-id-leak-fix-reply.md (residual B(i))
Deliverable-Id spec: DoE-claude coordinator/schemas/handoff.schema.json (deliverable_id field);
    coordinator_core/ops/session/record_pickup.py (write side).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

#: Range-shaped chunk-id prefix on a commit subject — `C1-C5: <prose>`,
#: `C1 - 5: <prose>`, `1-4: <prose>`. Deliberately requires DIGITS on BOTH
#: sides of the hyphen, which is what keeps every real compound dash-tag in
#: the corpus (`DOCTRINE-C7a:`, `RESIDUE-C9:`, `RESIDUE-C1..C7:`) out of it:
#: their left component is prose, so the alternation never starts. The
#: optional right-hand alpha prefix is captured so it can be checked equal to
#: the left one (or absent) before firing — `C1-D4:` is two different spine
#: families, not a range, and must not be reported as one.
_HYPHEN_RANGE_SUBJECT_RE = re.compile(
    r"^\s*(?P<lp>[A-Za-z]{0,10}?)(?P<ln>\d+)\s*-\s*(?P<rp>[A-Za-z]{0,10}?)(?P<rn>\d+)\s*:"
)


def _no_console_creationflags() -> dict:
    """Console-suppression kwargs for every spawn in this hook.

    Deliberately does NOT import
    ``coordinator_core.win_portability.no_console_creationflags``, which is the
    engine primitive the rest of the fleet splats. This file is a
    ``prepare-commit-msg`` hook: it runs on EVERY commit, on the interactive hot
    path the brightline polices, and it currently imports no engine module at
    all. Pulling ``coordinator_core`` in to fetch a two-line mapping would put
    an engine import on the commit path to buy nothing the stdlib does not
    already give, and would add an ImportError failure mode to a hook whose one
    hard rule is never to block a commit. The returned mapping is byte-identical
    to the primitive's, and is the same fallback shape
    ``coordinator/bin/append-plan-session.py`` already ships for the
    engine-unresolvable case.

    THE CATCH this file already satisfies, carried so a new call site does not
    lose it: a spawn passing these flags and NO ``stdin=``/``stdout=``/
    ``stderr=``/``capture_output=`` silently loses the child's output on
    Windows -- CPython sets ``STARTF_USESTDHANDLES`` only when at least one is
    given, so without it the child binds its handles to the fresh window-less
    console instead of the parent's. Every spawn in this file wires
    ``capture_output=True``. A new one must too, or use passthrough kwargs.
    """
    if os.name != "nt":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def _resolve_git_dir() -> str:
    """Resolve the current repo's git-dir with ZERO subprocess spawns —
    replaces the former ``git rev-parse --git-dir`` call on this hot path
    (§ C1(b)). Returns ``""`` on any failure (not a repo, unreadable
    ``.git``, permission error) — callers treat that as "no git-dir
    available" and degrade gracefully, exactly as the spawn-based version
    did.

    DELIBERATE TWIN OF ``coordinator_core.git.git_dir.resolve_git_dir``, kept
    rather than collapsed (2026-08-21, EM, on the peer reuse finding relayed
    by claude-klabauter-3a). That function resolves the same per-worktree
    git-dir in-process and handles the same ``.git``-is-a-FILE case, and
    "default to reusing" would ordinarily settle it. It does not here, for a
    structural reason, not a stylistic one: **this call is the FIRST thing
    ``main()`` does, and on a non-coordinator commit the hook returns 0 two
    lines later having imported no engine at all.** ``_ensure_claude_klabauter_on_
    syspath`` (and with it any ``coordinator_core`` import) is reached only
    on the deliverable-id path, far below. Importing the engine here to save
    ~40 lines would put an engine import on EVERY commit in EVERY repo
    carrying this hook -- the exact cost
    ``docs/plans/2026-08-21-a-commit-stops-paying-for-thirty-processes.md``
    exists to cut, on a path already measured over budget (that plan's
    § Corrections 8).

    The two also differ where it matters, so a mechanical collapse would be
    a behaviour change: this one honours ``$GIT_DIR`` (rung 1 below) and
    returns ``""`` on failure, where the engine twin has no ``$GIT_DIR``
    rung and fails open to a ``<repo_root>/.git`` join. Whoever revisits
    this must keep both contracts, not just the parse.

    NOT via ``GIT_INDEX_FILE``: it names ``$GIT_DIR/index`` only by
    default, is relocated by ordinary git operations (and by porcelain
    staging through a temporary index) with no signal that it moved, and a
    build on it fails silently with a plausible-looking wrong path — do not
    resurrect that shortcut here.

    Derivation, cheapest-safe-check first:
      1. ``$GIT_DIR``, if the environment sets it — ``git --git-dir=...
         commit`` exports it into the hook environment even though a plain
         ``git commit`` does not, so honouring it is free correctness, not
         dead code.
      2. Otherwise resolve ``.git`` relative to cwd — git invokes
         ``prepare-commit-msg`` with cwd already AT the worktree root
         (this file's module docstring and ``_resolve_staged_paths``'s own
         docstring both already rely on that same invariant for their own
         relative-path git calls), so no upward directory walk is needed
         or attempted.
         - a DIRECTORY there is an ordinary repo's git-dir: return ``".git"``.
         - a FILE there is a linked worktree or submodule gitlink: parse its
           ``gitdir: <path>`` first line and resolve that path relative to
           the FILE's own directory (not cwd) if it is not already
           absolute — the same trap commit ``87b2f3f43`` already paid for
           once in this codebase.

    This reproduces ``git rev-parse --git-dir``'s PER-WORKTREE answer
    (``.git/worktrees/<name>``), never the common dir —
    ``_resolve_deliverable_id_at``'s ``<git-dir>/coordinator-sessions/<id>/
    session-shape.json`` lookup and the ``common_dir=`` argument threaded
    into ``resolve_claim_state`` both depend on which one this returns; a
    "helpfully" common-dir-returning derivation would change behaviour
    silently.
    """
    try:
        env_git_dir = os.environ.get("GIT_DIR", "").strip()
        if env_git_dir:
            return env_git_dir

        cwd = os.getcwd()
        dotgit = os.path.join(cwd, ".git")
        if os.path.isdir(dotgit):
            return ".git"
        if os.path.isfile(dotgit):
            with open(dotgit, encoding="utf-8") as fh:
                first_line = fh.readline().strip()
            if first_line.startswith("gitdir:"):
                target = first_line[len("gitdir:"):].strip()
                if target and not os.path.isabs(target):
                    target = os.path.normpath(os.path.join(cwd, target))
                if target:
                    return target
        return ""
    except Exception:
        return ""


def _resolve_session_id(git_dir: str) -> str:
    """Hand-mirrored copy of ``coordinator_core.session.core
    .resolve_session_id`` / ``SESSION_ENV_PRECEDENCE`` (KS-6, 2026-08-07) —
    THAT function is the source of truth for this ladder; this copy exists
    only because this hook runs on the hot commit-hook path and cannot
    cheaply import ``coordinator_core`` there. A change to the precedence
    order or tier set in ``core.py`` MUST be mirrored here by hand.

    Full 3-tier ladder: ``COORDINATOR_SESSION_ID`` -> ``CLAUDE_SESSION_ID``
    -> ``CLAUDE_CODE_SESSION_ID`` — widened from the prior 2-tier (legacy
    env -> platform env) chain this function used to implement, to match
    the canonical reference (see ``SESSION_ENV_PRECEDENCE``'s own docstring
    for the prior break-class defect two disagreeing copies of this ladder
    caused).

    A former tier (the ``<git_dir>/coordinator-sessions/.current-session-id``
    sentinel file, plus its liveness gate ``_sentinel_session_live``) was
    REMOVED here, not merely gated — KS-1, mirrored from
    ``coordinator_core.git.commit_trailers._resolve_session_id`` (see that
    module's own docstring for the full rationale). Two independent
    reasons: (1) unsound by construction under this fleet's concurrency,
    documented as last-writer-wins in
    ``coordinator_core/bash_guards/guard_inprocess_search.py`` ~L84 — ~18
    concurrent sessions on one shared worktree means even a freshly-written
    sentinel hands session A the id of whichever session wrote last, so a
    liveness gate only made it confidently wrong rather than obviously
    wrong; (2) its writer, ``session-init.py`` (DoE-claude SessionStart
    hook), was deleted by PM directive 2026-07-15
    ("full-kill-keep-fast-orientation") — no production writer survives
    anywhere. ``git_dir`` is accepted (and resolved by the caller) purely
    for the Deliverable-Id lookups below, which still need it. Do not
    restore this tier without a new writer for the sentinel file."""
    sid = os.environ.get("COORDINATOR_SESSION_ID", "").strip()
    if sid:
        return sid
    sid = os.environ.get("CLAUDE_SESSION_ID", "").strip()
    if sid:
        return sid
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "").strip()
    if sid:
        return sid
    return ""


def _resolve_doe_root() -> str:
    """Locate DoE-claude's repo root via the SAME ``.doe-root`` pointer
    convention this hook already uses (see the SCRIPT-location fallback at
    the top of this file) — settings-home machine-local pointer first, then
    the legacy ``~/.claude`` location. Returns ``""`` if neither resolves.
    No subprocess spawn; at most two plain file reads."""
    home = (
        os.environ.get("CLAUDE_HOME")
        or os.environ.get("HOME")
        or os.environ.get("USERPROFILE")
        or str(Path.home())
    )
    settings_home = os.environ.get("COORDINATOR_SETTINGS_HOME", "").strip() or os.path.join(
        home, ".coordinator-claude-settings"
    )
    for candidate in (
        os.path.join(settings_home, "machine-local", ".doe-root"),
        os.path.join(home, ".claude", ".doe-root"),
    ):
        try:
            with open(candidate, encoding="utf-8") as fh:
                root = fh.read().strip()
        except Exception:
            continue
        if root:
            return root
    return ""


def _resolve_deliverable_id_at(git_dir: str, session_id: str) -> str:
    """Read ``<git_dir>/coordinator-sessions/<session_id>/session-shape.json``
    (ONE file read, no subprocess) and return ``pickup.deliverable_id`` if
    present and non-blank, else ``""``.

    Omit-rather-than-guess, mirroring the Session-Id discipline: a missing
    git_dir, missing/unreadable shape file, corrupt JSON, non-dict shape,
    non-dict ``pickup``, or absent/blank ``deliverable_id`` all return ``""``
    — never raises, never fabricates a value.
    """
    if not git_dir or not session_id:
        return ""
    shape_path = os.path.join(
        git_dir, "coordinator-sessions", session_id, "session-shape.json"
    )
    try:
        with open(shape_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    pickup = data.get("pickup")
    if not isinstance(pickup, dict):
        return ""
    deliverable_id = pickup.get("deliverable_id")
    if isinstance(deliverable_id, str) and deliverable_id.strip():
        return deliverable_id.strip()
    return ""


def _resolve_staged_paths(timeout: float = 10.0) -> list:
    """``git diff --cached --name-only``, ONE subprocess — derived here
    because this hook, unlike ``git_native.commit_scoped()``'s callers,
    receives no pathspec argument of its own (git invokes ``prepare-commit-
    msg`` with only the commit-message-file path; the staged set is never
    handed to it). Windows-safe (``creationflags``/``stdin=DEVNULL``) and
    BOUNDED (``timeout``) — this runs on the commit hot path, so a hang here
    is strictly worse than a missing trailer.

    Fail-soft, unconditionally: not a repo, git unavailable, a spawn error,
    a timeout, a non-zero exit, or a genuinely empty stage all return ``[]``
    — never raises. An empty result reads identically to "tier 0 has
    nothing to say" at the call site, which is exactly the fallback-to-
    session-tiers behaviour this hook must degrade to.

    This function does not itself import ``coordinator_core`` — see
    ``_no_console_creationflags()``'s docstring for why the console-
    suppression path in this file stays engine-free. The bootstrap call here
    instead pre-flights ``_ensure_claude_klabauter_on_syspath()`` — the same self-
    location bootstrap every ``coordinator_core`` import in this file already
    uses — on behalf of the downstream ``_resolve_deliverable_id()`` engine
    imports the caller is about to attempt with these paths: git spawns this
    script with no ``PYTHONPATH``, so ``coordinator_core`` is not importable
    off a bare ``sys.path`` in a real hook invocation, and a resolution
    failure here is reported once rather than surfacing separately at each
    downstream tier that would otherwise re-attempt the same bootstrap. A
    resolution failure still degrades to ``[]`` (never blocks the commit),
    matching the module's fail-soft contract, but is noted on stderr,
    matching the visible-not-silent convention this file already uses for
    tier-0 ambiguity (``_resolve_deliverable_id``) — a silently empty tier-0
    lookup here previously masqueraded as "nothing staged" indefinitely.
    """
    claude_klabauter_root = _ensure_claude_klabauter_on_syspath()
    if not claude_klabauter_root:
        sys.stderr.write(
            "coordinator-prepare-commit-msg: could not resolve the colocated "
            "claude-klabauter checkout for coordinator_core.win_portability; staged-path "
            "derivation (tier-0 Deliverable-Id resolution) skipped for this "
            "commit.\n"
        )
        return []
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            **_no_console_creationflags(),
        )
    except Exception as exc:
        sys.stderr.write(
            "coordinator-prepare-commit-msg: staged-path derivation failed "
            f"({exc}); tier-0 Deliverable-Id resolution skipped for this "
            "commit.\n"
        )
        return []
    if out.returncode != 0:
        return []
    return [line for line in (out.stdout or "").splitlines() if line.strip()]


def _ensure_claude_klabauter_on_syspath() -> str:
    """Bootstrap ``coordinator_core`` onto ``sys.path``, resolving the
    colocated claude-klabauter checkout via ``cc_invoke.resolve_colocated_claude_klabauter_root``
    (this script's own ``__file__`` parents) — the SAME bootstrap
    ``_resolve_deliverable_id_from_claimed_plan`` already performs inline,
    extracted so tier 0's artifact lookup can share it without duplicating
    the ``sys.path`` dance a second time. Returns the resolved claude-klabauter root,
    or ``""`` on any resolution failure — never raises.
    """
    try:
        lib_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
        if lib_dir not in sys.path:
            sys.path.insert(0, lib_dir)
        from cc_invoke import require_colocated_engine_on_path

        return require_colocated_engine_on_path(__file__)
    except Exception:
        return ""


def _resolve_deliverable_id_from_paths(
    paths: list, session_id: "str | None" = None, git_dir: "str | None" = None
) -> str:
    """Tier 0: resolve straight off the committed artifact(s), not the
    session — hand-mirrored from
    ``coordinator_core.git.commit_trailers._resolve_deliverable_id_from_paths``
    (see this file's module docstring and that module's own header note on
    why the pair is kept in sync by hand rather than one importing the
    other; that function's own docstring carries the full defect writeup
    this tier closes).

    Omit-rather-than-guess: ``paths`` empty, or none of ``paths`` resolve to
    a file carrying a ``deliverable_id``, returns ``""``. Two or more staged
    paths carrying DIFFERENT non-empty ``deliverable_id`` values ALSO return
    ``""`` (DR-328, 2026-08-19) — a divergent pathspec is the same
    "cannot resolve" case as an empty one, not a separate fail-loud posture,
    and producer-contract § 3 governs all three producers uniformly.

    This tier used to raise ``DivergentDeliverableIdError`` and depend on
    ``_resolve_deliverable_id``'s broad ``except Exception`` to swallow it.
    The observable outcome was already right, but only accidentally: the
    engine twin returned while this copy raised, so the hand-mirrored pair
    had genuinely diverged in control flow behind identical behaviour. That
    is the drift this file's module docstring warns the pair is kept in sync
    to prevent, and it is why the omit is now explicit here.

    Contention gate (2026-08-07, DR-207): a staged artifact claimed by a
    DIFFERENT live session (per
    ``coordinator_core.claim_state.resolve_claim_state``) must NOT have its
    ``deliverable_id`` stamped onto THIS commit — that enrolls the commit in
    the peer's chain DAG (see the memo-write-through defect this closes).
    Claimed-by-``session_id`` itself, or unclaimed, is not contention and is
    treated exactly as before. Each claim lookup is independently fail-soft:
    an exception, unresolvable path, or missing ledger degrades to "no claim
    information" — the SAFE direction here is to KEEP the artifact's
    ``deliverable_id`` (today's behaviour), never to suppress it. ``paths``
    carrying a claim only from a different session are dropped from
    consideration entirely, as if they had no ``deliverable_id``.
    """
    if not paths:
        return ""

    claude_klabauter_root = _ensure_claude_klabauter_on_syspath()
    if not claude_klabauter_root:
        return ""
    try:
        from coordinator_core.frontmatter.primitives import (
            read_fm_field_unquoted,
            split_frontmatter,
        )
    except Exception:
        return ""

    try:
        from coordinator_core.claim_state import resolve_claim_state
    except Exception:
        resolve_claim_state = None

    common_dir = Path(git_dir) if git_dir else None

    found = {}
    for rel_path in paths:
        try:
            with open(rel_path, encoding="utf-8") as fh:
                text = fh.read()
        except Exception:
            continue
        split = split_frontmatter(text)
        if split is None:
            continue
        deliverable_id = read_fm_field_unquoted(split.fm_text, "deliverable_id")
        if isinstance(deliverable_id, str):
            cleaned = deliverable_id.strip()
            if cleaned and cleaned.lower() not in ("none", "null", "~"):
                if resolve_claim_state is not None and session_id:
                    try:
                        claim = resolve_claim_state(
                            Path(rel_path), common_dir=common_dir
                        )
                        holder = claim.holder
                    except Exception:
                        # Fail-soft to today's behaviour: an errored claim
                        # lookup is NOT evidence of contention.
                        holder = None
                    if holder and holder != session_id:
                        continue
                found[rel_path] = cleaned

    # The value returned on the collapse-to-one path is always a RAW value
    # some staged artifact actually carries. Kept byte-identical in shape to
    # `commit_trailers._resolve_deliverable_id_from_paths`, which this
    # mirrors (review-integrator P1, coordinatorcode-reviewer-0f04f47d.md).
    distinct_values = sorted(set(found.values()))
    if not distinct_values:
        return ""
    if len(distinct_values) == 1:
        return found[min(found)]

    # Producer-contract § 3 / DR-328: omit, don't guess -- and don't raise
    # either. The engine twin returns "" here, and this copy relying on
    # `_resolve_deliverable_id`'s broad `except Exception` to convert a raise
    # into the same outcome made the two LOOK equivalent while their control
    # flow diverged; the fail-soft arm stays (it guards more than this one
    # exception) but is no longer what makes this tier correct.
    return ""


def _list_held_plan_claims(cwd: str) -> list:
    """Lazy wrapper over ``coordinator_core.session.claimed_plan
    .list_held_plan_claims`` (C1a) -- the SAME bootstrap
    (``_ensure_claude_klabauter_on_syspath``) step 4b's claimed-plan lookup already
    performs, reused rather than re-derived. Feeds both the scope-match tier
    and the ambiguity gate below (step 3b of the module docstring) with the
    ONE enumeration both consume. Never raises -- an unresolvable claude-klabauter
    root, an import failure, or any exception from the callee all degrade to
    ``[]``, the same omit-rather-than-guess contract ``list_held_plan_claims``
    itself documents."""
    claude_klabauter_root = _ensure_claude_klabauter_on_syspath()
    if not claude_klabauter_root:
        return []
    try:
        from coordinator_core.session.claimed_plan import list_held_plan_claims

        return list_held_plan_claims(cwd)
    except Exception:
        return []


def _resolve_deliverable_id_from_scope_match(cwd: str, paths: list, claims: list) -> str:
    """Lazy import of C2's landed
    ``coordinator_core.git.commit_trailers.resolve_deliverable_id_from_scope_match``
    -- step 3b of the module docstring. IMPORTED, not re-mirrored: verified
    live (C4) to trigger zero ``coordinator_core.ops`` module imports, so
    this costs no more than the pre-existing claimed-plan import below. That
    zero-import property depends on ``_ensure_claude_klabauter_on_syspath()`` (called
    just below) having already imported ``cc_invoke`` -- see the module
    docstring's ORDERING DEPENDENCY note under step 3b before reordering
    this call relative to that bootstrap.
    Never raises -- an unresolvable claude-klabauter root, an import failure, or any
    exception from the callee all degrade to ``""`` (tier abstains, caller
    falls through)."""
    claude_klabauter_root = _ensure_claude_klabauter_on_syspath()
    if not claude_klabauter_root:
        return ""
    try:
        from coordinator_core.git.commit_trailers import (
            resolve_deliverable_id_from_scope_match,
        )

        return resolve_deliverable_id_from_scope_match(cwd, paths, claims)
    except Exception:
        return ""


def _session_holds_multiple_plan_claims(claims: list) -> bool:
    """Lazy import of C2's landed
    ``coordinator_core.git.commit_trailers.session_holds_multiple_plan_claims``
    -- the ambiguity-gate predicate, step 3b of the module docstring.
    IMPORTED, not re-mirrored, for the same reason as
    ``_resolve_deliverable_id_from_scope_match`` above. Any import/lookup
    failure degrades to ``False`` -- the SAFE direction here is to NOT gate
    (fall through to the session-keyed tiers, today's behaviour), never to
    silently omit a resolvable trailer because the ambiguity check itself
    errored."""
    if not claims:
        return False
    claude_klabauter_root = _ensure_claude_klabauter_on_syspath()
    if not claude_klabauter_root:
        return False
    try:
        from coordinator_core.git.commit_trailers import (
            session_holds_multiple_plan_claims,
        )

        return session_holds_multiple_plan_claims(claims)
    except Exception:
        return False


def _resolve_deliverable_id_from_claimed_plan() -> str:
    """Step 4b of the module docstring: the same-session plan-execute path
    (no handoff). Reached only when steps 4 and 4a both miss.

    Lazily reaches into ``coordinator_core`` — deliberately NOT imported at
    module scope, so a hit on step 4/4a (the common case) never pays this
    import's cost on the commit hot path. Resolves the engine root via the
    self-location-first ``require_colocated_engine_on_path()`` (which wraps
    ``resolve_colocated_claude_klabauter_root()``; this script
    lives inside the claude-klabauter checkout at ``coordinator/bin/``, so
    ``Path(__file__)``'s own parents answer it with zero external
    dependency) SOLELY to put ``coordinator_core`` on ``sys.path`` for the
    import below -- ``resolve_claimed_plan_path()`` returns a path relative
    to THIS PROCESS's cwd (the repo the commit is landing in, per its own
    docstring), which is not necessarily the same repo this script's own
    ``__file__`` lives in (e.g. a hook process cwd'd into a different
    checkout); the plan file itself is therefore opened relative to the
    process cwd, never joined onto ``claude_klabauter_root``. Reuses
    ``resolve_claimed_plan_path()`` and the shared frontmatter primitives
    rather than re-deriving either — see that module's own negative-spec on
    the ``plan_claim_dir`` import-cycle trap before touching this function.

    Omit-rather-than-guess throughout: an unresolvable engine root, an
    unresolvable plan, a missing/unreadable file, or a missing/blank field
    all return ``""`` — never fabricates a value, never raises (any
    exception anywhere in this chain is swallowed and treated as "no
    match").

    Spec backlink: ``archive/specs/2026-08/2026-08-01-deliverable-id-carry-
    onto-executing-handoff.md`` execution note; DR-207 DD#1.
    """
    try:
        lib_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
        if lib_dir not in sys.path:
            sys.path.insert(0, lib_dir)
        from cc_invoke import require_colocated_engine_on_path

        require_colocated_engine_on_path(__file__)
        from coordinator_core.session.claimed_plan import resolve_claimed_plan_path
        from coordinator_core.frontmatter.primitives import (
            read_fm_field_unquoted,
            split_frontmatter,
        )

        plan_path = resolve_claimed_plan_path()
        if not plan_path:
            return ""

        with open(plan_path, encoding="utf-8") as fh:
            text = fh.read()
    except Exception:
        return ""

    split = split_frontmatter(text)
    if split is None:
        return ""
    deliverable_id = read_fm_field_unquoted(split.fm_text, "deliverable_id")
    # `read_fm_field_unquoted` is a text extractor, not a YAML-typed parser --
    # a `deliverable_id: null` line reads back as the LITERAL string "null",
    # not Python None. Treat that (and "none"/"~") as blank, the SAME
    # convention `coordinator_core.baton_assemble.__init__`'s own
    # `continued_into`/`predecessor` scalar reads already use.
    if isinstance(deliverable_id, str):
        cleaned = deliverable_id.strip()
        if cleaned and cleaned.lower() not in ("none", "null", "~"):
            return cleaned
    return ""


def _resolve_deliverable_id(git_dir: str, session_id: str, paths: "list | None" = None) -> str:
    """Step 3a (tier 0) + step 3b (scope-match tier + ambiguity gate,
    imported from C2's landed seam) + steps 4 + 4a + 4b of the module
    docstring: check the committed artifact(s) named by ``paths`` first
    (tier 0 — the multi-baton-session fix; see
    ``_resolve_deliverable_id_from_paths``), then a code-only commit's
    pathspec against every plan this session holds a claim on (step 3b —
    see ``_resolve_deliverable_id_from_scope_match``), gated by
    ``_session_holds_multiple_plan_claims`` (a 2+-claim session that neither
    tier above disambiguated OMITS the trailer rather than guessing among
    the session-keyed tiers below), then ``git_dir`` (the common
    single-baton case — a commit landed in the
    same repo ``/pickup`` ran in), then DoE-claude's own git-dir (the
    cross-repo case — a commit landed directly into claude-klabauter under the
    standing DoE→claude-klabauter write grant), then the session's claimed PLAN (the
    same-session plan-execute-without-a-handoff case — see
    ``_resolve_deliverable_id_from_claimed_plan``). Never fabricates a
    value; every lookup in the cascade is omit-rather-than-guess.

    Any failure raised resolving tier 0 is caught HERE, not left to
    propagate to ``main()`` — this hook's hot-path fail-soft contract
    (module docstring, step 3a) means an errored artifact lookup degrades to
    "tier 0 has nothing to say" and falls through to the session-keyed tiers
    below, never blocks or errors the commit.

    A DIVERGENT pathspec no longer reaches that arm and is not noted on
    stderr: DR-328 retired ``DivergentDeliverableIdError`` as a commit gate
    on the ruling that two deliverables in one commit "is not a divergence
    at all — it is ordinary", so tier 0 returns "" for it exactly as it does
    for an empty stage. Guarded by
    ``test_tier0_divergent_staged_artifacts_falls_back_soft_and_silent``.
    """
    if paths:
        try:
            deliverable_id = _resolve_deliverable_id_from_paths(
                paths, session_id=session_id, git_dir=git_dir
            )
        except Exception as exc:
            sys.stderr.write(
                "coordinator-prepare-commit-msg: tier-0 artifact deliverable-id "
                f"resolution failed ({exc}); falling back to "
                "session-keyed resolution.\n"
            )
            deliverable_id = ""
        if deliverable_id:
            return deliverable_id

    # Step 3b: scope-match tier + ambiguity gate (C4, importing C2's landed
    # seam). cwd is this process's own cwd -- the repo the commit is landing
    # in, matching what the git hook always runs against.
    cwd = os.getcwd()
    claims = _list_held_plan_claims(cwd)
    deliverable_id = _resolve_deliverable_id_from_scope_match(cwd, paths or [], claims)
    if deliverable_id:
        return deliverable_id
    if _session_holds_multiple_plan_claims(claims):
        return ""

    deliverable_id = _resolve_deliverable_id_at(git_dir, session_id)
    if deliverable_id:
        return deliverable_id
    doe_root = _resolve_doe_root()
    if doe_root:
        doe_git_dir = os.path.join(doe_root, ".git")
        if os.path.normpath(doe_git_dir) != os.path.normpath(git_dir):
            deliverable_id = _resolve_deliverable_id_at(doe_git_dir, session_id)
            if deliverable_id:
                return deliverable_id
    return _resolve_deliverable_id_from_claimed_plan()


def _has_trailer_line(commit_msg_file: str, prefix: str) -> bool:
    """Return True iff ``commit_msg_file`` already contains a line starting
    with ``prefix`` (e.g. ``"Session-Id:"``). Any read failure is treated as
    "not present" — the caller's outer try/except around the whole flow
    already guarantees exit 0 regardless."""
    try:
        with open(commit_msg_file, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith(prefix):
                    return True
    except Exception:
        return False
    return False


def _subject_line(commit_msg_file: str) -> str:
    """First non-blank, non-comment line of ``commit_msg_file`` — git's own
    notion of the subject. ``""`` on any read failure or an all-comment
    message (a commit being aborted)."""
    try:
        with open(commit_msg_file, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                return stripped
    except Exception:
        return ""
    return ""


def _warn_hyphen_range_subject(commit_msg_file: str) -> None:
    """Emit a write-time advisory (stderr, never a block) when the subject
    about to be committed uses a hyphen RANGE where the chunk-id convention
    takes an enumeration.

    Landed 2026-08-08 on a example-store-repo-em FYI memo (`cross-repo/inbox/
    2026-08-08-example-store-repo-em-close-out-and-stamp-chunk-id-separator.md`) —
    a second independent hit, in a consumer repo, of
    `state/lessons/2026-08-05-a-machine-parsed-commit-subject-is-an-api-and-
    a-hyphen-is-not-a-separator.yaml`. `_extract_chunk_ids` (close_out_and_
    stamp) recognizes `,`/`+`/`/` and deliberately NOT `-`, so `C1-C5:` takes
    the single-id path, matches no spine id, and five shipped chunks read as
    uncommitted at close-out — after which the honest repairs are a
    hand-stamp or a rebase of already-landed commits.

    The lesson's own discharge (`_hyphen_range_subject_diagnostics`) fires at
    close-out, which is the last possible moment; this is the first one. The
    sender's run is the evidence that read-time-only left a load-bearing gap:
    a human reads the range effortlessly, so nothing else in the chain
    disagrees with the author until the parser is consulted.

    NEVER blocks, and never edits the message. This hook's whole contract is
    fail-open (see this module's docstring and the `__main__` backstop), and
    a subject-shape opinion is emphatically not the thing to break it for.
    Rewriting `C1-C5:` into an enumeration is equally out of scope: this hook
    cannot know whether `C2`/`C3`/`C4` exist on the plan's spine, and
    inventing ids the author never wrote is the over-crediting
    `_extract_chunk_ids` already refuses on the read side.

    Negative-spec: do NOT widen `_HYPHEN_RANGE_SUBJECT_RE` to `..`/`through`/
    `etc` shapes on suspicion. The corpus contains legitimate compound tags
    carrying `..` inside a single id (`RESIDUE-C1..C7`); a diagnostic that
    confidently names a wrong cause is worse than none, and the hyphen shape
    is the one with two independent live incidents behind it.
    """
    subject = _subject_line(commit_msg_file)
    if not subject:
        return
    match = _HYPHEN_RANGE_SUBJECT_RE.match(subject)
    if not match:
        return
    left_prefix = match.group("lp")
    right_prefix = match.group("rp")
    if right_prefix and right_prefix.lower() != left_prefix.lower():
        return
    try:
        first = int(match.group("ln"))
        last = int(match.group("rn"))
    except ValueError:
        return
    if last <= first:
        return
    enumerated = ",".join("%s%d" % (left_prefix, n) for n in range(first, last + 1))
    sys.stderr.write(
        "[coordinator] commit subject reads as a chunk-id RANGE: %r\n"
        "              Write it enumerated instead: '%s: ...'\n"
        "              Close-out chunk-id parsing recognizes only , + / as "
        "separators (a hyphen is excluded on purpose — real ids carry one, "
        "e.g. DOCTRINE-C7a), so a range registers as ONE unknown id and every "
        "chunk in it reads as uncommitted at /execute-plan close-out.\n"
        "              Advisory only — this commit is NOT blocked; amend the "
        "subject now while it is free.\n"
        % (match.group(0).rstrip(":").strip(), enumerated)
    )


def main(argv: list) -> int:
    commit_msg_file = argv[0] if argv else ""
    if not commit_msg_file or not os.path.isfile(commit_msg_file):
        return 0

    # Ahead of the session-id gate on purpose: a range-shaped chunk-id
    # subject is equally wrong on a commit this hook adds no trailer to, and
    # the whole value of the advisory is that it lands BEFORE the commit
    # does. Pure string work — no subprocess, nothing added to the hot path.
    _warn_hyphen_range_subject(commit_msg_file)

    git_dir = _resolve_git_dir()
    session_id = _resolve_session_id(git_dir)
    if not session_id:
        return 0  # legitimate non-coordinator commit; leave unaffected.

    # Fail-safe: a non-UUID resolved id (e.g. a poisoned sentinel or a profiling-run
    # env override) must OMIT both trailers, never stamp a wrong Session-Id (or a
    # Deliverable-Id keyed off it). A missing trailer is coverage-neutral; a wrong
    # one mis-attributes session scope.
    # Spec: cross-repo/inbox/2026-07-21-claude-klabauter-em-claude-klabauter-session-id-leak-fix-reply.md (residual B(i))
    if not _UUID_RE.fullmatch(session_id):
        return 0

    try:
        need_session_id = not _has_trailer_line(commit_msg_file, "Session-Id:")
        need_deliverable_id_check = not _has_trailer_line(commit_msg_file, "Deliverable-Id:")
    except Exception:
        return 0

    trailer_args: list = []
    if need_session_id:
        trailer_args += ["--trailer", f"Session-Id: {session_id}"]
    if need_deliverable_id_check:
        staged_paths = _resolve_staged_paths()
        deliverable_id = _resolve_deliverable_id(git_dir, session_id, staged_paths)
        if deliverable_id:
            trailer_args += ["--trailer", f"Deliverable-Id: {deliverable_id}"]

    if not trailer_args:
        return 0  # idempotent: nothing missing (or nothing resolvable) to add.

    # Inject the trailer(s) in-place, ONE git interpret-trailers call. Failure
    # is swallowed — never block a commit.
    try:
        subprocess.run(
            ["git", "interpret-trailers", "--no-divider", "--in-place", *trailer_args, commit_msg_file],
            capture_output=True,
            timeout=15,
            **_no_console_creationflags(),
        )
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    # Top-level fail-open guard: an uncaught exception anywhere in main() (bad
    # argv shape, unexpected OSError, etc.) must never abort the commit — the
    # per-step try/excepts above cover the known failure points, but this is
    # the backstop honoring the "NEVER blocks a commit" contract even against
    # a future internal bug. exec-shim misinvocation (running this file under
    # `bash` instead of python3) is NOT caught here — that fails before Python
    # ever starts; the installer fix (git_hook_install.py) is the guard for
    # that failure mode.
    # Spec backlink: cross-repo/inbox/2026-07-21-example-market-data-repo-em-prepare-commit-msg-shim-execs-bash-on-python-hook.md
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
