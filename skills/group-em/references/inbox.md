---
segment_id: inbox
class: protected
order: 4
situation: inbox
---
    Workflow({scriptPath: "<plugin-root>/workflows/fleet-inbox-blitz.mjs", args: {repos: [...], gem: {...}}})

Fire it first after arming the watch. `repos` is the fleet map (`machine-local get repos.*`, repos
with `state/cross-repo/inbox`). **Do not hand-author a variant.** Save each
manifest to `<home>/state/residue/inbox-blitz/<date>/<repo>.json` (a second run that day: `<date>-r2/`), one parent folder for every run; residue, moved to cold storage once its run closes, never a record. **A repo with a live EM** (`claude
agents --json`): memo the manifest by path to that EM, who applies and commits it, and closes the apply memo itself in the same pass (the manifest predates that memo, so it never lists it). Then tap that EM with a `SendMessage` naming the memo and manifest path: a memo alone waits for the EM's next inbox read; the memo is the record, the tap is the alert. **A repo with
no live EM: apply it yourself** under `coordinator.feature.gem_cross_repo_commit` (writes, stamps,
moves, memos_to_send, then one commit scoped to `commit.pathspec`); a memo to an EM-less repo is
never read, and eight such repos sat unapplied for five rounds. Off: start a session there. Tripwires: `A-GROUP-EM-HAND-AUTHORING-THE-INBOX-WORKFLOW`,
`A-GROUP-EM-HOME-RECEIVES-MEMOS-AT-ITS-OWN-INBOX` (the fleet inbox grind covers the home's own inbox).
