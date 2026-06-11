# Post-Install Onboarding Pattern

> The shape of an **offer-shaped, optional, re-runnable** guided tour surfaced at the tail of a tool's install/setup chain — and how that shape changes when the tool sits in a dependency chain with a mandatory downstream link. This is the **pattern doctrine** (for an EM building a tour in any repo); the coordinator's own operator-facing *instance* of it is [`getting-started.md`](getting-started.md).

## The pattern, in one sentence

At the end of your install/setup chain, surface a single offer-shaped, optional, re-runnable pointer to a guided-tour wiki that the EM *facilitates as a conversation* with the freshly-installed operator — orient, tailor, test drive.

## The three movements (the wiki's spine)

1. **Orient — what they just installed.** The 3–5 headline ideas of the tool, in the order they'll matter. Not a feature dump; the EM calibrates to the operator's background and leads with what's relevant to *them*.
2. **Make it yours — tailor to taste.** Suggest the one or two customizations that follow from the orient conversation (offer, don't dump). Carries the load-bearing correctness point below.
3. **Test drive — a real spin.** Run something small and *real* (their project, their task) through the actual machinery so the operator feels it work, with the EM narrating what's happening and why.

Close with: it's optional, re-runnable, and the system is theirs to evolve. Add a compact "## For the EM facilitating this" playbook section at the foot so a subagent/EM that reads the file runs it conversationally rather than reciting it.

## The load-bearing point — customize the live surface, not the source

Movement 2 hinges on a correctness rule: **customizations land in the operator's live install surface, not the upstream source/distribution repo.** For coordinator that's "edit your git-tracked `~/.claude`, not a clone of `coordinator-claude`" — the source-is-live model. Each tool's live surface differs (a `.mcp.json` wiring + machine-local registry entry; an installed plugin location vs. the addon source repo; a UE project's installed plugin/MCP config vs. the tool source). Get this right and the tour teaches a true mental model; get it wrong and you teach operators to edit a tree that does nothing. Naming the operator's live surface is the **key adaptation decision** for each tool.

## Where it hangs

- **Install-chain link:** the tail of the setup skill. Offer-shaped per [design-as-offers](eager-agent-calibration.md) — lead with the invitation ("want a tour?"), not a nag. Skip under any `--check-only` mode.
- **Wiki home:** the repo's `docs/wiki/getting-started.md` (or reference-docs equivalent), registered in the wiki index. If the repo percolates to a publish target, confirm the wiki dir ships.
- **Doctor variant (optional):** a pointer from a rich doctor's clean-bill-of-health output too — a healthy re-run is also a "what now?" moment.

## Variant — hard-dependency chains: the chain onboards from the leaf

The base pattern assumes a **standalone-capable** tool (coordinator, project-rag host): the tour can self-fire at the tool's own setup/doctor-green, and degrade gracefully if some *optional* capability is absent. When the seeded pattern is applied to a tool with a **hard capability dependency** — e.g. holodeck, which is useless without the live UE workbench, or any addon that is inert without its host runtime — three things change:

1. **No standalone fire, no graceful-degrade.** With nothing useful to demo absent the dependency, the tour stays **silent** when the dependency is missing and instead points at the missing install. There is no partial form — a Movement 3 "real spin" is impossible without the capability, so a degraded tour would teach a false mental model.

2. **The auto-trigger centralizes at the LEAF of the dependency chain.** Parent/upstream links **defer**; the leaf fires once all prior links are installed. The standalone rule *"self-fire at your own setup/doctor-green"* flips to *"defer to the leaf"* whenever a downstream link is mandatory. This is what prevents a **double-offer** across the chain — without it, each link in an A→B→C install would offer its own tour and the operator would be onboarded three times to one capability.

3. **Orientation receipts nest as a superset chain.** Completing a higher (leaf) orientation marks every lower (upstream) one done — a superset relationship over the per-link receipts. Crucially, **suppression is auto-offers-only**: the nesting gates the *automatic nag*, never the *manual re-run*. The optional/re-runnable property of the base pattern is fully preserved — an operator can always re-take any link's tour by hand; they just won't be auto-prompted for a link a superset orientation already covered. (Receipt mechanics — first-occurrence-wins, set-once — are coordinator's [`coordinator-setup-state-receipt.md`](coordinator-setup-state-receipt.md); the nesting is the leaf-chain generalization of that single-tool receipt.)

### The reusable doctrine bit

> For a tool chain with a mandatory downstream link, **"every tool self-onboards" generalizes to "the chain onboards from the leaf."** Standalone tools self-fire and degrade; chained tools defer upstream and fire once at the leaf, with orientation receipts nesting as a superset and suppression gating only the automatic offer.

The discriminator is **mandatory vs. optional** downstream capability — an optional dependency keeps the standalone "self-fire and degrade" shape (Movement 3 just trims the unavailable spin); a mandatory one flips to leaf-onboarding.

### Coordinator-completeness rule (orthogonal to the mandatory-vs-optional discriminator)

The mandatory-vs-optional discriminator governs **how a downstream dep onboards** — does it self-fire, or does it defer to the leaf? The coordinator-completeness rule is a separate, orthogonal concern: **installing coordinator is installing a collaboration contract, not software.** The whole system goes in.

**DIY-cherry-pick of coordinator is unsupported — period.** Not "off the rails, your responsibility" with a shrug, but genuinely unsupportable: downstream repos plug into coordinator infra, and a cherry-picked subset could silently remove the skill, agent, or hook a downstream chain depends on. We can't validate a custom subset, so we cannot say whether the chain will work. The right move is install-everything-then-tweak — disable individual pieces after the fact, not during install (installed-but-disabled is a supported state; see `per-project-plugin-gating`).

**Offer granularity is the add-on level, never the component level.** Add-ons (deep-research, notebookLM) are genuine install-time picks. But once you've chosen to install coordinator, you get all of it — every skill and reviewer: `/staff-session`, the personas, the full pipeline. You never pick-'n'-mix coordinator's own internals during install.

These two rules apply simultaneously and do not interact: a chain can have optional dependencies and
still require a complete coordinator install on the upstream node, and a mandatory-dependency chain
still doesn't justify cherry-picking coordinator's internals.

## Onboarding bug fixes — three-layer rule

Onboarding failures recur unless the fix ships all three layers:

1. **Prevention** — fix the install / setup script so future runs don't hit the failure at all.
2. **Reactive repair** — a recovery path for users who already hit it and won't re-run the full installer. Valid shapes: a `doctor`-style script (`--fix` flag) or an idempotent slash command safe to re-run against broken state. What matters is recovery without a clean-slate install.
3. **Searchable docs** — a row in the troubleshooting table keyed on the **literal error text** the user would see, with cause and fix.

   ```markdown
   | Error | Cause | Fix |
   |-------|-------|-----|
   | `ModuleNotFoundError: No module named 'coordinator_whoami'` | coordinator-whoami package not installed | Run `/coordinator:install` to install the introspection package |
   ```

**When onboarding flags a new failure:** verify all three layers exist before closing. Missing layers are part of the same fix, not a follow-up task. Layer 2 typically lives at a doctor probe (e.g. probe P-5 in [`coordinator-doctor.md`](coordinator-doctor.md)).

## Cross-references

- [`getting-started.md`](getting-started.md) — the coordinator's operator-facing *instance* of this pattern (full structure, voice, EM-facilitation playbook). The reference impl to steal from.
- [`coordinator-setup-state-receipt.md`](coordinator-setup-state-receipt.md) — per-machine receipt mechanics + cross-repo chaining gate that the receipt-nesting variant builds on.
- [`eager-agent-calibration.md`](eager-agent-calibration.md) — design-as-offers: the offer-shape (not nag) discipline the install-chain link must follow.
- [`cross-repo-communication.md`](cross-repo-communication.md) — seeding this pattern to sibling repos is doctrine seeding (DoE altitude); wiring a specific sibling's install chain is that EM's install-surface work, relayed via the PM.
- Hard-dependency reference plan (sibling repo): `project-rag-ue-addon/docs/plans/2026-05-23-ue-flavored-guided-tour-wrap.md` — the holodeck/UE-addon application that surfaced the leaf-onboarding variant.
- [`agent-install-contract.md`](agent-install-contract.md) § Install-spinoff layer — the **install-execution** counterpart to this **onboarding-tour** doctrine. This wiki governs the leaf-fires-the-tour rule (suppress double-offers); the contract's install-spinoff layer governs how a multi-repo *install itself* is sequenced durably across the coordinator reboot: coordinator onboarding is the handoff, each queued downstream repo is a `kind: spinoff` baton in the standard `~/.claude/state/handoffs/` folder, stitched onto one install-chain spine. Tour = "what now?"; install-spinoff layer = "the install is still coming, here's the tracked chain."
- [`produce-not-prescribe.md`](produce-not-prescribe.md) — setup-class skills produce minimum-viable substrate; this doctrine is about the *conversation*, that one is about the *substrate*.
