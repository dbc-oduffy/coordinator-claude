#!/usr/bin/env node
'use strict';
/**
 * sentinel-blocks-cli.js — Thin CLI wrapper around sentinel-blocks.js for use in shell scripts.
 *
 * Spec backlink: docs/plans/2026-05-01-portable-ideas-from-obsidian-research.md §W2
 *
 * Commands:
 *   extract <file> <begin-marker> <end-marker>
 *     Prints the block content between markers (exclusive — marker lines not included) to stdout.
 *     Exits 1 if either marker is absent.
 *
 * Review: patrik R2 finding 0 — factor shared extraction primitive used by verify-preamble-sync.sh
 * and verify-calibration-sync.sh so all three implementations converge on one source of truth.
 */

const fs = require('fs');
const { extractBlock } = require('./sentinel-blocks.js');

function usage() {
  process.stderr.write(
    'Usage: sentinel-blocks-cli.js extract <file> <begin-marker> <end-marker>\n'
  );
  process.exit(1);
}

const [,, command, ...rest] = process.argv;

if (!command) usage();

switch (command) {
  case 'extract': {
    const [file, beginMarker, endMarker] = rest;
    if (!file || !beginMarker || !endMarker) usage();

    let content;
    try {
      content = fs.readFileSync(file, 'utf8');
    } catch (err) {
      process.stderr.write(`sentinel-blocks-cli: cannot read file: ${file}: ${err.message}\n`);
      process.exit(1);
    }

    const result = extractBlock(content, beginMarker, endMarker);
    if (!result) {
      process.stderr.write(
        `sentinel-blocks-cli: markers not found in ${file}\n` +
        `  begin: ${beginMarker}\n` +
        `  end:   ${endMarker}\n`
      );
      process.exit(1);
    }

    process.stdout.write(result.block);
    break;
  }

  default:
    process.stderr.write(`sentinel-blocks-cli: unknown command: ${command}\n`);
    usage();
}
