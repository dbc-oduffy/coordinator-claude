<!-- canonical source for no-grep-glob-harness-note — edit here, then run bin/verify-snippet-sync no-grep-glob-harness-note --fix -->
<!-- consumers: fixed list in snippets/registry.toml [snippet.no-grep-glob-harness-note] -->
<!-- INJECTED block, not paste-governed: assembled into the dispatched child prompt at dispatch -->
<!-- time via the `contract_blocks:` grammar (subagent-sandbox-policy.yaml), keyed by -->
<!-- `subagent_type`. Carries the static harness-capability fact that this harness build ships no -->
<!-- Grep/Glob tool — zero per-consumer customization across any carrier, the textbook injection -->
<!-- case. Relocated from 17 resident carriers (14 verbatim "phrasing A", 3 divergent "phrasing -->
<!-- B" paraphrases now converging on this canonical wording via injection) per -->
<!-- state/audits/2026-08-06-cross-body-duplication-census.md § Span 1. Canonicalized on -->
<!-- phrasing A's wording — crisper: names the two replacement primitives explicitly. -->
<!-- PLACEHOLDER-FREE BY CONSTRUCTION: do not add any placeholder here. The closed set is -->
<!-- {kind, sidecar_path, subagent_type} and this block needs none of them; the closed placeholder -->
<!-- set is enforced by coordinator/tests/test_contract_blocks.py. -->

This harness build provides no Grep/Glob tool. Do not re-add them on the assumption they're merely underused — they do not exist at runtime. Search with whatever shell your own `tools` list actually grants -- PowerShell (`Select-String`, `Get-ChildItem`) or `python -c`; a host that bans Bash bans it for you too. No shell in that list means no code search: say so rather than improvising one.
