<!-- canonical source for docs-checker-consumption — edit here, then run bin/verify-docs-checker-sync.sh --fix -->

## Docs Checker Integration

If your dispatch prompt cites a **docs-checker pre-flight** with sidecar paths (typically `tasks/review-findings/{timestamp}-docs-checker-edits.md` and a verification report), the artifact has already been mechanically verified and may have been auto-edited. Use the pre-flight to focus your review on architecture, approach, and design.

**Claim statuses:**
- **VERIFIED** — docs-checker confirmed the API claim against authoritative sources. Trust it. Do not re-verify.
- **AUTO-FIXED** — docs-checker corrected the claim inline. The edits are in a single git-revertible commit and listed in the changelog sidecar. Review the changelog only if you spot something docs-checker shouldn't have touched (e.g., it edited a deliberate battle-story breadcrumb). Surface as a finding if so — the EM will revert from the docs-checker commit.
- **UNVERIFIED** — docs-checker could not confirm. Verify these yourself with your available documentation tools, or flag them in your findings if verification matters and you cannot resolve.
- **INCORRECT (not auto-fixed)** — low-confidence corrections or items outside the AUTO-FIX allowlist. Already in the report. Disposition them as findings.

**EM spot-check obligation.** After your review completes, the EM will diff the docs-checker commit against the pre-edit artifact for any auto-fix you did not explicitly endorse. Your review record is the trigger — call out endorsed and unendorsed auto-fixes explicitly when relevant.

**When no docs-checker pre-flight ran**, verify APIs yourself using your available documentation tools. This integration is additive — your review standards don't change, only the division of mechanical labor.

### Header/include and module-placement claims defer to docs-checker

For compiled-language artifacts (especially C++ / UE), factual claims about which header declares a symbol, which module/`.Build.cs` the symbol lives in, or whether a symbol is `*_API`-exported are **docs-checker territory, not yours**. A plan can pass architectural review and still fail to compile from a wrong include path or a missing module dependency.

If the dispatch did not include a docs-checker pre-flight and the artifact contains specific header/include/visibility claims, **do not approve on architectural grounds alone** — flag in your verdict that a docs-checker pass is required before merge, or verify those specific claims yourself using LSP `goToDefinition` and source reads. Architectural soundness without a verified link surface is incomplete review.
