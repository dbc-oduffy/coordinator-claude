'use strict';
/**
 * __tests__/validate-frontmatter-schema.test.js — C0a scaffold-offer tests for the
 * PreToolUse frontmatter validator hook.
 *
 * Spec backlink: docs/plans/2026-06-29-cli-scaffold-deterministic-docs.md § C0a
 *
 * Covers:
 *   AC1 — scaffold offer fires on Write creating a new schema-matching path (no frontmatter);
 *          does NOT fire on Edit of an existing file or Write to an existing file.
 *   AC2 — drift-guard: every GENERATE-able coordinator-doc-new --type (excluding
 *          audit-record, queue types, lesson) triggers the offer on a new-file Write;
 *          vice-versa: no extra entries in SCAFFOLD_OFFER_MAP not in the covered set.
 *          Round-trip: each mapped sidecar type's derived default output path matches
 *          the schema glob the offer fires on.
 *
 * Convention: uses the same node:test / spawn pattern as the sibling test file
 * (hooks/scripts/validate-frontmatter-schema.test.js) so both files run with
 * the same runner: node --test <file>.
 *
 * Negative-spec (trigger condition):
 *   The offer fires on ANY new schema-matching file (Write + !existsSync), regardless
 *   of whether the content already contains hand-rolled frontmatter. The broadened
 *   trigger is the correct C0a semantic: even correctly-hand-authored new files are
 *   redirected to the scaffolder (which guarantees conformance; hand-rolling does not).
 *   Existing validation regression tests that write to non-existent schema paths were
 *   reconciled via pre-create: each fixture writes the file before calling the hook
 *   so fs.existsSync is true and the offer guard doesn't fire.
 */

const { describe, test } = require('node:test');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const HOOK_SCRIPT = path.join(__dirname, '..', 'validate-frontmatter-schema.js');
const COORDINATOR_ROOT = path.resolve(__dirname, '../../../../../../');
// hooks/scripts/__tests__ is 6 levels below ~/.claude:
//   ~/.claude/plugins/coordinator/hooks/scripts/__tests__
// Review: code-reviewer — F8: removed redundant COORDINATOR_ROOT alias; use COORDINATOR_ROOT throughout.

// Path to coordinator-doc-new for type-set parsing (drift-guard AC2).
const COORDINATOR_DOC_NEW = path.join(COORDINATOR_ROOT,
  'plugins', 'coordinator-claude', 'coordinator', 'bin', 'coordinator-doc-new');

// Path to schema.js for matchSchema round-trip tests.
const SCHEMA_JS = path.join(COORDINATOR_ROOT,
  'plugins', 'coordinator-claude', 'coordinator', 'bin', 'lib', 'schema.js');

const SCHEMAS_DIR = path.join(COORDINATOR_ROOT,
  'plugins', 'coordinator-claude', 'coordinator', 'schemas');

// Path to the coordinator registry manifest (single source of truth for doc-type registry).
const MANIFEST = path.join(COORDINATOR_ROOT,
  'plugins', 'coordinator-claude', 'coordinator', 'schemas', 'coordinator-registry.manifest.json');

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Spawn the hook with the given payload (object → JSON piped to stdin).
 * Returns { stdout, stderr, exitCode }.
 *
 * Pass { strict: true } to set COORDINATOR_SCHEMA_STRICT=1 so the hook
 * emits permissionDecision: 'deny' instead of additionalContext, making
 * assertions on offer presence unambiguous.
 */
function runHook(payload, opts = {}) {
  return new Promise((resolve, reject) => {
    const env = { ...process.env };
    if (opts.strict) env.COORDINATOR_SCHEMA_STRICT = '1';
    else delete env.COORDINATOR_SCHEMA_STRICT;
    const child = spawn(process.execPath, [HOOK_SCRIPT], {
      stdio: ['pipe', 'pipe', 'pipe'],
      env,
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', d => { stdout += d.toString(); });
    child.stderr.on('data', d => { stderr += d.toString(); });
    child.on('close', exitCode => resolve({ stdout, stderr, exitCode }));
    child.on('error', reject);
    child.stdin.write(JSON.stringify(payload));
    child.stdin.end();
  });
}

/** Build a minimal Write payload. */
function writePayload(filePath, content, cwd) {
  return {
    tool_name: 'Write',
    tool_input: { file_path: filePath, content },
    session_id: 'c0a-test',
    cwd: cwd || COORDINATOR_ROOT,
  };
}

/** Build a minimal Edit payload. */
function editPayload(filePath, oldString, newString, cwd) {
  return {
    tool_name: 'Edit',
    tool_input: { file_path: filePath, old_string: oldString, new_string: newString },
    session_id: 'c0a-test',
    cwd: cwd || COORDINATOR_ROOT,
  };
}

/**
 * Load the coordinator registry manifest.
 * Returns the parsed manifest object.
 */
function loadManifest() {
  return JSON.parse(fs.readFileSync(MANIFEST, 'utf8'));
}

// ---------------------------------------------------------------------------
// AC1 — scaffold offer fires on new-file Write; not on Edit or existing file
// ---------------------------------------------------------------------------

describe('C0a scaffold offer — AC1: offer fires on new-file Write, not on Edit or existing', () => {

  // AC1(a): Write creating a new plan file with NO frontmatter → scaffold offer fired
  test('AC1(a) — Write new docs/plans/*.md (no frontmatter) emits scaffold offer', async () => {
    const filePath = path.join(COORDINATOR_ROOT, 'docs', 'plans',
      'C0A-TEST-SCAFFOLD-OFFER-PLAN-DO-NOT-COMMIT.md');
    // Verify this test file does not exist on disk (precondition for new-file discriminator)
    assert.ok(!fs.existsSync(filePath), `precondition: test file must not exist: ${filePath}`);

    const content = '# Body only — no frontmatter\n';
    const { stdout, exitCode } = await runHook(writePayload(filePath, content), { strict: true });
    assert.equal(exitCode, 0, 'hook must exit 0');
    assert.ok(stdout.length > 0, 'hook must emit scaffold offer (non-empty stdout)');

    const parsed = JSON.parse(stdout);
    const h = parsed.hookSpecificOutput;
    assert.equal(h.permissionDecision, 'deny', 'strict mode: must emit deny');
    assert.ok(
      h.permissionDecisionReason.includes('coordinator-doc-new --type plan'),
      `offer must name coordinator-doc-new --type plan; got: ${h.permissionDecisionReason}`,
    );
    assert.ok(
      h.permissionDecisionReason.includes('schema: plan'),
      `offer must identify schema name; got: ${h.permissionDecisionReason}`,
    );
  });

  // AC1(b): Write creating a new prior-art-check sidecar → offer includes --plan <stem>
  test('AC1(b) — Write new docs/plans/<stem>.prior-art-check.md emits offer with --plan <stem>', async () => {
    const stem = 'C0A-TEST-PAC-SIDECAR-DO-NOT-COMMIT';
    const filePath = path.join(COORDINATOR_ROOT, 'docs', 'plans', `${stem}.prior-art-check.md`);
    assert.ok(!fs.existsSync(filePath), `precondition: test file must not exist: ${filePath}`);

    const content = '## Prior art check — body only\n';
    const { stdout, exitCode } = await runHook(writePayload(filePath, content), { strict: true });
    assert.equal(exitCode, 0);
    assert.ok(stdout.length > 0, 'scaffold offer must fire');

    const parsed = JSON.parse(stdout);
    const reason = parsed.hookSpecificOutput.permissionDecisionReason;
    assert.ok(
      reason.includes('--type prior-art-check'),
      `offer must name --type prior-art-check; got: ${reason}`,
    );
    assert.ok(
      reason.includes(`--plan ${stem}`),
      `offer must derive --plan ${stem} from path; got: ${reason}`,
    );
  });

  // AC1(c): Edit to an existing schema-matching file → NO scaffold offer
  // (Edit is not Write — the offer trigger checks toolName === 'Write')
  test('AC1(c) — Edit to existing schema-matching handoff file emits NO scaffold offer', async () => {
    // Use an existing handoff file from the repo (known to exist)
    const handoffs = fs.readdirSync(path.join(COORDINATOR_ROOT, 'state', 'handoffs'))
      .filter(f => f.endsWith('.md'));
    assert.ok(handoffs.length > 0, 'precondition: at least one handoff file must exist');
    const filePath = path.join(COORDINATOR_ROOT, 'state', 'handoffs', handoffs[0]);
    const content = fs.readFileSync(filePath, 'utf8');

    // Edit the file (replace first non-empty line with itself — a no-op edit)
    const firstLine = content.split('\n').find(l => l.trim().length > 0) || '---';
    const { stdout, exitCode } = await runHook(
      editPayload(filePath, firstLine, firstLine),
      { strict: true },
    );
    assert.equal(exitCode, 0);
    // Scaffold offer fires only for Write (toolName === 'Write' gate in hook). Edit never triggers
    // it, regardless of whether old_string === new_string.
    // review F8 — updated to attribute suppression to the toolName gate, not the no-op edit
    const isScaffoldOffer = stdout.includes('[scaffold offer]') ||
                            (stdout.length > 0 && (() => {
                              try {
                                const p = JSON.parse(stdout);
                                const r = p.hookSpecificOutput.permissionDecisionReason || '';
                                return r.includes('coordinator-doc-new --type');
                              } catch { return false; }
                            })());
    assert.ok(!isScaffoldOffer, `Edit must NOT emit scaffold offer; got: ${stdout}`);
  });

  // AC1(d): Write to an EXISTING schema-matching file → NO scaffold offer
  // (existsSync check discriminates new vs existing)
  test('AC1(d) — Write to existing schema-matching plan file emits NO scaffold offer', async () => {
    // Use an existing plan file from the repo
    // Plain plan files: exactly one dot (the .md extension); sidecars have two dots (e.g. .review.md)
    const plans = fs.readdirSync(path.join(COORDINATOR_ROOT, 'docs', 'plans'))
      .filter(f => f.endsWith('.md') && f.split('.').length === 2);
    // pick one that exists (plain .md, not sidecar)
    const existing = plans.find(f => fs.existsSync(path.join(COORDINATOR_ROOT, 'docs', 'plans', f)));
    assert.ok(existing, 'precondition: at least one plan file must exist');
    const filePath = path.join(COORDINATOR_ROOT, 'docs', 'plans', existing);

    const content = '# No frontmatter — but file exists\n';
    const { stdout, exitCode } = await runHook(writePayload(filePath, content), { strict: true });
    assert.equal(exitCode, 0);

    const isScaffoldOffer = stdout.length > 0 && (() => {
      try {
        const p = JSON.parse(stdout);
        const r = (p.hookSpecificOutput || {}).permissionDecisionReason || '';
        return r.includes('coordinator-doc-new');
      } catch { return false; }
    })();
    assert.ok(!isScaffoldOffer,
      `Write to EXISTING plan must NOT emit scaffold offer (existsSync guard); got: ${stdout}`);
  });

});

// ---------------------------------------------------------------------------
// AC2 — drift-guard: set parity + round-trip
// ---------------------------------------------------------------------------

describe('C0a scaffold offer — AC2: drift-guard set parity and sidecar round-trip', () => {

  // AC2(a): Every covered GENERATE-able type fires the scaffold offer on new-file Write.
  //
  // Covered types (subset of _KNOWN_TYPES ∪ _SIDECAR_TYPES):
  //   handoff, spinoff (shares handoff schema), plan, decision, review, prior-art-check,
  //   plan-coverage-check, docs-check.
  //
  // Excluded types (documented — satisfies "and vice-versa" side of set parity):
  //   audit-record    — requires --system <name>, not path-derivable
  //   spinoff         — shares handoff schema (handoff entry covers it)
  //   memo            — local draft has no stable schema glob; cross-repo-memo has own offer
  //   improvement-queue, bug-backlog, debt-backlog — delegate to coordinator-queue-append
  //   lesson          — delegates to coordinator-lesson-promote
  //
  // Fixture: type → { samplePath, isSidecar, expectedTypeToken, expectedPlanStem }
  // samplePath uses paths that do NOT exist on disk (precondition for new-file discriminator).
  const COVERED_TYPE_FIXTURE = [
    {
      type: 'handoff',
      samplePath: 'state/handoffs/C0A-DRIFT-GUARD-HANDOFF.md',
      expectedTypeToken: 'handoff',
      isSidecar: false,
    },
    {
      type: 'plan',
      samplePath: 'docs/plans/C0A-DRIFT-GUARD-PLAN.md',
      expectedTypeToken: 'plan',
      isSidecar: false,
    },
    {
      type: 'decision',
      samplePath: 'docs/decisions/DR-C0A-DRIFT-GUARD.md',
      expectedTypeToken: 'decision',
      isSidecar: false,
    },
    {
      type: 'review',
      samplePath: 'docs/plans/C0A-DRIFT-GUARD.review.md',
      expectedTypeToken: 'review',
      isSidecar: true,
      expectedPlanStem: 'C0A-DRIFT-GUARD',
    },
    {
      type: 'prior-art-check',
      samplePath: 'docs/plans/C0A-DRIFT-GUARD.prior-art-check.md',
      expectedTypeToken: 'prior-art-check',
      isSidecar: true,
      expectedPlanStem: 'C0A-DRIFT-GUARD',
    },
    {
      type: 'plan-coverage-check',
      samplePath: 'docs/plans/C0A-DRIFT-GUARD.plan-coverage-check.md',
      expectedTypeToken: 'plan-coverage-check',
      isSidecar: true,
      expectedPlanStem: 'C0A-DRIFT-GUARD',
    },
    {
      type: 'docs-check',
      samplePath: 'docs/plans/C0A-DRIFT-GUARD.docs-check.md',
      expectedTypeToken: 'docs-check',
      isSidecar: true,
      expectedPlanStem: 'C0A-DRIFT-GUARD',
    },
    {
      type: 'problem-set',
      samplePath: 'docs/problems/2026-06-30-test.md',
      expectedTypeToken: 'problem-set',
      isSidecar: false,
    },
    {
      type: 'completion',
      samplePath: 'archive/completed/2026-06/2026-06-30-test.md',
      expectedTypeToken: 'completion',
      isSidecar: false,
    },
    {
      type: 'health-status',
      samplePath: 'state/health/2026-06-30-test.md',
      expectedTypeToken: 'health-status',
      isSidecar: false,
    },
    {
      type: 'research-synthesis',
      samplePath: 'docs/research/2026-06-30-drift-guard-test.md',
      expectedTypeToken: 'research-synthesis',
      isSidecar: false,
    },
  ];

  // Run each covered type as an individual test so failures are individually identified.
  for (const fixture of COVERED_TYPE_FIXTURE) {
    const { type, samplePath, expectedTypeToken, isSidecar, expectedPlanStem } = fixture;

    test(`AC2(a) — covered type '${type}': Write new ${samplePath} fires scaffold offer`, async () => {
      const filePath = path.join(COORDINATOR_ROOT, ...samplePath.split('/'));
      assert.ok(!fs.existsSync(filePath),
        `precondition: drift-guard sample path must not exist: ${filePath}`);

      const content = `# Drift-guard body for --type ${type}\n`;
      const { stdout, exitCode } = await runHook(writePayload(filePath, content), { strict: true });
      assert.equal(exitCode, 0);
      assert.ok(stdout.length > 0, `type '${type}': scaffold offer must fire (non-empty stdout)`);

      const parsed = JSON.parse(stdout);
      const reason = parsed.hookSpecificOutput.permissionDecisionReason;
      assert.ok(
        reason.includes(`--type ${expectedTypeToken}`),
        `type '${type}': offer must include --type ${expectedTypeToken}; got: ${reason}`,
      );
      if (isSidecar && expectedPlanStem) {
        assert.ok(
          reason.includes(`--plan ${expectedPlanStem}`),
          `type '${type}' (sidecar): offer must derive --plan ${expectedPlanStem}; got: ${reason}`,
        );
      }
    });
  }

  // AC2(b): Excluded type 'audit-record' does NOT fire the scaffold offer.
  test('AC2(b) — excluded type audit-record: Write new audit-record path does NOT fire offer', async () => {
    const filePath = path.join(COORDINATOR_ROOT, 'docs', 'architecture', 'audit-records',
      'C0A-DRIFT-GUARD-AUDIT.md');
    assert.ok(!fs.existsSync(filePath),
      `precondition: drift-guard audit path must not exist: ${filePath}`);

    const content = '# Audit record body (no frontmatter)\n';
    const { stdout, exitCode } = await runHook(writePayload(filePath, content), { strict: true });
    assert.equal(exitCode, 0);

    // audit-record is NOT in SCAFFOLD_OFFER_MAP — no scaffold offer should fire
    const isScaffoldOffer = stdout.length > 0 && (() => {
      try {
        const p = JSON.parse(stdout);
        const r = (p.hookSpecificOutput || {}).permissionDecisionReason || '';
        return r.includes('coordinator-doc-new --type');
      } catch { return false; }
    })();
    assert.ok(!isScaffoldOffer,
      `audit-record is excluded: scaffold offer must NOT fire; got: ${stdout}`);
  });

  // AC2(c): Manifest validity — both consumers (the Python CLIs and the Node hook) now read
  // coordinator-registry.manifest.json as the single source of truth, so set-parity is
  // structural. This test guards the manifest's own internal correctness.
  //
  // Because both consumers share one file, a well-formed manifest is sufficient to ensure
  // they stay in sync; the old regex-scraping set-parity check is superseded.
  test('AC2(c) — manifest validity: offer/exclude disposition + identity triples well-formed', () => {
    const manifest = loadManifest();
    const { loadSchemas } = require(SCHEMA_JS);
    const schemas = loadSchemas(SCHEMAS_DIR);

    assert.ok(Array.isArray(manifest.docTypes), 'manifest.docTypes must be an array');
    assert.ok(manifest.docTypes.length > 0, 'manifest.docTypes must be non-empty');

    for (const entry of manifest.docTypes) {
      const label = `docTypes entry for type '${entry.type}'`;

      // offerable must be an explicit boolean (not undefined/null/defaulted).
      assert.strictEqual(typeof entry.offerable, 'boolean',
        `${label}: offerable must be typeof boolean, got ${typeof entry.offerable}`);

      // isSidecar must be an explicit boolean.
      assert.strictEqual(typeof entry.isSidecar, 'boolean',
        `${label}: isSidecar must be typeof boolean, got ${typeof entry.isSidecar}`);

      if (!entry.offerable) {
        // offerable:false entries must carry a non-empty excludeReason.
        assert.ok(
          typeof entry.excludeReason === 'string' && entry.excludeReason.trim().length > 0,
          `${label}: offerable:false entry must have a non-empty string excludeReason`,
        );
      } else {
        // offerable:true entries must have a non-null schemaName that resolves to a loaded schema.
        assert.ok(
          entry.schemaName !== null && entry.schemaName !== undefined,
          `${label}: offerable:true entry must have a non-null schemaName`,
        );
        assert.ok(
          Object.prototype.hasOwnProperty.call(schemas, entry.schemaName),
          `${label}: offerable:true entry schemaName '${entry.schemaName}' does not resolve ` +
          `to a loaded schema. Check SCHEMAS_DIR or the schemaName spelling.`,
        );
        // review F2 — type must be a non-empty string. A null/undefined type would produce
        // "--type undefined" in the scaffold offer, which errors at the CLI.
        assert.ok(
          typeof entry.type === 'string' && entry.type.trim().length > 0,
          `${label}: offerable:true entry must have a non-empty string type`,
        );
      }
    }

    // Identity triples well-formed: every repoAliases entry has required fields and the
    // dirBasename === registryKey.replace(/_/g, '-') convention is upheld.
    const { repoAliases } = manifest.identity;
    assert.ok(Array.isArray(repoAliases), 'manifest.identity.repoAliases must be an array');
    for (const alias of repoAliases) {
      const label = `repoAliases entry ${JSON.stringify(alias)}`;
      assert.ok(
        typeof alias.registryKey === 'string' && alias.registryKey.trim().length > 0,
        `${label}: registryKey must be a non-empty string`,
      );
      assert.ok(
        typeof alias.dirBasename === 'string' && alias.dirBasename.trim().length > 0,
        `${label}: dirBasename must be a non-empty string`,
      );
      assert.ok(
        typeof alias.shortname === 'string' && alias.shortname.trim().length > 0,
        `${label}: shortname must be a non-empty string`,
      );
      // The underscore→dash convention between registryKey and dirBasename is pinned.
      const expectedBasename = alias.registryKey.replace(/_/g, '-');
      assert.strictEqual(
        alias.dirBasename,
        expectedBasename,
        `${label}: dirBasename must equal registryKey.replace(/_/g, '-') ` +
        `(expected '${expectedBasename}', got '${alias.dirBasename}')`,
      );
    }

    // review F4 — assert uniqueness of offerable schemaNames. Object.fromEntries silently
    // takes the last entry on key collision; a duplicate schemaName shadows the earlier
    // SCAFFOLD_OFFER_MAP entry with no runtime error until a test exercises the shadowed path.
    const offerableSchemaNames = manifest.docTypes
      .filter(d => d.offerable === true)
      .map(d => d.schemaName);
    assert.strictEqual(
      offerableSchemaNames.length,
      new Set(offerableSchemaNames).size,
      `manifest.docTypes: offerable:true entries must have unique schemaNames; duplicates: ` +
      `${offerableSchemaNames.filter((n, i) => offerableSchemaNames.indexOf(n) !== i).join(', ')}`,
    );

    // review F3 — validate kindOfferOverride entry shapes. Missing type or isSidecar silently
    // produces undefined values in KIND_OFFER_OVERRIDE, yielding broken scaffold offers.
    for (const [kind, entry] of Object.entries(manifest.kindOfferOverride)) {
      const kindLabel = `kindOfferOverride entry for kind '${kind}'`;
      assert.ok(
        typeof entry.type === 'string' && entry.type.trim().length > 0,
        `${kindLabel}: type must be a non-empty string`,
      );
      assert.strictEqual(
        typeof entry.isSidecar, 'boolean',
        `${kindLabel}: isSidecar must be typeof boolean, got ${typeof entry.isSidecar}`,
      );
      assert.ok(
        entry.manualArgs === null || typeof entry.manualArgs === 'string',
        `${kindLabel}: manualArgs must be null or a string, got ${typeof entry.manualArgs}`,
      );
      assert.ok(
        entry.authoringHint === null || typeof entry.authoringHint === 'string',
        `${kindLabel}: authoringHint must be null or a string, got ${typeof entry.authoringHint}`,
      );
    }

    // review F5 — assert centralReceiverIds is non-empty.
    // An empty array is valid JSON and passes the manifest-load guard, but produces an
    // empty Set that silently misfires routing offers for correctly-addressed central memos.
    // NOTE: centralRepoBasenames was retired in C1 (central-identity-flip plan) — the hook
    // now path-anchors central detection via machine-local repos.doe_claude instead of a
    // manifest basename set (C3). Do NOT restore this assertion.
    assert.ok(
      Array.isArray(manifest.identity.centralReceiverIds) && manifest.identity.centralReceiverIds.length > 0,
      'manifest.identity.centralReceiverIds must be a non-empty array',
    );
  });

  // AC2(d): Round-trip — each sidecar type's default output path (docs/plans/<stem>.<type>.md)
  // is matched by matchSchema as the SAME schema name recorded in the manifest.
  // This catches schema-glob renames that would silently break the offer.
  // Sourced from the manifest (manifest.docTypes where isSidecar && offerable) to avoid
  // parsing the hook source now that the literal SCAFFOLD_OFFER_MAP is gone.
  // review F6 — moved before AC2(e)/AC2(f) to restore sequential AC2(c)→(d)→(e)→(f) order.
  test('AC2(d) — round-trip: sidecar sample paths match expected schema names', () => {
    const { loadSchemas, matchSchema } = require(SCHEMA_JS);
    const schemas = loadSchemas(SCHEMAS_DIR);
    const manifest = loadManifest();

    const sidecarEntries = manifest.docTypes.filter(d => d.isSidecar && d.offerable);
    assert.ok(sidecarEntries.length > 0, 'precondition: at least one offerable sidecar entry in manifest.docTypes');

    for (const entry of sidecarEntries) {
      const { schemaName, type } = entry;
      // Construct a canonical sample path for this sidecar type.
      // Pattern: docs/plans/<stem>.<type>.md (matches _default_output_path in coordinator-doc-new)
      const samplePath = `docs/plans/2026-06-29-round-trip-test.${type}.md`;
      const matched = matchSchema(samplePath, null, schemas);
      assert.ok(matched,
        `round-trip: samplePath '${samplePath}' for type '${type}' matches no schema. ` +
        `Check schema applies_to glob for schema '${schemaName}'.`);
      assert.equal(matched.schemaName, schemaName,
        `round-trip: samplePath '${samplePath}' for type '${type}' matched schema ` +
        `'${matched.schemaName}' but manifest expects schema '${schemaName}'. ` +
        `Schema glob or manifest entry needs updating.`);
    }
  });

  // AC2(e): kind: spinoff frontmatter offers --type spinoff (NOT --type handoff),
  // even though the path resolves to schemaName 'handoff'. Regression for the
  // 2026-06-30 hand-rolled-spinoff drift incident.
  test('AC2(e) — kind: spinoff offers --type spinoff, not --type handoff', async () => {
    const filePath = path.join(COORDINATOR_ROOT, 'state', 'handoffs', 'KIND-OVERRIDE-SPINOFF.md');
    assert.ok(!fs.existsSync(filePath),
      `precondition: kind-override sample path must not exist: ${filePath}`);

    const content = '---\nkind: spinoff\n---\n# spinoff body\n';
    const { stdout, exitCode } = await runHook(writePayload(filePath, content), { strict: true });
    assert.equal(exitCode, 0);
    assert.ok(stdout.length > 0, 'scaffold offer must fire for kind: spinoff');

    const reason = JSON.parse(stdout).hookSpecificOutput.permissionDecisionReason;
    // Review: code-reviewer — replaced two substring assertions with one boundary-anchored
    // regex. '--type spinoff-roadmap'.includes('--type spinoff') is true, so the first
    // assertion alone was non-discriminating. The negative-lookahead /(?!-roadmap)/ closes
    // that trap so --type spinoff-roadmap would correctly fail this assertion.
    assert.ok(
      /--type spinoff(?!-roadmap)/.test(reason),
      `offer must name --type spinoff (not spinoff-roadmap); got: ${reason}`,
    );
    assert.ok(!reason.includes('--type handoff'),
      `offer must NOT name --type handoff for a spinoff; got: ${reason}`);
  });

  // AC2(f): kind: spinoff-roadmap offers --type spinoff-roadmap with the
  // non-derivable required args surfaced as placeholders.
  test('AC2(f) — kind: spinoff-roadmap offers --type spinoff-roadmap with placeholder args', async () => {
    const filePath = path.join(COORDINATOR_ROOT, 'state', 'handoffs', 'KIND-OVERRIDE-ROADMAP.md');
    assert.ok(!fs.existsSync(filePath),
      `precondition: kind-override sample path must not exist: ${filePath}`);

    const content = '---\nkind: spinoff-roadmap\n---\n# roadmap stub body\n';
    const { stdout, exitCode } = await runHook(writePayload(filePath, content), { strict: true });
    assert.equal(exitCode, 0);
    assert.ok(stdout.length > 0, 'scaffold offer must fire for kind: spinoff-roadmap');

    const reason = JSON.parse(stdout).hookSpecificOutput.permissionDecisionReason;
    assert.ok(reason.includes('--type spinoff-roadmap'),
      `offer must name --type spinoff-roadmap; got: ${reason}`);
    assert.ok(reason.includes('--roadmap-id') && reason.includes('--stub-id'),
      `offer must surface --roadmap-id / --stub-id placeholders; got: ${reason}`);
    assert.ok(!reason.includes('--type handoff'),
      `offer must NOT name --type handoff for a spinoff-roadmap; got: ${reason}`);
  });

});

// ---------------------------------------------------------------------------
// C2 — canonical sidecar body skeletons (AC5 + AC9)
//
// Spec backlink: docs/plans/2026-06-29-cli-scaffold-deterministic-docs.md § C2
//
// AC5: each sidecar --type emits its canonical bucket/table headings, NOT the
//      old generic "## Summary / ## Findings" body.
// AC9: each scaffolded sidecar's frontmatter validates clean against its schema
//      (0 violations) — body enrichment must not break frontmatter conformance.
// ---------------------------------------------------------------------------

// Python interpreter command: Windows ships 'python', macOS/Linux ship 'python3'.
const PYTHON_CMD = process.platform === 'win32' ? 'python' : 'python3';

/**
 * Scaffold a sidecar via coordinator-doc-new and return its content + path.
 * Sets TMPDIR in the subprocess env so the path-containment guard accepts
 * the temp dir as a valid write root (coordinator-doc-new § _safe_output_roots).
 */
function scaffoldSidecar(type, stem) {
  return new Promise((resolve, reject) => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), `c2-scaffold-${type}-`));
    fs.mkdirSync(path.join(tmp, 'docs', 'plans'), { recursive: true });

    const child = spawn(
      PYTHON_CMD,
      [COORDINATOR_DOC_NEW, '--type', type, '--plan', stem],
      {
        cwd: tmp,
        // TMPDIR must be the parent of the temp dir so coordinator-doc-new's
        // _safe_output_roots() accepts writes under it.
        env: { ...process.env, TMPDIR: os.tmpdir() },
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true,  // suppress console popup on Windows (CREATE_NO_WINDOW equivalent)
      },
    );

    let stdout = '';
    let stderr = '';
    child.stdout.on('data', d => { stdout += d.toString(); });
    child.stderr.on('data', d => { stderr += d.toString(); });

    child.on('error', reject);
    child.on('close', exitCode => {
      if (exitCode !== 0) {
        return reject(new Error(
          `coordinator-doc-new --type ${type} exited ${exitCode}\n` +
          `stdout: ${stdout}\nstderr: ${stderr}`,
        ));
      }
      // stdout is the written path (printed by coordinator-doc-new)
      const writtenPath = stdout.trim();
      // Resolve relative to cwd if not absolute
      const outPath = path.isAbsolute(writtenPath)
        ? writtenPath
        : path.join(tmp, writtenPath);
      try {
        const content = fs.readFileSync(outPath, 'utf8');
        resolve({ content, outPath, tmp });
      } catch (e) {
        reject(new Error(
          `coordinator-doc-new --type ${type}: output file not readable at ${outPath}\n` +
          `stdout: ${stdout}\nstderr: ${stderr}\nerr: ${e.message}`,
        ));
      }
    });
  });
}

describe('C2 scaffold bodies — AC5: canonical bucket/table headings per sidecar type', () => {

  // AC5(prior-art-check): 3 canonical buckets from agents/prior-art-checker.md § Sidecar Format
  test('AC5 prior-art-check — emits Conflicts / Compatible-but-relevant / Silent headings', async () => {
    const { content } = await scaffoldSidecar('prior-art-check', 'c2-test-plan');

    assert.ok(
      content.includes('### Conflicts (plan contradicts prior art)'),
      `prior-art-check must include Conflicts heading; got:\n${content}`,
    );
    assert.ok(
      content.includes('### Compatible-but-relevant (plan should cite or align)'),
      `prior-art-check must include Compatible-but-relevant heading; got:\n${content}`,
    );
    assert.ok(
      content.includes('### Silent areas (no prior art found)'),
      `prior-art-check must include Silent areas heading; got:\n${content}`,
    );
    // Negative: must NOT contain the old generic ## Findings section
    assert.ok(
      !content.includes('\n## Findings\n'),
      `prior-art-check must NOT include generic ## Findings section; got:\n${content}`,
    );
  });

  // AC5(plan-coverage-check): 4 section headings (covering 5 named buckets) from
  // agents/plan-coverage-checker.md § Sidecar Format (Weak-OOS and Hedges share one section)
  test('AC5 plan-coverage-check — emits Missed / Ambiguous / Weak-OOS+Hedges / Substrate-drift headings', async () => {
    const { content } = await scaffoldSidecar('plan-coverage-check', 'c2-test-plan');

    assert.ok(
      content.includes('### Missed audit items'),
      `plan-coverage-check must include Missed heading; got:\n${content}`,
    );
    assert.ok(
      content.includes('### Ambiguous audit items'),
      `plan-coverage-check must include Ambiguous heading; got:\n${content}`,
    );
    assert.ok(
      content.includes('### Weak OOS / hedges'),
      `plan-coverage-check must include Weak OOS / hedges heading; got:\n${content}`,
    );
    assert.ok(
      content.includes('### Substrate drift'),
      `plan-coverage-check must include Substrate drift heading; got:\n${content}`,
    );
    // Negative: must NOT contain the old generic ## Findings section
    assert.ok(
      !content.includes('\n## Findings\n'),
      `plan-coverage-check must NOT include generic ## Findings section; got:\n${content}`,
    );
  });

  // AC5(docs-check): verification TABLE from agents/docs-checker.md § Output Format
  test('AC5 docs-check — emits Verification Report + Table with column headers + Incorrect/Unverified sections', async () => {
    const { content } = await scaffoldSidecar('docs-check', 'c2-test-plan');

    assert.ok(
      content.includes('## Docs Verification Report'),
      `docs-check must include Docs Verification Report heading; got:\n${content}`,
    );
    assert.ok(
      content.includes('### Verification Table'),
      `docs-check must include Verification Table heading; got:\n${content}`,
    );
    assert.ok(
      content.includes('| # | Claim | Source | Status | Action | Detail |'),
      `docs-check must include Verification Table column headers; got:\n${content}`,
    );
    assert.ok(
      content.includes('### Incorrect Claims'),
      `docs-check must include Incorrect Claims heading; got:\n${content}`,
    );
    assert.ok(
      content.includes('### Unverified Claims'),
      `docs-check must include Unverified Claims heading; got:\n${content}`,
    );
    // Negative: must NOT contain the old generic ## Findings section
    assert.ok(
      !content.includes('\n## Findings\n'),
      `docs-check must NOT include generic ## Findings section; got:\n${content}`,
    );
  });

  // AC5(review): Summary + Findings-by-severity (critical/major/minor/nitpick) + Verdict
  test('AC5 review — emits Summary + Findings with severity sub-sections + Verdict', async () => {
    const { content } = await scaffoldSidecar('review', 'c2-test-plan');

    assert.ok(
      content.includes('## Summary'),
      `review must include Summary heading; got:\n${content}`,
    );
    assert.ok(
      content.includes('## Findings'),
      `review must include Findings heading; got:\n${content}`,
    );
    assert.ok(
      content.includes('### critical'),
      `review must include critical severity sub-section; got:\n${content}`,
    );
    assert.ok(
      content.includes('### major'),
      `review must include major severity sub-section; got:\n${content}`,
    );
    assert.ok(
      content.includes('### minor'),
      `review must include minor severity sub-section; got:\n${content}`,
    );
    assert.ok(
      content.includes('### nitpick'),
      `review must include nitpick severity sub-section; got:\n${content}`,
    );
    assert.ok(
      content.includes('## Verdict'),
      `review must include Verdict heading; got:\n${content}`,
    );
  });

});

describe('C2 scaffold bodies — AC9: frontmatter conformance (0 violations) per sidecar type', () => {

  const SIDECAR_TYPES = ['prior-art-check', 'plan-coverage-check', 'docs-check', 'review'];

  for (const type of SIDECAR_TYPES) {
    test(`AC9 ${type} — scaffolded frontmatter validates clean (0 hook violations, strict mode)`, async () => {
      const { content, outPath, tmp } = await scaffoldSidecar(type, 'c2-ac9-test');

      // Pre-create: existsSync must be true so the C0a scaffold offer does not fire.
      // The file was already written by coordinator-doc-new; this write keeps the
      // disk state consistent with the hook payload.
      fs.writeFileSync(outPath, content);

      const payload = {
        tool_name: 'Write',
        tool_input: { file_path: outPath, content },
        session_id: 'c2-ac9',
        cwd: tmp,
      };

      const { stdout, exitCode } = await runHook(payload, { strict: true });

      assert.equal(exitCode, 0, `hook must exit 0 for type ${type}`);
      assert.equal(
        stdout,
        '',
        `AC9: ${type} scaffolded frontmatter must produce 0 violations in strict mode;\n` +
        `got hook output: ${stdout}\nScaffolded content:\n${content}`,
      );
    });
  }

});

// ---------------------------------------------------------------------------
// C3a — problem-set scaffold (AC6)
//
// Spec backlink: docs/plans/2026-06-29-cli-scaffold-deterministic-docs.md § C3a
//
// AC6: scaffold --type problem-set emits the canonical section headings (## Problems,
//      ## Out of scope (architectural reasons)) and its frontmatter validates clean
//      against the problem-set schema (0 violations, strict mode).
// ---------------------------------------------------------------------------

/**
 * Scaffold a problem-set via coordinator-doc-new and return its content + path.
 * Sets TMPDIR in the subprocess env so the path-containment guard accepts
 * the temp dir as a valid write root (coordinator-doc-new § _safe_output_roots).
 */
function scaffoldProblemSet(title) {
  return new Promise((resolve, reject) => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'c3a-scaffold-problem-set-'));
    fs.mkdirSync(path.join(tmp, 'docs', 'problems'), { recursive: true });

    const args = ['--type', 'problem-set'];
    if (title) args.push('--title', title);

    const child = spawn(
      PYTHON_CMD,
      [COORDINATOR_DOC_NEW, ...args],
      {
        cwd: tmp,
        // TMPDIR must be the parent of the temp dir so coordinator-doc-new's
        // _safe_output_roots() accepts writes under it.
        env: { ...process.env, TMPDIR: os.tmpdir() },
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true,  // suppress console popup on Windows (CREATE_NO_WINDOW equivalent)
      },
    );

    let stdout = '';
    let stderr = '';
    child.stdout.on('data', d => { stdout += d.toString(); });
    child.stderr.on('data', d => { stderr += d.toString(); });

    child.on('error', reject);
    child.on('close', exitCode => {
      if (exitCode !== 0) {
        return reject(new Error(
          `coordinator-doc-new --type problem-set exited ${exitCode}\n` +
          `stdout: ${stdout}\nstderr: ${stderr}`,
        ));
      }
      // stdout is the written path (printed by coordinator-doc-new)
      const writtenPath = stdout.trim();
      // Resolve relative to cwd if not absolute
      const outPath = path.isAbsolute(writtenPath)
        ? writtenPath
        : path.join(tmp, writtenPath);
      try {
        const content = fs.readFileSync(outPath, 'utf8');
        resolve({ content, outPath, tmp });
      } catch (e) {
        reject(new Error(
          `coordinator-doc-new --type problem-set: output file not readable at ${outPath}\n` +
          `stdout: ${stdout}\nstderr: ${stderr}\nerr: ${e.message}`,
        ));
      }
    });
  });
}

// ---------------------------------------------------------------------------
// C3b — completion scaffold (AC6)
//
// Spec backlink: docs/plans/2026-06-29-cli-scaffold-deterministic-docs.md § C3b
//
// AC6: scaffold --type completion emits a skeleton with the nested loe: block
//      and status: pending-release, and its frontmatter validates clean against
//      the completion-entry schema (0 violations, strict mode).
// ---------------------------------------------------------------------------

/**
 * Scaffold a completion entry via coordinator-doc-new and return its content + path.
 * Uses --out pointing to archive/completed/YYYY-MM/<stem>.md inside tmp so the path
 * matches the completion-entry schema glob (archive/completed/*\/*.md) and the hook
 * can resolve it to the correct schema.
 */
function scaffoldCompletion(title, nature, chain) {
  return new Promise((resolve, reject) => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'c3b-scaffold-completion-'));
    // Create the archive/completed/YYYY-MM/ directory structure the scaffolder will write to.
    const today = new Date().toISOString().slice(0, 10);
    const month = today.slice(0, 7);
    const outDir = path.join(tmp, 'archive', 'completed', month);
    fs.mkdirSync(outDir, { recursive: true });
    const outFile = path.join(outDir, `${today}-c3b-test.md`);

    const args = ['--type', 'completion', '--out', outFile];
    if (title) args.push('--title', title);
    if (nature) args.push('--nature', nature);
    if (chain) args.push('--chain', chain);

    const child = spawn(
      PYTHON_CMD,
      [COORDINATOR_DOC_NEW, ...args],
      {
        cwd: tmp,
        env: { ...process.env, TMPDIR: os.tmpdir() },
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true,
      },
    );

    let stdout = '';
    let stderr = '';
    child.stdout.on('data', d => { stdout += d.toString(); });
    child.stderr.on('data', d => { stderr += d.toString(); });

    child.on('error', reject);
    child.on('close', exitCode => {
      if (exitCode !== 0) {
        return reject(new Error(
          `coordinator-doc-new --type completion exited ${exitCode}\n` +
          `stdout: ${stdout}\nstderr: ${stderr}`,
        ));
      }
      const writtenPath = stdout.trim();
      const resolvedPath = path.isAbsolute(writtenPath)
        ? writtenPath
        : path.join(tmp, writtenPath);
      try {
        const content = fs.readFileSync(resolvedPath, 'utf8');
        resolve({ content, outPath: resolvedPath, tmp, month });
      } catch (e) {
        reject(new Error(
          `coordinator-doc-new --type completion: output file not readable at ${resolvedPath}\n` +
          `stdout: ${stdout}\nstderr: ${stderr}\nerr: ${e.message}`,
        ));
      }
    });
  });
}

describe('C3b completion scaffold — AC6: loe block + status + 0 schema violations', () => {

  // AC6(a): scaffold emits loe: block with 4 null keys and status: pending-release
  test('AC6(a) — emits nested loe: block with 4 null keys and status: pending-release', async () => {
    const { content } = await scaffoldCompletion('Test completion', 'infra', null);

    assert.ok(
      content.includes('status: pending-release'),
      `completion must include status: pending-release; got:\n${content}`,
    );
    assert.ok(
      content.includes('loe:'),
      `completion must include loe: block; got:\n${content}`,
    );
    assert.ok(
      content.includes('  agent_dispatches: null'),
      `completion must include loe.agent_dispatches: null; got:\n${content}`,
    );
    assert.ok(
      content.includes('  opus_dispatches: null'),
      `completion must include loe.opus_dispatches: null; got:\n${content}`,
    );
    assert.ok(
      content.includes('  em_tokens: null'),
      `completion must include loe.em_tokens: null; got:\n${content}`,
    );
    assert.ok(
      content.includes('  tshirt: null'),
      `completion must include loe.tshirt: null; got:\n${content}`,
    );
    // Sanity: commits must be empty list placeholder (not filled by scaffolder)
    assert.ok(
      content.includes('commits: []'),
      `completion scaffold must emit commits: [] (empty — filled at runtime); got:\n${content}`,
    );
    // Sanity: nature must be infra (valid enum)
    assert.ok(
      content.includes('nature: infra'),
      `completion scaffold must have nature: infra; got:\n${content}`,
    );
  });

  // AC6(b): scaffolded frontmatter validates clean against completion-entry schema (0 violations)
  test('AC6(b) — scaffolded frontmatter validates clean (0 hook violations, strict mode)', async () => {
    const { content, outPath, tmp, month } = await scaffoldCompletion('Test completion AC6', 'infra', null);

    // Pre-create: existsSync must be true so the C0a scaffold offer does not fire.
    fs.writeFileSync(outPath, content);

    // The hook resolves repoRoot via `git rev-parse --show-toplevel` in cwd=tmp.
    // Since tmp is not a git repo, it falls back to cwd (tmp itself).
    // repoRel = archive/completed/<month>/2026-06-30-c3b-test.md
    // This matches the completion-entry schema glob: archive/completed/*/*.md
    const payload = {
      tool_name: 'Write',
      tool_input: { file_path: outPath, content },
      session_id: 'c3b-ac6',
      cwd: tmp,
    };

    const { stdout, exitCode } = await runHook(payload, { strict: true });

    assert.equal(exitCode, 0, 'hook must exit 0 for completion');
    assert.equal(
      stdout,
      '',
      `AC6: completion scaffolded frontmatter must produce 0 violations in strict mode;\n` +
      `got hook output: ${stdout}\nScaffolded content:\n${content}`,
    );
  });

});

// ---------------------------------------------------------------------------
// C3c — spinoff-roadmap scaffold (AC8)
//
// Spec backlink: docs/plans/2026-06-29-cli-scaffold-deterministic-docs.md § C3c
//
// AC8: scaffold --type spinoff-roadmap emits valid graph frontmatter (roadmap_id,
//      stub_id, wave, blocks, blocked_by, gate_dependency) + ## Soft seams heading
//      + trailing <!-- spinoff-roadmap: ... --> marker, with pickup_ready ABSENT and
//      0 CROSS_FIELD_RULES violations against the handoff schema.
// ---------------------------------------------------------------------------

/**
 * Scaffold a spinoff-roadmap stub via coordinator-doc-new and return its content + path.
 * Uses --out pointing to state/handoffs/ inside tmp so the path matches the handoff
 * schema glob (state/handoffs/*.md) and the hook can resolve it to the correct schema.
 */
function scaffoldSpinoffRoadmap(title, roadmapId, stubId, outFile) {
  return new Promise((resolve, reject) => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'c3c-scaffold-spinoff-roadmap-'));
    fs.mkdirSync(path.join(tmp, 'state', 'handoffs'), { recursive: true });

    const resolvedOut = outFile || path.join(tmp, 'state', 'handoffs',
      `${new Date().toISOString().slice(0, 10)}_000000_roadmap-${stubId || 'placeholder-stub-1'}.md`);

    const args = ['--type', 'spinoff-roadmap', '--out', resolvedOut];
    if (title) args.push('--title', title);
    if (roadmapId) args.push('--roadmap-id', roadmapId);
    if (stubId) args.push('--stub-id', stubId);

    const child = spawn(
      PYTHON_CMD,
      [COORDINATOR_DOC_NEW, ...args],
      {
        cwd: tmp,
        // TMPDIR must be the parent of the temp dir so coordinator-doc-new's
        // _safe_output_roots() accepts writes under it.
        env: { ...process.env, TMPDIR: os.tmpdir() },
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true,  // suppress console popup on Windows (CREATE_NO_WINDOW equivalent)
      },
    );

    let stdout = '';
    let stderr = '';
    child.stdout.on('data', d => { stdout += d.toString(); });
    child.stderr.on('data', d => { stderr += d.toString(); });

    child.on('error', reject);
    child.on('close', exitCode => {
      if (exitCode !== 0) {
        return reject(new Error(
          `coordinator-doc-new --type spinoff-roadmap exited ${exitCode}\n` +
          `stdout: ${stdout}\nstderr: ${stderr}`,
        ));
      }
      const writtenPath = stdout.trim();
      const resolvedPath = path.isAbsolute(writtenPath)
        ? writtenPath
        : path.join(tmp, writtenPath);
      try {
        const content = fs.readFileSync(resolvedPath, 'utf8');
        resolve({ content, outPath: resolvedPath, tmp });
      } catch (e) {
        reject(new Error(
          `coordinator-doc-new --type spinoff-roadmap: output file not readable at ${resolvedPath}\n` +
          `stdout: ${stdout}\nstderr: ${stderr}\nerr: ${e.message}`,
        ));
      }
    });
  });
}

describe('C3c spinoff-roadmap scaffold — AC8: graph frontmatter + Soft seams + 0 schema violations', () => {

  // AC8(a): scaffold emits all required graph fields + ## Soft seams + trailing marker;
  // pickup_ready is ABSENT (per SKILL § Phase 2.1 "defaults to absent for roadmap stubs").
  test('AC8(a) — emits graph frontmatter fields, ## Soft seams heading, trailing marker; pickup_ready absent', async () => {
    const { content } = await scaffoldSpinoffRoadmap(
      'Test stub', 'test-rm', 'test-1',
    );

    // Required graph fields
    assert.ok(
      content.includes('roadmap_id:'),
      `spinoff-roadmap must include roadmap_id:; got:\n${content}`,
    );
    assert.ok(
      content.includes('stub_id:'),
      `spinoff-roadmap must include stub_id:; got:\n${content}`,
    );
    assert.ok(
      content.includes('wave:'),
      `spinoff-roadmap must include wave:; got:\n${content}`,
    );
    assert.ok(
      content.includes('blocks:'),
      `spinoff-roadmap must include blocks:; got:\n${content}`,
    );
    assert.ok(
      content.includes('blocked_by:'),
      `spinoff-roadmap must include blocked_by:; got:\n${content}`,
    );
    // gate_dependency (required when deployment_state=awaiting_gate)
    assert.ok(
      content.includes('gate_dependency:'),
      `spinoff-roadmap must include gate_dependency:; got:\n${content}`,
    );
    // ## Soft seams must be present (SKILL § Step 2.2)
    assert.ok(
      content.includes('## Soft seams'),
      `spinoff-roadmap must include ## Soft seams section; got:\n${content}`,
    );
    // Trailing marker must be present
    assert.ok(
      content.includes('<!-- spinoff-roadmap:'),
      `spinoff-roadmap must include trailing <!-- spinoff-roadmap: ... --> marker; got:\n${content}`,
    );
    assert.ok(
      content.includes('test-rm') && content.includes('test-1'),
      `trailing marker must include roadmap_id and stub_id; got:\n${content}`,
    );
    // pickup_ready MUST be absent (SKILL § Phase 2.1: "defaults to absent for roadmap stubs")
    assert.ok(
      !content.includes('pickup_ready:'),
      `spinoff-roadmap must NOT include pickup_ready: (absent by design); got:\n${content}`,
    );
    // kind must be spinoff-roadmap
    assert.ok(
      content.includes('kind: spinoff-roadmap'),
      `spinoff-roadmap must include kind: spinoff-roadmap; got:\n${content}`,
    );
    // category: roadmap required post-cutoff (cross-field rule)
    assert.ok(
      content.includes('category: roadmap'),
      `spinoff-roadmap must include category: roadmap; got:\n${content}`,
    );
  });

  // AC8(b): scaffolded frontmatter validates clean against handoff schema CROSS_FIELD_RULES
  // (0 violations) — validates roadmap_id/stub_id/wave/blocks/blocked_by requirements,
  // gate_dependency coupling, category/summary post-cutoff requirements.
  test('AC8(b) — scaffolded frontmatter validates clean (0 hook violations, strict mode)', async () => {
    const { content, outPath, tmp } = await scaffoldSpinoffRoadmap(
      'Test stub AC8', 'test-rm', 'test-1',
    );

    // Pre-create: existsSync must be true so the C0a scaffold offer does not fire.
    // coordinator-doc-new already wrote the file; this ensures the hook sees it as existing.
    fs.writeFileSync(outPath, content);

    // The hook resolves repoRoot via `git rev-parse --show-toplevel` in cwd=tmp.
    // Since tmp is not a git repo, it falls back to cwd (tmp itself).
    // repoRel = state/handoffs/<date>_000000_roadmap-test-1.md
    // This matches the handoff schema glob: state/handoffs/*.md
    const payload = {
      tool_name: 'Write',
      tool_input: { file_path: outPath, content },
      session_id: 'c3c-ac8',
      cwd: tmp,
    };

    const { stdout, exitCode } = await runHook(payload, { strict: true });

    assert.equal(exitCode, 0, 'hook must exit 0 for spinoff-roadmap');
    assert.equal(
      stdout,
      '',
      `AC8: spinoff-roadmap scaffolded frontmatter must produce 0 violations in strict mode;\n` +
      `got hook output: ${stdout}\nScaffolded content:\n${content}`,
    );
  });

  // AC8(c): NEGATIVE — mutated spinoff-roadmap frontmatter with a CROSS_FIELD_RULES violation
  // (gate_dependency cleared while deployment_state=awaiting_gate) MUST emit a violation.
  // Review: code-reviewer — F2: codifies the EM-manual-only negative check as an automated test.
  // Uses the same hook strict-mode path as AC8(b) so the validator path is identical.
  test('AC8(c) — NEGATIVE: empty gate_dependency with awaiting_gate emits CROSS_FIELD_RULES violation', async () => {
    const { content, outPath, tmp } = await scaffoldSpinoffRoadmap(
      'Test stub AC8c', 'test-rm', 'test-neg',
    );

    // Mutate: blank out gate_dependency value while deployment_state remains awaiting_gate.
    // This violates the CROSS_FIELD_RULES deployment_state_coupling rule:
    //   deployment_state=awaiting_gate requires a non-empty gate_dependency.
    const mutated = content.replace(/^(gate_dependency):.*$/m, '$1:');
    // Sanity: mutation must have taken effect and awaiting_gate must still be present.
    // review F7 — replaced !includes('gate_dependency: P') with a regex that asserts
    // no non-whitespace value follows the colon. The former check implicitly coupled
    // to the scaffolder's default starting with 'P'; if the default changed to start
    // with any other character, the sanity check would pass trivially without confirming
    // the blank. !/^gate_dependency:\s+\S/m is robust to any default value format.
    // review F7 — use [ \t]* (horizontal whitespace only) not \s+ to avoid crossing line
    // boundaries. In JS, \s matches \n, so /^gate_dependency:\s+\S/m would match across
    // the newline to the first char of the next line, always returning true regardless of
    // whether gate_dependency has a value. [ \t]* restricts to the same line.
    assert.ok(
      mutated.includes('gate_dependency:') && !/^gate_dependency:[ \t]*\S/m.test(mutated),
      `precondition: gate_dependency must be blanked; got mutated:\n${mutated}`,
    );
    assert.ok(
      mutated.includes('deployment_state: awaiting_gate'),
      `precondition: awaiting_gate must still be present; got mutated:\n${mutated}`,
    );

    fs.writeFileSync(outPath, mutated);

    const payload = {
      tool_name: 'Write',
      tool_input: { file_path: outPath, content: mutated },
      session_id: 'c3c-ac8c',
      cwd: tmp,
    };

    const { stdout, exitCode } = await runHook(payload, { strict: true });

    assert.equal(exitCode, 0, 'hook must exit 0 (violations surface via output, not exit code)');
    assert.ok(
      stdout.length > 0,
      `AC8(c): CROSS_FIELD_RULES violation must be emitted for empty gate_dependency; got empty stdout. Mutated:\n${mutated}`,
    );
    // Confirm the emitted output references gate_dependency (not just any hook output).
    const outputStr = stdout;
    assert.ok(
      outputStr.includes('gate_dependency'),
      `AC8(c): violation output must reference gate_dependency; got: ${outputStr}`,
    );
  });

});

// ---------------------------------------------------------------------------
// C3d — health-status scaffold (AC7)
//
// Spec backlink: docs/plans/2026-06-29-cli-scaffold-deterministic-docs.md § C3d
//
// AC7: scaffold --type health-status emits BOTH required axes (status: LIFECYCLE,
//      health: POSTURE) with valid enum values, and its frontmatter validates clean
//      against the health-status schema (0 violations, strict mode).
// ---------------------------------------------------------------------------

/**
 * Scaffold a health-status record via coordinator-doc-new and return its content + path.
 * Uses --out pointing to state/health/ inside tmp so the path matches the health-status
 * schema glob (state/health/*.md) and the hook can resolve it to the correct schema.
 */
function scaffoldHealthStatus(title) {
  return new Promise((resolve, reject) => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'c3d-scaffold-health-status-'));
    fs.mkdirSync(path.join(tmp, 'state', 'health'), { recursive: true });

    const today = new Date().toISOString().slice(0, 10);
    const outFile = path.join(tmp, 'state', 'health', `${today}-health-summary.md`);

    const args = ['--type', 'health-status', '--out', outFile];
    if (title) args.push('--title', title);

    const child = spawn(
      PYTHON_CMD,
      [COORDINATOR_DOC_NEW, ...args],
      {
        cwd: tmp,
        // TMPDIR must be the parent of the temp dir so coordinator-doc-new's
        // _safe_output_roots() accepts writes under it.
        env: { ...process.env, TMPDIR: os.tmpdir() },
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true,  // suppress console popup on Windows (CREATE_NO_WINDOW equivalent)
      },
    );

    let stdout = '';
    let stderr = '';
    child.stdout.on('data', d => { stdout += d.toString(); });
    child.stderr.on('data', d => { stderr += d.toString(); });

    child.on('error', reject);
    child.on('close', exitCode => {
      if (exitCode !== 0) {
        return reject(new Error(
          `coordinator-doc-new --type health-status exited ${exitCode}\n` +
          `stdout: ${stdout}\nstderr: ${stderr}`,
        ));
      }
      const writtenPath = stdout.trim();
      const resolvedPath = path.isAbsolute(writtenPath)
        ? writtenPath
        : path.join(tmp, writtenPath);
      try {
        const content = fs.readFileSync(resolvedPath, 'utf8');
        resolve({ content, outPath: resolvedPath, tmp });
      } catch (e) {
        reject(new Error(
          `coordinator-doc-new --type health-status: output file not readable at ${resolvedPath}\n` +
          `stdout: ${stdout}\nstderr: ${stderr}\nerr: ${e.message}`,
        ));
      }
    });
  });
}

describe('C3d health-status scaffold — AC7: both axes present + 0 schema violations', () => {

  // AC7(a): scaffold emits both required axes with valid enum values;
  // status (LIFECYCLE axis) = active; health (POSTURE axis) = one of 4 posture values.
  test('AC7(a) — emits status: active (LIFECYCLE) and health: one-of-4-posture (POSTURE) with schema: lead key', async () => {
    const { content } = await scaffoldHealthStatus('Test health C3d');

    // Two-axis trap: status is LIFECYCLE, health is POSTURE — must NOT be conflated.
    assert.ok(
      content.includes('status: active'),
      `health-status must emit status: active (LIFECYCLE axis); got:\n${content}`,
    );

    // health: must be one of the 4 valid posture values
    const POSTURE_VALUES = ['HEALTHY', 'WATCH', 'ACTION', 'CRITICAL'];
    const hasValidPosture = POSTURE_VALUES.some(v => content.includes(`health: ${v}`));
    assert.ok(
      hasValidPosture,
      `health-status must emit health: one of ${POSTURE_VALUES.join('|')}; got:\n${content}`,
    );

    // leading schema: health-status key (mirrors existing conformant record)
    assert.ok(
      content.includes('schema: health-status'),
      `health-status must include leading schema: health-status key; got:\n${content}`,
    );

    // required fields: title and created
    assert.ok(
      content.includes('title:'),
      `health-status must include title: field; got:\n${content}`,
    );
    assert.ok(
      content.includes('created:'),
      `health-status must include created: field; got:\n${content}`,
    );
  });

  // AC7(b): scaffolded frontmatter validates clean against health-status schema (0 violations)
  test('AC7(b) — scaffolded frontmatter validates clean (0 hook violations, strict mode)', async () => {
    const { content, outPath, tmp } = await scaffoldHealthStatus('Test health AC7');

    // Pre-create: existsSync must be true so the C0a scaffold offer does not fire.
    // coordinator-doc-new already wrote the file; this ensures the hook sees it as existing.
    fs.writeFileSync(outPath, content);

    // The hook resolves repoRoot via `git rev-parse --show-toplevel` in cwd=tmp.
    // Since tmp is not a git repo, it falls back to cwd (tmp itself).
    // repoRel = state/health/<date>-health-summary.md
    // This matches the health-status schema glob: state/health/*.md
    const payload = {
      tool_name: 'Write',
      tool_input: { file_path: outPath, content },
      session_id: 'c3d-ac7',
      cwd: tmp,
    };

    const { stdout, exitCode } = await runHook(payload, { strict: true });

    assert.equal(exitCode, 0, 'hook must exit 0 for health-status');
    assert.equal(
      stdout,
      '',
      `AC7: health-status scaffolded frontmatter must produce 0 violations in strict mode;\n` +
      `got hook output: ${stdout}\nScaffolded content:\n${content}`,
    );
  });

});

describe('C3a problem-set scaffold — AC6: canonical headings + 0 schema violations', () => {

  // AC6(a): scaffold emits ## Problems and ## Out of scope (architectural reasons) headings
  test('AC6(a) — emits ## Problems and ## Out of scope (architectural reasons) headings', async () => {
    const { content } = await scaffoldProblemSet('Test problem set C3a');

    assert.ok(
      content.includes('## Problems'),
      `problem-set must include ## Problems heading; got:\n${content}`,
    );
    assert.ok(
      content.includes('## Out of scope (architectural reasons)'),
      `problem-set must include ## Out of scope (architectural reasons) heading; got:\n${content}`,
    );
    // Sanity: scaffolded status must be draft, not ratified
    assert.ok(
      content.includes('status: draft'),
      `problem-set scaffold must have status: draft (not ratified); got:\n${content}`,
    );
    // Sanity: kind must be present for kind-first schema matching
    assert.ok(
      content.includes('kind: problem-set'),
      `problem-set scaffold must include kind: problem-set; got:\n${content}`,
    );
  });

  // AC6(b): scaffolded frontmatter validates clean against problem-set schema (0 violations)
  test('AC6(b) — scaffolded frontmatter validates clean (0 hook violations, strict mode)', async () => {
    const { content, outPath, tmp } = await scaffoldProblemSet('Test problem set C3a AC6');

    // Pre-create: existsSync must be true so the C0a scaffold offer does not fire.
    // The file was already written by coordinator-doc-new; this write keeps disk state
    // consistent with the hook payload.
    fs.writeFileSync(outPath, content);

    const payload = {
      tool_name: 'Write',
      tool_input: { file_path: outPath, content },
      session_id: 'c3a-ac6',
      cwd: tmp,
    };

    const { stdout, exitCode } = await runHook(payload, { strict: true });

    assert.equal(exitCode, 0, 'hook must exit 0 for problem-set');
    assert.equal(
      stdout,
      '',
      `AC6: problem-set scaffolded frontmatter must produce 0 violations in strict mode;\n` +
      `got hook output: ${stdout}\nScaffolded content:\n${content}`,
    );
  });

});
