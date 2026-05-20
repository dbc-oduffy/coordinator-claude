---
title: ".gitattributes LFS Carve-Outs — Last-Match Semantics"
status: active
kind: doctrine-wiki
created: 2026-05-18
---

# .gitattributes LFS Carve-Outs — Last-Match Semantics

## Overview

`.gitattributes` patterns are matched line-by-line; the LAST line whose pattern matches a given
file determines that file's attributes. This is the opposite of the `.gitignore` mental-model
(first match wins), and it is a common foot-gun.

When LFS is in use and you want to carve out an exception ("track these `.bin` files in regular
git, even though `*.bin filter=lfs` exists earlier"), the carve-out line MUST appear AFTER the
generic rule. Placing it before the generic rule is silently wrong — the generic rule re-applies
and the carve-out has no effect.

## The Failure Mode

```gitattributes
# .gitattributes — WRONG ORDER
deploy/keep-*.bin -filter -diff -merge -text   # carve-out is BEFORE…
*.bin filter=lfs diff=lfs merge=lfs -text      # …so this line wins for keep-*.bin too
```

```gitattributes
# .gitattributes — CORRECT ORDER
*.bin filter=lfs diff=lfs merge=lfs -text
deploy/keep-*.bin -filter -diff -merge -text   # carve-out AFTER the generic rule
```

Verification: `git check-attr --all deploy/keep-foo.bin` — Git prints the resolved attributes
for that path. If `filter` is still `lfs`, the ordering is wrong.

## Silent Failure Chain (project-rag-ue-addon, 2026-05-15)

1. `.gitattributes` has `*.bin filter=lfs` with no effective carve-out (carve-out existed but
   appeared BEFORE the generic rule, so it was overridden).
2. A new `.bin` fixture is committed locally; Git generates an LFS pointer file.
3. A worktree dispatch creates `.claude/worktrees/agent-<hash>/` and attempts to smudge the LFS
   pointer so the agent can read the real file content.
4. Smudge fails — the LFS object was committed but not yet pushed; the LFS server has no object.
5. Worktree creation aborts with a cryptic LFS-smudge error.
6. Every Agent dispatch (worktree-isolated mode) fails until the root cause is diagnosed.
7. EM sees "Agent dispatch failed"; the actual cause — carve-out ordering in `.gitattributes` —
   is not visible in the error message.

The cascade is: wrong attribute ordering → LFS pointer for non-LFS file → smudge miss →
worktree abort → dispatch blocked.

## The Rule

For every `.gitattributes` entry that intends to OVERRIDE a more-general rule:

1. Confirm the more-general rule appears EARLIER in the file.
2. Place the carve-out AFTER it.
3. Verify with `git check-attr --all <path>` — Git resolves and prints the winning attribute
   for that specific path.
4. If the carve-out is for test fixtures or generated assets that will never be pushed to an
   LFS server, add it at time of first commit — not retroactively after smudge failures start.

## Onboarding Checklist Addition

At repo setup time (`/project-onboarding`), if `.gitattributes` is present:

- Read the file; identify every `filter=lfs` rule.
- For each LFS rule, ask: "are there fixture paths, test-data paths, or generated-asset paths
  that are currently or likely to become tracked by this pattern but should NOT go through LFS?"
- Add any carve-outs immediately AFTER the corresponding LFS rule.
- Run `git check-attr --all <representative-path>` for at least one path per carve-out to
  confirm the resolved attribute is `-filter` (not `lfs`).

Propose adding a `gitattributes audit` step to `coordinator/skills/project-onboarding/SKILL.md`.

## Quick Diagnostic

```bash
# Show resolved attributes for every tracked file — pipe through grep to find surprises
git ls-files | xargs git check-attr filter | grep lfs

# Check a single path (most useful during investigation)
git check-attr --all path/to/suspect/file.bin
```

If a path you expected to be a carve-out shows `filter: lfs`, the carve-out line is either
absent or ordered before the generic rule.

## Related

- → `docs/wiki/lfs-coordinator-auto-push-merge.md` (LFS + post-commit hook interaction)
- → `docs/wiki/agent-dispatch-economics.md` (worktree-creation costs and failure modes)
- → `coordinator/skills/project-onboarding/SKILL.md` (gitattributes audit step — propose adding)
