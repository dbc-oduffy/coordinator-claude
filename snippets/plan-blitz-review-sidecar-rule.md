<!-- Read directly by the plan-blitz reviewer and premise-check briefs; not a synced snippet, no embedding. -->
<!-- The brief supplies the slots this text refers to: the provisioner invocation, your pointer path and your `agent_type` value. -->

Write your findings sidecar to YOUR OWN PROVISIONED SIDECAR under
`<machinery_root>/subagent-share/<your session id>/`, and return its absolute path verbatim as
`sidecarPath`.

Write your findings outside the wave trail: `review-findings-ledger`
refuses any path without `subagent-share` as a path segment, and a findings sidecar it cannot
open is a review whose ledger is never recorded.

That sidecar must open with YAML frontmatter carrying the `agent_type:` key at column zero, with
the value the brief gives you.

The same op checks the agent type as well as the path, and refuses a sidecar carrying neither an
allowlisted reviewer type nor the `review-findings` doc token. The refusal is the quiet one: your
review still runs, but nothing else verifies it applied, and nothing in the wave reports that the
block is missing. Measured 2026-09-10 on a live five-fire wave: 24 of 25 findings sidecars carried
no `agent_type` at all, and the whole wave's ledgers went unrecorded.

**The BODY needs one heading, spelled exactly `## Findings Ledger`, holding exactly one fenced
```json array — one row per finding, per § Contract.** Then write a POINTER file at EXACTLY the
pointer path the brief gives you, containing a SHORT STRUCTURED RECORD as one JSON object and
nothing else — not a bare path:

```json
{"sidecarPath": "<the absolute sidecar path above>", "verdict": "<your verdict, exactly as you return it below>", "premiseFailure": "<your premiseFailure verbatim, or null if you did not state one>"}
```

The pointer is how the wave finds you. A findings sidecar with no pointer is a review the
wave cannot see, and a pointer with no sidecar is worse — it reads as a review that ran.

The sidecar is the durable record this wave is read from: a finding that exists only in your
returned summary is a finding the wave's reader will never see.
