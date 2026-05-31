---
title: LFS + coordinator-auto-push Post-Commit Hook Merge
status: living
last_updated: 2026-05-14
applies_to: any consumer repo running both git-lfs and coordinator-auto-push
source: project-rag-ue-addon/docs/wiki/lfs-gitattributes-discipline.md § "LFS + coordinator-auto-push Post-Commit Hook Merge [UNIVERSAL]"
note: plugin-bundled UNIVERSAL companion; project-local source is canonical for project context
xref:
  - coordinator-auto-push
---

# LFS + coordinator-auto-push Post-Commit Hook Merge

Operational pattern for any consumer repo that adopts both `git-lfs` and
the coordinator-auto-push post-commit helper. The collision is structural,
not project-specific — both tools want exclusive ownership of
`.git/hooks/post-commit`, and `git lfs install --local` does not support a
"merge into existing hook" mode.

First codified in `project-rag-ue-addon` during the W0-T5 LFS rollout
(2026-05-13); promoted here as a universal pattern. The project-local wiki
at `project-rag-ue-addon/docs/wiki/lfs-gitattributes-discipline.md` carries
the full clone-and-go-contract context; this file extracts the
hook-merge dance for general consumption.

## Failure Mode

`git lfs install --local` exits 2 when `.git/hooks/post-commit` already
carries the coordinator-auto-push helper. The LFS installer does a
byte-equality idempotency check against its expected hook content; a
foreign hook present blocks the install.

Filter wiring in `.git/config`
(`filter.lfs.{required,clean,smudge,process}`) is wired correctly by
`git lfs install --local` *regardless* of the hook collision — only the
hook merge needs human intervention. The visible symptom is the exit-2;
the LFS install is otherwise complete.

## The Manual Merge Dance

The merged `.git/hooks/post-commit` must run `git lfs post-commit` BEFORE
the coordinator-auto-push helper (LFS expects to run synchronously against
the freshly-created commit; auto-push runs after and pushes the result):

```sh
#!/usr/bin/env bash
# Merged hook: LFS first, then coordinator-auto-push.
git lfs post-commit "$@"
exec coordinator-auto-push "$@"
```

The AC spirit (LFS post-commit runs after every commit) is satisfied; the
AC letter (`git lfs install --local` exits 0 idempotently) is blocked by
the existing hook. Override workflow:

```sh
git lfs update --manual       # documents the manual-merge state
# Author the merged hook by hand (template above).
chmod +x .git/hooks/post-commit
```

## Why This Is Universal

ANY consumer repo adopting both LFS + coordinator-auto-push hits this. The
collision is structural — neither tool ships a merge mode. The fix is
mechanical (a four-line shell hook) but undocumented in either tool's
README, so first-time consumers re-derive it under time pressure.

## Optional Follow-Up — Installer Amendment

Separate plan, not part of this wiki: amend `coordinator-auto-push`
installer to detect an existing LFS hook (or vice versa) and emit the
merged form directly, eliminating the manual step. Until that lands, the
manual dance above is the contract.

## When to Apply This Pattern

- Any new repo onboarded with `coordinator:project-onboarding` that also
  needs LFS for large artifacts (corpora, asset packs, model weights).
- Any existing repo adding LFS to a tree that already carries the
  coordinator-auto-push hook.

## When NOT to Apply

- Repos using LFS but not coordinator-auto-push — `git lfs install --local`
  works idempotently in that case.
- Repos using coordinator-auto-push but not LFS — no collision.
