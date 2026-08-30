Three mechanisms live downstream. They are named here so the author knows the ground is covered,
not so this run performs them:

- **Readiness view** (POSIX-host form, Shape A; PowerShell hosts: Shape W,
  `snippets/resolve-coordinator-bin.md`). Resolving `roadmap-number-stubs --state <run-id>` prints
  every stub's `deployment_state` and its gate text, sorted by `(sprint, wave, stub_id)`. It is a *view* for whoever is choosing what to pick up — never a loop this skill runs. Nothing wires the resolver in yet. (see `/workday-start` Steps 1.473, 1.55.)
- **Gate transitions are not this skill's to make.** A stub moves `awaiting_gate → ready_to_fire` when the `/handoff` or `/workstream-complete` of some *other* session clears its gate. Never auto-transition a sibling's stub, and never pre-emptively mark one ready because its gate looks satisfied from here.
- **End-of-roadmap review** belongs to whoever closes the roadmap out — a cross-cutting pass over the shipped output, dispatched from `/workstream-complete` once every stub has shipped. Specified below for that session, not queued for this one.

**Roadmap stubs are never handed to `/mise-en-place` directly.** Mise's Phase 0 readiness gate
rejects them by construction, on three independent counts: `deployment_state: awaiting_gate` is a
hard bypass-disqualifier and is one of the two legal stub states; criterion 1 ("the decisions are
made") fails because a stub is precisely the artifact that carries decisions forward — its
`pm-gates.md` rows and `## Recommended next steps` block are open forks by design; and criterion 3
("a single Sonnet executor can complete it given the spec") fails because a stub's deliverable is
decisions, not typed lines. Mise optimizes for deep planning BEFORE the run; the stub is the
pre-planning artifact. Routing stubs there produces a guaranteed reject-and-`pickup-assemble drop`
round trip.

## Downstream mechanism — gate-meaningfulness audit (brief recommendation F)

**Fires from `/handoff` and `/workstream-complete`, never from this skill.** Specified here because
this skill authors the gates it audits.

Named op: **gate-meaningfulness-audit**, invoked by `/handoff` and `/workstream-complete` whenever either is about to write `deployment_state: ready_to_fire` over an existing `awaiting_gate` value (the *unblock* event). NOT invoked from `/pickup` — pickup transitions to `in_flight`, not `ready_to_fire`.

The op resolves prior frontmatter from git (`git show HEAD:state/handoffs/<file>`) and fires only on a detected `awaiting_gate → ready_to_fire` edge. Idempotent under concurrent-EM operation by construction: it fires only on that literal edge observed against the file's current git state, so a stub a concurrent EM already transitioned reads `ready_to_fire` as the prior state and the op skips silently — no double-prompt, no race window where neither EM fires it. Whichever commit lands first owns the audit.

**Judgment residue (the op surfaces this; it does not resolve it — human/EM call only):** on a detected edge, the op surfaces the prior `blocking_notes` text (falling back to `gate_dependency` for pre-deprecation records that carry the prose there instead) and asks:

```
The gate that blocked this stub was:
  <blocking_notes (or gate_dependency, for older records) text from prior frontmatter>

Does that gate still mean what it meant when authored? (y/n/clarify)
```

- `y` → transition proceeds.
- `n` → stub returns to `awaiting_gate`; author updates `blocking_notes` (or `gate_dependency` on an older record still carrying it there) to reflect what's actually now blocking.
- `clarify` → PM disposition required before transition.

Would have caught ESC-5 (G1 went structurally hollow when synthetic-baseline acceptance changed its meaning).

## Downstream mechanism — end-of-roadmap review

**Owned by the session that closes the roadmap out, not by this run.** Once every stub has shipped,
dispatch ONE Sonnet review across the whole roadmap output — NOT per-wave Opus (empirical finding: end-of-run
Sonnet beat per-wave Opus on cost without meaningful signal loss). Brief: "Cross-cutting review of
<run-id> roadmap execution. Flag any drift from stubs, missing acceptance criteria, deferred items
that should have been fixed in-session."

1. **Dispatch `coordinator:code-reviewer`** (UNNAMED — no `name:` param) on the roadmap output. It is auto-provisioned a `review-findings`-typed sidecar at spawn (`report_type_map`, `state/subagent-share/…`); the brief states the doc-handoff contract: write findings there and return a pointer, not a dump — `DONE: <sidecar-path> | verdict: <OK|WARN|BLOCKED> | findings: <N>`. No pre-scaffold, no claim marker. Read the returned path.
2. **Integrate via `coordinator:review-integrator`** pointing at the on-disk sidecar path from the returned pointer — not an inline finding list (`agents/review-integrator.md` § Intake precondition hard-stops on inline-relayed findings). Surface escalations (ESC-N format) to PM.
