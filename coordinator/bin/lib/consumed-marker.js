'use strict';
/**
 * consumed-marker.js — shared constants and regex for consumed-marker handling.
 *
 * Spec backlink: docs/plans/2026-05-14-normalize-consumed-frontmatter.md
 *
 * Single source of truth for TERMINAL_STATUS, TERMINAL_DEPLOYMENT, and
 * CONSUMED_MARKER_RE so the write-time path (normalize-consumed-frontmatter.js)
 * and the read-time path (query-records.js) are greppably aligned.
 *
 * Review: Patrik F3 — shared terminal-state constants to keep write-time and
 * read-time paths in sync without copy-paste drift.
 */

// Fields whose status values are terminal (no flip allowed).
const TERMINAL_STATUS = new Set(['consumed', 'superseded']);

// Fields whose deployment_state values are terminal (no flip allowed).
const TERMINAL_DEPLOYMENT = new Set(['shipped', 'abandoned']);

// Matches `<!-- consumed: YYYY-MM-DD [optional notes] -->` in a document body.
// Review: Patrik F4 — capture group widened to `(.*?)\s*-->` (lazy,
// terminator-anchored) so `>` characters in notes (e.g. "shipped via PR > main")
// are captured correctly rather than being swallowed by a greedy `[^>]*` stop.
const CONSUMED_MARKER_RE = /<!--\s*consumed:\s*(\d{4}-\d{2}-\d{2})(?:\s+(.*?))?\s*-->/i;

module.exports = { TERMINAL_STATUS, TERMINAL_DEPLOYMENT, CONSUMED_MARKER_RE };
