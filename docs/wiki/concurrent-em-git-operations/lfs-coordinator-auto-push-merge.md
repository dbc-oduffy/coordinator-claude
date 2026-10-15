---
title: LFS + coordinator-auto-push Post-Commit Hook Merge (retired)
status: retired
last_updated: 2026-10-13
applies_to: any consumer repo running both git-lfs and coordinator-auto-push
note: retired; no LFS hook is installed into a repo
xref:
  - coordinator-auto-push
  - gitattributes-lfs-carve-outs
---

# LFS + coordinator-auto-push Post-Commit Hook Merge (retired)

Retired. This page used to teach merging `git lfs post-commit` into
`.git/hooks/post-commit` after `git lfs install --local`. Do not install
git-lfs hooks into a repo: the push path runs no git-lfs and no test runner
(`PRE-PUSH-RUNS-NO-TESTS-AND-NO-LFS`).

What applies instead:

- Git-LFS is opt-in per repo: it applies only where the root `.gitattributes` has a
  `filter=lfs` pattern plus `# lfs-justification: <reason>`. The installer never enables it.
- A repo that LFS-tracks content keeps its `.gitattributes` rules
  (`gitattributes-lfs-carve-outs`); filter config is enough for clean/smudge.
- Never run bare `git lfs install` or `git lfs install --local` in a
  coordinator-hooked repo.
