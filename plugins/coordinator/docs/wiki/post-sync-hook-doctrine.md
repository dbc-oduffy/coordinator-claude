---
name: post-sync-hook-doctrine
status: canonical
---

# Post-Sync Hook Doctrine

<!-- spec backlink: none — doctrine distilled from publish pipeline operational experience -->

Post-sync hooks that run after `rsync` or `publish.sh` completes MUST constrain their work to the set of files the sync actually transferred. A hook that walks the destination tree as a whole operates on state it didn't create, and silently mutates files this sync had no stake in.

## The Leak

When `rsync` syncs a delta — say, 3 changed files out of 200 in the destination — a naive post-sync hook that iterates `dest/**` will process all 200. For read-only checks (grep audits, schema validation) this is usually harmless. For **mutating** hooks — depersonalisation scripts, link-rewriters, license-stampers — it is a corruption vector:

- Files that arrived in a previous sync run get re-mutated under the new run's assumptions.
- State the hook injects may not match what this sync delivered (e.g., rewriting a brand token using the source repo's identity when the file came from a different source).
- Idempotency is illusory: the hook appears to succeed on re-run, but output diverges from what a from-scratch sync would produce.

## The Discipline

A mutating post-sync hook MUST accept the rsync touched-file list on stdin and operate only on those paths. The hook is a pure function of `{rsync output} → {destination mutations}` — not of the destination tree's current state.

**Contract:**
```
# hook receives one relative path per line on stdin (rsync's --out-format='%n')
# and operates only on those paths in the destination
while IFS= read -r path; do
  mutate "$DEST_ROOT/$path"
done
```

The hook MUST NOT open `dest/` independently. If a path outside the stdin list needs mutating, that is a separate maintenance task — not a post-sync side-effect.

## rsync Recipe

Feed `rsync --out-format='%n'` through `tee` to both capture the list for the hook and let normal stdout progress flow:

```bash
rsync --out-format='%n' [OPTIONS] "$SRC/" "$DEST/" \
  | tee >(post-sync-hook --dest "$DEST")
```

The hook reads stdin. `tee` lets the caller see progress too. If you need the list for auditing as well:

```bash
rsync --out-format='%n' [OPTIONS] "$SRC/" "$DEST/" \
  | tee touched.log \
  | post-sync-hook --dest "$DEST"
```

On Windows/Git-Bash, `tee >()` process substitution may not be available — use an intermediate file:

```bash
rsync --out-format='%n' [OPTIONS] "$SRC/" "$DEST/" > touched.log
post-sync-hook --dest "$DEST" < touched.log
```

## When This Matters

Apply the touched-list constraint to any hook that **mutates** destination content:

- **Depersonalisation scripts** — strip author-specific strings, brand tokens, or machine paths.
- **Link-rewriters** — adjust cross-reference paths from source-repo layout to publish-repo layout.
- **License-stampers** — prepend or update license headers.
- **Tag-injectors** — embed version or provenance metadata into file content.

If the hook rewrites even one byte of a file it didn't receive via this sync, the constraint applies.

## Read-Only Checks Are Exempt

Post-sync checks that only **read** the destination — grep audits, schema validators, link-checkers, checksum verifiers — may scan the full destination tree. They produce no mutations, so destination-tree scope does not corrupt state. The touched-list constraint is a mutation guard, not a query guard.

## Cross-References

- `docs/wiki/percolate-setup.md` — percolation pipeline where hook scoping first mattered
- `docs/wiki/plugin-extraction-and-distribution.md` — publish pipeline that drives `publish.sh` / rsync invocations
