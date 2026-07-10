'use strict';
/**
 * nudge-em-code-dispatch.js — PreToolUse hook that offers dispatch over inline
 * code-file authoring when the EM (main-agent) writes a non-doc/data file.
 *
 * Design-as-offers: leads with the dispatcher path (/execute-plan, fan-out wave)
 * before naming the inline carve-out.  NEVER exits non-zero — NEVER blocks.
 *
 * Negative-spec: subagent writes (agent_id present in payload) are ALWAYS allowed
 * silently; executors are supposed to write code.  Doc/data extensions are allowed
 * silently — the nudge is for code files only (denylist shape, not allowlist).
 *
 * Sentinel suppression: the EM may create /tmp/coordinator-dispatch-nudge-ok-<SESSION_ID>
 * to suppress the nudge for an authorized inline run.  Autonomous-run sentinel
 * /tmp/autonomous-run-<SESSION_ID> (written by /autonomous-mode) also suppresses.
 *
 * Pending-dispatch artifact (written for unambiguous single-file cases):
 *   Path:   <os.tmpdir()>/coordinator-pending-dispatch-<SESSION_ID>-<hash8>.json
 *   Schema: coordinator-pending-dispatch/v1
 *   Fields:
 *     schema           {string}  "coordinator-pending-dispatch/v1"
 *     generated_at     {string}  ISO-8601 timestamp
 *     session_id       {string}  resolved session ID
 *     file_path        {string}  absolute path of the file being written
 *     executor_type    {string}  derived executor type (e.g. "python-executor")
 *     dispatch_brief_text {string} ready-to-paste executor brief
 *     ambiguous        {boolean} true when executor type could not be determined
 *                                deterministically — artifact is NOT written when true
 *
 * Full auto-spawn is deferred to strang-06d (post strang-05).
 *
 * Spec backlink: coordinator-tripwires.md § NUDGE-EM-CODE-DISPATCH
 * Design: docs/wiki/eager-agent-calibration.md (design-as-offers)
 * strang-06 item D: cross-repo/inbox/2026-07-06-strang-06-nag-to-action-hook-conversions.md
 */

const crypto = require('crypto');
const fs   = require('fs');
const os   = require('os');
const path = require('path');

// ---------------------------------------------------------------------------
// Doc / data extension denylist — nudge fires on everything EXCEPT these.
// A code-allowlist would let .sh, .rb, .kt, .sql, .swift, extensionless scripts
// escape.  "Guards match conditions, not containers."
// ---------------------------------------------------------------------------
const DOC_DATA_EXTENSIONS = new Set([
  '.md', '.yaml', '.yml', '.json', '.txt', '.toml',
  '.csv', '.lock', '.cfg', '.ini',
]);

// ---------------------------------------------------------------------------
// Executor type derivation — extension → type mapping.
// ---------------------------------------------------------------------------
const EXT_EXECUTOR_MAP = {
  '.py':   'python-executor',
  '.js':   'js-executor',
  '.mjs':  'js-executor',
  '.cjs':  'js-executor',
  '.ts':   'ts-executor',
  '.tsx':  'ts-executor',
  '.jsx':  'js-executor',
  '.sh':   'shell-executor',
  '.bash': 'shell-executor',
  '.rb':   'ruby-executor',
  '.go':   'go-executor',
  '.rs':   'rust-executor',
  '.java': 'jvm-executor',
  '.kt':   'jvm-executor',
  '.c':    'cpp-executor',
  '.cpp':  'cpp-executor',
  '.cc':   'cpp-executor',
  '.h':    'cpp-executor',
  '.hpp':  'cpp-executor',
  '.swift': 'swift-executor',
  '.sql':  'sql-executor',
};

// Path markers that signal coordinator-domain files → coordinator-executor override.
const COORDINATOR_PATH_MARKERS = [
  'coordinator/',
  'coordinator_core/',
  'plugins/coordinator',
];

// ---------------------------------------------------------------------------
// F7 carve-out: machine-config / bootstrap writes are not product code.
// Writing a trampoline to ~/.local/bin or a shim under ~/.claude/{bin,shell}
// is install-time plumbing, not something the EM should dispatch an executor
// for — and any write outside a git work-tree entirely is by definition not
// "product code in a repo" the dispatch-vs-inline economics apply to.
// Negative-spec: this is a path-based carve-out, NOT a size/triviality
// threshold — a large file written to one of these locations still skips
// the nudge, because the *location* (not the line count) is what disqualifies
// it from "code the EM should be delegating."
// Spec backlink: tasks/2026-07-08-install-dogfood-friction.md § F7
// ---------------------------------------------------------------------------
function bootstrapDirs() {
  const home = process.env.HOME;
  if (!home) return [];
  return [
    path.join(home, '.local', 'bin'),
    path.join(home, '.claude', 'bin'),
    path.join(home, '.claude', 'shell'),
  ];
}

/**
 * True when filePath sits under one of the machine-config/bootstrap dirs
 * (~/.local/bin, ~/.claude/bin, ~/.claude/shell). Resolves both the
 * candidate dir and filePath to absolute paths before comparing so relative
 * segments (e.g. "..") can't slip past a naive prefix check.
 */
function isUnderBootstrapDir(filePath) {
  const absFile = path.resolve(filePath);
  return bootstrapDirs().some((dir) => {
    const absDir = path.resolve(dir) + path.sep;
    return (absFile + path.sep).startsWith(absDir) || absFile === path.resolve(dir);
  });
}

/**
 * True when filePath is NOT inside any git work-tree. Walks up from the
 * file's containing directory looking for a `.git` entry (file or dir —
 * worktrees and submodules use a `.git` *file* pointing elsewhere, so this
 * checks existence, not directory-ness). Missing containing directory
 * (write to a not-yet-created path) still walks correctly since we start
 * from path.dirname and existence of ancestor dirs is what matters here,
 * not the target file itself.
 */
function isOutsideGitWorkTree(filePath) {
  let dir = path.resolve(path.dirname(filePath));
  const root = path.parse(dir).root;
  // eslint-disable-next-line no-constant-condition
  while (true) {
    try {
      if (fs.existsSync(path.join(dir, '.git'))) {
        return false; // found an enclosing .git → inside a work-tree
      }
    } catch {
      // ignore stat errors and keep walking up
    }
    if (dir === root) break;
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return true; // no .git found all the way to the filesystem root
}

/**
 * F7 carve-out predicate: skip the nudge for writes that are machine-config
 * or bootstrap, not product code — outside any git work-tree, or under a
 * known bootstrap dir (~/.local/bin, ~/.claude/bin, ~/.claude/shell).
 */
function isBootstrapOrOutOfRepo(filePath) {
  if (isUnderBootstrapDir(filePath)) return true;
  if (isOutsideGitWorkTree(filePath)) return true;
  return false;
}

/**
 * Derive executor type from file extension and path prefix.
 *
 * Returns { executorType: string, ambiguous: boolean }.
 * ambiguous is true when the type cannot be determined deterministically;
 * the pending-dispatch artifact is NOT written for ambiguous cases.
 */
function deriveExecutorInfo(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  const basename = path.basename(filePath);
  // Normalise path separators for consistent marker matching on Windows.
  const normPath = filePath.replace(/\\/g, '/');

  // Path-prefix override: coordinator domain — deterministic regardless of extension.
  const isCoordinator = COORDINATOR_PATH_MARKERS.some(m => normPath.includes(m));
  if (isCoordinator) {
    return { executorType: 'coordinator-executor', ambiguous: false };
  }

  // Extension-based lookup.
  const byExt = EXT_EXECUTOR_MAP[ext];
  if (byExt) {
    return { executorType: byExt, ambiguous: false };
  }

  // Extensionless: identify by well-known filename patterns.
  if (/^[Mm]akefile$/.test(basename) ||
      /^[Dd]ockerfile(?:\..+)?$/.test(basename) ||
      /^[Rr]akefile$/.test(basename) ||
      /^[Gg]runtfile\.js$/.test(basename) ||
      /^[Gg]ulpfile\.js$/.test(basename)) {
    return { executorType: 'devops-executor', ambiguous: false };
  }

  // Unknown extension or unrecognised extensionless file → ambiguous.
  return { executorType: 'generic-executor', ambiguous: true };
}

/**
 * Build a ready-to-paste executor dispatch brief for the given file and type.
 */
function buildDispatchBrief(filePath, executorType) {
  return [
    '## Pre-assembled executor dispatch brief',
    `file:          ${filePath}`,
    `executor-type: ${executorType}`,
    `in-scope:      ${filePath} (only)`,
    'commit:        false  — EM commits after verification',
    '---',
    'task: [TODO: describe the specific change you want made to this file]',
    'acceptance-criteria:',
    '  AC-1: [TODO: define done condition]',
    '',
    'Dispatch via: fan-out-dispatch.sh or Agent tool with the above brief.',
    'Docs: docs/wiki/dispatching-parallel-agents.md',
  ].join('\n');
}

/**
 * Write the pending-dispatch artifact to os.tmpdir().
 * Silently no-ops on write failure — the artifact is a convenience, not a gate.
 */
function writePendingDispatchArtifact(sessionId, filePath, executorType, dispatchBriefText) {
  const hash8 = crypto.createHash('sha256').update(filePath).digest('hex').slice(0, 8);
  const artifactPath = path.join(
    os.tmpdir(),
    `coordinator-pending-dispatch-${sessionId}-${hash8}.json`,
  );
  const artifact = {
    schema: 'coordinator-pending-dispatch/v1',
    generated_at: new Date().toISOString(),
    session_id: sessionId,
    file_path: filePath,
    executor_type: executorType,
    dispatch_brief_text: dispatchBriefText,
    ambiguous: false,
  };
  try {
    fs.writeFileSync(artifactPath, JSON.stringify(artifact, null, 2), 'utf8');
  } catch {
    // Best-effort: artifact write failure does not affect the nudge path.
  }
}

// ---------------------------------------------------------------------------
// Session-ID resolution
// Tries payload.session_id first, then falls back to a <hostname>-<pid> key.
// The fallback is stable within one node process invocation and collides only
// if two sessions share a machine + pid (astronomically unlikely in practice).
// ---------------------------------------------------------------------------
function resolveSessionId(payload) {
  const sid = payload.session_id;
  if (sid && typeof sid === 'string' && sid.trim().length > 0) {
    // Sanitize to [A-Za-z0-9_-]: strip every char outside this set before the
    // value is used as a filename component in path.join calls.  path.join
    // normalises embedded .. segments and CAN escape os.tmpdir() when the
    // session_id is attacker-supplied (e.g. "foo/../../../etc/target").
    // A legitimate session id is already in this charset; a malformed one is
    // neutralized here rather than relying on path.join for containment.
    // Security-fix: strang-06 item D path-traversal hardening.
    const safe = sid.trim().replace(/[^A-Za-z0-9_-]/g, '');
    if (safe.length > 0) {
      return safe;
    }
    // All characters stripped (e.g. session_id was '../../..') — fall through
    // to the hostname-pid fallback below.
  }
  // Fallback: hostname + pid — NOT persistent across hook re-invocations for
  // the same session, so sentinel files written using this fallback will only
  // work if the hook happens to be invoked by the same OS pid.  This is a
  // known limitation; document and don't crash.
  // FALLBACK-NOTE: if payload.session_id is absent/empty, the sentinel path
  // constructed from this fallback is pid-scoped.  The EM should use the
  // payload's session_id to derive the correct sentinel path when writing it
  // manually; the hook will match only if called under the same pid.
  const hostname = os.hostname().replace(/[^a-zA-Z0-9_-]/g, '-');
  return `${hostname}-${process.pid}`;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  // Read all stdin
  let raw = '';
  try {
    for await (const chunk of process.stdin) {
      raw += chunk;
    }
  } catch {
    process.exit(0);
  }

  // Parse PreToolUse payload
  let payload;
  try {
    payload = JSON.parse(raw);
  } catch {
    process.exit(0);
  }

  // --- Bypass 1: subagent writes are allowed unconditionally ---
  // agent_id present in payload → this is a subagent executor; executors are
  // supposed to write code.  Allow silently.
  if (Object.prototype.hasOwnProperty.call(payload, 'agent_id')) {
    process.exit(0);
  }

  // --- Extract file path ---
  // Review: code-reviewer — MultiEdit payloads carry no top-level file_path;
  // they carry tool_input.edits[].file_path instead (same pattern as
  // nudge-windows-subprocess-popup.sh and block-bin-polyglot-break.sh).
  // Select the first edit whose extension is NOT in the doc/data denylist so
  // the nudge fires on the same conditions as a plain Write to that file.
  const toolInput = payload.tool_input || {};
  let filePath = toolInput.file_path;
  let multipleCodeFiles = false;

  if (!filePath && Array.isArray(toolInput.edits)) {
    let codeFileCount = 0;
    for (const edit of toolInput.edits) {
      const editExt = path.extname(edit.file_path || '').toLowerCase();
      if (!DOC_DATA_EXTENSIONS.has(editExt)) {
        codeFileCount++;
        if (!filePath) {
          filePath = edit.file_path;
        }
      }
    }
    multipleCodeFiles = codeFileCount > 1;
  }

  if (!filePath) process.exit(0);

  // --- Bypass 1.5: machine-config / bootstrap / out-of-repo writes (F7) ---
  // Writes outside any git work-tree, or under ~/.local/bin, ~/.claude/bin,
  // ~/.claude/shell, are install-time plumbing — not product code the EM
  // should be dispatching an executor for. Firing here trained the operator
  // to ignore the nudge (observed: 25-line trampoline write to
  // ~/.local/bin/claude-doe). See isBootstrapOrOutOfRepo() above.
  if (isBootstrapOrOutOfRepo(filePath)) {
    process.exit(0);
  }

  // --- Bypass 2: doc/data extension denylist ---
  const ext = path.extname(filePath).toLowerCase();
  if (DOC_DATA_EXTENSIONS.has(ext)) {
    process.exit(0);
  }

  // --- Resolve session id and sentinel paths ---
  const sessionId = resolveSessionId(payload);

  // --- Bypass 3: dispatch-nudge suppression sentinel ---
  // Review: code-reviewer (F9) — use os.tmpdir() instead of hardcoded /tmp/ for
  // Windows portability (Git Bash / WSL have a different temp dir). os and path already imported.
  const nudgeOkSentinel = path.join(os.tmpdir(), `coordinator-dispatch-nudge-ok-${sessionId}`);
  try {
    fs.accessSync(nudgeOkSentinel, fs.constants.F_OK);
    process.exit(0); // sentinel present → suppressed
  } catch {
    // sentinel absent → continue
  }

  // --- Bypass 4: autonomous-run sentinel ---
  const autonomousSentinel = path.join(os.tmpdir(), `autonomous-run-${sessionId}`);
  try {
    fs.accessSync(autonomousSentinel, fs.constants.F_OK);
    process.exit(0); // autonomous mode → suppress nudge
  } catch {
    // not in autonomous mode → continue
  }

  // --- Derive executor type and build dispatch brief ---
  const { executorType, ambiguous } = deriveExecutorInfo(filePath);
  const dispatchBriefText = buildDispatchBrief(filePath, executorType);

  // --- Write pending-dispatch artifact for unambiguous single-file cases ---
  // multipleCodeFiles (MultiEdit with >1 code file) is also treated as ambiguous
  // because a single executor brief targeting one file is insufficient.
  if (!ambiguous && !multipleCodeFiles) {
    writePendingDispatchArtifact(sessionId, filePath, executorType, dispatchBriefText);
  }

  // --- Emit the offer-shaped nudge ---
  // Leads with the better path (dispatcher), then names the inline carve-out.
  // Never blocks, never exits non-zero.

  // When session_id was absent the resolved sentinel path is pid-scoped and
  // will not match across re-invocations — append a warning so the EM is not
  // misled into writing a sentinel that will never be seen again.
  // Review: code-reviewer — fallback sentinel instruction misleads when session_id absent
  const hasTrueSessionId = payload.session_id &&
    typeof payload.session_id === 'string' &&
    payload.session_id.trim().length > 0;

  const hash8 = crypto.createHash('sha256').update(filePath).digest('hex').slice(0, 8);
  const artifactNote = (!ambiguous && !multipleCodeFiles)
    ? ` Pending-dispatch artifact written to: ${path.join(os.tmpdir(), `coordinator-pending-dispatch-${sessionId}-${hash8}.json`)}.`
    : '';

  const nudgeMessage =
    `You're the EM, not the typist. Code-file write detected: ${filePath}. ` +
    `Did you mean to dispatch an executor (/execute-plan or a fan-out wave)? ` +
    `If inline is genuinely cheaper here, name why per the When-to-EM-Inline checklist (agent-dispatch-economics.md). ` +
    // Review: code-reviewer (F7) — use the already-computed nudgeOkSentinel variable so the
    // message reports the same path the check looks at (os.tmpdir(), not hardcoded /tmp/).
    // On Windows / platforms where tmpdir != /tmp the EM was being told to write the sentinel
    // in the wrong location, causing the bypass to silently fail.
    `To suppress for an authorized inline run, the carve-out path writes ${nudgeOkSentinel}` +
    (hasTrueSessionId
      ? '.'
      : ' (invocation-scoped — session_id was absent from payload; this sentinel only matches if the same OS pid runs the hook again).') +
    `\n\n${dispatchBriefText}` +
    artifactNote;

  // Warn-branch shape: hookSpecificOutput.hookEventName is a REQUIRED field per
  // the harness schema — emitting additionalContext without it fails validation
  // ("hookSpecificOutput is missing required field hookEventName") and the nudge
  // is dropped as a hook error.
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      additionalContext: `[em-code-dispatch nudge] ${nudgeMessage}`,
    },
  }));
  process.exit(0);
}

main().catch(err => {
  process.stderr.write(`nudge-em-code-dispatch: unexpected error: ${err.message}\n`);
  process.exit(0);
});
