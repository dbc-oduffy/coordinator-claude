"""
_resolve_claude_klabauter.py — shared resolve-claude-klabauter-bin ladder, extracted from
``coordinator_core.install.substrate._write_agent_forwarder``'s
formerly-inline-per-forwarder body.

Every emitted bin forwarder used to carry its own copy (~50 lines) of the
registry-then-sentinel resolution ladder that locates
``<claude-klabauter-root>/coordinator/bin/`` and validates it before exec'ing into a
target CLI there. With the forwarder SET now derived from a directory
listing (rather than a hand-maintained ~10-entry tuple — see
``substrate.py``'s ``_derive_agent_helper_names``), that duplication would
have scaled to ~127+ near-identical copies of the same ladder. This module
is installed ONCE (alongside every emitted forwarder, in the same shim
dir — settings-home ``bin/`` and the ``~/.claude/bin`` compat mirror) and
imported by each forwarder's now-trivial ~6-line body.

Contract preserved verbatim from the prior inline body (DoE-claude
``coordinator/snippets/resolve-claude-klabauter-bin.md``, DoE commit ``ad7fb0d1``):
registry-key-then-sentinel resolution rungs, ``coordinator/bin`` composition,
the ``..``-traversal guard, on-disk existence checks for the resolved root
and ``coordinator/bin``, an *executable* sentinel probe (``archive-stamp-cli``),
and distinct fail-loud messages for the two on-disk failure modes (wrong/
incomplete checkout vs. stale/partial migration).

Deliberately does NOT carry the ``_cc_trusted``/``.doe-root`` trust-prefix
dance the prior template never carried either — this seam's trust posture
differs from ``cc-root-source-guard``: ``registry.local.toml`` and
``.claude-klabauter-root`` are per-machine, gitignored, operator-authored config under
the operator's own settings-home, not a harness-supplied value an external
actor can steer. What this module DOES check — because a typo'd or stale
config value is a real, non-adversarial failure mode, not a trust boundary —
is exactly the four checks enumerated above.

Spec backlink:
    DoE-claude coordinator/snippets/resolve-claude-klabauter-bin.md (DoE commit ad7fb0d1)
    docs/plans/2026-07-23-... (M1 — forwarder-ladder extraction + derived set)
    cross-repo/inbox/2026-07-22-claude-central-em-forwarder-template-still-execs-dead-doe-bin.md

Port source: coordinator_core.install.substrate._write_agent_forwarder

Review: code-reviewer — sanctioned path-load consumer surface. Underscore-
prefixed names below (``_ml_dir``, ``_registry_value``,
``_resolve_claude_klabauter_root``) are NOT general-purpose public API — this module's
only stable contract for arbitrary callers is
``resolve_claude_klabauter_root_with_class()``, the ``RESOLUTION_*`` constants, and
``resolve_claude_klabauter_bin_dir()``/``exec_cli()``. The ONE declared exception:
``coordinator_core.engine_root`` (loaded BY PATH, never imported as a
package — see that module's own docstring) is a named path-load consumer of
``_ml_dir``, ``_registry_value``, and ``_resolve_claude_klabauter_root`` directly, in
its hot-path short-circuit that skips the full
``resolve_claude_klabauter_root_with_class()`` ladder when ``repos.claude_klabauter``
is not registered. Changing ``resolve_claude_klabauter_root_with_class()``'s step-1
precondition (the published-engine-registered-and-usable check) obliges
updating that wrapper's short-circuit in the SAME change — see
``coordinator_core/engine_root.py``'s matching declaration, and
``coordinator_core/tests/test_engine_root_two_tier.py``'s cross-entrypoint
agreement test (fixture: ``repos.claude_klabauter`` absent) for the
mechanical backstop that catches drift here.

C7 naming-retirement note
(docs/plans/2026-08-19-an-engine-root-is-a-stamped-build.md § C7,
docs/reference/engine-vs-locator-resolver-routing.md): C7 decided the fate
of the publish-time ``_resolve_claude_klabauter_root`` -> ``_resolve_claude_klabauter_root``
rename transform is to KEEP it, not retire it — it still functions as a
useful tripwire (a symbol that exists only post-publish, so a caller
accidentally importing the pre-publish name fails loud instead of silently
resolving the wrong tree). C7 also bucketed every caller of the
``_resolve_claude_klabauter``-symbol family across the tree by priority order into a
routing table (the doc above) rather than hand-triaging each one.

Naming note: this module's ``_resolve_claude_klabauter_root(ml_dir)`` above and
``coordinator/bin/lib/cc_invoke.py``'s module-level ``_resolve_claude_klabauter_root()``
are UNRELATED functions that happen to share a name — this one resolves
``repos.claude_klabauter`` (the SOURCE TREE / claude-klabauter repo location, the exact
"dangerous name" collision the PM's naming ruling calls out), cc_invoke's
resolves the ENGINE (dispatch axis, delegated through the DR-132/stamp
gate). This one is already the "source-tree resolver, confined to a named
narrow seam" C7's body asks for in substance — underscore-private, and its
only declared exception consumer is ``coordinator_core.engine_root``'s
path-load (see the Review note above) — but is NOT renamed to say so in
this pass: that consumer path-loads it BY THIS NAME, so a rename here
requires updating that consumer in the same change, and
``coordinator_core/engine_root.py`` is outside this chunk's ``writes:``
scope. Left as a named exception, not a silent skip.
"""
from __future__ import annotations

import os
import runpy
import stat
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple


class ClaudeKlabauterResolutionError(RuntimeError):
    """A fully-formed, fail-loud message ready to write to stderr verbatim.

    Each raise site below matches one distinct failure mode from the ladder
    (missing config, traversal, missing root, missing coordinator/bin,
    missing/non-executable sentinel) — callers must not collapse these into
    a single generic message; see module docstring.
    """


def _settings_home() -> Path:
    """Resolve the coordinator settings home (mirrors _claude_home.py's
    settings_home() precedence, replicated inline here rather than imported
    — this module must stay import-independent of coordinator_core, since it
    is installed standalone into a bare bin/ directory with no package
    context).

    HOME guard (2026-07-28): the Windows claude-doe.cmd -> `bash -c` launch
    chain is a NON-LOGIN, cmd-spawned shell env that can present with
    COORDINATOR_SETTINGS_HOME/CLAUDE_HOME/HOME all empty. The prior body then
    fell back to os.path.expanduser("~"), which returns a LITERAL "~" when no
    home var is resolvable — silently yielding the garbage relative path
    "~/.coordinator-claude-settings"; the shell-equivalent
    "$HOME/.coordinator-claude-settings" with empty $HOME collapses to
    "/.coordinator-claude-settings", which Windows resolves to the current
    DRIVE ROOT (a stray 0-byte ``<drive>:\\.coordinator-claude-settings`` was created that
    way, 2026-07-28). This resolver now (a) consults USERPROFILE so a bare
    cmd.exe session with no HOME still resolves on Windows, and (b) fails loud
    (ClaudeKlabauterResolutionError, caught by exec_cli into a clean stderr message)
    rather than returning a path a downstream writer lands junk at. Empty
    COORDINATOR_SETTINGS_HOME still falls through (unchanged) — a launch env
    that exports it empty must not start failing.
    """
    override = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if override:
        return Path(override)
    home = (
        os.environ.get("CLAUDE_HOME")
        or os.environ.get("HOME")
        or os.environ.get("USERPROFILE")
        or ""
    )
    if not home:
        expanded = os.path.expanduser("~")
        if expanded and expanded != "~":
            home = expanded
    if not home:
        raise ClaudeKlabauterResolutionError(
            "ERROR: cannot resolve the coordinator settings home — none of "
            "COORDINATOR_SETTINGS_HOME, CLAUDE_HOME, HOME, or USERPROFILE is set "
            "and '~' is unexpandable (a non-login shell env). Set CLAUDE_HOME or "
            "HOME to your home directory, or launch from a normal shell\n"
        )
    return Path(home) / ".coordinator-claude-settings"


def _ml_dir() -> Path:
    """Resolve the machine-local registry directory.

    Negative-spec: does NOT validate ``MACHINE_LOCAL_REGISTRY_DIR`` itself —
    by the time this override is read, the operator has already selected
    the file; a guard here would be vacuous (the value has no independent
    "before use" moment to police).
    """
    override = os.environ.get("MACHINE_LOCAL_REGISTRY_DIR")
    return Path(override) if override else (_settings_home() / "machine-local")


def _resolve_claude_klabauter_root(ml_dir: Path) -> str:
    """Resolve the claude-klabauter root path via the registry-then-sentinel
    ladder, validating it before return.

    Rung 1 (preferred): registry.toml (tracked baseline) then
    registry.local.toml (per-machine override, wins on collision) — key
    "repos.claude_klabauter" in either the nested [repos] table or the flat
    quoted-dotted-key form ``machine-local set`` writes. Empty-string is a
    miss, not a hit (never overwrites a value already resolved from the
    other file).

    Rung 2 (fallback): .claude-klabauter-root sentinel — honored when the registry key
    above is absent or the file itself is missing.

    Raises ClaudeKlabauterResolutionError (with a fail-loud, distinct message) when:
      - neither rung resolves anything,
      - the resolved value contains a '..' traversal segment,
      - the resolved value does not exist on disk as a directory.
    """
    claude_klabauter_root = ""
    for fname in ("registry.toml", "registry.local.toml"):
        registry_path = ml_dir / fname
        if not registry_path.is_file():
            continue
        try:
            import tomllib
            with open(registry_path, "rb") as f:
                registry_data = tomllib.load(f)
        except Exception:
            continue
        nested = registry_data.get("repos", {})
        if isinstance(nested, dict):
            v = nested.get("claude_klabauter")
            if isinstance(v, str) and v:
                claude_klabauter_root = v
        flat = registry_data.get("repos.claude_klabauter")
        if isinstance(flat, str) and flat:
            claude_klabauter_root = flat

    if not claude_klabauter_root:
        sentinel_path = ml_dir / ".claude-klabauter-root"
        try:
            with open(sentinel_path, "r", encoding="utf-8") as f:
                claude_klabauter_root = f.read().rstrip("\r\n")
        except OSError:
            claude_klabauter_root = ""

    claude_klabauter_root = claude_klabauter_root.rstrip("\r\n").rstrip("/")

    if not claude_klabauter_root:
        raise ClaudeKlabauterResolutionError(
            "ERROR: cannot resolve claude-klabauter — set it via 'machine-local set "
            f"repos.claude_klabauter <path>' (writes {ml_dir}/registry.local.toml), "
            f"or write the path to {ml_dir}/.claude-klabauter-root, or register a published "
            "engine mirror via 'machine-local set repos.claude_klabauter <path>'\n"
        )

    # Corrupted/typo'd-config guard, not a hostile-input guard — see module
    # docstring for why no harness-facing prefix-allowlist applies here.
    # Checks both separators: a resolved path can carry OS-native
    # backslashes on Windows (e.g. `str(Path(...))`), and `/..` alone would
    # silently miss a Windows-style `\..` traversal segment.
    if "/.." in claude_klabauter_root or "\\.." in claude_klabauter_root:
        raise ClaudeKlabauterResolutionError(
            f"ERROR: resolved claude-klabauter root '{claude_klabauter_root}' contains a "
            f"'..' traversal segment — refusing; fix {ml_dir}/registry.local.toml "
            f"or {ml_dir}/.claude-klabauter-root\n"
        )

    if not os.path.isdir(claude_klabauter_root):
        raise ClaudeKlabauterResolutionError(
            f"ERROR: resolved claude-klabauter root '{claude_klabauter_root}' does not exist "
            "on disk — re-run 'machine-local set repos.claude_klabauter <path>' or fix "
            f"{ml_dir}/.claude-klabauter-root\n"
        )

    return claude_klabauter_root


# Resolution classes returned alongside the root by
# ``resolve_claude_klabauter_root_with_class()``. Verbatim from DoE-claude's
# ``coordinator/hooks/scripts/_engine_root.py`` — a conformance fixture
# (chunk C8) drives both implementations against the same registry-state
# cases, so the string values themselves are part of the contract, not just
# their names.
RESOLUTION_RESOLVED_ENGINE = "resolved-engine"
RESOLUTION_LIVE_WORKING_TREE = "live-working-tree"
RESOLUTION_UNRESOLVED = "unresolved"


# --- publisher-only targets: never resolvable from the published engine ----
#
# ``resolve_claude_klabauter_root_with_class()``'s divert (C5) sends any session whose
# own repo root is not the live claude-klabauter checkout to the published engine
# mirror. For nearly every forwarded target that is correct — the mirror
# carries a complete, stamped engine build. For the percolate publish
# family it is not, and cannot be made so: the mirror is the PUBLISH
# DESTINATION, and the modules these targets dispatch against
# (``coordinator_core.percolate.*``, ``coordinator_core.ops.percolate_run``)
# are publisher-side only and deliberately absent from it — see
# ``state/bug-backlog/2026-08-11-klabauter-mirror-ships-the-ops-registry-287f6526da3a.yaml``.
# Their FILENAMES are published (C13 closed the per-name gap so a missing
# target means a broken install rather than a known hole), so the divert
# resolves, the sentinel probe passes, the target file exists — and the run
# then dies on an import that can never succeed there. ``--dry-run`` returns
# before that import, so it reports clean and reads as clearance.
#
# These targets therefore resolve LIVE-TREE-ONLY, via ``_resolve_claude_klabauter_root``
# (the single-tier ladder ``resolve_claude_klabauter_bin_dir`` uses), and fail loud
# naming the publisher when it misses. Publishing FROM the published copy is
# not a thing that can work, so there is no second root to try.
#
# MEMBERSHIP RULE — publish-DENIED, not percolate-importing. The percolate
# family above is the loudest instance of the class, never its definition.
# The rule is: a ``coordinator/bin/*.py`` name on the
# ``claude-klabauter-coordinator-bin`` row's ``deny`` list in
# ``setup/publish-allowlist-declarations.yaml`` is never published at all, so
# a session diverted to the mirror finds no target under EITHER spelling and
# dies at C13's fail-loud 127 naming a root that could never have carried it.
# That remediation cannot be acted on: the file is not missing from a broken
# install, it is absent by declaration. Five names were publisher-only by that
# rule while the earlier import-token reading admitted only the percolate
# five — ``check-persona-slug-leak``, ``coordinator-validate-local-config``,
# ``engine-gap-lint``, ``percolate-push`` and ``publish-time-transform-py``
# each shipped a forwarder that diverted and died. Deny is the CAUSE; the
# percolate import is one symptom of it.
#
# Do NOT read the mirror on disk to decide membership. The mirror is a build
# artifact and may be any vintage; the declarations yaml is the authoring
# input that decides what a round ships, and it is the same answer on a box
# with no mirror at all.
#
# Hand-maintained here because this module is installed standalone into a
# bare ``bin/`` with only the stdlib importable (see the module docstring) —
# it cannot read the declarations yaml or import the engine to derive the set.
# Drift is caught instead by
# ``coordinator_core/install/test_resolve_claude_klabauter_publisher_only.py``, which
# re-derives the set from that ``deny`` list and fails when the two disagree,
# in BOTH directions. That guard is what makes the next omission impossible
# rather than merely unlikely: adding a bin CLI to ``deny`` without adding it
# here turns the suite red.
PUBLISHER_ONLY_TARGETS = frozenset({
    "check-persona-slug-leak.py",
    "coordinator-publish.py",
    "coordinator-validate-local-config.py",
    "engine-gap-lint.py",
    "percolate-gate.py",
    "percolate-push.py",
    "percolate-round.py",
    "publish-time-transform-py.py",
    "publish.py",
    "verify-publish-targets-portable-sync.py",
})


def _is_publisher_only_target(target: str) -> bool:
    """True iff *target* names a member of ``PUBLISHER_ONLY_TARGETS``.

    Accepts the bare and ``.py``-suffixed spellings alike: the installed
    forwarders name one or the other depending on when they were generated
    (see ``exec_cli``'s ``.py``-suffix probe and the POSIX-exec drain that
    made both spellings live at once), and a resolution rule that fired for
    only one of them would be a coin flip on install vintage."""
    base = target.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return base in PUBLISHER_ONLY_TARGETS or (base + ".py") in PUBLISHER_ONLY_TARGETS


# --- C5: engine/edit skew advisory -----------------------------------------
#
# PM-ruled 2026-08-07 (option (b), verbatim: "that's fine, skew detection").
# Spec backlink: pln-two-tier-engine-root-resolutio-024269 § C5
#
# Fires exactly once per process, ONLY when this resolution came back
# ``RESOLUTION_RESOLVED_ENGINE`` (a published engine was chosen) AND
# ``repos.claude_klabauter`` *also* resolves to an existing directory on this
# box — the genuinely ambiguous configuration: a live working tree exists,
# but the CLI just invoked is not that tree. Reports a CONFIGURATION, never a
# staleness verdict — deliberately NOT a sha comparison (a stored ref
# "nothing compares against gets trusted eventually"); a pure registry read
# that cannot go stale.
#
# Negative-spec:
#   - Does NOT spawn a subprocess or touch git — reuses ``_resolve_claude_klabauter_root``
#     (registry-then-sentinel rungs only), the same pure-read ladder
#     ``resolve_claude_klabauter_root_with_class`` already runs for the live-tree leg.
#   - Does NOT fire for ``RESOLUTION_LIVE_WORKING_TREE`` or
#     ``RESOLUTION_UNRESOLVED`` — only the resolved-engine branch is the
#     ambiguous one this advisory exists to name.
#   - Writes to stderr ONLY, never stdout — this module is loaded by every
#     emitted forwarder and by hook-path callers; stdout is reserved for
#     PreToolUse hook JSON envelopes and CLI target output.
#
# PM-ruled 2026-08-10: OPT-IN, not opt-out. This module is loaded by every
# forwarder, so the advisory landed on the `claude` startup banner — PM-facing
# chrome on a configuration only an engine-side reader can act on. Silent
# unless CLAUDE_KLABAUTER_ROOT_SKEW_VERBOSE is set; the older QUIET kill-switch stays
# honoured (it wins over VERBOSE) so an install that exported it keeps working.
CLAUDE_KLABAUTER_SKEW_ADVISORY_QUIET_VAR = "CLAUDE_KLABAUTER_ROOT_SKEW_QUIET"
CLAUDE_KLABAUTER_SKEW_ADVISORY_VERBOSE_VAR = "CLAUDE_KLABAUTER_ROOT_SKEW_VERBOSE"

_skew_advisory_emitted = False


def _env_flag_set(name: str) -> bool:
    """True iff ``name`` is present and not one of the falsey spellings.

    Review: code-reviewer — a bare truthy check on the raw string treats "0"
    and "false" as set, since Python treats those strings as truthy; an
    operator spelling a flag off that way would silently get it on.
    """
    raw = os.environ.get(name)
    if raw is None:
        return False
    return raw.strip().lower() not in ("", "0", "false")


def _reset_skew_advisory() -> None:
    """Test-only helper: clear the once-per-process advisory flag."""
    global _skew_advisory_emitted
    _skew_advisory_emitted = False


# --- C3b: the currency verdict this door READS and never computes -----------
#
# The advisory above reports a CONFIGURATION (you ran the mirror, not your
# tree) and deliberately not a vintage. That left the harm unaddressed: a
# session against a stale mirror produces work that silently does not take
# effect, which is what this plan's own authoring burned six cross-session
# messages on.
#
# WHY THIS DOOR MAY NOT COMPUTE IT. `warm.skew.publish_lag` costs 15.6ms of
# process time / 99.3ms wall (measured k=5, 2026-08-28) and two git spawns,
# and this module is on the interpreter floor of EVERY coordinator invocation
# on a box carrying 50-70 concurrent sessions. It is also forbidden to import
# `coordinator_core` at all. So the verdict is computed by the post-commit
# path -- which runs on the event that invalidates it and already pays for git
# -- and read here for 0.078ms (measured k=200).
#
# TWO POPULATIONS, TWO ANSWERS, AND THEY ARE DIFFERENT AXES:
#
#   Box WITH a claude-klabauter checkout: "N commits behind" is computable, and the
#   cache carries it. The key is (source HEAD sha, engine stamp text); a
#   verdict whose key does not match what this door observes is ABSENT, never
#   a lower-confidence answer.
#
#   Box WITHOUT one -- the population that diverts in the first place: the
#   commit count is not computable by ANYTHING here. `publish_lag` resolves
#   the stamp sha against the source history, and that sha is not present in
#   the mirror's own history (`git cat-file` rc=128, measured 2026-08-28). The
#   only vintage fact that population holds is when the round ran, which
#   publish emits as `_engine_published_at`.
#
# NEGATIVE SPEC -- AN AGE IS NOT A WEAK STALENESS MEASURE, IT IS A DIFFERENT
# QUESTION, and the two come apart in BOTH directions: a mirror published
# three days ago is current if nothing engine-touching landed since, and one
# published five minutes ago can be six commits behind. So the published-at
# line MUST say which axis it is on. A signal that gets read as the other axis
# is the failure this whole plan exists to remove.
#
# NEGATIVE SPEC -- do NOT read the timestamp off the stamp file's mtime, and
# do NOT fold it into `_engine_stamp`. mtime does not survive a copy, rsync,
# clone or archive extract -- every one of which is how a mirror arrives on a
# checkout-free box. And `skew.read_engine_stamp_sha` silently returns a
# CORRUPT sha for both an inline and a second-line extension of the stamp
# (measured), which takes the currency signal dark rather than wrong.
_CURRENCY_CACHE_RELATIVE_PARTS = ("coordinator", "engine-currency.json")

#: Sibling of `_engine_stamp`, written by the percolate round
#: (`percolate.rewrite_basename.emit_published_at`). A SIBLING, never a second
#: line in the stamp -- see this section's second negative spec.
_PUBLISHED_AT_RELATIVE_PARTS = ("coordinator_core", "_engine_published_at")


def _currency_cache_path() -> Optional[Path]:
    """Standalone twin of `warm.skew.currency_cache_path` -- this module
    cannot import it (see the module docstring's stdlib-only rule), so the two
    are synchronised by hand and asserted equal by
    `coordinator_core/install/test_resolve_claude_klabauter_currency_signal.py`."""
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if not local:
        return None
    return Path(local).joinpath(*_CURRENCY_CACHE_RELATIVE_PARTS)


def _source_head_sha(source_root: str) -> Optional[str]:
    """Standalone twin of `warm.skew.source_head_sha` -- the source tree's
    HEAD sha read straight off `.git`, no subprocess. Never raises; `None`
    means "no key", which means "no verdict"."""
    try:
        git_dir = Path(source_root) / ".git"
        raw = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if not raw.startswith("ref: "):
            return raw or None
        ref = raw[5:].strip()
        try:
            return (git_dir / ref).read_text(encoding="utf-8").strip() or None
        except OSError:
            pass
        for line in (git_dir / "packed-refs").read_text(encoding="utf-8").splitlines():
            if line.endswith(" " + ref):
                return line.split()[0]
        return None
    except Exception:
        return None


def _cached_commits_behind(published: str, live: Optional[str]) -> Optional[int]:
    """The cached commit count, iff its key still matches what this door
    observes right now. `None` for every other outcome -- no cache, no live
    tree to key against, a key that has moved, or a malformed payload -- and a
    key mismatch is deliberately indistinguishable from an absent cache here.
    Never raises."""
    if not live:
        return None
    path = _currency_cache_path()
    if path is None:
        return None
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
        key = payload.get("key") or {}
        if key.get("source_head") != _source_head_sha(live):
            return None
        stamp = Path(published).joinpath(*_ENGINE_STAMP_RELATIVE_PARTS)
        if key.get("engine_stamp") != stamp.read_text(encoding="utf-8").strip():
            return None
        behind = payload.get("engine_commits_behind")
        return behind if isinstance(behind, int) and behind > 0 else None
    except Exception:
        return None


def _published_at(published: str) -> Optional[str]:
    """The round's own timestamp as publish committed it, or `None`. An absent
    or unreadable file is UNKNOWN -- never an error, and never a zero. Every
    mirror published before this file existed carries none."""
    try:
        raw = Path(published).joinpath(*_PUBLISHED_AT_RELATIVE_PARTS).read_text(
            encoding="utf-8"
        ).strip()
        return raw or None
    except Exception:
        return None


def _currency_line(published: str, live: Optional[str]) -> Optional[str]:
    """The one line this door adds about the mirror's vintage, or `None` when
    it holds no vintage fact at all. Silence is the correct degradation and
    the ordinary one."""
    behind = _cached_commits_behind(published, live)
    if behind is not None:
        return (
            f"        behind  {behind} commit(s) touching engine code — "
            "publish: python coordinator/bin/coordinator-publish.py\n"
        )
    if live is not None:
        # A box holding the source history is the population for which the
        # COUNT is the answer. No cache yet means no verdict yet, and silence
        # is the right degradation — falling through to the age here would put
        # "what landed since is not knowable" on a box where it is knowable
        # and may well be zero. Two axes, and this is the seam between them.
        return None
    at = _published_at(published)
    if at:
        # Says its axis in its own words. "published at T" is a fact this box
        # can hold; "stale" is not a claim it can make.
        return f"        published  {at} (an age — what landed since is not knowable here)\n"
    return None


def _maybe_emit_skew_advisory(ml_dir: Path, published: str) -> None:
    """Emit the engine/edit skew advisory (stderr, once per process) iff
    ``repos.claude_klabauter`` ALSO resolves to an existing directory
    alongside the published-engine resolution just made, AND the operator
    opted in via ``CLAUDE_KLABAUTER_ROOT_SKEW_VERBOSE``. Silent, and never raises, on
    any other outcome (not opted in, kill-switch set, already emitted, or
    ``repos.claude_klabauter`` unset/unresolved/nonexistent)."""
    global _skew_advisory_emitted
    if _skew_advisory_emitted:
        return
    if not _env_flag_set(CLAUDE_KLABAUTER_SKEW_ADVISORY_VERBOSE_VAR):
        return
    if _env_flag_set(CLAUDE_KLABAUTER_SKEW_ADVISORY_QUIET_VAR):
        return
    try:
        live: Optional[str] = _resolve_claude_klabauter_root(ml_dir)
    except ClaudeKlabauterResolutionError:
        live = None
    except Exception:
        live = None

    # C3b: the vintage line, computed by the post-commit path and only read
    # here. Resolved BEFORE the early return below, because the configuration
    # note needs a live tree to compare against and the vintage does not — a
    # box with no claude-klabauter checkout is exactly the population that diverts, and
    # returning silently there is what left it with no signal at all.
    currency = _currency_line(published, live)
    if live is None and currency is None:
        return

    _skew_advisory_emitted = True
    # Shape, not decoration: the consequence leads, and the two paths are
    # aligned so the reader compares them at a glance instead of parsing them
    # out of prose. No silencing tail — the reader set VERBOSE to get here and
    # knows how to unset it. The registry key name is deliberately NOT here:
    # implementation detail for a reader of this module, not of this notice.
    if live is not None:
        sys.stderr.write(
            "note: ran the published engine, not your working tree — "
            "edits to the tree do not affect this CLI.\n"
            f"        ran   {published}\n"
            f"        tree  {live}\n"
        )
    elif currency is not None:
        sys.stderr.write(f"note: ran the published engine at {published}.\n")
    if currency is not None:
        sys.stderr.write(currency)


def _flatten_registry(data: dict, _prefix: str = "") -> dict:
    """Flatten nested registry TOML tables to dotted keys.

    Mirrors DoE's ``_engine_root.py::_flatten_registry`` bit-for-bit —
    ``_registry_value`` below needs to look up keys under a table prefix
    (e.g. ``repos.claude_klabauter``) the same way regardless of whether the
    on-disk TOML used a nested table form or the flat quoted-dotted-key form
    ``machine-local set`` writes. ``_resolve_claude_klabauter_root`` above does not use
    this helper — it reads exactly one key with its own inline nested/flat
    handling, predates this extraction, and stays untouched (AC7:
    byte-identical on a single-tree box)."""
    result: dict = {}
    for k, v in data.items():
        full_key = f"{_prefix}{k}"
        if isinstance(v, dict):
            result.update(_flatten_registry(v, _prefix=f"{full_key}."))
        else:
            result[full_key] = v
    return result


def _registry_value(ml_dir: Path, key: str) -> Optional[str]:
    """Read *key* from the machine-local registry TOML pair under *ml_dir*.

    Reads ``registry.local.toml`` before the tracked ``registry.toml``
    baseline and returns the first hit — mirrors DoE's ``_registry_value``.
    Fail-open throughout: missing file, unparseable TOML, or a missing
    ``tomllib`` (pre-3.11) all fall through to the next rung rather than
    raising. An empty-string value is a declaration, not a resolution."""
    try:
        import tomllib
    except ImportError:
        return None

    for name in ("registry.local.toml", "registry.toml"):
        reg = ml_dir / name
        try:
            if not reg.is_file():
                continue
            with reg.open("rb") as fh:
                data = tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError):
            continue
        v = _flatten_registry(data).get(key)
        if isinstance(v, str) and v:
            return v

    return None


# --- C3: box-wide engine target -------------------------------------------
#
# PM RULING 2026-08-16, verbatim: "There will not be any 'some repos use x
# engine, others use y engine' as the engine choice will be for the entire
# box." One declared fact, box-wide, two values. No per-repo axis exists to
# SET this — ``engine.working_repos`` (above) remains a per-repo LOCATOR
# (which repos are working trees to divert away from), a different axis
# entirely; C4 retires its exemption duty but this fact never grows one of
# its own.
#
# Registry key: ``engine.target`` (nested ``[engine] target = "..."`` or the
# flat quoted-dotted-key form ``machine-local set`` writes), read via
# ``_registry_value`` — registry.local.toml (per-machine override) wins over
# the tracked registry.toml baseline, first-hit-wins, identical precedence to
# every other declared fact this module reads.
#
# HARD CONSTRAINT (memo-invalidation): this key MUST live in one of the two
# files ``_registry_mtime_pair`` (coordinator_core/engine_root.py) already
# stats -- registry.toml or registry.local.toml -- so that writing it
# self-invalidates both ``_ROOT_MEMO`` and ``_GATE_MEMO`` by mtime with no
# explicit reset call. ``_registry_value`` reads exactly those two files, so
# this constraint is satisfied by construction; do not move this fact to a
# new sentinel file, a settings-home JSON, or an env-only var -- any of those
# would sit outside the stat tuple and make a rollback silently ineffective
# for every process that has already resolved. ``_reset_root_memo()`` is a
# test-only seam with zero non-test callers -- it is not the rollback
# mechanism; the mtime pair changing IS the mechanism.
#
# NEGATIVE SPEC: this is NOT a channel axis on the resolver's ladder above --
# ``resolve_claude_klabauter_root_with_class()`` still resolves a PATH, and this
# declaration does not touch it, ``resolution_class``, or the conformance
# schema. The target fact is a declared value for resolution/diagnostics
# callers (C8+) to consume later, never a per-call ref check spliced into the
# ladder here.
#
# NEGATIVE SPEC: never inferred from whatever the mirror has checked out.
# Declared or nothing -- the closed defect ``track_ref`` already exists to
# prevent that shape.
#
# AC20: absent or unreadable is a READ-SITE default (resolves the way the
# box resolves today), never a third stored value and never an opt-out --
# ``resolve_engine_target`` returns ``None`` for both "key absent" and "key
# present but not one of the two declared values" (a typo'd/stale config
# value is treated the same as absence, not raised as an error -- consistent
# with every other fail-open reader in this module).
ENGINE_TARGET_MAIN = "main"
ENGINE_TARGET_CANDIDATE = "candidate"
ENGINE_TARGET_KEY = "engine.target"
ENGINE_TARGET_VALUES = frozenset({ENGINE_TARGET_MAIN, ENGINE_TARGET_CANDIDATE})


def resolve_engine_target(ml_dir: Optional[Path] = None) -> Optional[str]:
    """Read the box-wide ``engine.target`` fact, or ``None`` if absent,
    unreadable, or not one of the two declared values.

    ``ml_dir`` defaults to ``_ml_dir()`` (same override-aware resolution
    every other reader in this module uses) when not supplied. Never raises.
    """
    if ml_dir is None:
        ml_dir = _ml_dir()
    value = _registry_value(ml_dir, ENGINE_TARGET_KEY)
    if value not in ENGINE_TARGET_VALUES:
        return None
    return value


def _same_repo_path(a: str, b: str) -> bool:
    """Cross-platform path-equality check — mirrors DoE's
    ``_same_repo_path``: ``samefile`` when both paths exist, falling back to
    ``normcase``+``realpath`` comparison (so a registry entry pointing at a
    not-yet-cloned repo never raises). Never raises.

    Mirrors ``coordinator_core.win_portability.same_path`` (the consolidated
    primitive; state/sizings/2026-08-07-path-equality-consolidates-onto-one-
    prim.yaml) but does NOT import it -- this module's own docstring requires
    it to stay import-independent of coordinator_core (installs standalone
    into a bare ``bin/`` with no package context), so this copy is a
    PERMANENT, structural exception, not a laggard."""
    try:
        return os.path.samefile(a, b)
    except Exception:
        try:
            return os.path.normcase(os.path.realpath(a)) == os.path.normcase(
                os.path.realpath(b)
            )
        except Exception:
            return False


def _session_repo_root() -> Optional[Path]:
    """The repo root of the SESSION currently running.

    Mirrors DoE's ``_session_repo_root``: ``CLAUDE_PROJECT_DIR`` env var
    first, then a pure-Python upward walk from ``Path.cwd()`` looking for a
    ``.git`` entry (directory for a normal clone, file for a worktree).
    Never raises. Returns ``None`` if undeterminable."""
    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_root:
        try:
            p = Path(env_root)
            if p.is_dir():
                return p
        except Exception:
            pass

    try:
        cwd = Path.cwd()
    except Exception:
        return None

    try:
        for candidate in (cwd, *cwd.parents):
            if (candidate / ".git").exists():
                return candidate
    except Exception:
        return None

    return None


def _is_claude_klabauter_source_tree(ml_dir: Path) -> Optional[bool]:
    """Is the CURRENT session running inside the engine's OWN resolved
    source tree — i.e. does ``_session_repo_root()`` equal
    ``_resolve_claude_klabauter_root()``'s own resolved value?

    RETIRES the per-repo exemption family (``_is_engine_working_repo`` /
    ``_engine_working_repo_roots``, both removed) that used to answer this
    by scanning ``engine.working_repos.*`` set membership. PM ruling
    2026-08-18: a per-repo exemption family cannot express a box-wide
    choice, so it does not survive as the discriminant here — but the
    discriminant this function DOES express is not a list either. It is one
    STRUCTURAL relationship ("is this session inside the tree that IS the
    engine"), derived from the single root the live-tree ladder already
    computes, with nothing to enumerate and nothing to maintain per repo.
    ``engine.working_repos`` itself survives unmodified as a PURE LOCATOR
    (other callers still read it to find a named repo's root — see
    ``setup_chain_walker.py``, ``workday-start-health-probes.py``) — it is
    simply no longer consulted HERE, because resolution class was never a
    box-wide-choice-shaped question and a locator was never the right tool
    to answer a structural one. See the tripwire this must not re-derive:
    ``coordinator-tripwires/repos-star-is-not-engine-working-set.md``
    (``REPOS-STAR-IS-NOT-ENGINE-WORKING-SET``) — this function does not read
    ``repos.*`` at all, only the ONE ``repos.claude_klabauter``-keyed value
    ``_resolve_claude_klabauter_root`` itself already resolves for the live-tree leg,
    so no working-set is being re-derived here under a new name.

    Tri-state, deliberately, mirroring the retired function's contract:
    ``True``/``False`` are determinations; ``None`` means "could not
    determine" (no session root, or the live-tree ladder itself does not
    resolve) — a genuinely different thing from ``False``. A caller MUST NOT
    treat ``None`` as ``False``: diverting an undeterminable session away
    from the live tree, with nowhere principled to divert it FROM, would
    silently strand it. See ``resolve_claude_klabauter_root_with_class``'s ``is False``
    check, never bare falsiness. Never raises."""
    session_root = _session_repo_root()
    if session_root is None:
        return None

    try:
        live_root = _resolve_claude_klabauter_root(ml_dir)
    except ClaudeKlabauterResolutionError:
        return None

    try:
        return _same_repo_path(str(session_root), live_root)
    except Exception:
        return None


#: C5 (docs/plans/2026-08-19-an-engine-root-is-a-stamped-build.md): "an
#: engine root is a stamped build. No stamp, no engine." This module cannot
#: import ``coordinator_core.warm.engine_root`` (the C2 shared predicate) —
#: its own module docstring requires it stay import-independent of
#: ``coordinator_core``, since it is installed standalone into a bare
#: ``<settings-home>/bin/`` with only the stdlib importable. The predicate
#: is therefore replicated inline here rather than imported: "readable and
#: non-empty" at ``<root>/coordinator_core/_engine_stamp``, mirroring
#: ``coordinator_core.warm.skew.ENGINE_STAMP_FILENAME`` /
#: ``_engine_stamp_path`` byte-for-byte in shape. Keep the two in sync by
#: hand if the stamp filename or location ever changes.
_ENGINE_STAMP_RELATIVE_PARTS = ("coordinator_core", "_engine_stamp")


def _is_stamped_engine_root(root_path: Path) -> bool:
    """True iff *root_path* carries a valid engine build stamp.

    Standalone twin of ``coordinator_core.warm.engine_root.is_engine_root``
    — see ``_ENGINE_STAMP_RELATIVE_PARTS`` above for why this cannot import
    that module instead. Never raises."""
    stamp_path = root_path.joinpath(*_ENGINE_STAMP_RELATIVE_PARTS)
    try:
        return len(stamp_path.read_bytes()) > 0
    except OSError:
        return False


def _resolve_published_engine(ml_dir: Path) -> Optional[str]:
    """The published-engine seam — resolves the published engine mirror
    (``repos.claude_klabauter``), the coordinator-engine distribution a
    consumer repo should fall back to when its own tree is not the live
    working checkout.

    "Registered and usable" iff the key resolves to a value, that path
    exists as a directory, ``<root>/coordinator_core`` exists (guards the
    half-installed-clone case, where a root got registered before its clone
    finished), AND the root carries a valid engine build stamp (C5: "an
    engine root is a stamped build. No stamp, no engine." —
    ``_is_stamped_engine_root`` above). An unstamped tree is no longer
    "usable" here at all, regardless of directory shape — this is the
    published-engine half of C5's fail-closed rule; the live-working-tree
    leg (``_resolve_claude_klabauter_root``) is deliberately untouched by this check.
    Fail-open, never raises."""
    try:
        root = _registry_value(ml_dir, "repos.claude_klabauter")
        if not root:
            return None
        root_path = Path(root)
        if not root_path.is_dir():
            return None
        if not (root_path / "coordinator_core").is_dir():
            return None
        if not _is_stamped_engine_root(root_path):
            return None
        return root
    except Exception:
        return None


def resolve_claude_klabauter_root_with_class() -> Tuple[Optional[str], str]:
    """Resolve the engine root AND say which class of thing answered — this
    is the DISPATCH axis: "which engine executes?".

    C5 (docs/plans/2026-08-19-an-engine-root-is-a-stamped-build.md, see
    docs/reference/engine-root-resolution.md and the C10 decision record):
    **the ladder now prefers the published, STAMPED engine over the live
    working tree on dispatch.** This REVERSES the prior rule recorded here
    (DR-132's live-tree preference, "do not simplify this into a
    live-tree-first ladder or invert it to prefer the published engine") —
    that prohibition is superseded, not merely violated; see DR-132's/
    DR-328's supersede notes and the new decision record. The rule is now:
    an unstamped tree is never a legitimate answer to "which engine
    executes" — ``_resolve_published_engine`` denies an unstamped published
    root outright (C5), and C4 already removed the live-tree ref-based
    fallback from ``compute_client_token``. The LOCATOR axis ("where is the
    claude-klabauter repo?") is unaffected — ``resolve_claude_klabauter_bin_dir()`` below stays
    single-tier, live-tree-only, deliberately un-flipped; see its own
    docstring and DR-326.

    Returns ``(root, resolution_class)`` where the class is one of
    ``RESOLUTION_RESOLVED_ENGINE``, ``RESOLUTION_LIVE_WORKING_TREE``, or
    (only via a raised ``ClaudeKlabauterResolutionError`` — see below)
    ``RESOLUTION_UNRESOLVED`` never actually returned by this function today,
    since the terminal miss raises rather than returning a sentinel tuple;
    it is exported for callers building their own class-comparison logic.

    Ladder:
      1. A published engine registered/usable AND ``engine.target`` is
         readable (AC20: presence/readability only — its VALUE is never
         inspected here, same as DoE's own reader) AND the structural gate
         (``_is_claude_klabauter_source_tree`` — is THIS session inside the engine's
         own resolved source tree?) returns literally ``False`` (a
         CONFIRMED not-the-source-tree session, not an undeterminable one)
         -> ``(published, RESOLUTION_RESOLVED_ENGINE)``.
      2. Otherwise today's existing ladder (``_resolve_claude_klabauter_root``:
         registry key -> ``.claude-klabauter-root`` sentinel) -> if it resolves,
         ``(root, RESOLUTION_LIVE_WORKING_TREE)``.
      3. Otherwise, if a published engine is registered/usable ->
         ``(published, RESOLUTION_RESOLVED_ENGINE)``.
      4. Otherwise re-raise the ``ClaudeKlabauterResolutionError`` step 2 raised —
         "the existing" error, its remediation text now extended (see
         ``_resolve_claude_klabauter_root``) to also mention ``repos.claude_klabauter``.

    2026-08-18 (C4): step 1's discriminant used to be per-repo
    ``engine.working_repos.*`` set membership (``_is_engine_working_repo``,
    retired). PM ruling: a per-repo exemption family cannot express a
    box-wide choice. The structural check that replaced it answers the same
    question ("is this session the engine's own source, or does it fall
    through to the published mirror") without a membership list — you
    cannot develop the engine while running a different copy of it, which is
    a structural fact about THIS session's root vs. the ONE resolved claude-klabauter
    root, not a per-repo exemption. Consequence, deliberate: a session in
    any OTHER repo (doe-claude, project-rag, ...) now diverts to the
    published engine where it may not have before, even if that repo
    happens to be listed under ``engine.working_repos.*`` (that key remains
    a pure LOCATOR for other callers — see ``setup_chain_walker.py`` — it is
    simply not this gate's input any more).

    ``engine.target`` GATES the divert too (AC20, ruling correction
    2026-08-18): a box with ``repos.claude_klabauter`` registered but
    ``engine.target`` never written (every machine installed before C8) MUST
    NOT divert — "not yet rolled out" is the only meaning of absence, never
    a silent opt-in, and C8's installer writes the key on the same pass that
    registers the mirror. Presence/readability only; the VALUE (``main`` vs
    ``candidate``) selects a channel elsewhere and is never inspected here,
    matching DoE's own reader.

    Fail-open (AC7): on a single-tree box with no ``repos.claude_klabauter``,
    ``published`` is always ``None`` and step 1 never fires — behavior
    collapses to step 2 exactly as it runs today, byte-identical."""
    ml_dir = _ml_dir()
    published = _resolve_published_engine(ml_dir)
    target_readable = resolve_engine_target(ml_dir) is not None

    if published and target_readable and _is_claude_klabauter_source_tree(ml_dir) is False:
        _maybe_emit_skew_advisory(ml_dir, published)
        return published, RESOLUTION_RESOLVED_ENGINE

    try:
        live = _resolve_claude_klabauter_root(ml_dir)
        return live, RESOLUTION_LIVE_WORKING_TREE
    except ClaudeKlabauterResolutionError:
        if published:
            _maybe_emit_skew_advisory(ml_dir, published)
            return published, RESOLUTION_RESOLVED_ENGINE
        raise


def _is_executable(path: str) -> bool:
    """Stdlib-only twin of ``coordinator_core.win_portability.is_executable``
    — POSIX exec-bit inspection, Windows PATHEXT resolvability (a suffixed
    file must carry a PATHEXT suffix; an extensionless one is launchable only
    via a PATHEXT-suffixed sibling, which is what ``CreateProcess`` actually
    execs).

    Negative-spec — this MUST NOT become
    ``from coordinator_core.win_portability import is_executable``, at module
    scope or lazily. This file is installed standalone into the operator's
    ``<settings-home>/bin/`` beside every generated forwarder (the set is
    derived by ``substrate._derive_agent_helper_target_map`` from a
    ``coordinator/bin/`` listing, not a frozen count) and runs on a
    bare ``#!/usr/bin/env python3`` with only the stdlib importable: its
    entire job is to FIND claude-klabauter, so it cannot presuppose claude-klabauter is already
    importable. The package import landed here in ``a141074a``'s 40-site
    ``os.access(X_OK)`` -> ``is_executable()`` sweep, which had no way to see
    that this one call site executes outside the package, and it took down
    every bareword CLI on PATH at once — ``ModuleNotFoundError:
    coordinator_core`` before the ladder's first line, including
    ``~/.local/bin/claude-doe``, i.e. launching Claude Code itself.

    A lazy import off the resolved root is not the fix either: it would make
    the sentinel probe demand a FULL, importable checkout, conflating
    "coordinator/bin/ holds a launchable sentinel" (what this ladder rung
    actually asks) with "this tree is an installed Python package". The
    duplication is the deliberate cost of this file's standalone contract —
    keep the two in sync by hand if the Windows semantics change.

    ``os.access(path, os.X_OK)`` is banned repo-wide (see
    ``win_portability``'s own docstring: it degrades to existence-only on
    NTFS) — mode-bit inspection, not that call, is the POSIX branch here."""
    p = Path(path)
    if os.name != "nt":
        try:
            mode = os.stat(p).st_mode
        except OSError:
            return False
        return bool(mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))

    # PATHEXT's own separator is always ';' on Windows — never os.pathsep,
    # which would be ':' under a POSIX host modelling Windows semantics.
    pathext = os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD")
    exts = [e.upper() for e in pathext.split(";") if e.strip()]
    if p.suffix:
        return p.is_file() and p.suffix.upper() in exts
    return any((p.parent / (p.name + ext.lower())).is_file() for ext in exts)


def _validate_bin_dir(claude_klabauter_root: str) -> str:
    """Validate ``<claude_klabauter_root>/coordinator/bin`` and return it.

    Extracted from ``resolve_claude_klabauter_bin_dir()`` (C4b) so ``exec_cli`` can run
    the identical directory/sentinel validation against a root it resolved
    via the class-aware ``resolve_claude_klabauter_root_with_class()`` ladder, without
    duplicating the two fail-loud messages below. ``resolve_claude_klabauter_bin_dir()``
    itself is untouched byte-for-byte in behaviour — see its own docstring.

    Probes a specific, load-bearing executable (``archive-stamp-cli``)
    rather than trusting dir-existence alone — a bare directory can exist
    without containing the CLIs a caller needs.

    Raises ClaudeKlabauterResolutionError with a message distinguishing "wrong or
    incomplete checkout" (coordinator/bin/ itself missing) from "stale or
    partial migration" (coordinator/bin/ exists but its sentinel doesn't) —
    these are different failure modes and must not be collapsed into one
    generic message.
    """
    bin_dir = claude_klabauter_root + "/coordinator/bin"
    if not os.path.isdir(bin_dir):
        raise ClaudeKlabauterResolutionError(
            f"ERROR: '{bin_dir}' does not exist — the claude-klabauter clone at '"
            f"{claude_klabauter_root}' has no coordinator/bin/ directory; wrong or incomplete "
            "checkout. Confirm repos.claude_klabauter points at the claude-klabauter repo "
            "root (not a subdirectory)\n"
        )

    # Both shapes are accepted, and the `.py` one is accepted on EXISTENCE
    # rather than the exec bit: the POSIX-exec drain (docs/plans/2026-08-13-
    # grind-the-posix-exec-baseline-to-zero.md, chunk C6) renames the
    # extensionless entrypoints to `.py` and clears their exec bit, so
    # demanding an executable extensionless sentinel means demanding the
    # pre-drain shape forever. Checking both also keeps this resolver working
    # while the rename is mid-flight on a shared tree, which is when a false
    # negative here does the most damage.
    # Accepting both shapes is necessary but NOT sufficient to survive the
    # rename, because C6 lands it as delete-then-write rather than an atomic
    # move: for the instant between the two, NEITHER shape is on disk and a
    # single probe reads the same as a genuinely absent sentinel. Measured
    # live 2026-08-13 from a memo pickup taken mid-wave — the resolver raised,
    # and since archive-stamp-cli is the sole authorized frontmatter writer,
    # every concurrent session's handoff and memo stamping fails closed for
    # the width of that window.
    #
    # Re-probe before believing the miss. A rename window is sub-millisecond;
    # a genuinely absent sentinel stays absent, so the retry costs a bounded
    # ~300ms on a path that was about to hard-fail anyway and nothing at all
    # on the happy path (the first probe short-circuits). Deliberately NOT
    # solved by widening the sentinel to several files: that trades a precise
    # "this exact writer is missing" diagnostic for a fuzzy one, and every
    # candidate file is renamed by the same wave.
    sentinel_bare = bin_dir + "/archive-stamp-cli"
    sentinel_py = sentinel_bare + ".py"

    def _sentinel_present() -> bool:
        return _is_executable(sentinel_bare) or os.path.isfile(sentinel_py)

    if not _sentinel_present():
        for _backoff_sec in (0.05, 0.1, 0.15):
            time.sleep(_backoff_sec)
            if _sentinel_present():
                break
        else:
            raise ClaudeKlabauterResolutionError(
                f"ERROR: neither '{sentinel_bare}' nor '{sentinel_py}' is present — "
                f"coordinator/bin exists at '{bin_dir}' but its sentinel CLI "
                "(archive-stamp-cli, the sole authorized handoff/memo frontmatter "
                "writer) is absent in either shape, and stayed absent across a "
                "re-probe; this is a stale or partial claude-klabauter migration, "
                "not a wrong-path problem. Re-run the "
                "installer against this clone, or check out the missing file with "
                "`git checkout -- coordinator/bin/` — do NOT re-clone: this tree is "
                "shared by concurrent sessions and a re-clone discards their "
                "uncommitted work\n"
            )

    return bin_dir


def resolve_claude_klabauter_bin_dir() -> str:
    """Resolve, validate, and return ``<claude-klabauter-root>/coordinator/bin``.

    The coordinator-owned CLIs live at ``<claude-klabauter-root>/coordinator/bin``, NOT
    ``<claude-klabauter-root>/bin`` (that top-level bin/ is a different, unrelated
    claude-klabauter directory with its own entries).

    Byte-identical to its pre-C4b behaviour: resolves the root via the
    single-tier ``_resolve_claude_klabauter_root`` ladder only (never the published
    engine) — this is the function ``test_resolve_claude_klabauter.py`` exercises
    directly, and callers other than ``exec_cli`` (e.g. install-time
    tooling) still want the live-tree-only contract. ``exec_cli`` itself
    (C4b) resolves via ``resolve_claude_klabauter_root_with_class()`` instead and
    calls ``_validate_bin_dir`` directly — see its own docstring.
    """
    ml_dir = _ml_dir()
    claude_klabauter_root = _resolve_claude_klabauter_root(ml_dir)
    return _validate_bin_dir(claude_klabauter_root)


def _run_target_in_process(target_path: str, argv: List[str], claude_klabauter_root: str) -> int:
    """Run *target_path* (a ``coordinator/bin/`` Python CLI) in-process,
    return its intended exit code.

    Every ``coordinator/bin/`` CLI is a plain ``.py``-shaped module (some
    extensionless, some ``.py``-suffixed — see ``substrate.py``'s
    ``_write_agent_forwarder`` docstring) whose body is either a bare script
    or the ``if __name__ == "__main__": sys.exit(main(sys.argv[1:]))``
    pattern (e.g. ``archive-stamp-cli``). ``runpy.run_path(...,
    run_name="__main__")`` is the portable stdlib primitive that executes a
    plain file path as if it were run as ``__main__`` — no shebang
    interpretation needed (unlike ``os.execv`` on Windows, which goes
    through ``CreateProcess`` and cannot honor ``#!`` lines), no second
    interpreter cold-start, and no module-registry entry required for a
    target this function has no static import path for (targets are
    resolved dynamically by filename, not by package name).

    ``sys.argv`` is swapped for the duration of the call (restored in
    ``finally``) because target scripts read ``sys.argv`` directly (as
    ``archive-stamp-cli`` does) rather than accepting an injected argv
    parameter — this is the in-process equivalent of what ``execv``/
    ``subprocess`` would otherwise set up via the child's own process argv.

    TWO entries are inserted at the FRONT of ``sys.path`` for the duration of
    the call — *claude_klabauter_root* and the target script's OWN directory — restored
    (never merely popped — a target is free to mutate ``sys.path`` itself) in
    the same ``finally`` as ``sys.argv``.

    Why both: ``runpy.run_path`` on a plain FILE path contributes NOTHING to
    ``sys.path``. It prepends only for a directory or zipfile argument; a
    ``.py`` file is executed in a throwaway namespace with ``sys.path``
    untouched. An earlier revision of this docstring asserted the opposite —
    that ``run_path`` supplies ``<claude_klabauter_root>/coordinator/bin`` — and that
    false premise is why the script-dir insert was missing here. Do not
    re-derive it: verified against CPython, a file-path ``run_path`` leaves
    ``sys.path`` byte-identical.

    So a normal ``python target_path`` invocation (the POSIX leg of
    ``exec_cli``) gets the script's directory for free from the interpreter's
    own startup and needs neither insert; this leg gets neither and needs
    both. Without *claude_klabauter_root*, a target doing ``import coordinator_core`` at
    module scope dies with ``ModuleNotFoundError`` before running a line of
    its own logic. Without the script directory, so does every target built on
    ``entry_point_shim`` — ``from lib.entry_point_shim import run_target``
    resolves ``lib`` relative to ``coordinator/bin``, which nothing else puts
    on the path (observed live: ``sizing-assemble`` on the Windows in-process
    leg, ``No module named 'lib.entry_point_shim'``).

    The root the caller already resolved (``resolve_claude_klabauter_root_with_class``
    et al.) is reused here, never re-resolved. Idempotent per entry: an entry
    already present is skipped, so a target that itself re-enters this
    function (or is invoked from a process that already has either directory
    on ``sys.path``) never accumulates duplicates.

    A target that calls ``sys.exit(n)`` raises ``SystemExit(n)`` through
    ``run_path`` exactly as it would run standalone; that is caught here and
    its ``.code`` propagated (``None`` and non-int codes normalize to 0/1
    per Python's own ``sys.exit`` contract, mirrored here rather than
    reinvented). A target that falls off the end without calling
    ``sys.exit`` completes with implicit success (0), matching normal
    process-exit semantics.

    Negative-spec: the POSIX leg of ``exec_cli`` (interpreter-targeted
    ``os.execv``) needs none of this — a fresh interpreter process resolves
    its own ``sys.path`` from ``target_path``'s directory the normal way,
    and this function is never called on that leg. Do not add a ``sys.path``
    insert there; it would be a no-op on a process image this function never
    touches.
    """
    original_argv = sys.argv
    original_path = list(sys.path)
    try:
        sys.argv = [target_path] + argv
        target_dir = os.path.dirname(os.path.abspath(target_path))
        for entry in (target_dir, claude_klabauter_root):
            if entry and entry not in sys.path:
                sys.path.insert(0, entry)
        runpy.run_path(target_path, run_name="__main__")
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        sys.stderr.write(str(code) + "\n")
        return 1
    finally:
        sys.argv = original_argv
        sys.path[:] = original_path
    return 0


def _resolve_publisher_root() -> str:
    """The live working checkout, for a ``PUBLISHER_ONLY_TARGETS`` member.

    Single-tier on purpose — ``_resolve_claude_klabauter_root``'s registry-then-sentinel
    ladder only, never ``resolve_claude_klabauter_root_with_class``'s published-engine
    rung. See ``PUBLISHER_ONLY_TARGETS`` for why the published engine is not a
    legitimate answer for these targets at all: they are denied by the publish
    allowlist, so the mirror carries neither the target file nor (for the
    percolate family) the engine modules it dispatches against.

    Re-raises ``_resolve_claude_klabauter_root``'s miss with publisher-specific
    remediation. The generic message names ``repos.claude_klabauter`` as a
    third way to satisfy the resolution — true for every other target, and
    exactly the wrong advice here.

    Says "does not ship in the mirror", never "runs the percolate engine":
    only half the set does, and a reader told the wrong reason checks the
    wrong thing. ``engine-gap-lint`` and ``check-persona-slug-leak`` import
    no percolate module at all; they are here because publish DENIES them."""
    ml_dir = _ml_dir()
    try:
        return _resolve_claude_klabauter_root(ml_dir)
    except ClaudeKlabauterResolutionError as exc:
        raise ClaudeKlabauterResolutionError(
            str(exc).rstrip("\n")
            + "\n  NOTE: this is a publisher-only CLI — the publish allowlist denies "
            "it, so it exists only in the live claude-klabauter checkout. The published "
            "engine mirror (repos.claude_klabauter) is the publish DESTINATION and "
            "cannot satisfy it; set repos.claude_klabauter.\n"
        ) from exc


#: Basename of the src->dst map publish emits into `coordinator/bin/` of the
#: published tree (`percolate.rewrite_basename.PUBLISHED_NAME_MAP_BASENAME`).
#: Hardcoded rather than imported for the same reason the whole module is
#: stdlib-only: this file is installed standalone into a bare `bin/` with no
#: package context, and an engine import on the exec path costs ~75ms before
#: any work happens. Deliberately NOT dot-prefixed -- `round.py`'s
#: `_smack_copy_in` skips every top-level dotfile when copying staging into
#: the destination, so a dotted name never reaches the mirror at all.
PUBLISHED_NAME_MAP_BASENAME = "published-name-map.json"


def resolve_target_path(bin_dir: str, target: str) -> str:
    """The path `exec_cli` should run for *target* under an already-resolved
    *bin_dir*, consulting publish's rename map when the asked-for name misses.

    WHY THIS EXISTS. Publish applies an identity transform to filenames:
    `check-claude-klabauter-doctor-sentinel.sh` ships as
    `check-claude-klabauter-doctor-sentinel.py`. The installed forwarder body
    is `exec_cli("check-claude-klabauter-doctor-sentinel.sh")` -- verbatim, the claude-klabauter
    spelling -- so on a box diverted to the published engine the target is
    absent under the only name asked for, and the run dies at C13's fail-loud
    127 naming a root that does, in fact, contain the program. The transform
    renamed the file; nothing renamed what the forwarder asks for.

    The mapping cannot be inferred. Three of the four live renames look like a
    `claude-klabauter` -> `claude-klabauter` token rewrite, but
    `probe-cwd-project-rag-relevance.py` ships as
    `probe-cwd-example-retrieval-repo-relevance.py`, which is derivable from
    nothing. One counter-example makes inference wrong for the whole set
    rather than incomplete on one member, so the map is SHIPPED by the process
    that performs the rename and merely read here.

    Negative-spec, in order of how easily each would be got wrong:

    - Callers must invoke this ONLY for `RESOLUTION_RESOLVED_ENGINE`. A
      live-tree miss is a genuinely broken checkout and must keep failing
      loudly per C13; a rename map has no business rescuing it, and there is
      no map in a live tree to read anyway.
    - This does NOT widen `PUBLISHER_ONLY_TARGETS` and must never be made to.
      The publisher-only class and the renamed class share a symptom and take
      INVERSE repairs: publisher-only targets exist nowhere but the live tree,
      so pinning them there is right; renamed targets ship and work and are
      merely misaddressed, so pinning them live-tree-only would break them on
      every box without a checkout -- the population that currently has them
      working.
    - Returns the ORIGINAL path when anything is missing or unreadable: no
      map, unparseable map, name absent from it, or a mapped name that is not
      on disk. The caller then fails exactly as it does today. An absent map
      means "no mapping known", never an error -- most mirrors carry no map
      until a round has run since it was introduced.
    - Reads the map only on the MISS path. A target that resolves under its
      own name never opens this file, so the ordinary case pays nothing.
    """
    map_path = bin_dir + "/" + PUBLISHED_NAME_MAP_BASENAME
    original = bin_dir + "/" + target
    try:
        import json
        with open(map_path, "r", encoding="utf-8") as fh:
            mapping = json.load(fh)
        if not isinstance(mapping, dict):
            return original
        published = mapping.get(target)
        if not published and not target.endswith(".py"):
            published = mapping.get(target + ".py")
        if not isinstance(published, str) or not published:
            return original
        candidate = bin_dir + "/" + published
        return candidate if os.path.isfile(candidate) else original
    except Exception:
        return original


def exec_cli(target: str, argv: Optional[List[str]] = None) -> None:
    """Resolve ``<claude-klabauter-root>/coordinator/bin/<target>`` and run it,
    forwarding *argv* (defaults to ``sys.argv[1:]``).

    POSIX: ``os.execv``s into ``sys.executable`` with *target_path* as its
    first argument (``[sys.executable, target_path, *argv]`` — never returns
    on success, replaces the current process image). Interpreter-targeted,
    not shebang-dependent: this runs the target as ``python target_path``
    rather than executing *target_path* itself, so it no longer relies on
    every ``coordinator/bin/`` CLI carrying a ``#!/usr/bin/env python3``
    shebang or its executable bit being set.

    Windows: ``os.execv`` cannot honor a POSIX shebang — ``CreateProcess``
    (which ``os.execv`` goes through on Windows) does not interpret ``#!``
    lines, so a bare extensionless *target_path* fails outright. Windows
    also can't truly replace the current process image the way POSIX
    ``exec`` does. The prior body worked around both problems by resolving
    a second Python interpreter and ``subprocess.run``-ing the target — a
    full interpreter cold-start on every single forwarder call. Every
    ``coordinator/bin/`` target is a Python CLI (naked ``.py``-shaped file,
    with or without a ``.py`` suffix — see ``substrate.py``'s
    ``_write_agent_forwarder`` docstring), so there is no "genuinely
    unimportable target class" requiring a spawn fallback: this process is
    already running Python, so the fix is to run the target **in-process**
    via ``_run_target_in_process`` (``runpy.run_path``) instead of shelling
    out to a second one. This removes the interpreter-resolution failure
    mode entirely — there is no longer a "no Python interpreter found on
    PATH" case, because no second interpreter is ever located or started.

    Negative-spec (POSIX mechanism) — interpreter-targeted ``execv`` was
    chosen over in-process ``runpy.run_path`` (the same primitive the
    Windows leg uses) for the POSIX leg too. Measured on one warm macOS
    box, 12 runs each, both orders, pessimistic reading: status quo
    ``os.execv(target_path, ...)`` 32.6ms; interpreter-targeted execv
    31.3ms; in-process 20.2ms. In-process was rejected despite being
    fastest because it abandons process identity and couples forwarder and
    target process state permanently — specifically, ``runpy.run_path``
    from a forwarder leaves the FORWARDER's directory at ``sys.path[0]``
    rather than the target's, breaking bare sibling imports that
    direct-script invocation handles. Interpreter-targeted execv runs the
    target as ``python target_path``, which CPython treats identically to
    today's shebang-invoked script for ``sys.path[0]``, ``sys.argv[0]``,
    ``__file__``, signal disposition, and traceback shape — this is why the
    POSIX leg does NOT collapse onto ``_run_target_in_process``.

    On a resolution failure, writes the distinct fail-loud message to
    stderr and exits 1 (matching the prior inline body's contract). On a
    missing (or unreadable — see the `os.access(os.R_OK)` pre-check below)
    *target* itself (partial install, mid-refresh tree, or a name-map entry
    pointing at a stale target), exits 127 (POSIX command-not-found
    convention) with a one-line remediation. Non-executable is no longer a
    127 case: the interpreter-targeted POSIX mechanism below runs the
    target as `python target_path`, not target_path directly, so the exec
    bit is never required.

    C4b (RETIRED by C13) — per-target existence gate on the published-engine
    rung. Root resolution goes through `resolve_claude_klabauter_root_with_class()`
    (C3's two-tier ladder) rather than the single-tier
    `resolve_claude_klabauter_bin_dir()`, so this function can see WHICH class
    answered. A directory-level sentinel probe (`resolve_claude_klabauter_bin_dir`'s
    `archive-stamp-cli` check) passes against the published mirror even
    though the claude-klabauter-vs-published forwarder sets were NOT nested when C4b
    landed (C4a's oracle: 20 names live-tree-only, 5 published-only on that
    tree) — the gap was per-target, so C4b's gate fell back to the live
    working tree (via the single-tier `resolve_claude_klabauter_bin_dir`) and exec'd
    the target from there when it existed, only failing loud (127, naming
    both roots tried) if that ALSO missed.

    C13 (docs/plans/2026-08-19-an-engine-root-is-a-stamped-build.md § C13):
    that fallback is REMOVED. C13 first closed the measured per-name gap
    (published-engine `coordinator/bin/` allowlist vs. the installed-name ->
    on-disk-target map `_derive_agent_helper_target_map` resolves against —
    see `setup/publish-targets.portable`'s `claude-klabauter-coordinator-bin`
    row) — once the published set carries every name the live tree does, a
    missing target under a resolved published-engine root is no longer "a
    known gap the live tree covers", it is a genuinely broken install. A
    missing *target* under EITHER resolution class now fails loud (127)
    naming only the ONE root actually tried — there is no second root to
    silently reach into any more.

    PUBLISHER-ONLY CARVE-OUT. A *target* in ``PUBLISHER_ONLY_TARGETS`` skips
    the class-aware ladder entirely and resolves live-tree-only, via
    ``_resolve_publisher_root``. This is not an exemption from C13's
    fail-loud rule — it is upstream of it: for these targets the published
    engine is the publish DESTINATION, so it is never a legitimate root, and
    diverting there yields a target that exists and then dies on an import
    that cannot succeed. Everything else is unchanged, byte-for-byte, on
    both legs. Negative-spec: do NOT "generalize" this into a fallback that
    tries the published engine when the live tree misses — a publish round
    run from the published copy is not a degraded round, it is not a round.
    """
    if argv is None:
        argv = sys.argv[1:]

    try:
        if _is_publisher_only_target(target):
            claude_klabauter_root = _resolve_publisher_root()
            resolution_class = RESOLUTION_LIVE_WORKING_TREE
        else:
            claude_klabauter_root, resolution_class = resolve_claude_klabauter_root_with_class()
        bin_dir = _validate_bin_dir(claude_klabauter_root)
    except ClaudeKlabauterResolutionError as exc:
        sys.stderr.write(str(exc))
        sys.exit(1)

    target_path = bin_dir + "/" + target
    # `.py`-suffix probe for a bare target name. The 745 installed settings-home
    # forwarders each call `exec_cli("<bare-name>")`, and the POSIX-exec drain
    # (docs/plans/2026-08-13-grind-the-posix-exec-baseline-to-zero.md, chunk C6)
    # renames the extensionless entrypoints they name to `<bare-name>.py`. The
    # install chain maps the suffix back off at INSTALL time, so a re-installed
    # tree is fine either way — but a forwarder installed before the rename
    # keeps naming the bare form, and every session on a not-yet-reinstalled
    # tree would exec-fail until it reinstalled. Probing here makes the
    # transition survivable without a fleet-wide reinstall, which is the same
    # bargain DoE took for `install-sentinel-write` in their `d34a977a8`.
    if not os.path.isfile(target_path) and not target.endswith(".py"):
        suffixed = target_path + ".py"
        if os.path.isfile(suffixed):
            target_path = suffixed
    if not os.path.isfile(target_path) and resolution_class == RESOLUTION_RESOLVED_ENGINE:
        target_path = resolve_target_path(bin_dir, target)
    target_claude_klabauter_root = claude_klabauter_root

    # Hoisted above the os.name branch (Review: code-reviewer F4 — was
    # byte-for-byte duplicated on both legs). Readability, not executability
    # (Review: code-reviewer F1) — the interpreter-targeted POSIX mechanism
    # below execs `sys.executable`, which always exists and is executable,
    # so `os.execv` itself no longer raises for an unreadable *target*; the
    # failure would otherwise surface only after process replacement, inside
    # the second interpreter's own `open()` of target_path, losing both the
    # 127 contract and the remediation message for exactly the
    # partial-install/mid-refresh scenario this check exists to catch. A
    # target can still change state between this check and the exec below
    # (TOCTOU) — that narrower window is accepted, not closed, and the
    # `except OSError` handler on the POSIX leg remains its backstop.
    if not os.path.isfile(target_path) or not os.access(target_path, os.R_OK):
        # C13: no live-tree fallback — the resolved root (whichever class
        # answered) is the only root tried; a missing target here fails
        # loud rather than silently reaching a second tree. See exec_cli's
        # own docstring, "C4b (RETIRED by C13)".
        sys.stderr.write(
            f"ERROR: coordinator helper '{target_path}' is missing under the "
            f"resolved {resolution_class} root ('{claude_klabauter_root}') — run "
            "python3 <engine-clone>/scripts/setup.py to repair the plugin tree\n"
        )
        sys.exit(127)

    if os.name == "nt":
        sys.exit(_run_target_in_process(target_path, argv, target_claude_klabauter_root))

    try:
        os.execv(sys.executable, [sys.executable, target_path, *argv])
    except OSError as exc:
        sys.stderr.write(
            f"ERROR: coordinator helper '{target_path}' is missing or not "
            f"executable ({exc.strerror}) — run python3 "
            "<engine-clone>/scripts/setup.py to repair the plugin tree\n"
        )
        sys.exit(127)
