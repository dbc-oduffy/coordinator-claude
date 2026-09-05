# Peer-Port Discipline — Adopting and Comparing Across Sibling Repos

> **Scope.** What to re-verify whenever an artifact crosses a repo boundary — copied helper code, cribbed scaffolding/manifests, or a peer-comparison gap-audit. This is the *adoption-and-comparison* sibling of `peer-repo-polarity.md` (which governs *which repo owns what*). Polarity answers "where does this capability live?"; this wiki answers "I'm pulling something across — what did I inherit that the author didn't intend, and is the gap I'm declaring real?"

The shared failure shape across all three rules below: **a cross-repo artifact carries hidden state from its origin context, and "complete / already reviewed upstream" is sender-side framing that predates your current reality.** Re-verify against *your* repo's current contract, license, and surface — not the source's.

## Rule 1 — Re-verify an adopted helper against YOUR module's CURRENT contract

Verbatim-adopting a sibling-authored helper that calls **your** package's API can carry a latent bug: the sibling coded against whatever contract your API had when they wrote it. Your API may have evolved since.

- **Case (functional_probe adoption from example-game-repo → project-rag-ue-addon):** example-game-repo's `verify_engine_corpus.py` (authored for us, copied verbatim per the memo) `.exists()`-checked the return of `_paths.engine_structural_index_path()`. But this repo's per-band layout later changed that resolver to **raise** `AddonResolutionError` on absent corpus instead of returning a non-existent path. The copied code let the raise escape as an uncaught traceback on the most common install state ("corpus not downloaded yet"); the exit code was coincidentally still 1, so the contract held but the operator saw a scary stack trace.
- **How to apply:** before trusting an adopted call site that invokes a module **you** own, grep that module's *current* return/raise contract (sentinel vs. raise? which exception?) and confirm the adopted code handles it. "Complete / already reviewed upstream" is sender-side and predates your API's evolution. Converges with the inbound-memo-conformance-is-a-hypothesis rule (`cross-repo-communication.md`): re-verify sibling artifacts — claims **and** code — against your own current reality.

## Rule 2 — Scrub copied metadata fields (license / author / copyright / URLs) before propagating

Copy-paste scaffolding from a precedent file silently carries that project's **license / copyright / author / repository** claims. These look like template-shaped boilerplate but encode legal claims about a *different* project.

- **Case (MCP-registry-distribution spinoff in example-game-repo):** scaffolding cribbed shape from `Unreal_mcp`'s `package.json` + `server.json` + `publish-mcp.yml`. A `"license": "MIT"` string had already laundered into example-game-repo's `control/server/package.json` weeks earlier (predated this spinoff per `git log`) and was propagated again into `server.json` and a wiki draft. Example-game-repo's actual LICENSE is "Copyright (c) 2026 Dónal O'Duffy. All rights reserved." — proprietary. PM caught it on commit-review.
- **Why it slips:** copy-paste scaffolding optimizes for getting the *shape* right (workflow steps, jq patterns, env-vars); semantic-but-text-shaped fields ride along unnoticed.
- **How to apply:** at any "I'm adapting workflow/manifest X from peer repo Y" moment, the **first** grep after the paste is `(license|author|copyright|homepage|repository|bugs)` against the new file vs. the local `LICENSE` / git remote. Treat license-string drift as a **P0 correctness bug**, not a cosmetic cleanup.

## Rule 3 — Peer-comparison gap-audits run in BOTH directions (peers AND host)

A peer-comparison gap-audit must include an **"already-shipped-in-this-repo"** coverage check before declaring a gap. "No peer has an equivalent" implicitly asserts "and we don't either" — that's the omitted half.

- **Case (UE+MCP peer-comparison S4 closeout in example-game-repo):** T15 (material function introspection) was spun off as a P3 absorption candidate with "no peer including S2/S3 has an equivalent." Pickup-side Phase 0 found it had **already shipped** in `390928b48 — feat(VUE-4G)` weeks prior — full stack including TS dispatch, schema, and 4 unit tests. The synthesis gap-audit looked outward (peer tools) but never ran the symmetric inward check (this repo).
- **How to apply:** at gap-audit time on any comparison campaign, the substrate-coverage check runs in two directions. Cheap mechanical test: **grep the proposed action name across the host's handler tree** before authoring the absorption candidate.

## When this fires

- Adopting/copying any code, manifest, workflow, or scaffolding from a sibling repo.
- Running a peer-comparison / market-survey / competitive-gap campaign where the host repo is the destination for "absorption" candidates.
- Receiving a cross-repo memo whose `ask` is "adopt our helper / mirror our manifest" — the adoption still routes through Rules 1–2 even when the memo was accepted.

## Related

- `peer-repo-polarity.md` — which repo owns which capability (the ownership axis; this wiki is the adoption/comparison axis)
- `cross-repo-communication.md` — memo content is hypothesis; verify before acting
- `repo-registry.md` — peer-repo prior-art lookup
- CLAUDE.md § Implementation Standards — "existence ≠ fit" (a reused helper's *shape* must match, the in-repo correctness analog of Rule 1)
