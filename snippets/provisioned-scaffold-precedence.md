<!-- canonical source for provisioned-scaffold-precedence — edit here, then run bin/verify-snippet-sync provisioned-scaffold-precedence --fix -->
<!-- consumers: fixed list in snippets/registry.toml [snippet.provisioned-scaffold-precedence] -->
<!-- INJECTED block, not paste-governed: assembled into the dispatched child prompt at dispatch -->
<!-- time via the `contract_blocks:` grammar, keyed by `subagent_type`. Carried by EVERY -->
<!-- `report_sidecar`-eligible subagent_type — this is the one contract block with no family, and -->
<!-- that universality is the point. The three artifact-type families (sidecar-frontmatter-contract, -->
<!-- sidecar-emission-contract, run-report-citizenship) each declare a DIFFERENT frontmatter field -->
<!-- set, and every one of them differs from the shape the engine actually scaffolds; the -->
<!-- reconciliation between "what my contract names" and "what is on my disk" is identical for all -->
<!-- of them, so it lives here once rather than in each family. It previously lived in -->
<!-- sidecar-frontmatter-contract only, and the two families that lacked it generated repeat false -->
<!-- alarms against correctly-provisioned sidecars — per-family placement is what leaks, which is -->
<!-- why re-inlining this text into a family block would reopen the defect it closes. -->
<!-- PLACEHOLDER-FREE BY CONSTRUCTION: do not add `{{kind}}` or any other placeholder here. This -->
<!-- block is the one piece of contract text that is byte-identical for every report type; a -->
<!-- per-type placeholder would defeat its purpose (and the closed placeholder set is enforced by -->
<!-- coordinator/tests/test_contract_blocks.py). -->

## The Provisioned Scaffold On Disk Always Wins

Your sidecar was already created for you before you started. Its frontmatter will **not** match the
field list your own contract block describes — that mismatch is correct provisioning, not a defect
or a template-resolution bug, and not something to report.

The fields your contract names are the ones you **add** *within* the scaffold you were handed —
never a competing frontmatter to overwrite it with. Fill the scaffold you got; leave its existing
fields alone.

**The scaffold's frontmatter is type-invariant.** `status: open`, `agent_type:`, `spawned_at:`,
`lead_session_id:`, `divergence:`, `commits:`, and `dispatch_feed:` are emitted identically for
every report type, and `## Exit interview` closes every scaffold regardless of type — none of them
indicates a particular type. **No scaffold is born carrying a `kind:` field:** it is one of the
fields your contract asks you to add, so its absence tells you nothing.

**Read the body headings, never the frontmatter, to confirm you got the type you asked for:**

| Scaffold body sections | Report type |
|---|---|
| `## Verdict`, `## Rationale` | `staff-eng-review` |
| `## Findings` | `review-findings` |
| `## Questions` | `assessment` |
| `## Run notes`, `## Observations` (± `## Divergence from plan`, `## Completion`) | `run-report` |

If your body sections match, say nothing and get on with the work — reporting an upstream
provisioning defect on frontmatter alone is a false alarm this block exists to prevent, and
merging the two shapes "to be safe" produces a file neither consumer expects.

Only a genuine **body-section** mismatch is worth raising, and then by noting it in your own output
(`divergence:` where your type has one, your findings body otherwise) — never by overwriting the
scaffold to the shape you expected.
