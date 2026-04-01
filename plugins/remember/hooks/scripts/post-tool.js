#!/usr/bin/env node
// PostToolUse hook — monitors session JSONL growth, triggers background saves.
// Must complete in <5 seconds. Most invocations exit in <100ms (cooldown/delta check).
//
// All imports are static (ESM requirement). All operations are synchronous on the
// hot path — async only for the line count, wrapped in top-level await.

import { readFileSync, statSync } from 'fs';
import { join, dirname } from 'path';
import { spawn } from 'child_process';
import { fileURLToPath } from 'url';
import { findLatestJsonl, stateFilePath, nowSec, safeWriteFile } from '../../lib/paths.js';

// --- Read hook input from stdin (synchronous, safe on Windows) ---
let input = '';
try { input = readFileSync(0, 'utf8'); } catch { /* stdin may be empty or closed */ }

let hookData = {};
try { hookData = JSON.parse(input); } catch { process.exit(0); }

// Skip Stop events (incompatible schema)
if (hookData.hook_event_name === 'Stop' || !hookData.tool_name) process.exit(0);

const projectDir = hookData.cwd || process.env.CLAUDE_PROJECT_DIR || process.cwd();
if (!hookData.session_id) process.exit(0);

// --- Load config ---
const __dir = dirname(fileURLToPath(import.meta.url));
const configPath = join(__dir, '..', '..', 'config.json');
let config = {};
try { config = JSON.parse(readFileSync(configPath, 'utf8')); } catch {}

// --- Find latest JSONL ---
const jsonlPath = findLatestJsonl(projectDir);
if (!jsonlPath) process.exit(0);

// --- Read state ---
const statePath = stateFilePath(projectDir);
let state = {};
try { state = JSON.parse(readFileSync(statePath, 'utf8')); } catch {}

// --- Quick size check (sync, no streaming — fast for hot path) ---
// Use file size as a growth heuristic rather than counting lines.
// Approximate lines ≈ bytes / 500 (average JSONL line is ~500 bytes).
// This avoids reading the entire file on every tool call.
let fileSize = 0;
try { fileSize = statSync(jsonlPath).size; } catch { process.exit(0); }

const lastSize = state.lastSave?.fileSize || 0;
const bytesPerLine = 500; // approximate
const estimatedDelta = lastSize === 0 || fileSize < lastSize
  ? Math.floor(fileSize / bytesPerLine)
  : Math.floor((fileSize - lastSize) / bytesPerLine);
const threshold = config.thresholds?.deltaLinesTrigger || 50;

if (estimatedDelta < threshold) process.exit(0);

// --- Cooldown check ---
if (state.lastSave?.timestamp) {
  const elapsed = nowSec() - state.lastSave.timestamp;
  if (elapsed < (config.cooldowns?.saveSeconds || 120)) process.exit(0);
}

// --- PID liveness check (with staleness timeout) ---
const STALE_PID_SECONDS = 300; // 5 minutes
if (state.savePid?.pid) {
  const pidAge = nowSec() - (state.savePid.startedAt || 0);
  if (pidAge < STALE_PID_SECONDS) {
    try { process.kill(state.savePid.pid, 0); process.exit(0); /* still alive and fresh */ }
    catch { /* dead — proceed */ }
  }
  // else: stale PID — ignore it regardless of liveness (Windows PID recycling)
}

// --- Spawn detached save process ---
// Use process.execPath (same Node binary running this hook) instead of 'node'
const pipelinePath = join(__dir, '..', '..', 'lib', 'pipeline.js');
const child = spawn(process.execPath, [pipelinePath, 'save'], {
  cwd: projectDir,
  env: { ...process.env, CLAUDE_PROJECT_DIR: projectDir },
  detached: true,
  stdio: 'ignore',
  windowsHide: true
});

child.on('error', () => {}); // prevent unhandled error if spawn fails
child.unref();

// --- Record PID in state (best effort) ---
state.savePid = { pid: child.pid, startedAt: nowSec() };
try { safeWriteFile(statePath, JSON.stringify(state, null, 2)); } catch {}

process.exit(0);
