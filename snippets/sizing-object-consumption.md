<!-- canonical source for sizing-object-consumption — edit here, then run bin/verify-snippet-sync sizing-object-consumption --fix -->
<!-- consumers: see bin/snippet-registry list-consumers sizing-object-consumption -->

<!-- BEGIN sizing-object-consumption (synced from snippets/sizing-object-consumption.md) -->
## Sizing Object

A plan whose frontmatter names `sizing_object:` was routed by that file; read it before judging scope. `intent` is the ask; `premise.evidence` and `em_analysis` hold scope, deferrals and settled decisions; `detent_discharges`/`pm_resolution` rulings; `surfaced_to_pm` open ones; `blocked_by`/`awaiting_gate` the gates. Settled is not a finding unless the tree or prior art contradicts it.
<!-- END sizing-object-consumption -->

<!-- AUTHORING NOTES — deliberately placed AFTER the END sentinel. Everything between
     BEGIN and END is injected verbatim into the dispatch prompt, so an authoring note inside
     the span is paid on every dispatch to all 8 carriers. Guarded by
     coordinator/tests/test_injected_blocks_carry_no_authoring_comment.py. -->
