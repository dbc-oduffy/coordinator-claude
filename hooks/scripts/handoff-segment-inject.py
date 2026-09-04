"""UserPromptExpansion auto-fire hook that serves `/handoff`'s residue
segments into the SAME turn the EM's `/handoff` prompt is being expanded
into (naked Python, no bash) -- so the EM never hand-opens a segment file
under `coordinator/skills/handoff/residue/`.

Purpose: a peer authoring pass cut `coordinator/skills/handoff/SKILL.md`
down to a resident core plus a `residue/` directory of case-gated segments
(frozen contract, one file per segment, YAML frontmatter with exactly four
keys: `segment_id`, `case` (`shared|predecessor|dirty-tree|carried-items`),
`class` (`protected|droppable`), `order`). This hook is the retrieval seam
for that split: it resolves which cases are ACTIVE for the current session
(`shared` always; `dirty-tree` from a read-only `git status --porcelain`;
`predecessor`/`carried-items` from the read-only `baton-assemble brief
handoff` CLI), selects every segment whose `case` is active, sorts them
ascending by `order`, and injects the concatenated bodies as one
`additionalContext` envelope. The directory listing under `residue/` IS the
manifest -- there is no separate registry file to keep in sync.

Segment source: `baton-assemble brief handoff`'s decision object carries a
`segments[]` key -- already case-filtered and selected by that CLI's own
engine. `segments_from_engine_brief` prefers it when present and
well-formed (a list; malformed individual entries are dropped, not the
whole engine payload); `main()` falls back to this hook's own local
`load_all_segments(_RESIDUE_DIR)` derivation when the key is absent, the
top-level shape isn't a list, OR the list was non-empty but every entry in
it failed validation (treated as a likely engine-side shape drift, not a
trusted zero-selection -- only a genuinely EMPTY raw list is trusted as
"engine selected zero"). Both paths converge on the SAME
`render_additional_context` budget ladder -- the engine supplies segments,
never the budget policy. `render_additional_context` also still re-applies
this hook's own locally-computed `active_cases` via `select_segments`
against EITHER source -- belt-and-suspenders, not a second case-filtering
authority, so a future reader must not "simplify" it away on the
assumption the engine's filtering alone is sufficient.

Contract (mirrors the sibling hooks in this directory -- pickup-autofire.py,
mise-autofire.py):
  stdin   -- UserPromptExpansion JSON (command_name, command_args,
             command_source, cwd, expansion_type, session_id, prompt_id, ...)
  stdout  -- one `hookSpecificOutput` JSON envelope with `additionalContext`
             when a `handoff`-verb command was matched and at least one
             segment was selected; NOTHING otherwise (silent pass -- a
             non-handoff command, an empty case set with no `shared`
             segment, or a total transport failure, all produce no output)
  exit 0  -- always. This hook is advisory only, read-only end to end, and
             must NEVER block `/handoff` -- see the safety envelope below.

Safety envelope, each clause load-bearing:
  (a) READ-ONLY, END TO END. `baton-assemble brief handoff` is called with
      no artifact-path argument (SKILL.md's own documented "pass nothing --
      self-resolves to the held handoff" form) -- `apply` is NEVER invoked
      from this module, and there is no code path anywhere in this file
      that could reach it. Unlike `pickup-autofire.py`'s twin surface (which
      auto-fires a mutating `apply` half on a clear coast), this hook has NO
      mutating half and must never grow one -- the same discipline
      `mise-autofire.py` documents for its own `mint-run-id`/`brief` pair.
      `git status --porcelain` is the only other subprocess this module
      spawns, and it is inherently read-only.
  (b) EVERY FAILURE MODE DEGRADES TO SILENT PASS. An unresolvable
      `baton-assemble` binary, a non-zero exit, a timeout, malformed JSON,
      a missing/unreadable residue directory, or a single segment with
      malformed frontmatter all fail open -- `main()` wraps the whole
      compute-and-render path in one try/except and never raises. `/handoff`
      fires under context pressure by definition (see SKILL.md's own Step 0
      trigger gate); a hook that hard-fails there is worse than one that
      says nothing.
  (c) DELIBERATE ASYMMETRY from `review-assemble`'s residue engine, which
      fail-louds on a malformed segment (an EM-invoked assembler can afford
      to surface a authoring defect for a human to fix before the run
      continues). This hook is a PROMPT-SURFACE hook, not an EM-invoked
      assembler -- a malformed segment here is silently DROPPED from the
      render (see `_load_segment`), never raised, because there is no human
      turn between this hook firing and the EM's own prompt landing to
      absorb a loud failure. A later reader must not "fix" this into a
      fail-loud without first giving this hook an EM-visible failure channel
      it does not currently have.
  (d) `async: false` -- the injected context must land in the SAME turn the
      EM's `/handoff` prompt is being expanded into. An async fire would
      compute the segment set after the EM has already started acting on
      the prompt, defeating the purpose entirely (same reasoning as
      pickup-autofire.py/mise-autofire.py's own `async: false` entries).
  (e) BUDGET DEGRADE IS VISIBLE, NEVER A SILENT OR MID-BODY EDIT.
      `additionalContext` never exceeds `_CONTEXT_BUDGET_CHARS` (24,000 --
      see that constant's own comment for the derivation; this is NOT the
      280-char guard-prose ceiling `coordinator/tests/test_hook_message_
      budget.py` gates, which governs a different population of hooks
      entirely and does not apply to `additionalContext` injection).
      Over budget, whole `class: droppable` segments are dropped from the
      tail (reverse `order`) before a `class: protected` segment is EVER
      touched; if every droppable segment is gone and the render still
      overflows, whole `class: protected` segments are ALSO dropped from
      the tail, same reverse-order rule -- see `render_additional_context`.
      EVERY drop leaves a visible marker line naming the omitted
      `segment_id` and its file path, so an EM who lost a rule can still go
      get it -- an EM who cannot see a rule was withheld has simply lost
      it, which is the exact failure this whole residue-split workstream
      exists to prevent. This hook NEVER slices anything -- not a segment
      body, not the marker list. The drop loop always leaves at least one
      segment standing, so a single over-budget segment is emitted WHOLE and
      the budget is knowingly overrun: a budget overrun is recoverable, and
      a rule cut mid-sentence -- which reads as a complete rule saying
      something different -- is not. The marker list is bounded by the
      segment count, so it cannot overrun anything on its own.

Install-surface note (recorded, not re-discovered): this hook type
(`UserPromptExpansion`) required `/reload-plugins` before it started firing
in the spike that proved the mechanism -- see pickup-autofire.py's own
module docstring for the same finding; a plain hooks.json edit alone was
not observed to be enough.

Segment-registry-drift, doctrine convention: coordinator/docs/wiki/
coordinator-tripwires.md registers the general convention this hook is an
instance of -- a doctrine skill body that used to load its whole rule corpus
resident at a gate firing under context pressure, corrected by segmenting
into a `residue/` directory with a `case:`-keyed frontmatter contract,
retrieved by an assembler or hook rather than "go open the file".
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except Exception:  # pragma: no cover -- defensive: PyYAML is a hook-venv
    # dependency (enforce-agent-dispatch-mode.py already imports it
    # unconditionally in this same directory), but an isolated test harness
    # or partial deploy must still fail open rather than crash on import.
    yaml = None

# --- Constants ---------------------------------------------------------------

# The bare verb this hook reacts to -- same normalization discipline as
# pickup-autofire.py's `_PICKUP_COMMAND_NAMES` / mise-autofire.py's
# `_MISE_COMMAND_NAMES`.
_HANDOFF_COMMAND_NAMES = frozenset({"handoff"})

# `<repo-or-plugin-root>/coordinator/hooks/scripts/handoff-segment-inject.py`
# -- `parents[3]` is the SAME content-root resolution `_prompt_surface_
# citations.py` (this directory's own wiki/skill-citation guard) already
# uses to reach `coordinator/skills/...`: on a doctrine-repo source checkout
# this resolves to the repo root (`coordinator/` IS the plugin root there);
# on a live plugin install it resolves to the plugin root one level ABOVE
# its own `coordinator/` subdirectory. Either way, joining "coordinator" /
# "skills" / "handoff" / "residue" reaches the same relative location. Never
# a doctrine-repo-root pointer read directly (that breaks on a pure OSS install, which
# has no such pointer) and never a second, independently-invented ladder.
REPO_ROOT = Path(__file__).resolve().parents[3]
_RESIDUE_DIR = REPO_ROOT / "coordinator" / "skills" / "handoff" / "residue"

# Deliberately NOT the 10_000 that pickup-autofire.py / mise-autofire.py
# carry, and the divergence is the point. Those two render narration THEY
# compose -- truncating it costs phrasing. This hook renders peer-authored
# doctrine lifted verbatim out of the skill body, where truncation costs a
# RULE, and a rule cut mid-sentence reads as a complete rule that says
# something else. Derivation: the all-cases-active segment set measures
# 19,451 chars, so this sits above it with headroom -- a backstop against
# pathological growth in the residue directory, never a routine ceiling.
# Baseline for judging that number: the resident body this replaces was
# 30,895 bytes loaded unconditionally on EVERY invocation. Worst case now
# is ~12k resident + ~19.5k injected (roughly parity, and only on a
# predecessor + dirty + carried handoff); the common shared-only case is
# ~12k + ~9k. Raising this constant is cheaper than losing a rule; if the
# residue set ever approaches it, segment further rather than truncating.
_CONTEXT_BUDGET_CHARS = 24_000

#: Emitted in place of any segment the budget ladder drops. A withheld rule
#: an EM can SEE was withheld is recoverable -- they open the named file. A
#: silently dropped one is just gone, which is the exact failure this whole
#: segmentation exists to remove, re-created by a new mechanism.
_OMISSION_MARKER = (
    "_(omitted for context budget: {segment_id} — "
    "coordinator/skills/handoff/residue/{source})_"
)

_VALID_CASES = frozenset({"shared", "predecessor", "dirty-tree", "carried-items"})
_VALID_CLASSES = frozenset({"protected", "droppable"})
_REQUIRED_SEGMENT_KEYS = frozenset({"segment_id", "case", "class", "order"})

_GIT_STATUS_TIMEOUT_SECONDS = 5
_BRIEF_TIMEOUT_SECONDS = 12

# Windows console-subprocess discipline: `python.exe` is a CONSOLE-subsystem
# child. `getattr` resolves to 0 (no-op) on every non-Windows platform --
# same idiom as every sibling hook in this directory.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _normalize_command_name(name: str | None) -> str:
    """Normalize a raw `command_name` payload value to its bare verb.

    Byte-for-byte the same shape as pickup-autofire.py's
    `_normalize_command_name` / mise-autofire.py's own copy -- strips any
    `<namespace>:` prefix by taking the segment after the LAST `:`, so both
    the namespaced plugin-slash-command shape (`"coordinator:handoff"`) and
    a bare typed/projectSettings verb (`"handoff"`) normalize identically.
    Kept as an independent copy rather than a shared import, matching this
    directory's own stated convention (each hook script is a self-contained
    single-file module loaded by path -- see mise-autofire.py's own
    `resolve_settings_home` docstring for the same reasoning applied to a
    different helper). Returns `""` for `None`/non-`str` input.
    """
    if not isinstance(name, str):
        return ""
    return name.rsplit(":", 1)[-1]


# --- COORDINATOR_SETTINGS_HOME resolution (mirrors pickup-autofire.py) ------


def resolve_settings_home() -> Path:
    """Resolve the coordinator-claude settings-home root.

    Precedence: an explicit `COORDINATOR_SETTINGS_HOME` override is used
    AS-IS; otherwise `CLAUDE_HOME` (or `HOME`) joined with the fixed
    `.coordinator-claude-settings` suffix -- bit-for-bit the same precedence
    as pickup-autofire.py / mise-autofire.py's own `resolve_settings_home`.
    """
    override = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if override:
        return Path(override)
    base = os.environ.get("CLAUDE_HOME") or str(Path.home())
    return Path(base) / ".coordinator-claude-settings"


# --- Shared forwarder resolution ---------------------------------------------
_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _forwarder_resolve import forwarder_argv as _forwarder_argv
    from _forwarder_resolve import resolve_forwarder as _resolve_forwarder
except Exception:
    # Defensive fallback -- a deploy missing its sibling _forwarder_resolve.py must
    # degrade to the pre-existing extensionless-only behaviour (which the caller
    # already treats as a fail-open transport failure), never crash on import.
    def _resolve_forwarder(bin_dir, name):  # type: ignore[misc]
        candidate = bin_dir / name
        return candidate if candidate.is_file() else None

    def _forwarder_argv(script_path, tail=()):  # type: ignore[misc]
        # Review: overengineering-reviewer F3 -- see _forwarder_resolve's
        # "Import-fallback contract" docstring section for the rationale.
        raise OSError("forwarder resolution unavailable -- import fallback declined to guess a launch decision")


def resolve_baton_assemble_bin(settings_home: Path) -> "Path | None":
    """Resolve the installed `baton-assemble` forwarder under `settings_home`.
    Returns the extensionless script or the native `.exe`, whichever the install
    carries, or None -- the caller treats a None return as a transport failure and
    fails open, never a crash.

    Probing the extensionless name alone (what this did) resolved nothing on a
    Windows box carrying the native-forwarder generation, silently emptying every
    handoff segment of its predecessor/carried-items. `.cmd` stays deliberately
    unresolved -- see `_forwarder_resolve`'s negative-spec for why."""
    return _resolve_forwarder(settings_home / "bin", "baton-assemble")


def _baton_assemble_argv(script_path: Path, tail: list[str]) -> list[str]:
    """Interpreter prefix iff the resolved variant needs one -- a native `.exe` must
    be launched bare. See `_forwarder_resolve.forwarder_argv`."""
    return _forwarder_argv(script_path, tail)


# --- Repo-root resolution (spawn-free, mirrors pickup-autofire.py) ---------


def _resolve_repo_root() -> "Path | None":
    """Zero-spawn upward walk for a `.git` entry, identical in shape to
    pickup-autofire.py's own `_resolve_repo_root`. Worktrees are banned by
    doctrine (see this repo's CLAUDE.md), so no file-vs-dir branch is
    needed. Returns None when undeterminable -- callers degrade the
    `dirty-tree` case to inactive rather than raising."""
    try:
        cwd = Path.cwd()
    except OSError:
        return None
    try:
        for candidate in (cwd, *cwd.parents):
            if (candidate / ".git").exists():
                return candidate
    except OSError:
        return None
    return None


# --- git status (read-only) -------------------------------------------------


def _git_status_porcelain(repo_root: Path) -> "str | None":
    """`git status --porcelain` in `repo_root`, or None on any failure to
    complete (spawn error, timeout, non-zero exit) -- read-only, never a
    mutating git call."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_STATUS_TIMEOUT_SECONDS,
            creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _is_dirty_tree(repo_root: "Path | None") -> bool:
    if repo_root is None:
        return False
    out = _git_status_porcelain(repo_root)
    return bool(out and out.strip())


# --- baton-assemble brief (read-only) ---------------------------------------


def _run_baton_assemble_brief(script_path: Path) -> "subprocess.CompletedProcess | None":
    """`baton-assemble brief handoff` with NO artifact-path argument --
    SKILL.md's own documented form ("pass nothing -- self-resolves to the
    held handoff"). Returns None on ANY failure to complete the subprocess
    (spawn error, timeout) -- never lets a raw OSError/TimeoutExpired
    escape."""
    try:
        # Review: overengineering-reviewer F3 -- argv computation moved inside
        # the try so a fallback-leg OSError (see _forwarder_resolve) is
        # absorbed by the handler below rather than needing its own guard.
        argv = _baton_assemble_argv(script_path, ["brief", "handoff"])
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_BRIEF_TIMEOUT_SECONDS,
            creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _decode_brief_payload(stdout: str) -> "dict | None":
    """Parse `brief`'s stdout into its decision-object dict, or None on any
    shape mismatch (unparseable JSON, or a non-dict top level) -- fail-open,
    never raises."""
    try:
        obj = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


def predecessor_path_from_brief(brief: dict) -> "str | None":
    """The `artifact.lineage.predecessor` signal named in this hook's own
    dispatch brief -- a non-null value means this session's held handoff
    claim names a predecessor. Accepts either a bare path string (the
    documented shape) or a `{"path": ...}`-wrapped dict (a defensive
    tolerance -- this repo's own decision-object shapes have carried both a
    bare string and a nested dict for related fields elsewhere, e.g.
    pickup-autofire.py's own `artifact.path` handling), so a shape this
    authoring pass could not directly confirm against a live
    `baton-assemble` binary does not silently under-detect the `predecessor`
    case. Returns None for anything else (absent, null, empty, or an
    unrecognized shape) -- fail-open, matching every other predicate in this
    module."""
    artifact = brief.get("artifact")
    if not isinstance(artifact, dict):
        return None
    lineage = artifact.get("lineage")
    if not isinstance(lineage, dict):
        return None
    predecessor = lineage.get("predecessor")
    if isinstance(predecessor, str) and predecessor:
        return predecessor
    if isinstance(predecessor, dict):
        path = predecessor.get("path")
        if isinstance(path, str) and path:
            return path
    return None


# --- Frontmatter parsing (shared by predecessor carried_items lookup and --
# --- residue-segment loading) -----------------------------------------------


def _split_frontmatter(text: str) -> "tuple[dict | None, str]":
    """Split a `---\\n<yaml>\\n---\\n<body>` document into `(frontmatter_dict,
    body)`. Returns `(None, text)` on ANY shape mismatch (no leading `---`
    fence, fewer than two fences, unparseable YAML, or a non-dict parsed
    value, including when PyYAML itself is unavailable) -- fail-open, never
    raises. Callers of this function (`_carried_items_active`,
    `_load_segment`) both treat a `None` frontmatter as "this file/case does
    not resolve", never as an error to surface."""
    if not text.startswith("---"):
        return None, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text
    fm_text, body = parts[1], parts[2]
    if body.startswith("\n"):
        body = body[1:]
    if yaml is None:
        return None, text
    try:
        fm = yaml.safe_load(fm_text)
    except Exception:
        return None, text
    if not isinstance(fm, dict):
        return None, text
    return fm, body


def _carried_items_active(repo_root: "Path | None", predecessor_rel_path: "str | None") -> bool:
    """True iff the predecessor handoff named by `predecessor_rel_path`
    carries a non-empty `carried_items:` frontmatter array
    (`coordinator/schemas/handoff.schema.json`'s `carried_items` field).
    Resolves the predecessor path relative to `repo_root` when available
    (the ordinary case); falls back to treating it as already-resolvable
    (e.g. an absolute path, or a relative path off this process's own cwd)
    when `repo_root` is None, rather than refusing outright. Any read/parse
    failure degrades to False (case inactive) -- fail-open."""
    if not predecessor_rel_path:
        return False
    candidate = (repo_root / predecessor_rel_path) if repo_root is not None else Path(predecessor_rel_path)
    try:
        text = candidate.read_text(encoding="utf-8")
    except OSError:
        return False
    fm, _body = _split_frontmatter(text)
    if not isinstance(fm, dict):
        return False
    items = fm.get("carried_items")
    return isinstance(items, list) and len(items) > 0


# --- Active-case computation --------------------------------------------------


def _compute_active_cases_and_brief(
    repo_root: "Path | None", settings_home: Path
) -> "tuple[set[str], dict | None]":
    """Core of `compute_active_cases`, additionally returning the decoded
    `baton-assemble brief handoff` decision object (or None on any
    transport/shape failure) so `main()` can read its `segments[]` key
    WITHOUT spawning the CLI a second time. `compute_active_cases` itself
    stays a thin wrapper over this so its existing call sites/tests are
    untouched."""
    active: "set[str]" = {"shared"}

    if _is_dirty_tree(repo_root):
        active.add("dirty-tree")

    script_path = resolve_baton_assemble_bin(settings_home)
    if script_path is None:
        return active, None

    result = _run_baton_assemble_brief(script_path)
    if result is None or result.returncode != 0:
        return active, None

    brief = _decode_brief_payload(result.stdout)
    if brief is None:
        return active, None

    predecessor = predecessor_path_from_brief(brief)
    if not predecessor:
        return active, brief
    active.add("predecessor")

    if _carried_items_active(repo_root, predecessor):
        active.add("carried-items")

    return active, brief


def compute_active_cases(repo_root: "Path | None", settings_home: Path) -> "set[str]":
    """The active case set for this hook firing: `shared` unconditionally,
    `dirty-tree` from a read-only `git status --porcelain`, and
    `predecessor`/`carried-items` from the read-only `baton-assemble brief
    handoff` CLI (self-resolving to this session's own held handoff claim,
    per SKILL.md's documented no-argument form). Every external call is
    wrapped to fail open -- an unresolvable CLI, a non-zero exit, or
    malformed JSON simply leaves `predecessor`/`carried-items` inactive
    rather than raising."""
    active, _brief = _compute_active_cases_and_brief(repo_root, settings_home)
    return active


# --- Residue-segment loading (fail-open per clause (c) above) --------------


def _normalize_segment_fields(
    segment_id: object,
    case: object,
    klass: object,
    order: object,
    body: object,
    source: str,
) -> "dict | None":
    """The single validation rule shared by BOTH segment sources -- the
    on-disk residue file (`_load_segment`) and the engine-supplied
    `segments[]` entry (`_load_engine_segment`). Returns None on ANY
    malformed shape: an empty/wrong-typed `segment_id`, a `case` outside
    `_VALID_CASES`, a `class` outside `_VALID_CLASSES`, a non-int `order`,
    or a non-string/empty body. Kept as ONE copy deliberately -- see this
    module's dispatch brief, constraint 2: a second, divergently-drifting
    validator is exactly the defect this factoring exists to prevent."""
    if not (isinstance(segment_id, str) and segment_id):
        return None
    if case not in _VALID_CASES:
        return None
    if klass not in _VALID_CLASSES:
        return None
    if not isinstance(order, int) or isinstance(order, bool):
        return None
    if not isinstance(body, str):
        return None
    body = body.strip("\n")
    if not body:
        return None
    return {
        "segment_id": segment_id,
        "case": case,
        "class": klass,
        "order": order,
        "body": body,
        "source": source,
    }


def _load_segment(path: Path) -> "dict | None":
    """Parse one residue segment file into `{segment_id, case, class, order,
    body}`, or None on ANY malformed shape -- missing/unreadable file,
    missing frontmatter fence, missing one of the four required keys, an
    empty/wrong-typed `segment_id`/`case`, a `class` outside
    `{protected, droppable}`, a non-int `order`, or an empty body. A
    malformed segment is silently DROPPED here (see clause (c) in this
    module's own docstring for why this hook's asymmetry from `review-
    assemble`'s fail-loud residue engine is deliberate, not an oversight)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    fm, body = _split_frontmatter(text)
    if not isinstance(fm, dict):
        return None
    if not _REQUIRED_SEGMENT_KEYS.issubset(fm.keys()):
        return None
    return _normalize_segment_fields(
        fm.get("segment_id"), fm.get("case"), fm.get("class"), fm.get("order"), body, path.name
    )


def _load_engine_segment(entry: object) -> "dict | None":
    """Validate ONE `segments[]` entry handed back by `baton-assemble brief
    handoff` (`{segment_id, case, class, order, content, source_path}`),
    reusing `_normalize_segment_fields` -- the exact same rule the on-disk
    path enforces via `_load_segment`, never a second divergent copy. The
    engine's field is `content`; normalized here, once, to this module's own
    `body` spelling (dispatch brief constraint 3) -- nothing downstream of
    this function ever sees `content`. Returns None on ANY malformed shape:
    non-dict entry, missing one of the four required keys or `content`
    itself, or anything `_normalize_segment_fields` itself rejects. A single
    malformed entry is DROPPED, matching `_load_segment`/`load_all_segments`'s
    own per-item (not per-batch) fail-open convention -- see
    `segments_from_engine_brief` for why the top-level shape check is
    separate from this per-entry one."""
    if not isinstance(entry, dict):
        return None
    if not _REQUIRED_SEGMENT_KEYS.issubset(entry.keys()) or "content" not in entry:
        return None
    source_path = entry.get("source_path")
    source = Path(source_path).name if isinstance(source_path, str) and source_path else "?"
    return _normalize_segment_fields(
        entry.get("segment_id"),
        entry.get("case"),
        entry.get("class"),
        entry.get("order"),
        entry.get("content"),
        source,
    )


def segments_from_engine_brief(brief: object) -> "list[dict] | None":
    """The engine-supplied segment set from a `baton-assemble brief handoff`
    decision object, or None when the caller should fall back to the local
    `residue/` derivation instead (dispatch brief: "prefer the engine's
    `segments[]` when present, and fall back to its existing local
    derivation when absent").

    Returns None (fall back wholesale) when: `brief` is not a dict, the
    `segments` key is absent/null, `segments` is present but is NOT a list
    at all -- that is a top-level SHAPE failure, not a per-item content
    failure, and this hook cannot trust a non-list value enough to iterate
    it -- OR when `segments` IS a non-empty list but EVERY entry in it
    failed `_load_engine_segment` validation. That last case is
    deliberately folded into "fall back," not trusted as "engine selected
    zero": a non-empty raw list that yields zero survivors is far more
    likely to be a shape drift on the engine side (a field rename, an enum
    change) than a genuine zero-segment selection, and trusting it silently
    zeroes every `/handoff` doctrine injection with no signal (review
    finding: 40a7251e2 code-review, Finding 1). The local `load_all_segments`
    derivation is a strictly safer default in that situation.

    Returns a (possibly empty) list when `segments` IS a list AND (it was
    empty to begin with, or at least one entry survived validation): each
    entry is validated independently via `_load_engine_segment` and a
    malformed entry is DROPPED, not treated as cause to abandon the whole
    engine payload -- the same per-item fail-open convention
    `load_all_segments` already applies to the on-disk path (dispatch brief
    constraint 2's chosen answer: drop the entry, not the whole engine
    path). Only a genuinely EMPTY raw `segments` list is trusted as "engine
    legitimately selected zero segments" -- `render_additional_context`
    already treats that empty selection as "inject nothing" per
    constraint 4."""
    if not isinstance(brief, dict):
        return None
    raw = brief.get("segments")
    if not isinstance(raw, list):
        return None
    if not raw:
        return []
    validated = [s for s in (_load_engine_segment(entry) for entry in raw) if s is not None]
    if not validated:
        return None
    return validated


def load_all_segments(residue_dir: Path) -> "list[dict]":
    """Every well-formed segment directly under `residue_dir` (the
    directory listing IS the manifest -- no separate registry file). A
    missing or unreadable directory yields an empty list rather than
    raising."""
    try:
        candidates = sorted(residue_dir.glob("*.md"))
    except OSError:
        return []
    segments: "list[dict]" = []
    for path in candidates:
        segment = _load_segment(path)
        if segment is not None:
            segments.append(segment)
    return segments


# --- Selection + budget-degraded rendering ----------------------------------


def select_segments(segments: "list[dict]", active_cases: "set[str]") -> "list[dict]":
    """Every segment whose `case` is active, ascending by `order`."""
    selected = [s for s in segments if s["case"] in active_cases]
    selected.sort(key=lambda s: s["order"])
    return selected


def render_additional_context(segments: "list[dict]", active_cases: "set[str]") -> str:
    """Render the selected, order-sorted segment bodies (joined by a blank
    line) as the `additionalContext` string, hard-capped at
    `_CONTEXT_BUDGET_CHARS`.

    Degrade ladder, cheapest (least load-bearing) first: whole `class:
    droppable` segments are dropped from the TAIL (reverse `order`) one at a
    time, re-measuring after each drop, before a `class: protected` segment
    is ever touched -- this is the entire reason the `class` field exists
    (see this module's own docstring, clause (e)). Only once every droppable
    segment is spent do `protected` segments drop, also from the tail.

    TWO invariants hold at every rung, and both exist because what is being
    dropped is a RULE:

      1. A drop is never silent. Each dropped segment leaves an
         `_OMISSION_MARKER` line naming its `segment_id` and its file, so an
         EM can see a rule was withheld and go read it. The markers are
         counted against the budget like any other text.
      2. A segment body is never cut mid-sentence. Segments leave whole or
         not at all -- a truncated rule reads as a complete rule that says
         something different, which is worse than an absent one that says so.

    Returns `""` when no segment is selected -- the caller reads that as
    "nothing to inject" and produces no `additionalContext` at all.
    """
    selected = select_segments(segments, active_cases)
    if not selected:
        return ""

    def _render(kept: "list[dict]", dropped: "list[dict]") -> str:
        parts = [s["body"] for s in kept]
        parts.extend(
            _OMISSION_MARKER.format(
                segment_id=s.get("segment_id", "?"),
                source=s.get("source", "?"),
            )
            for s in sorted(dropped, key=lambda s: s["order"])
        )
        return "\n\n".join(parts)

    kept = list(selected)
    dropped: "list[dict]" = []
    rendered = _render(kept, dropped)
    if len(rendered) <= _CONTEXT_BUDGET_CHARS:
        return rendered

    # Droppables first (tail-to-head), then protected on the same rule. The
    # last segment standing is never sliced: an over-budget single segment is
    # emitted whole, because a budget overrun is recoverable and a doctored
    # rule is not.
    for klass in ("droppable", "protected"):
        while len(rendered) > _CONTEXT_BUDGET_CHARS:
            victim = next(
                (i for i in range(len(kept) - 1, -1, -1) if kept[i]["class"] == klass),
                None,
            )
            if victim is None or len(kept) == 1:
                break
            dropped.append(kept.pop(victim))
            rendered = _render(kept, dropped)
        if len(rendered) <= _CONTEXT_BUDGET_CHARS:
            break

    return rendered


# --- Entry point --------------------------------------------------------------


def main(stdin_text: "str | None" = None) -> int:
    try:
        raw = stdin_text if stdin_text is not None else sys.stdin.read()
    except Exception:
        return 0  # fail-open -- stdin unreadable

    try:
        payload = json.loads(raw) if raw else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    command_name = _normalize_command_name(payload.get("command_name"))
    if command_name not in _HANDOFF_COMMAND_NAMES:
        return 0  # not a /handoff invocation -- silent pass

    try:
        repo_root = _resolve_repo_root()
        settings_home = resolve_settings_home()
        active_cases, brief = _compute_active_cases_and_brief(repo_root, settings_home)
        engine_segments = segments_from_engine_brief(brief)
        segments = engine_segments if engine_segments is not None else load_all_segments(_RESIDUE_DIR)
        additional_context = render_additional_context(segments, active_cases)
    except Exception:
        # Total-function guard: an unanticipated defect anywhere in the
        # compute-and-render path must never surface as a raised exception
        # on this hot, context-pressure-gated path -- see this module's own
        # docstring, safety-envelope clause (b).
        return 0

    if not additional_context:
        return 0

    try:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptExpansion",
                        "additionalContext": additional_context,
                    }
                }
            )
        )
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
