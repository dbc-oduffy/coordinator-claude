<!-- canonical source for sidecar-frontmatter-contract — edit here, then run bin/verify-snippet-sync sidecar-frontmatter-contract --fix -->
<!-- consumers: fixed list in snippets/registry.toml [snippet.sidecar-frontmatter-contract] -->
<!-- INJECTED block, not paste-governed (C1, un-tooled-scaffolding extraction): assembled into the -->
<!-- dispatched child prompt at dispatch time via the `contract_blocks:` grammar (W0-delivered -->
<!-- mechanism), keyed by `subagent_type`, NOT pasted by verify-snippet-sync. Carries a {{kind}} -->
<!-- placeholder the engine resolves per persona from the existing `report_type_map:` — templating -->
<!-- a paste pass can't do, which is why this block rides injection rather than residency. -->

## Sidecar-Frontmatter Contract

When your review is saved to disk as a provisioned sidecar (the path named in your dispatch brief — typically `state/subagent-share/<session>/<provision_key>.md`), the canonical frontmatter is `kind: {{kind}}` plus `reviewer:`, `verdict:`, `findings_count:` (count of items in your `findings` array), and `plan:` (the reviewed artifact path).

Because you write your own findings to your provisioned sidecar path yourself — there is no EM persist step — you MUST include `plan: <reviewed-plan-path>` in your sidecar frontmatter; the reviewed plan/artifact path is named in your dispatch brief.

That `kind:` routes the file to the `review-sidecar` schema — NOT the plan schema — so it must NOT carry plan-schema fields (`title`/`author`/`status`-enum) to pass the frontmatter hook. `{{kind}}` is the role-based canonical value for your persona; legacy review-family values (`review`, `plan-review`, `review-sidecar`, and prior per-persona `<name>-review` values) still resolve.

The fields above are ones you ADD within the scaffold you were handed — see the **Provisioned Scaffold On Disk Always Wins** block in this prompt for why your scaffold's frontmatter will not match this list, and how to confirm your type from the body headings instead.

**Run-nonce stamp.** When your brief carries `run_nonce:`, write the sidecar THIS run and stamp `run_nonce: <value>` verbatim into its frontmatter. Never copy a nonce off disk, never emit one you were not given, and do not substitute your own timestamp — a consumer refuses any verdict whose sidecar lacks this run's nonce, and a same-session re-dispatch lands on the same provisioned path. No `run_nonce:` in your brief → omit the field.

> When a `review-integrator` is downstream, your brief carries your provisioned subagent-share sidecar path — write your `ReviewOutput` there and return only the pointer line; inline ONLY when no path is in the brief. The integrator hard-stops on inline-relayed findings (`agents/review-integrator.md` § Intake precondition).

**Named dispatch?** A teammate's return text never arrives — `SendMessage` this pointer to `"main"`.
