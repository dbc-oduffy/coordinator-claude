#!/usr/bin/env node
// lib/pipeline.js — Save, NDC, and consolidation pipelines
// CLI: node pipeline.js save [sessionId] [--force]
//       node pipeline.js ndc
//       node pipeline.js consolidate

import { readFileSync, writeFileSync, appendFileSync, mkdirSync, existsSync, readdirSync, statSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { execSync } from 'child_process';
import { extractSession } from './extract.js';
import { callHaiku } from './haiku.js';
import { memorySessionsDir, stateFilePath, findLatestJsonl, nowSec, safeWriteFile } from './paths.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PROMPTS_DIR = join(__dirname, '..', 'prompts');
const CONFIG_PATH = join(__dirname, '..', 'config.json');

// --- Config ---
function loadConfig() {
  try { return JSON.parse(readFileSync(CONFIG_PATH, 'utf8')); }
  catch { return {}; }
}

// --- State management (atomic read/write) ---
function readState(projectDir) {
  const path = stateFilePath(projectDir);
  try { return JSON.parse(readFileSync(path, 'utf8')); }
  catch { return { lastSave: {}, lastNdc: {}, lastConsolidation: {}, savePid: null }; }
}

function writeState(projectDir, state) {
  safeWriteFile(stateFilePath(projectDir), JSON.stringify(state, null, 2));
}

// --- Template loading ---
function loadPrompt(name) {
  return readFileSync(join(PROMPTS_DIR, name), 'utf8');
}

function fillTemplate(template, vars) {
  let result = template;
  for (const [key, value] of Object.entries(vars)) {
    result = result.replaceAll(`{{${key}}}`, value);
  }
  return result;
}

// --- Ensure sessions directory exists ---
function ensureSessionsDir(projectDir) {
  const dir = memorySessionsDir(projectDir);
  mkdirSync(join(dir, 'daily'), { recursive: true });
  return dir;
}

// --- SAVE pipeline ---
async function save(projectDir, sessionId, force = false) {
  const config = loadConfig();
  const state = readState(projectDir);
  const sessDir = ensureSessionsDir(projectDir);

  // Cooldown check (unless --force)
  if (!force && state.lastSave?.timestamp) {
    const elapsed = nowSec() - state.lastSave.timestamp;
    if (elapsed < (config.cooldowns?.saveSeconds || 120)) {
      return { action: 'cooldown', elapsed: Math.round(elapsed) };
    }
  }

  // Extract — resolve the actual session first, then check for incremental
  const result = await extractSession(sessionId, projectDir, {});
  const resolvedId = result.sessionId; // actual UUID from the JSONL filename
  const skipToLine = (state.lastSave?.session === resolvedId)
    ? (state.lastSave?.line || 0)
    : 0;

  // Re-extract incrementally if we have a saved position
  const extractResult = skipToLine > 0
    ? await extractSession(resolvedId, projectDir, { skipToLine })
    : result;

  if (extractResult.messageCount === 0) {
    return { action: 'empty' };
  }

  // Min human messages check (unless --force)
  const minHuman = config.thresholds?.minHumanMessages || 3;
  if (!force && extractResult.humanCount < minHuman) {
    return { action: 'below-threshold', humanCount: extractResult.humanCount };
  }

  // Build save prompt
  const currentPath = join(sessDir, 'current.md');
  const lastEntry = getLastEntry(currentPath);
  const d = new Date();
  const time = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  const branch = getBranch();

  const template = loadPrompt('save-session.txt');
  const prompt = fillTemplate(template, {
    TIME: time,
    BRANCH: branch,
    LAST_ENTRY: lastEntry,
    EXTRACT: extractResult.exchanges
  });

  // Call Haiku
  const haiku = await callHaiku(prompt);

  if (haiku.isSkip) {
    // Update position but don't write
    const jsonlPath2 = findLatestJsonl(projectDir);
    let skipFileSize = 0;
    try { skipFileSize = statSync(jsonlPath2).size; } catch { /* file may be gone */ }
    state.lastSave = { session: resolvedId, line: extractResult.position, fileSize: skipFileSize, timestamp: nowSec() };
    writeState(projectDir, state);
    return { action: 'skip', tokens: haiku.tokens };
  }

  // Append to current.md
  mkdirSync(dirname(currentPath), { recursive: true });
  appendFileSync(currentPath, haiku.text.trim() + '\n\n');

  // Update state
  // Track both line position (for extraction) and file size (for post-tool.js heuristic)
  const jsonlPath = findLatestJsonl(projectDir);
  let fileSize = 0;
  try { fileSize = statSync(jsonlPath).size; } catch { /* file may be gone */ }

  state.lastSave = { session: resolvedId, line: extractResult.position, fileSize, timestamp: nowSec() };
  state.savePid = null;
  writeState(projectDir, state);

  return { action: 'saved', entry: haiku.text.trim(), tokens: haiku.tokens };
}

// --- NDC pipeline (now → daily) ---
async function ndc(projectDir) {
  const config = loadConfig();
  const state = readState(projectDir);
  const sessDir = ensureSessionsDir(projectDir);

  // Cooldown
  if (state.lastNdc?.timestamp) {
    const elapsed = nowSec() - state.lastNdc.timestamp;
    if (elapsed < (config.cooldowns?.ndcSeconds || 3600)) {
      return { action: 'cooldown' };
    }
  }

  const currentPath = join(sessDir, 'current.md');
  if (!existsSync(currentPath)) return { action: 'empty' };

  const content = readFileSync(currentPath, 'utf8').trim();
  if (!content) return { action: 'empty' };

  // Build NDC prompt
  const template = loadPrompt('compress-ndc.txt');
  const prompt = fillTemplate(template, { NOW_CONTENT: content });

  const haiku = await callHaiku(prompt, { timeout: 180_000 });

  // Write to daily file FIRST — verify success before clearing current.md
  const today = new Date().toISOString().slice(0, 10);
  const dailyPath = join(sessDir, 'daily', `${today}.md`);
  mkdirSync(dirname(dailyPath), { recursive: true });
  appendFileSync(dailyPath, haiku.text.trim() + '\n\n');

  // Only clear current.md after daily write confirmed
  // (if appendFileSync threw, we preserve current.md — no data loss)
  writeFileSync(currentPath, '');

  // Update state
  state.lastNdc = { timestamp: nowSec() };
  writeState(projectDir, state);

  return { action: 'compressed', tokens: haiku.tokens };
}

// --- CONSOLIDATION pipeline (daily → recent) ---
async function consolidate(projectDir) {
  const sessDir = ensureSessionsDir(projectDir);
  const dailyDir = join(sessDir, 'daily');
  if (!existsSync(dailyDir)) return { action: 'empty' };

  const today = new Date().toISOString().slice(0, 10);

  // Find unprocessed daily files (not today, no .done marker)
  const files = readdirSync(dailyDir)
    .filter(f => f.endsWith('.md') && !f.includes(today))
    .filter(f => !existsSync(join(dailyDir, f.replace('.md', '.done'))));

  if (files.length === 0) return { action: 'nothing-to-consolidate' };

  // Read staging content
  const stagingContent = files.map(f => {
    const content = readFileSync(join(dailyDir, f), 'utf8');
    return `--- ${f} ---\n${content}`;
  }).join('\n\n');

  // Read current recent.md
  const recentPath = join(sessDir, 'recent.md');
  const recent = existsSync(recentPath) ? readFileSync(recentPath, 'utf8') : '';

  // Build consolidation prompt
  const template = loadPrompt('consolidate.txt');
  const prompt = fillTemplate(template, {
    STAGING_FILES: stagingContent,
    RECENT: recent || '(empty)'
  });

  const haiku = await callHaiku(prompt, { timeout: 180_000 });

  // Parse response — expect ===RECENT=== delimiter
  let recentNew = haiku.text;
  if (haiku.text.includes('===RECENT===')) {
    recentNew = haiku.text.split('===RECENT===')[1] || haiku.text;
    // Strip ===ARCHIVE=== section if present (legacy prompt may still emit it)
    if (recentNew.includes('===ARCHIVE===')) {
      recentNew = recentNew.split('===ARCHIVE===')[0];
    }
  }
  recentNew = recentNew.trim();
  if (!recentNew.startsWith('# Recent')) {
    recentNew = '# Recent\n\n' + recentNew;
  }

  // Write recent.md (atomic, Windows-safe)
  safeWriteFile(recentPath, recentNew + '\n');

  // Mark daily files as done
  for (const f of files) {
    writeFileSync(join(dailyDir, f.replace('.md', '.done')), '');
  }

  // Update state
  const state = readState(projectDir);
  state.lastConsolidation = { timestamp: nowSec() };
  writeState(projectDir, state);

  return { action: 'consolidated', fileCount: files.length, tokens: haiku.tokens };
}

// --- Helpers ---
function getLastEntry(currentPath) {
  if (!existsSync(currentPath)) return '(none)';
  const content = readFileSync(currentPath, 'utf8').trim();
  if (!content) return '(none)';
  // Get the last ## entry
  const entries = content.split(/(?=^## )/m);
  return entries[entries.length - 1]?.trim() || '(none)';
}

function getBranch() {
  try {
    return execSync('git branch --show-current', { encoding: 'utf8', timeout: 5000 }).trim() || 'unknown';
  } catch { return 'unknown'; }
}

// --- CLI entry point ---
const [,, command, ...args] = process.argv;
const projectDir = process.env.CLAUDE_PROJECT_DIR || process.cwd();

(async () => {
  try {
    let result;
    switch (command) {
      case 'save': {
        const sessionId = args.find(a => !a.startsWith('-')) || undefined;
        const force = args.includes('--force');
        result = await save(projectDir, sessionId, force);
        break;
      }
      case 'ndc':
        result = await ndc(projectDir);
        break;
      case 'consolidate':
        result = await consolidate(projectDir);
        break;
      default:
        console.error('Usage: node pipeline.js <save|ndc|consolidate>');
        process.exit(1);
    }
    // Log result to stderr (stdout reserved for hook output)
    console.error(JSON.stringify(result));
  } catch (err) {
    console.error(`Pipeline error: ${err.message}`);
    process.exit(1);
  }
})();
