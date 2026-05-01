'use strict';
/**
 * sentinel-blocks.js — Extract and replace sentinel-delimited blocks in markdown content.
 *
 * Spec backlink: docs/plans/2026-05-01-portable-ideas-from-obsidian-research.md §W2 (Sentinel-Block Primitives)
 *
 * Exports:
 *   extractBlock(content, beginMarker, endMarker) → {block, before, after} | null
 *   replaceBlock(content, beginMarker, endMarker, newBlockContent) → string | null
 *   insertOrReplaceBlock(content, beginMarker, endMarker, newBlockContent, insertAt) → string
 *
 * All ops use plain string index lookups — no regex — so markers with special chars work safely.
 * Markers are treated as exact substrings. Typical form: <!-- BEGIN x --> / <!-- END x -->.
 *
 * Line-boundary handling: if a marker sits at the start of its line (possibly after whitespace),
 * the surrounding newlines are consumed so that the extracted block / replacement is clean.
 */

/**
 * Find begin/end marker positions, handling both "marker on its own line" and inline cases.
 * Returns { beginStart, beginEnd, endStart, endEnd } (all byte offsets into `content`), or null.
 *
 * beginStart — index of the first character of the begin marker line (or the marker itself)
 * beginEnd   — index just after the end of the begin marker (including its trailing newline if any)
 * endStart   — index of the first character of the end marker line (or the marker itself)
 * endEnd     — index just after the end of the end marker (including its trailing newline if any)
 */
function findMarkers(content, beginMarker, endMarker) {
  const bi = content.indexOf(beginMarker);
  if (bi === -1) return null;

  const ei = content.indexOf(endMarker, bi + beginMarker.length);
  if (ei === -1) return null;

  // Determine line extents for begin marker
  let beginLineStart = bi;
  while (beginLineStart > 0 && content[beginLineStart - 1] !== '\n') {
    beginLineStart--;
  }
  let beginLineEnd = bi + beginMarker.length;
  // Consume trailing newline (including \r\n)
  if (content[beginLineEnd] === '\r') beginLineEnd++;
  if (content[beginLineEnd] === '\n') beginLineEnd++;

  // Determine line extents for end marker
  let endLineStart = ei;
  while (endLineStart > 0 && content[endLineStart - 1] !== '\n') {
    endLineStart--;
  }
  let endLineEnd = ei + endMarker.length;
  if (content[endLineEnd] === '\r') endLineEnd++;
  if (content[endLineEnd] === '\n') endLineEnd++;

  // Only use line extents if the text before the marker on its line is whitespace-only.
  // If there's non-whitespace before the marker, treat as inline — use raw positions.
  const textBeforeBegin = content.slice(beginLineStart, bi);
  const textBeforeEnd = content.slice(endLineStart, ei);

  const beginIsOwnLine = textBeforeBegin.trim() === '';
  const endIsOwnLine = textBeforeEnd.trim() === '';

  return {
    beginStart: beginIsOwnLine ? beginLineStart : bi,
    beginEnd:   beginIsOwnLine ? beginLineEnd   : bi + beginMarker.length,
    endStart:   endIsOwnLine   ? endLineStart   : ei,
    endEnd:     endIsOwnLine   ? endLineEnd     : ei + endMarker.length,
  };
}

/**
 * Extract the content between beginMarker and endMarker.
 *
 * Returns { block, before, after } where:
 *   block  — the text between the two markers (not including marker lines themselves)
 *   before — the text before (and including) the begin marker line
 *   after  — the text from (and including) the end marker line to end of file
 *
 * Returns null if either marker is not found.
 */
function extractBlock(content, beginMarker, endMarker) {
  const pos = findMarkers(content, beginMarker, endMarker);
  if (!pos) return null;

  const before = content.slice(0, pos.beginEnd);
  const block = content.slice(pos.beginEnd, pos.endStart);
  const after = content.slice(pos.endStart);

  return { block, before, after };
}

/**
 * Replace the block content between beginMarker and endMarker with newBlockContent.
 *
 * Preserves the marker lines themselves. newBlockContent is placed verbatim between them;
 * a trailing newline is added before the end marker if newBlockContent doesn't end with one.
 *
 * Returns the updated string, or null if either marker is missing.
 */
function replaceBlock(content, beginMarker, endMarker, newBlockContent) {
  const pos = findMarkers(content, beginMarker, endMarker);
  if (!pos) return null;

  // Reconstruct: everything up to (and including) begin marker line, then new content,
  // then end marker line to end of file.
  const head = content.slice(0, pos.beginEnd);
  const tail = content.slice(pos.endStart);

  // Ensure newBlockContent ends with newline so end marker starts on its own line
  let body = newBlockContent;
  if (body.length > 0 && !body.endsWith('\n')) {
    body += '\n';
  }

  return head + body + tail;
}

/**
 * Like replaceBlock, but if the markers don't exist, insert them.
 *
 * insertAt: 'end' (default) appends the block at the end of content.
 *           'start' prepends at the beginning.
 *
 * Returns the updated string (never null).
 */
function insertOrReplaceBlock(content, beginMarker, endMarker, newBlockContent, insertAt = 'end') {
  const replaced = replaceBlock(content, beginMarker, endMarker, newBlockContent);
  if (replaced !== null) return replaced;

  // Markers missing — insert them
  let body = newBlockContent;
  if (body.length > 0 && !body.endsWith('\n')) {
    body += '\n';
  }
  const block = beginMarker + '\n' + body + endMarker + '\n';

  if (insertAt === 'start') {
    return block + content;
  }
  // 'end' — ensure there's a newline separator
  const sep = content.length > 0 && !content.endsWith('\n') ? '\n' : '';
  return content + sep + block;
}

module.exports = { extractBlock, replaceBlock, insertOrReplaceBlock };
