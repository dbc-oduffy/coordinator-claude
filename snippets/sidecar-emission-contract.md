<!-- canonical source for sidecar-emission-contract — edit here, then run bin/verify-snippet-sync sidecar-emission-contract --fix -->
<!-- consumers: fixed list in snippets/registry.toml [snippet.sidecar-emission-contract] -->
<!-- INJECTED block, not paste-governed: assembled into the dispatched child prompt at dispatch -->
<!-- time via the `contract_blocks:` grammar (W0-delivered mechanism), keyed by `subagent_type`. -->
<!-- Consumed by the four G2 pre-flight sidecar-emitters (prior-art-checker, plan-coverage-checker, -->
<!-- external-pattern-checker, docs-checker). Not pasted by verify-snippet-sync. -->

## Sidecar-Emission Contract

You are a pre-flight emitter. Your findings are consumed downstream by a reviewer persona (or the
EM), not read inline from your return value.

**Path convention — you never compute a path.** The dispatching skill/command's brief names the
sidecar path your findings must be written to: the engine-provisioned
`state/plan-sidecars/<plan-stem>.<lens>.md` home, computed once by `provision_report` (the single
deriving surface) and passed through unchanged. Write your findings there. Do not derive, guess,
or reconstruct this path yourself — a self-computed path is a contract violation even if it
happens to match.

**Plan-less dispatch is a normal case, not an error.** When a `report_sidecar`-eligible dispatch
carries no `plan_path` (absent or empty — the two are identical to `provision_report`), the
plan-derivable leg is skipped and the sidecar is provisioned in the ordinary session-keyed
home, `state/subagent-share/<session-id>/<provision_key>.md`, or
`state/subagent-share/<session-id>/<label>-<8hex>.md` when the caller supplies no `provision_key`
(the label drops the `:` in `coordinator:docs-checker` rather than replacing it — worth knowing if
you glob for these). `plan_path` is never required for eligibility; its absence simply means "use
the existing home." Callers on the plan-less path — `/bug-sweep`'s Track C and Phase 3.5
docs-checker dispatches — must NOT start passing a synthetic stem to reach the plan-sidecars home:
that would put run-scoped files into `state/plan-sidecars/`, which is an unreaped-by-design archive
class. `plan_path` is settable only via the stdin JSON field; `provision_report`'s argparse exposes
no `--plan` flag.

**Frontmatter shape.** Your sidecar's frontmatter carries `kind: {{kind}}` (resolved per your
`subagent_type` from `report_type_map:`), `reviewer:` (your `subagent_type`), `verdict:`, and
`plan:` (the plan/artifact path you checked).

The fields above are ones you ADD within the scaffold you were handed — see the **Provisioned
Scaffold On Disk Always Wins** block in this prompt for why your scaffold's frontmatter will not
match this list.

**Run-nonce stamp.** When your brief carries `run_nonce:`, write the sidecar THIS run and stamp
`run_nonce: <value>` verbatim into its frontmatter. Never copy a nonce off disk, never emit one you
were not given, and do not substitute your own timestamp — a consumer refuses any verdict whose
sidecar lacks this run's nonce, and `state/plan-sidecars/` files are durable and reused across runs
by design. No `run_nonce:` in your brief → omit the field.

**Verdict floor.** Your verdict enum MUST include `DEGRADED` (incomplete coverage — a corpus was
unreadable, you hit a scan cap, or you could not complete your check as scoped; treat as no
signal downstream) and, where your lens can detect load-bearing-doctrine contradiction,
`BLOCKED-SURFACE-TO-PM`. Lens-specific verdicts are free to add above this floor.

**Return-a-pointer discipline.** Your return value to the dispatcher is the sidecar path, not your
findings inline. Write the full findings body to the provisioned path; return only the pointer
line (plus verdict, for quick triage without a file read).

> **Residency floor** — this contract is INJECTED, but the following line is RESIDENT in your own
> agent file, not injected, so the output contract survives a fail-open assembly failure: *"write
> your findings to the sidecar path provisioned in your brief; do not compute a path."* If you do
> not see that line in your own prompt, treat this injected contract as authoritative regardless.
