'use strict';
/**
 * schema.frontmatter-write.test.js — unit tests for the write-side frontmatter
 * primitives (splitFrontmatter / readFmField / serializeYamlScalar /
 * replaceFmField / insertFmField) exported from bin/lib/schema.js.
 *
 * Run with: node bin/lib/schema.frontmatter-write.test.js
 *
 * Spec backlink: these 5 primitives were extracted 2026-07-09 from divergent
 * copies in handoff-transition.js, memo-transition.js,
 * normalize-consumed-frontmatter.js, and stamp-shipped-in.js into this single
 * canonical implementation. Locks the reconciled behavior (boundary-lookahead
 * key matching, block-scalar replace guard, preamble round-trip, quoting
 * edge cases) so downstream CLIs can be safely repointed at this module.
 */

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const {
  splitFrontmatter,
  readFmField,
  serializeYamlScalar,
  replaceFmField,
  insertFmField,
  removeFmField,
} = require('./schema.js');

describe('splitFrontmatter', () => {
  it('splits a simple frontmatter document', () => {
    const content = '---\nstatus: active\nkind: handoff\n---\nBody text.\n';
    const result = splitFrontmatter(content);
    assert.ok(result);
    assert.equal(result.preamble, '');
    assert.equal(result.fmText, 'status: active\nkind: handoff\n');
    assert.equal(result.bodyWithLeadingNewline, '\nBody text.\n');
  });

  it('returns null for content with no frontmatter', () => {
    assert.equal(splitFrontmatter('Just a plain markdown file.\n'), null);
  });

  it('returns null when the closing --- is missing', () => {
    assert.equal(splitFrontmatter('---\nstatus: active\n'), null);
  });

  it('tolerates a leading HTML comment preamble and captures it verbatim', () => {
    const content =
      '<!-- provenance: installer-seeded 2026-05-01 -->\n---\nstatus: active\n---\nBody.\n';
    const result = splitFrontmatter(content);
    assert.ok(result);
    assert.equal(result.preamble, '<!-- provenance: installer-seeded 2026-05-01 -->\n');
    assert.equal(result.fmText, 'status: active\n');
    assert.equal(result.bodyWithLeadingNewline, '\nBody.\n');
  });

  it('tolerates leading blank lines before the opening ---', () => {
    const content = '\n\n---\nstatus: active\n---\nBody.\n';
    const result = splitFrontmatter(content);
    assert.ok(result);
    assert.equal(result.preamble, '\n\n');
  });

  it('preserves the body leading blank line (does not over-consume with \\s)', () => {
    const content = '---\nstatus: active\n---\n\nBody starts after a blank line.\n';
    const result = splitFrontmatter(content);
    assert.ok(result);
    assert.equal(result.bodyWithLeadingNewline, '\n\nBody starts after a blank line.\n');
  });
});

describe('readFmField', () => {
  const fmText = '\nstatus: active\nstatus_message: all good\ncount: 3\n';

  it('reads an existing field value, trimmed', () => {
    assert.equal(readFmField(fmText, 'status'), 'active');
  });

  it('returns null for an absent key', () => {
    assert.equal(readFmField(fmText, 'missing_key'), null);
  });

  it('does not match a key that is a prefix of a longer key (boundary lookahead)', () => {
    // "status" must not match the "status_message:" line.
    const onlyLongKey = '\nstatus_message: hello\n';
    assert.equal(readFmField(onlyLongKey, 'status'), null);
  });

  it('reads the correct field when both a key and its longer sibling are present', () => {
    assert.equal(readFmField(fmText, 'status_message'), 'all good');
  });

  it('strips a matched pair of surrounding double quotes (A-F3)', () => {
    assert.equal(readFmField('\nstatus: "draft"\n', 'status'), 'draft');
  });

  it('strips a matched pair of surrounding single quotes, unfolding \'\'-escape (A-F3)', () => {
    assert.equal(readFmField("\nstatus: 'it''s draft'\n", 'status'), "it's draft");
  });

  it('does not treat a regex-metachar key as a pattern (A-F2)', () => {
    // A literal "." key must match only a literal "." — not "status" via /./.
    const fm = '\n.: active\nstatus: other\n';
    assert.equal(readFmField(fm, '.'), 'active');
  });
});

describe('serializeYamlScalar', () => {
  it('leaves a plain scalar unquoted', () => {
    assert.equal(serializeYamlScalar('active'), 'active');
  });

  it('quotes a value containing a hash (comment risk)', () => {
    assert.equal(serializeYamlScalar('abc123 #42'), "'abc123 #42'");
  });

  it('quotes a value starting with a dash', () => {
    assert.equal(serializeYamlScalar('-leading-dash'), "'-leading-dash'");
  });

  it('quotes an all-numeric value (would parse as a YAML integer)', () => {
    assert.equal(serializeYamlScalar('274671833'), "'274671833'");
  });

  it('quotes a scientific-notation-shaped value', () => {
    assert.equal(serializeYamlScalar('1958e194'), "'1958e194'");
  });

  it('escapes internal single quotes by doubling', () => {
    assert.equal(serializeYamlScalar("it's a test: yes"), "'it''s a test: yes'");
  });

  it('quotes a value with a leading space', () => {
    assert.equal(serializeYamlScalar(' leading space'), "' leading space'");
  });
});

describe('replaceFmField', () => {
  it('replaces an existing field value and preserves other keys and their order', () => {
    const fmText = '\nstatus: active\nkind: handoff\ndeployment_state: in_flight\n';
    const result = replaceFmField(fmText, 'status', 'consumed');
    assert.equal(result, '\nstatus: consumed\nkind: handoff\ndeployment_state: in_flight\n');
  });

  it('quotes the replacement value when it needs quoting', () => {
    const fmText = '\nshipped_in: pending\n';
    const result = replaceFmField(fmText, 'shipped_in', 'abc123 #42');
    assert.equal(result, "\nshipped_in: 'abc123 #42'\n");
  });

  it('does not corrupt a sibling field that is a prefix-collision risk', () => {
    const fmText = '\nstatus: active\nstatus_message: leave me alone\n';
    const result = replaceFmField(fmText, 'status', 'consumed');
    assert.equal(result, '\nstatus: consumed\nstatus_message: leave me alone\n');
  });

  it('writes a value containing $1/$&/$$ literally, not as a replace() pattern token (A-F1)', () => {
    const fmText = '\nnote: pending\n';
    const result = replaceFmField(fmText, 'note', 'has $1 and $& and $$ literally');
    assert.equal(result, "\nnote: 'has $1 and $& and $$ literally'\n");
  });

  it('does not construct a broken regex when the key contains a metacharacter (A-F2)', () => {
    const fmText = '\nfield.name: old\n';
    const result = replaceFmField(fmText, 'field.name', 'new');
    assert.equal(result, '\nfield.name: new\n');
  });

  it('throws rather than truncating a block-scalar (>) value', () => {
    const fmText = '\nnotes: >\n  folded text\n  continues here\nstatus: active\n';
    assert.throws(() => replaceFmField(fmText, 'notes', 'x'), /block-scalar/);
  });

  it('throws rather than truncating a block-scalar (|) value', () => {
    const fmText = '\nnotes: |\n  literal text\nstatus: active\n';
    assert.throws(() => replaceFmField(fmText, 'notes', 'x'), /block-scalar/);
  });

  it('round-trips through splitFrontmatter: parse -> replace -> re-parse preserves other keys', () => {
    const content = '---\nstatus: active\nkind: handoff\npredecessor: none\n---\nBody.\n';
    const split = splitFrontmatter(content);
    const newFmText = replaceFmField(split.fmText, 'status', 'consumed');
    const rebuilt = split.preamble + '---' + '\n' + newFmText.replace(/^\n/, '') + '---' + split.bodyWithLeadingNewline;
    const reparsed = splitFrontmatter(rebuilt);
    assert.ok(reparsed);
    assert.equal(readFmField(reparsed.fmText, 'status'), 'consumed');
    assert.equal(readFmField(reparsed.fmText, 'kind'), 'handoff');
    assert.equal(readFmField(reparsed.fmText, 'predecessor'), 'none');
  });
});

describe('insertFmField', () => {
  it('inserts a new key immediately after the named afterKey', () => {
    const fmText = '\nstatus: active\nkind: handoff\n';
    const result = insertFmField(fmText, 'shipped_in', 'abc123', 'status');
    assert.equal(result, '\nstatus: active\nshipped_in: abc123\nkind: handoff\n');
  });

  it('quotes the inserted value when it needs quoting', () => {
    const fmText = '\nstatus: active\n';
    const result = insertFmField(fmText, 'shipped_in', 'PR#42 fixed', 'status');
    assert.equal(result, "\nstatus: active\nshipped_in: 'PR#42 fixed'\n");
  });

  it('appends to the end of frontmatter when afterKey is not present', () => {
    const fmText = '\nstatus: active\nkind: handoff\n';
    const result = insertFmField(fmText, 'shipped_in', 'abc123', 'nonexistent_key');
    assert.equal(result, '\nstatus: active\nkind: handoff\nshipped_in: abc123\n');
  });

  it('does not insert after a prefix-colliding afterKey', () => {
    // afterKey "status" must not match "status_message:" — insertion point
    // must be the "status:" line, not the longer sibling.
    const fmText = '\nstatus_message: hello\nstatus: active\n';
    const result = insertFmField(fmText, 'new_field', 'v', 'status');
    assert.equal(result, '\nstatus_message: hello\nstatus: active\nnew_field: v\n');
  });

  it('round-trips: insert then read finds the new field', () => {
    const fmText = '\nstatus: active\n';
    const result = insertFmField(fmText, 'shipped_in', '2026-07-09', 'status');
    assert.equal(readFmField(result, 'shipped_in'), '2026-07-09');
    assert.equal(readFmField(result, 'status'), 'active');
  });
});

describe('removeFmField', () => {
  it('removes the key: line and its trailing newline', () => {
    const fmText = '\nstatus: active\ngate_dependency: some subsystem\nkind: handoff\n';
    const result = removeFmField(fmText, 'gate_dependency');
    assert.equal(result, '\nstatus: active\nkind: handoff\n');
  });

  it('is boundary-safe — removing "a" does not remove sibling "ab" (B-F1)', () => {
    const result = removeFmField('a: 1\nab: 2\n', 'a');
    assert.equal(result, 'ab: 2\n');
  });

  it('is safe when the key is the last line with no trailing newline', () => {
    const fmText = '\nstatus: active\ngate_dependency: x';
    const result = removeFmField(fmText, 'gate_dependency');
    assert.equal(result, '\nstatus: active\n');
  });
});
