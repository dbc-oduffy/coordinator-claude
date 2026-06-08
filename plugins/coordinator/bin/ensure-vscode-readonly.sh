#!/bin/bash
# ensure-vscode-readonly.sh — idempotently mark the generated handoff tracker
# files read-only in VS Code (and forks that honor files.readonlyInclude).
#
# Spec backlink: docs/plans/2026-05-29-handoff-tracker-system.md (edit-resistance follow-up)
#
# The handoff tracker (state/handoff-tracker.md, state/doe-handoff-tracker.md) is
# a disposable render of handoff frontmatter. This is the EDITOR-side guard
# (layer 1): VS Code opens the files read-only and refuses to save, so a human
# does not accidentally hand-edit a render. It complements the agent-side guard
# (layer 2, hooks/scripts/block-tracker-edit.sh) which blocks Claude's Write/Edit.
#
# Offer-shaped, not a hard lock: a user can still override per-file via VS Code's
# "Set Active Editor Writeable" command. The next render overwrites edits anyway.
#
# Idempotent and ADDITIVE: ALWAYS merges our two readonlyInclude globs into an
# existing .vscode/settings.json without clobbering existing settings or existing
# readonlyInclude entries. Handles strict JSON losslessly. Handles JSONC (the
# common case — VS Code settings frequently carry // and /* */ comments): strips
# comments to parse, backs the original up to settings.json.bak, and writes back
# strict JSON (comments are normalized away — restore from .bak if you need them).
# Safe to re-run. Creates .vscode/settings.json if absent.
#
# Usage: ensure-vscode-readonly.sh [--root <repo-root>]   (default: cwd)
#
# Cross-platform: uses node (guaranteed present alongside the renderer) for a
# robust JSONC-tolerant merge — no jq dependency (jq is frequently absent on
# Windows OSS installs). If node is absent, skips loudly to stderr.

set -uo pipefail

ROOT="."
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      [[ -z "${2:-}" ]] && { echo "ensure-vscode-readonly: --root requires a value" >&2; exit 2; }
      ROOT="$2"; shift 2 ;;
    *) echo "ensure-vscode-readonly: unknown argument: $1" >&2; exit 2 ;;
  esac
done

[[ -d "$ROOT" ]] || { echo "ensure-vscode-readonly: root not a directory: $ROOT" >&2; exit 2; }

# Resolve node (node, then nodejs on some distros).
NODE_BIN=""
if command -v node &>/dev/null; then NODE_BIN="node"
elif command -v nodejs &>/dev/null; then NODE_BIN="nodejs"
else
  echo "[coordinator] ensure-vscode-readonly: node not on PATH — skipped (cannot safely merge JSON). Add by hand: files.readonlyInclude → \"**/state/handoff-tracker.md\": true, \"**/state/doe-handoff-tracker.md\": true" >&2
  exit 0
fi

VSCODE_DIR="$ROOT/.vscode"
SETTINGS="$VSCODE_DIR/settings.json"
mkdir -p "$VSCODE_DIR"

# Merge runs in node: JSONC-tolerant, additive, idempotent, atomic. Settings path
# passed via env (avoids `node -` argv ambiguity). Exit codes: 0 = ok/idempotent/
# skipped-unparseable; 1 = write failure.
SETTINGS="$SETTINGS" "$NODE_BIN" <<'NODE'
const fs = require('fs');
const settingsPath = process.env.SETTINGS;
const KEYS = {
  "**/state/handoff-tracker.md": true,
  "**/state/doe-handoff-tracker.md": true,
};

// Strip // and /* */ comments that fall OUTSIDE string literals, then drop
// trailing commas — the JSONC superset VS Code settings.json uses.
function stripJsonc(s) {
  let out = "", i = 0, inStr = false, q = "", esc = false;
  while (i < s.length) {
    const c = s[i];
    if (inStr) {
      out += c;
      if (esc) esc = false;
      else if (c === "\\") esc = true;
      else if (c === q) inStr = false;
      i++; continue;
    }
    if (c === '"' || c === "'") { inStr = true; q = c; out += c; i++; continue; }
    if (c === "/" && s[i + 1] === "/") { while (i < s.length && s[i] !== "\n") i++; continue; }
    if (c === "/" && s[i + 1] === "*") { i += 2; while (i < s.length && !(s[i] === "*" && s[i + 1] === "/")) i++; i += 2; continue; }
    out += c; i++;
  }
  return out.replace(/,(\s*[}\]])/g, "$1");
}

let raw = null;
try { raw = fs.readFileSync(settingsPath, "utf8"); } catch { raw = null; }

let obj = {};
let hadComments = false;
if (raw !== null && raw.trim() !== "") {
  try {
    obj = JSON.parse(raw);
  } catch {
    hadComments = true;
    try {
      obj = JSON.parse(stripJsonc(raw));
    } catch {
      process.stderr.write("[coordinator] ensure-vscode-readonly: " + settingsPath +
        " could not be parsed even after comment-strip — skipped to avoid clobbering. " +
        "Add by hand: files.readonlyInclude → \"**/state/handoff-tracker.md\": true, " +
        "\"**/state/doe-handoff-tracker.md\": true\n");
      process.exit(0);
    }
  }
}
if (typeof obj !== "object" || obj === null || Array.isArray(obj)) {
  process.stderr.write("[coordinator] ensure-vscode-readonly: " + settingsPath +
    " is not a JSON object — skipped.\n");
  process.exit(0);
}

const cur = (obj["files.readonlyInclude"] && typeof obj["files.readonlyInclude"] === "object" &&
             !Array.isArray(obj["files.readonlyInclude"])) ? obj["files.readonlyInclude"] : {};

// Idempotent: both keys already present and true → no write (no mtime churn).
if (Object.keys(KEYS).every((k) => cur[k] === true)) process.exit(0);

obj["files.readonlyInclude"] = Object.assign({}, cur, KEYS);

// JSONC path is lossy on comments — back the original up before rewriting strict.
if (hadComments) {
  try { fs.writeFileSync(settingsPath + ".bak", raw); } catch {}
  process.stderr.write("[coordinator] ensure-vscode-readonly: " + settingsPath +
    " had comments (JSONC) — merged the guard and wrote strict JSON. Original backed " +
    "up to " + settingsPath + ".bak (re-add comments there if you need them).\n");
}

const outStr = JSON.stringify(obj, null, 2) + "\n";
const tmp = settingsPath + ".tmp." + process.pid;
try {
  fs.writeFileSync(tmp, outStr);
  fs.renameSync(tmp, settingsPath);
} catch (e) {
  try { fs.unlinkSync(tmp); } catch {}
  process.stderr.write("[coordinator] ensure-vscode-readonly: write failed for " + settingsPath + ": " + e.message + "\n");
  process.exit(1);
}
process.stdout.write("[coordinator] ensure-vscode-readonly: " +
  (raw === null ? "created " : "merged tracker read-only globs into ") + settingsPath + "\n");
NODE
exit $?
