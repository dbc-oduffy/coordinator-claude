# General work

This folder is the landing spot for work with no project fit: taxes, errands, one-off research,
anything no fleet repo owns. It is not a project, but it is a git repository by default, so the
work here is tracked.

## Working state and memos

- This is a coordinator working folder: handoffs go in `state/handoffs/`, plans in
  `docs/plans/`, and memos arrive in `state/cross-repo/inbox/`.
- Its memo identity is `general-work-em`, used for both sending and receiving.
- The folder is a git repository; do not re-initialise it.

## Layout

Each task gets its own subfolder, named for the task (`taxes-2026/`, `trip-planning/`). Keep a
task's files together inside it.

## Personal content stays here

Personal content (finances, taxes, health) never leaves this folder into a repo, memo, lesson or
handoff. Do not quote it into any of them, and do not summarize it into one.
A path or file listed in `.git/info/exclude` is never staged, and never quoted into a memo or handoff.

## Working across the box

Errand work is done by hand, anywhere on the box: no sizing, engine-ask or XS budget applies here.
The boundary is a git-tracked repo other than this folder. A change inside one belongs to that
repo's EM: send it as a memo (`cross-repo-memo`) and keep working. Reading any repo is fine.
The repo registry (`repos.*`, read with `machine-local`) is the authority on which repos exist
and where; never hardcode a path. The section below is generated from it.

<!-- BEGIN generated: repos -->
<!-- END generated: repos -->
