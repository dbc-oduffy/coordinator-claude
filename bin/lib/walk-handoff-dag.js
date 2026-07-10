'use strict';
/**
 * walk-handoff-dag.js — edge-kind-aware handoff DAG traversal primitive.
 *
 * Purpose: shared kernel for forward accumulation (LoE aggregation) and reverse-membership
 * testing (archival has-live-children guard). Centralises the edge-kind SSOT so no consumer
 * re-derives which frontmatter fields are edges.
 *
 * Cycle-vs-convergence semantics (contrast with roadmap-graph.js):
 *   roadmap-graph.js throws RoadmapCycleError on ANY revisit — DAGs are strict there.
 *   walk-handoff-dag.js uses DFS gray/black coloring:
 *     - gray-set re-encounter → genuine back-edge (authoring error) → terminatedEarly='lineage-cycle'
 *     - black-set re-encounter → benign diamond convergence → skip (continue), NOT abort.
 *   This preserves diamond summation (the Director of Engineering F1) AND surfaces true authoring cycles (the Director of Engineering F6).
 *
 * Spec backlink: docs/plans/2026-06-29-handoff-lineage-dag-fan-in-fan-out.md § Primitive interface
 *
 * Exports:
 *   handoffEdges(nodeMeta, edgeKinds) → string[]
 *     Edge-kind SSOT kernel. Returns resolved edge-target strings for the named fields.
 *   walkForward(startPath, {edgeKinds, nodeGate, handoffDir}) → {nodes, orderedPaths, terminatedEarly}
 *     Forward BFS/DFS accumulation with gray/black cycle detection and path-level diamond dedup.
 *   referencedBy(target, liveSet, {edgeKinds, handoffDir, exclude}) → {referenced, referencedBy}
 *     DIRECT non-transitive reverse-membership test. opts.exclude (array|Set) drops matching
 *     liveSet paths before the scan; absent → byte-identical to prior behaviour.
 *   _resolveTarget(ref, handoffDir, repoRoot) → string|null
 *     Promoted (C2, F1) so consumers reuse resolution instead of duplicating it — notably the
 *     write-time lineage-reachability hard-reject in validate-frontmatter-schema.js and the C6
 *     backfill sweep (validate-handoff.js). Three-tier resolution: live ∪ archive-on-disk ∪
 *     git-history. Returns an absolute disk path (tier 1/2), the sentinel string 'git-history'
 *     (tier 3 — disk-absent, git-known; no disk path to return), or null (unresolvable in all
 *     three tiers — the only condition C2's reject may act on).
 *     Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C2
 *
 * Negative-spec:
 *   - Does NOT implement topological sort, shortest-path, or betweenness — roadmap-graph.js owns topo.
 *   - Does NOT throw on cycle — uses terminatedEarly='lineage-cycle' instead.
 *   - Does NOT abort on missing-link — skips the unresolvable edge, continues, sets terminatedEarly.
 *   - Does NOT auto-infer adjacency as ancestry — only explicit frontmatter edge fields are followed.
 *
 * No external dependencies — uses only Node built-ins. CommonJS module.exports shape (same as schema.js).
 */

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const { parseFrontmatter } = require('./schema.js');

// ---------------------------------------------------------------------------
// Edge-kind field map — the SSOT for which frontmatter keys are DAG edges.
// Consumers supply a Set<edgeKind> to select which subset to follow.
// ---------------------------------------------------------------------------

/**
 * Map from edge-kind name → the frontmatter field that carries it.
 * 'additional_predecessors' is an array field; all others are scalar.
 * @type {Object.<string, {field: string, multi: boolean}>}
 */
var EDGE_KIND_META = {
  predecessor:             { field: 'predecessor',             multi: false },
  additional_predecessors: { field: 'additional_predecessors', multi: true  },
  forked_from:             { field: 'forked_from',             multi: false  },
  // Provenance edge-kind — isolated from continuity/coverage walks.
  // NEVER included in the default edgeKinds set; walkable only via an explicit
  // edgeKinds subset param. origin_session / origin_plan_id / origin_goal_id
  // are cross-entity refs (not handoff paths) and are NOT registered here.
  //
  // Distinct from forked_from (above): forked_from is spinoff-ONLY (schema.js
  // kind-gate), PM-directed, and IS followed by the archival has-live-children
  // guard (referencedBy default set); origin_handoff applies to all fork kinds,
  // is auto-captured, and is followed by NEITHER the LoE walk NOR the archival
  // guard. When both are set on one record they must be equal (schema.js Rule
  // C2-5). They are orthogonal axes that frequently coincide, not aliases.
  origin_handoff:          { field: 'origin_handoff',          multi: false },
};

// ---------------------------------------------------------------------------
// Utility: parse frontmatter from a file path. Returns {} on any error.
// ---------------------------------------------------------------------------

function _readMeta(filePath) {
  try {
    var content = fs.readFileSync(filePath, 'utf8');
    var parsed = parseFrontmatter(content);
    return parsed.frontmatter || {};
  } catch (_) {
    return {};
  }
}

// ---------------------------------------------------------------------------
// Utility: git-history-aware existence checks (tier 3 of _resolveTarget).
//
// Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C2 (F1)
//
// A target that is disk-absent (relocated, e.g. flat archive → month-foldered
// archive) but git-reachable is NOT "never existed" — cockpit spot-checked 17
// live handoffs and found 3 exactly this shape. Both helpers are best-effort:
// any git failure (not a repo, git missing, timeout) resolves to "not found"
// rather than throwing — a resolver used inside a write-time hard-reject must
// never itself crash the hook (the hook's own infra-failure invariant, see
// validate-frontmatter-schema.js header). A git-history miss here simply falls
// through to the caller's existing "unresolvable" outcome, unchanged from
// pre-F1 behaviour.
// ---------------------------------------------------------------------------

/**
 * True if `sha` is `git cat-file -e`-reachable in repoRoot's object database
 * (any ref, any point in history — reachable objects, not just current HEAD).
 * Best-effort: any git failure (not a repo, unknown sha, timeout) → false.
 */
function _gitObjectExists(sha, repoRoot) {
  if (!sha) return false;
  try {
    execFileSync('git', ['cat-file', '-e', sha], {
      cwd: repoRoot,
      stdio: ['ignore', 'ignore', 'ignore'],
      timeout: 3000,
    });
    return true;
  } catch (_e) {
    return false;
  }
}

/**
 * True if `repoRelPath` was ever a git-tracked path at any point in this
 * repo's full history (`git log --all -- <path>` has at least one entry) —
 * covers a path relocated or deleted between commits, disk-absent now but
 * git-known. Best-effort: any git failure → false.
 */
function _gitPathEverTracked(repoRelPath, repoRoot) {
  if (!repoRelPath) return false;
  try {
    var out = execFileSync('git', ['log', '--all', '--max-count=1', '--format=%H', '--', repoRelPath], {
      cwd: repoRoot,
      stdio: ['ignore', 'pipe', 'ignore'],
      timeout: 3000,
      encoding: 'utf8',
    });
    return out.trim().length > 0;
  } catch (_e) {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Batch-sweep git-history memoization (C6 GAP1 perf, code-reviewer F5).
//
// _resolveTarget's tier-3 fallback spawns up to two `git log --all` subprocesses
// per unresolved field per record — over a large corpus (records × up-to-4-fields
// × up-to-2-subprocesses) this multiplies into hundreds-to-thousands of full
// history-walk subprocess spawns for a nightly sweep. buildGitHistoryCache
// primes a SINGLE `git log --all --name-only --diff-filter=A` pass once per
// validateAllRecords invocation, building an in-memory Set of every
// repo-relative path ever added anywhere in history. Threaded into
// _resolveTarget/checkLineageReachability as an OPTIONAL 4th/5th param —
// absent (undefined/null), both fall back to the original per-call
// execFileSync path unchanged, so the write-time single-record hook path
// (which never primes a cache — one write, one lookup, priming would be pure
// overhead) keeps its current behaviour byte-for-byte.
//
// Cache correctness note: `--diff-filter=A` only catches ADD events. A path
// that was renamed INTO its final name (never freshly `git add`ed under that
// exact name) would be missed by the cache but still found by the per-call
// `git log --all -- <path>` fallback (which matches on any history touching
// that path, not just adds) — so a cache miss here is deliberately treated as
// "unknown, fall through" rather than "definitely absent"; see
// _resolveTargetCached below. The cache is a fast-path accept, never a
// fast-path reject.
//
// Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C2 (F5)
// ---------------------------------------------------------------------------

/**
 * Prime a Set of every repo-relative path ever `git add`ed anywhere in this
 * repo's history, via a single `git log --all --name-only --diff-filter=A`
 * pass. Best-effort: any git failure (not a repo, git missing, timeout on a
 * very large history) returns null — callers must treat a null cache
 * identically to an absent one (fall back to per-call resolution).
 *
 * @param {string} repoRoot  Absolute repo root.
 * @param {number} [timeoutMs]  Subprocess timeout (default 15000 — a single
 *   full-history prime pass costs more than one `git log --all --max-count=1`
 *   call, but amortizes across the whole sweep).
 * @returns {Set<string>|null}
 */
function buildGitHistoryCache(repoRoot, timeoutMs) {
  if (!repoRoot) return null;
  try {
    var out = execFileSync(
      'git',
      ['log', '--all', '--name-only', '--diff-filter=A', '--pretty=format:'],
      {
        cwd: repoRoot,
        stdio: ['ignore', 'pipe', 'ignore'],
        timeout: timeoutMs || 15000,
        encoding: 'utf8',
        maxBuffer: 64 * 1024 * 1024, // 64MB — a large corpus's full added-path history
      }
    );
    var set = new Set();
    out.split('\n').forEach(function(line) {
      var trimmed = line.trim();
      if (trimmed) set.add(trimmed);
    });
    return set;
  } catch (_e) {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Utility: resolve a handoff path reference to an absolute path.
//
// Resolution tiers (git-history-aware, per cockpit F1):
//   1. live — handoffDir (typically state/handoffs/)
//   2. archive-on-disk — archive/handoffs/ (flat or month-foldered)
//   3. git-history — the path was ever git-tracked anywhere in history, even
//      though it is absent from both tiers above right now (relocated/deleted)
//
// Returns the resolved absolute path for tiers 1-2 (disk-present), or the
// literal string 'git-history' as a sentinel for a tier-3-only resolution
// (there is no disk path to return — the caller only needs to know the
// target is NOT "never existed"). Returns null only when unresolvable in
// ALL THREE tiers — the sole condition under which C2's write-time hard-reject
// may fire.
//
// @param {Set<string>} [gitHistoryCache]  Optional, code-reviewer F5 perf.
//   A pre-built cache from buildGitHistoryCache() — when present, tier 3
//   checks the cache first (Set.has, O(1)) before falling back to a per-call
//   `git log --all` subprocess spawn. Absent/null → per-call resolution,
//   unchanged from pre-F5 behaviour (the write-time single-record hook path
//   never passes this — priming would be pure overhead for one lookup). A
//   cache MISS is never treated as definitive absence (see buildGitHistoryCache
//   header — --diff-filter=A only catches adds, not pure renames) — it always
//   falls through to the per-call `_gitPathEverTracked` check, so the cache is
//   a fast-path ACCEPT only, never a fast-path REJECT.
// ---------------------------------------------------------------------------

function _resolveTarget(ref, handoffDir, repoRoot, gitHistoryCache) {
  if (!ref || ref === 'none' || ref === 'null' || ref === null) return null;
  var target = String(ref).trim();
  if (!target || target === 'none' || target === 'null') return null;

  function everTracked(repoRelPath) {
    if (gitHistoryCache && gitHistoryCache.has(repoRelPath)) return true;
    return _gitPathEverTracked(repoRelPath, repoRoot);
  }

  // Already absolute and exists?
  if (path.isAbsolute(target)) {
    if (fs.existsSync(target)) return target;
    // Tier 3 for an absolute path: derive repo-relative form if possible.
    if (repoRoot) {
      var normRoot = repoRoot.replace(/[/\\]+$/, '');
      if (target.indexOf(normRoot) === 0) {
        var rel = target.slice(normRoot.length).replace(/^[/\\]/, '');
        if (everTracked(rel)) return 'git-history';
      }
    }
    return null;
  }

  // Bare filename or relative path — try under handoffDir first
  var candidates = [
    path.resolve(handoffDir, target),
  ];

  // Archive fallback: replace state/handoffs with archive/handoffs (may be month-foldered)
  // and also try archive/handoffs/YYYY-MM/<basename>
  var basename = path.basename(target);
  candidates.push(path.resolve(repoRoot, 'archive', 'handoffs', target));
  candidates.push(path.resolve(repoRoot, 'archive', 'handoffs', basename));

  for (var i = 0; i < candidates.length; i++) {
    if (fs.existsSync(candidates[i])) return candidates[i];
  }

  // Try month-foldered archive (archive/handoffs/YYYY-MM/<basename>)
  var archiveDir = path.resolve(repoRoot, 'archive', 'handoffs');
  if (fs.existsSync(archiveDir)) {
    try {
      var months = fs.readdirSync(archiveDir).filter(function(d) {
        return /^\d{4}-\d{2}$/.test(d);
      });
      for (var m = 0; m < months.length; m++) {
        var candidate = path.join(archiveDir, months[m], basename);
        if (fs.existsSync(candidate)) return candidate;
      }
    } catch (_e) { /* archive dir unreadable — treat as empty, continue */ }
    // Review: code-reviewer (F11) — named catch var + comment documents intent; silent swallow is intentional.
  }

  // Tier 3 — git-history. Try the ref as given (relative to repoRoot, the
  // conventional form for predecessor/forked_from/origin_handoff/
  // additional_predecessors values) and, if that path form itself looks like
  // it might be handoffDir-relative rather than repoRoot-relative, also try
  // resolving it against handoffDir's repo-relative form.
  if (repoRoot) {
    if (everTracked(target)) return 'git-history';
    // Also try the handoffDir-resolved absolute path re-derived as repo-relative,
    // in case `target` was a bare filename (handoffDir-relative) rather than a
    // repoRoot-relative path — covers the same shape candidates[] above tried
    // on-disk, now against git history.
    var normRootForRel = repoRoot.replace(/[/\\]+$/, '');
    for (var c = 0; c < candidates.length; c++) {
      var candAbs = candidates[c];
      if (candAbs.indexOf(normRootForRel) === 0) {
        var candRel = candAbs.slice(normRootForRel.length).replace(/^[/\\]/, '');
        if (everTracked(candRel)) return 'git-history';
      }
    }
  }

  return null;
}

// ---------------------------------------------------------------------------
// Utility: infer repoRoot from a handoffDir
// ---------------------------------------------------------------------------

function _repoRootFromHandoffDir(handoffDir) {
  // handoffDir is typically <repoRoot>/state/handoffs or <repoRoot>/archive/handoffs
  return path.resolve(handoffDir, '..', '..');
}

// ---------------------------------------------------------------------------
// Waived pre-reclaim-boundary dangling predecessors (C6 GAP2, 2026-07-08).
//
// All five entries below were introduced to this repo by a SINGLE commit,
// `50e2847 reclaim(archive): DoE pre-July archive history from example-orchestration-hub`, which
// squash-reclaimed inert pre-July archive records that had been stranded in
// example-orchestration-hub by the 2026-07-03 relocation. That reclaim brought in each
// SUCCESSOR handoff (the record listed as a key below) but NOT its own
// predecessor, which lived and died entirely inside example-orchestration-hub's original
// (pre-split) repo history — never independently reclaimed because it was
// already consumed/superseded before the reclaim boundary. This is
// mechanically distinct from cockpit's archive-relocation-stranded class
// (F1/F3): those targets are git-history-tier resolvable WITHIN this repo;
// these are provably absent from this repo's entire history because they
// were never part of it — verified via `git log --all --diff-filter=A
// --name-only | grep <basename>` returning zero hits for each target below
// (independently re-verified at C6 GAP2, not merely trusted from the prior
// executor's count).
//
// One sibling dangling-predecessor case in the same reclaim batch WAS
// repairable (a plugin-source-relocation path rewrite, not a repo-history
// boundary loss) and was fixed in-place rather than waived — see
// archive/handoffs/2026-06/2026-06-30_134544_e8824721.md predecessor.
//
// Waiver shape: keyed by the RECORD's own repo-relative path (not the
// unresolvable target — a record can carry at most one waived edge in this
// narrow class), so a future edit to a waived record that introduces a NEW
// unrelated dangling edge is NOT silently covered by this list.
//
// Mirrors validate-handoff.js's existing "False-red design contract
// (negative-spec)" doctrine — known-legitimate corpus variants are
// documented explicitly in code, not silently absorbed.
//
// Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C6 (GAP2)
// ---------------------------------------------------------------------------
var WAIVED_DANGLING_PREDECESSORS = {
  'archive/handoffs/2026-06-28_081122_d5714a02-8a54-4897-babf-457e5833ed9c.md':
    'state/handoffs/2026-06-27_224629_roadmap-stub-numbering-dependency-order.md',
  'archive/handoffs/2026-06-28_081627_52b35ed9-0b63-47fa-a501-a93734abff15.md':
    'state/handoffs/2026-06-27_223611_pickup-liveness-canonical-not-raw-pid.md',
  'archive/handoffs/2026-06-30_040412_e92b195b-799d-4e54-8baf-75882a82e659.md':
    'state/handoffs/2026-06-28_080820_eff4f4ab-5277-4e3c-8362-e0c229a2b9dc.md',
  'archive/handoffs/2026-06/2026-06-30_114057_80de4efd-6159-4812-a16f-7c8dc8578c9e.md':
    '2026-06-30_033536_b7d4f348.md',
  'archive/handoffs/2026-06/2026-06-30_185537_d92000f8.md':
    'state/handoffs/2026-06-27_095007_roadmap-ccos-7.md',
};

// ---------------------------------------------------------------------------
// Exported: checkLineageReachability — shared reachability rule kernel
//
// Promoted (C6 GAP1 backfill, 2026-07-08) so the write-time PreToolUse hook
// (validate-frontmatter-schema.js) and the batch corpus sweep
// (query-records.js validateAllRecords, consumed by validate-handoff.js) apply
// the IDENTICAL reachability rule — not just the same _resolveTarget, but the
// same per-field rule set (which fields are checked, the kind:recovery
// same-repo-only carve-out, the "resolved is git-history sentinel → OK" logic).
// Before this promotion, the rule itself (not just resolution) was duplicated
// only in the hook — the batch sweep never checked reachability at all (GAP1).
//
// Checks predecessor / forked_from / additional_predecessors[] / origin_handoff
// (F4 — origin_handoff is a real state/handoffs/ path edge, walked the same way
// as the other three) via _resolveTarget (live ∪ archive-on-disk ∪ git-history,
// C2 F1). A target unresolvable in all three tiers is a hard violation —
// provably never-existed, not merely relocated.
//
// kind:recovery predecessor is a SHA, not a handoff path — SUBJECT TO THE
// SAME-REPO-ONLY FOREIGN-BATON CARVE-OUT (the Staff Engineer F9, example-orchestration-hub F2): there is no
// per-record repo-identity discriminator, so an unreachable recovery SHA is
// NEVER rejected here — it may be a legitimate sibling-repo crash SHA per the
// deliberately-deferred foreign-baton boundary. This function does NOT check
// kind:recovery predecessor at all; the field is simply skipped.
//
// Negative-spec: does NOT walk transitively — each of the four fields is
// checked as a single direct edge, not a chain (unlike walkForward's
// accumulation). Reachability is a per-field existence predicate here, not a
// graph traversal.
//
// Returns [] when frontmatter is null/absent, or when the fields are all
// absent/none/null — the common case, silent. Returns an array of
// {field, value, reason} violation objects otherwise.
//
// Fail-open on any resolver error: an individual field's resolution throwing
// is treated as "cannot prove unresolvable" (not a violation) — never crash
// or spuriously deny/reject on an infra hiccup.
//
// @param {Object|null} frontmatter  Parsed frontmatter for the handoff record.
// @param {string} repoRoot          Absolute repo root.
// @param {string} [handoffDir]      Absolute dir the record's own relative
//   path fields resolve against (defaults to <repoRoot>/state/handoffs — the
//   write-time hook's convention). The batch sweep passes the record's own
//   directory (state/handoffs/ OR archive/handoffs/<...>) since a backfilled
//   archived record's relative predecessor is conventionally repoRoot-relative
//   already, matching write-time semantics.
// @param {string} [recordRepoRelPath]  The record's OWN repo-relative path
//   (forward-slash form), used ONLY to key WAIVED_DANGLING_PREDECESSORS
//   (C6 GAP2). Absent at write-time (a not-yet-written record can never be
//   in the waive-list); the batch sweep passes it.
// @param {Set<string>} [gitHistoryCache]  Optional, code-reviewer F5 perf.
//   Threaded straight through to _resolveTarget's tier-3 check. Absent →
//   per-call `git log --all` resolution, unchanged from pre-F5 behaviour (the
//   write-time hook never passes this). The batch sweep primes one via
//   buildGitHistoryCache() once per validateAllRecords invocation and passes
//   it to every record's checkLineageReachability call.
// @returns {Array<{field: string, value: string, reason: string}>}
//
// Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C2, § C6 (GAP1/GAP2), F5
// ---------------------------------------------------------------------------
function checkLineageReachability(frontmatter, repoRoot, handoffDir, recordRepoRelPath, gitHistoryCache) {
  if (!frontmatter) return [];
  const dir = handoffDir || path.join(repoRoot, 'state', 'handoffs');
  const waivedTarget = recordRepoRelPath ? WAIVED_DANGLING_PREDECESSORS[recordRepoRelPath] : undefined;
  const violations = [];

  function checkField(field, rawValue) {
    if (rawValue === undefined || rawValue === null) return;
    const value = String(rawValue).trim();
    if (!value || value === 'none' || value === 'null') return;
    if (waivedTarget !== undefined && value === waivedTarget) return; // C6 GAP2 explicit waiver
    let resolved;
    try {
      resolved = _resolveTarget(value, dir, repoRoot, gitHistoryCache);
    } catch (_e) {
      // Resolver threw — fail-open (cannot prove unresolvable).
      return;
    }
    if (resolved === null) {
      violations.push({
        field,
        value,
        reason: 'unresolvable in live ∪ archive-on-disk ∪ git-history (provably never-existed)',
      });
    }
    // resolved is an absolute path or the 'git-history' sentinel → both OK, no violation.
  }

  // predecessor is a handoff-path edge EXCEPT on kind:recovery, where it is a
  // SHA subject to the same-repo-only foreign-baton carve-out (never rejected
  // here — see function header).
  const kind = frontmatter.kind;
  if (kind !== 'recovery') {
    checkField('predecessor', frontmatter.predecessor);
  }

  // Review: code-reviewer F4 — forked_from / additional_predecessors are
  // checked UNCONDITIONALLY here (no kind:recovery exemption), and that is
  // correct: per coordinator CLAUDE.md § Handoff Lineage and
  // docs/wiki/spinoff-handoffs.md's crash-recovery section ("separate
  // predecessor: pointers to each crashed handoff's SHA"), the recovery
  // convention is SHA-shaped ONLY on predecessor. forked_from and
  // additional_predecessors are always real handoff-path edges, even on a
  // kind:recovery record — a recovery handoff never carries a fan-in SHA in
  // additional_predecessors[] or a branch-point SHA in forked_from. Extending
  // the exemption to those fields would silently admit a genuinely
  // never-existed path edge on a recovery record.
  checkField('forked_from', frontmatter.forked_from);
  checkField('origin_handoff', frontmatter.origin_handoff);

  if (Array.isArray(frontmatter.additional_predecessors)) {
    frontmatter.additional_predecessors.forEach((entry, idx) => {
      checkField(`additional_predecessors[${idx}]`, entry);
    });
  }

  return violations;
}

// ---------------------------------------------------------------------------
// Exported: handoffEdges — the edge-kind SSOT kernel
// ---------------------------------------------------------------------------

/**
 * Given parsed frontmatter metadata for a node and a Set of edge-kind names,
 * return the resolved edge-target strings for those fields (raw string values,
 * not resolved paths). Sentinels ('none', 'null', null, '') are excluded.
 *
 * @param {Object} nodeMeta   Parsed frontmatter object for the node.
 * @param {Set<string>} edgeKinds  Subset of {'predecessor','additional_predecessors','forked_from'}.
 * @returns {string[]}  Raw edge-target references (not yet path-resolved).
 */
function handoffEdges(nodeMeta, edgeKinds) {
  var result = [];
  edgeKinds.forEach(function(kind) {
    var kindMeta = EDGE_KIND_META[kind];
    if (!kindMeta) return; // unknown kind — skip
    var val = nodeMeta[kindMeta.field];
    if (val === undefined || val === null) return;
    if (kindMeta.multi) {
      // Array field — include each non-sentinel element
      if (Array.isArray(val)) {
        val.forEach(function(item) {
          var s = String(item).trim();
          if (s && s !== 'none' && s !== 'null') result.push(s);
        });
      }
    } else {
      var s = String(val).trim();
      if (s && s !== 'none' && s !== 'null') result.push(s);
    }
  });
  return result;
}

// ---------------------------------------------------------------------------
// Exported: walkForward — forward BFS/DFS accumulation
// ---------------------------------------------------------------------------

/**
 * Forward traversal from startPath, following edges named in edgeKinds.
 *
 * Traversal:
 *   - DFS with explicit stack to avoid recursion depth limits.
 *   - BLACK set: fully-finished nodes. Re-encounter → benign diamond → skip (not abort).
 *   - GRAY set: nodes currently on the active DFS path. Re-encounter → back-edge → lineage-cycle.
 *   - Each file is parsed at most once (path-level dedup = the VISITED_PATHS structural diamond guard).
 *   - BFS-order approximation: frontier is processed depth-first per edge but orderedPaths reflects
 *     first-encounter order, which matches the producer intent (terminal → roots).
 *
 * Missing-link handling:
 *   - An edge-target that cannot be resolved → terminatedEarly='missing-link', but accumulation
 *     continues on the remaining edges of the current node and the rest of the frontier.
 *
 * @param {string} startPath  Absolute path to the starting node.
 * @param {{edgeKinds?: Set<string>, nodeGate?: (meta:Object)=>boolean, handoffDir?: string}} opts
 * @returns {{nodes: Object.<string,Object>, orderedPaths: string[], terminatedEarly: string}}
 *   nodes        — map from absolute path → parsed frontmatter for each visited node.
 *   orderedPaths — paths in first-encounter (BFS-ish) order, startPath first.
 *   terminatedEarly — '' | 'lineage-cycle' | 'missing-link'.
 */
function walkForward(startPath, opts) {
  opts = opts || {};
  var edgeKinds = opts.edgeKinds || new Set(['predecessor']);
  var nodeGate  = opts.nodeGate  || function() { return true; };
  var handoffDir = opts.handoffDir || null;

  // Resolve startPath to absolute
  var absStart = path.resolve(startPath);

  // Infer handoffDir and repoRoot from startPath if not provided
  if (!handoffDir) {
    handoffDir = path.dirname(absStart);
  }
  var repoRoot = _repoRootFromHandoffDir(handoffDir);

  var nodes = {};         // absolute path → frontmatter
  var orderedPaths = [];  // first-encounter order
  var terminatedEarly = '';

  // DFS with explicit stack
  // Each stack entry: { absPath: string, parentPath: string|null }
  // graySet: paths on the current DFS active path (for back-edge detection)
  // blackSet: fully finished nodes (for diamond convergence detection)

  var graySet = new Set();
  var blackSet = new Set();

  // DFS via explicit stack (iterative DFS to handle large chains)
  // We simulate DFS by processing neighbors in reverse-push order.
  // Review: code-reviewer (F2) — removed dead `stack` and `grayStack` vars; traversal uses dfsStack.

  // Iterative DFS: push each node, process its edges, mark black when done.
  // Since we need gray/black tracking (to distinguish back-edge vs diamond),
  // we use a two-visit approach: first visit marks gray + processes edges,
  // second "pop" visit marks black.

  // Stack entries: { path: string, phase: 'enter'|'exit' }
  // Review: code-reviewer (F8) — removed dead `edgeTargets: null` field from all frame sites.
  var dfsStack = [{ path: absStart, phase: 'enter' }];

  while (dfsStack.length > 0) {
    var frame = dfsStack.pop();
    var absPath = frame.path;

    if (frame.phase === 'exit') {
      // Finishing this node — mark black, remove from gray
      graySet.delete(absPath);
      blackSet.add(absPath);
      continue;
    }

    // phase === 'enter'

    // Diamond check: already fully finished (black)?
    if (blackSet.has(absPath)) {
      // Benign convergence — skip, do not abort
      continue;
    }

    // Cycle check: currently on active path (gray)?
    if (graySet.has(absPath)) {
      terminatedEarly = 'lineage-cycle';
      // Do not abort — just skip this re-encounter
      continue;
    }

    // Parse the node
    var meta = _readMeta(absPath);

    // nodeGate: if the gate rejects this node, do not expand or count it
    if (!nodeGate(meta)) {
      // Mark black immediately (don't visit its edges)
      blackSet.add(absPath);
      continue;
    }

    // Mark gray (entering)
    graySet.add(absPath);

    // Record this node (first encounter)
    nodes[absPath] = meta;
    orderedPaths.push(absPath);

    // Push exit frame BEFORE processing edges so gray→black on the way back up
    dfsStack.push({ path: absPath, phase: 'exit' });

    // Collect edges
    var rawEdges = handoffEdges(meta, edgeKinds);

    // Resolve edges and push to DFS stack in reverse (so first edge processes first)
    var edgesToPush = [];
    for (var i = 0; i < rawEdges.length; i++) {
      var targetAbs = _resolveTarget(rawEdges[i], handoffDir, repoRoot);
      if (!targetAbs) {
        // Unresolvable edge — record missing-link but continue
        terminatedEarly = 'missing-link';
        continue;
      }
      if (targetAbs === 'git-history') {
        // Tier-3-only resolution: the target existed (proves the edge is not
        // "never existed", which is what C2's write-time reachability reject
        // cares about) but has no disk path to walk into for LoE forward
        // accumulation. Not a missing-link (the target IS resolvable) — just
        // nothing further to traverse from here.
        continue;
      }
      edgesToPush.push(targetAbs);
    }

    // Push in reverse order so first edge is processed first (DFS characteristic)
    for (var j = edgesToPush.length - 1; j >= 0; j--) {
      dfsStack.push({ path: edgesToPush[j], phase: 'enter' });
    }
  }

  return {
    nodes: nodes,
    orderedPaths: orderedPaths,
    terminatedEarly: terminatedEarly,
  };
}

// ---------------------------------------------------------------------------
// Exported: referencedBy — DIRECT non-transitive reverse-membership test
// ---------------------------------------------------------------------------

/**
 * Test whether `target` is named as an edge-target (via any field in edgeKinds)
 * by any node in `liveSet`. Single-hop membership test, NOT transitive reachability.
 *
 * @param {string} target    Absolute path of the candidate node to test.
 * @param {string[]} liveSet Array of absolute paths to scan for references to target.
 * @param {{edgeKinds?: Set<string>, handoffDir?: string, exclude?: string[]|Set<string>}} opts
 *   opts.exclude — paths to drop from liveSet before scanning (compared by resolved absolute path).
 *                  Absent or empty → behaviour byte-identical to today.
 * @returns {{referenced: boolean, referencedBy: string[]}}
 *   referenced    — true if any node in liveSet names target as an edge.
 *   referencedBy  — array of absolute paths of nodes that reference target.
 */
function referencedBy(target, liveSet, opts) {
  opts = opts || {};
  var edgeKinds = opts.edgeKinds || new Set(['predecessor', 'additional_predecessors', 'forked_from']);
  var handoffDir = opts.handoffDir || (liveSet.length > 0 ? path.dirname(liveSet[0]) : process.cwd());
  var repoRoot = _repoRootFromHandoffDir(handoffDir);

  // Build exclusion set (resolved absolute paths) so callers can pass --exclude <path>
  // and have matching liveSet members dropped before the membership scan.
  var excludeSet = new Set();
  if (opts.exclude) {
    var excludeArr = Array.isArray(opts.exclude)
      ? opts.exclude
      : Array.from(opts.exclude); // handle Set<string> input too
    for (var ei = 0; ei < excludeArr.length; ei++) {
      if (excludeArr[ei]) excludeSet.add(path.resolve(String(excludeArr[ei])));
    }
  }

  // Filter liveSet by exclusion set (no-op when excludeSet is empty)
  var filteredLiveSet = excludeSet.size === 0
    ? liveSet
    : liveSet.filter(function(p) { return !excludeSet.has(path.resolve(p)); });

  var absTarget = path.resolve(target);
  // Also collect the basename for comparison (callers may pass just filename refs)
  var targetBasename = path.basename(absTarget);

  var referencers = [];

  for (var i = 0; i < filteredLiveSet.length; i++) {
    var nodeAbsPath = filteredLiveSet[i];
    var meta = _readMeta(nodeAbsPath);
    var nodeHandoffDir = path.dirname(nodeAbsPath);
    var rawEdges = handoffEdges(meta, edgeKinds);

    for (var j = 0; j < rawEdges.length; j++) {
      var rawRef = rawEdges[j];
      // Resolve the raw ref to absolute
      var resolvedRef = _resolveTarget(rawRef, nodeHandoffDir, repoRoot);
      if (!resolvedRef || resolvedRef === 'git-history') {
        // Unresolvable, or tier-3-only (no disk path to compare against
        // absTarget — a live-membership test needs a disk path on both
        // sides). Fall back to basename comparison in either case.
        if (path.basename(rawRef) === targetBasename) {
          referencers.push(nodeAbsPath);
          break;
        }
        continue;
      }
      if (path.resolve(resolvedRef) === absTarget) {
        referencers.push(nodeAbsPath);
        break;
      }
    }
  }

  return {
    referenced: referencers.length > 0,
    referencedBy: referencers,
  };
}

// ---------------------------------------------------------------------------
// CLI — thin shell interface for bash consumers
// ---------------------------------------------------------------------------

/**
 * CLI usage:
 *   node walk-handoff-dag.js --start <path> [--edge-kinds a,b,c] [--format paths|json] [--handoff-dir <dir>]
 *   node walk-handoff-dag.js --reverse-membership <target> --live-set-json <json-array> [--edge-kinds a,b,c] [--format paths|json] [--exclude <path>]...
 *
 * Forward mode --format paths output contract (for bash consumers, no jq required):
 *   <absolute-path-1>
 *   <absolute-path-2>
 *   ...
 *   terminatedEarly=<value>
 */
function _runCli(argv) {
  var args = argv.slice(2);
  var startPath = null;
  var edgeKindArg = null;
  var format = 'paths';
  var handoffDirArg = null;
  var reverseTarget = null;
  var liveSetJson = null;
  var excludePaths = []; // accumulates --exclude <path> occurrences (reverse mode only)

  for (var i = 0; i < args.length; i++) {
    if (args[i] === '--start' && args[i + 1]) {
      startPath = args[++i];
    } else if (args[i] === '--edge-kinds' && args[i + 1]) {
      edgeKindArg = args[++i];
    } else if (args[i] === '--format' && args[i + 1]) {
      format = args[++i];
    } else if (args[i] === '--handoff-dir' && args[i + 1]) {
      handoffDirArg = args[++i];
    } else if (args[i] === '--reverse-membership' && args[i + 1]) {
      reverseTarget = args[++i];
    } else if (args[i] === '--live-set-json' && args[i + 1]) {
      liveSetJson = args[++i];
    } else if (args[i] === '--exclude' && args[i + 1]) {
      excludePaths.push(args[++i]);
    }
  }

  var edgeKinds = new Set(
    edgeKindArg
      ? edgeKindArg.split(',').map(function(s) { return s.trim(); }).filter(Boolean)
      : ['predecessor']
  );

  if (reverseTarget !== null) {
    // Reverse-membership mode
    var liveSet = [];
    try {
      liveSet = liveSetJson ? JSON.parse(liveSetJson) : [];
    } catch (e) {
      process.stderr.write('walk-handoff-dag: failed to parse --live-set-json: ' + e.message + '\n');
      process.exit(1);
    }
    var revOpts = { edgeKinds: edgeKinds };
    if (handoffDirArg) revOpts.handoffDir = handoffDirArg;
    if (excludePaths.length > 0) revOpts.exclude = excludePaths;
    var revResult = referencedBy(reverseTarget, liveSet, revOpts);
    if (format === 'json') {
      process.stdout.write(JSON.stringify(revResult, null, 2) + '\n');
    } else {
      revResult.referencedBy.forEach(function(p) { process.stdout.write(p + '\n'); });
      process.stdout.write('referenced=' + (revResult.referenced ? 'true' : 'false') + '\n');
    }
    return;
  }

  if (!startPath) {
    process.stderr.write('walk-handoff-dag: --start <path> is required\n');
    process.exit(1);
  }

  var fwdOpts = { edgeKinds: edgeKinds };
  if (handoffDirArg) fwdOpts.handoffDir = handoffDirArg;

  var result = walkForward(startPath, fwdOpts);

  if (format === 'json') {
    process.stdout.write(JSON.stringify(result, null, 2) + '\n');
  } else {
    // --format paths: newline-delimited resolved absolute paths + trailing terminatedEarly= line
    result.orderedPaths.forEach(function(p) { process.stdout.write(p + '\n'); });
    process.stdout.write('terminatedEarly=' + result.terminatedEarly + '\n');
  }
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

module.exports = {
  handoffEdges: handoffEdges,
  walkForward: walkForward,
  referencedBy: referencedBy,
  // Promoted per C2 (F1) — the write-time reachability pass in
  // validate-frontmatter-schema.js reuses this directly rather than
  // duplicating resolution logic. Returns an absolute disk path (tier 1/2),
  // the string sentinel 'git-history' (tier 3, disk-absent but git-known),
  // or null (unresolvable in all three tiers).
  // Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C2
  _resolveTarget: _resolveTarget,
  // Promoted per C6 GAP1 backfill — the shared reachability RULE (not just
  // resolution) so validate-frontmatter-schema.js (write-time) and
  // query-records.js validateAllRecords (batch sweep, consumed by
  // validate-handoff.js) apply byte-identical reachability semantics.
  // Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C2, § C6
  checkLineageReachability: checkLineageReachability,
  // Batch-sweep perf (code-reviewer F5) — primes a Set of every repo-relative
  // path ever `git add`ed in history via one `git log --all --name-only
  // --diff-filter=A` pass, for callers doing many checkLineageReachability
  // calls in one sweep (query-records.js validateAllRecords) to pass as the
  // optional gitHistoryCache param instead of paying a per-call subprocess
  // spawn for every unresolved field. Returns null on any git failure —
  // callers must treat null identically to "no cache" (fall back to per-call).
  // Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C2 (F5)
  buildGitHistoryCache: buildGitHistoryCache,
};

// Run CLI when invoked directly
if (require.main === module) {
  _runCli(process.argv);
}
