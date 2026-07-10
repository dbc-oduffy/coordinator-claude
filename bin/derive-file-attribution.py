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

Negative-spec:
  - Do NOT write to state/ or any other disk location.
  - Do NOT fabricate a file path on Bash parse ambiguity — emit link_type:unknown +
    file_path:null instead. A wrong path is a harder failure than unknown.
  - Do NOT import or call project.mjs.
  - capture_source MUST be 'derived' for every output row (data comes from transcripts,
    not journal_projection or hook_capture).
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


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
# tables in the existing §8.14 aggregator (emit-cockpit-snapshot.sh lines ~2224-2226).
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

        # Attempt patch parse when result looks like a unified diff.
        # In practice Claude Code transcripts carry success strings, not patches,
        # so line counts will usually remain None (spec: "if absent, leave null").
        if result_str and result_str.strip().startswith('---'):
            la, lr, ic = parse_patch(result_str)
            if la is not None:
                lines_added = la
                lines_removed = lr
                is_create = ic

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
            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue

            obj_type = obj.get('type')

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
                                tname, tinput, tuid, result_content, session_id
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
    return project_root.replace('\\', '/').replace('/', '-').replace('.', '-')


# ---------------------------------------------------------------------------
# derive_rows — importable entry point for raw row derivation.
# ---------------------------------------------------------------------------

def derive_rows(
    project_root: str,
    transcript_dir: Optional[str] = None,
    session_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Derive all raw attribution rows from Claude Code transcripts for a project.

    Args:
        project_root:    Absolute path to the project root (e.g. /Users/example-operator/.claude).
        transcript_dir:  Override transcript directory. If None, derives from project_root.
        session_filter:  If set, only process the transcript for this session ID.

    Returns a flat list of raw per-tool attribution rows (not yet aggregated).

    Performance: streams each .jsonl file line-by-line; skips OSError on unreadable files.
    """
    if transcript_dir is None:
        encoded = encode_project_path(os.path.abspath(project_root))
        transcript_dir = os.path.join(os.path.expanduser('~/.claude/projects'), encoded)

    if not os.path.isdir(transcript_dir):
        return []

    all_rows: List[Dict[str, Any]] = []

    for fname in sorted(os.listdir(transcript_dir)):
        if not fname.endswith('.jsonl'):
            continue
        session_id = fname[:-len('.jsonl')]
        if session_filter and session_id != session_filter:
            continue
        fpath = os.path.join(transcript_dir, fname)
        try:
            rows = process_transcript(fpath, session_id)
            all_rows.extend(rows)
        except OSError:
            pass

    return all_rows


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
    the existing §8.14 aggregator (emit-cockpit-snapshot.sh lines ~2224-2248).

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
                'ref': {'branch': git_branch, 'sha': git_sha},
                'path': transcript_path,
                'observed_at': observed_at,
                'derivation': 'derived',
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

    rows = derive_rows(
        project_root,
        transcript_dir=transcript_dir,
        session_filter=args.session,
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
