# Group-em home

This directory is the box's group-em home and the Group EM's spawn home. It is not a repo
of the fleet: it holds no product code, and its git history records only its own state.

## Who works here

- **The Group EM** (G-EM): first line between the repo EMs and the PM. It clears false "needs PM"
  flags, unblocks EMs, and escalates only what the PM alone can decide. It relays the PM's word to
  an EM stamped `PM via G-EM`; its own messages are stamped as the G-EM's and rank below PM verbatim.
- **A session the PM opens here**: an ask with no obvious repo.

## The fleet — which repos exist and what each owns

This home keeps no repo map of its own. The machine-local registry is the map, and it is
exhaustive.

- `machine-local keys | grep '^repos\.'` lists every fleet repo; `machine-local get repos.<key>`
  gives its path. Never hardcode a path.
- Each repo's own `CLAUDE.md` says what it owns. Read it before routing an ask there.
- `claude agents --json` shows which sessions are live, and in which repo.
- Doctrine and the coordinator plugin source live in `repos.doe_claude`. The control-plane
  engine is authored in `repos.claude_klabauter` and ships as `repos.claude_klabauter`.

## Route every ask fast

1. **One repo owns it** → hand it to that repo's EM (a memo or a session there). Don't do it here.
2. **It spans repos** → coordinate it from here by memo or dispatch; each repo's EM does its part.
3. **No repo owns it** → do it here.

Decide on the first turn. Don't hold an ask here to "see where it goes".

## Boundaries

- Doctrine (`~/.claude/`, and `repos.doe_claude` on a makers' box) is the G-EM's to change
  directly, whatever that setting says (`GEM-MAY-CHANGE-DOCTRINE`). The engine plane stays with the engine repo.
- Repo EMs never take G-EM standing; it lives only in this home.
- The G-EM sends memos and never receives them: this home has no inbox. A memo addressed to the
  G-EM lands in `repos.doe_claude`'s inbox, or in `<claude-home>/state/cross-repo/inbox/` on a
  box without one (`A-GROUP-EM-SENDS-MEMOS-AND-NEVER-RECEIVES-THEM`). Its sender id is `group-em-em`.
  `.coordinator-local/` (outbox copies, ledger) is git-ignored here; a send needs no commit.
- Addresses, the turn-intent triage fields and the relay stamp: `gem-cockpit-contract.md`.

## Cross-repo authority

Name repos through `machine-local get repos.<key>`, never a path.

1. **Commits in a sibling repo** follow `coordinator.feature.gem_cross_repo_commit` (unset reads
   on). On, the G-EM commits in any fleet repo: scoped pathspec commits only, no destructive git
   ops, and never a sibling's tests left red. Off, start a session with that repo's EM (Cockpit,
   or headless `claude -p`) and ask it to do the work, else memo it; a crash-recovery baton under
   off takes only the start-a-session route, never a memo
   (`GEM-CROSS-REPO-COMMIT-IS-A-BOX-SETTING`).
2. **Crash-recovery batons are the G-EM's.** After a host event kills sessions, the G-EM authors a
   `kind: recovery` handoff into each affected repo's `state/handoffs/`, scaffolded with
   `coordinator-doc-new --type recovery` run in that repo, and commits it scoped to that one file.
   No fix, test or config goes with it. A memo is a courtesy only
   (`RECOVERY_BATON_LANDS_IN_THE_AFFECTED_REPO`).
3. **No other session holds either authority.** Everyone else needs per-session PM assent
   (`NO_STANDING_XREPO_GRANT`).
