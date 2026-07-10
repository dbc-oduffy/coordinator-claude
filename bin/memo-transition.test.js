'use strict';
/**
 * memo-transition.test.js — byte-identical output regression guard for
 * memo-transition.js's claim/action/release verbs, post schema.js migration.
 *
 * Purpose: memo-transition.js was migrated onto the shared frontmatter
 * primitives in lib/schema.js (splitFrontmatter/readFmField/serializeYamlScalar/
 * replaceFmField/insertFmField/removeFmField — see module header). It is the
 * only one of the 4 migrated CLIs (handoff-transition.js, memo-transition.js,
 * normalize-consumed-frontmatter.js, stamp-shipped-in.js) that lacked a
 * byte-identical output regression test at migration time. This file closes
 * that gap, mirroring the pattern in
 * bin/tests/test-handoff-transition-consume.js's 'byte-identical output'
 * describe block and normalize-consumed-frontmatter.test.js's snapshot test.
 *
 * Each expected string below was derived empirically by running the CURRENT
 * (post-migration) memo-transition.js against a fixed fixture and locking the
 * output verbatim — not hand-authored/predicted.
 *
 * Run with: node --test bin/memo-transition.test.js
 *
 * Spec backlink: docs/plans/2026-06-21-memo-pickup-claim-lock-and-routed-plan-reconcile.md § C2
 */

const { describe, it, before, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { execFileSync } = require('child_process');

const BIN_DIR = __dirname;
const MEMO_TRANSITION = path.join(BIN_DIR, 'memo-transition.js');

const AT = '2026-06-26T12:00:00Z';
const SESSION_ID = 'test-session-memo-01';

/**
 * Known-valid cross-repo-memo fixture. created: 2026-05-01 is BEFORE the
 * 2026-05-22 grandfather cutoff (schema.js applyCrossFieldRulesFor
 * 'cross-repo-memo' Rule 1) so cross-field validation is skipped entirely —
 * keeps the fixture minimal while still exercising the real validation seam
 * (skip branch, not a bypass of the code path).
 */
const VALID_MEMO_BODY = `---
schema: cross-repo-memo
title: "Test memo for regression fixture"
status: open
created: 2026-05-01
from: repo-a
to: repo-b
---
# Test Memo
body
`;

let tmpRoot;

function writeMemo(slug, content) {
  const p = path.join(tmpRoot, `${slug}.md`);
  fs.writeFileSync(p, content, 'utf8');
  return p;
}

function runVerb(verb, args) {
  return execFileSync(
    process.execPath,
    [MEMO_TRANSITION, verb, ...args],
    { encoding: 'utf8' }
  );
}

before(() => {
  tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'test-memo-transition-'));
});

after(() => {
  fs.rmSync(tmpRoot, { recursive: true, force: true });
});

describe('memo-transition — byte-identical output (schema.js migration regression net)', () => {
  it('produces a fixed, known-good byte-for-byte rebuilt file on claim', () => {
    const p = writeMemo('byte-identical-claim', VALID_MEMO_BODY);
    runVerb('claim', ['--memo', p, '--session-id', SESSION_ID, '--at', AT]);
    const actual = fs.readFileSync(p, 'utf8');

    const expected = `---
schema: cross-repo-memo
title: "Test memo for regression fixture"
status: in_progress
picked_up_at: '${AT}'
picked_up_by: ${SESSION_ID}
created: 2026-05-01
from: repo-a
to: repo-b
---
# Test Memo
body
`;

    assert.strictEqual(
      actual,
      expected,
      `Post-migration claim output diverged from the known-good byte-for-byte rebuild.\n--- actual ---\n${actual}\n--- expected ---\n${expected}`
    );
  });

  it('produces a fixed, known-good byte-for-byte rebuilt file on action (--decision accepted)', () => {
    const p = writeMemo('byte-identical-action-decision', VALID_MEMO_BODY);
    runVerb('claim', ['--memo', p, '--session-id', SESSION_ID, '--at', AT]);
    runVerb('action', [
      '--memo', p,
      '--decision', 'accepted',
      '--decision-note', 'landed cleanly',
      '--realized-by', 'commit abc1234',
    ]);
    const actual = fs.readFileSync(p, 'utf8');

    const expected = `---
schema: cross-repo-memo
title: "Test memo for regression fixture"
status: actioned
decision: accepted
decision_note: landed cleanly
realized_by: commit abc1234
picked_up_at: '${AT}'
picked_up_by: ${SESSION_ID}
created: 2026-05-01
from: repo-a
to: repo-b
---
# Test Memo
body
`;

    assert.strictEqual(
      actual,
      expected,
      `Post-migration action(--decision) output diverged from the known-good byte-for-byte rebuild.\n--- actual ---\n${actual}\n--- expected ---\n${expected}`
    );
  });

  it('produces a fixed, known-good byte-for-byte rebuilt file on action (--actioned-note, consult/fyi shape)', () => {
    const p = writeMemo('byte-identical-action-note', VALID_MEMO_BODY);
    runVerb('claim', ['--memo', p, '--session-id', SESSION_ID, '--at', AT]);
    runVerb('action', ['--memo', p, '--actioned-note', 'acknowledged, no action needed']);
    const actual = fs.readFileSync(p, 'utf8');

    const expected = `---
schema: cross-repo-memo
title: "Test memo for regression fixture"
status: actioned
actioned_note: 'acknowledged, no action needed'
picked_up_at: '${AT}'
picked_up_by: ${SESSION_ID}
created: 2026-05-01
from: repo-a
to: repo-b
---
# Test Memo
body
`;

    assert.strictEqual(
      actual,
      expected,
      `Post-migration action(--actioned-note) output diverged from the known-good byte-for-byte rebuild.\n--- actual ---\n${actual}\n--- expected ---\n${expected}`
    );
  });

  it('produces a fixed, known-good byte-for-byte rebuilt file on release', () => {
    const p = writeMemo('byte-identical-release', VALID_MEMO_BODY);
    runVerb('claim', ['--memo', p, '--session-id', SESSION_ID, '--at', AT]);
    runVerb('release', ['--memo', p]);
    const actual = fs.readFileSync(p, 'utf8');

    // release CLEARS picked_up_by/picked_up_at entirely (negative-spec in
    // memo-transition.js release(): contrast with action, which preserves them) —
    // output is byte-identical to the original fixture.
    const expected = VALID_MEMO_BODY;

    assert.strictEqual(
      actual,
      expected,
      `Post-migration release output diverged from the known-good byte-for-byte rebuild.\n--- actual ---\n${actual}\n--- expected ---\n${expected}`
    );
  });
});
