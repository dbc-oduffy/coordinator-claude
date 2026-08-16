"""
cross-repo-memo — dispatch a cross-repo memo to a receiver-EM's working tree.

Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, and correct
for this shape. On Windows, this file's co-located `.cmd` twin wins via
`PATHEXT` when invoked as a bareword, so the shebang is never read there; on
macOS/Linux `python3` is the right interpreter. Caution: callers must invoke
via the extensionless name or a resolved-interpreter prefix, never a bareword
`.py` through git-bash — git-bash DOES honor the shebang and would exec-127
with no `python3` present. See the carve-out in DoE-claude's
coordinator/docs/wiki/bash-on-windows-gotchas.md § Carve-out (cross-repo —
this wiki lives in the DoE-claude repo, not here). There is no `.test.py`
sibling and no separate polyglot trampoline line — this file is the
pure-`.py`-with-`.cmd` shape end to end.

Invocation: in an INTERACTIVE shell on a machine where C1 install-time PATH
provisioning has run, this CLI is bareword-reachable on PATH — no interpreter
prefix, no full $HOME/... path needed:
  cross-repo-memo --to <receiver-em> --topic <slug> --title "<one-line>" --body-file <path>
That guarantee is scoped to post-install interactive shells: rc-file
provisioning (.zshrc / .bashrc) does not cover CI, non-interactive `sh -c`
invocations, or any shell that hasn't sourced the provisioned rc file. AUTHORED
surfaces (skills, agent prompts, .md docs) are read in contexts where none of
that is guaranteed and MUST keep using the explicit settings-home path form
(see below) — this header change does not license dropping it there.
The polyglot trampoline above means `bash cross-repo-memo ...` and
`python cross-repo-memo ...` now work too — they re-exec under python rather than
erroring, so a habitual `bash` prefix is forgiven, not punished. `--help` lists
every flag (and `bash cross-repo-memo --help` now prints it instead of a
traceback). Do NOT route it through `pythonw`/`py` to dodge the Windows console
flash: pythonw discards stdout, and this CLI prints the receiver path on stdout
that you must hand the PM. The transient flash from this manually-invoked CLI is
acceptable (not a hot-path spawn); the recurring blue powershell.exe flash was the
PowerShell tool backing process, fixed separately by CLAUDE_CODE_USE_POWERSHELL_TOOL=0
— not per-call interpreter gymnastics.

Spec backlink: docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md § Chunk 3
Prior spec: docs/plans/2026-05-21-cross-repo-memo-discoverability.md § Chunk 2

Purpose: Write ONE dirty delivery memo into the RECEIVER's repo at
  <receiver-repo>/cross-repo/inbox/YYYY-MM-DD-<topic>.md
left uncommitted (dirty) so it surfaces in the receiver's `git status`.

Single-delivery-copy model (PM ruling 2026-05-23):
- Sender writes ONE memo into receiver's cross-repo/ directory — NO sender copy,
  NO archive/cross-repo/ write at send time.
- The CLI prints the receiver path and a "hand the PM this path for relay" line.
- The receiver reads the dirty file, acts on it, flips status: open → actioned
  in place via a normal Edit + commit. Terminal state — no move, no closure
  subcommand, no second side.
- The act of sending is noted in the sender's normal workstream-complete notes.

Negative-spec: There is NO closure subcommand. The receiver edits the memo in
place (open → actioned). Do NOT add a --close/--action subcommand — receiver
uses a plain Edit on the memo file and commits it in their repo.

Reader-only relationship to machine-local registry
---------------------------------------------------
This script reads machine-local via `_machine_local.py get repos.<key>` to
resolve receiver repo paths. It does NOT write to machine-local — ever.

Negative-spec (machine-local-registry.md anti-pattern): if you find yourself
wanting to write to machine-local from a script, stop. Per-machine path
values belong in the registry; they are NOT sidecar'd in local config files
next to the script. The registry is the audited source; the script is a reader
only. See: docs/wiki/machine-local-registry.md § 5a–5b (Reader only — never
writes to machine-local. If you find yourself wanting to write to machine-local
from a script, stop.)

Receiver-EM identity → repo resolution (convention over table)
--------------------------------------------------------------
The receiver set IS the machine-local repo list — there is no hand-maintained
identity→repo table to keep in sync (PM ruling 2026-05-23). A receiver-EM
identity resolves to a registry key by convention:

    <receiver>-em  →  repos.<receiver with dashes→underscores>

e.g. <your-repo>-em → repos.<your_repo>,
     <another-repo>-em → repos.<another_repo>.

Consequence: any repo registered in the machine-local registry under
repos.<name> is automatically a valid receiver, with NO code change here.
Register the repo (machine-local set repos.<name> <path>) and <name>-em (dashes
for underscores) delivers to it. Anyone installing the coordinator gets this for
free — the receiver list is THEIR machine-local repo list, not ours.

RECEIVER_EM_ALIASES holds ONLY the handful of identities whose stable doctrine
name diverges from the repo's registry shortname (e.g. <alias-em> ↔
repos.<canonical_name>). It does NOT grow with the number of repos —
convention covers those — so it stays tiny. Identity space is still global
doctrine; path space is still per-machine — the registry resolves the path.
"""
from __future__ import annotations

# NOTE (slice-A F7, originally declined): `from __future__ import annotations` has now
# been added above (between the trampoline and this docstring block). The earlier
# decline was incorrect — the trampoline line `''''exec...#'''` IS the module docstring
# (Python's first string literal), so `from __future__` placed immediately after it is
# at the beginning of the module as required. This docstring block is a second string
# expression, not the module docstring. The fix makes `str | None` annotations safe on
# Python 3.7+ and closes the cryptic-crash-on-import risk on macOS stock Python 3.9.

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time as _time
from pathlib import Path

GENERATES = []  # writes ONE dirty memo into the RECEIVER's (sibling) repo tree at <receiver-repo>/cross-repo/inbox/ — never into claude-klabauter's own tree

# ---------------------------------------------------------------------------
# Shared memo composer — extracted to bin/lib/memo_compose.py (example-initiative tc-0 C4)
#
# Spec backlink: docs/plans/2026-06-25-example-initiative-tc-0-canonical-baton-shape.md § C4
#
# _compose_frontmatter and _compose_memo are thin wrappers below that delegate
# to the shared lib, passing from_id=_sender_em_id() at call time. Their public
# signatures are unchanged so existing call sites and tests are unaffected.
# ---------------------------------------------------------------------------
_MC_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _MC_LIB_DIR not in sys.path:
    sys.path.insert(0, _MC_LIB_DIR)
from memo_compose import (  # noqa: E402 (late import after sys.path manipulation)
    _yaml_quote,
    _today,
    _now_iso,
    _SUMMARY_MAX_CHARS,
    _derive_summary,
    compose_frontmatter as _mc_compose_frontmatter,
    compose_memo as _mc_compose_memo,
)
from coordinator_registry import (  # noqa: E402 (late import after sys.path manipulation)
    CENTRAL_RECEIVER_IDS as _CENTRAL_RECEIVER_IDS,
    REDIRECT_ALIASES as _DOE_CANONICAL_REDIRECT_ALIASES,
    RECEIVER_EM_ALIASES,
    _central_canonical_id,
    _same_path,
    em_id_for_root,
    repo_key_to_em_id,
)
import cc_invoke  # noqa: E402 (late import after sys.path manipulation)
from machine_local_impl_resolve import (  # noqa: E402 (late import after sys.path manipulation)
    machine_local_impl_path as _mlir_machine_local_impl_path,
)
from raw_cmdline_recovery import (  # noqa: E402
    RAW_CMDLINE_FILE_ENV,
    UnsoundRawCmdlineTransport,
    recover_windows_argv,
    spawn_shape_prefix,
)

# Review: staff-eng (Finding 1) — cross-repo-memo.py is a member of both
# gen-launcher-shim.py's _RAW_CMDLINE_ENTRYPOINTS and substrate.py's
# _RAW_CMDLINE_TARGETS (added alongside scoped-git-commit per
# cross-repo/inbox/2026-08-07-doe-claude-em-cmd-forwarder-drops-everything-
# after-a-newline.md: this CLI takes multi-line memo bodies as a matter of
# course, so caret fidelity plausibly matters here too), so its .cmd
# launcher already captures %CMDCMDLINE% -- but until this fix nothing ever
# called recover_windows_argv, leaking a capture directory under %TEMP% on
# every Windows invocation while never recovering the caret. Wired in here
# to match the intent recorded in both generators' docstrings rather than
# dropped from the sets, which would silently reverse that intent.
_LAUNCHER_CMD_NAME = "cross-repo-memo.cmd"

# C2b (docs/plans/2026-08-15-the-caret-fix-went-to-the-caller-that-never-
# broke.md): detect-and-record, NOT refuse, on `UnsoundRawCmdlineTransport`.
# The named limitation is soundness is not decidable from the capture text
# alone -- refusal here would fleet-break this hot path for ~40 concurrent
# sessions on a heuristic with known false-refusal shapes. This ledger exists
# so a follow-up chunk can flip to refusal once it shows zero unsound-or-
# unknown classifications among invocations that themselves succeeded. Same
# ledger path and row shape as `scoped-git-commit`'s own copy of this pair of
# helpers -- duplicated rather than imported because both files' writes are
# scoped independently and `raw_cmdline_recovery.py` (the one module already
# shared between them) is out of scope for this chunk.
_RAW_CMDLINE_LEDGER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "state",
    "raw-cmdline-transport-ledger.jsonl",
)


def _peek_raw_cmdline_capture() -> "str | None":
    """Best-effort, non-destructive peek at the raw `%CMDCMDLINE%` capture
    file BEFORE `recover_windows_argv` reads-and-deletes it, so a subsequent
    `UnsoundRawCmdlineTransport` can still be logged with the text that
    justified it -- the exception itself carries only the classification
    (SOUND/UNSOUND/UNKNOWN), never the raw text (see
    `raw_cmdline_recovery.UnsoundRawCmdlineTransport`'s own docstring). Never
    raises; any failure here must not affect the real recovery path below.
    """
    raw_file = os.environ.get(RAW_CMDLINE_FILE_ENV)
    if not raw_file:
        return None
    try:
        return Path(raw_file).read_text(encoding="utf-8", errors="replace").rstrip("\r\n")
    except OSError:
        return None


def _record_unsound_raw_cmdline_transport(
    entrypoint: str, exc: Exception, raw_capture: "str | None"
) -> None:
    """C2b's detect-and-record consequence for `UnsoundRawCmdlineTransport`:
    warns on stderr and appends one JSONL row to the shared observation
    ledger. Never raises, never changes the caller's exit code -- the caller
    falls back to proceeding on the un-recovered (possibly caret-mangled)
    argv, same as `recover_windows_argv`'s own other fail-safe branches.

    Row: classification (parsed off `str(exc)`'s leading token -- the only
    structured signal the exception carries), the entrypoint name, a UTC ISO
    timestamp, and `spawn_shape` -- the leading transport tokens (comspec
    path, `/d`/`/s`/etc., the `/c`/`/k` switch itself) `spawn_shape_prefix`
    extracts from the raw capture, NEVER the remainder that follows the
    switch. The remainder is the caller's actual command and argument
    payload -- a commit message, memo body, or `--note` value can carry
    secrets or sensitive text, and this ledger is shared append-space across
    ~40 concurrent sessions (docs/wiki/machine-load-norm.md), readable by
    every one of them. The ledger's own purpose only needs the transport
    SHAPE: refusal on these two entrypoints flips on once the ledger shows a
    caller-shape distribution with zero unsound-or-unknown classifications
    among invocations that succeeded (C2b's flip-condition), which is a
    question about spawn shape, never about payload content.

    Concurrency: `state/` is shared append-space across ~40 concurrent
    sessions (docs/wiki/machine-load-norm.md). A single `os.open` with
    `O_APPEND | O_CREAT` plus one `os.write` call keeps each row's bytes from
    tearing into a concurrent writer's row; cross-process row ORDER is not
    guaranteed and does not need to be.

    Message register (docs/wiki/guard-messaging.md § Register): one fact,
    one terse pointer at the ledger, no self-legitimacy, no apology -- and
    critically, no language implying the operation was stopped, because it
    was not.
    """
    classification = (str(exc).split(":", 1)[0].strip()) or "UNKNOWN"
    # Review: coordinator:code-reviewer (9245562b, P2) -- persist only the
    # spawn-shape prefix, never the raw payload; see docstring above.
    spawn_shape = spawn_shape_prefix(raw_capture or "")
    print(
        "%s: warning: raw cmdline transport for this invocation could not be "
        "vouched for (%s) -- proceeding on possibly-mangled argv. Recorded to "
        "%s." % (entrypoint, classification, _RAW_CMDLINE_LEDGER_PATH),
        file=sys.stderr,
    )
    row = {
        "classification": classification,
        "spawn_shape": spawn_shape,
        "entrypoint": entrypoint,
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    }
    try:
        os.makedirs(os.path.dirname(_RAW_CMDLINE_LEDGER_PATH), exist_ok=True)
        line = (json.dumps(row, sort_keys=True) + "\n").encode("utf-8")
        fd = os.open(
            _RAW_CMDLINE_LEDGER_PATH, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644
        )
        try:
            os.write(fd, line)
        finally:
            os.close(fd)
    except OSError:
        pass  # best-effort -- a ledger write failure must never block the memo path


# --topic must be filesystem-safe to prevent path traversal out of cross-repo/.
# Allows: lowercase alphanum + dashes, must start with alphanum. No '..', '/', '\'.
_TOPIC_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*$")

# ---------------------------------------------------------------------------
# Receiver-EM identity → machine-local registry key.
#
# Convention-first: <receiver>-em → repos.<receiver, dashes→underscores>. The
# receiver set is therefore the machine-local repo list (repos.*) — register a
# repo and its <name>-em identity delivers to it with no edit here.
#
# RECEIVER_EM_ALIASES is ONLY for identities whose doctrine name diverges from
# the repo's registry shortname. It does not grow with repo count — keep tiny.
#
# Single source of truth: schemas/coordinator-registry.manifest.json § identity.repoAliases
# (via bin/lib/coordinator_registry.py). Drift is now structurally prevented —
# the manifest is the authoritative list; this import reads it at load time.
# ---------------------------------------------------------------------------
# RECEIVER_EM_ALIASES imported above from coordinator_registry.

# ---------------------------------------------------------------------------
# Central-receiver identity set (B2 — DM1)
#
# Spec backlink: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § B2
#
# The DoE-claude repo (repos.doe_claude in the machine-local registry) is the
# authoritative delivery target for central memos. `--to claude-central-em`
# (or any alias) resolves to repos.doe_claude — NOT to ~/.claude.
#
# Guards BOTH the receiver path resolver (_resolve_receiver_path) AND the sender
# identity (em_id_for_root emits the canonical central identity — see
# _central_canonical_id() — when the cwd repo matches repos.doe_claude, the
# canonical set member; anchored on repos.doe_claude, NOT
# ~/.claude — see coordinator_registry.em_id_for_root for resolution order).
#
# Single source of truth: schemas/coordinator-registry.manifest.json § identity.centralReceiverIds
# (via bin/lib/coordinator_registry.py). Drift is now structurally prevented —
# the manifest is the authoritative list; this import reads it at load time.
#
# "No implicit fallback" guarantee is PRESERVED: only an explicit --to <member>
# triggers central delivery; an unregistered sibling still hard-errors.
# ---------------------------------------------------------------------------
# _CENTRAL_RECEIVER_IDS imported above (as alias) from coordinator_registry.


def _is_central_receiver(receiver_em_id: str) -> bool:
    """True when receiver_em_id (case/whitespace-normalised) names the central coordinator."""
    return receiver_em_id.strip().lower() in _CENTRAL_RECEIVER_IDS


# ---------------------------------------------------------------------------
# Publish-target ownership — schema-derived (C4; 2026-06-30)
#
# Spec backlinks: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § H (D6);
#                 docs/wiki/cross-repo-communication.md § Publish-target mirrors have an owner;
#                 docs/plans/2026-06-30-registry-publish-vs-working-targets.md § C4 (D1, F3)
#
# Publish-target repos (OSS distribution mirrors) are NOT EM working trees.
# They are outward publish.sh destinations — a memo dropped there is invisible
# to EMs and gets clobbered on the next publish run. D6 still holds, unchanged.
#
# Schema-derived (C4): the ownership map is now built lazily from
# machine-local's publish.mirrors.* namespace instead of a hardcoded dict.
# For each mirror key (e.g. deep_research_claude), two aliases are mechanically
# derivable (deep-research-claude, deep-research-claude-em); non-derivable legacy
# short-forms are stored in the optional publish.mirrors.<key>.aliases field
# (e.g. deep-research, deep-research-em for deep_research_claude).
#
# The example-game-repo carve-out from the former hardcoded dict is still honoured by
# architecture: example-game-repo publishes INTO a subdirectory of the example-game-repo EM working
# tree (not an independent OSS mirror), so it NEVER appears in publish.mirrors.*
# and never becomes a publish-target rejection. Example-game-repo-em remains a valid
# memo receiver. Do NOT add example-game-repo to publish.mirrors.* without a new plan.
#
# Retired hardcoded _PUBLISH_TARGET_OWNERS dict (2026-06-30):
# The former 6-alias dict ("coordinator-claude-em", "coordinator-claude",
# "deep-research-claude-em", "deep-research-claude", "deep-research-em",
# "deep-research") is now fully covered by schema + aliases. The dict is gone;
# the schema is the single source of truth.
# ---------------------------------------------------------------------------

_PUBLISH_TARGET_OWNERS_CACHE: dict[str, str] | None = None


# ---------------------------------------------------------------------------
# DoE-canonical home/mirror redirect — MANIFEST-DRIVEN (R1 2026-07-15; promoted
# to schemas/coordinator-registry.manifest.json § identity.redirectAliases 2026-07-21)
#
# Spec backlink: cross-repo/inbox/2026-07-14-claude-em-claude-home-redirects-to-doe-in-all-cases.md
# Spec backlink: cross-repo/inbox/2026-07-21-claude-klabauter-em-check-addressee-op-facade-repoint.md
#   § "Defect 1 (redirect-alias MATCH)"
#
# On a DoE-claude system, ~/.claude and coordinator-claude are the SAME central
# surface — the Claude Code harness resolves coordinator plugin source live from
# the DoE-claude repo's coordinator/ tree; ~/.claude is the live-install, not a
# distinct working tree, and we don't do active work there. `.claude-em` /
# `claude-home` / `coordinator-claude` / `coordinator-claude-em` must therefore
# ALWAYS redirect to the canonical central identity (_DOE_CANONICAL_REDIRECT_OWNER),
# on every machine that installs
# DoE-claude — this is a structural fact about the repo layout, not a per-machine
# preference.
#
# Originally (R1, 2026-07-15) this was a hardcoded Python constant, deliberately
# NOT folded into the schema-derived publish.mirrors.* map (_get_publish_target_owners,
# above) because THAT map is gated on machine-local config (publish.mirrors.
# coordinator_claude.owner) being SET — on a fresh clone with no machine-local
# mirrors configured, the schema-derived guard would be silently inactive.
#
# _DOE_CANONICAL_REDIRECT_ALIASES is now imported from coordinator_registry.py
# (REDIRECT_ALIASES), which reads schemas/coordinator-registry.manifest.json §
# identity.redirectAliases — a repo-checked-in file, not machine-local config, so
# the "zero-config on a fresh clone" property from R1 is preserved: the manifest
# ships with the repo and needs no setup step. coordinator_registry.py retains the
# original literal ONLY as a `.get(..., <fallback>)` default for the (should-never-
# happen) case of a manifest predating this promotion or missing the key — see
# that module for the fallback comment. This manifest field is a cross-repo
# contract surface: claude-klabauter's coordinator_core/ops/fleet/_memo_resolver.py
# `read_redirect_aliases()` reads it declaratively as the receiving half of this
# same promotion (their negative-spec forbids hardcoding the literal on their
# side) — a future editor should not treat this as DoE-private.
# ---------------------------------------------------------------------------

_DOE_CANONICAL_REDIRECT_OWNER = _central_canonical_id()
# _DOE_CANONICAL_REDIRECT_ALIASES imported above (aliased from REDIRECT_ALIASES)
# from coordinator_registry.


def _machine_local_mirror_keys() -> "list[str] | None":
    """Enumerate publish.mirrors.* mirror keys from the machine-local registry.

    Filters 'machine-local keys' output for keys matching publish.mirrors.<name>.owner,
    returning the middle <name> segment.

    The .owner key is the canonical sentinel — every mirror table MUST have it,
    so filtering on *.owner gives the definitive mirror-key list without false
    positives from *.path or *.aliases keys.

    Returns [] (empty list) when machine-local succeeds but no mirrors are configured
    (valid empty — "no mirrors" is a legitimate state on a fresh machine).

    Returns None on registry call failure (returncode≠0 or OSError) — callers MUST
    distinguish this from the valid-empty case: a cached {} from a transient failure
    permanently deactivates the publish-target guard for the process lifetime.

    Review: code-reviewer (F4) — previously conflated "no mirrors" and "registry failed",
    both silently returning []. Now returns None on failure so _get_publish_target_owners
    can avoid caching an authoritative-looking empty map.

    Spec backlink: docs/plans/2026-06-30-registry-publish-vs-working-targets.md § C4
    """
    impl = _machine_local_impl()
    python = _resolve_python()
    if impl.endswith(".py") or impl.endswith(".py3"):
        cmd = [python, impl, "keys"]
    else:
        cmd = [impl, "keys"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as exc:
        print(
            f"cross-repo-memo: WARNING: could not enumerate publish mirrors "
            f"(OSError: {exc}); publish-target guard may be inactive.",
            file=sys.stderr,
        )
        return None
    if result.returncode != 0:
        print(
            f"cross-repo-memo: WARNING: could not enumerate publish mirrors "
            f"(machine-local keys exited {result.returncode}); publish-target guard may be inactive.",
            file=sys.stderr,
        )
        return None
    # 2026-08-07 incident fix: `.owner` alone used to be the sole sentinel — a
    # mirror table declared with `.path` but no `.owner` (claude_klabauter:
    # `.path` set, `.owner` never set) was invisible here, so
    # `_is_publish_target_em` never fired and `resolve_receiver_inbox`'s
    # ordinary `repos.*` match delivered the memo straight into a published
    # OSS mirror. `.path` is now ALSO a sentinel — a mirror declared by
    # EITHER field is enough to guard; `_get_publish_target_owners` below
    # substitutes a placeholder owner string when `.owner` is genuinely unset
    # so the guard still fires (with an actionable message) rather than
    # silently trusting an incomplete registration.
    mirror_keys = set()
    for line in result.stdout.splitlines():
        key = line.strip()
        for suffix in (".owner", ".path"):
            if key.startswith("publish.mirrors.") and key.endswith(suffix):
                middle = key[len("publish.mirrors."):-len(suffix)]
                if middle and "." not in middle:
                    mirror_keys.add(middle)
    return sorted(mirror_keys)


def _mirror_key_to_hyphenated(mirror_key: str) -> str:
    """Convert a mirror registry key (e.g. deep_research_claude) to its hyphenated form."""
    return mirror_key.replace("_", "-")


def _derive_mirror_alias_set(mirror_key: str) -> frozenset[str]:
    """Compute all receiver-EM aliases for a publish mirror registry key.

    Standard pair (mechanically derivable from the key):
      <hyphenated-key>     (e.g. coordinator-claude)
      <hyphenated-key>-em  (e.g. coordinator-claude-em)

    Plus any explicit aliases stored in publish.mirrors.<key>.aliases
    (newline-separated by machine-local get — used for legacy short-forms that
    are NOT derivable from the key name, e.g. deep-research, deep-research-em).

    Spec backlink: docs/plans/2026-06-30-registry-publish-vs-working-targets.md § C4 F3
    """
    # Review: code-reviewer (F7) — lowercase the standard pair and any explicit aliases
    # within this function. The sole caller (_get_publish_target_owners) also lowercases
    # on insert, but the docstring implies the returned set is canonical (normalised).
    # Lowercasing here matches the contract the docstring describes.
    hyphenated = _mirror_key_to_hyphenated(mirror_key)
    aliases: set[str] = {hyphenated.lower(), f"{hyphenated.lower()}-em"}

    # Read optional aliases field (newline-joined list from machine-local get).
    aliases_val = _machine_local_get(f"publish.mirrors.{mirror_key}.aliases")
    if aliases_val:
        for alias in aliases_val.splitlines():
            alias = alias.strip().lower()
            if alias:
                aliases.add(alias)

    return frozenset(aliases)


def _get_publish_target_owners() -> dict[str, str]:
    """Build (lazily cached) map of all publish-mirror aliases → owning-EM identity.

    Schema-derived from machine-local's publish.mirrors.* namespace:
      - Enumerates mirror keys via publish.mirrors.<key>.owner sentinel pattern.
      - For each key, derives the standard alias pair + any explicit .aliases.
      - Maps every alias (normalised to lowercase) to the declared owner.

    On valid-empty (no mirrors configured): caches and returns {}.
    On registry call failure: returns {} WITHOUT caching — a transient failure must not
    permanently deactivate the guard for the process lifetime. The WARNING is emitted by
    _machine_local_mirror_keys() on the failure path.

    Lazily populated on first call; the cache persists for the process lifetime.
    Per-invocation recaching would add multiple machine-local subproc calls on
    every --to check — unnecessary given the map is static for a single CLI run.

    Spec backlink: docs/plans/2026-06-30-registry-publish-vs-working-targets.md § C4
    """
    global _PUBLISH_TARGET_OWNERS_CACHE
    if _PUBLISH_TARGET_OWNERS_CACHE is not None:
        return _PUBLISH_TARGET_OWNERS_CACHE

    mirror_keys = _machine_local_mirror_keys()
    if mirror_keys is None:
        # Review: code-reviewer (F4) — registry call failed; warning already printed.
        # Return {} without caching so a transient failure doesn't freeze the guard off.
        return {}

    owners: dict[str, str] = {}
    for mirror_key in mirror_keys:
        owner = _machine_local_get(f"publish.mirrors.{mirror_key}.owner")
        if not owner:
            # 2026-08-07 incident fix: a mirror declared via `.path` alone (no
            # `.owner` set) MUST still classify as a publish target — an
            # incomplete registration is a registry-data defect, not a
            # license to treat the repo as an ordinary receiver. Placeholder
            # owner keeps `_is_publish_target_em` True and gives the
            # rejection message something actionable to print instead of
            # silently falling through to `resolve_receiver_inbox`.
            owner = (
                f"<owner unset — run: machine-local set "
                f"publish.mirrors.{mirror_key}.owner <em-id>>"
            )
        for alias in _derive_mirror_alias_set(mirror_key):
            owners[alias.lower()] = owner

    _PUBLISH_TARGET_OWNERS_CACHE = owners
    return owners


def _normalize_receiver_id(receiver_em_id: str) -> str:
    """Canonical form for receiver-id comparison: stripped + lowercased.

    Single source of normalisation shared by `_is_publish_target_em` and
    `_publish_target_owner` — the non-None guarantee at the owner call sites
    (an `_is_publish_target_em` True-guard implies `_publish_target_owner` non-None)
    holds because BOTH route through this one function. Do not inline `.strip().lower()`
    at either site — that re-creates the divergence risk this collapses. (slice-A F1.)
    """
    return receiver_em_id.strip().lower()


def _is_publish_target_em(receiver_em_id: str) -> bool:
    """True when receiver_em_id (case/whitespace-normalised) names a publish-target
    repo, OR a code-pinned DoE-canonical home/mirror alias (R1).

    Publish targets are outward distribution mirrors, not EM working trees.
    Memos sent there are invisible and get clobbered on next publish.

    Schema-derived (C4): consults _get_publish_target_owners() — the lazily-built
    map from publish.mirrors.* in the machine-local registry — rather than the
    retired hardcoded _PUBLISH_TARGET_OWNERS dict.

    R1 (2026-07-15): ALSO true for `_DOE_CANONICAL_REDIRECT_ALIASES` — this is
    invariant of machine-local config (see the constant's comment above), so a
    fresh clone with no publish.mirrors.* configured still rejects these ids.
    """
    normalized = _normalize_receiver_id(receiver_em_id)
    return (
        normalized in _DOE_CANONICAL_REDIRECT_ALIASES
        or normalized in _get_publish_target_owners()
    )


def _publish_target_owner(receiver_em_id: str) -> str | None:
    """Return the owning-EM identity for a publish-target mirror (or DoE-canonical
    home/mirror alias), or None.

    The owner is the EM working tree that authors and stewards the mirror — the
    correct --to for any concern about the mirrored plugin. None when the id is
    not a publish-target (callers should not be asking in that case). Shares
    `_normalize_receiver_id` with `_is_publish_target_em` so a guarded call site
    is structurally guaranteed non-None.

    R1 (2026-07-15): the code-pinned constant takes precedence over the
    schema-derived map — `_DOE_CANONICAL_REDIRECT_ALIASES` always resolves to
    `_DOE_CANONICAL_REDIRECT_OWNER` regardless of what machine-local says.

    Schema-derived (C4): falls back to _get_publish_target_owners() — same source
    as _is_publish_target_em so the is-guarded-then-owner-call pattern is safe.
    """
    normalized = _normalize_receiver_id(receiver_em_id)
    if normalized in _DOE_CANONICAL_REDIRECT_ALIASES:
        return _DOE_CANONICAL_REDIRECT_OWNER
    return _get_publish_target_owners().get(normalized)


def _redirect_kind(receiver_em_id: str) -> str | None:
    """Classify which flavour of _is_publish_target_em rejection applies.

    Returns "home" when the normalised id is one of the code-pinned DoE-canonical
    home/mirror aliases (`_DOE_CANONICAL_REDIRECT_ALIASES`) — takes precedence
    over "publish" so a receiver that happened to appear in both would still get
    the accurate ~/.claude-is-not-a-mirror wording, not the OSS-mirror wording.
    Returns "publish" when it's a schema-derived publish.mirrors.* alias.
    Returns None when neither (callers should not be asking in that case).
    """
    normalized = _normalize_receiver_id(receiver_em_id)
    if normalized in _DOE_CANONICAL_REDIRECT_ALIASES:
        return "home"
    if normalized in _get_publish_target_owners():
        return "publish"
    return None


def _publish_target_rejection_msg(receiver_em_id: str, owner: str, hint: str = "") -> str:
    """Shared rejection text for a publish-target --to.

    Single source so the legacy `main()` path and the `_cmd_send` path can never
    drift in wording. (slice-A F8.) Displays the stripped receiver id (slice-A F4)
    so padded input doesn't print with stray whitespace; `owner` is the resolved
    `_publish_target_owner` value.
    """
    return (
        f"cross-repo-memo: cannot deliver to '{receiver_em_id.strip()}': it is a "
        f"publish-target OSS distribution mirror owned by `{owner}`, not an EM working "
        f"repo — a memo dropped there is invisible to EMs and clobbered on next publish. "
        f"Route this concern to its owner: `--to {owner}`.{hint}"
    )


def _home_redirect_rejection_msg(receiver_em_id: str, owner: str, hint: str = "") -> str:
    """Rejection text for a DoE-canonical home/mirror alias --to (R1).

    Sibling to `_publish_target_rejection_msg`, split out because that message's
    "publish-target OSS distribution mirror" wording is FALSE for `.claude-em` /
    `claude-home` / `coordinator-claude` / `coordinator-claude-em` — those are not
    outward distribution mirrors, they're the same central surface as `owner`
    under a different name. Single source so the legacy `main()` path and the
    `_cmd_send` path can never drift in wording (mirrors _publish_target_rejection_msg's
    slice-A F8 rationale). Displays the stripped receiver id; `owner` is the
    resolved `_publish_target_owner` value (always `_DOE_CANONICAL_REDIRECT_OWNER`
    for this kind, but callers pass the resolved value rather than the literal so
    the message tracks the constant if it ever changes).
    """
    return (
        f"cross-repo-memo: cannot deliver to '{receiver_em_id.strip()}': on a "
        f"coordinator doctrine repo system, ~/.claude and coordinator-claude are the same central "
        f"surface (we don't do active work in ~/.claude), owned by `{owner}`, not a "
        f"separate EM working tree. Route this concern to its owner: `--to {owner}`.{hint}"
    )


def _receiver_repo_key(receiver_em_id: str) -> str:
    """Map a receiver-EM identity to its machine-local repos.<name> key.

    Strips a trailing '-em' (a bare shortname without the suffix is also
    accepted), applies RECEIVER_EM_ALIASES for the divergent cases, then converts
    dashes→underscores under the repos. namespace. The returned key may or may
    not exist in the registry — the caller resolves it via machine-local and
    hard-errors when absent (single-surface model).
    """
    shortname = receiver_em_id[:-3] if receiver_em_id.endswith("-em") else receiver_em_id
    # code-review F12: guard against an empty shortname after stripping '-em'
    # (e.g. receiver_em_id == "-em" alone). Empty shortname → 'repos.' is degenerate;
    # a cleaner error surfaces downstream when machine-local rejects the empty key.
    if not shortname:
        shortname = receiver_em_id  # keep original so caller gets a clear key to report
    shortname = RECEIVER_EM_ALIASES.get(shortname, shortname)
    return "repos." + shortname.replace("-", "_")


def _print_receiver_unresolved_error(to: str) -> int:
    """Shared 'receiver unresolved' diagnostic for both --dry-run and a real send.

    Review: code-reviewer (Finding 3) — extracted so the --dry-run preview
    branch and the real-send branch can never drift in wording, mirroring
    the _publish_target_rejection_msg / _home_redirect_rejection_msg
    extraction rationale above (single source, both call sites `return` its
    result). Prints either the central-registry-absent message or the
    sibling-not-registered message to stderr and returns 1.
    """
    if _is_central_receiver(to):
        print(
            f"cross-repo-memo: cannot deliver to central ('{to}') — "
            f"repos.doe_claude is not registered on this machine.\n"
            f"  Remediation: machine-local set repos.doe_claude <path-to-the-coordinator-doctrine-repo>.",
            file=sys.stderr,
        )
        return 1
    repo_key = _receiver_repo_key(to)
    known = _known_receiver_ids()
    hint = (
        f"\n  Known receivers on this machine: {', '.join(known)}."
        if known else ""
    )
    print(
        f"cross-repo-memo: cannot deliver to '{to}' — it resolves to "
        f"machine-local key '{repo_key}', which is not registered on this "
        f"machine. A dirty memo cannot be written to a repo that isn't here.\n"
        f"  Remediation: if that repo lives on this machine, register it with "
        f"`machine-local set {repo_key} <path>`. Otherwise route this memo via "
        f"the PM's next session in that repo — there is no central-only "
        f"fallback in the single-surface model.{hint}",
        file=sys.stderr,
    )
    return 1

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _machine_local_impl() -> str:
    """Return the absolute path to _machine_local.py.

    The machine-local shell wrapper (bin/machine-local) is a bash script —
    not directly invocable as a Python subprocess on Windows. We call the
    Python implementation directly, honouring MACHINE_LOCAL_IMPL for test
    isolation (allows tests to mock the lookup without touching the registry).

    Settings-home first (DR-210 Amendment 2026-07-24: "resolves nothing
    through ~/.claude/bin"), falling back to the retired compat mirror only
    when the settings-home candidate is absent on disk. Delegates to
    machine_local_impl_resolve.machine_local_impl_path() (shared resolver —
    review: code-reviewer F3, was a hand-rolled duplicate of that ladder).
    """
    return _mlir_machine_local_impl_path("MACHINE_LOCAL_IMPL")


def _resolve_python() -> str:
    """Return the Python interpreter path for subprocesses.

    Tries python3 first (POSIX), falls back to python, then sys.executable.
    Honours CROSS_REPO_MEMO_PYTHON for test injection.

    Uses sys.executable as final fallback — the interpreter running this
    script is always valid. Probing via subprocess.run can raise
    FileNotFoundError on Windows when the alias doesn't exist on PATH; we
    catch that and move on to the next candidate rather than crashing.

    Deliberate isolation boundary — do not convert to an in-process
    import. This is a distinct interpreter: a `--version` probe of a
    candidate python must observe that candidate's own process exit, not
    this script's. Reason recorded in
    state/audits/2026-08-06-self-spawn-isolation-boundary-classification.md.
    """
    override = os.environ.get("CROSS_REPO_MEMO_PYTHON")
    if override:
        return override
    # python3-first is correct HERE (subprocess calls to _machine_local.py): macOS
    # ships python3 and no bare `python` post-Catalina; Windows clean installs have
    # `python` but no `python3`, so the fallback covers it. This is NOT in tension
    # with the module docstring's `python`-not-`python3` rule — that rule governs the
    # polyglot shebang/exec line (which must run under bash on a clean Windows box),
    # a different concern from interpreter resolution for a Python subprocess.
    for candidate in ("python3", "python"):
        try:
            result = subprocess.run(
                [candidate, "--version"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return candidate
        except FileNotFoundError:
            continue
    # sys.executable is always valid — the interpreter running this script.
    return sys.executable


# ---------------------------------------------------------------------------
# machine-local integration
# ---------------------------------------------------------------------------

# machine-local's own AmbiguousRepoMatch message signature. Its `cmd_get`
# routes `repos.<slug>` through the 4-rung sibling-repo ladder and turns an
# ambiguous rung-2 autodiscovery into `EXIT_OPERATIONAL` (2) — the SAME exit
# code it uses for a version-guard trip or malformed TOML — so the exit code
# alone cannot separate "your slug is ambiguous, pin it with REPO_<SLUG>" from
# "the registry is unreadable". The stderr line can: match on it rather than on
# the exit code, which is what `_machine_local_get_detail`'s third element
# exists to carry.
_AMBIGUOUS_SLUG_STDERR_SIGNATURE = "Ambiguous match for repo slug"


def _machine_local_get_detail(key: str) -> "tuple[str | None, bool, str]":
    """`_machine_local_get_status` plus machine-local's own stderr.

    Same `(value, invocation_ok)` contract as `_machine_local_get_status` —
    see its docstring for the exit-code mapping — with the subprocess's stderr
    appended as a third element (empty string when there was none, or when the
    subprocess could not be launched at all).

    The stderr is not decoration: on an ambiguous repo slug, machine-local has
    ALREADY computed and printed the correct, specific remediation
    (`Set REPO_<SLUG> to disambiguate`), and discarding it is what forced this
    CLI to fall back to a generic message naming two remediations that are both
    wrong for that fault. Callers that must tell an ambiguity apart from a
    genuine read failure use this; everything else keeps the two-tuple.
    """
    impl = _machine_local_impl()
    python = _resolve_python()

    if impl.endswith(".py") or impl.endswith(".py3"):
        cmd = [python, impl, "get", key]
    else:
        # Mock stub: executable script (test mode).
        cmd = [impl, "get", key]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None, False, ""
    stderr = (result.stderr or "").strip()
    if result.returncode == 0:
        value = result.stdout.strip()
        return (value if value else None), True, stderr
    if result.returncode == 1:
        # EXIT_NOT_FOUND — a clean, expected "key not configured here", not a
        # tooling failure. See `_machine_local_get_status`'s docstring.
        return None, True, stderr
    # Any other exit code (e.g. EXIT_OPERATIONAL=2) is a genuine read failure.
    return None, False, stderr


def _machine_local_get_status(key: str) -> "tuple[str | None, bool]":
    """Call machine-local get <key>; return (value, invocation_ok).

    Distinguishes "machine-local itself failed to run" from "the key is
    genuinely absent from the registry" — the ambiguity `_machine_local_get`
    deliberately collapses for its many best-effort callers. Return shape:

      (value, True)  — machine-local ran successfully and returned a value.
      (None, True)   — machine-local ran successfully; the key is genuinely
                       absent (`get` exits 1 — EXIT_NOT_FOUND in
                       _machine_local.py's own exit-code contract, documented
                       there as "always a clean absence — never a broken
                       reader").
      (None, False)  — machine-local invocation itself failed: any exit code
                       OTHER than 0 (success) or 1 (clean not-found) — e.g. 2
                       (EXIT_OPERATIONAL: version guard, malformed TOML) — or
                       an OSError launching the subprocess. Callers that need
                       to distinguish this from genuine absence (e.g.
                       `_classify_receiver`'s "registry-error" branch) MUST
                       check `invocation_ok`, not just test `value is None`.

    Do NOT treat every non-zero exit as failure — exit 1 from `get` is a
    NORMAL, expected outcome (key not configured on this machine yet), not a
    tooling error. Conflating the two would misclassify every legitimately
    unregistered receiver as a registry-read failure — the mirror-image of
    the bug this function exists to fix.

    `_machine_local_get` remains the simple None-collapsing wrapper for the
    many call sites that legitimately treat invocation-failure and genuine-
    absence the same (composing memo frontmatter, sender identity, listing
    display) — this helper exists only for callers that must fail loud
    specifically on invocation failure.

    Spec backlink: docs/plans/2026-06-30-registry-publish-vs-working-targets.md § C4
    (mirrors the None-vs-[] contract established there for
    `_machine_local_mirror_keys` / `_machine_local_repos_keys`).
    """
    value, invocation_ok, _stderr = _machine_local_get_detail(key)
    return value, invocation_ok


def _machine_local_get(key: str) -> str | None:
    """Call machine-local get <key> and return the value, or None on failure.

    On a machine where repos.<key> is absent from the registry, this returns
    None and the caller hard-errors — a dirty memo cannot be written to a repo
    that isn't on this machine (single-surface model: no central-only fallback).

    Collapses BOTH "invocation failed" and "key genuinely absent" to None —
    the many callers here (frontmatter composition, sender identity, listing
    display) don't need to distinguish the two. Callers that DO need to
    distinguish them (draft-time receiver classification) use
    `_machine_local_get_status` instead.

    Suppresses the unrel.install_root namespace warning that machine-local
    emits on stderr on this machine — that warning is cosmetic and unrelated
    to the get call.
    """
    value, _invocation_ok = _machine_local_get_status(key)
    return value


def _machine_local_repos_keys() -> "list[str] | None":
    """Return the raw repos.* keys known to the machine-local registry.

    Returns [] (empty list) when machine-local succeeds but no repos.* keys
    are registered (valid empty — a fresh machine with nothing set up yet).

    Returns None on registry call failure (returncode≠0 or OSError) — callers
    MUST distinguish this from the valid-empty case. Conflating the two was
    the confirmed bug: a transient `machine-local keys` failure silently
    collapsed the sibling receiver set to "none registered", which
    `_classify_receiver` then misreported as "unknown receiver" (typo) for a
    perfectly-registered sibling. Never render None as if it were [] —
    iterating None directly raises; the correct handling is a loud warning
    (see `_format_receiver_listing`) or a distinct classification (see
    `_classify_receiver`'s "registry-error" branch), never silent central-only.

    Mirrors `_machine_local_mirror_keys`'s None-vs-[] contract (F4).

    Spec backlink: docs/plans/2026-06-30-registry-publish-vs-working-targets.md § C4
    """
    impl = _machine_local_impl()
    python = _resolve_python()
    if impl.endswith(".py") or impl.endswith(".py3"):
        cmd = [python, impl, "keys"]
    else:
        cmd = [impl, "keys"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip().startswith("repos.")
    ]


def _known_receiver_ids() -> list[str]:
    """Return the receiver-EM identities known on this machine, for diagnostics.

    Prepends the canonical central identity (see _central_canonical_id()) so it appears
    in the repo-absent error hint even though central is not a repos.* key.
    Used only for the error message (suggestion text / "known receivers" hint)
    — never for correctness-critical classification, that is
    `_classify_receiver`'s job, which surfaces registry read failure as its own
    distinct "registry-error" status rather than folding it in here.

    When `_machine_local_repos_keys()` returns None (registry read failed),
    emits a loud stderr warning and falls back to central-only — this is
    diagnostic hint text, not a receiver-validity verdict, so a degraded hint
    is acceptable as long as it doesn't masquerade as an authoritative list.
    """
    # Review: code-reviewer — F3: filter repos.doe_claude from sibling scan; post-flip
    # repo_key_to_em_id("repos.doe_claude") → the canonical central id (via _central_canonical_id()), already prepended.
    repo_keys = _machine_local_repos_keys()
    if repo_keys is None:
        print(
            "cross-repo-memo: WARNING — machine-local registry read FAILED; "
            "the known-receivers hint below is INCOMPLETE (central only), not "
            "authoritative. Re-run 'machine-local keys' to see the underlying error.",
            file=sys.stderr,
        )
        repo_keys = []
    sibling_ids = sorted(
        repo_key_to_em_id(k)
        for k in repo_keys
        if k != "repos.doe_claude"
    )
    return [_central_canonical_id()] + sibling_ids


def _render_receiver_listing(candidates: list) -> str:
    """Render `memo.list` enumeration-mode candidates into --list-receivers text.

    Purpose: the invoke-and-render half of the --list-receivers A8 strangler
    trampoline — sources ALL section content (central-first header, sibling
    receivers, publish mirrors, DoE-canonical-home aliases, trailing note)
    from the `memo.list` op's kind-discriminated `candidates` list, replacing
    the prior `_format_receiver_listing()`'s independent local re-derivation
    via direct `machine-local` calls. `is_central`/`aliases` arrive
    machine-readable on each `kind:"receiver"` candidate — no client-side
    inference. Central-first ordering is still a render-time decision here
    (the op returns `repos.*` sorted; central-ness is flagged via
    `is_central`, not positioned).

    Doctrine: docs/wiki/cross-repo-communication.md § CLI (Discovering valid receivers).

    Negative-spec: does NOT reproduce `_format_receiver_listing`'s prior
    "registry read FAILED — sibling list UNAVAILABLE" warn-and-CONTINUE
    branch — a hard registry-read failure never reaches this function at all
    (the op fails loud with an `exit_code:1` setup-error envelope instead,
    handled by the caller before this renderer is invoked; see the
    --list-receivers trampoline above). This is an intended A8 contract
    change (map §2), not an omission.

    Spec backlink: pln-memo-tool-rebuild-claude-klabauter-owns--bd5745 § C2, AC2.
    """
    receivers = [c for c in candidates if c.get("kind") == "receiver"]
    mirrors = [c for c in candidates if c.get("kind") == "publish_mirror"]
    home_aliases = [c for c in candidates if c.get("kind") == "canonical_home_alias"]

    central = next((c for c in receivers if c.get("is_central")), None)
    siblings = [c for c in receivers if not c.get("is_central")]

    cid = _central_canonical_id()
    cont_indent = " " * (2 + len(cid) + len("   → "))
    lines = ["Valid --to receivers on this machine:", ""]
    if central is not None:
        # Filter the canonical id out of its own alias annotation so the row
        # never self-lists (the op's central candidate surfaces only the
        # convention-resolvable central id, which is the canonical one).
        alias_str = ", ".join(
            a for a in (central.get("aliases") or []) if a != cid
        )
        lines.append(
            f"  {cid}   → {central.get('repo_path')} "
            f"(the coordinator doctrine repo — coordinator home)"
        )
        if alias_str:
            lines.append(f"{cont_indent}aliases: {alias_str}")
        lines.append(
            f"{cont_indent}resolves via repos.doe_claude in the "
            "machine-local registry"
        )
    else:
        lines.append(
            f"  {cid}   → (repos.doe_claude not registered on this "
            "machine) (the coordinator doctrine repo — coordinator home)"
        )
    lines.append("")

    if siblings:
        lines.append("  Sibling repos (machine-local registry, repos.*):")
        for c in siblings:
            em_id = repo_key_to_em_id(c.get("repo_key"))
            lines.append(f"    {em_id}   → {c.get('repo_path')}")
    else:
        lines.append(
            "  (no sibling repos registered — "
            "`machine-local set repos.<name> <path>` to add one)"
        )

    if mirrors:
        lines.append("")
        lines.append(
            "  Publish-target mirrors (NOT directly addressable — route to the OWNER):"
        )
        for m in mirrors:
            lines.append(
                f"    {m.get('em_id')}   → owned by {m.get('owner')}  "
                f"(OSS distribution mirror — address the owner, not the mirror)"
            )

    # DoE-canonical home/mirror aliases (R1) — sourced from the op's
    # `identity.redirectAliases` enumeration (empty today, not an error, until
    # DoE promotes the manifest field — see memo_list.py's own docstring).
    lines.append("")
    lines.append(
        "  DoE-canonical home aliases (NOT directly addressable — always redirect "
        f"to {_DOE_CANONICAL_REDIRECT_OWNER}):"
    )
    for a in home_aliases:
        lines.append(f"    {a.get('alias')}   → redirects to {_DOE_CANONICAL_REDIRECT_OWNER}")
    lines.append("")
    lines.append(
        "Note: publish-target mirrors are outward OSS distribution mirrors (e.g. "
        "deep-research), not EM working trees — addressing them as --to is "
        "rejected, and the rejection names the owner. DoE-canonical home aliases "
        "(listed above, when the manifest has promoted them) are a separate case: "
        "they're not distribution mirrors at all, just the same central surface "
        f"as {_DOE_CANONICAL_REDIRECT_OWNER} under a different name. Route any concern "
        f"about either kind to the owner named above (→ {_DOE_CANONICAL_REDIRECT_OWNER})."
    )
    return "\n".join(lines)


def _central_receiver_path() -> str | None:
    """Return the DoE-claude repo path for the central receiver, or None if not registered.

    Central delivery resolves to repos.doe_claude in the machine-local registry
    (the DoE-claude repo), NOT to ~/.claude. If repos.doe_claude is absent, returns
    None — the caller must hard-error with a central-specific remediation message.

    Spec backlink: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § B2 (DM1)
    """
    return _machine_local_get("repos.doe_claude")


def _resolve_receiver_path(receiver_em_id: str) -> tuple[str | None, bool]:
    """Resolve a receiver-EM identity to an absolute repo path, or (None, ...) on failure.

    Spec backlink: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § B2 (DM1)

    Returns a `(path, diagnostic_already_printed)` tuple. `diagnostic_already_printed`
    tells the caller whether THIS function already emitted a complete stderr
    diagnostic for the None case — if True, the caller must NOT also print its
    own generic "not registered on this machine" message (that would be a
    second, misleading diagnostic; see the registry-read-failure note below).

    Two-branch resolution, mirroring em_id_for_root on the sender side:
      1. Central special-case: if receiver_em_id is any member of _CENTRAL_RECEIVER_IDS
         (case/whitespace-normalised), return the DoE-claude repo path via
         _central_receiver_path(). Central is NOT a repos.* sibling key — it resolves
         to repos.doe_claude specifically. Returns (None, False) when repos.doe_claude
         is absent (clean absence — caller hard-errors with a central-specific
         remediation message).
      2. Fall-through: convert receiver_em_id to a repos.<name> key via
         _receiver_repo_key and look it up via machine-local. Returns (None, False)
         when the key is cleanly absent (caller hard-errors — no implicit central
         fallback).

    Send-time parent-folder-scan fallback (2026-07-17, gated default-off
    2026-07-21 — Defect #3): when the primary machine-local read genuinely
    FAILS (`invocation_ok is False` — NOT a clean key-absence), the
    parent-folder scan is now an explicit OPT-IN gated behind the
    `COORDINATOR_MEMO_ALLOW_FOLDER_SCAN=1` environment variable, because it
    is the COMMITTING send path: a stderr WARNING is not consent, and a
    same-named or mislaid sibling directory silently delivering here would
    write+commit a memo into the WRONG repo. DEFAULT (env var unset or not
    "1"): the scan does NOT run; a fail-loud diagnostic naming the opt-in is
    printed to stderr and this function returns (None, True) — the diagnostic
    has ALREADY been printed here, so the caller must not print its own.
    OPT-IN (env var == "1"): behavior is unchanged from 2026-07-17 —
    `_resolve_receiver_via_parent_scan` runs; a single verified match returns
    that path after the mandatory WARNING to stderr (rule 6); zero or
    ambiguous matches return (None, True) exactly as before, since both the
    "none" and "ambiguous" sub-cases print their own diagnostic before
    returning (ambiguous candidates are surfaced to stderr first — rule 4).
    Never fires for the central branch above (rule 2 — central keeps its
    existing resolution unconditionally), and never touches
    `_classify_receiver` (draft-time validation is non-committing, so it
    keeps the unconditional scan).

    Security-audit trace (2026-07-21): prior to this tuple return, a
    registry-read FAILURE (situation 2 above) was indistinguishable from a
    clean key-absence (situation 1) once this function returned bare None —
    every caller then unconditionally printed its own
    `_print_receiver_unresolved_error`-shaped "not registered on this
    machine" message on top of the diagnostic already printed here, so the
    operator saw TWO stderr messages and the second one was factually
    misleading (the repo may in fact be registered; the registry *read*
    just failed). `diagnostic_already_printed` closes that gap.

    Ambiguous-slug branch (2026-07-29, project-rag-em memo): `invocation_ok`
    is two-state, and an ambiguous repo slug is a THIRD situation it collapsed
    into "read FAILED" — machine-local raises `AmbiguousRepoMatch` at
    `EXIT_OPERATIONAL` (2), the same code as a version-guard trip or malformed
    TOML. Both remediations the read-failure diagnostic then offered were wrong
    for that fault: the repo IS registered (so "register it" is a no-op), and
    the folder-scan opt-in would opt into an ambiguous scan — the wrong-repo
    delivery the gate exists to prevent. The branch is keyed on machine-local's
    own stderr signature rather than its exit code (which cannot separate the
    two), fires ahead of the folder-scan gate regardless of the opt-in, and
    names `REPO_<SLUG>` — rung 1, which outranks the scan.
    """
    if _is_central_receiver(receiver_em_id):
        return _central_receiver_path(), False
    repo_key = _receiver_repo_key(receiver_em_id)
    value, invocation_ok, ml_stderr = _machine_local_get_detail(repo_key)
    if not invocation_ok:
        if _AMBIGUOUS_SLUG_STDERR_SIGNATURE in ml_stderr:
            # Ambiguity is a THIRD situation the two-state `invocation_ok`
            # boolean cannot express, and it is not a read failure: the registry
            # is fine and the receiver is registered — the slug just resolves to
            # more than one candidate directory. Short-circuits AHEAD of the
            # folder-scan gate deliberately, in both gate positions: the scan is
            # precisely the thing that is ambiguous here, so opting into it (or
            # even naming it as a remediation) points the operator at a
            # wrong-repo delivery. `REPO_<SLUG>` is rung 1 and outranks the
            # scan.
            _print_ambiguous_slug_diagnostic(receiver_em_id, ml_stderr)
            return None, True
        if os.environ.get("COORDINATOR_MEMO_ALLOW_FOLDER_SCAN") != "1":
            _print_folder_scan_disabled_diagnostic(receiver_em_id)
            return None, True
        fallback_path, fallback_status, candidates = _resolve_receiver_via_parent_scan(receiver_em_id)
        if fallback_status == "resolved":
            _print_fallback_resolved_warning(receiver_em_id, fallback_path)
            return fallback_path, False
        if fallback_status == "ambiguous":
            _print_fallback_ambiguous_warning(receiver_em_id, candidates)
        elif fallback_status == "none":
            # Review: code-review F2 — without this, a genuine machine-local
            # registry-read failure at send time was indistinguishable from a
            # clean "receiver never registered" absence once this function
            # returns None; the caller's generic not-registered message then
            # gives the wrong remediation (the repo IS registered, the read
            # just failed).
            _print_registry_error_diagnostic(receiver_em_id)
        return None, True
    return value, False


# _classify_receiver (draft-time receiver classification) DELETED 2026-07-21
# (A8 strangler cutover, verb #5 `draft`) — its sole caller, `_cmd_draft`, now
# passes `classify_receiver: True` to claude-klabauter's `memo.draft` op, which reuses
# memo.send's own resolution authority (`_classify_receiver_for_draft`
# engine-side) instead of this CLI-local classifier. Confirmed zero remaining
# callers via `grep -n "_classify_receiver("` before deletion — the send/
# self-receipt paths use `_resolve_receiver_path`/`_is_publish_target_em`
# directly, never this function. Its own dedicated registry-error helper,
# `_classify_receiver_registry_error`, was deleted alongside it for the same
# reason (its only two call sites were inside this function's body).


def _current_repo_root() -> str | None:
    """The git repo root of the cwd this CLI was invoked from — the sender's
    repo. Returns None when cwd is not inside a git repo or git is unavailable."""
    cc_invoke.ensure_engine_on_path(__file__)
    from coordinator_core.git.repo_root import show_toplevel

    return show_toplevel()


# ---------------------------------------------------------------------------
# Parent-folder-scan fallback resolver (2026-07-17)
#
# Fires ONLY when the primary machine-local read genuinely FAILS (invocation
# error — `_machine_local_get_status`'s `invocation_ok is False`, or a
# `_machine_local_repos_keys()` invocation failure), never on a clean
# key-absence and never for central/publish-target receivers (those keep
# their existing resolution/rejection — see `_classify_receiver` and
# `_resolve_receiver_path`, which run this scan strictly after those checks).
#
# Operators keep active repos co-located (e.g. `/Users/example-operator/X/` holds
# DoE-claude, project-rag, claude-klabauter, example-cockpit-repo,
# example-market-data-repo as sibling git repos) — when the registry itself is
# unreadable, a same-named sibling directory next to the sender's own repo
# root is a reasonable fallback guess, PROVIDED it is exact (never
# prefix/substring — `project-rag` and `project-rag-ue-addon` both exist and
# must never collide) and verified (a real git repo showing coordinator-
# receiver evidence, not merely a coincidentally-named directory). Zero or
# multiple verified matches is a hard fail-loud, never a guess — delivering a
# memo into the wrong tree is worse than failing outright.
# ---------------------------------------------------------------------------

def _normalize_repo_name(name: str) -> str:
    """Fold a repo/receiver shortname to a canonical comparison form.

    Lowercases, strips whitespace, and removes every '-'/'_' run entirely.
    Equality on this folded form is the fallback scan's ONLY match test —
    deliberately NOT prefix/substring — so co-located sibling directories that
    share a prefix (`project-rag` vs `project-rag-ue-addon`) never collide.
    """
    return re.sub(r"[-_]+", "", name.strip().lower())


def _looks_like_coordinator_receiver(path: str) -> bool:
    """Verify-before-deliver gate (rule 5) for the parent-folder-scan fallback.

    A same-named directory must look like a genuine coordinator-receiver repo
    before it can receive a memo — a coincidentally-named non-receiver
    directory is rejected outright (treated as no-match by the caller).
    Requires BOTH: a real git repo (`.git/` present) AND at least one of
    `cross-repo/inbox/`, `cross-repo/`, or a `coordinator.local.md` marker.
    """
    # Review: code-review F5 — use os.path.exists rather than os.path.isdir:
    # in a git-worktree sibling, .git is a FILE (gitdir: pointer), not a
    # directory. isdir would wrongly reject a legitimate worktree receiver.
    if not os.path.exists(os.path.join(path, ".git")):
        return False
    return (
        os.path.isdir(os.path.join(path, "cross-repo", "inbox"))
        or os.path.isdir(os.path.join(path, "cross-repo"))
        or os.path.isfile(os.path.join(path, "coordinator.local.md"))
    )


def _resolve_receiver_via_parent_scan(receiver_em_id: str) -> "tuple[str | None, str, list[str]]":
    """Fallback receiver resolution: scan the SENDER's parent folder for a
    verified sibling git repo whose name exactly (normalized) matches the
    receiver — used ONLY when the primary machine-local read has genuinely
    FAILED (see module note above `_normalize_repo_name`).

    Sender repo root is `_current_repo_root()` (cwd's git root, never a
    hardcoded path); the scan enumerates IMMEDIATE subdirectories of its
    parent (not recursive).

    Returns `(path, status, candidate_names)`:
      "resolved"  — exactly one verified match; `path` is set.
      "none"      — zero verified matches, or the sender's repo root could
                    not be determined (cwd not in a git repo) — `path` is
                    None, `candidate_names` is empty.
      "ambiguous" — more than one verified match — `path` is None,
                    `candidate_names` lists every match so the caller can
                    surface what was ambiguous. NEVER picked between; the
                    caller always falls through to the existing loud
                    registry-error failure on this status.

    Spec: dispatch brief "add a parent-folder-scan fallback resolver"
    (2026-07-17, cross-repo-memo resilience feature — no standalone plan file).
    """
    sender_root = _current_repo_root()
    if sender_root is None:
        return None, "none", []
    parent = os.path.dirname(sender_root)
    shortname = receiver_em_id[:-3] if receiver_em_id.strip().endswith("-em") else receiver_em_id
    # Review: code-review F1 — resolve RECEIVER_EM_ALIASES before normalizing,
    # mirroring _receiver_repo_key (line ~523), so the scan searches for the
    # same on-disk shortname the primary machine-local path would have used
    # (e.g. 'example-game-repo' -> 'example_game_workbench_repo'). Without this, the fallback
    # can never resolve for any alias-divergent receiver.
    shortname = RECEIVER_EM_ALIASES.get(shortname, shortname)
    target = _normalize_repo_name(shortname)
    if not target:
        return None, "none", []
    try:
        entries = sorted(os.listdir(parent))
    except OSError:
        return None, "none", []
    matches = []
    for entry in entries:
        candidate_dir = os.path.join(parent, entry)
        if not os.path.isdir(candidate_dir):
            continue
        if _normalize_repo_name(entry) != target:
            continue
        if _looks_like_coordinator_receiver(candidate_dir):
            matches.append(candidate_dir)
    if len(matches) == 1:
        return matches[0], "resolved", [os.path.basename(m) for m in matches]
    if not matches:
        return None, "none", []
    return None, "ambiguous", [os.path.basename(m) for m in matches]


def _print_fallback_resolved_warning(receiver_em_id: str, path: str) -> None:
    """Rule 6 ("Loud when used"): the single canonical WARNING wording for a
    successful parent-folder-scan fallback resolution — printed to STDERR
    (never stdout — stdout stays the machine-parseable path contract) from
    BOTH the draft-time (`_classify_receiver`) and send-time
    (`_resolve_receiver_path`) call sites, so the wording never drifts."""
    print(
        f"cross-repo-memo: WARNING — machine-local registry read FAILED; "
        f"resolved '{receiver_em_id}' to {path} via SENDER-PARENT-FOLDER SCAN "
        f"(fallback). Verify this is the intended receiver before relying on it.",
        file=sys.stderr,
    )


def _print_folder_scan_disabled_diagnostic(receiver_em_id: str) -> None:
    """Fail-loud companion for the send-time (`_resolve_receiver_path`)
    default-off folder-scan gate (Defect #3, 2026-07-21): printed instead of
    running `_resolve_receiver_via_parent_scan` when
    `COORDINATOR_MEMO_ALLOW_FOLDER_SCAN` is unset/not "1". Names the opt-in
    explicitly so the operator knows the scan CAN run, just not silently."""
    repo_key = _receiver_repo_key(receiver_em_id)
    print(
        f"cross-repo-memo: machine-local registry read FAILED — cannot "
        f"resolve receiver '{receiver_em_id.strip()}'. The parent-folder-scan "
        f"fallback is DISABLED by default on this (committing) send path "
        f"because it can silently deliver a memo into the WRONG repo (a "
        f"mislaid or same-named sibling directory would match). "
        f"Remediation: fix the machine-local registry (register "
        f"'{repo_key}' — re-run 'machine-local keys' to see the underlying "
        f"error), or set COORDINATOR_MEMO_ALLOW_FOLDER_SCAN=1 to explicitly "
        f"opt into the scan for this invocation.",
        file=sys.stderr,
    )


def _print_ambiguous_slug_diagnostic(receiver_em_id: str, machine_local_stderr: str) -> None:
    """Fail-loud for an AMBIGUOUS receiver slug at send time — distinct from
    both a registry-read failure and a clean key-absence.

    Relays machine-local's own stderr verbatim (it already names the specific
    slug, the candidate count, and the exact `REPO_<SLUG>` to set) and names
    rung 1 as THE remediation. Deliberately does NOT mention
    `COORDINATOR_MEMO_ALLOW_FOLDER_SCAN`: on an ambiguous slug the parent-folder
    scan is strictly wrong advice, because the scan is the ambiguous step — it
    would opt the operator into exactly the wrong-repo delivery the gate exists
    to prevent.

    Negative spec: never suggest registering the repo either. It IS registered;
    "register it" is a no-op that sends the operator hunting a fault that isn't
    there.
    """
    slug = _receiver_repo_key(receiver_em_id).split(".", 1)[-1]
    env_var = f"REPO_{slug.upper()}"
    print(
        f"cross-repo-memo: cannot resolve receiver '{receiver_em_id.strip()}' — "
        f"its repo slug is AMBIGUOUS on this machine. This is NOT a registry-read "
        f"failure and NOT an unregistered receiver; machine-local reports:\n"
        f"  {machine_local_stderr}\n"
        f"Remediation: set {env_var} to the intended repo path (rung 1 of the "
        f"resolution ladder — it outranks the search-root scan that is ambiguous "
        f"here) and retry.",
        file=sys.stderr,
    )


def _print_registry_error_diagnostic(receiver_em_id: str) -> None:
    """Review: code-review F2 — send-time (`_resolve_receiver_path`) companion
    to the draft-time "registry-error" message: printed as a side effect
    ALONGSIDE (not instead of) the caller's existing not-registered message,
    the same "print diagnostic, then fall through to the existing message"
    convention `_print_fallback_ambiguous_warning` already uses — so a
    genuine machine-local registry-read failure at send time is distinguished
    from a clean "receiver never registered" absence, mirroring the wording
    `_classify_receiver_registry_error`'s draft-time exit-3 branch uses."""
    print(
        f"cross-repo-memo: machine-local registry read FAILED — cannot "
        f"resolve receiver '{receiver_em_id.strip()}'. This is a tooling "
        f"failure, NOT confirmation that the receiver is unregistered. "
        f"Re-run 'machine-local keys' to see the underlying error before "
        f"retrying.",
        file=sys.stderr,
    )


def _print_fallback_ambiguous_warning(receiver_em_id: str, candidate_names: list[str]) -> None:
    """Surfaces the candidate directory names for an ambiguous parent-folder
    scan (rule 4) — printed alongside (not instead of) the existing loud
    registry-error failure message at the call site."""
    print(
        f"cross-repo-memo: machine-local registry read FAILED, and the "
        f"SENDER-PARENT-FOLDER SCAN fallback found AMBIGUOUS candidates for "
        f"'{receiver_em_id}': {', '.join(candidate_names)}. Refusing to guess — "
        f"resolve the ambiguity or fix the registry read and retry.",
        file=sys.stderr,
    )


# _classify_receiver_registry_error DELETED 2026-07-21 (A8 strangler cutover,
# verb #5 `draft`) — its only two call sites lived inside `_classify_receiver`
# (deleted above), so it went dead alongside it. Confirmed via
# `grep -n "_classify_receiver_registry_error("` before deletion.


def _sender_em_id() -> str:
    """Identify the sending EM from the repo this CLI runs in — never hardcoded,
    never an EM self-identify step. Inferred from cwd's git root against the
    machine-local repo list (the inverse of receiver resolution).

    Central identity anchored on repos.doe_claude (not ~/.claude) — see
    coordinator_registry.em_id_for_root for resolution order.
    """
    root = _current_repo_root()
    # _machine_local_repos_keys() returns None on registry-read failure — treat
    # as empty here (best-effort identity derivation, not correctness-critical
    # classification; a registry-read failure degrades to the unregistered-repo
    # basename fallback in em_id_for_root, which is already a non-fatal path).
    paths = {k: _machine_local_get(k) for k in (_machine_local_repos_keys() or [])}
    # Ensure repos.doe_claude is present — it's the central identity anchor.
    paths.setdefault("repos.doe_claude", _machine_local_get("repos.doe_claude"))
    return em_id_for_root(root, {k: v for k, v in paths.items() if v})


def _guard_sender_identity_before_delivery() -> str | None:
    """Detect-then-fail-loud guard for every SEND/DRAFT path that composes a memo.

    Root cause (2026-07-11): an EM ran the CLI from a non-repo cwd (e.g. the
    parent directory of all sibling repos) — `_current_repo_root()` returned
    None, `_sender_em_id()` silently degraded to 'unknown-sender-em', and the
    memo was delivered anyway with a phantom sender. That degrade-and-send is
    the bug: identity is script-derived from cwd's git root, never self-
    asserted, so an unresolvable sender must ABORT the send/draft, not paper
    over it with a placeholder id.

    Returns an error message (caller prints to stderr and aborts, non-zero
    exit) when the sender is unresolvable — i.e. cwd is not inside any git
    repo, so _sender_em_id() would return 'unknown-sender-em'. Returns None
    when the sender resolved to a real identity (proceed with send/draft).

    Scope (PM ruling 2026-07-11): fail-loud applies ONLY to the
    'unknown-sender-em' (root=None) case. The unregistered-repo basename
    fallback (em_id_for_root case #4 — a real git repo that just isn't
    registered in machine-local yet) is a WARNING, not a hard fail — see
    _warn_if_unregistered_sender below. Do not widen this guard to cover that
    case; it would break legitimate sends from a freshly-cloned, not-yet-
    registered sibling repo.

    Negative-spec: there is no --from / self-identify override here or
    anywhere on the send path. The whole point of script-derived identity is
    that a sender cannot assert who it is — cd into the sending repo instead.
    """
    root = _current_repo_root()
    if root is not None:
        return None
    cwd = os.getcwd()
    return (
        f"cross-repo-memo: cannot determine sender identity — cwd is not inside "
        f"a git repo, so 'from:' would silently become 'unknown-sender-em'.\n"
        f"  Current directory: {cwd}\n"
        f"  Sender identity is resolved DETERMINISTICALLY from your cwd's git "
        f"root against the machine-local registry — it is never self-asserted. "
        f"`cd` into the sending repo's working tree (not a parent directory "
        f"containing multiple repos) and re-run."
    )


def _warn_if_unregistered_sender() -> None:
    """Emit a one-line WARNING when the sender resolves via the unregistered-repo
    basename fallback (em_id_for_root case #4) — a real git repo not yet
    registered under repos.<name> in the machine-local registry.

    Non-fatal by design (PM ruling 2026-07-11) — flagged here for reviewer
    follow-up, not hardened into a block: unlike the 'unknown-sender-em' case
    guarded by _guard_sender_identity_before_delivery, this sender IS a real
    repo, just not yet in the registry, so blocking would punish a legitimate
    fresh-clone sender.
    """
    root = _current_repo_root()
    if root is None:
        return
    # _machine_local_repos_keys() returns None on registry-read failure — treat
    # as empty here (same best-effort rationale as _sender_em_id above).
    raw_paths = {k: _machine_local_get(k) for k in (_machine_local_repos_keys() or [])}
    raw_paths.setdefault("repos.doe_claude", _machine_local_get("repos.doe_claude"))
    known_paths = {k: v for k, v in raw_paths.items() if v}
    resolved = em_id_for_root(root, known_paths)
    basename_fallback = os.path.basename(root.rstrip("/\\")) + "-em"
    is_registered_match = any(_same_path(root, p) for p in known_paths.values())
    if resolved == basename_fallback and not is_registered_match:
        print(
            f"cross-repo-memo: WARNING — sender resolved to '{resolved}' from an "
            f"UNREGISTERED repo ({root}) — verify this is intended. Register it with "
            f"`machine-local set repos.<name> {root}` if it should have a stable identity.",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# Shared pre-dispatch steps (--to and --campaign-to)
# ---------------------------------------------------------------------------
# Review: code-reviewer (Finding 2) — main()'s --campaign-to block was a
# hand-duplicated near-copy of these four pre-dispatch steps from the
# ordinary --to path (exactly the drift risk that produced Finding 1: the
# --to path's --dry-run handling never got ported to --campaign-to because
# nothing forced the two blocks to stay in sync). Extracted here so both
# call sites share one implementation each.


def _check_summary_over_cap(summary: str | None) -> str | None:
    """Shared --summary over-cap check for every live send path.

    Fails loud on an over-cap EXPLICITLY authored --summary rather than
    silently truncating it mid-sentence (2026-07-22 body-drop verdict memo,
    cross-repo/inbox/2026-07-22-claude-central-em-snippet-sync-adoption-and-
    body-drop-verdict.md).

    Returns the stderr diagnostic string when `summary` exceeds
    `_SUMMARY_MAX_CHARS`, else None (pass).
    """
    if summary is not None and len(summary) > _SUMMARY_MAX_CHARS:
        return (
            f"cross-repo-memo: --summary is {len(summary)} chars, cap is "
            f"{_SUMMARY_MAX_CHARS} — shorten it or omit --summary to derive "
            f"one from the body instead."
        )
    return None


def _read_body_from_file_or_stdin(
    body_file: str | None, empty_body_ok: bool
) -> tuple[str | None, str | None]:
    """Shared body read + empty-body guard for every live send path.

    `body_file` is `--body-file` (None / '-' / a path) — the '-' stdin
    sentinel and an omitted --body-file both read stdin (Unix curl/tar/git
    convention). Empty-body guard (2026-07-22 body-drop root-cause verdict
    memo): under Claude Code's Bash tool, stdin is /dev/null — a send whose
    heredoc never arrived on the terminal used to yield body="" with no
    warning, silently composing a hollow frontmatter-only memo (claude-klabauter
    1d44757c). Both transport shapes (stdin AND a zero-byte --body-file) get
    the same guard; `empty_body_ok` (--empty-body) is the explicit opt-in
    for a deliberately body-less memo.

    Returns (body, error) — exactly one is None.
    """
    if body_file and body_file != "-":
        try:
            with open(body_file, "r", encoding="utf-8") as f:
                body = f.read()
        except OSError as exc:
            return None, f"cross-repo-memo: cannot read body file: {exc}"
        if not body.strip() and not empty_body_ok:
            return None, (
                f"cross-repo-memo: --body-file {body_file!r} was empty — "
                f"pass --empty-body to send a deliberately body-less memo."
            )
        return body, None
    body = sys.stdin.read()
    if not body.strip() and not empty_body_ok:
        return None, (
            "cross-repo-memo: body read from stdin was empty — under Claude "
            "Code's Bash tool stdin is /dev/null; pass --body-file <path>, "
            "or pass --empty-body to send a deliberately body-less memo."
        )
    return body, None


def _sender_identity_guard_and_warn() -> str | None:
    """Shared sender-identity guard + unregistered-sender warning.

    Fails loud on an unresolvable sender BEFORE any filesystem mutation (see
    `_guard_sender_identity_before_delivery` docstring for the root-cause: a
    phantom 'unknown-sender-em' memo was silently delivered from a cwd
    outside any git repo). No --from override exists to bypass this.

    Returns an error message (caller prints to stderr and aborts) when the
    sender is unresolvable. Otherwise emits the non-fatal
    unregistered-sender WARNING (`_warn_if_unregistered_sender`, if
    applicable) as a side effect and returns None.
    """
    guard_error = _guard_sender_identity_before_delivery()
    if guard_error is not None:
        return guard_error
    _warn_if_unregistered_sender()
    return None


def _build_and_validate_scoped_to(
    args: argparse.Namespace, *, error_prefix: str
) -> tuple[dict[str, str] | None, str | None]:
    """Shared scoped_to assembly + presence-triggered completeness gate.

    Assembles the nested scoped_to dict from the --scoped-to-* flags and
    validates it against `_scoped_to_errors` (the same presence-triggered
    completeness rule enforced on the outbox/self-receipt paths — see
    _scoped_to_errors docstring / schema.js:2290). `error_prefix` carries
    the only wording difference between call sites (e.g. "refusing send" vs
    "refusing --campaign-to send").

    Returns (scoped_to, error) — exactly one is None. `error` is the
    complete stderr diagnostic string (caller only needs to print it).
    """
    scoped_to = _build_scoped_to(
        args.scoped_to_artifact,
        args.scoped_to_version,
        args.scoped_to_sha,
        args.scoped_to_seam,
    )
    errors = _scoped_to_errors(args.kind, scoped_to)
    if errors:
        return None, (
            f"cross-repo-memo: {error_prefix} — " + "; ".join(errors) + " Nothing was sent."
        )
    return scoped_to, None


# ---------------------------------------------------------------------------
# Frontmatter composition
# ---------------------------------------------------------------------------

# _today, _now_iso, _SUMMARY_MAX_CHARS, _derive_summary — imported from memo_compose above.
# (example-initiative tc-0 C4: extracted to shared lib so coordinator-doc-new and cross-repo-memo share them.)


# sent_by (C7, docs/plans/2026-08-13-session-identity-earns-its-keep.md):
# same explicit sentinel memo_send.py._resolve_sent_by uses for "this send
# could not resolve its own session id" — a memo that cannot name its sender
# must SAY SO, never omit the field silently.
_SENT_BY_UNRESOLVED = "unresolved"


def _resolve_sent_by(cwd: str | None = None) -> str:
    """Resolve THIS send's session UUID via the canonical resolver
    (coordinator_core.session.core.resolve_session_id), substituting the
    explicit `_SENT_BY_UNRESOLVED` sentinel — never silent omission — when
    resolution fails.

    Mirrors memo_send.py._resolve_sent_by exactly (same resolver, same
    sentinel, same never-raise contract) so the engine-routed send path and
    this CLI's direct self-receipt write path agree on what an unresolvable
    session id means. Resolved ONCE per invocation by the caller and
    threaded through — never re-resolved per write point (two resolutions
    can disagree).
    """
    try:
        cc_invoke.ensure_engine_on_path(__file__)
        from coordinator_core.session import core as _session_core

        session_id = _session_core.resolve_session_id(cwd)
    except Exception:
        session_id = ""
    return session_id or _SENT_BY_UNRESOLVED


def _compose_frontmatter(
    *,
    title: str,
    to: str,
    topic: str,
    body: str,
    self_receipt: bool = False,
    decision: str | None = None,
    supersedes: str | None = None,
    summary: str | None = None,
    kind: str | None = None,
    scoped_to: dict[str, str] | None = None,
    sent_by: str | None = None,
) -> str:
    """Compose the YAML frontmatter block for a memo.

    Thin wrapper — delegates to memo_compose.compose_frontmatter, passing
    from_id=_sender_em_id() (resolved from the sender's repo at call time).
    Public signature unchanged so existing call sites and tests work without
    modification (scoped_to and sent_by are additive, default to None).

    Schema: docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md § Chunk 3
    Spec backlink: docs/plans/2026-06-25-example-initiative-tc-0-canonical-baton-shape.md § C4
    See memo_compose.compose_frontmatter for full docstring and semantics.
    """
    return _mc_compose_frontmatter(
        from_id=_sender_em_id(),
        title=title,
        to=to,
        topic=topic,
        body=body,
        self_receipt=self_receipt,
        decision=decision,
        supersedes=supersedes,
        summary=summary,
        kind=kind,
        scoped_to=scoped_to,
        sent_by=sent_by,
    )


# _yaml_quote — imported from memo_compose above (example-initiative tc-0 C4).


def _compose_memo(
    *,
    title: str,
    to: str,
    topic: str,
    body: str,
    self_receipt: bool = False,
    decision: str | None = None,
    supersedes: str | None = None,
    summary: str | None = None,
    kind: str | None = None,
    scoped_to: dict[str, str] | None = None,
    sent_by: str | None = None,
) -> str:
    """Compose the full memo document (frontmatter + body).

    Thin wrapper — delegates to memo_compose.compose_memo, passing
    from_id=_sender_em_id() (resolved from the sender's repo at call time).
    Public signature unchanged so existing call sites work without modification
    (scoped_to and sent_by are additive, default to None).

    Spec backlink: docs/plans/2026-06-25-example-initiative-tc-0-canonical-baton-shape.md § C4
    """
    return _mc_compose_memo(
        from_id=_sender_em_id(),
        title=title,
        to=to,
        topic=topic,
        body=body,
        self_receipt=self_receipt,
        decision=decision,
        supersedes=supersedes,
        summary=summary,
        kind=kind,
        scoped_to=scoped_to,
        sent_by=sent_by,
    )


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def _memo_filename(topic: str, sender: str) -> str:
    """Produce the receiver-side inbox filename: <date>-<from>-<topic>.md.

    Folds the sender identity into the name to prevent same-day+topic clobber
    when one broadcast memo goes to N repos and each replies with the same
    obvious topic slug.  The O_EXCL clobber guard remains the safety net — this
    makes the guard rarely fire rather than removing it.

    sender is passed in by the caller (resolved from _sender_em_id()) rather
    than fetched here so this function is unit-testable without cwd mocking.

    Defensive empty-sender fallback: if sender is absent or reduces to nothing
    after slug sanitization, fall back to <date>-<topic>.md — never emit a
    bare <date>--<topic>.md double-dash filename.

    Doubled-date guard: senders often name --topic slugs after a dated
    state/memo-outbox/ listing, so topic may already carry a leading
    YYYY-MM-DD- prefix — sometimes more than one (an already-doubled topic
    fed back through, e.g. after a prior filename was reused as a topic
    string). Strip a RUN of leading date prefixes before prepending
    _today() — a single-prefix strip only removes one and leaves a doubled
    result still doubled after re-prepending (e.g.
    2026-07-06-2026-07-06-foo -> single strip -> 2026-07-06-foo -> prepend
    today -> 2026-07-06-2026-07-06-foo, unchanged).
    Spec backlink: cross-repo/inbox/2026-07-02-cross-repo-memo-doubles-date-prefix.md
    """
    # Slug-sanitize sender: lowercase, collapse any run of non-[a-z0-9-] chars
    # to a single dash, collapse consecutive dashes, strip leading/trailing dashes.
    sanitized = re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9-]+", "-", sender.lower())).strip("-") if sender else ""
    topic = re.sub(r"^(\d{4}-\d{2}-\d{2}-)+", "", topic)
    if not sanitized:
        # Empty sender after sanitize — fall back to the pre-sender shape to
        # avoid emitting a bare <date>--<topic>.md double-dash filename.
        return f"{_today()}-{topic}.md"
    return f"{_today()}-{sanitized}-{topic}.md"


def _write_file(path: str, content: str, receiver_path: str) -> None:
    """Write content to path, creating parent directories as needed.

    Spec backlink: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § B1 (T1)

    code-review F2: the path argument is the composed receiver_side_path, derived from
    machine-local receiver_path + 'cross-repo/inbox/' + validated topic slug. Even so,
    we resolve to realpath and assert the result stays within the receiver repo root
    before writing, to guard against registry-value or OS symlink shenanigans.

    T1 fix (correctness trap): expected_root is now anchored directly to receiver_path
    rather than being derived by walking up from the composed path. With the new path
    shape cross-repo/inbox/<file>, walking up ONE parent yields cross-repo/inbox/ and
    walking up TWO parents yields cross-repo/ — both wrong. Anchoring to receiver_path
    directly is unambiguous regardless of how many subdirs deep the target lives.
    Negative-spec: do NOT re-derive expected_root by walking up from `path` — with
    cross-repo/inbox/<file> that requires walking two parents, a brittle count that
    breaks silently if the path depth changes again.

    Raises:
        FileExistsError: if ``path`` already exists (same-day collision guard).
        ValueError: if the resolved path escapes ``receiver_path`` (traversal guard).
    """
    # T1: anchor the traversal guard to receiver_path — the repo root known at the call
    # site — not derived by walking up from the composed path (which is one level deeper
    # now that the target is cross-repo/inbox/<file> instead of cross-repo/<file>).
    expected_root = receiver_path

    # Amended 2026-05-23 per code-reviewer chain-end review (F5 — security):
    # Run the realpath guard BEFORE os.makedirs — spec § B3 DM2 requires zero
    # filesystem mutation on the hard-error path. os.path.realpath resolves symlinks
    # in the existing portion of each path without requiring the target to exist, so
    # the traversal-via-symlink case is caught correctly without creating directories.
    # Review: F5 — move makedirs after guard; orphan dirs on traversal-via-symlink path
    inbox_dir = os.path.dirname(path)  # e.g. /work/<your-repo>/cross-repo/inbox
    real_path = os.path.realpath(path)
    real_root = os.path.realpath(expected_root)

    # Normalise for case-insensitive file systems (Windows).
    if not os.path.normcase(real_path).startswith(os.path.normcase(real_root + os.sep)):
        raise ValueError(
            f"Path-traversal guard: resolved path {real_path!r} escapes receiver root "
            f"{real_root!r}. Refusing write."
        )

    # makedirs only after the guard passes — no filesystem mutation on the error path.
    os.makedirs(inbox_dir, exist_ok=True)

    # Atomic exclusive create — mirrors the outbox O_EXCL pattern.
    # Memo filenames are deterministic YYYY-MM-DD-<from>-<topic>.md (no nonce); two
    # sends on the same day from the same sender with the same topic would resolve to
    # the same path and a plain open("w") would silently clobber the first memo.
    # O_EXCL fails loud instead.
    # Negative-spec: do NOT switch back to open("w") — silent clobber is data loss.
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        raise FileExistsError(
            f"cross-repo-memo: refusing to deliver to {path!r}: "
            f"a memo with this date+topic already exists (would silently clobber). "
            f"Choose a distinct --topic or remove the existing file."
        ) from None

    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)


def _resolve_machine_slug() -> str:
    """Best-effort machine-slug resolver for the receiver's daily-branch name.

    Mirrors the precedence in coordinator_core/machine_resolver.py's
    compute_machine() (a cheap standalone replica, not a fork of the canonical
    resolver): $COORDINATOR_MACHINE env override → machine-local
    registry `coordinator.machine_slug` → live `hostname`. Never raises — an
    OSError from the hostname probe falls through to "unknown-machine", which
    still yields a legible (if generic) branch name rather than crashing the
    delivery commit.
    """
    override = os.environ.get("COORDINATOR_MACHINE", "").strip()
    if override:
        return override
    registry_slug = _machine_local_get("coordinator.machine_slug")
    if registry_slug:
        return registry_slug
    try:
        import socket
        host = socket.gethostname().strip()
        if host:
            return host.split(".")[0]
    except OSError:
        pass
    return "unknown-machine"


def _commit_delivered_memo(
    receiver_path: str, receiver_side_path: str, sender: str, title: str
) -> "tuple[str, bool] | None":
    """Stage+commit ONLY the just-delivered memo file in the RECEIVER repo.

    SOLE CALLER: the `--self-receipt` arm. Every ordinary send routes through
    the claude-klabauter engine, which commits the delivery itself
    (`coordinator_core/ops/fleet/memo_send.py::_commit_delivered_memo`); this
    copy was retired from that path 2026-07-21 and is retained only for
    self-receipt, which bypasses the engine entirely and is its own sole
    committer. `--self-receipt` is single-repo by construction (rejected with
    `--campaign-to`, see `_cmd_send`), so on this path the "receiver" IS the
    caller's own repo.

    NOT A DUPLICATE OF THE ENGINE COPY — negative spec, do not "dedupe". The
    two differ on exactly two invariants, and both differences follow from the
    single-repo/foreign-repo split above:

      1. NO all-hooks-off `-c core.hooksPath=<empty-tmpdir>`. The engine
         suppresses the receiver's hooks because a FOREIGN repo's commit-time
         machinery is not ours to run — a `prepare-commit-msg` stamping a
         Session-Id trailer would inject a false trailer onto a foreign
         delivery. Here the hooks are the repo's OWN, on its own commit, and
         running them is correct. Adding hooksPath here would suppress hooks
         the repo is entitled to fire.
      2. Branch creation is RETAINED (see the PM ruling below). The engine
         removed it 2026-07-21 (the Staff Engineer REQUIRES_CHANGES) because creating or
         switching a branch in a repo the engine does not own is an
         unacceptable foreign mutation — a receiver mid-bisect or mid-rebase
         has its branch state changed out from under it. Self-receipt has no
         foreign tree to mutate, so that rationale does not reach this path.

    Collapsing the two would either suppress the local repo's own hooks or
    reintroduce foreign branch mutation, depending on which copy won. Nothing
    else here is deliberately divergent: the scoped single-path add/commit, the
    never-raise contract, the AC3 unstage-on-failure, and the three-phrasing
    idempotent-no-op guard are all held in common and SHOULD be kept in step.

    Reliable-delivery fix (2026-07-11): delivery previously left the memo as a
    dirty untracked file, relying on a receiver-EM organically noticing it in
    `git status`. That's a soft signal — this commits the memo so delivery is a
    durable, cross-device-visible fact rather than a hope.

    Explicit single-path commit: `git add -- <memo_relpath>` then
    `git commit -m "<subject>" -- <memo_relpath>`. NEVER `git add -A` / `git
    add .` here — a dirty receiver tree (normal under concurrent-EM git
    operations, see coordinator/CLAUDE.md § Concurrent-EM Git Operations) must
    never be swept into the delivery commit. This mirrors the coordinator-wide
    scoped-commit discipline (`scoped-safety-commits.md`), applied to a repo
    this script does not own.

    Does NOT push — the receiver's own auto-push hook on work/* branches
    handles propagation; pushing from here would be a foreign write to a repo
    this CLI doesn't drive interactively.

    PM ruling (2026-07-11, refining the initial skip-on-no-branch design):
    a receiver with NO active branch (detached HEAD, or unborn/no-commits-yet)
    gets a work branch CREATED, not skipped — prefer the receiver's own daily-
    branch convention `work/{machine}/{YYYY-MM-DD}` (cheap best-effort
    machine+date resolution via _resolve_machine_slug + local date), falling
    back to a clearly-named `work/cross-repo-memo-delivery` if branch creation
    under the daily-convention name fails for any reason (e.g. it already
    exists and points somewhere unexpected). A repo already on a normal branch
    is used as-is — never create/switch away from an existing branch.

    Graceful degradation (best-effort, never fails the send):
      - detached HEAD / bare repo / no commits yet → CREATE + switch to a work
        branch (see above), then commit there.
      - branch creation itself fails (e.g. truly bare repo with no way to
        create a first commit) → SKIP, emit WARNING, leave the file
        written+uncommitted.
      - on `main`/`master` (pre-existing, not just-created) → still commit
        (branch discipline is the receiver's to resolve, not this script's) —
        WARNING notes it so the operator sees.
      - nothing to commit (git status reports no change to the memo path,
        e.g. an already-committed identical file) → treat as success, no-op.
      - any git subprocess failure → SKIP, emit WARNING, leave file as-is.

    Never raises — this is a post-delivery reliability enhancement, not a
    correctness gate. The memo is already durably written by the time this
    runs; a commit failure here must not turn a successful delivery into a
    reported failure.

    Design-as-offers (coordinator ~/.claude/CLAUDE.md § Implementation
    Standards — Extensions): on a successful commit, the caller (not this
    function) prints an explanatory stdout line naming the receiver repo and
    branch, and stating plainly that committing into another repo's working
    tree is a deliberate, sanctioned exception to "don't touch others' repos"
    — done because the dirty-file model's weakness is fragility (an
    uncommitted memo can be lost or missed by an EM that never lands on that
    device), not because the commit-in-receiver approach is free of tradeoffs.
    This function returns the (branch, committed) outcome so the caller can
    render that message accurately instead of guessing.
    """
    memo_relpath = os.path.relpath(receiver_side_path, receiver_path)

    def _unstage_delivered_memo() -> None:
        """Undo `git add` of memo_relpath (AC3) so a failed delivery leaves
        the receiver's index exactly as it found it. Best-effort and never
        raises, mirroring this function's own never-raise contract — an
        unstage failure must not turn an already-reported commit failure
        into a crash. `git reset -- <path>` is a safe no-op when the path
        was never staged (e.g. the `git add` step itself failed).
        """
        try:
            subprocess.run(
                ["git", "-C", receiver_path, "reset", "--", memo_relpath],
                capture_output=True,
                text=True,
            )
        except OSError:
            pass

    try:
        head_check = subprocess.run(
            ["git", "-C", receiver_path, "symbolic-ref", "-q", "HEAD"],
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        print(
            f"cross-repo-memo: WARNING — could not commit delivered memo in receiver "
            f"repo ({exc}); file was written but left uncommitted.",
            file=sys.stderr,
        )
        return None

    branch_name: str
    just_created = False
    if head_check.returncode != 0:
        # Detached HEAD, bare repo, or no commits yet (symbolic-ref -q fails silently
        # on all three) — create+switch to a work branch rather than skipping, so the
        # delivery commit always lands somewhere durable and discoverable.
        today = datetime.date.today().isoformat()
        machine_slug = _resolve_machine_slug()
        candidate_branch = f"work/{machine_slug}/{today}"
        checkout_result = subprocess.run(
            ["git", "-C", receiver_path, "checkout", "-b", candidate_branch],
            capture_output=True,
            text=True,
        )
        if checkout_result.returncode != 0:
            # Daily-convention name collided or otherwise failed — fall back to a
            # clearly-named delivery branch rather than giving up on committing.
            fallback_branch = "work/cross-repo-memo-delivery"
            checkout_result = subprocess.run(
                ["git", "-C", receiver_path, "checkout", "-B", fallback_branch],
                capture_output=True,
                text=True,
            )
            if checkout_result.returncode != 0:
                print(
                    f"cross-repo-memo: WARNING — receiver repo at {receiver_path!r} has "
                    f"no current branch (detached HEAD, bare, or no commits yet), and "
                    f"creating a work branch failed ({checkout_result.stderr.strip()}) — "
                    f"delivered memo was written but left UNCOMMITTED.",
                    file=sys.stderr,
                )
                return None
            branch_name = fallback_branch
        else:
            branch_name = candidate_branch
        just_created = True
    else:
        ref = head_check.stdout.strip()
        branch_name = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref
        if branch_name in ("main", "master"):
            print(
                f"cross-repo-memo: WARNING — receiver repo is on '{branch_name}' — "
                f"committing the delivered memo there anyway; branch discipline is the "
                f"receiver's to resolve.",
                file=sys.stderr,
            )

    try:
        add_result = subprocess.run(
            ["git", "-C", receiver_path, "add", "--", memo_relpath],
            capture_output=True,
            text=True,
        )
        if add_result.returncode != 0:
            print(
                f"cross-repo-memo: WARNING — 'git add' of delivered memo failed in "
                f"receiver repo ({add_result.stderr.strip()}); file was written but "
                f"left uncommitted.",
                file=sys.stderr,
            )
            return None

        subject = f"cross-repo: deliver {title} memo from {sender}"
        commit_result = subprocess.run(
            [
                "git", "-C", receiver_path,
                "-c", "commit.gpgsign=false",  # GAP-6: neutralise repo/global signing config for this TTY-less invocation
                "commit", "-m", subject, "--", memo_relpath,
            ],
            capture_output=True,
            text=True,
        )
        if commit_result.returncode != 0:
            combined = (commit_result.stdout + commit_result.stderr).lower()
            if (
                "nothing to commit" in combined
                or "nothing added to commit" in combined
                or "no changes added to commit" in combined
            ):
                # Idempotent no-op — the memo path is already committed as-is.
                # All three phrasings are git's "nothing staged/changed" family:
                # "nothing to commit" (clean tree), "nothing added to commit"
                # (untracked only), and "no changes added to commit" (tracked-but-
                # unstaged, emitted when the tree has OTHER dirty files — routine
                # under concurrent-EM git). Missing the third let an already-
                # committed memo read as an uncommitted-delivery failure.
                return (branch_name, just_created)
            _unstage_delivered_memo()
            print(
                f"cross-repo-memo: WARNING — 'git commit' of delivered memo failed in "
                f"receiver repo ({(commit_result.stderr or commit_result.stdout).strip()}); "
                f"file was written but left uncommitted.",
                file=sys.stderr,
            )
            return None
    except OSError as exc:
        # add and commit are both inside this try — an exception could land
        # either before or after `git add` staged the path, so unstage
        # unconditionally (AC3); see _unstage_delivered_memo's no-op note.
        _unstage_delivered_memo()
        print(
            f"cross-repo-memo: WARNING — could not commit delivered memo in receiver "
            f"repo ({exc}); file was written but left uncommitted.",
            file=sys.stderr,
        )
        return None

    return (branch_name, just_created)


def _print_delivery_commit_notice(receiver_path: str, commit_outcome: "tuple[str, bool] | None") -> None:
    """Design-as-offers stdout notice for a successful delivery commit.

    Only prints when _commit_delivered_memo actually committed (commit_outcome
    is not None) — a WARNING-and-skip already explains itself on stderr, and
    printing a success notice on that path would misstate what happened.

    States plainly that this CLI just committed into ANOTHER repo's working
    tree — a deliberate, sanctioned small exception to "don't touch others'
    repos" — and why: the dirty-file delivery model's failure mode is
    fragility (an uncommitted memo can be lost, or simply never seen by an EM
    that doesn't happen to land a session on that device), not that the
    dirty-file model was wrong to try in the first place. Committing trades a
    small, well-scoped repo-boundary crossing (single file, single commit, no
    push) for durable cross-device/cross-session delivery.
    """
    if commit_outcome is None:
        return
    branch_name, just_created = commit_outcome
    created_note = " (created — receiver had no active branch)" if just_created else ""
    print(
        f"Committed into {receiver_path} on branch '{branch_name}'{created_note}."
    )
    print(
        "Note: committing into the receiver's repo is a deliberate, sanctioned "
        "exception to \"don't touch others' repos\" — done so this memo is "
        "reliably received across devices/sessions rather than left as a "
        "dirty file that depends on an EM organically noticing it."
    )


_VERIFY_HEAD_RETRY_ATTEMPTS = 3
_VERIFY_HEAD_RETRY_DELAY_SECONDS = 0.4


def _verify_delivery_landed(
    receiver_path: str,
    receiver_side_path: str,
    *,
    expected_sha: str | None = None,
) -> bool:
    """Prove the memo actually landed in the receiver's tree; print the verdict.

    The engine's success envelope is a CLAIM about a write into ANOTHER repo's
    working tree — a tree this process does not otherwise observe. Printing the
    path it claims to have written and stopping there leaves the sender to run
    the `ls` themselves, which is the transcription this surface exists to
    discharge (CLAUDE.md § north star, the discharge test). Two cheap oracles
    settle it here instead: the file is on disk, and git tracks it at a commit.

    Returns True when both oracles pass. A failure is loud on stderr; as of
    2026-08-04, an untracked read-back (on disk but not committed) ALSO makes
    the caller return exit code 2 — the non-fatal/degraded code, matching the
    in-repo precedent in coordinator_core/ops/ceremony/commit_pipeline.py's
    StageOutcome (exit_code == 2 for missing_caller_paths / ignored_caller_paths:
    "the work partly did not land"). The engine still owns the send's
    success/failure verdict (exit 0 vs 1) — this read-back only ever escalates
    a successful send to degraded, never turns it into a failure.

    `expected_sha` (2026-08-15, false-warning-on-proven-delivery fix): the
    receiver-side commit sha the engine's own `CommitOutcome.committed_sha`
    already resolved, pathspec-scoped, in the same synchronous call chain
    that performed the commit (coordinator_core/ops/fleet/memo_send.py) —
    i.e. BEFORE this process ever runs. A bare `HEAD:<path>` read here is a
    SEPARATE, LATER read of the same shared, concurrently-written receiver
    tree (doctrine: 50-70 concurrently active LLMs is this machine's norm),
    and can transiently miss a commit that unquestionably landed if some
    OTHER session's own commit interleaves in the read window — the exact
    "a receiver repo is a foreign, concurrently-written tree" hazard
    `CommitOutcome.committed_sha`'s own docstring names for the identical
    reason it resolves its sha the same way rather than off a blind HEAD
    read. Checking `<sha>:<path>` instead of `HEAD:<path>` is race-immune:
    once a commit object is written it is permanent (no `gc --prune` runs on
    this hot path), so its existence can never be un-done by a LATER,
    unrelated sibling commit moving HEAD — only a check anchored to HEAD can
    be fooled by that. When `expected_sha` is absent (the engine's own
    idempotent no-op arm reports `committed_sha=None`) or its check fails
    (a real mismatch, not a guess to paper over), this falls through to the
    HEAD-based oracle below, now with a bounded settle-retry rather than
    failing loud on a single read — the oracle must still catch a genuinely
    uncommitted delivery, so neither arm is weakened into never warning.
    """
    if not os.path.isfile(receiver_side_path):
        print(
            f"cross-repo-memo: WARNING — engine reported delivery but no file "
            f"exists at {receiver_side_path}. The memo did NOT land.",
            file=sys.stderr,
        )
        return False

    memo_relpath = os.path.relpath(receiver_side_path, receiver_path)
    # A git `HEAD:<path>` revspec addresses a path in a git TREE, and tree
    # paths are always forward-slash-separated on every platform — a
    # backslash is never a valid separator in that namespace. So converting
    # backslashes to forward slashes before building the revspec is
    # domain-correct everywhere, not a Windows special case: keying this on
    # os.sep (as a prior version of this fix did) made a property of git
    # conditional on a property of the host, which is the wrong axis. Hence
    # a hardcoded "\\" replace, not os.sep — this must run identically
    # regardless of which OS built receiver_side_path. Without it,
    # os.path.relpath's Windows-native output 100%-false-negatives every
    # send on Windows, and this oracle's own remediation text tells the
    # operator to duplicate-deliver via --supersedes. Theoretical cost: a
    # POSIX filename containing a literal backslash gets mangled — accepted,
    # since such a name can't be addressed through a HEAD: revspec anyway,
    # and block_illegal_filename keeps names like that out of this repo.
    memo_relpath_posix = memo_relpath.replace("\\", "/")

    # Sha-anchored fast path (race-immune — see docstring). `<sha>:<path>`
    # addresses a fixed, immutable commit object, never HEAD, so a sibling
    # session's own commit landing in this same window cannot affect the
    # answer either way.
    if expected_sha:
        sha_check = subprocess.run(
            ["git", "-C", receiver_path, "cat-file", "-e", f"{expected_sha}:{memo_relpath_posix}"],
            capture_output=True,
            text=True,
        )
        if sha_check.returncode == 0:
            branch = subprocess.run(
                ["git", "-C", receiver_path, "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
            )
            branch_name = (
                branch.stdout.strip() if branch.returncode == 0 and branch.stdout.strip() else "?"
            )
            print(
                f"Delivery verified: on disk and committed as {expected_sha[:7]} "
                f"on '{branch_name}' (engine-reported sha)."
            )
            return True
        # expected_sha given but doesn't check out for this path — do not
        # trust it blindly (a genuine failure must still be caught); fall
        # through to the HEAD-based oracle below.

    # AC1: read HEAD, not the index — `git ls-files --error-unmatch` passes
    # for a path that was `git add`ed and then failed to commit (it's still
    # in the index), which is exactly the false-positive state this oracle
    # exists to catch. `cat-file -e HEAD:<path>` only succeeds when the path
    # is actually present in the committed tree.
    #
    # Bounded settle-retry (2026-08-15): a blind HEAD read is the one part
    # of this oracle with no fixed-object anchor, so it is the part still
    # exposed to the concurrent-sibling-commit race the sha fast path above
    # exists to dodge. `_INDEX_LOCK_MAX_ATTEMPTS`-shaped bound (memo_send.py)
    # — a few short, capped attempts to let a genuinely in-flight sibling
    # write settle, never an unbounded poll — before reporting the
    # duplicate-delivery remediation, which must stay reserved for an
    # UNPROVEN negative, not a transient one.
    # `max(1, ...)` keeps the loop body reachable for any value the constant
    # could be edited to: at zero attempts the oracle would fall through to
    # the WARNING arm having never read HEAD at all, reporting a delivery
    # uncommitted on no evidence — the exact failure this retry was added to
    # stop.
    at_head = None
    for attempt in range(max(1, _VERIFY_HEAD_RETRY_ATTEMPTS)):
        at_head = subprocess.run(
            ["git", "-C", receiver_path, "cat-file", "-e", f"HEAD:{memo_relpath_posix}"],
            capture_output=True,
            text=True,
        )
        if at_head.returncode == 0:
            break
        if attempt < _VERIFY_HEAD_RETRY_ATTEMPTS - 1:
            _time.sleep(_VERIFY_HEAD_RETRY_DELAY_SECONDS)
    if at_head.returncode != 0:
        print(
            f"cross-repo-memo: WARNING — engine reported delivery but {memo_relpath_posix} "
            f"is not committed at HEAD in {receiver_path}. Re-send with "
            f"--supersedes {memo_relpath_posix}.",
            file=sys.stderr,
        )
        return False

    described = subprocess.run(
        ["git", "-C", receiver_path, "log", "-1", "--format=%h", "--", memo_relpath_posix],
        capture_output=True,
        text=True,
    )
    branch = subprocess.run(
        ["git", "-C", receiver_path, "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
    )
    # AC2: the "verified" line must never carry a blank SHA. `git log -1
    # --format=%h` for a path that IS at HEAD always exits 0, but keying the
    # fallback on returncode alone misses the case where stdout is empty for
    # some other reason (e.g. a shallow clone) — key on empty stdout too.
    described_sha = described.stdout.strip()
    sha = described_sha if described.returncode == 0 and described_sha else "?"
    branch_name = branch.stdout.strip() if branch.returncode == 0 and branch.stdout.strip() else "?"
    print(f"Delivery verified: on disk and committed as {sha} on '{branch_name}'.")
    return True


# kind values that assert something about the receiver's tree/work state
# ("they have/haven't done X", "a fix hasn't landed") and therefore carry a
# premise that's cheap to falsify BEFORE sending, given a resolved local
# clone. fyi/consult don't assert a receiver-state premise — advisory would
# be noise on those kinds.
_PREMISE_BEARING_KINDS = frozenset({"ask", "proposal"})


def _print_premise_check_advisory(
    receiver_em_id: str,
    receiver_path: str,
    kind: str | None,
    scoped_to: dict | None = None,
    *,
    stage: str = "send",
    outbox_path: str | None = None,
) -> None:
    """Check the memo's premise against the receiver's local clone, for
    premise-bearing kinds — performing the check where the memo pinned one.

    Two arms. A memo carrying `scoped_to` pinned something resolvable, so this
    RESOLVES it (_run_scoped_premise_checks) and prints a verdict. A memo with
    nothing pinned has no premise this process can address, so the offer is to
    pin it — not a description of a grep for the sender to go run.

    Lifecycle rule (2026-08-03, doe-claude-em memo — see
    cross-repo/inbox/2026-08-03-doe-claude-em-premise-check-advisory-fires-
    after-delivery.md): the advisory belongs to the stage that OWNS the
    editable buffer, not to send. `_cmd_draft` and `_cmd_compose` both hold
    `state/memo-outbox/<topic>.md` open for edits at the moment they call
    this — `stage="draft"`/`"compose"` — so a missing `scoped_to` there is
    still a live, takeable offer: add the keys (or re-run with
    --scoped-to-*) and the buffer is fixed before it ever ships. By the time
    `_cmd_send` calls this (`stage="send"`, the default), the memo has
    ALREADY been committed into the receiver's tree via
    `_verify_delivery_landed` — the unpinned arm can only describe what
    could have been pinned, so it prints as a receipt, not an offer. Send's
    call site is kept regardless: DoE explicitly wants a post-hoc "this went
    out unpinned" signal even when it's too late to act on, AND it is the
    ONLY reachable emission for the legacy one-shot flag form (`main()`'s
    flag-only send arm) that bypasses the outbox buffer entirely — draft/
    compose never see that path.

    That one-shot form gets its OWN receipt arm, `stage="send_oneshot"`
    (doe-claude-em memo, 2026-08-03): the pins ARE takeable on that form —
    the --scoped-to-* flags parse there and a complete triple short-circuits
    to `_run_scoped_premise_checks` above — so routing it to the generic
    send receipt advised re-running at `draft`/`compose`, a lifecycle that
    caller deliberately did not use. Same timing, correct remedy. Making it
    a genuine pre-write OFFER on that form would require BLOCKING the send
    (a non-blocking pre-write print is a receipt with extra steps, since
    the write follows immediately). PM ruling 2026-08-03: memo send is NOT
    to be blocked on a missing scoped_to, on any form. The advisory stays
    advisory at every stage — do not reintroduce a pre-flight gate here.

    Until 2026-07-29 the unpinned arm named the work and handed it back
    (describing a grep for the sender to run) — the transcription-relocation
    the discharge test rules out (CLAUDE.md § north star). Until this
    2026-08-03 fix, even the fixed wording only ever fired post-commit,
    which is the same defect one stage later: the remedy it names was no
    longer takeable by the time it printed.

    Fires only when kind is 'ask' or 'proposal' (None/absent defaults to
    'ask' per the reader-side convention documented at the kind frontmatter
    parse site — see _validate_outbox_frontmatter's kind handling) AND the
    receiver's clone resolved to a local path. fyi/consult are silently
    skipped: they don't assert a receiver-tree-state premise, and nagging on
    them is noise (offers-not-nags — CLAUDE.md § design-as-offers).

    Never blocks, never changes exit code, at any stage — advisory only.
    At `send`, this prints alongside (not instead of) the existing "Hand the
    PM this path for relay" stdout contract line, which callers must keep
    intact for programmatic capture. At `draft`/`compose`, EVERYTHING this
    function prints goes to stderr — both stages' stdout contracts are a
    single captured line (the draft/outbox absolute path) and must not
    gain a second line.

    Spec backlink: coordinator/docs/wiki/cross-repo-communication.md §
    Memo content is hypothesis.
    Spec backlink (scoped_to prompt + co-located-fleet note):
    docs/plans/2026-07-21-cross-repo-decision-scoping-and-peer-read-reconciliation.md § C3
    """
    effective_kind = kind if kind is not None else "ask"
    if effective_kind not in _PREMISE_BEARING_KINDS:
        return
    if not receiver_path:
        return
    # Review: code-reviewer — F3: absolutize to match the adjacent "Hand the
    # PM this path for relay" line's os.path.abspath normalization, so both
    # paths in the same stdout block are consistently absolute.
    abs_receiver_path = os.path.abspath(receiver_path)

    # draft/compose hold the outbox buffer open for edits when they call
    # this — their stdout contract is a single captured line, so every
    # emission here must land on stderr instead. `file=None` is print()'s
    # own sentinel for "current sys.stdout", so the send stage (the
    # default) is untouched.
    stream = sys.stderr if stage in ("draft", "compose") else None

    if scoped_to:
        _run_scoped_premise_checks(
            receiver_em_id, abs_receiver_path, effective_kind, scoped_to, file=stream
        )
        return

    if stage in ("draft", "compose"):
        location = outbox_path or "the outbox draft"
        print(
            f"Premise check ({effective_kind}): {receiver_em_id}'s clone is local at "
            f"{abs_receiver_path}, but this memo pins nothing checkable yet. Add "
            f"scoped_to_artifact plus scoped_to_sha (or scoped_to_version) and "
            f"scoped_to_seam to {location} now, or re-run `draft`/`compose` with "
            f"--scoped-to-artifact/--scoped-to-sha/--scoped-to-seam — `send` will "
            f"then verify the pin against {receiver_em_id}'s clone for you.",
            file=stream,
        )
    elif stage == "send_oneshot":
        print(
            f"Premise check ({effective_kind}): {receiver_em_id}'s clone is local at "
            f"{abs_receiver_path}, and this memo shipped with nothing pinned. Too "
            f"late to pin THIS one — this is a receipt, not an offer — but this "
            f"form takes the pin on the invocation itself: add "
            f"--scoped-to-artifact plus --scoped-to-sha (or --scoped-to-version) "
            f"and --scoped-to-seam to the next one-shot send and it will be "
            f"verified against {receiver_em_id}'s clone.",
            file=stream,
        )
    else:
        print(
            f"Premise check ({effective_kind}): {receiver_em_id}'s clone is local at "
            f"{abs_receiver_path}, and this memo shipped with nothing pinned. Too "
            f"late to pin THIS one — this is a receipt, not an offer — but "
            f"--scoped-to-artifact plus --scoped-to-sha (or --scoped-to-version) "
            f"and --scoped-to-seam are still takeable at `draft`/`compose` time on "
            f"the next one, while the outbox buffer is still editable.",
            file=stream,
        )
    print(
        "See coordinator/docs/wiki/cross-repo-communication.md § Memo content is hypothesis.",
        file=stream,
    )


# Environment variables that scope git to a repository. `git -C <path>` changes
# only the process working directory — every one of these still WINS over
# directory-based discovery, so a `git -C <receiver>` probe run by a process that
# inherited them silently resolves against the SENDER's repo (or against no repo
# at all). git exports GIT_DIR to every hook it runs, commonly as the relative
# ".", so any invocation downstream of a hook inherits it. Stripped before every
# receiver-side probe below.
_GIT_REPO_SCOPING_ENV = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_NAMESPACE",
    "GIT_CEILING_DIRECTORIES",
    "GIT_DISCOVERY_ACROSS_FILESYSTEM",
)

# Tri-state verdict for one premise probe. The middle and the last are DIFFERENT
# claims and must never render as the same sentence: NO asserts the receiver
# cannot resolve the pin, UNKNOWN asserts only that this process failed to find
# out.
_PREMISE_YES = "yes"
_PREMISE_NO = "no"
_PREMISE_UNKNOWN = "unknown"


def _receiver_git_env() -> dict:
    """Return os.environ minus every repo-scoping git variable.

    See _GIT_REPO_SCOPING_ENV — without this, `git -C <receiver>` is not
    actually scoped to the receiver.
    """
    return {k: v for k, v in os.environ.items() if k not in _GIT_REPO_SCOPING_ENV}


def _first_line(text: str) -> str:
    """First non-empty line of git's stderr, for embedding in a one-line verdict."""
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _receiver_repo_unusable_reason(abs_receiver_path: str) -> str | None:
    """Return None when abs_receiver_path is usable as a git repo, else why not.

    Runs BEFORE any premise probe so that "the receiver path is not a git repo",
    "the path does not exist", "git is not installed", and "discovery landed on
    somebody else's repo" are all reported as *could not check* rather than
    silently becoming an absence claim about the receiver's objects.

    The git-dir confinement check is the part that catches a poisoned
    environment: with GIT_DIR inherited, `git -C <receiver> rev-parse` exits 0
    and happily answers questions about the WRONG repo. Comparing the resolved
    git dir against the receiver's own tree is what makes that detectable.
    """
    try:
        probe = subprocess.run(
            ["git", "-C", abs_receiver_path, "rev-parse", "--absolute-git-dir"],
            capture_output=True,
            text=True,
            env=_receiver_git_env(),
        )
    except OSError as exc:
        return f"could not run git: {exc}"
    if probe.returncode != 0:
        return _first_line(probe.stderr) or f"git rev-parse exited {probe.returncode}"
    git_dir = probe.stdout.strip()
    if not git_dir:
        return "git reported no git directory for this path"
    try:
        real_git_dir = os.path.realpath(git_dir)
        real_receiver = os.path.realpath(abs_receiver_path)
        inside = os.path.commonpath([real_git_dir, real_receiver]) == real_receiver
    except (OSError, ValueError) as exc:
        return f"could not confirm {git_dir} belongs to this path: {exc}"
    if not inside:
        return (
            f"git resolved this path to {git_dir}, which is outside the "
            f"receiver's tree — the probe would answer about the wrong repo"
        )
    return None


def _git_premise_probe(abs_receiver_path: str, args: list) -> "tuple[str, str]":
    """Run one receiver-scoped git predicate and map its exit code to a tri-state.

    git's convention for the predicates used here (`rev-parse --verify --quiet`,
    `merge-base --is-ancestor`) is 0 = true, 1 = false, anything else = the
    question could not be answered at all. Collapsing that third code into the
    second is the 2026-08-03 defect this function exists to prevent: a genuinely
    dangling sha and a probe that never reached the receiver's object database
    rendered as the identical "NOT in their clone" sentence, which laundered a
    real finding into noise.

    Returns (verdict, reason) — reason is non-empty only for _PREMISE_UNKNOWN.
    """
    try:
        probe = subprocess.run(
            ["git", "-C", abs_receiver_path] + list(args),
            capture_output=True,
            text=True,
            env=_receiver_git_env(),
        )
    except OSError as exc:
        return _PREMISE_UNKNOWN, f"could not run git: {exc}"
    if probe.returncode == 0:
        return _PREMISE_YES, ""
    if probe.returncode == 1:
        return _PREMISE_NO, ""
    return _PREMISE_UNKNOWN, _first_line(probe.stderr) or f"git exited {probe.returncode}"


_ARTIFACT_LINE_PIN_RE = re.compile(r":(\d+)(?:-(\d+))?$")


def _split_artifact_line_pin(artifact: str) -> "tuple[str, str]":
    """Split a `path:line` / `path:start-end` citation into (path, pin).

    A memo that pins its premise at a line range — `…/scoped-safety-commits.md:98-103`
    — cites a real file, and the whole point of that pin is to be more precise than
    a bare filename. Resolving the pinned string as a literal filename makes both
    oracles below miss (`HEAD:<path>:98-103` is not a pathspec git can resolve, and
    no such file exists on disk), so the most carefully-cited memos in the corpus
    were the ones reported as NOT FOUND. A receiver who trusts that line would
    distrust a sound memo.

    Only a numeric suffix is treated as a pin: a colon inside an actual filename
    survives untouched, and the returned `pin` is re-attached to every printed
    label so the operator still sees the citation they wrote.
    """
    match = _ARTIFACT_LINE_PIN_RE.search(artifact)
    if not match:
        return artifact, ""
    return artifact[: match.start()], match.group(0)


def _run_scoped_premise_checks(
    receiver_em_id: str,
    abs_receiver_path: str,
    effective_kind: str,
    scoped_to: dict,
    *,
    file=None,
) -> None:
    """Verify a pinned `scoped_to` premise against the receiver's clone.

    The advisory this replaces described a grep for the sender to run — it
    relocated the check rather than discharging it. Where the memo pins its
    premise, the sender's process can resolve it directly: the receiver's clone
    is local, so artifact presence and sha reachability are two subprocess calls
    away. `version` stays unresolvable (no general oracle for "which version is
    this tree at"), and is reported as pinned-but-unverifiable rather than
    silently dropped.

    Every resolvable field reports one of THREE outcomes, never two: it
    resolves, it definitively does not resolve, or it could not be checked. The
    third prints as its own sentence, explicitly disclaimed as not being an
    absence claim — see `_git_premise_probe` for the incident that makes
    conflating the last two a correctness defect rather than a wording nit.

    `file` mirrors `print()`'s own parameter (None = current sys.stdout) —
    threaded through by `_print_premise_check_advisory` so the draft/compose
    stages, whose stdout contract is a single captured line, land every one
    of these lines on stderr instead. send keeps the prior stdout behavior.

    Advisory throughout — never blocks, never changes the exit code.
    """
    artifact = (scoped_to.get("artifact") or "").strip()
    sha = (scoped_to.get("sha") or "").strip()
    version = (scoped_to.get("version") or "").strip()
    seam = (scoped_to.get("seam") or "").strip()

    print(
        f"Premise check ({effective_kind}): resolved against {receiver_em_id}'s "
        f"clone at {abs_receiver_path} —",
        file=file,
    )

    repo_unusable = _receiver_repo_unusable_reason(abs_receiver_path)
    if repo_unusable and (artifact or sha):
        print(
            f"  COULD NOT CHECK this receiver's git state — {repo_unusable}. "
            f"Nothing below about artifact/sha is a claim that they are missing.",
            file=file,
        )

    def probe(args: list) -> "tuple[str, str]":
        """One premise probe, short-circuited to UNKNOWN when the repo is unusable."""
        if repo_unusable:
            return _PREMISE_UNKNOWN, repo_unusable
        return _git_premise_probe(abs_receiver_path, args)

    if artifact:
        artifact_path, line_pin = _split_artifact_line_pin(artifact)
        # Review: coordinator:code-reviewer 9266869a finding 2 — same defect
        # class as _verify_delivery_landed's HEAD: revspec bug (this commit's
        # fix target), arriving via a different route: `artifact` is
        # author-typed, not os.path.relpath output, so a Windows author who
        # pastes an Explorer/PowerShell citation (backslash-separated) gets a
        # false "NOT FOUND" premise verdict on any receiver, POSIX included.
        # A backslash cannot legitimately appear in a tracked repo-relative
        # path on either OS (Windows forbids it as a path component itself,
        # POSIX repos sourced from Windows authors are the failure mode this
        # exists to catch), so the blanket replace is safe. Advisory-only —
        # never blocks, never changes exit code — hence normalized here
        # rather than restructuring the probe helper.
        artifact_path = artifact_path.replace("\\", "/")
        at_head, why = probe(["rev-parse", "--verify", "--quiet", f"HEAD:{artifact_path}"])
        if at_head == _PREMISE_UNKNOWN:
            print(
                f"  artifact {artifact}: COULD NOT CHECK ({why}) — this is not a "
                f"claim the artifact is absent.",
                file=file,
            )
        elif at_head == _PREMISE_YES:
            pinned = f" (line pin {line_pin.lstrip(':')} not verified)" if line_pin else ""
            print(f"  artifact {artifact}: present at their HEAD{pinned}.", file=file)
        elif os.path.exists(os.path.join(abs_receiver_path, artifact_path)):
            print(f"  artifact {artifact}: on disk but NOT at their HEAD (uncommitted).", file=file)
        else:
            print(
                f"  artifact {artifact}: NOT FOUND in their tree — if the memo "
                f"asserts anything about this file, the premise is already stale.",
                file=file,
            )

    if sha:
        resolves, why = probe(["rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}"])
        if resolves == _PREMISE_UNKNOWN:
            print(
                f"  sha {sha}: COULD NOT CHECK ({why}) — this is not a claim the "
                f"sha is missing from their clone.",
                file=file,
            )
        elif resolves == _PREMISE_NO:
            print(f"  sha {sha}: NOT in their clone — they cannot resolve this pin.", file=file)
        else:
            merged, merged_why = probe(["merge-base", "--is-ancestor", sha, "HEAD"])
            if merged == _PREMISE_UNKNOWN:
                where = (
                    f"present, but COULD NOT CHECK whether it is in their HEAD "
                    f"({merged_why})"
                )
            elif merged == _PREMISE_YES:
                where = "in their HEAD"
            else:
                where = "present but NOT in their HEAD"
            print(f"  sha {sha}: {where}.", file=file)

    if seam:
        print(f"  seam {seam}: pinned (no automated oracle — reader-side context).", file=file)

    if version:
        print(f"  version {version}: pinned (no automated oracle — reader-side context).", file=file)


# ---------------------------------------------------------------------------
# Outbox draft helpers
# ---------------------------------------------------------------------------

_OUTBOX_REQUIRED_FIELDS = ("title", "from", "to", "created", "status", "delivery_mode", "summary")

# Mirrors the canonical `kind` enum in coordinator/bin/lib/schema.js:2131
# (validKinds) — the receiver-side cross-field rule. Checked here too so a
# malformed kind fails loud on the SENDER side, before delivery, instead of
# jamming the receiver's lifecycle wrappers at stamp time.
_VALID_KINDS = ("ask", "consult", "fyi", "proposal")

# scoped_to sub-field keys, flattened for this CLI's internal representation
# (scoped_to_artifact / scoped_to_version / scoped_to_sha / scoped_to_seam) —
# `_parse_outbox_file` accepts BOTH the flat `scoped_to_artifact: "..."`
# top-level-key shape (hand-edited drafts, this CLI's own pre-2026-07-21
# emission) AND claude-klabauter's `memo.draft` op's nested `scoped_to:` mapping shape
# (schema.js's shape), normalizing either into these same flat keys on read —
# see `_parse_outbox_file`'s docstring for the round-trip fix (2026-07-21).
# The --scoped-to-* CLI flags emit/consume this flattened shape too.
_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")


# CANONICAL SOURCE OF TRUTH: coordinator/bin/lib/schema.js:2290 (the
# scoped_to presence-triggered-completeness check) and claude-klabauter's
# coordinator_core/ops/fleet/memo_send.py. All three implementations must
# stay legibly identical — this function mirrors the other two CLI-side, same
# direction/idiom as the _VALID_KINDS mirror above, so a malformed scoped_to
# fails loud on the SENDER side, before delivery, instead of only surfacing
# when the receiver validates the inbox copy. schema.js is authoritative;
# this is the copy — keep all three in sync on any future change to the
# scoped_to shape.
def _scoped_to_errors(kind: str | None, scoped_to: dict[str, str | None] | None) -> list[str]:
    """Validate scoped_to under presence-triggered completeness.

    Rule (2026-07-21, replaces the retired ask/proposal-requires-scoped_to
    gate): scoped_to is OPTIONAL for every kind, with no exception — a
    directional/doctrine ask with no point-in-time pin to declare simply
    omits scoped_to and passes. If ANY sub-key is supplied, the COMPLETE
    triple is required regardless of kind: 'artifact' (non-empty str),
    exactly one of 'version' (non-empty str) or 'sha' (7-40 hex str), and
    'seam' (non-empty str) — else fail loud. This mirrors claude-klabauter's
    memo_send.py and DoE's schema.js:2290 exactly; do not reintroduce a
    kind-based gate here — the old "required when kind=ask/proposal" rule
    was the actual source of sender friction being fixed (see
    cross-repo/inbox/2026-07-21-claude-klabauter-em-scoped-to-engine-fixed-gate-is-yours.md).

    The `kind` parameter is retained (unused) only to avoid a call-site
    churn across every invocation site in this file; the presence-triggered
    rule no longer varies by kind. A future cleanup pass may drop it and
    update all call sites in one motion.

    Returns a list of error strings; empty list = valid (or exempt because
    scoped_to was omitted entirely).
    """
    scoped_to = scoped_to or {}
    artifact = (scoped_to.get("artifact") or "").strip()
    seam = (scoped_to.get("seam") or "").strip()
    version = (scoped_to.get("version") or "").strip()
    sha = (scoped_to.get("sha") or "").strip()
    has_version = bool(version)
    has_sha = bool(sha)
    if not (artifact or seam or has_version or has_sha):
        # scoped_to entirely absent/blank — optional for every kind, no error.
        return []
    sha_well_formed = has_sha and bool(_SHA_RE.match(sha))
    problems = []
    if not artifact:
        problems.append("artifact (non-empty string naming the governed surface)")
    if has_version == has_sha:
        problems.append(
            "exactly one of version or sha (currently "
            + ("both set" if has_version and has_sha else "neither set")
            + ")"
        )
    elif has_sha and not sha_well_formed:
        problems.append("sha (must be 7-40 hex chars)")
    if not seam:
        problems.append("seam (non-empty string naming the boundary this pin governs)")
    if not problems:
        return []
    return [
        "scoped_to is incomplete — when any of artifact/version/sha/seam is "
        "set, all of scoped_to_artifact, exactly one of "
        "scoped_to_version/scoped_to_sha, and scoped_to_seam are required. "
        f"Problems found: {'; '.join(problems)}."
    ]


def _build_scoped_to(
    artifact: str | None,
    version: str | None,
    sha: str | None,
    seam: str | None,
) -> dict[str, str] | None:
    """Assemble the nested scoped_to dict claude-klabauter's memo.send op expects.

    Spec backlink: docs/plans/2026-07-21-cross-repo-decision-scoping-and-peer-read-reconciliation.md § C3b

    Takes the CLI's flat scoped_to_artifact/scoped_to_version/scoped_to_sha/
    scoped_to_seam values (whether sourced from outbox frontmatter or
    --scoped-to-* flags) and produces the nested {artifact, version|sha, seam}
    shape _scoped_to_errors validates and claude-klabauter's memo.send op composes into
    receiver-side frontmatter (claude-klabauter bcc7cdbe). Sub-keys absent/blank
    are OMITTED, never included as None — claude-klabauter fails loud on unknown
    scoped_to sub-keys, so a present-but-empty key would misrepresent intent.
    Returns None when no scoped_to fields are set at all.
    """
    result: dict[str, str] = {}
    if artifact:
        result["artifact"] = artifact
    if version:
        result["version"] = version
    if sha:
        result["sha"] = sha
    if seam:
        result["seam"] = seam
    return result or None


def _validate_outbox_frontmatter(fm: dict) -> list[str]:
    """CLI-local validator for outbox draft frontmatter.

    Spec backlink: docs/plans/2026-06-15-cross-repo-memo-draft-lifecycle.md § C1
    2026-08-07 extraction: docs/plans/2026-06-15-cross-repo-memo-draft-lifecycle.md
    (the rule set itself now lives in
    coordinator_core.ops.fleet._outbox_frontmatter_rules.validate_outbox_frontmatter
    — SINGLE SOURCE OF TRUTH shared with
    coordinator_core.write_guards.nudge_outbox_draft_frontmatter_shape, the
    write-time advisory guard that catches the same defect at authoring time
    instead of only at `send`. This wrapper's signature/name/call site are
    unchanged; only the body now delegates.)

    Accepts status == "draft" and validates the required sender-side fields.
    This is intentionally separate from schemas/cross-repo-memo.yaml — the inbox
    schema's applies_to glob fires only on cross-repo/inbox/*.md paths; outbox
    files at state/memo-outbox/*.md are a different lifecycle and must NOT extend
    the inbox schema (would couple two separate lifecycles without runtime benefit).

    summary is allowed to be present-but-empty at draft time (user fills in body
    later via `compose`); only its KEY must be present. All other required fields
    must be present and non-empty.

    `_cmd_send` normalizes a hand-authored `status: open` to `draft` BEFORE
    calling this function (see its own docstring) — this function's status
    check itself is UNCHANGED (still requires exactly `draft`), so its error
    strings/exit codes are unaffected; the normalization is upstream of it.

    Returns a list of error strings; empty list = valid.
    """
    cc_invoke.ensure_engine_on_path(__file__)
    from coordinator_core.ops.fleet._outbox_frontmatter_rules import (
        validate_outbox_frontmatter as _shared_validate_outbox_frontmatter,
    )
    return _shared_validate_outbox_frontmatter(fm)


# _compose_outbox_frontmatter DELETED 2026-07-21 (A8 strangler cutover, verb
# #5 `draft`) — its sole caller, `_cmd_draft`, no longer composes draft
# frontmatter CLI-side; claude-klabauter's `memo.draft` op now owns that composition
# (coordinator_core.ops.fleet.memo_draft.compose_draft_frontmatter, which
# renders `scoped_to` as a REAL nested YAML mapping via `_render_extra_field`
# rather than this function's flat `scoped_to_artifact`/`scoped_to_version`/
# `scoped_to_sha`/`scoped_to_seam` keys — an intentional shape change, not a
# byte-identical port). Confirmed zero remaining callers via
# `grep -n "_compose_outbox_frontmatter("` before deletion.


def _print_route_mutation_failure_reasons(exc: BaseException) -> None:
    """Print per-item engine 'reason' strings from a RouteMutationError, if any.

    `cc_invoke.route_mutation` raises `RouteMutationError` (a `RuntimeError`
    subclass carrying a `.result` dict) on any non-zero `exit_code`; the bare
    `str(exc)` rendering — e.g. "route_mutation: op='memo.draft' refused
    (exit_code=2, failed=1)" — names only a count, swallowing the engine's
    actual, useful per-item reason text (e.g. memo_send.py's
    `{"reason": "collision: ..."}` shape) that would tell the user WHY and
    what to do next. Call this immediately after printing `str(exc)` in every
    `except RuntimeError as exc:` handler around a `route_mutation()` call, to
    surface those reasons in addition to the bare message.

    Fully defensive — never raises. `exc.result` may be absent (the
    seam-absent/transport-failure `legacy_*()` stubs raise a bare
    `RuntimeError` with no `.result`), may not be a dict, `failed` may be
    missing/empty/not-a-list, and entries may lack a `reason` key.

    Fallback: a well-formed refusal envelope (e.g. `_setup_error()`'s
    exit_code:1/failed:[] shape) has nothing in `failed[]` to iterate — the
    engine's own diagnostic sentence lives on the child process's stderr
    instead, plumbed through by `cc_invoke.route_mutation` onto `exc.op_stderr`.
    When the `failed[]` loop above prints nothing, fall back to that text so
    the refusal is never silently swallowed.

    Anti-double-print: `route_mutation` ALSO appends `op_stderr` onto the
    raised message itself (so a bare `str(exc)` is self-diagnosing for any
    caller that never calls this printer). Every caller in this file prints
    `str(exc)` before calling this function, so a naive unconditional fallback
    print would duplicate that same text underneath it. Guarded by a
    containment check: only print the fallback when `op_stderr` is NOT already
    a substring of `str(exc)` — i.e. only when this exception reached us via a
    path that didn't fold it into the message (defensive; today's
    `route_mutation` always folds it in when non-empty, so this is belt-and-
    suspenders against a future caller constructing `RouteMutationError`
    directly with a bare message).
    """
    result_obj = getattr(exc, "result", None)
    failed_items = result_obj.get("failed") if isinstance(result_obj, dict) else None
    printed_any = False
    if isinstance(failed_items, list):
        for item in failed_items:
            reason = item.get("reason") if isinstance(item, dict) else None
            if reason:
                print(f"  reason: {reason}", file=sys.stderr)
                printed_any = True
    if not printed_any:
        op_stderr = getattr(exc, "op_stderr", "")
        op_stderr_stripped = op_stderr.strip() if isinstance(op_stderr, str) else ""
        if op_stderr_stripped and op_stderr_stripped not in str(exc):
            print(f"  op stderr: {op_stderr_stripped}", file=sys.stderr)


def _cmd_draft(args: argparse.Namespace) -> int:
    """Handle: cross-repo-memo draft <topic> --to <em> --title <line> [--summary] [--kind] [--in-reply-to]

    A8 strangler cutover: thin invoke-and-render trampoline onto claude-klabauter's
    `memo.draft` op (dry_run:false, classify_receiver:true) — the engine owns
    receiver classification (reusing memo.send's resolver authority) AND the
    O_EXCL draft-file creation; the CLI only validates the topic slug,
    resolves the sender repo root, and renders the op's result.

    Spec backlink: docs/plans/2026-06-15-cross-repo-memo-draft-lifecycle.md § C1
                   /private/tmp/.../scratchpad/six-verb-cutover-map.md § #5 draft

    Exit-code split restored on the wire (claude-klabauter commit a5003f50): the op's
    classification-rejection envelope carries a `rejection_class` field that
    the handler below maps to a discriminated exit code —
    publish_target_rejected->1, unknown_receiver->2, registry_error->3,
    ambiguous_receiver->3 — falling back to exit 1 on a missing/unrecognized
    rejection_class (including seam-absent/transport failure, which never
    reaches classification). See the inline comment at the `rejection_class`
    read below for the full mapping and rationale.
    """
    topic = args.topic
    to = args.to
    title = args.title

    # Validate topic slug (reuse existing guard — path traversal prevention).
    if not _TOPIC_SLUG_RE.fullmatch(topic):
        print(
            f"cross-repo-memo draft: invalid topic {topic!r}; must match "
            f"lowercase-alphanum + dashes, start with alphanum (e.g. 'my-topic').",
            file=sys.stderr,
        )
        return 2

    # Resolve sender repo root (cwd's git root — NOT a hardcoded path).
    sender_root = _current_repo_root()
    if sender_root is None:
        guard_error = _guard_sender_identity_before_delivery()
        # guard_error is non-None here by construction (sender_root is None ⟺
        # _current_repo_root() is None ⟺ the guard fires) — asserted, not
        # re-derived, so the message is the single canonical wording.
        print(guard_error or "cross-repo-memo draft: cwd is not a git working tree.", file=sys.stderr)
        return 2
    _warn_if_unregistered_sender()

    # scoped_to: presence-triggered — only threaded when at least one of the
    # four sub-keys is supplied; the op enforces the complete-triple rule
    # (artifact + exactly one of version|sha + seam) itself, so the CLI just
    # forwards whatever non-None sub-keys exist rather than re-validating.
    scoped_to_raw = {
        "artifact": getattr(args, "scoped_to_artifact", None),
        "version": getattr(args, "scoped_to_version", None),
        "sha": getattr(args, "scoped_to_sha", None),
        "seam": getattr(args, "scoped_to_seam", None),
    }
    scoped_to = {k: v for k, v in scoped_to_raw.items() if v} or None

    invoke_params = {
        "dry_run": False,
        "topic": topic,
        "to": to,
        "title": title,
        "summary": getattr(args, "summary", None),
        "kind": getattr(args, "kind", None),
        "classify_receiver": True,
        # Root-cause fix (2026-07-21, state/bug-backlog/2026-07-21-cross-repo-memo-
        # draft-stamps-wrong-sende-d8f5a7c8d003.yaml): without an explicit
        # from_id, memo_draft.py's op falls back to its own internal
        # _ENGINE_ACTOR_ID ("claude-klabauter-engine") — the same divergence
        # `_send_via_engine` already avoids by passing `"from_id": sender`
        # (built from `_sender_em_id()`, the SAME self-resolution
        # `--check-addressee` uses). Mirror that here so draft and send (and
        # --check-addressee) can never disagree on this repo's own identity.
        "from_id": _sender_em_id(),
    }
    if scoped_to:
        invoke_params["scoped_to"] = scoped_to

    in_reply_to = getattr(args, "in_reply_to", None)
    if in_reply_to:
        invoke_params["in_reply_to"] = in_reply_to

    def legacy_draft() -> None:
        """Fail-loud legacy stub — mirrors _send_via_engine.legacy_send.

        A working direct-compute fallback here would silently defeat the
        claude-klabauter-engine integrity cut; this stub only ever raises, so
        State-1 (seam absent), State-2 transport failure, and State-2
        op-refusal all converge on the same `except RuntimeError` handler
        below.
        """
        raise RuntimeError(
            "claude-klabauter engine seam not found (CLAUDE_KLABAUTER_ROOT unresolvable or "
            "coordinator_core.invoke not importable) — the direct-write "
            "fallback has been retired. Install/configure the claude-klabauter "
            "engine to draft cross-repo memos."
        )

    try:
        result = cc_invoke.route_mutation("memo.draft", invoke_params, sender_root, legacy_draft)
    except RuntimeError as exc:
        # route_mutation raises RouteMutationError (a RuntimeError subclass
        # with a `.result` attribute) on ANY non-zero exit_code — both the
        # collision failed-envelope (exit_code:2) and every classify/setup
        # rejection land here. Collision keeps DoE's historical exit 2
        # (checked first, unaffected by rejection_class). For every other
        # rejection, the op's classification-rejection envelope carries a
        # `rejection_class` field (claude-klabauter commit a5003f50) that we map to a
        # distinct exit code so the caller can discriminate failure modes:
        #   publish_target_rejected -> 1
        #   unknown_receiver        -> 2
        #   registry_error          -> 3
        #   ambiguous_receiver      -> 3 (same resolution-failure class as
        #                                 registry_error for exit purposes)
        # A missing or unrecognized rejection_class (including seam-absent /
        # transport failure, which never reaches classification) falls back
        # to the prior coarse behavior: exit 1.
        result_obj = getattr(exc, "result", None)
        op_exit_code = result_obj.get("exit_code") if isinstance(result_obj, dict) else None
        rejection_class = (
            result_obj.get("rejection_class") if isinstance(result_obj, dict) else None
        )
        print(f"cross-repo-memo draft: {exc}", file=sys.stderr)
        _print_route_mutation_failure_reasons(exc)
        if op_exit_code == 2:
            # Collision refusal — the engine's own reason text (surfaced
            # above via `_print_route_mutation_failure_reasons`) already
            # names `memo.compose`; add the CLI-facing verb form of both
            # remedies explicitly, matching the existing compose/discard
            # hint convention used by `_cmd_send`'s malformed-frontmatter path.
            print(
                f"Use `cross-repo-memo compose {topic}` to edit the existing "
                f"draft, or `cross-repo-memo discard {topic}` to remove it "
                f"and start over.",
                file=sys.stderr,
            )
            return 2
        rejection_exit_codes = {
            "publish_target_rejected": 1,
            "unknown_receiver": 2,
            "registry_error": 3,
            "ambiguous_receiver": 3,
        }
        return rejection_exit_codes.get(rejection_class, 1)

    acted = result.get("acted") if isinstance(result, dict) else None
    if not (isinstance(result, dict) and result.get("exit_code") == 0 and acted):
        print(
            "cross-repo-memo draft: claude-klabauter reported success but returned no "
            "written draft (empty 'acted') — aborting.",
            file=sys.stderr,
        )
        return 1

    draft_path = acted[0].get("id") if isinstance(acted[0], dict) else None
    if not draft_path:
        print(
            "cross-repo-memo draft: claude-klabauter reported success but the written "
            "entry is malformed (missing 'id') — aborting.",
            file=sys.stderr,
        )
        return 1

    # 2026-07-24 papercut fix: memo.draft's classify_receiver:true path
    # auto-accepts an UNAMBIGUOUS "did you mean?" match (e.g. 'claude-klabauter-em' ->
    # 'claude-klabauter-em') rather than hard-failing — see memo_draft.py's
    # _classify_receiver_for_draft. The acted envelope's `to` then carries
    # the RESOLVED id, which may differ from the literal `--to` this CLI
    # sent; surface that substitution to the operator on stderr so it is
    # never a silent rewrite.
    acted_to = acted[0].get("to") if isinstance(acted[0], dict) else None
    if isinstance(acted_to, str) and acted_to != args.to:
        print(f"cross-repo-memo draft: resolved {args.to!r} -> {acted_to!r}", file=sys.stderr)

    # Premise-check advisory at the stage that OWNS the editable buffer — see
    # _print_premise_check_advisory's docstring (lifecycle rule, 2026-08-03).
    # Resolve against the RESOLVED receiver id (acted_to when the "did you
    # mean?" substitution above fired, else the literal args.to — same
    # substitution already surfaced to stderr two lines up). stderr only:
    # this function's own stdout contract is exactly one line below.
    resolved_to = acted_to if isinstance(acted_to, str) else args.to
    advisory_receiver_path, _ = _resolve_receiver_path(resolved_to)
    _print_premise_check_advisory(
        resolved_to,
        advisory_receiver_path or "",
        getattr(args, "kind", None),
        scoped_to,
        stage="draft",
        outbox_path=draft_path,
    )

    # Print absolute path to stdout (the op's `id` is already the absolute
    # target_path — see memo_draft.py's build_act_result acted entry).
    print(draft_path)
    return 0


def _unquote_yaml_scalar(v: str) -> str:
    """Strip outer quotes and unescape backslash sequences from a scalar value.

    Shared by `_parse_outbox_file`'s flat-key and nested `scoped_to:` parsing —
    both need the identical quoted/unquoted handling so a value round-trips the
    same way regardless of which shape carried it.
    """
    if not v.startswith('"'):
        return v
    raw = v[1:]
    chars: list[str] = []
    j = 0
    while j < len(raw):
        c = raw[j]
        if c == '\\' and j + 1 < len(raw):
            nc = raw[j + 1]
            if nc == '"':
                chars.append('"')
            elif nc == '\\':
                chars.append('\\')
            elif nc == 'n':
                chars.append('\n')
            elif nc == 'r':
                # Review: code-reviewer — _yaml_quote emits \r but parser did not handle it
                chars.append('\r')
            elif nc == 't':
                chars.append('\t')
            else:
                chars.append(nc)
            j += 2
            continue
        if c == '"':
            break
        chars.append(c)
        j += 1
    return ''.join(chars)


# scoped_to sub-field keys accepted inside a nested `scoped_to:` mapping —
# flattened to fm["scoped_to_<subkey>"] on read so downstream code
# (_scoped_to_errors, _validate_outbox_frontmatter, the send params) needs no
# change; see _parse_outbox_file's docstring for the two accepted shapes.
_SCOPED_TO_SUBKEYS = ("artifact", "version", "sha", "seam")


def _parse_outbox_file(path: str) -> tuple[dict[str, str], str]:
    """Parse an outbox draft file into (frontmatter_dict, body_str).

    Spec backlink: docs/plans/2026-06-15-cross-repo-memo-draft-lifecycle.md § C2
    Spec backlink (nested scoped_to support): docs/plans/2026-07-21-cross-repo-decision-scoping-and-peer-read-reconciliation.md § C3b

    Minimal YAML parser — handles simple key: "value" and key: value lines within
    --- delimiters. Returns the frontmatter dict and the body text (after the closing
    --- delimiter). Both raw string values and quoted string values are supported.

    scoped_to is accepted in TWO shapes and normalized to the same flat
    scoped_to_artifact/scoped_to_version/scoped_to_sha/scoped_to_seam keys
    either way:
      1. Flat top-level keys (`scoped_to_artifact: "..."`, etc.) — the
         hand-edited-draft shape and this CLI's own pre-2026-07-21 emission.
      2. A nested `scoped_to:` mapping (`scoped_to:` with no inline value,
         followed by indented `artifact:`/`version:`/`sha:`/`seam:` lines) —
         the shape claude-klabauter's memo.draft op now composes
         (coordinator_core.ops.fleet.memo_draft.compose_draft_frontmatter,
         via `_render_extra_field`). Prior to this fix, this parser handled
         ONLY the flat shape, so a nested scoped_to silently vanished on
         draft -> send (confirmed by
         test_cross_repo_memo_draft.py::test_scoped_to_round_trips_via_draft_flags).
      If both shapes are present in one file, the nested mapping wins for any
      sub-key it sets (it is what the engine now writes); this never crashes.

    Returns ({}, "") on parse failure (empty frontmatter signals invalid file to caller).
    """
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return {}, ""

    lines = content.splitlines()
    fm: dict[str, str] = {}
    nested_scoped_to: dict[str, str] = {}
    in_fm = False
    in_scoped_to = False
    body_start = len(lines)

    for i, line in enumerate(lines):
        if line.strip() == "---":
            if not in_fm:
                in_fm = True
                continue
            else:
                body_start = i + 1
                break
        if not in_fm:
            continue

        if in_scoped_to:
            # A non-indented line ends the nested mapping — re-process it as
            # an ordinary top-level frontmatter line below (fall through).
            if not line or not line[0].isspace():
                in_scoped_to = False
            else:
                stripped = line.strip()
                if ":" in stripped:
                    sub_key, _, sub_rest = stripped.partition(":")
                    sub_key = sub_key.strip()
                    if sub_key in _SCOPED_TO_SUBKEYS:
                        sub_v = _unquote_yaml_scalar(sub_rest.strip())
                        if sub_v:
                            nested_scoped_to[sub_key] = sub_v
                continue

        if ":" in line:
            key, _, rest = line.partition(":")
            key_stripped = key.strip()
            v = rest.strip()
            if key_stripped == "scoped_to" and v == "":
                in_scoped_to = True
                continue
            fm[key_stripped] = _unquote_yaml_scalar(v)

    # Nested scoped_to (when present) wins over any flat scoped_to_* keys
    # parsed above — it is the shape the engine now writes; a flat key left
    # over from a hand-edit or an older draft is superseded per sub-key.
    for sub_key, sub_v in nested_scoped_to.items():
        fm[f"scoped_to_{sub_key}"] = sub_v

    body = "\n".join(lines[body_start:]).lstrip("\n")
    return fm, body


# Sent-outbox archive location — a stamped (status: sent) outbox copy must
# not stay in state/memo-outbox/ itself: state/lessons/2026-07-12-an-empty-
# memo-outbox-is-the-sent-state-n-c3db55355656.yaml pins "an empty outbox is
# the SENT state" as an existing, relied-upon convention (a workstream-
# complete B-wave reviewer treats an absent outbox file as evidence of send),
# and coordinator_core/ops/workday_start_cross_repo_memo_outbox_surface.py's
# stale-draft nudge scans every *.md directly under the outbox dir with no
# status filter — a stamped file left in place would be mis-flagged as a
# stale draft forever. `state/memo-outbox/sent/` mirrors the sibling
# lessons-outbox convention (`<outbox>/drained/`, see cross-repo/archive/
# 2026-07-23-claude-central-em-lessons-outbox-relocation-and-subject-
# confirmation.md § 2/§ "no drained/ has ever existed") of parking
# lifecycle-complete entries in a same-named subdirectory a non-recursive
# `os.listdir()` scan never descends into, rather than inventing a new
# top-level location.
def _sent_outbox_archive_path(outbox_path: str) -> str:
    """The `state/memo-outbox/sent/<topic>.md` path a stamped, sent copy of
    `outbox_path` (a `state/memo-outbox/<topic>.md` draft) is archived to.

    Purely a path computation — callers still have to check existence.
    """
    outbox_dir = os.path.dirname(outbox_path)
    sent_dir = os.path.join(outbox_dir, "sent")
    return os.path.join(sent_dir, os.path.basename(outbox_path))


def _archive_sent_outbox_draft(outbox_path: str, sender_root: str | None = None) -> None:
    """Best-effort: move the now-stamped (`status: sent`) outbox draft at
    `outbox_path` into `state/memo-outbox/sent/`, preserving it as the
    sender's durable delivery record rather than destroying it.

    Called only after the receiver-side write has already succeeded (see
    `_send_via_engine`'s COMMITTED ACTION comment) — the engine's
    `_stamp_sender_outbox_sent` (coordinator_core/ops/fleet/memo_send.py) has
    already rewritten `outbox_path` in place with `status: sent`, `sent_at`,
    and `delivered_to` by the time this runs; this function only relocates
    the file, it never edits its content.

    Never raises — mirrors the prior `os.remove()`'s best-effort contract:
    the memo was delivered regardless of whether this archival step
    succeeds, so an `OSError` here (permissions, disk full, concurrent
    removal) must not turn a successful send into a reported failure.

    Negative-spec: does NOT delete `outbox_path` outright (that was the bug
    this closes — see `_send_via_engine`'s docstring) and does NOT touch any
    OTHER file already under `state/memo-outbox/sent/`.

    Routes the move through `coordinator_core.session.scope.relocate_touched_
    path` (docs/plans/2026-08-06-relocation-re-declares-the-touch-claim.md,
    C4) so a `memo.send` claim already T-declared on the pre-move outbox
    path is re-stated onto the archived one, rather than stranding on a path
    that no longer exists. `sender_root` (the sending repo's git root,
    already resolved by every caller before this function is ever reached)
    is used BOTH as the `cwd` `relocate_touched_path` normalizes paths
    against AND as the `coordinator_core.session.core.resolve_session_id`
    input — the same canonical 4-tier resolver every other coordinator/bin
    script uses for session identity (env vars, then the tier-4 sentinel),
    never a bespoke or ad-hoc lookup, and never re-consulted more than once
    here.

    Falls back to a plain `shutil.move` — silently, with no stderr noise —
    whenever the helper is unimportable (coordinator_core not on this
    machine/PYTHONPATH), `sender_root` is unresolvable, `resolve_session_id`
    comes back empty, or the helper itself raises for any reason: a
    successfully delivered memo must never be reported as a failure just
    because the CLAIM re-statement (a bookkeeping nicety) could not happen.

    Once the move has landed — via EITHER branch above — and re-declared the
    touch claim (when that branch ran), best-effort `commit_scoped`s the
    archived path into the sending repo (docs/plans/2026-08-06-memo-send-
    sender-side-commit-leg.md, C3). Sequencing is load-bearing: the commit
    only ever follows the move/claim-relocation, never substitutes for it —
    see `_commit_archived_outbox_draft` for the commit mechanism itself. Like
    every other branch here, a commit failure is best-effort and never turns
    a successfully delivered, successfully archived memo into a reported
    failure.
    """
    if not os.path.isfile(outbox_path):
        return  # nothing to archive — e.g. _stamp_sender_outbox_sent no-op'd
    dest = _sent_outbox_archive_path(outbox_path)
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
    except OSError:
        return  # Best-effort — the memo was delivered; archival is secondary.

    moved_via_relocate = False
    if sender_root:
        try:
            cc_invoke.ensure_engine_on_path(__file__)
            from coordinator_core.session import core as _session_core
            from coordinator_core.session import scope as _session_scope

            session_id = _session_core.resolve_session_id(sender_root)
            if session_id:
                src_rel = os.path.relpath(outbox_path, sender_root)
                dst_rel = os.path.relpath(dest, sender_root)
                _session_scope.relocate_touched_path(
                    session_id, src_rel, dst_rel, cwd=sender_root
                )
                moved_via_relocate = True
        except Exception:
            pass  # Best-effort — fall through to the plain move below.

    if not moved_via_relocate:
        try:
            shutil.move(outbox_path, dest)
        except OSError:
            return  # Best-effort — the memo was delivered; archival is secondary.

    if sender_root:
        _commit_archived_outbox_draft(outbox_path, dest, sender_root)


def _commit_archived_outbox_draft(outbox_path: str, dest: str, sender_root: str) -> None:
    """Best-effort: `commit_scoped` the just-archived `dest`
    (`state/memo-outbox/sent/<topic>.md`) into the sending repo, after
    `_archive_sent_outbox_draft`'s move (whichever branch performed it) has
    already landed on disk.

    Mechanism: `coordinator_core.ops.ceremony.git_native.commit_scoped` with
    explicit single FILE paths only — never a directory pathspec.
    `commit_scoped` fails loud on a directory entry by design; this leg's
    own source memo was a directory pathspec sweeping sibling `sent/`
    records into one commit, which is exactly the incident `commit_scoped`
    (and this single-file-only call site) closes.

    The archival move is a rename: `outbox_path` is deleted, `dest` is
    created. Whether `outbox_path` belongs in `commit_scoped`'s `paths` is
    NOT optional — it depends on whether `outbox_path` was tracked in
    `HEAD`, determined immediately below via `git ls-files --error-unmatch`:
      - UNTRACKED (the dominant case — `memo.draft`/`memo.compose` don't
        commit, so the outbox draft is normally untracked at send time):
        pass `dest` ONLY. `outbox_path` was never in the index or `HEAD`;
        passing it anyway lands it in `commit_scoped`'s trailing pathspec
        despite never having been staged (the AGREE branch's own `existing`
        filter skips a path no longer present on disk post-move), and a
        pathspec component matching nothing fails the WHOLE `git commit`
        call (measured: exit 128, stages NOTHING) — silently no-op'ing this
        leg on every ordinary send.
      - TRACKED in `HEAD` (rare — only if the draft was itself committed
        before send): pass BOTH `outbox_path` and `dest` — the rename's
        deletion half needs representing in the same commit.

    Never raises — mirrors `_archive_sent_outbox_draft`'s own best-effort,
    never-fail contract: the memo is already delivered and archived on disk
    by the time this runs, so a commit failure (coordinator_core
    unimportable, a non-repo cwd, `commit_scoped` itself failing) must never
    turn a successful send into a reported failure. Prints a WARNING to
    stderr on failure, and the archive commit's SHA to stdout (alongside
    `_verify_delivery_landed`'s "Delivery verified: ... committed as <sha>"
    line, cross-repo-memo:2017) on success.
    """
    try:
        cc_invoke.ensure_engine_on_path(__file__)
        from coordinator_core.ops.ceremony import git_native

        src_rel = os.path.relpath(outbox_path, sender_root)
        dst_rel = os.path.relpath(dest, sender_root)

        tracked = subprocess.run(
            ["git", "-C", sender_root, "ls-files", "--error-unmatch", "--", src_rel],
            capture_output=True,
            text=True,
            timeout=30,
        )
        paths = [dst_rel] if tracked.returncode != 0 else [src_rel, dst_rel]

        message = f"cross-repo-memo: archive sent outbox draft {dst_rel}\n"
        msg_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            ) as fh:
                # Review: code-reviewer (P2) — assign before write so `finally`
                # can always unlink even if `fh.write` itself raises.
                msg_path = fh.name
                fh.write(message)
            result = git_native.commit_scoped(paths, msg_path, sender_root)
        finally:
            if msg_path:
                try:
                    os.unlink(msg_path)
                except OSError:
                    pass

        if not result.ok:
            print(
                f"cross-repo-memo: WARNING — archive commit failed: {result.stderr}",
                file=sys.stderr,
            )
            return

        # Resolve the sha by the path this leg just committed, NOT by reading
        # HEAD: `commit_scoped` surfaces no sha of its own (its AGREE branch
        # returns `commit_with_message_file`'s summary text, its private-index
        # branch lands via CAS `update-ref`), and on this machine a peer commit
        # routinely lands between the commit and any HEAD read — which would
        # print a sha naming someone else's commit. `dst_rel` is unique to this
        # memo, so the last commit touching it is unambiguously this one.
        sha_result = subprocess.run(
            ["git", "-C", sender_root, "log", "-1", "--format=%H", "--", dst_rel],
            capture_output=True,
            text=True,
            timeout=30,
        )
        sha = sha_result.stdout.strip() if sha_result.returncode == 0 else ""
        if sha:
            print(f"Archive committed: {dst_rel} committed as {sha}.")
        else:
            print(f"Archive committed: {dst_rel} (sha unresolved).")
    except Exception as exc:
        print(
            f"cross-repo-memo: WARNING — archive commit failed: {exc}",
            file=sys.stderr,
        )


def _print_live_peer_advisory(receiver_path: str) -> None:
    """Advisory-only: name the live sessions whose `cwd` is inside
    `receiver_path`, so the sender knows whether the recipient repo's EM is
    around right now.

    Wired here, and ONLY here, per
    `state/handoffs/2026-08-13-live-peer-roster.md` § 4/AC7: this is the one
    place "is the recipient even here?" actually blocks a decision, and the
    only ingredient this CLI already has is a receiver REPO path, not a
    session UUID — `session.resolve_address` (keyed on a UUID) cannot answer
    that question, so it has to be the roster.

    Never blocks, never changes the exit code, at any stage. Any failure —
    the engine unresolvable, the roster read raising — degrades to printing
    nothing, same as `peer_roster.build_roster`'s own advisory-read
    discipline. Anti-scope (same handoff): a READ surface only — this never
    calls `SendMessage` and never suggests the caller do so.

    The calling session's own row (`is_self`) is excluded from the printed
    set: this line answers "who is over there," not "am I over there."
    """
    try:
        cc_invoke.ensure_engine_on_path(__file__)
        from coordinator_core.session import peer_roster

        rows = peer_roster.build_roster(receiver_path)
    except Exception:
        return

    repo_label = os.path.basename(os.path.normpath(receiver_path)) or receiver_path
    addresses = [row.address for row in rows if not row.is_self and row.address]

    if not addresses:
        print(f"No live sessions in {repo_label}.")
        return
    print(f"{len(addresses)} live session(s) in {repo_label}: {', '.join(addresses)}")


# Review: code-reviewer (Finding 2) — extracted from what were two ~100-line
# near-identical copies (`_cmd_send`'s dispatch tail and main()'s ordinary
# flag-only send arm). Both call sites mirror the same
# materialize-kind / build-invoke_params / route_mutation / extract-acted /
# containment-guard / commit / print sequence; duplicating it invited silent
# drift between the two "mirrored" paths (Finding 3 was a live instance of
# that drift — inconsistent `kind` argument to `_print_premise_check_advisory`
# — already present before this extraction). `outbox_path` is the one real
# difference between the two call sites: `_cmd_send` archives the (now
# engine-stamped) outbox draft to `state/memo-outbox/sent/` on success, the
# flag-only arm has no outbox and passes None.
def _send_via_engine(
    *,
    topic: str,
    to: str,
    title: str,
    body: str,
    kind: str | None,
    summary: str | None,
    supersedes: str | None,
    sender: str,
    sender_root: str,
    receiver_path: str,
    outbox_path: str | None = None,
    scoped_to: dict[str, str] | None = None,
    in_reply_to: str | None = None,
) -> int:
    """Dispatch a memo send through the claude-klabauter engine (DR-210 graduation).

    Shared by `_cmd_send` (topic-file send) and main()'s ordinary flag-only
    send arm. The receiver-side filename, gitignore delivery guard,
    containment check, and collision refusal are composed/enforced
    claude-klabauter-side (memo_send.py); DoE no longer recomputes the filename (DEC-3)
    or writes the memo content directly (Q-c hard, DEC-2).

    `outbox_path`, when not None, is best-effort archived to
    `state/memo-outbox/sent/` on success only (see
    `_archive_sent_outbox_draft`) — this is `_cmd_send`'s topic-file
    draft-cleanup step. By the time this runs, claude-klabauter's `memo.send` op has
    already stamped `outbox_path` in place with `status: sent`, `sent_at`,
    and `delivered_to` (`_stamp_sender_outbox_sent`,
    coordinator_core/ops/fleet/memo_send.py); this function only relocates
    that stamped copy, it never deletes the sender's delivery evidence. The
    flag-only send arm has no outbox draft and passes `outbox_path=None`,
    which skips this step entirely.

    Returns the process exit code (0 on success, 1 on any refusal/error).
    """

    def legacy_send() -> None:
        """Fail-loud legacy stub — Q-c hard (DEC-2). NOT a direct-write fallback.

        A working fallback here would silently defeat the claude-klabauter-engine
        integrity cut (lesson 2026-07-08: a swallowed native rejection ships
        a break-class regression the legacy-only test never catches). This
        stub only ever raises — State-1 (seam absent), State-2 transport
        failure, and State-2 op-refusal all converge on the same
        `except RuntimeError` handler below.
        """
        raise RuntimeError(
            "claude-klabauter engine seam not found (CLAUDE_KLABAUTER_ROOT unresolvable or "
            "coordinator_core.invoke not importable) — the direct-write "
            "fallback has been retired (Q-c hard). Install/configure the "
            "claude-klabauter engine to send cross-repo memos."
        )

    # kind materialization: DoE's inputs treat kind as optional (reader
    # defaults to 'ask'); claude-klabauter's op requires a non-None kind (DEC-4).
    invoke_kind = kind or "ask"

    invoke_params = {
        "dry_run": False,
        "topic": topic,
        "to": to,
        "title": title,
        "body": body,
        "from_id": sender,
        "kind": invoke_kind,
        "summary": summary,
        "supersedes": supersedes,
    }
    # scoped_to is threaded to claude-klabauter's memo.send op (bcc7cdbe), which
    # composes the receiver-side frontmatter from params; omit the key
    # entirely when absent — claude-klabauter fails loud on scoped_to=None.
    if scoped_to:
        invoke_params["scoped_to"] = scoped_to
    # in_reply_to (2026-07-25 write-side addition) — omit the key entirely
    # when absent; claude-klabauter's memo.send op normalizes to a basename and
    # existence-checks it against this repo's own cross-repo/{inbox,archive}/
    # before writing anything to the receiver (memo_send._validate_in_reply_to_exists).
    if in_reply_to:
        invoke_params["in_reply_to"] = in_reply_to

    try:
        result = cc_invoke.route_mutation("memo.send", invoke_params, sender_root, legacy_send)
    except RuntimeError as exc:
        # State-1 legacy-raise, State-2 transport-fail, and State-2 op-refusal
        # (route_mutation's exit_code/failed inspection) all land here. Outbox
        # (if any) stays, nothing is committed, exit non-zero (AC2/AC9).
        print(f"cross-repo-memo send: {exc}", file=sys.stderr)
        # Review: code-reviewer (Finding 1) — route_mutation's message hardcodes
        # only "refused (...)" with a failed *count*; without the per-item reason
        # text (memo_send.py's "failed": [{"reason": "gitignore-delivery-guard: …"}]
        # / "collision: …" shape), a caller (or a test asserting "the word
        # 'refused' is present") cannot distinguish WHICH refusal fired. Surface
        # `exc.result`'s failed-item reasons when present (RouteMutationError
        # only — the legacy_send() stub raises a bare RuntimeError with no
        # `.result`) so reason-specific substrings become assertable again.
        _print_route_mutation_failure_reasons(exc)
        return 1

    acted = result.get("acted") if isinstance(result, dict) else None
    if not (isinstance(result, dict) and result.get("exit_code") == 0 and acted):
        # route_mutation already raises on any non-success envelope; this is a
        # defensive net for an anomalous success shape (exit_code:0, empty
        # acted) — treat it the same as a refusal: leave outbox (if any), no commit.
        outbox_note = " outbox retained." if outbox_path is not None else ""
        print(
            "cross-repo-memo send: claude-klabauter reported success but returned no "
            f"delivered memo (empty 'acted') — aborting.{outbox_note}",
            file=sys.stderr,
        )
        return 1

    # acted[0]['id'] is the absolute receiver-side path claude-klabauter wrote to
    # (memo_send.py:909, target_path is registry-derived absolute — DEC-5).
    receiver_side_path = acted[0].get("id") if isinstance(acted[0], dict) else None
    if not receiver_side_path:
        outbox_note = " outbox retained." if outbox_path is not None else ""
        print(
            "cross-repo-memo send: claude-klabauter reported success but the delivered-memo "
            f"entry is malformed (missing 'id') — aborting.{outbox_note}",
            file=sys.stderr,
        )
        return 1

    # delivery_commit (pinned contract — coordinator_core/ops/fleet/memo_send.py
    # C1) is the engine's own account of whether it committed the delivered
    # memo into the receiver repo. Surface the git failure reason to stderr
    # when it did not, so the operator sees WHY before _verify_delivery_landed
    # (below) reports the same fact as an untracked read-back (AC7).
    delivery_commit = acted[0].get("delivery_commit") if isinstance(acted[0], dict) else None
    if isinstance(delivery_commit, dict) and delivery_commit.get("committed") is False:
        print(
            f"cross-repo-memo: delivery commit failed in the receiver repo: "
            f"{delivery_commit.get('reason')}",
            file=sys.stderr,
        )

    # The claude-klabauter memo.send op commits the delivered memo into the receiver repo
    # itself, all hooks neutralized via `-c core.hooksPath=<empty-tmpdir>`
    # (DR-211 D2 criterion 3 retired; DR-214 mechanism — see claude-klabauter
    # coordinator_core/ops/fleet/memo_send.py). DoE does NOT re-commit here: the
    # previous _commit_delivered_memo call on this path was redundant, and
    # because the receiver tree is routinely dirty under concurrent-EM git, its
    # `git commit -- <memo>` consistently exited non-zero with "no changes added
    # to commit" (claude-klabauter already committed the memo) — which the idempotent-no-op
    # guard in _commit_delivered_memo missed, tripping a false "left uncommitted"
    # WARNING on every successful delivery. That warning is the ONE signal a
    # genuine commit failure would ever raise, so a permanent false positive on
    # it masked the alarm that matters (claude-klabauter-em memo, 2026-07-21).
    # _commit_delivered_memo is retained solely for the --self-receipt path,
    # which bypasses the claude-klabauter engine entirely and is its own sole committer.

    # Stdout output (mirrors legacy path).
    abs_receiver = os.path.abspath(receiver_side_path)
    print(f"Receiver-side: {abs_receiver}")
    delivery_sha = delivery_commit.get("sha") if isinstance(delivery_commit, dict) else None
    landed = _verify_delivery_landed(receiver_path, abs_receiver, expected_sha=delivery_sha)

    # Sender-side (local) commit announcement — the fix for a recurring
    # false belief (surfaced repeatedly across EM sessions, most recently
    # 2026-08-14) that a memo-deliverable plan chunk has "no representable
    # completion state" because the memo's CONTENT commit lands in the
    # receiver's tree. It does — but memo.send ALSO commits the sent-ledger
    # append into the SENDER's own tree (coordinator_core/ops/fleet/
    # memo_send.py `_commit_sender_ledger`), and that local commit already
    # carries the chunk's `Deliverable-Id` when the plan stamps one. The
    # prior receipt never named this commit at all, so it was invisible to
    # a reader looking for completion evidence. Printed once, immediately
    # after the receiver-side verdict above (not buried under the relay
    # lines this replaces) and explicitly contrasted with it so the two
    # commits — one per repo — cannot blur into each other.
    sender_ledger_commit = (
        acted[0].get("sender_ledger_commit") if isinstance(acted[0], dict) else None
    )
    if sender_ledger_commit:
        print(
            f"Local commit (this repo, not the receiver's): "
            f"{sender_ledger_commit} — the completion evidence for this chunk."
        )

    # AC7 (docs/plans/2026-08-13-memo-send-delivery-commit-verify-hole.md):
    # archive the stamped draft (if any) only AFTER verification, so a
    # failed/uncommitted delivery leaves the draft in place for `send
    # <topic>` to retry — archiving before verification ran previously left
    # a failed delivery with no draft to retry. `_cmd_send`-only cleanup;
    # the flag-only send arm passes outbox_path=None and skips this.
    if landed and outbox_path is not None:
        _archive_sent_outbox_draft(outbox_path, sender_root)

    # Change 2 (PM directive, 2026-08-14): this used to be followed by two
    # more lines — "Hand the PM this path for relay: <path>" and "Reminder:
    # Hand the PM the receiver path — PM-relay is still the primary
    # channel." — restating the SAME receiver path already printed above
    # as "Receiver-side: <path>", plus a relay instruction nobody follows
    # ("nobody does the second bit anyway" — PM). Both lines are cut; the
    # single "Receiver-side:" statement above is the one fact, stated once.
    _print_live_peer_advisory(receiver_path)
    # Review: code-reviewer (Finding 3) — pass the already-materialized
    # invoke_kind (never None) at both call sites for consistency, rather
    # than one site passing a possibly-None raw arg — a future edit to the
    # advisory helper that assumes non-None kind would otherwise silently
    # misbehave on only one call site.
    # `outbox_path is None` is exactly the legacy one-shot flag form (the only
    # caller that passes it) — that form has no draft/compose stage, so the
    # generic send receipt would name a lifecycle it never used. Route it to
    # the arm that names the remedy takeable on ITS invocation shape instead
    # (doe-claude-em memo, 2026-08-03).
    _print_premise_check_advisory(
        to,
        receiver_path,
        invoke_kind,
        scoped_to,
        stage="send" if outbox_path is not None else "send_oneshot",
    )

    # Never-fail-the-send stays intact: a committed delivery is still exit 0.
    # An untracked read-back is degraded, not failed — exit 2, not 1 (AC8/AC9;
    # the send itself succeeded, only the receiver-side commit did not land).
    return 0 if landed else 2


def _send_campaign_via_engine(
    *,
    topic: str,
    to_list: list[str],
    title: str,
    body: str,
    kind: str | None,
    summary: str | None,
    supersedes: str | None,
    sender: str,
    sender_root: str,
    campaign_id: str | None,
    dry_run: bool = False,
    scoped_to: dict[str, str] | None = None,
) -> int:
    """1->N fan-out dispatch (DEC-3/C7) — `--campaign-to`'s engine call.

    ONE `memo.send` invocation with `to` bound to `to_list` (a list, not a
    string) — claude-klabauter's op (coordinator_core/ops/fleet/memo_send.py
    `_memo_send_fan_out`) iterates the exact same single-receiver write path
    once per receiver, sharing one campaign_id, and returns an extended
    envelope carrying `campaign_id` + a per-receiver `manifest`
    ([{receiver, outcome, error, campaign_id}, ...]).

    route_mutation raises on ANY non-zero exit_code — including the
    DETERMINATE-PARTIAL exit_code:2 a fan-out with SOME failing receivers
    returns — so both the all-succeeded (normal return) and
    some-failed/all-failed (RouteMutationError) cases are handled here; the
    manifest lives in `result` either way (`RouteMutationError.result`
    mirrors the same payload a bare success return would have carried — see
    `cc_invoke.RouteMutationError`'s docstring).

    Unlike `_send_via_engine`, this does NOT call
    `_print_premise_check_advisory` per receiver (out of scope for the
    campaign broadcast surface — a single-receiver refinement, not a
    fan-out one) and does NOT resolve/print each receiver's on-disk repo
    path — the manifest's receiver ids plus the printed campaign_id are the
    contract this command hands the PM for relay.

    dry_run: Review: code-reviewer (Finding 1) — threaded straight into
    `invoke_params["dry_run"]`; the engine op (`_memo_send_fan_out`) already
    supports dry_run end to end (validate + containment + compose +
    frontmatter self-validate, WITHOUT any filesystem write, per receiver)
    and reports each receiver's manifest entry as `outcome: "previewed"`
    rather than `"delivered"`. `render()` below treats "previewed" as
    success alongside "delivered" — unlike `--to`'s dry-run (which
    intercepts BEFORE reaching `_send_via_engine`), this function is the
    single call path for both real and preview campaign sends, so there is
    no separate early-return branch to maintain.

    Returns the process exit code: 0 (every receiver delivered/previewed),
    1 (no per-receiver manifest at all — transport/setup failure), or 2
    (DETERMINATE-PARTIAL — at least one receiver failed, at least one
    other outcome may have succeeded; see the printed per-receiver lines).
    """

    def legacy_send() -> None:
        """Fail-loud legacy stub — mirrors _send_via_engine.legacy_send (Q-c hard)."""
        raise RuntimeError(
            "claude-klabauter engine seam not found (CLAUDE_KLABAUTER_ROOT unresolvable or "
            "coordinator_core.invoke not importable) — the direct-write "
            "fallback has been retired (Q-c hard). Install/configure the "
            "claude-klabauter engine to send cross-repo memos."
        )

    invoke_kind = kind or "ask"
    invoke_params: dict[str, object] = {
        # Review: code-reviewer (Finding 1) — was hardcoded False, so
        # --campaign-to always performed a real, committed broadcast even
        # when the caller passed --dry-run. Now threaded through: the
        # engine op fully supports dry_run for the fan-out path.
        "dry_run": dry_run,
        "topic": topic,
        "to": list(to_list),
        "title": title,
        "body": body,
        "from_id": sender,
        "kind": invoke_kind,
        "summary": summary,
        "supersedes": supersedes,
    }
    if campaign_id:
        invoke_params["campaign_id"] = campaign_id
    if scoped_to:
        invoke_params["scoped_to"] = scoped_to

    if dry_run:
        print("cross-repo-memo --campaign-to: DRY RUN — no write, no commit.")

    def render(result: object) -> bool:
        """Print the per-receiver manifest; return True iff any receiver failed.

        Review: code-reviewer (Finding 1) — a receiver's manifest `outcome`
        is "previewed" (not "delivered") on a dry_run invocation
        (memo_send.py `_memo_send_fan_out`); both are success outcomes here,
        matching the single-receiver `--to` path's dry-run semantics (no
        write, exit 0). Only "error" counts as a failure.
        """
        manifest = result.get("manifest") if isinstance(result, dict) else None
        returned_campaign_id = (
            result.get("campaign_id") if isinstance(result, dict) else None
        )
        if not isinstance(manifest, list) or not manifest:
            print(
                "cross-repo-memo --campaign-to: claude-klabauter reported a result but "
                "returned no per-receiver manifest — aborting.",
                file=sys.stderr,
            )
            return True
        print(f"Campaign id: {returned_campaign_id}")
        saw_failure = False
        for entry in manifest:
            if not isinstance(entry, dict):
                saw_failure = True
                continue
            receiver = entry.get("receiver")
            outcome = entry.get("outcome")
            if outcome == "delivered":
                print(f"  [delivered] {receiver}")
            elif outcome == "previewed":
                print(f"  [previewed] {receiver}")
            else:
                saw_failure = True
                print(f"  [failed]    {receiver}: {entry.get('error')}", file=sys.stderr)
        if dry_run:
            print(
                "Reminder: this was a dry run — no receiver was written to "
                "and no commit was made. Re-run without --dry-run to send."
            )
        else:
            # Sender-side (local) commit announcement — same fix as the
            # single-receiver `--to` path above (see that call site's
            # comment for the "unresolvable" belief this closes). One
            # commit covers the whole campaign (memo_send.py
            # `_memo_send_fan_out` fires it once, after every receiver's
            # ledger row has landed), so every acted entry carries the
            # same SHA — read it off the first one.
            acted = result.get("acted") if isinstance(result, dict) else None
            sender_ledger_commit = (
                acted[0].get("sender_ledger_commit")
                if isinstance(acted, list) and acted and isinstance(acted[0], dict)
                else None
            )
            if sender_ledger_commit:
                print(
                    f"Local commit (this repo, not any receiver's): "
                    f"{sender_ledger_commit} — the completion evidence for "
                    f"this campaign."
                )
        return saw_failure

    try:
        result = cc_invoke.route_mutation("memo.send", invoke_params, sender_root, legacy_send)
    except RuntimeError as exc:
        payload = getattr(exc, "result", None)
        if isinstance(payload, dict) and payload.get("manifest"):
            # DETERMINATE-PARTIAL (exit_code:2) or all-failed (exit_code:2) —
            # route_mutation raises on ANY non-zero exit_code, but the
            # manifest (with per-receiver detail) still rode along on
            # RouteMutationError.result.
            return 2 if render(payload) else 0
        print(f"cross-repo-memo send --campaign-to: {exc}", file=sys.stderr)
        _print_route_mutation_failure_reasons(exc)
        return 1

    return 2 if render(result) else 0


def _cmd_send(args: argparse.Namespace) -> int:
    """Handle: cross-repo-memo send <topic>

    Reads state/memo-outbox/<topic>.md from sender repo, validates frontmatter
    (required fields present, status is 'draft'), then dispatches via the existing
    _compose_memo / _write_file pipeline. Promotes status: draft → open and applies
    created: today at send time (not draft time — matches today's send-flow semantics).

    On success, the outbox file is stamped `status: sent` by claude-klabauter's
    memo.send op (`_stamp_sender_outbox_sent`) and then archived to
    `state/memo-outbox/sent/<topic>.md` (`_archive_sent_outbox_draft`) —
    receiver write is the committed action; the stamped copy is the
    sender's durable delivery record, not something send discards.

    Failure-shape taxonomy (spec: § C2):
      Validation fail (missing fields / wrong status) → leave outbox, exit 2
      Receiver-resolution fail                        → leave outbox, exit 1
      Pre-write pipeline failure                      → leave outbox, exit 1
      Receiver-write succeeds, anything after fails   → archive outbox, exit 0

    Already-sent topic (no draft at state/memo-outbox/<topic>.md, but a
    stamped copy exists at state/memo-outbox/sent/<topic>.md): reported
    explicitly (exit 1, pointing at the archived record) rather than falling
    through to the generic "outbox draft not found" message — see the
    archived-copy check below.

    Spec backlink: docs/plans/2026-06-15-cross-repo-memo-draft-lifecycle.md § C2
    """
    topic = args.topic

    # Review: code-reviewer — validate topic slug before any path construction to prevent
    # path traversal (e.g. "../../../some/path"). Mirrors _cmd_draft's slug validation.
    if not _TOPIC_SLUG_RE.fullmatch(topic):
        print(
            f"cross-repo-memo send: invalid topic slug '{topic}'. "
            f"Topic must match [a-z0-9][a-z0-9-]* (lowercase alphanum and dashes only).",
            file=sys.stderr,
        )
        return 2

    # Resolve sender repo root. Fail loud (not silent-degrade) when unresolvable —
    # see _guard_sender_identity_before_delivery docstring for the root-cause.
    sender_root = _current_repo_root()
    if sender_root is None:
        guard_error = _guard_sender_identity_before_delivery()
        print(guard_error or "cross-repo-memo send: cwd is not a git working tree.", file=sys.stderr)
        return 1
    _warn_if_unregistered_sender()

    # Locate outbox file.
    outbox_path = os.path.join(sender_root, "state", "memo-outbox", f"{topic}.md")
    if not os.path.isfile(outbox_path):
        # Explicit already-sent case (see _cmd_send docstring): a topic whose
        # draft is gone but whose stamped delivery record survives at
        # state/memo-outbox/sent/<topic>.md was already sent — name that
        # instead of falling through to the generic "not found" hint, which
        # would otherwise point the caller at `draft`/`list` for a topic that
        # was never actually lost.
        archived_path = _sent_outbox_archive_path(outbox_path)
        if os.path.isfile(archived_path):
            print(
                f"cross-repo-memo send: topic '{topic}' was already sent — "
                f"see the stamped delivery record at {archived_path}. "
                f"To send this content again, stage a new topic with "
                f"`cross-repo-memo draft <new-topic> --to <em> --title \"...\"`.",
                file=sys.stderr,
            )
            return 1
        print(
            f"cross-repo-memo send: outbox draft '{topic}' not found at {outbox_path}. "
            f"Use `cross-repo-memo list` to see pending drafts, or "
            f"`cross-repo-memo draft {topic} --to <em> --title \"...\"` to create one.",
            file=sys.stderr,
        )
        return 1

    # Parse and validate frontmatter.
    fm, body = _parse_outbox_file(outbox_path)

    if not fm:
        print(
            f"cross-repo-memo send: could not parse frontmatter from '{outbox_path}'. "
            f"The outbox file may be empty or malformed. "
            f"Use `cross-repo-memo compose {topic}` to view the path and fix it, "
            f"or `cross-repo-memo discard {topic}` to remove it and start over.",
            file=sys.stderr,
        )
        return 2

    # 2026-08-07 open->draft normalization (cross-repo/inbox/2026-08-07-
    # example-store-repo-em-memo-tool-rejects-the-shape-it-teaches.md): an outbox
    # draft hand-authored with `status: open` — the shape every *received*
    # inbox memo around it carries, an easy field to copy by mistake — is
    # unambiguous sender-side: `open` on a file still sitting in
    # state/memo-outbox/ can only mean "this was meant to be a draft", since
    # `send` is what promotes draft -> open in the first place (see this
    # function's own docstring). Normalized here, in-memory only (the file on
    # disk is untouched — the existing send flow already stamps it), so
    # `_validate_outbox_frontmatter` never sees `open` on this path. Any
    # OTHER status (not 'draft' or 'open') still fails loud, unchanged, via
    # the validator below.
    if fm.get("status") == "open":
        print(
            f"cross-repo-memo send: outbox draft '{topic}' has status: open — "
            f"normalizing to status: draft before send. 'open' is the shape a "
            f"*received* memo carries; an outbox draft is un-sent by "
            f"definition, so this is unambiguous. (Fix the draft file to avoid "
            f"this notice on a future send.)",
            file=sys.stderr,
        )
        fm = dict(fm)
        fm["status"] = "draft"

    validation_errors = _validate_outbox_frontmatter(fm)
    if validation_errors:
        # Fail-closed: outbox draft is left INTACT, nothing sent (exit 2).
        # Error text names the preserved draft path so a scoped_to refusal
        # (or any other validation failure) is actionable without a second
        # lookup — see _scoped_to_errors / schema.js:2290.
        print(
            f"cross-repo-memo send: outbox draft '{topic}' has invalid frontmatter "
            f"— cannot send:\n"
            + "\n".join(f"  - {e}" for e in validation_errors)
            + f"\nYour draft is preserved at {os.path.abspath(outbox_path)}; fix it "
            + f"with `cross-repo-memo compose {topic}` (or hand-edit the file "
            + f"directly — e.g. add scoped_to_artifact/scoped_to_version-or-"
            + f"scoped_to_sha/scoped_to_seam), then re-send.",
            file=sys.stderr,
        )
        return 2

    # Extract fields from outbox frontmatter for dispatch.
    # Review: code-reviewer — supersedes was silently dropped; extract and pass through
    # so the receiver-side memo preserves the field from the outbox draft.
    to = fm.get("to", "")
    title = fm.get("title", "")
    summary = fm.get("summary") or None
    kind = fm.get("kind") or None
    supersedes = fm.get("supersedes") or None
    in_reply_to = fm.get("in_reply_to") or None
    # Assemble the nested scoped_to dict claude-klabauter's memo.send op expects from
    # the outbox draft's flattened scoped_to_* frontmatter keys (same shape
    # _scoped_to_errors validated above) — see _build_scoped_to docstring.
    scoped_to = _build_scoped_to(
        fm.get("scoped_to_artifact"),
        fm.get("scoped_to_version"),
        fm.get("scoped_to_sha"),
        fm.get("scoped_to_seam"),
    )

    # Reject publish-target receivers (reuse existing guard from legacy path).
    if _is_publish_target_em(to) and os.environ.get("COORDINATOR_OVERRIDE_PUBLISH_TARGET_RECEIVER") != "1":
        known = _known_receiver_ids()
        hint = (
            f"\n  Known EM receivers: {', '.join(known)}."
            if known else ""
        )
        owner = _publish_target_owner(to)  # non-None: guarded by _is_publish_target_em above
        msg = (
            _home_redirect_rejection_msg(to, owner, hint)
            if _redirect_kind(to) == "home"
            else _publish_target_rejection_msg(to, owner, hint)
        )
        print(msg, file=sys.stderr)
        return 1

    # Resolve receiver repo path.
    receiver_path, diagnostic_already_printed = _resolve_receiver_path(to)

    if receiver_path is None:
        if diagnostic_already_printed:
            # _resolve_receiver_path already emitted a complete, accurate
            # diagnostic (registry-read failure, not a clean key-absence) —
            # printing the generic "not registered on this machine" message
            # below would be a second, misleading diagnostic.
            return 1
        if _is_central_receiver(to):
            print(
                f"cross-repo-memo send: cannot deliver to central ('{to}') — "
                f"repos.doe_claude is not registered on this machine.\n"
                f"  Remediation: machine-local set repos.doe_claude <path-to-the-coordinator-doctrine-repo>.",
                file=sys.stderr,
            )
            return 1
        repo_key = _receiver_repo_key(to)
        known = _known_receiver_ids()
        hint = (
            f"\n  Known receivers on this machine: {', '.join(known)}."
            if known else ""
        )
        print(
            f"cross-repo-memo send: cannot deliver to '{to}' — it resolves to "
            f"machine-local key '{repo_key}', which is not registered on this machine.\n"
            f"  Remediation: if that repo lives on this machine, register it with "
            f"`machine-local set {repo_key} <path>`. Otherwise route this memo via "
            f"the PM's next session in that repo.{hint}",
            file=sys.stderr,
        )
        return 1

    # Dispatch the write through the claude-klabauter engine (DR-210 graduation). The
    # receiver-side filename, gitignore delivery guard, containment check, and
    # collision refusal are now composed/enforced claude-klabauter-side (memo_send.py);
    # DoE no longer recomputes the filename (DEC-3) or writes the memo content
    # directly (Q-c hard, DEC-2) — see the _cmd_send docstring / plan DEC-1..5.
    sender = _sender_em_id()

    return _send_via_engine(
        topic=topic,
        to=to,
        title=title,
        body=body,
        kind=kind,
        summary=summary,
        supersedes=supersedes,
        sender=sender,
        sender_root=sender_root,
        receiver_path=receiver_path,
        outbox_path=outbox_path,
        scoped_to=scoped_to,
        in_reply_to=in_reply_to,
    )


def _format_age(seconds: float) -> str:
    """Format an age in seconds as a human-readable string (e.g. '5m', '3h', '2d').

    Spec backlink: docs/plans/2026-06-15-cross-repo-memo-draft-lifecycle.md § C3
    """
    # Review: code-reviewer — avoid "0m" for brand-new files; "<1m" is clearer
    if seconds < 60:
        return "<1m"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h"
    return f"{int(seconds // 86400)}d"


def _cmd_list(args: argparse.Namespace) -> int:
    """Handle: cross-repo-memo list

    A8 strangler cutover: thin invoke-and-render trampoline onto claude-klabauter's
    `memo.list_outbox` op — the engine owns the enumeration + frontmatter
    parse; the CLI performs a MINIMAL stat pass over the returned candidates'
    `path`s to reproduce the mtime-based age/stale/sort presentation the op
    deliberately does not provide (age/stale/mtime-sort is CLI-side
    rendering by design, not an op contract gap).

    Marks entries older than COORDINATOR_OUTBOX_STALE_HOURS (default 24) as
    [stale]. Empty outbox → exit 0 with 'no drafts'.

    Output format per draft (sorted by mtime ascending, oldest first):
      <topic>  <age>  → <to>  :: <title>

    Stale entries get a '[stale]' marker after the age column.

    Spec backlink: docs/plans/2026-06-15-cross-repo-memo-draft-lifecycle.md § C3
                   /private/tmp/.../scratchpad/six-verb-cutover-map.md § #4 list
    """
    sender_root = _current_repo_root()
    if sender_root is None:
        print(
            "cross-repo-memo list: must be invoked from inside a git repo (sender). "
            "Current cwd is not a git working tree.",
            file=sys.stderr,
        )
        return 2

    def legacy_list_outbox() -> None:
        """Fail-loud legacy stub — mirrors _send_via_engine.legacy_send.

        A working direct-compute fallback here would silently defeat the
        claude-klabauter-engine integrity cut; this stub only ever raises, so
        State-1 (seam absent), State-2 transport failure, and State-2
        op-refusal all converge on the same `except RuntimeError` handler
        below.
        """
        raise RuntimeError(
            "claude-klabauter engine seam not found (CLAUDE_KLABAUTER_ROOT unresolvable or "
            "coordinator_core.invoke not importable) — the direct-compute "
            "fallback has been retired. Install/configure the claude-klabauter "
            "engine to list outbox drafts."
        )

    try:
        result = cc_invoke.route_mutation(
            "memo.list_outbox",
            {"dry_run": True},
            sender_root,
            legacy_list_outbox,
        )
    except RuntimeError as exc:
        print(f"cross-repo-memo list: {exc}", file=sys.stderr)
        _print_route_mutation_failure_reasons(exc)
        return 1

    # memo.list_outbox is a COMPUTE_ONLY/dry_run-only op — its data lives in
    # the dry_run envelope's `candidates` list, NOT `acted` (always empty for
    # a dry-run result). Same extraction shape as --check-addressee/--list-receivers.
    candidates = result.get("candidates") if isinstance(result, dict) else None
    if not isinstance(candidates, list):
        print(
            "cross-repo-memo list: claude-klabauter reported success but returned no "
            "candidate list — aborting.",
            file=sys.stderr,
        )
        return 1

    if not candidates:
        print("no drafts")
        return 0

    # Op returns candidates sorted by FILENAME with no mtime/age/stale — the
    # CLI reproduces the historical mtime-based UX with a minimal stat pass
    # over each candidate's `path`. A candidate whose file vanished between
    # the op's enumeration and this stat (race) or whose `note` marks it
    # unreadable/unparseable still renders (mtime falls back to 0.0 — sorts
    # first, ages as "very old" — rather than silently dropping the entry;
    # the op's own negative-spec guarantees a malformed draft is never
    # silently dropped, and the CLI must not undo that here).
    entries: list[tuple[float, dict]] = []  # (mtime, candidate)
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        path = candidate.get("path")
        mtime = 0.0
        if path:
            try:
                mtime = os.stat(path).st_mtime
            except OSError:
                mtime = 0.0
        entries.append((mtime, candidate))

    # Sort by mtime ascending (oldest first) — preserves the historical UX.
    entries.sort(key=lambda t: t[0])

    stale_hours = float(os.environ.get("COORDINATOR_OUTBOX_STALE_HOURS", "24"))
    stale_threshold_seconds = stale_hours * 3600
    now = _time.time()

    for mtime, candidate in entries:
        age_seconds = now - mtime
        age_str = _format_age(age_seconds)
        is_stale = age_seconds > stale_threshold_seconds
        stale_marker = "  [stale]" if is_stale else ""

        topic = candidate.get("topic") or candidate.get("filename") or "?"
        to = candidate.get("to") or "?"
        title = candidate.get("title") or "(no title)"

        print(f"{topic}  {age_str}{stale_marker}  → {to}  :: {title}")

    return 0


def _cmd_discard(args: argparse.Namespace) -> int:
    """Handle: cross-repo-memo discard <topic>

    Removes state/memo-outbox/<topic>.md from the sender repo.
    Missing file → exit non-zero with hint to use 'cross-repo-memo list'.
    Uses FileNotFoundError catch (TOCTOU-safe; not os.path.exists).

    Spec backlink: docs/plans/2026-06-15-cross-repo-memo-draft-lifecycle.md § C3
    """
    topic = args.topic

    # Review: code-reviewer — validate topic slug before path construction to prevent
    # path traversal. Mirrors _cmd_draft and _cmd_send validation.
    if not _TOPIC_SLUG_RE.fullmatch(topic):
        print(
            f"cross-repo-memo discard: invalid topic slug '{topic}'. "
            f"Topic must match [a-z0-9][a-z0-9-]* (lowercase alphanum and dashes only).",
            file=sys.stderr,
        )
        return 2

    sender_root = _current_repo_root()
    if sender_root is None:
        print(
            "cross-repo-memo discard: must be invoked from inside a git repo (sender). "
            "Current cwd is not a git working tree.",
            file=sys.stderr,
        )
        return 2

    outbox_path = os.path.join(sender_root, "state", "memo-outbox", f"{topic}.md")

    try:
        os.remove(outbox_path)
    except FileNotFoundError:
        print(
            f"cross-repo-memo discard: outbox draft '{topic}' not found. "
            f"Use `cross-repo-memo list` to see drafts.",
            file=sys.stderr,
        )
        return 1

    return 0


def _emit_compose_stage_advisory(abs_path: str, *, fm: dict | None = None) -> None:
    """`compose`-stage premise-check advisory — reads the outbox buffer's
    current frontmatter and fires `_print_premise_check_advisory` at it.

    Shared by both `_cmd_compose` call sites: plain `compose` (no `--open`,
    `fm=None` — this function does its own fresh `_parse_outbox_file` read)
    and post-`--open` (`fm` supplied as the caller's already-re-read
    post-edit frontmatter, so this does not re-read a second time and risk
    disagreeing with what the caller just parsed).

    Never blocks, never changes the exit code — same contract as
    `_print_premise_check_advisory` itself; a missing/unparseable draft
    degrades to `_parse_outbox_file`'s `({}, "")` and the advisory's own
    `if not receiver_path: return` guard, never an error.
    """
    if fm is None:
        fm, _ = _parse_outbox_file(abs_path)
    to = fm.get("to")
    if not to:
        return
    scoped_to = _build_scoped_to(
        fm.get("scoped_to_artifact"),
        fm.get("scoped_to_version"),
        fm.get("scoped_to_sha"),
        fm.get("scoped_to_seam"),
    )
    receiver_path, _ = _resolve_receiver_path(to)
    _print_premise_check_advisory(
        to,
        receiver_path or "",
        fm.get("kind"),
        scoped_to,
        stage="compose",
        outbox_path=abs_path,
    )


def _cmd_compose(args: argparse.Namespace) -> int:
    """Handle: cross-repo-memo compose <topic> [--open]

    Default (no flags): print the absolute path of state/memo-outbox/<topic>.md
    and exit 0. This is the safe default — works in any context (agent or human).

    With --open AND $EDITOR set: launch the editor on the outbox file (human
    opt-in only; never fires unconditionally), BLOCK until it exits, then hand
    the edited body to claude-klabauter's `memo.compose` op for the headless frontmatter
    rewrite + prose-first summary re-derivation (footgun #4). A8 strangler
    cutover: this is a genuine behavior UPGRADE — the prior CLI never itself
    wrote frontmatter/summary (that fill-in only ever happened inside the
    human's $EDITOR session); the engine now performs the same rewrite the CLI
    never had a headless path for. The $EDITOR launch itself STAYS CLI-side
    (invocation-by-doctrine — a headless spawn-per-call engine cannot/should
    not own an interactive editor); only the finished-body content-rewrite
    moved to `memo.compose`.

    With --open but $EDITOR unset/empty: print path + warning that $EDITOR is
    unset; exit 0.

    Missing file → exit non-zero with hint to use 'cross-repo-memo list'.

    CRITICAL negative-spec: plain 'compose <topic>' (without --open) MUST NEVER
    exec an editor unconditionally. This is the F12 footgun the plan exists to
    prevent. The --open flag is the human opt-in gate.

    Spec backlink: docs/plans/2026-06-15-cross-repo-memo-draft-lifecycle.md § C3
                   /private/tmp/.../scratchpad/six-verb-cutover-map.md § #6 compose
    """
    topic = args.topic
    open_flag = getattr(args, "open", False)

    # Review: code-reviewer — validate topic slug before path construction to prevent
    # path traversal. Mirrors _cmd_draft and _cmd_send validation.
    if not _TOPIC_SLUG_RE.fullmatch(topic):
        print(
            f"cross-repo-memo compose: invalid topic slug '{topic}'. "
            f"Topic must match [a-z0-9][a-z0-9-]* (lowercase alphanum and dashes only).",
            file=sys.stderr,
        )
        return 2

    sender_root = _current_repo_root()
    if sender_root is None:
        print(
            "cross-repo-memo compose: must be invoked from inside a git repo (sender). "
            "Current cwd is not a git working tree.",
            file=sys.stderr,
        )
        return 2

    outbox_path = os.path.join(sender_root, "state", "memo-outbox", f"{topic}.md")
    abs_path = os.path.abspath(outbox_path)

    if not os.path.isfile(outbox_path):
        print(
            f"cross-repo-memo compose: outbox draft '{topic}' not found. "
            f"Use `cross-repo-memo list` to see drafts.",
            file=sys.stderr,
        )
        return 1

    # Always print the absolute path first — the safe default output.
    print(abs_path)

    # Premise-check advisory at the stage that OWNS the editable buffer — see
    # _print_premise_check_advisory's docstring (lifecycle rule, 2026-08-03).
    # Plain 'compose' (no --open) never touches the buffer, so the advisory
    # reflects whatever frontmatter is on disk right now — the same
    # `_parse_outbox_file` reader `send` uses, so draft/compose/send never
    # disagree on how a hand-edited draft parses. Gated to `not open_flag`:
    # the --open branch below fires its OWN advisory after the edit lands,
    # against the post-edit frontmatter — firing this one too would double-
    # emit (once against the stale pre-edit state, once against the real
    # one). stderr only: this function's own stdout contract is exactly the
    # path line above.
    if not open_flag:
        _emit_compose_stage_advisory(abs_path)

    if open_flag:
        editor = os.environ.get("EDITOR", "").strip()
        if editor:
            # Human opt-in: launch the editor. $EDITOR launch STAYS CLI-side
            # (invocation-by-doctrine — a headless spawn-per-call engine
            # cannot/should not own an interactive editor). A8 strangler
            # cutover changed this from os.execvp (process replacement) to a
            # BLOCKING subprocess.call so control returns here once the
            # editor exits — needed so the frontmatter/summary rewrite below
            # can run against the human's finished edit.
            subprocess.call([editor, abs_path])

            # Read the edited body back and hand it to claude-klabauter's `memo.compose`
            # op for the frontmatter rewrite + prose-first summary
            # re-derivation (footgun #4) — a genuine UPGRADE over the prior
            # CLI, which never itself wrote frontmatter/summary; that fill-in
            # previously happened only inside the human's $EDITOR session.
            # _parse_outbox_file re-reads abs_path fresh (post-edit) and
            # returns (frontmatter_dict, body_str) — only the body half
            # (after the closing '---') is what memo.compose wants; a
            # missing/unparseable file degrades to ({}, "") rather than
            # raising, so an empty edited_body here is a legitimate (if
            # unusual) input the op itself will reject if the draft vanished.
            edited_fm, edited_body = _parse_outbox_file(abs_path)

            # Advisory reflects what the author actually left in the file —
            # fired against `edited_fm` (the post-edit re-read above), never
            # the pre-edit frontmatter (the plain-compose advisory above is
            # gated to `not open_flag` specifically so it never fires here
            # against stale state). Fires regardless of whether the
            # memo.compose call below succeeds: it describes the buffer as
            # the human left it, not the engine's rewrite of it.
            _emit_compose_stage_advisory(abs_path, fm=edited_fm)

            def legacy_compose() -> None:
                """Fail-loud legacy stub — mirrors _send_via_engine.legacy_send.

                A working direct-compute fallback here would silently defeat
                the claude-klabauter-engine integrity cut; this stub only ever raises,
                so State-1 (seam absent), State-2 transport failure, and
                State-2 op-refusal all converge on the same `except
                RuntimeError` handler below.
                """
                raise RuntimeError(
                    "claude-klabauter engine seam not found (CLAUDE_KLABAUTER_ROOT unresolvable or "
                    "coordinator_core.invoke not importable) — the direct-write "
                    "fallback has been retired. Install/configure the claude-klabauter "
                    "engine to compose cross-repo memos."
                )

            try:
                result = cc_invoke.route_mutation(
                    "memo.compose",
                    {"dry_run": False, "topic": topic, "body": edited_body},
                    sender_root,
                    legacy_compose,
                )
            except RuntimeError as exc:
                # Covers seam-absent, transport failure, AND the op's setup-
                # error (missing draft / status != "draft" / unparseable
                # frontmatter — all exit_code:1). Map to DoE exit 1.
                print(f"cross-repo-memo compose: {exc}", file=sys.stderr)
                _print_route_mutation_failure_reasons(exc)
                return 1

            acted = result.get("acted") if isinstance(result, dict) else None
            if not (isinstance(result, dict) and result.get("exit_code") == 0 and acted):
                print(
                    "cross-repo-memo compose: claude-klabauter reported success but "
                    "returned no rewritten draft (empty 'acted') — the edited "
                    "body was saved but frontmatter/summary were NOT updated.",
                    file=sys.stderr,
                )
                return 1
        else:
            # $EDITOR unset or empty — warn, but still exit 0 (path was printed).
            print(
                "Warning: $EDITOR is not set. Set $EDITOR to an editor command "
                "to use `--open` (e.g. export EDITOR=vim).",
                file=sys.stderr,
            )
            # No editor ran, so the buffer is exactly what's on disk right
            # now — the same state the `not open_flag` branch above would
            # have advised on, had --open not been passed.
            _emit_compose_stage_advisory(abs_path)

    return 0


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

# Verbs that trigger subcommand dispatch (not legacy flag-only path).
_SUBCOMMAND_VERBS: frozenset[str] = frozenset({"draft", "compose", "send", "list", "discard"})

# Verbs that plausibly name "close/action an inbound memo" intent — this tool
# has no such verb (it only sends OUTBOUND memos), so these get a pointer at
# archive-stamp-cli's memo.transition verbs instead of the generic unknown-
# subcommand verb list, which is a dead end for a reader who named their
# intent correctly. A genuinely unrecognised typo (e.g. "sned", "lst") still
# falls through to the plain verb-list message below.
_CLOSE_INTENT_VERBS: frozenset[str] = frozenset(
    {"resolve", "action", "close", "actioned", "claim", "release", "transition", "done"}
)


def _build_legacy_parser() -> argparse.ArgumentParser:
    """Build the legacy flag-only parser (--to / --topic / --title / --body-file).

    Unchanged from before the subcommand refactor — all existing automation and
    workday-start surfacer continue to work identically.
    """
    description = textwrap.dedent("""\
        Dispatch a cross-repo memo to a receiver-EM working tree.

        RECEIVER-EM IDENTITY RESOLUTION
        Run `cross-repo-memo --list-receivers` to see every valid --to target on
        this machine — that is the canonical discovery surface.

        The --to argument accepts a receiver-EM identifier resolved two ways:
          1. The canonical central receiver (aliases: claude-central-em, central-em,
             central) → the coordinator doctrine repo (repos.doe_claude in the machine-local
             registry). Run --list-receivers for its current canonical id. Central
             delivery requires repos.doe_claude to be registered; if absent, the CLI
             hard-errors with a remediation message. (Do NOT hand-author into
             ~/.claude/cross-repo/inbox/ — --to claude-central-em still delivers to
             the coordinator doctrine repo, which is the correct delivery surface.)
          2. A sibling repo, by convention:
               <receiver>-em → repos.<receiver, dashes→underscores>
               e.g. <your-repo>-em → repos.<your_repo>
                    <another-repo>-em → repos.<another_repo>
             Any repo registered under repos.<name> is a valid <name>-em receiver
             with no code change — register it (machine-local set repos.<name>
             <path>) and it delivers.

        Divergent identities (doctrine name ≠ repo shortname) are handled by
        RECEIVER_EM_ALIASES in this script — currently only:
          <alias-em> → repos.<canonical_name>

        MACHINE-LOCAL REGISTRY
        This script reads machine-local (via _machine_local.py get repos.<key>)
        to resolve receiver repo paths. It does NOT write to machine-local.
        Reader only — never writes to machine-local. If you find yourself
        wanting to write to machine-local from a script, stop. See:
        docs/wiki/machine-local-registry.md § 5a–5b.

        DIRTY-FILE BACKSTOP
        The receiver-side memo is written to <receiver>/cross-repo/inbox/ but NOT
        committed. The receiver-EM sees it as an untracked file in git status
        at every workstream-start, /workday-start, and commit attempt.
        PM-relay is the primary channel; the dirty file is the structural
        backstop. The receiver edits the memo in place (open → actioned) and
        commits in their own repo — no move, no closure subcommand.

        SINGLE-SURFACE MODEL — NO CENTRAL-ONLY FALLBACK
        Delivery is always one dirty file in the receiver repo. If the receiver
        repo is not registered on this machine, the CLI hard-errors (exit 1) —
        it will not silently degrade to a central-only no-op. Register the repo
        or route the memo via the PM's next session in that repo.
    """)

    parser = argparse.ArgumentParser(
        prog="cross-repo-memo",
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--to",
        required=False,
        default=None,
        metavar="RECEIVER_EM_ID",
        help=(
            "Receiver-EM identifier (e.g. <your-repo>-em, <another-repo>-em, "
            "claude-central-em). Sibling repos resolve to repos.<name> "
            "in the machine-local registry by convention. The central receiver "
            "(aliases: claude-central-em, central-em, central) delivers to the "
            "coordinator doctrine repo (repos.doe_claude "
            "in the machine-local registry) — requires repos.doe_claude to be "
            "registered. Run `cross-repo-memo --list-receivers` to see every valid "
            "target (central + registered siblings). If a repo isn't registered on "
            "this machine, the CLI hard-errors — route via the PM's next session instead."
        ),
    )
    parser.add_argument(
        "--campaign-to",
        action="append",
        default=None,
        metavar="RECEIVER_EM_ID",
        help=(
            "1->N fan-out (DEC-3/C7): repeat to broadcast ONE memo to several "
            "receivers in a single engine invocation, e.g. "
            "--campaign-to em-a --campaign-to em-b --campaign-to em-c. "
            "Mutually exclusive with --to — use one or the other, never both. "
            "Every receiver gets its own independent, individually-atomic "
            "write (same admission bounds as a plain --to send) but shares "
            "one campaign_id frontmatter field (see --campaign-id), so a "
            "rag-side query can later ask 'did all N act?'. A failure "
            "delivering to one receiver does not block delivery to the "
            "others — see the per-receiver outcome printed after send."
        ),
    )
    parser.add_argument(
        "--campaign-id",
        default=None,
        metavar="CAMPAIGN_ID",
        help=(
            "Explicit campaign/correlation id to stamp on every --campaign-to "
            "receiver's memo. Optional — when omitted, the engine generates "
            "one and prints it. Ignored (and rejected) without --campaign-to."
        ),
    )
    parser.add_argument(
        "--check-addressee",
        metavar="RECEIVER_EM_ID",
        default=None,
        help="Resolve THIS repo's own EM identity (from cwd) and compare against the "
             "given receiver id (a memo's `to:` value). Exit 0 = addressed to this repo; "
             "exit 3 = mismatch (addressed elsewhere); exit 4 = receiver unresolvable. "
             "Used by the pickup skill's Memo Branch addressee guard.",
    )
    parser.add_argument(
        "--list-receivers",
        action="store_true",
        default=False,
        help=(
            "Print every valid --to target on this machine and exit. Lists "
            "the canonical central receiver (the coordinator home, always available) first, then "
            "every sibling repo registered under repos.<name>. This is the canonical "
            "receiver-discovery surface — `machine-local keys` omits central by design. "
            "When set, --to/--topic/--title are not required."
        ),
    )
    parser.add_argument(
        "--topic",
        required=False,
        default=None,
        metavar="SLUG",
        help="Short slug used in the memo filename; receiver file is "
        "<date>-<from>-<topic>.md (e.g. 2026-07-07-project-rag-em-gate-check-failures.md). "
        "Required unless --list-receivers is given.",
    )
    parser.add_argument(
        "--title",
        required=False,
        default=None,
        metavar="ONE_LINE",
        help="One-line memo title (appears in frontmatter and workday-start surfacing). "
        "Required unless --list-receivers is given.",
    )
    parser.add_argument(
        "--body-file",
        metavar="PATH",
        default=None,
        help="Path to a file containing the memo body. Use '-' or omit to read from stdin.",
    )
    parser.add_argument(
        "--empty-body",
        action="store_true",
        default=False,
        help=(
            "Explicit opt-in to send a deliberately body-less memo. Without this "
            "flag, an empty body (from stdin, or from a zero-byte --body-file) "
            "fails loud — under Claude Code's Bash tool, stdin is /dev/null, so an "
            "omitted --body-file with no heredoc silently composed a hollow "
            "frontmatter-only memo (2026-07-22 body-drop root-cause verdict: "
            "cross-repo/inbox/2026-07-22-claude-central-em-snippet-sync-adoption-"
            "and-body-drop-verdict.md). Pass --body-file <path> instead if the "
            "body was simply lost in transit."
        ),
    )
    parser.add_argument(
        "--self-receipt",
        action="store_true",
        default=False,
        help=(
            "Dispatcher IS the receiver (central-EM acting in trio repo on its own behalf). "
            "Writes the terminal status=actioned with action_taken_at=<now>. Requires "
            "--decision. Skips PM-relay reminder in stdout."
        ),
    )
    parser.add_argument(
        "--decision",
        choices=["accepted", "declined", "partial", "superseded"],
        default=None,
        help="Decision outcome. Required when --self-receipt is set.",
    )
    parser.add_argument(
        "--supersedes",
        metavar="PATH",
        default=None,
        help=(
            "Path to a prior memo this one supersedes (exercises supersession chain). "
            "Written as `supersedes:` in frontmatter."
        ),
    )
    parser.add_argument(
        "--in-reply-to",
        metavar="MEMO",
        default=None,
        help=(
            "OPTIONAL. Basename (or path — normalized to basename) of the "
            "inbound memo this send replies to, e.g. "
            "2026-07-25-doe-claude-em-some-ask.md. Must name a memo present "
            "in THIS repo's own cross-repo/inbox/ or cross-repo/archive/ "
            "(searched recursively) — checked before anything is written to "
            "the receiver, and the send fails loud on a typo/unresolvable "
            "value rather than silently omitting the field. Written as "
            "`in_reply_to:` in frontmatter; consumed by the pickup skill's "
            "reply-closure check (a citation of the inbound filename in the "
            "memo body still works too — this is a structured alternative, "
            "not a replacement)."
        ),
    )
    parser.add_argument(
        "--summary",
        metavar="TEXT",
        default=None,
        help=(
            f"One-line tl;dr (≤{_SUMMARY_MAX_CHARS} chars). Written as `summary:` in "
            "frontmatter. If omitted, derived from the first non-empty body line. "
            "Truncated to the cap if longer — the CLI never emits a summary that "
            "would fail the schema.js ≤120-char cross-field rule."
        ),
    )
    parser.add_argument(
        "--kind",
        choices=list(_VALID_KINDS),
        default=None,
        help=(
            "Sender-declared memo shape. Enum: ask | consult | fyi | proposal. "
            "ask — sender requests the receiver DO something (action request); "
            "surfaces with urgency, receiver adjudicates-and-owns disposition. "
            "consult — sender requests the receiver's input/opinion; surfaces with "
            "urgency, receiver replies-in-place (captures response in actioned_note), "
            "NO return-memo. "
            "fyi — informational, no action or response expected; quiet log line, "
            "receiver acknowledges only. "
            "proposal — sender presents a concrete change + recommendation; surfaces "
            "with urgency (action-requiring), receiver decides whether to adopt. "
            "When omitted, NO kind: line is written — absence is meaningful: readers "
            "apply an 'ask' default for unlabelled memos (back-compat safe default). "
            "NOTE: 'ack' is NOT a valid kind — acknowledgement is receipt-state "
            "(the receiver flipping status: open → actioned), never a sender-declared kind."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help=(
            "Resolve the receiver and print the target inbox path WITHOUT writing "
            "or committing anything. Use this to discover/verify the correct --to "
            "receiver for a memo before actually sending. No body is read from stdin "
            "in this mode. Legacy-flag-form-only convenience — no equivalent on the "
            "draft/compose/send subcommand lifecycle."
        ),
    )
    # scoped_to sub-fields — OPTIONAL for every kind (presence-triggered
    # completeness, not kind-gated): omit all four and the send is valid
    # regardless of --kind. Supply ANY one of the four and the complete
    # triple (artifact + exactly one of version/sha + seam) is required,
    # else the send fails loud. Mirrors coordinator/bin/lib/schema.js:2290
    # — see _scoped_to_errors. IS now threaded into the composed memo
    # frontmatter (memo_compose.py's compose_memo/compose_frontmatter accept
    # scoped_to; the self-receipt call site assembles it via
    # _build_scoped_to before composing) — these flags feed both the
    # completeness gate AND the delivered value.
    parser.add_argument("--scoped-to-artifact", metavar="ARTIFACT", default=None, help="scoped_to.artifact — the file/contract/schema/subsystem this decision governs")
    parser.add_argument("--scoped-to-version", metavar="VERSION", default=None, help="scoped_to.version — point-in-time pin (mutually exclusive with --scoped-to-sha); use this arm when the artifact is only reachable via a publish mirror, since it is never sha-verified against the receiver's clone")
    parser.add_argument("--scoped-to-sha", metavar="SHA", default=None, help="scoped_to.sha — 7-40 hex chars, point-in-time pin (mutually exclusive with --scoped-to-version)")
    parser.add_argument("--scoped-to-seam", metavar="SEAM", default=None, help="scoped_to.seam — the boundary/interface this decision applies at")
    return parser


def _build_combined_parser(for_help: bool = False) -> argparse.ArgumentParser:
    """Build the combined top-level parser showing both new verbs and legacy form.

    Spec backlink: docs/plans/2026-06-15-cross-repo-memo-draft-lifecycle.md § C1

    This parser is shown for `--help` and for the absent/empty argv[0] case.
    It enumerates draft|compose|send|list|discard alongside the legacy --to form
    so that `cross-repo-memo --help` satisfies AC9.

    The subparsers here are argument-schema stubs only — the actual command
    handlers live in _cmd_draft / _cmd_send_stub etc. and are invoked directly
    from main() after verb detection. This avoids duplicating argument schemas
    in two places while still giving argparse correct subcommand help text.

    for_help=True registers the legacy one-shot flags (--to, --topic, --title,
    --body-file, --summary, --dry-run, --scoped-to-*) directly on THIS parser
    too, purely so they render in the `options:` section of `--help` output —
    they were previously discoverable only by reading _build_legacy_parser's
    source or guessing (see cross-repo/inbox/2026-07-21-claude-klabauter-em-
    cross-repo-memo-help-legacy-flags-undocumented.md). Deliberately NOT
    wired for_help=False (the default): main()'s verb-dispatch call site
    (`combined_parser.parse_args(argv)`) never needs these — legacy-flag
    invocations route to `_build_legacy_parser()` instead — and adding
    same-named optional flags to a parser that also owns subparsers risks
    a flag-before-verb ordering edge case (`--kind X draft ...`) silently
    losing the value to the subparser's own default. Keeping the two call
    shapes (verb-dispatch vs. help-rendering) on separate parser instances
    avoids that risk entirely rather than relying on "nobody does that."
    """
    description = textwrap.dedent("""\
        cross-repo-memo — dispatch cross-repo memos between EM working trees.

        DRAFT LIFECYCLE (canonical multi-line workflow):
          1. draft   <topic> --to <em> --title "<line>" [--summary <s>] [--kind <k>]
                     [--in-reply-to <inbound-memo>]
                     Stage a draft in state/memo-outbox/<topic>.md; prints the path.
          2. compose <topic>
                     Print the outbox path again (--open execs $EDITOR, human opt-in).
          3. send    <topic>
                     Validate frontmatter and dispatch to the receiver repo; removes draft.
          4. list    Enumerate outbox drafts with age (>24h marked stale).
             discard <topic>
                     Remove an outbox draft without sending.

        Stale drafts (>24h) surface at /workstream-start and /workday-start.
        Never write memo bodies to %TEMP% or tasks/ paths — the CLI owns the buffer.

        LEGACY FLAG FORM (preserved — one-shot send for short memos):
          cross-repo-memo --to <em> --topic <slug> --title "<line>" [--body-file <path>]
          (reads body from --body-file or stdin when --body-file is omitted or '-')
          Add --dry-run to preview the resolved receiver + target inbox dir
          without writing/committing anything (legacy-form-only convenience;
          no equivalent on the draft/compose/send subcommand lifecycle).

          --in-reply-to <inbound-memo-basename> is OPTIONAL on both the
          legacy form and draft/send: it links this memo to an inbound one
          this repo actually received (checked against this repo's own
          cross-repo/inbox/ and cross-repo/archive/, fail-loud on a typo),
          so a reply-closure check can find it without depending on a body
          citation of the inbound filename.

          scoped_to is OPTIONAL for every --kind, including ask/proposal — a
          directional/doctrine memo with no point-in-time pin simply omits
          the four --scoped-to-* flags below. But supply ANY ONE of them and
          the complete triple is required: --scoped-to-artifact, exactly one
          of --scoped-to-version/--scoped-to-sha, and --scoped-to-seam —
          else the send fails loud before anything is written.

          If the artifact you're pinning is only reachable through a publish
          mirror (so no sha of it exists in the receiver's own clone),
          --scoped-to-version is the correct arm, not --scoped-to-sha: sha
          verification only fires when --scoped-to-sha is supplied
          (`_verify_scoped_to_sha_resolvable`), so a version pin never
          triggers a receiver-clone lookup that a mirror-only artifact could
          never satisfy.

        Run `cross-repo-memo --list-receivers` to see valid --to targets.
    """)
    epilog = textwrap.dedent("""\
        Example — legacy one-shot send with a complete scoped_to pin:
          cross-repo-memo --to claude-central-em --topic my-topic \\
            --title "One-line title" --kind ask --body-file body.md \\
            --scoped-to-artifact coordinator/bin/cross-repo-memo \\
            --scoped-to-sha 4022cd77 \\
            --scoped-to-seam "cross-repo-memo CLI help/usage surface"

        INBOUND memos (closing one someone sent YOU):
          This tool only sends OUTBOUND memos. To close/action a memo already
          sitting in your own cross-repo/inbox/, use archive-stamp-cli instead:
            archive-stamp-cli resolve-memo cross-repo/inbox/<memo-file>.md
    """)

    parser = argparse.ArgumentParser(
        prog="cross-repo-memo",
        description=description,
        epilog=epilog if for_help else None,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="verb", metavar="VERB")

    if for_help:
        # Legacy one-shot flags — registered HERE (in addition to
        # _build_legacy_parser, which is what actually parses a legacy
        # invocation) purely so they render in this parser's `options:`
        # section for `--help` output. See this function's docstring for
        # why for_help=False (the verb-dispatch path) never adds these.
        parser.add_argument(
            "--to", metavar="RECEIVER_EM_ID", default=None,
            help="[legacy form] Receiver-EM identifier (e.g. <your-repo>-em, "
                 "claude-central-em). Run --list-receivers to see valid targets.",
        )
        parser.add_argument(
            "--campaign-to", action="append", metavar="RECEIVER_EM_ID", default=None,
            help="[legacy form] 1->N fan-out (DEC-3/C7): repeat to broadcast ONE "
                 "memo to several receivers sharing one campaign_id. Mutually "
                 "exclusive with --to.",
        )
        parser.add_argument(
            "--campaign-id", metavar="CAMPAIGN_ID", default=None,
            help="[legacy form] Explicit campaign/correlation id for "
                 "--campaign-to (default: engine-generated). Ignored without "
                 "--campaign-to.",
        )
        parser.add_argument(
            "--topic", metavar="SLUG", default=None,
            help="[legacy form] Short slug used in the memo filename.",
        )
        parser.add_argument(
            "--title", metavar="ONE_LINE", default=None,
            help="[legacy form] One-line memo title.",
        )
        parser.add_argument(
            "--body-file", metavar="PATH", default=None,
            help="[legacy form] Path to a file containing the memo body "
                 "('-' or omit to read from stdin).",
        )
        parser.add_argument(
            "--empty-body", action="store_true", default=False,
            help="[legacy form] Explicit opt-in to send a deliberately body-less "
                 "memo — without it, an empty stdin/--body-file body fails loud.",
        )
        parser.add_argument(
            "--in-reply-to", metavar="MEMO", default=None,
            help="[legacy form] OPTIONAL. Basename of the inbound memo this "
                 "send replies to — must be present in this repo's own "
                 "cross-repo/inbox/ or cross-repo/archive/. Written as "
                 "`in_reply_to:` in frontmatter.",
        )
        parser.add_argument(
            "--summary", metavar="TEXT", default=None,
            help=f"[legacy form] One-line tl;dr (≤{_SUMMARY_MAX_CHARS} chars); "
                 "derived from the first body line if omitted.",
        )
        parser.add_argument(
            "--dry-run", action="store_true", default=False,
            help="[legacy form] Print the resolved receiver + target inbox "
                 "path without writing or committing anything.",
        )
        parser.add_argument(
            "--scoped-to-artifact", metavar="ARTIFACT", default=None,
            help="[legacy form] scoped_to.artifact — the file/contract/schema/"
                 "subsystem this decision governs. Optional for every --kind; "
                 "if you set ANY --scoped-to-* flag, the complete triple "
                 "(artifact + version-xor-sha + seam) is required.",
        )
        parser.add_argument(
            "--scoped-to-version", metavar="VERSION", default=None,
            help="[legacy form] scoped_to.version — point-in-time pin "
                 "(mutually exclusive with --scoped-to-sha).",
        )
        parser.add_argument(
            "--scoped-to-sha", metavar="SHA", default=None,
            help="[legacy form] scoped_to.sha — 7-40 hex chars, point-in-time "
                 "pin (mutually exclusive with --scoped-to-version).",
        )
        parser.add_argument(
            "--scoped-to-seam", metavar="SEAM", default=None,
            help="[legacy form] scoped_to.seam — the boundary/interface this "
                 "decision applies at.",
        )
        parser.add_argument(
            "--supersedes", metavar="PATH", default=None,
            help="[legacy form] Path to a prior memo this one supersedes "
                 "(exercises supersession chain). Written as `supersedes:` "
                 "in frontmatter.",
        )
        parser.add_argument(
            "--self-receipt", action="store_true", default=False,
            help="[legacy form] Dispatcher IS the receiver (central-EM acting "
                 "in trio repo on its own behalf). Writes the terminal "
                 "status=actioned with action_taken_at=<now>. Requires "
                 "--decision.",
        )
        parser.add_argument(
            "--decision",
            choices=["accepted", "declined", "partial", "superseded"],
            default=None,
            help="[legacy form] Decision outcome. Required when --self-receipt "
                 "is set.",
        )

    # draft subparser — argument schema (handler is _cmd_draft)
    draft_p = subparsers.add_parser(
        "draft",
        help="Stage a new draft in state/memo-outbox/<topic>.md",
    )
    draft_p.add_argument("topic", metavar="TOPIC", help="Topic slug (lowercase-alphanum + dashes)")
    draft_p.add_argument("--to", required=True, metavar="RECEIVER_EM_ID", help="Receiver-EM identifier")
    draft_p.add_argument("--title", required=True, metavar="ONE_LINE", help="One-line memo title")
    draft_p.add_argument("--summary", metavar="TEXT", default=None, help=f"One-line tl;dr (≤{_SUMMARY_MAX_CHARS} chars)")
    draft_p.add_argument("--kind", choices=list(_VALID_KINDS), default=None, help="Memo kind (ask | consult | fyi | proposal)")
    draft_p.add_argument(
        "--in-reply-to", metavar="MEMO", default=None,
        help="OPTIONAL. Basename (or path — normalized to basename) of the "
             "inbound memo this draft will reply to when sent. Written as "
             "`in_reply_to:` in the draft's frontmatter and threaded through "
             "`send`; existence against this repo's own cross-repo/inbox/ or "
             "cross-repo/archive/ is checked at send time, not draft time.",
    )
    # scoped_to sub-fields — OPTIONAL for every kind (presence-triggered
    # completeness, not kind-gated): omit all four and the draft is valid
    # regardless of --kind. Supply ANY one of the four and the complete
    # triple (artifact + exactly one of version/sha + seam) is required at
    # send time, else the send fails loud. Mirrors
    # coordinator/bin/lib/schema.js:2290 — see _scoped_to_errors.
    draft_p.add_argument("--scoped-to-artifact", metavar="ARTIFACT", default=None, help="scoped_to.artifact — the file/contract/schema/subsystem this decision governs")
    draft_p.add_argument("--scoped-to-version", metavar="VERSION", default=None, help="scoped_to.version — point-in-time pin (mutually exclusive with --scoped-to-sha); use this arm when the artifact is only reachable via a publish mirror, since it is never sha-verified against the receiver's clone")
    draft_p.add_argument("--scoped-to-sha", metavar="SHA", default=None, help="scoped_to.sha — 7-40 hex chars, point-in-time pin (mutually exclusive with --scoped-to-version)")
    draft_p.add_argument("--scoped-to-seam", metavar="SEAM", default=None, help="scoped_to.seam — the boundary/interface this decision applies at")

    # compose subparser (handler is _cmd_compose)
    compose_p = subparsers.add_parser(
        "compose",
        help="Print outbox path so you can open it in your editor (--open to exec $EDITOR)",
    )
    compose_p.add_argument("topic", metavar="TOPIC", help="Topic slug")
    compose_p.add_argument("--open", action="store_true", default=False, help="Open $EDITOR (human opt-in)")

    # send subparser (handler is _cmd_send)
    send_p = subparsers.add_parser(
        "send",
        help="Validate frontmatter and dispatch the outbox draft to the receiver repo",
    )
    send_p.add_argument("topic", metavar="TOPIC", help="Topic slug")

    # list subparser (handler is _cmd_list)
    subparsers.add_parser(
        "list",
        help="List outbox drafts in the sender repo with age (marks >24h stale)",
    )

    # discard subparser (handler is _cmd_discard)
    discard_p = subparsers.add_parser(
        "discard",
        help="Remove an outbox draft without sending (hard-errors on missing topic)",
    )
    discard_p.add_argument("topic", metavar="TOPIC", help="Topic slug")

    return parser


def _build_parser() -> argparse.ArgumentParser:
    """Return the combined parser (used for --help routing).

    This is now an alias for _build_combined_parser so that callers of the
    legacy _build_parser() name (e.g. tests that call mod._build_parser())
    still work — the combined parser is the new canonical surface.
    """
    return _build_combined_parser()


# ---------------------------------------------------------------------------
# Main dispatch logic
# ---------------------------------------------------------------------------

def _cmd_version() -> int:
    """Print this running script's identity and flag drift from the canonical DoE source.

    Spec backlink: cross-repo/inbox/2026-07-20-claude-klabauter-em-stale-cross-repo-memo-shim-on-path.md
    § Ask 2 ("Consider a version/self-check"). A stale copy on PATH (e.g. a
    machine-local `~/bin/cross-repo-memo` shim) silently implements retired
    routing while looking like a normal invocation — `command -v` resolves to
    whichever copy PATH finds first, not necessarily the canonical
    `<doe-root>/coordinator/bin/cross-repo-memo`. `__file__` here always names
    the file actually executing (the shim, if that's what ran), so comparing
    it against the canonical path turns "silently wrong for weeks" into a
    one-line diagnostic instead of the invisible-until-`diff` failure mode the
    memo describes.
    """
    self_path = os.path.realpath(__file__)
    try:
        with open(self_path, "rb") as fh:
            content = fh.read()
    except OSError as exc:
        print(f"cross-repo-memo --version: could not read {self_path}: {exc}", file=sys.stderr)
        return 1
    digest = hashlib.sha256(content).hexdigest()[:12]
    line_count = content.count(b"\n") + 1

    print(f"cross-repo-memo {digest} ({line_count} lines)")
    print(f"running from: {self_path}")

    doe_root_file = os.path.join(
        os.environ.get("CLAUDE_HOME")
        or os.environ.get("HOME")
        or os.environ.get("USERPROFILE")
        or str(Path.home()),
        ".claude",
        ".doe-root",
    )
    canonical = None
    try:
        with open(doe_root_file, "r", encoding="utf-8") as fh:
            doe_root = fh.read().strip()
        if doe_root:
            canonical = os.path.join(doe_root, "coordinator", "bin", "cross-repo-memo")
    except OSError:
        canonical = None

    if canonical is None:
        print(
            "canonical source: unresolved "
            f"({doe_root_file} not found, empty, or unreadable)"
        )
        return 0

    canonical_real = os.path.realpath(canonical)
    if canonical_real == self_path:
        print(f"canonical source: {canonical} (this IS the canonical copy — OK)")
        return 0

    print(f"canonical source: {canonical}")
    if not os.path.exists(canonical_real):
        print(
            "WARNING: canonical source path does not exist on this machine — "
            "cannot confirm drift, but this is NOT the canonical copy.",
            file=sys.stderr,
        )
        return 2
    print(
        "WARNING: this is NOT the canonical DoE copy — a stale shim may be "
        "shadowing it on PATH (e.g. a machine-local ~/bin/cross-repo-memo). "
        f"Compare with: diff {self_path} {canonical_real}",
        file=sys.stderr,
    )
    return 2


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns exit code (0 = success, non-zero = failure).

    Verb-detection truth table (spec: docs/plans/2026-06-15-cross-repo-memo-draft-lifecycle.md § C1):
      argv[0] ∈ {draft, compose, send, list, discard} → verb dispatch → subparser
      argv[0] == '--version'                           → self-check; exit 0/1/2 (see _cmd_version)
      argv[0] starts with '--'                         → legacy parser (unchanged)
      absent / empty                                   → combined help; exit 0

    The in-CLI PATH-unresolvable self-check retired 2026-07-25 (spec:
    `docs/plans/2026-07-25-posix-bareword-path-provisioning.md` C5): it could
    only fire once this script was already running, so it structurally could
    not catch the failure mode it existed for (`cross-repo-memo: command not
    found`). C1 provisions the settings-home `bin/` onto PATH at install
    time, and C3's `check_bareword_path_provisioning` (in
    `coordinator_core/ops/install_health_run.py`) asserts that provisioning
    took effect, at install time, when it can still be repaired — the layer
    that actually owns this property.
    """
    if argv is None:
        argv = sys.argv[1:]

    # Absent / empty → combined help, exit 0.
    if not argv:
        _build_combined_parser(for_help=True).print_help()
        return 0

    first = argv[0]

    # --version is a discovery-only one-shot (like --help/--list-receivers):
    # short-circuits before verb/legacy dispatch, no send-path validation.
    if first == "--version":
        return _cmd_version()

    # Verb dispatch → subparser.
    if first in _SUBCOMMAND_VERBS:
        combined_parser = _build_combined_parser()
        args = combined_parser.parse_args(argv)
        verb = args.verb
        if verb == "draft":
            return _cmd_draft(args)
        elif verb == "send":
            return _cmd_send(args)
        elif verb == "list":
            return _cmd_list(args)
        elif verb == "discard":
            return _cmd_discard(args)
        elif verb == "compose":
            return _cmd_compose(args)
        else:
            # Should not reach here — argparse would have exited.
            print(f"cross-repo-memo: unknown verb {verb!r}", file=sys.stderr)
            return 2

    # Legacy path: starts with '--' or any unrecognised non-verb.
    # --help routes through combined parser (satisfies AC9), rendered
    # with for_help=True so the legacy one-shot flags are discoverable
    # here too (see _build_combined_parser docstring).
    if first == "--help" or first == "-h":
        _build_combined_parser(for_help=True).print_help()
        return 0

    # Review: code-reviewer — detect likely typo verbs before falling through to legacy
    # parser, which would emit a confusing argparse error about unrecognised flags.
    # A non-flag non-verb token (no leading '--') that isn't in _SUBCOMMAND_VERBS is
    # almost certainly a typo (e.g. "sned", "lst"). Emit a friendly hint and exit 2.
    if not first.startswith("-"):
        if first.lower() in _CLOSE_INTENT_VERBS:
            print(
                f"cross-repo-memo: '{first}' is not a cross-repo-memo verb — "
                f"this tool only sends OUTBOUND memos (draft, compose, send, "
                f"list, discard). To close/action an INBOUND memo already "
                f"sitting in your cross-repo/inbox/, use "
                f"archive-stamp-cli resolve-memo <memo_path> instead:\n"
                f"  archive-stamp-cli resolve-memo cross-repo/inbox/<memo-file>.md",
                file=sys.stderr,
            )
            return 2
        print(
            f"cross-repo-memo: unknown subcommand '{first}'. "
            f"Valid verbs: draft, compose, send, list, discard. "
            f"Run 'cross-repo-memo --help' for the legacy flag-only form.",
            file=sys.stderr,
        )
        return 2

    # All other flag-prefixed args → legacy parser (unchanged behaviour).
    legacy_parser = _build_legacy_parser()
    args = legacy_parser.parse_args(argv)

    # --check-addressee is a discovery-only mode (like --list-receivers): it
    # resolves THIS repo's own EM identity from cwd and compares it against a
    # given receiver id (a memo's `to:` value), then exits before any
    # send-path argument validation. Used by the pickup skill's Memo Branch
    # addressee guard (M-addr) to detect a session actioning a memo addressed
    # to a different repo's EM.
    #
    # Review: the comparison MUST be path-based (realpath of the resolved
    # repo roots), NOT a string compare on the ids — _normalize_receiver_id
    # is only .strip().lower() and does not resolve aliases ("central" /
    # "central-em" both resolve to claude-central-em's repo path). A naive id
    # string compare would false-fire on an aliased `to:` value.
    if args.check_addressee is not None:
        # Review: mirror --to's `not val` empty-string handling — an explicit
        # empty string already fails safe via _resolve_receiver_path("")
        # returning None (exit 4), but give a clearer diagnostic than
        # "receiver '' does not resolve..." for what is a malformed invocation.
        if args.check_addressee.strip() == "":
            print("check-addressee: empty receiver id", file=sys.stderr)
            return 4
        self_root = _current_repo_root()
        if self_root is None:
            print(
                "check-addressee: current directory is not inside a git repo — "
                "cannot resolve self EM identity",
                file=sys.stderr,
            )
            return 1
        # Review: self_em is best-effort/display-only (human-facing verdict
        # lines only) — the exit code below is purely the engine's path-based
        # verdict and does not depend on self_em's accuracy.
        self_em = _sender_em_id()
        to_val = args.check_addressee

        def legacy_check_addressee() -> None:
            """Fail-loud legacy stub — mirrors _send_via_engine.legacy_send.

            A working direct-compute fallback here would silently defeat the
            claude-klabauter-engine integrity cut; this stub only ever raises, so
            State-1 (seam absent), State-2 transport failure, and State-2
            op-refusal all converge on the same `except RuntimeError` handler
            below.
            """
            raise RuntimeError(
                "claude-klabauter engine seam not found (CLAUDE_KLABAUTER_ROOT unresolvable or "
                "coordinator_core.invoke not importable) — the direct-compute "
                "fallback has been retired. Install/configure the claude-klabauter "
                "engine to check memo addressees."
            )

        try:
            result = cc_invoke.route_mutation(
                "memo.check_addressee",
                {"dry_run": True, "to": to_val},
                self_root,
                legacy_check_addressee,
            )
        except RuntimeError as exc:
            print(f"cross-repo-memo check-addressee: {exc}", file=sys.stderr)
            _print_route_mutation_failure_reasons(exc)
            return 1

        # memo.check_addressee is a COMPUTE_ONLY/dry_run-only op — its verdict
        # lives in the dry_run envelope's `candidates` list, NOT `acted`
        # (which is always empty for a dry-run result). This differs from
        # _send_via_engine's `acted`-based extraction — see the op's own
        # docstring (build_dry_run_result contract).
        candidates = result.get("candidates") if isinstance(result, dict) else None
        candidate = candidates[0] if isinstance(candidates, list) and candidates else None
        if not isinstance(candidate, dict):
            print(
                "cross-repo-memo check-addressee: claude-klabauter reported success but "
                "returned no verdict candidate — aborting.",
                file=sys.stderr,
            )
            return 1

        verdict = candidate.get("verdict")
        to_root = candidate.get("to_repo")
        print(f"self: {self_em} ({self_root})")
        print(f"to:   {to_val} ({to_root if to_root is not None else 'UNRESOLVED'})")
        if verdict == "MATCH":
            print("verdict: MATCH — this memo is addressed to this repo")
            return 0
        if verdict == "MISMATCH":
            print(
                f"verdict: MISMATCH — this memo is addressed to {to_val}, not this "
                f"repo ({self_em})"
            )
            return 3
        # UNRESOLVED (or any other/unexpected verdict string — treat as
        # unresolved rather than silently falling through as a MATCH).
        print(
            f"verdict: receiver '{to_val}' does not resolve to a known repo on "
            f"this machine"
        )
        return 4

    # --list-receivers is a discovery-only mode: print every valid --to target
    # (central first, then registered siblings) and exit before any send-path
    # argument validation. This is the canonical answer to "who can I send to?"
    # — the one enumerator that includes the central receiver. A8 strangler
    # cutover: this is now a thin invoke-and-render trampoline onto claude-klabauter's
    # `memo.list` op (enumeration mode, `to` absent) — the engine owns the
    # registry read; the CLI only renders the returned candidates.
    if args.list_receivers:
        self_root = _current_repo_root()
        if self_root is None:
            print(
                "cross-repo-memo --list-receivers: current directory is not "
                "inside a git repo — cannot resolve the claude-klabauter engine seam",
                file=sys.stderr,
            )
            return 1

        def legacy_list_receivers() -> None:
            """Fail-loud legacy stub — mirrors _send_via_engine.legacy_send.

            A working direct-compute fallback here would silently defeat the
            claude-klabauter-engine integrity cut; this stub only ever raises, so
            State-1 (seam absent), State-2 transport failure, and State-2
            op-refusal all converge on the same `except RuntimeError` handler
            below.
            """
            raise RuntimeError(
                "claude-klabauter engine seam not found (CLAUDE_KLABAUTER_ROOT unresolvable or "
                "coordinator_core.invoke not importable) — the direct-compute "
                "fallback has been retired. Install/configure the claude-klabauter "
                "engine to list memo receivers."
            )

        try:
            result = cc_invoke.route_mutation(
                "memo.list",
                {"dry_run": True},
                self_root,
                legacy_list_receivers,
            )
        except RuntimeError as exc:
            # Covers seam-absent, transport failure, AND the op's own hard
            # registry-read failure (exit_code:1 setup-error — route_mutation
            # raises RouteMutationError, a RuntimeError subclass, on any
            # non-zero exit_code). Intended contract change (A8/map §2): the
            # op fails loud here rather than falling back to
            # `_format_receiver_listing`'s prior warn-and-CONTINUE degraded
            # listing — this deliberately kills that footgun.
            print(f"cross-repo-memo --list-receivers: {exc}", file=sys.stderr)
            _print_route_mutation_failure_reasons(exc)
            return 1

        # memo.list is a COMPUTE_ONLY/dry_run-only op — its data lives in the
        # dry_run envelope's `candidates` list, NOT `acted` (always empty for
        # a dry-run result). Same extraction shape as --check-addressee above.
        candidates = result.get("candidates") if isinstance(result, dict) else None
        if not isinstance(candidates, list):
            print(
                "cross-repo-memo --list-receivers: claude-klabauter reported success "
                "but returned no candidate list — aborting.",
                file=sys.stderr,
            )
            return 1
        print(_render_receiver_listing(candidates))
        return 0

    # ── DEC-3/C7: 1->N fan-out (--campaign-to) ────────────────────────────────
    # Self-contained: every return below exits main() directly, so nothing in
    # the singular --to logic further down needs to become list-aware.
    if args.campaign_to is not None:
        if args.to:
            print(
                "cross-repo-memo: --to and --campaign-to are mutually exclusive "
                "— use --to for a single receiver or --campaign-to (repeatable) "
                "for a 1->N broadcast, never both.",
                file=sys.stderr,
            )
            return 2
        campaign_receivers = [r for r in args.campaign_to if r and r.strip()]
        if not campaign_receivers:
            print(
                "cross-repo-memo: --campaign-to requires at least one "
                "non-empty receiver-EM identifier.",
                file=sys.stderr,
            )
            return 2
        if len(campaign_receivers) != len(set(campaign_receivers)):
            print(
                "cross-repo-memo: --campaign-to lists the same receiver more "
                "than once — each receiver may appear at most once per campaign.",
                file=sys.stderr,
            )
            return 2

        campaign_missing = [
            flag
            for flag, val in (("--topic", args.topic), ("--title", args.title))
            if not val
        ]
        if campaign_missing:
            print(
                f"cross-repo-memo: missing required argument(s): "
                f"{', '.join(campaign_missing)}.",
                file=sys.stderr,
            )
            return 2

        if not _TOPIC_SLUG_RE.fullmatch(args.topic):
            print(
                f"cross-repo-memo: invalid --topic {args.topic!r}; must match "
                f"lowercase-alphanum + dashes, start with alphanum (e.g. "
                f"'gate-check-failures').",
                file=sys.stderr,
            )
            return 2

        if args.self_receipt:
            print(
                "cross-repo-memo: --self-receipt is not supported with "
                "--campaign-to (self-receipt is a single-repo terminal-status "
                "write, not a broadcast).",
                file=sys.stderr,
            )
            return 2

        # Same publish-target rejection every --to receiver goes through,
        # applied PER receiver (fail loud before any engine call for a
        # rejected id) — a rejected receiver never reaches the engine, and
        # rejecting it does not block delivery to the remaining receivers.
        campaign_rejected: list[tuple[str, str]] = []
        valid_campaign_receivers: list[str] = []
        for receiver in campaign_receivers:
            if _is_publish_target_em(receiver) and os.environ.get(
                "COORDINATOR_OVERRIDE_PUBLISH_TARGET_RECEIVER"
            ) != "1":
                known = _known_receiver_ids()
                hint = f"\n  Known EM receivers: {', '.join(known)}." if known else ""
                owner = _publish_target_owner(receiver)
                msg = (
                    _home_redirect_rejection_msg(receiver, owner, hint)
                    if _redirect_kind(receiver) == "home"
                    else _publish_target_rejection_msg(receiver, owner, hint)
                )
                campaign_rejected.append((receiver, msg))
                continue
            valid_campaign_receivers.append(receiver)

        for receiver, reason in campaign_rejected:
            print(
                f"cross-repo-memo --campaign-to: refusing {receiver!r}: {reason}",
                file=sys.stderr,
            )

        if not valid_campaign_receivers:
            print(
                "cross-repo-memo --campaign-to: no valid receivers remained "
                "after publish-target rejection — nothing sent.",
                file=sys.stderr,
            )
            return 1

        # Review: code-reviewer (Finding 2) — the four steps below (summary
        # cap, body read, sender-identity guard+warn, scoped_to build+
        # validate) are shared with the ordinary --to path via
        # _check_summary_over_cap / _read_body_from_file_or_stdin /
        # _sender_identity_guard_and_warn / _build_and_validate_scoped_to.
        summary_cap_error = _check_summary_over_cap(args.summary)
        if summary_cap_error is not None:
            print(summary_cap_error, file=sys.stderr)
            return 2

        campaign_body, body_error = _read_body_from_file_or_stdin(
            args.body_file, args.empty_body
        )
        if body_error is not None:
            print(body_error, file=sys.stderr)
            return 2

        campaign_guard_error = _sender_identity_guard_and_warn()
        if campaign_guard_error is not None:
            print(campaign_guard_error, file=sys.stderr)
            return 1
        campaign_sender = _sender_em_id()
        campaign_sender_root = _current_repo_root()

        campaign_scoped_to, campaign_scoped_to_error = _build_and_validate_scoped_to(
            args, error_prefix="refusing --campaign-to send"
        )
        if campaign_scoped_to_error is not None:
            print(campaign_scoped_to_error, file=sys.stderr)
            return 2

        return _send_campaign_via_engine(
            topic=args.topic,
            to_list=valid_campaign_receivers,
            title=args.title,
            body=campaign_body,
            kind=args.kind,
            summary=args.summary,
            supersedes=args.supersedes,
            sender=campaign_sender,
            sender_root=campaign_sender_root,
            campaign_id=args.campaign_id,
            dry_run=args.dry_run,
            scoped_to=campaign_scoped_to,
        )

    if args.campaign_id is not None:
        print(
            "cross-repo-memo: --campaign-id requires --campaign-to (it is "
            "ignored without a fan-out send).",
            file=sys.stderr,
        )
        return 2

    # --to/--topic/--title are required for the send path (made conditionally
    # optional only so --list-receivers can run without them). Enforce here.
    # `not val` treats BOTH None (flag omitted) and "" (explicit empty string)
    # as missing — the error message is the same for both, which is acceptable.
    # A whitespace-only value (e.g. --title "   ") is truthy, so it passes this
    # check; --to's whitespace is caught by the strip() guard just below, and
    # --topic's by the slug regex (_TOPIC_SLUG_RE) further down.
    missing = [
        flag
        for flag, val in (("--to", args.to), ("--topic", args.topic), ("--title", args.title))
        if not val
    ]
    if missing:
        print(
            f"cross-repo-memo: missing required argument(s): {', '.join(missing)}. "
            f"(These are required unless --list-receivers is given. Run "
            f"`cross-repo-memo --list-receivers` to see valid --to targets.)",
            file=sys.stderr,
        )
        return 2

    # Reject an empty/whitespace --to before it derives a degenerate 'repos.' key.
    # Invariant: args.to is guaranteed a non-empty string here — the `missing`
    # check above already returned 2 for both None and "" (via `not val`), so the
    # only values reaching .strip() are truthy strings. Do NOT refactor the
    # `missing` check to skip the falsy/None case without also guarding this line
    # (an AttributeError on None.strip() is the trap that would reintroduce).
    if not args.to.strip():
        print(
            "cross-repo-memo: --to must be a non-empty receiver-EM identifier "
            "(e.g. <your-repo>-em).",
            file=sys.stderr,
        )
        return 2

    # Reject publish-target repos as receivers — they are outward distribution
    # mirrors, not EM working trees. A memo dropped there is invisible to EMs
    # and gets clobbered on the next publish run. See D6.
    # Override: COORDINATOR_OVERRIDE_PUBLISH_TARGET_RECEIVER=1 (rare use — e.g.
    # testing publish mechanics, fixture authoring).
    #
    # Exit-code note (Review: F7 — document deliberate exit-1-for-semantic distinction):
    # exit 1 = delivery-time semantic error (publish-target rejection — valid arg, wrong meaning).
    # exit 2 = argument validation error (empty --to, bad topic slug — malformed input).
    # The distinction is intentional: callers that care about "is this even a real receiver?"
    # can distinguish semantic rejection (1) from input validation failure (2).
    if _is_publish_target_em(args.to) and os.environ.get("COORDINATOR_OVERRIDE_PUBLISH_TARGET_RECEIVER") != "1":
        known = _known_receiver_ids()
        hint = (
            f"\n  Known EM receivers: {', '.join(known)}."
            if known else ""
        )
        owner = _publish_target_owner(args.to)  # non-None: guarded by _is_publish_target_em above
        msg = (
            _home_redirect_rejection_msg(args.to, owner, hint)
            if _redirect_kind(args.to) == "home"
            else _publish_target_rejection_msg(args.to, owner, hint)
        )
        print(msg, file=sys.stderr)
        return 1

    # Validate --topic slug — refuse anything that could path-traverse out of cross-repo/.
    if not _TOPIC_SLUG_RE.fullmatch(args.topic):
        print(
            f"cross-repo-memo: invalid --topic {args.topic!r}; must match "
            f"lowercase-alphanum + dashes, start with alphanum (e.g. "
            f"'gate-check-failures').",
            file=sys.stderr,
        )
        return 2

    # --dry-run: resolve-and-preview only. Runs after the send-trifecta
    # required-args check, the --to empty/strip check, the publish-target
    # rejection, and the --topic slug validation above (so a dry-run benefits
    # from the same input validation a real send gets), but strictly BEFORE
    # the body read below — a resolution probe must never block on stdin or
    # require a piped body. No engine call, no write, no commit. A8 strangler
    # cutover: this is now a thin invoke-and-render trampoline onto claude-klabauter's
    # `memo.list` op (resolution mode, `to` + `topic` supplied) — the engine
    # owns receiver resolution AND the authoritative DR-026 filename; the CLI
    # only renders the returned candidate.
    if args.dry_run:
        # Review: code-reviewer (Finding 2) — run the same sender-identity guard
        # a real send hits, in the same relative position (before anything
        # sender-derived is computed / before the engine call). Without this,
        # --dry-run from a non-git cwd would silently preview a filename
        # containing 'unknown-sender-em' and exit 0, contradicting the "same
        # input validation a real send gets" claim above. Kept CLI-side per
        # A8 map §3 — the op computes `_ENGINE_ACTOR_ID` as the sender it will
        # actually deliver as, independent of this gate; the gate stays
        # because it's what makes --to's `to`/self_root resolvable at all.
        guard_error = _guard_sender_identity_before_delivery()
        if guard_error is not None:
            print(guard_error, file=sys.stderr)
            return 1
        # Guaranteed non-None here — guard_error is None only when
        # _current_repo_root() resolved (see _guard_sender_identity_before_delivery).
        self_root = _current_repo_root()

        def legacy_dry_run() -> None:
            """Fail-loud legacy stub — mirrors _send_via_engine.legacy_send.

            A working direct-compute fallback here would silently defeat the
            claude-klabauter-engine integrity cut; this stub only ever raises, so
            State-1 (seam absent), State-2 transport failure, and State-2
            op-refusal all converge on the same `except RuntimeError` handler
            below.
            """
            raise RuntimeError(
                "claude-klabauter engine seam not found (CLAUDE_KLABAUTER_ROOT unresolvable or "
                "coordinator_core.invoke not importable) — the direct-compute "
                "fallback has been retired. Install/configure the claude-klabauter "
                "engine to preview a memo delivery."
            )

        try:
            result = cc_invoke.route_mutation(
                "memo.list",
                {
                    "dry_run": True,
                    "to": args.to,
                    "topic": args.topic,
                    "from_id": _sender_em_id(),
                },
                self_root,
                legacy_dry_run,
            )
        except RuntimeError as exc:
            print(f"cross-repo-memo --dry-run: {exc}", file=sys.stderr)
            _print_route_mutation_failure_reasons(exc)
            return 1

        # memo.list is a COMPUTE_ONLY/dry_run-only op — its verdict lives in
        # the dry_run envelope's `candidates` list, NOT `acted` (always empty
        # for a dry-run result). Same extraction shape as --check-addressee.
        candidates = result.get("candidates") if isinstance(result, dict) else None
        candidate = candidates[0] if isinstance(candidates, list) and candidates else None
        if not isinstance(candidate, dict):
            print(
                "cross-repo-memo --dry-run: claude-klabauter reported success but "
                "returned no resolution candidate — aborting.",
                file=sys.stderr,
            )
            return 1

        if not candidate.get("resolved"):
            # Render the op's fail-loud note (which carries the C4 "did you
            # mean?" nearest-match suggestion) — the bespoke central-specific
            # remediation text `_print_receiver_unresolved_error` rendered is
            # NOT ported; the op's note is the upgrade (A8 map §3).
            print(
                candidate.get("note")
                or f"cross-repo-memo --dry-run: receiver {args.to!r} did not resolve.",
                file=sys.stderr,
            )
            return 1

        # Filename is now taken directly from the op's `resolved_filename` —
        # claude-klabauter namespaces it by the calling repo's `from_id` sender (passed
        # above in the `memo.list` invoke params), so it matches what `send`
        # would actually write. This replaces the former CLI-side
        # `_memo_filename(args.topic, _sender_em_id())` workaround, which
        # existed only because the op used to namespace by its own
        # `_ENGINE_ACTOR_ID` ("claude-klabauter-engine") instead of the caller's sender
        # (fixed upstream in claude-klabauter commit 85456f96).
        resolved_filename = candidate.get("resolved_filename")
        if not resolved_filename:
            print(
                "cross-repo-memo --dry-run: claude-klabauter returned no "
                "resolved_filename — aborting.",
                file=sys.stderr,
            )
            return 1
        print("cross-repo-memo: DRY RUN — no write, no commit.")
        print(f"receiver repo: {candidate.get('repo_path')}")
        print(f"target inbox dir: {candidate.get('target_inbox')}")
        print(f"filename: {resolved_filename}")
        return 0

    # --self-receipt requires --decision.
    if args.self_receipt and not args.decision:
        print(
            "cross-repo-memo: --self-receipt requires --decision "
            "(accepted|declined|partial)",
            file=sys.stderr,
        )
        return 2

    # Fail loud on an over-cap EXPLICITLY authored --summary rather than
    # silently truncating it mid-sentence. Diverges deliberately from any
    # clamp behavior elsewhere (e.g. a DERIVED summary self-caps via
    # _derive_summary/derive_prose_summary — those stay untouched) — see the
    # 2026-07-22 body-drop verdict memo (cross-repo/inbox/2026-07-22-claude-
    # central-em-snippet-sync-adoption-and-body-drop-verdict.md), which
    # root-caused the delivered hollow memo's 120-char summary to this exact
    # silent-clamp shape.
    # Review: code-reviewer (Finding 2) — shared with the --campaign-to block
    # via _check_summary_over_cap / _read_body_from_file_or_stdin.
    summary_cap_error = _check_summary_over_cap(args.summary)
    if summary_cap_error is not None:
        print(summary_cap_error, file=sys.stderr)
        return 2

    body, body_error = _read_body_from_file_or_stdin(args.body_file, args.empty_body)
    if body_error is not None:
        print(body_error, file=sys.stderr)
        return 2

    # Resolve receiver repo path. _resolve_receiver_path handles both the
    # central special-case (--to claude-central-em / central-em / central →
    # repos.doe_claude, the DoE-claude repo) and the fall-through to the repos.*
    # registry.
    # Spec backlink: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § B2
    receiver_path, receiver_diagnostic_already_printed = _resolve_receiver_path(args.to)

    # Single-surface model: delivery is always one dirty file in the receiver
    # repo. There is NO implicit central fallback — a memo to a repo that isn't
    # on this machine cannot be written, so we hard-error rather than silently
    # degrade. Valid explicit targets include claude-central-em (and aliases
    # central-em, central) which resolve to repos.doe_claude.
    if receiver_path is None:
        if receiver_diagnostic_already_printed:
            # _resolve_receiver_path already emitted a complete, accurate
            # diagnostic (registry-read failure, not a clean key-absence) —
            # _print_receiver_unresolved_error would be a second, misleading
            # diagnostic on top of it.
            return 1
        # Review: code-reviewer (Finding 3) — was a byte-for-byte duplicate of
        # the --dry-run branch's unresolved-receiver messaging; extracted to
        # _print_receiver_unresolved_error so the two can never drift.
        return _print_receiver_unresolved_error(args.to)

    # Review: code-reviewer (Finding 2) — shared with the --campaign-to block
    # via _sender_identity_guard_and_warn (see its docstring for the
    # root-cause: a phantom 'unknown-sender-em' memo was silently delivered
    # from a cwd outside any git repo). No --from override exists to bypass
    # this.
    guard_error = _sender_identity_guard_and_warn()
    if guard_error is not None:
        print(guard_error, file=sys.stderr)
        return 1

    sender = _sender_em_id()
    # Review: code-reviewer (Finding 5) — moved inside the else (ordinary-arm)
    # branch below, immediately before its first use; the self-receipt arm
    # above never consumes sender_root, so computing it unconditionally here
    # ran a needless subprocess on that path.

    # --self-receipt is a distinct write shape memo.send does not support
    # (memo_send.py's own negative-spec: "status is ALWAYS 'open' ... Self-receipt
    # is out of scope for memo.send" — it is a terminal status=actioned +
    # action_taken_at self-stamp, not a receiver-repo delivery). Repointing this
    # arm onto the engine would either silently drop the self-receipt semantics
    # (memo lands status:open, contradicting the caller's --decision) or require
    # engine-side scope this plan's op explicitly excludes. DoE retains the
    # direct-write pipeline for --self-receipt only; the ordinary (non-self-
    # receipt) flag-only send below is the DR-210 graduation target and is
    # repointed onto cc_invoke.route_mutation("memo.send", …), mirroring _cmd_send.
    if args.self_receipt:
        # Single-delivery-copy model: ONE dirty file in receiver's cross-repo/inbox/.
        # No archive copy, no sender-side copy — the send is noted in the sender's
        # workstream-complete notes as a natural part of the session record.
        # B1: target is cross-repo/inbox/<file> (not flat cross-repo/).
        # Spec backlink: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § B1
        filename = _memo_filename(args.topic, sender)
        # DM4: single receiver_side_path variable feeds BOTH the gitignore check
        # (B3) AND the _write_file call — no separately-constructed string that
        # could drift. B1 must land before B3 (ordering constraint in plan § DM4).
        receiver_side_path = os.path.join(receiver_path, "cross-repo", "inbox", filename)

        # B3: gitignore delivery guard — run BEFORE any filesystem mutation.
        # Spec backlink: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § B3
        #
        # The delivery contract is "dirty file → receiver sees it in git status."
        # If the receiver's .gitignore swallows the inbox path, the memo is written
        # but invisible — the sender believes it delivered; the receiver never sees it.
        # Check first (before makedirs in _write_file), hard-error on confirmed ignored.
        #
        # Exit-code semantics for `git check-ignore`:
        #   exit 0  → path IS ignored → hard-error (silent delivery impossible)
        #   exit 1  → path is NOT ignored → proceed
        #   exit 128 / OSError → not a git repo, or git unavailable → PROCEED-not-block
        #     (a non-git receiver cannot gitignore anything; blocking here would
        #      wrongly deny legitimate delivery to a freshly-registered/non-git path)
        #
        # Relative-path form for check-ignore: git -C <root> check-ignore <rel>.
        # git check-ignore is pure pattern matching — does NOT stat the filesystem,
        # so the parent directory need not exist. No TOCTOU concern; no "parent must
        # exist" concern. Running in main() BEFORE _write_file ensures zero filesystem
        # mutation (no makedirs, no file write) on the hard-error path.
        rel_inbox_path = os.path.join("cross-repo", "inbox", filename)
        try:
            gi_result = subprocess.run(
                ["git", "-C", receiver_path, "check-ignore", rel_inbox_path],
                capture_output=True,
            )
            if gi_result.returncode == 0:
                # Path IS gitignored — delivery would be invisible.
                print(
                    f"cross-repo-memo: refusing to deliver to '{receiver_side_path}': "
                    f"it is gitignored in the receiver repo and would be invisible in "
                    f"`git status`. Remediation: fix the receiver's .gitignore — it must "
                    f"not swallow cross-repo/ (global CLAUDE.md § deny-all .gitignore "
                    f"patterns are forbidden).",
                    file=sys.stderr,
                )
                return 1
            # exit 1 → not ignored → proceed; exit 128 → not a git repo → proceed
        except OSError:
            # git not available on PATH → treat as non-git receiver → proceed
            pass

        # Assemble the nested scoped_to dict from the --scoped-to-* flags
        # (same shape the engine path threads via _send_via_engine) BEFORE
        # composing, so the self-receipt memo actually carries the value the
        # gate below requires — the pin used to be validated then discarded
        # because _compose_memo had no scoped_to param at all (Finding 1,
        # 2026-07-21 review); it is now threaded through.
        self_receipt_scoped_to = _build_scoped_to(
            args.scoped_to_artifact,
            args.scoped_to_version,
            args.scoped_to_sha,
            args.scoped_to_seam,
        )

        # sent_by (C7): resolved ONCE here via the same canonical resolver
        # the engine send path uses (_resolve_sent_by mirrors memo_send.py's
        # _resolve_sent_by) and threaded straight into _compose_memo — never
        # re-resolved. Self-receipt is its own sole committer (bypasses the
        # engine entirely — see module docstring), so this is the only place
        # that can ever attach sent_by to a self-receipt memo.
        self_receipt_sent_by = _resolve_sent_by(_current_repo_root())

        receiver_content = _compose_memo(
            title=args.title,
            to=args.to,
            topic=args.topic,
            body=body,
            self_receipt=args.self_receipt,
            decision=args.decision,
            supersedes=args.supersedes,
            summary=args.summary,
            kind=args.kind,
            scoped_to=self_receipt_scoped_to,
            sent_by=self_receipt_sent_by,
        )

        # Fail-closed gate — mirrors coordinator/bin/lib/schema.js:2290
        # (presence-triggered scoped_to completeness, regardless of kind;
        # see _scoped_to_errors).
        # This is the ONE live write path that bypasses the claude-klabauter engine
        # entirely (memo_send.py has no self-receipt support — see
        # `legacy_send`'s docstring on _send_via_engine), so the CLI must
        # enforce the rule itself here: no engine-side validation will ever
        # see this write. Gate immediately before _write_file — NOT inside
        # it (its signature has no access to kind/scoped_to and its job is
        # path-safety + atomic create, kept single-purpose). Validated
        # against the same nested dict just composed into receiver_content
        # (_scoped_to_errors reads the same artifact/version/sha/seam keys
        # whether given the flat CLI-flag shape or _build_scoped_to's nested
        # shape — both are plain dicts with identical key names).
        self_receipt_scoped_to_errors = _scoped_to_errors(
            args.kind,
            self_receipt_scoped_to,
        )
        if self_receipt_scoped_to_errors:
            print(
                "cross-repo-memo: refusing self-receipt send — "
                + "; ".join(self_receipt_scoped_to_errors)
                + " Nothing was written to the receiver inbox.",
                file=sys.stderr,
            )
            return 2

        try:
            _write_file(receiver_side_path, receiver_content, receiver_path)
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 1

        # Commit the delivered memo in the RECEIVER repo — best-effort, never fails the send.
        commit_outcome = _commit_delivered_memo(receiver_path, receiver_side_path, sender, args.title)
        _print_delivery_commit_notice(receiver_path, commit_outcome)

        # Stdout output.
        abs_receiver = os.path.abspath(receiver_side_path)
        print(f"Receiver-side: {abs_receiver}")
        # _commit_delivered_memo (above) already put its own git failure
        # reason on stderr via its WARNING prints (AC7 is satisfied there,
        # not here — this is the fully-local self-receipt path, it has no
        # engine envelope to read a reason off). This read-back only decides
        # the exit code (AC8): degraded (2) on an untracked landing, still 0
        # otherwise — never-fail-the-send stays intact.
        landed = _verify_delivery_landed(receiver_path, abs_receiver)

        return 0 if landed else 2

    # ── Ordinary flag-only send (DR-210 graduation target) ──────────────────
    # Dispatch the write through the claude-klabauter engine via the shared
    # `_send_via_engine` helper, which also backs `_cmd_send` — see that
    # helper's docstring (code-reviewer Finding 2) for why this is no longer
    # a hand-duplicated ~100-line mirror of `_cmd_send`'s dispatch tail.
    # sender_root feeds _send_via_engine's repo_root arg; guarded non-None by
    # _guard_sender_identity_before_delivery above (mirrors _cmd_send's
    # sender_root = _current_repo_root() at ~L2101). Computed here, not
    # unconditionally above the self-receipt branch, since only this
    # (ordinary) arm consumes it (code-reviewer Finding 5).
    sender_root = _current_repo_root()

    # Assemble the nested scoped_to dict from the --scoped-to-* flags (same
    # shape the self-receipt gate above validates) and gate this, the third
    # live send path, against the presence-triggered scoped_to completeness
    # rule — closing the enforcement gap left by C3 (which validated
    # scoped_to on the outbox/self-receipt paths but let this ordinary-flag
    # path through unchecked). See _scoped_to_errors / schema.js:2290.
    # Review: code-reviewer (Finding 2) — shared with the --campaign-to block
    # via _build_and_validate_scoped_to.
    ordinary_scoped_to, ordinary_scoped_to_error = _build_and_validate_scoped_to(
        args, error_prefix="refusing send"
    )
    if ordinary_scoped_to_error is not None:
        print(ordinary_scoped_to_error, file=sys.stderr)
        return 2

    return _send_via_engine(
        topic=args.topic,
        to=args.to,
        title=args.title,
        body=body,
        kind=args.kind,
        summary=args.summary,
        supersedes=args.supersedes,
        sender=sender,
        sender_root=sender_root,
        receiver_path=receiver_path,
        outbox_path=None,
        scoped_to=ordinary_scoped_to,
        in_reply_to=args.in_reply_to,
    )


if __name__ == "__main__":
    _raw_capture = _peek_raw_cmdline_capture()
    try:
        _argv = recover_windows_argv(sys.argv[1:], _LAUNCHER_CMD_NAME)
    except UnsoundRawCmdlineTransport as _exc:
        # C2b: detect-and-record, not refuse -- see the constant/helpers
        # above for the full rationale and flip-condition.
        _record_unsound_raw_cmdline_transport(
            "cross-repo-memo", _exc, _raw_capture
        )
        _argv = sys.argv[1:]
    sys.exit(main(_argv))
