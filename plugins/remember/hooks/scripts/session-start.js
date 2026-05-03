#!/usr/bin/env node
// SessionStart hook — inject memory context, spawn recovery + consolidation.
// Async, 10s timeout. Output goes to additionalContext.

import { readFileSync, writeFileSync, existsSync, readdirSync, mkdirSync } from 'fs';
import { join, basename, dirname } from 'path';
import { spawn } from 'child_process';
import { fileURLToPath } from 'url';
import { memorySessionsDir, stateFilePath, findLatestJsonl, findSession } from '../../lib/paths.js';

// Read hook input
let input = '';
try { input = readFileSync(0, 'utf8'); } catch {}

let hookData = {};
try { hookData = JSON.parse(input); } catch {}

const projectDir = hookData.cwd || process.env.CLAUDE_PROJECT_DIR || process.cwd();
const __dir = dirname(fileURLToPath(import.meta.url));
const sessDir = memorySessionsDir(projectDir);

// --- Ensure directory exists ---
mkdirSync(join(sessDir, 'daily'), { recursive: true });

// --- Recovery: save unsaved prior sessions ---
const configPath = join(__dir, '..', '..', 'config.json');
let config = {};
try { config = JSON.parse(readFileSync(configPath, 'utf8')); } catch {}

if (config.features?.recovery !== false) {
  const state = (() => {
    try { return JSON.parse(readFileSync(stateFilePath(projectDir), 'utf8')); }
    catch { return {}; }
  })();

  // Find second-most-recent JSONL (the previous session)
  // The latest is the current session — we want the one before it
  const latestJsonl = findLatestJsonl(projectDir);
  if (latestJsonl && state.lastSave?.session) {
    const latestId = basename(latestJsonl, '.jsonl');
    if (latestId !== state.lastSave.session) {
      // Previous session wasn't saved — recover it (verify JSONL still exists first)
      const prevJsonl = findSession(state.lastSave.session, projectDir);
      if (prevJsonl) {
        const pipelinePath = join(__dir, '..', '..', 'lib', 'pipeline.js');
        const child = spawn(process.execPath, [pipelinePath, 'save', state.lastSave.session, '--force'], {
          cwd: projectDir,
          env: { ...process.env, CLAUDE_PROJECT_DIR: projectDir },
          detached: true,
          stdio: 'ignore',
          windowsHide: true
        });
        child.on('error', () => {});
        child.unref();
      }
    }
  }
}

// --- Inject memory into context ---
const output = [];

// Session history hint
output.push('=== SESSION MEMORY ===');
output.push('Temporal session history is stored in memory/sessions/. Files: current.md (buffer), daily/*.md (compressed), recent.md (7-14 day rolling). The /remember skill saves a handoff note.');
output.push('');

// Load memory files in order. `tail` caps injection size for unbounded
// accumulator files — the full file stays on disk for /remember to consume,
// but only the last N blocks land in EM context at boot.
const filesToLoad = [
  { path: join(sessDir, 'handoff.md'), label: 'handoff (one-shot)', clear: true },
  { path: join(sessDir, `daily/${new Date().toISOString().slice(0, 10)}.md`), label: 'today' },
  { path: join(sessDir, 'current.md'), label: 'current session buffer (last 8 entries — full file on disk)', tail: 8 },
  { path: join(sessDir, 'recent.md'), label: 'recent (7-14 days)' },
];

// Tail an `## HH:MM | ...`-headered markdown buffer to its last N blocks.
function tailBlocks(content, n) {
  const blocks = content.split(/(?=^## )/m).filter(b => b.trim());
  if (blocks.length <= n) return content;
  return blocks.slice(-n).join('').trimEnd();
}

let hasContent = false;

for (const { path, label, clear, tail } of filesToLoad) {
  if (!existsSync(path)) continue;
  let content = readFileSync(path, 'utf8').trim();
  if (!content) continue;

  if (tail) content = tailBlocks(content, tail);

  hasContent = true;
  output.push(`--- ${label} ---`);
  output.push(content);
  output.push('');

  // Clear one-shot files (handoff) — use writeFileSync (already statically imported)
  if (clear) {
    try { writeFileSync(path, ''); } catch {}
  }
}

if (!hasContent) {
  output.push('(no session history yet — memory will accumulate as you work)');
  output.push('');
}

// --- Consolidation: compress past daily files ---
const dailyDir = join(sessDir, 'daily');
if (existsSync(dailyDir)) {
  const today = new Date().toISOString().slice(0, 10);
  const unprocessed = readdirSync(dailyDir)
    .filter(f => f.endsWith('.md') && !f.includes(today))
    .filter(f => !existsSync(join(dailyDir, f.replace('.md', '.done'))));

  if (unprocessed.length > 0) {
    output.push(`${unprocessed.length} day(s) of session memory to consolidate — running in background.`);
    const pipelinePath = join(__dir, '..', '..', 'lib', 'pipeline.js');
    const child = spawn(process.execPath, [pipelinePath, 'consolidate'], {
      cwd: projectDir,
      env: { ...process.env, CLAUDE_PROJECT_DIR: projectDir },
      detached: true,
      stdio: 'ignore',
      windowsHide: true
    });
    child.on('error', () => {});
    child.unref();
  }
}

// Emit output
console.log(output.join('\n'));
