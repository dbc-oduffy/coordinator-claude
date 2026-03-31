// lib/paths.js — Cross-platform path resolution for remember plugin
import { resolve, join, dirname, basename } from 'path';
import { homedir } from 'os';
import { existsSync, readdirSync, statSync, writeFileSync, mkdirSync, unlinkSync, renameSync } from 'fs';

/**
 * Convert a project directory to Claude Code's session slug.
 * Replaces all non-alphanumeric, non-dash characters with dashes.
 * On Windows, path.resolve() already returns the native path (C:\Users\...)
 * so no cygpath needed.
 */
export function projectSlug(projectDir) {
  const resolved = resolve(projectDir);
  return resolved.replace(/[^a-zA-Z0-9-]/g, '-');
}

/**
 * Return the Claude Code sessions directory for a project.
 */
export function sessionsDir(projectDir) {
  return join(homedir(), '.claude', 'projects', projectSlug(projectDir));
}

/**
 * Return the memory/sessions/ directory for storing remember data.
 */
export function memorySessionsDir(projectDir) {
  return join(homedir(), '.claude', 'projects', projectSlug(projectDir), 'memory', 'sessions');
}

/**
 * Find the most recent .jsonl file in the sessions directory.
 * Returns null if no sessions exist.
 */
export function findLatestJsonl(projectDir) {
  const dir = sessionsDir(projectDir);
  if (!existsSync(dir)) return null;

  let latest = null;
  let latestMtime = 0;

  for (const entry of readdirSync(dir)) {
    if (!entry.endsWith('.jsonl')) continue;
    const fullPath = join(dir, entry);
    try {
      const mtime = statSync(fullPath).mtimeMs;
      if (mtime > latestMtime) {
        latestMtime = mtime;
        latest = fullPath;
      }
    } catch { /* race: file deleted between readdir and stat */ }
  }

  return latest;
}

/**
 * Find a specific session JSONL by ID.
 */
export function findSession(sessionId, projectDir) {
  if (!sessionId) return findLatestJsonl(projectDir);
  // Reject path traversal
  if (sessionId.includes('/') || sessionId.includes('\\') || sessionId.includes('..')) {
    throw new Error(`Invalid session ID: ${sessionId}`);
  }
  const path = join(sessionsDir(projectDir), `${sessionId}.jsonl`);
  return existsSync(path) ? path : null;
}

/**
 * State file path.
 */
export function stateFilePath(projectDir) {
  return join(memorySessionsDir(projectDir), 'state.json');
}

/**
 * Seconds since epoch. Centralizes the ms→s conversion used throughout.
 */
export function nowSec() {
  return Math.floor(Date.now() / 1000);
}

/**
 * Write a file atomically (safe on Windows where renameSync can't overwrite).
 * Writes to .tmp, unlinks target if it exists, then renames.
 */
export function safeWriteFile(filePath, content) {
  mkdirSync(dirname(filePath), { recursive: true });
  const tmp = filePath + '.tmp';
  writeFileSync(tmp, content);
  try { unlinkSync(filePath); } catch { /* may not exist yet */ }
  renameSync(tmp, filePath);
}
