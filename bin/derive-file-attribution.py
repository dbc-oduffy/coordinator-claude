#!/usr/bin/env python3
"""
derive-file-attribution.py — Derive session→file attribution from Claude Code transcripts.

Purpose: Reads ~/.claude/projects/<encoded-project>/<session-uuid>.jsonl transcript files
and computes per-(session_id, file_path) attribution rows purely from transcript data.
No hooks, no producers, no writes to state/. Output is a JSON array to stdout.

CLI:
    python3 derive-file-attribution.py --project <root> [--transcript-dir <dir>] [--session <id>]

Importable API:
    from derive_file_attribution import derive_rows, aggregate

Performance target: ≤60s wall-clock over the full ~/.claude transcript set (~628MB, ~198 files).
Achieves this via line-by-line streaming (never json.load a whole file) and a single O(n)
pass per transcript.

Spec backlink: docs/plans/2026-07-02-ccos-6-rehome-attribution-python.md § C1
Ported from: plugins/coordinator/bin/lib/file-attribution/project.mjs

Performance cache (2026-07-29): a full re-scan (read + regex + json.loads every
transcript line, on every invocation, no caching) cost ~2.4s wall against a
representative corpus — too slow for a script `emit()` shells out to on every run
(coordinator_core/ops/emit/sections/file_attribution.py). A prior spike proved a
stat-based per-transcript-file cache sound and byte-identical, but landed it as a
SEPARATE wrapper script (derive-file-attribution-cached.py) that importlib-loaded this
module, to avoid touching the "Do NOT write to state/" ban below. That shape was
rejected: two scripts deriving the same attribution WILL drift (this op's history is a
catalogue of exactly that failure mode), and this producer's consumer
(_PRODUCER_REL in file_attribution.py) would have needed a second entry point to pick
up the speedup at all. The cache is folded in here instead — one producer, one
derivation path, one place that reads transcripts.

Derivation-version note for future editors: `_DERIVATION_VERSION` below MUST be bumped
whenever `derive_attribution`, `process_transcript`, `parse_bash_for_writes`, or any
other function that shapes a per-file cached row changes behavior. The cache's
invalidation predicate is transcript-file (size, mtime_ns) — transcripts are
append-only and untouched by an edit to THIS file, so a stat check alone cannot detect
"the code that turns transcript bytes into rows changed." Every cache entry carries
`_DERIVATION_VERSION`; a mismatch is treated as a full miss for that file, same as an
absent cache. Skipping this bump on a derivation-logic change silently serves
pre-change attributions forever — the exact failure this comment exists to prevent.

Negative-spec:
  - The producer's OUTPUT CONTRACT is unchanged and still disk-write-free: it MUST NOT
    write to state/ or any other work-state artifact, and MUST NOT emit attribution
    output anywhere but stdout as a JSON array. That is what the original "Do NOT write
    to state/" ban protected, and it still holds in full.
  - Narrowed, deliberately, on 2026-07-29 (PM-authorized): the producer MAY maintain its
    own private performance cache under the durable-data plane
    (`$(coordinator-settings-home)/claude-klabauter/file-attribution-cache/`, per
    CLAUDE.md § Durable-data plane) — NOT state/, NOT an ad-hoc `~/` path. This is an
    internal implementation detail of the producer's own runtime, not attribution
    OUTPUT; a cache miss, corrupt/missing/unwritable cache, or a `--no-cache` run all
    fall through to the exact same full-scan derivation and produce byte-identical
    stdout. A future reader should read this as a considered, scoped amendment to the
    original ban, not an erosion of it — the ban on writing attribution DATA to disk
    anywhere but stdout is untouched.
  - Do NOT fabricate a file path on Bash parse ambiguity — emit link_type:unknown +
    file_path:null instead. A wrong path is a harder failure than unknown.
  - Do NOT import or call project.mjs.
  - capture_source MUST be 'derived' for every output row (data comes from transcripts,
    not journal_projection or hook_capture).
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Bumped whenever the derivation logic that shapes a per-transcript-file cached row
# changes — see module docstring "Derivation-version note for future editors".
# v1 -> v2 (2026-07-29): transcript enumeration became recursive one level down into
# `<session>/subagents/agent-*.jsonl` — see DR-244 § Amendment 2026-07-29, Q3. This is
# exactly the "derivation-logic changed, transcript files themselves didn't" case the
# note above warns about: a stale cache would silently keep serving top-level-only rows.
_DERIVATION_VERSION = 2

_CACHE_SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# NON_FILE_SINK_RE — sinks that must never be attributed as a file path.
# Ported from project.mjs lines ~98.
# ---------------------------------------------------------------------------
NON_FILE_SINK_RE = re.compile(
    r'^(/dev/(null|stdout|stderr|stdin|fd/?[0-9]+|[a-z]+[0-9]*)'
    r'|/?proc/'
    r'|&[0-9]+'
    r'|-$)'
)

# ---------------------------------------------------------------------------
# Honesty-marker worst-case ordering (higher index = worse quality).
# Must match the COMPLETENESS_ORDER/CAPTURE_SOURCE_ORDER/PROV_COMPLETENESS_ORDER
# tables in the existing §8.14 aggregator (coordinator/bin/emit-cockpit-snapshot.py).
# ---------------------------------------------------------------------------
COMPLETENESS_ORDER: Dict[str, int] = {'complete': 0, 'partial': 1, 'unknown': 2}
CAPTURE_SOURCE_ORDER: Dict[str, int] = {'journal_projection': 0, 'hook_capture': 1, 'derived': 2}
PROV_COMPLETENESS_ORDER: Dict[str, int] = {'complete': 0, 'unknown': 1}


# ---------------------------------------------------------------------------
# Bash write-redirect parser — ported from project.mjs lines ~98–241.
# Conservative: on ANY path-token ambiguity return a single unknown sentinel.
# Invariant: never fabricate a path.
# ---------------------------------------------------------------------------

def mask_quotes(command: str) -> str:
    """
    Replace quoted spans with spaces so that > inside a string literal is not
    mistaken for a redirect operator. Used only to locate redirect positions;
    the original command is used for token extraction.

    Ported from maskQuotes (project.mjs:105-129).
    """
    # Fast path: no quote characters at all means every char falls through to the
    # `else` branch below unchanged, so the output is byte-identical to the input.
    # Profiled hotspot (2026-07-29): this char-by-char scan was ~24% of total
    # derive-rows wall time; most Bash commands carry no quoting at all.
    if "'" not in command and '"' not in command:
        return command

    result: List[str] = []
    in_single = False
    in_double = False
    i = 0
    while i < len(command):
        c = command[i]
        if c == "'" and not in_double:
            in_single = not in_single
            result.append(' ')
        elif c == '"' and not in_single:
            in_double = not in_double
            result.append(' ')
        elif in_double and c == '\\':
            # Consume the escaped char so it cannot toggle state.
            result.append(' ')
            if i + 1 < len(command):
                i += 1
                result.append(' ')
        elif in_single or in_double:
            result.append(' ')
        else:
            result.append(c)
        i += 1
    return ''.join(result)


def extract_shell_token(command: str, pos: int) -> Tuple[Optional[str], bool, int]:
    """
    Extract the next shell token from command starting at pos.
    Returns (token, is_double_quoted, end_pos).

    Ported from extractShellToken (project.mjs:137-166).
    """
    # Skip leading whitespace (space or tab)
    while pos < len(command) and command[pos] in (' ', '\t'):
        pos += 1
    if pos >= len(command):
        return None, False, pos

    c = command[pos]
    if c == '"':
        chars: List[str] = []
        j = pos + 1
        while j < len(command) and command[j] != '"':
            # Review: code-reviewer (F1) — handle backslash escapes so \" inside a
            # double-quoted redirect target doesn't short-read into a fabricated
            # truncated path. Mirrors mask_quotes semantics; preserves never-fabricate.
            if command[j] == '\\' and j + 1 < len(command):
                j += 1
                chars.append(command[j])
            else:
                chars.append(command[j])
            j += 1
        return ''.join(chars), True, j + 1
    elif c == "'":
        chars = []
        j = pos + 1
        while j < len(command) and command[j] != "'":
            chars.append(command[j])
            j += 1
        return ''.join(chars), False, j + 1
    else:
        chars = []
        j = pos
        while j < len(command) and command[j] not in (' ', '\t', ';', '|', '&', '<', '>'):
            chars.append(command[j])
            j += 1
        return ''.join(chars), False, j


def is_token_ambiguous(token: str, is_double_quoted: bool) -> bool:
    """
    Return True when a redirect target token should not be attributed as a
    concrete file path.

    Double-quoted: shell expands $VAR and `cmd` — ambiguous.
    Unquoted: $, `, *, ?, [, { are all ambiguous.
    Single-quoted: no expansion — $ and other specials are literals (not ambiguous).

    Ported from isTokenAmbiguous (project.mjs:176-182).
    """
    if is_double_quoted:
        return bool(re.search(r'[$`]', token))
    # Unquoted
    return bool(re.search(r'[$`*?\[{]', token))


def parse_bash_for_writes(command: str) -> List[Dict[str, Any]]:
    """
    Parse a Bash command for write operations (> and >> redirects).

    Returns a list containing:
      {'file_path': str, 'ambiguous': False}  — a parseable redirect target
      {'file_path': None, 'ambiguous': True}  — ambiguous; caller emits unknown row

    Non-file sinks (/dev/null etc.) are filtered and produce no entry.
    Empty list means no write pattern was detected — caller emits no row.

    Conservatism rule: on ANY ambiguity return immediately with a single
    {'file_path': None, 'ambiguous': True}. Never accumulate partial results.

    Invariant: never fabricate a path.

    Ported from parseBashForWrites (project.mjs:201-241).
    """
    if not command or not isinstance(command, str):
        return []

    # Fast path: neither '>' (redirect) nor '<' (heredoc `<<`) appears anywhere in the
    # RAW command. Masking never introduces characters, only blanks them out, so if the
    # raw text has zero '>' it cannot contain a redirect after masking either, and if it
    # has zero '<' it cannot contain a heredoc marker after masking either — both of this
    # function's detection branches are therefore guaranteed to find nothing. Skips
    # mask_quotes (profiled hotspot, 2026-07-29) for the ~1/3 of commands that neither
    # redirect nor heredoc.
    if '>' not in command and '<' not in command:
        return []

    masked = mask_quotes(command)

    # Heredoc bodies can contain > that look like redirects but are not.
    # Conservatively mark the whole command as ambiguous.
    if '<<' in masked:
        return [{'file_path': None, 'ambiguous': True}]

    results: List[Dict[str, Any]] = []
    for match in re.finditer(r'>{1,2}', masked):
        op_end = match.end()
        token, is_double_quoted, _ = extract_shell_token(command, op_end)
        if not token:
            continue

        if is_token_ambiguous(token, is_double_quoted):
            # Any ambiguity → immediately return a single unknown sentinel.
            return [{'file_path': None, 'ambiguous': True}]

        # Filter non-file sinks.
        if NON_FILE_SINK_RE.match(token):
            continue

        results.append({'file_path': token, 'ambiguous': False})

    # Multiple non-sink redirects → ambiguous (cannot safely attribute to one file).
    if len(results) > 1:
        return [{'file_path': None, 'ambiguous': True}]

    return results


# ---------------------------------------------------------------------------
# Patch parser — ported from project.mjs lines ~252-269.
# ---------------------------------------------------------------------------

def parse_patch(patch_str: str) -> Tuple[Optional[int], Optional[int], bool]:
    """
    Parse a unified diff patch string.

    Returns (lines_added, lines_removed, is_create).
    Returns (None, None, False) if patch_str is absent or not a string.
    is_create is True when a '--- /dev/null' header is present.

    Ported from parsePatch (project.mjs:252-269).
    """
    if not patch_str or not isinstance(patch_str, str):
        return None, None, False

    lines_added = 0
    lines_removed = 0
    is_create = False

    for line in patch_str.split('\n'):
        if line.startswith('--- /dev/null'):
            is_create = True
            continue
        if line.startswith('+++') or line.startswith('---'):
            continue
        if line.startswith('+'):
            lines_added += 1
        elif line.startswith('-'):
            lines_removed += 1

    return lines_added, lines_removed, is_create


def parse_structured_patch(hunks: Any) -> Tuple[Optional[int], Optional[int]]:
    """
    Count added/removed lines from a Claude Code `structuredPatch` hunk array
    (the shape attached to `toolUseResult.structuredPatch` for Edit/MultiEdit
    tool results — a list of {oldStart, oldLines, newStart, newLines, lines}
    dicts, each `lines` entry prefixed ' '/'+'/'-').

    Returns (None, None) when hunks is absent, not a list, or empty — the
    caller falls back to other line-count sources.
    """
    if not isinstance(hunks, list) or not hunks:
        return None, None

    lines_added = 0
    lines_removed = 0
    for hunk in hunks:
        if not isinstance(hunk, dict):
            continue
        hunk_lines = hunk.get('lines')
        if not isinstance(hunk_lines, list):
            continue
        for line in hunk_lines:
            if not isinstance(line, str):
                continue
            if line.startswith('+'):
                lines_added += 1
            elif line.startswith('-'):
                lines_removed += 1

    return lines_added, lines_removed


# ---------------------------------------------------------------------------
# Attribution derivation — adapted from deriveAttribution (project.mjs:287-432).
# New input adapter for the Claude Code transcript format (.message.content[] tool_use)
# instead of the ccos-4 journal {event_kind:'tool_call'} shape.
# Derivation logic is the same; capture_source is always 'derived'.
# ---------------------------------------------------------------------------

def _result_to_str(result_content: Any) -> str:
    """Normalise a tool_result content block to a plain string."""
    if isinstance(result_content, str):
        return result_content
    if isinstance(result_content, list):
        parts: List[str] = []
        for item in result_content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get('type') == 'text':
                parts.append(item.get('text', ''))
        return '\n'.join(parts)
    return ''


def derive_attribution(
    tool_name: str,
    args: Dict[str, Any],
    tool_use_id: Optional[str],
    result_content: Any,
    session_id: str,
    tool_use_result: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Derive zero or more attribution rows from a single transcript tool_use+result pair.

    link_type derivation:
      Read                              → read
      Edit/Write/MultiEdit/NotebookEdit → edited (operation: create or edit)
      Bash with parseable redirect      → edited (operation: bash)
      Bash with ambiguous token         → unknown (file_path: null)
      Grep/Glob/LS                      → referenced (using the path arg)
      All others                        → [] (no row)

    capture_source is always 'derived' (transcript-derived, not journal_projection).

    tool_use_result is the sibling `toolUseResult` object attached to the
    top-level transcript-line for this tool result (distinct from
    result_content, which is the tool_result content block itself). For
    Edit/Write/MultiEdit/NotebookEdit it carries `structuredPatch` (hunk
    line data) and, for a Write create, the full new-file `content` string —
    the only sources that actually populate lines_added/lines_removed;
    Claude Code never emits a raw unified-diff string as tool_result content.

    Negative-spec: on Bash ambiguity emit unknown+null, never a guessed path.
    """
    result_str = _result_to_str(result_content)

    # -- Read → read --------------------------------------------------------
    if tool_name == 'Read':
        file_path = args.get('file_path')
        if not file_path:
            return []
        bytes_read = len(result_str.encode('utf-8')) if result_str else None
        was_partial = (args.get('offset') is not None or args.get('limit') is not None)
        return [{
            'session_id': session_id,
            'file_path': file_path,
            'link_type': 'read',
            'tool_use_id': tool_use_id,
            'metadata': {
                'toolName': 'Read',
                'bytesRead': bytes_read,
                'wasPartial': was_partial,
            },
            'system': {
                'capture_source': 'derived',
                'completeness': 'complete',
                'provenance_completeness': 'complete',
            },
        }]

    # -- Edit / Write / MultiEdit / NotebookEdit → edited -------------------
    if tool_name in ('Edit', 'Write', 'MultiEdit', 'NotebookEdit'):
        file_path = args.get('file_path')
        if not file_path:
            return []

        lines_added: Optional[int] = None
        lines_removed: Optional[int] = None
        is_create = False

        tur = tool_use_result if isinstance(tool_use_result, dict) else None
        if tur is not None:
            is_create = tur.get('type') == 'create'
            la, lr = parse_structured_patch(tur.get('structuredPatch'))
            if la is not None:
                lines_added = la
                lines_removed = lr
            elif is_create:
                # Write-create hunks are empty (no prior content to diff
                # against) — derive the count from the full new-file body.
                new_content = tur.get('content')
                if isinstance(new_content, str) and new_content:
                    lines_added = new_content.count('\n') + 1
                    lines_removed = 0

        # Fallback: legacy unified-diff-string parse. Claude Code tool_result
        # content is a success string, never a raw diff, in every transcript
        # sampled — this branch is dead in practice but kept in case a future
        # transport ever emits one, so a genuine diff isn't silently dropped.
        if lines_added is None and result_str and result_str.strip().startswith('---'):
            la, lr, ic = parse_patch(result_str)
            if la is not None:
                lines_added = la
                lines_removed = lr
                is_create = is_create or ic

        operation = 'create' if is_create else 'edit'

        return [{
            'session_id': session_id,
            'file_path': file_path,
            'link_type': 'edited',
            'tool_use_id': tool_use_id,
            'metadata': {
                'operation': operation,
                'toolName': tool_name,
                'linesAdded': lines_added,
                'linesRemoved': lines_removed,
            },
            'system': {
                'capture_source': 'derived',
                'completeness': 'complete',
                'provenance_completeness': 'complete',
            },
        }]

    # -- Bash → edited (bash) or unknown ------------------------------------
    if tool_name == 'Bash':
        cmd = args.get('command')
        if not cmd:
            return []

        writes = parse_bash_for_writes(cmd)
        if not writes:
            return []  # No write pattern detected — no row.

        write = writes[0]
        if write['ambiguous']:
            return [{
                'session_id': session_id,
                'file_path': None,
                'link_type': 'unknown',
                'tool_use_id': tool_use_id,
                'metadata': {'toolName': 'Bash', 'bashCommand': cmd},
                'system': {
                    'capture_source': 'derived',
                    'completeness': 'partial',
                    'provenance_completeness': 'complete',
                },
            }]

        return [{
            'session_id': session_id,
            'file_path': write['file_path'],
            'link_type': 'edited',
            'tool_use_id': tool_use_id,
            'metadata': {
                'operation': 'bash',
                'toolName': 'Bash',
                'bashCommand': cmd,
            },
            'system': {
                'capture_source': 'derived',
                'completeness': 'partial',  # bash parse is a heuristic
                'provenance_completeness': 'complete',
            },
        }]

    # -- Grep / Glob / LS → referenced --------------------------------------
    if tool_name in ('Grep', 'Glob', 'LS'):
        file_path = args.get('path') or None
        if not file_path:
            return []
        return [{
            'session_id': session_id,
            'file_path': file_path,
            'link_type': 'referenced',
            'tool_use_id': tool_use_id,
            'metadata': {'mentionContext': None, 'messageIndex': None},
            'system': {
                'capture_source': 'derived',
                'completeness': 'complete',
                'provenance_completeness': 'complete',
            },
        }]

    return []


# ---------------------------------------------------------------------------
# Transcript processor — Claude Code JSONL → raw attribution rows.
# Single streaming pass per file: buffer pending tool_use blocks, process
# when the corresponding tool_result arrives.
# ---------------------------------------------------------------------------

def process_transcript(fpath: str, session_id: str) -> List[Dict[str, Any]]:
    """
    Stream a single Claude Code transcript JSONL file line-by-line.

    Buffers tool_use blocks from assistant messages and matches them to
    tool_result blocks in subsequent user messages to derive attribution rows.

    Performance: O(n) in lines, O(k) memory where k = max in-flight tool calls.

    Review: code-reviewer (F13) — Tool calls buffered in `pending` at end-of-file
    are silently discarded. They represent incomplete (no-result) tool invocations
    and produce no attribution row. This is intentional: no result → no attribution.
    """
    # Pending tool calls: tool_use_id → (tool_name, input_dict)
    pending: Dict[str, Tuple[str, Dict[str, Any]]] = {}
    rows: List[Dict[str, Any]] = []

    with open(fpath, 'r', encoding='utf-8', errors='replace') as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            # Fast path: a transcript line can only ever populate `pending` (via a
            # tool_use block) or resolve an entry from it (via a tool_result block).
            # json.dumps always renders the literal string "tool_use"/"tool_result" as
            # the quoted substring '"tool_use"'/'"tool_result"' wherever it appears in
            # the parsed structure — including as a `type` value — so a line lacking
            # both substrings cannot contain either block anywhere, and skipping the
            # full json.loads for it is guaranteed lossless. A line whose *content*
            # merely mentions one of these words (false positive) still gets parsed,
            # same as today — this can only skip MORE parsing than necessary, never
            # less. Profiled hotspot (2026-07-29): json.loads was ~25% of wall time and
            # ~45% of transcript lines carry neither substring.
            if '"tool_use"' not in line and '"tool_result"' not in line:
                continue
            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue

            obj_type = obj.get('type')
            # toolUseResult is a sibling of `message` on the top-level user
            # transcript line — one per line, since Claude Code emits each
            # tool result as its own user message (never batched). It is
            # NOT part of the tool_result content block itself.
            tool_use_result = obj.get('toolUseResult')

            if obj_type == 'assistant':
                msg = obj.get('message') or {}
                content = msg.get('content')
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get('type') == 'tool_use':
                        tuid = block.get('id')
                        tname = block.get('name', '')
                        tinput = block.get('input') or {}
                        if tuid and tname:
                            pending[tuid] = (tname, tinput)

            elif obj_type == 'user':
                msg = obj.get('message') or {}
                content = msg.get('content')
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get('type') == 'tool_result':
                        tuid = block.get('tool_use_id')
                        if tuid and tuid in pending:
                            tname, tinput = pending.pop(tuid)
                            result_content = block.get('content', '')
                            derived = derive_attribution(
                                tname, tinput, tuid, result_content, session_id,
                                tool_use_result=tool_use_result,
                            )
                            rows.extend(derived)

    return rows


# ---------------------------------------------------------------------------
# Path encoding — matches Claude Code's project-directory naming scheme.
# ---------------------------------------------------------------------------

def encode_project_path(project_root: str) -> str:
    """
    Encode a project root path to the Claude Code transcript subdirectory name.

    Claude Code encodes by replacing every '/' and '.' with '-'.
    Example: /Users/example-operator/.claude → -Users-example-operator--claude
    """
    # Review: code-reviewer (F8) — normalize Windows path separators before encoding
    # so coordinator_root on Windows (C:\Users\...) produces the same encoded form
    # as forward-slash paths (Claude Code encodes all separators as '-').
    #
    # The drive-letter colon is part of that same normalization and is NOT
    # optional: Claude Code encodes `X:\claude-klabauter` as `X--claude-klabauter`
    # (colon AND separator each become '-'), so stripping only the backslash
    # yields `X:-claude-klabauter`, which matches no directory that exists. The
    # miss is silent all the way up — `derive_rows` returns [] for a missing
    # transcript dir, the section porter swallows that into [], and the
    # emission simply carries an empty `file_attributions` collection. That is
    # how 2566 attribution rows disappeared from the cockpit snapshot on
    # 2026-07-28 with no error anywhere in the chain.
    return project_root.replace('\\', '/').replace(':', '-').replace('/', '-').replace('.', '-')


# ---------------------------------------------------------------------------
# Performance cache — per-transcript-file stat cache, durable-data-plane resident.
# See module docstring "Performance cache" / "Derivation-version note" for the full
# soundness argument. Fully self-contained (no coordinator_core import): this module
# must stay runnable via a bare subprocess spawn from any cwd without the repo root
# on sys.path, the same constraint the rest of the file already honours.
# ---------------------------------------------------------------------------

def _require_rooted_env(var: str, raw: str) -> str:
    """Return `raw`, or raise ValueError if it would anchor the cache at the cwd.

    A rooted path ('/srv/x', 'C:\\Users\\x', '\\\\server\\share') is accepted; a
    relative one ('foo', 'C:foo') is not. On Windows a drive letter alone is NOT
    absolute — 'C:foo' means "foo relative to the cwd on drive C:" — so the test is
    `is_absolute() or root`, which accepts a POSIX-style rooted path under a Windows
    interpreter while still rejecting the drive-relative form.

    Inlined mirror of coordinator_core/_settings_home.py::_require_rooted, deliberately
    not imported — see the module-level self-containment note above. Rejecting is the
    point: this producer is spawned as a subprocess with no explicit `cwd=`, so a
    relative override silently relocates the cache with the caller's cwd and the cache
    never hits again. An ignored override is a worse failure than a refused one.
    """
    p = Path(raw)
    if not (p.is_absolute() or p.root):
        raise ValueError(
            f"{var} must be an absolute path; got {raw!r} — a relative value anchors "
            "the attribution cache at a cwd that moves between runs, silently disabling "
            "the cache. (On Windows, a drive letter alone is insufficient — use "
            "'C:\\...' form.)"
        )
    return raw


def _default_cache_dir() -> str:
    """Resolve the durable-data-plane cache directory.

    Mirrors coordinator_core/_settings_home.py's precedence (COORDINATOR_SETTINGS_HOME,
    else CLAUDE_HOME, else Path.home()) AND its rooted-path rejection for both
    overrides, without importing that package — see the module-level self-containment
    note above.

    Review: code-reviewer (Finding 1) — the precedence was mirrored but
    `_require_rooted`'s fail-loud check was not, so a relative override was silently
    accepted and joined against the cwd; see `_require_rooted_env`.
    """
    override = os.environ.get('COORDINATOR_SETTINGS_HOME')
    if override:
        home = _require_rooted_env('COORDINATOR_SETTINGS_HOME', override)
    else:
        claude_home = os.environ.get('CLAUDE_HOME')
        base = (
            _require_rooted_env('CLAUDE_HOME', claude_home)
            if claude_home
            else os.path.expanduser('~')
        )
        home = os.path.join(base, '.coordinator-claude-settings')
    return os.path.join(home, 'claude-klabauter', 'file-attribution-cache')


def _cache_file_path(cache_dir: str, transcript_dir: str) -> str:
    """One cache file per transcript_dir, named by a hash of its path — collision-safe
    across different --project roots and different --transcript-dir overrides alike.
    The cache spans whatever project each caller points at, so a key derived from the
    transcript dir (not the repo) is required — a cache entry for one corpus must never
    be served for another.
    """
    digest = hashlib.sha256(os.path.abspath(transcript_dir).encode('utf-8')).hexdigest()[:32]
    return os.path.join(cache_dir, f'{digest}.json')


def _load_cache(cache_path: str, transcript_dir: str) -> Dict[str, Any]:
    """Load and validate the cache. ANY problem (missing, corrupt, schema mismatch,
    derivation-version mismatch, transcript_dir mismatch, unreadable) yields an empty
    cache — full-scan fallback for every file, never a crash, never a stale hit.
    """
    empty: Dict[str, Any] = {
        'schema_version': _CACHE_SCHEMA_VERSION,
        'derivation_version': _DERIVATION_VERSION,
        'transcript_dir': os.path.abspath(transcript_dir),
        'files': {},
    }
    try:
        with open(cache_path, 'r', encoding='utf-8') as fh:
            obj = json.load(fh)
    except (OSError, ValueError):
        return empty
    if not isinstance(obj, dict):
        return empty
    if obj.get('schema_version') != _CACHE_SCHEMA_VERSION:
        return empty
    if obj.get('derivation_version') != _DERIVATION_VERSION:
        return empty
    if obj.get('transcript_dir') != os.path.abspath(transcript_dir):
        return empty
    files = obj.get('files')
    if not isinstance(files, dict):
        return empty
    return {
        'schema_version': _CACHE_SCHEMA_VERSION,
        'derivation_version': _DERIVATION_VERSION,
        'transcript_dir': os.path.abspath(transcript_dir),
        'files': files,
    }


def _save_cache(cache_path: str, cache_obj: Dict[str, Any]) -> None:
    """Best-effort atomic write (temp file + os.replace, which is atomic on both POSIX
    and Windows — unlike os.rename, which raises on Windows if the destination exists).
    Any failure (read-only dir, disk full, permissions, concurrent writer) is swallowed —
    caching is a pure optimization; failing to persist it must never fail the producer
    run itself, and a killed process leaves only the never-renamed-into-place temp file,
    never a torn cache that a later run would trust.
    """
    try:
        cache_dir = os.path.dirname(cache_path)
        os.makedirs(cache_dir, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix='.file-attribution-cache-', dir=cache_dir)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as fh:
                json.dump(cache_obj, fh, ensure_ascii=False)
            os.replace(tmp_path, cache_path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception:
        return


def _iter_transcript_entries(
    transcript_dir: str,
) -> List[Tuple[str, str, str, str]]:
    """Enumerate every transcript to derive rows from, one level recursive.

    Yields `(cache_key, parent_session_id, row_session_id, fpath)` tuples:
      - top-level `<session>.jsonl`: cache_key == fname, parent_session_id ==
        row_session_id == the session stem.
      - nested `<session>/subagents/agent-*.jsonl`: cache_key is the
        `<session>/subagents/<agent-fname>` relative path (cache-collision-safe
        against a top-level file of the same leaf name); parent_session_id is
        the enclosing top-level session (used for `--session` scoping only);
        row_session_id is the SUBAGENT TRANSCRIPT'S OWN STEM — deliberately not
        collapsed onto the parent, per DR-244 § Amendment 2026-07-29 Q3 (cockpit
        asked for the subagent's own identity to survive rather than being
        pre-aggregated into its parent session).

    Recursion is exactly one level deep (`<session>/subagents/`), not a general
    `os.walk` — this mirrors Claude Code's own on-disk transcript layout and
    avoids picking up unrelated directories a future transcript format might
    place under a session dir.

    Negative-spec: this enumeration used to be non-recursive by "settled intent
    (DR-244)" — a load-bearing comment that DR-244's own 2026-07-29 amendment
    reverses (Q3 is answered: ship the recursive read). Do not restore the
    top-level-only behaviour by citing the original DR-244 text without also
    reading its amendment.
    """
    entries: List[Tuple[str, str, str, str]] = []
    for fname in sorted(os.listdir(transcript_dir)):
        if not fname.endswith('.jsonl'):
            continue
        session_stem = fname[:-len('.jsonl')]
        top_path = os.path.join(transcript_dir, fname)
        entries.append((fname, session_stem, session_stem, top_path))

        subagents_dir = os.path.join(transcript_dir, session_stem, 'subagents')
        if not os.path.isdir(subagents_dir):
            continue
        for sub_fname in sorted(os.listdir(subagents_dir)):
            if not sub_fname.endswith('.jsonl'):
                continue
            sub_session_id = sub_fname[:-len('.jsonl')]
            sub_path = os.path.join(subagents_dir, sub_fname)
            cache_key = os.path.join(session_stem, 'subagents', sub_fname)
            entries.append((cache_key, session_stem, sub_session_id, sub_path))

    return entries


def _derive_rows_from_dir(
    transcript_dir: str,
    session_filter: Optional[str],
    cache_dir: Optional[str],
) -> List[Dict[str, Any]]:
    """Derive rows for every (or one filtered) transcript in transcript_dir, using the
    stat cache when cache_dir is given. Mirrors the pre-cache file loop exactly, adding
    only the per-file cache skip — never changes iteration order or which files are read.

    session_filter narrows to one top-level session (O(1) via string compare against
    parent_session_id from `_iter_transcript_entries`), and also includes that
    session's own `subagents/agent-*.jsonl` transcripts — a `--session` scoped run
    stays scoped to one session's work while still surfacing its subagent touches.
    Caching adds nothing to a single-session run and is skipped to avoid reading (and
    rewriting) the whole full-corpus cache file for one entry.
    """
    if session_filter or not cache_dir:
        all_rows: List[Dict[str, Any]] = []
        for _cache_key, parent_session_id, row_session_id, fpath in _iter_transcript_entries(
            transcript_dir
        ):
            if session_filter and parent_session_id != session_filter:
                continue
            try:
                all_rows.extend(process_transcript(fpath, row_session_id))
            except OSError:
                pass
        return all_rows

    cache_path = _cache_file_path(cache_dir, transcript_dir)
    cache = _load_cache(cache_path, transcript_dir)
    cached_files: Dict[str, Any] = cache['files']

    new_files: Dict[str, Any] = {}
    all_rows = []

    for cache_key, _parent_session_id, row_session_id, fpath in _iter_transcript_entries(
        transcript_dir
    ):
        # Stat BEFORE the read, deliberately: transcripts are append-only, so size is
        # monotonic and the recorded (size, mtime_ns) can only ever be BEHIND the
        # content this pass derives — which forces a miss on the next run rather than
        # serving a stale hit. Statting after the read would record the post-read size
        # against pre-read rows, which is the direction that CAN go stale.
        try:
            st = os.stat(fpath)
        except OSError:
            continue

        entry = cached_files.get(cache_key)
        if (
            isinstance(entry, dict)
            and entry.get('size') == st.st_size
            and entry.get('mtime_ns') == st.st_mtime_ns
            and isinstance(entry.get('rows'), list)
        ):
            rows = entry['rows']
        else:
            try:
                rows = process_transcript(fpath, row_session_id)
            except OSError:
                continue

        new_files[cache_key] = {'size': st.st_size, 'mtime_ns': st.st_mtime_ns, 'rows': rows}
        all_rows.extend(rows)

    _save_cache(cache_path, {
        'schema_version': _CACHE_SCHEMA_VERSION,
        'derivation_version': _DERIVATION_VERSION,
        'transcript_dir': os.path.abspath(transcript_dir),
        'files': new_files,
    })

    return all_rows


# ---------------------------------------------------------------------------
# derive_rows — importable entry point for raw row derivation.
# ---------------------------------------------------------------------------

def derive_rows(
    project_root: str,
    transcript_dir: Optional[str] = None,
    session_filter: Optional[str] = None,
    cache_dir: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Derive all raw attribution rows from Claude Code transcripts for a project.

    Args:
        project_root:    Absolute path to the project root (e.g. /Users/example-operator/.claude).
        transcript_dir:  Override transcript directory. If None, derives from project_root.
        session_filter:  If set, only process the transcript for this session ID.
        cache_dir:       If set, use the per-transcript-file stat cache under this
                          directory (see module docstring "Performance cache"). If None
                          (the importable-API default, unchanged from before caching was
                          added), every call does a full re-derivation with no cache
                          read or write — existing callers of this function are
                          unaffected unless they opt in.

    Returns a flat list of raw per-tool attribution rows (not yet aggregated).

    Performance: streams each .jsonl file line-by-line; skips OSError on unreadable files.
    """
    if transcript_dir is None:
        encoded = encode_project_path(os.path.abspath(project_root))
        transcript_dir = os.path.join(os.path.expanduser('~/.claude/projects'), encoded)

    if not os.path.isdir(transcript_dir):
        return []

    return _derive_rows_from_dir(transcript_dir, session_filter, cache_dir)


# ---------------------------------------------------------------------------
# Aggregate — importable entry point for producing per-(session, file) rows.
# ---------------------------------------------------------------------------

def _worst_marker(order_map: Dict[str, int], a: Optional[str], b: Optional[str]) -> Optional[str]:
    """Return the worse of two honesty-marker values (higher order = worse)."""
    if a is None:
        return b
    if b is None:
        return a
    return a if order_map.get(a, 99) >= order_map.get(b, 99) else b


def aggregate(
    rows: List[Dict[str, Any]],
    *,
    repo: str = '',
    coordinator_root_path: str = '.',
    git_branch: str = '',
    git_sha: str = '',
    observed_at: Optional[str] = None,
    transcript_dir: str = '',
) -> List[Dict[str, Any]]:
    """
    Aggregate raw attribution rows to per-(session_id, file_path) output records.

    Honesty markers (completeness, capture_source, provenance_completeness) use
    worst-case aggregation across all touches of a file within a session —
    same COMPLETENESS_ORDER/CAPTURE_SOURCE_ORDER/PROV_COMPLETENESS_ORDER logic as
    the existing §8.14 aggregator (coordinator/bin/emit-cockpit-snapshot.py).

    - Rows with link_type:unknown and file_path:null are skipped (file_path required).
    - link_type:unknown rows with a non-null file_path count as referenced (forward-compat).
    - capture_source is always 'derived' in the output (overrides any row-level value).

    Returns a list of aggregate output records matching the cockpit file-attribution shape.
    """
    if observed_at is None:
        observed_at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    # keyed by (session_id, file_path)
    agg_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for row in rows:
        file_path = row.get('file_path')
        link_type = row.get('link_type', 'unknown')
        session_id = row.get('session_id', '')

        # Skip rows with null file_path (link_type:unknown forward-compat rows).
        if file_path is None:
            continue
        if not isinstance(file_path, str):
            continue
        # Review: code-reviewer (F14) — filter empty-string paths (e.g. cmd > "")
        # which pass the None and isinstance checks but are not valid file paths.
        if not file_path:
            continue

        sys_block = row.get('system') or {}
        row_completeness = sys_block.get('completeness', 'unknown')
        row_capture_source = sys_block.get('capture_source', 'derived')
        row_prov_completeness = sys_block.get('provenance_completeness', 'unknown')

        key = (session_id, file_path)
        if key not in agg_map:
            agg_map[key] = {
                'session_id': session_id,
                'file_path': file_path,
                'edited_count': 0,
                'read_count': 0,
                'referenced_count': 0,
                'lines_added_total': None,
                'lines_removed_total': None,
                'last_operation': None,
                'completeness': row_completeness,
                # Review: code-reviewer (F2) — capture_source is always 'derived' in
                # the output dict; accumulating it via _worst_marker was dead code
                # (the accumulated value was never read). Removed to avoid misleading
                # future readers.
                'provenance_completeness': row_prov_completeness,
            }
        else:
            # Review: code-reviewer (F12) — use direct dict access here to eliminate
            # the confusing double-binding of 'a' (once inside else, again below).
            # Both bindings pointed at the same dict; the re-assignment was misleading.
            agg_map[key]['completeness'] = _worst_marker(
                COMPLETENESS_ORDER, agg_map[key]['completeness'], row_completeness
            )
            # Review: code-reviewer (F2) — capture_source accumulation removed; output
            # always hardcodes 'derived' (see output block below).
            agg_map[key]['provenance_completeness'] = _worst_marker(
                PROV_COMPLETENESS_ORDER, agg_map[key]['provenance_completeness'], row_prov_completeness
            )

        a = agg_map[key]

        if link_type == 'edited':
            a['edited_count'] += 1
            meta = row.get('metadata') or {}
            la = meta.get('linesAdded')
            lr = meta.get('linesRemoved')
            if isinstance(la, int):
                a['lines_added_total'] = (a['lines_added_total'] or 0) + la
            if isinstance(lr, int):
                a['lines_removed_total'] = (a['lines_removed_total'] or 0) + lr
            op = meta.get('operation')
            if op in ('edit', 'create', 'delete', 'rename', 'bash'):
                a['last_operation'] = op
        elif link_type == 'read':
            a['read_count'] += 1
        elif link_type == 'referenced':
            a['referenced_count'] += 1
        else:
            # link_type:unknown with non-null file_path → referenced (forward-compat).
            a['referenced_count'] += 1

    results: List[Dict[str, Any]] = []
    for (session_id, file_path), a in agg_map.items():
        # Build provenance.path pointing to the transcript file.
        transcript_path = ''
        if transcript_dir:
            raw_path = os.path.join(transcript_dir, f'{session_id}.jsonl')
            home = os.path.expanduser('~')
            transcript_path = (
                '~' + raw_path[len(home):]
                if raw_path.startswith(home)
                else raw_path
            )

        result: Dict[str, Any] = {
            'repo': repo,
            'coordinator_root_path': coordinator_root_path,
            'session_id': session_id,
            'file_path': file_path,
            'edited_count': a['edited_count'],
            'read_count': a['read_count'],
            'referenced_count': a['referenced_count'],
            'lines_added': a['lines_added_total'],
            'lines_removed': a['lines_removed_total'],
            'last_operation': a['last_operation'],
            'completeness': a['completeness'] or 'unknown',
            'capture_source': 'derived',  # MUST be 'derived' for transcript-derived rows
            'provenance_completeness': a['provenance_completeness'] or 'unknown',
            'provenance': {
                'source_kind': 'coordinator_artifact',
                'repo': repo,
                # source_kind:coordinator_artifact is non-git; ProvenanceEnvelope
                # requires ref:null for non-git source_kinds (see
                # artifact-shape-contract.schema.json ~line 4482-4485).
                'ref': None,
                'path': transcript_path,
                'observed_at': observed_at,
                'derivation': 'derived',
                'entity_anchor': None,
            },
        }
        results.append(result)

    return results


# ---------------------------------------------------------------------------
# Git helpers — optional, for CLI provenance metadata.
# ---------------------------------------------------------------------------

def _git_info(project_root: str) -> Tuple[str, str]:
    """Return (branch, sha) from git in project_root. Returns ('', '') on failure."""
    try:
        branch = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        ).stdout.decode().strip()
        sha = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        ).stdout.decode().strip()
        return branch, sha
    except Exception:
        return '', ''


def _repo_name(project_root: str) -> str:
    """Derive a short repo name from the project root path (last path component)."""
    return os.path.basename(project_root.rstrip('/\\')) or project_root


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    """
    CLI: derive-file-attribution.py --project <root> [--transcript-dir <dir>]
                                    [--session <id>] [--repo-name <name>]
                                    [--git-branch <b>] [--git-sha <sha>]
                                    [--observed-at <iso>]

    Prints a JSON array of aggregate attribution rows to stdout.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog='derive-file-attribution.py',
        description='Derive session→file attribution from Claude Code transcripts.',
        epilog='Outputs a JSON array of aggregate attribution rows to stdout.',
    )
    parser.add_argument(
        '--project', required=True,
        help='Project root path (e.g. /Users/example-operator/.claude)',
    )
    parser.add_argument(
        '--transcript-dir',
        help='Override transcript directory (default: ~/.claude/projects/<encoded-project>)',
    )
    parser.add_argument(
        '--session',
        help='Only process the transcript for this session ID',
    )
    parser.add_argument(
        '--repo-name',
        help='Repo name for provenance (default: last component of --project)',
    )
    parser.add_argument(
        '--git-branch',
        help='Git branch for provenance (default: derived from --project)',
    )
    parser.add_argument(
        '--git-sha',
        help='Git SHA for provenance (default: derived from --project)',
    )
    parser.add_argument(
        '--observed-at',
        help='Observed-at timestamp ISO8601 (default: now)',
    )
    parser.add_argument(
        '--cache-dir',
        default=None,
        help=(
            'Override the performance-cache directory (default: durable-data-plane '
            'precedence — $COORDINATOR_SETTINGS_HOME, else $CLAUDE_HOME, else '
            '~/.coordinator-claude-settings — /claude-klabauter/file-attribution-cache/).'
        ),
    )
    parser.add_argument(
        '--no-cache',
        action='store_true',
        help='Bypass the performance cache entirely; always does a full re-derivation.',
    )
    args = parser.parse_args(argv)

    project_root = os.path.abspath(args.project)

    transcript_dir = args.transcript_dir
    if not transcript_dir:
        encoded = encode_project_path(project_root)
        transcript_dir = os.path.join(
            os.path.expanduser('~/.claude/projects'), encoded
        )

    repo = args.repo_name or _repo_name(project_root)

    git_branch = args.git_branch or ''
    git_sha = args.git_sha or ''
    if not git_branch or not git_sha:
        b, s = _git_info(project_root)
        git_branch = git_branch or b
        git_sha = git_sha or s

    observed_at = args.observed_at or datetime.now(timezone.utc).strftime(
        '%Y-%m-%dT%H:%M:%SZ'
    )

    cache_dir = None if args.no_cache else (args.cache_dir or _default_cache_dir())

    rows = derive_rows(
        project_root,
        transcript_dir=transcript_dir,
        session_filter=args.session,
        cache_dir=cache_dir,
    )

    result = aggregate(
        rows,
        repo=repo,
        git_branch=git_branch,
        git_sha=git_sha,
        observed_at=observed_at,
        transcript_dir=transcript_dir,
    )

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
