---
segment_id: inbox
class: protected
order: 4
situation: inbox
---
    Workflow({scriptPath: "<plugin-root>/workflows/fleet-inbox-blitz.mjs", args: {repos: [...], gem: {...}}})

Fire it first after arming the watch. `repos` is the fleet map (`machine-local get repos.*`, repos
with `state/cross-repo/inbox`). **Do not hand-author a variant.** Save each
manifest to `<home>/state/inbox-blitz-<date>/<repo>.json` and memo it by path to that repo's EM,
who applies and commits it. Tripwires: `A-GROUP-EM-HAND-AUTHORING-THE-INBOX-WORKFLOW`,
`A-GROUP-EM-SENDS-MEMOS-AND-NEVER-RECEIVES-THEM`.
