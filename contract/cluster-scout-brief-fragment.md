# Cluster-scout-brief fragment

`cluster-scout-brief-fragment.json` is the dispatch shape behind `dispatch-cluster-scout` —
`roadmap-planning` Step 1.5.1, one research scout per cluster. The doctrine plane owns the brief and the
exclusion rules; a consumer reads them from here rather than reconstructing them, on the
`review-roster-fragment` precedent.

Doctrine source: `skills/roadmap-planning/SKILL.md` step 1.5.0–1.5.1, its UE-cluster precondition,
and `docs/wiki/planning/roadmap-planning-residue.md` § "Research-corpus scouting, beyond the default".

## The brief is fixed; only the scope varies

`preamble_text` is `snippets/internet-research-scout.md` inlined verbatim rather than referenced
by path, so the consumer resolves nothing across repos at dispatch time. Composition is the
preamble, a blank line, then the cluster's own scope text — and that is the whole prompt. No
per-cluster brief authoring. The census types this row MECHANICAL precisely because the brief does
not vary: vary it and the row stops being mechanical, which is the classification the assembler
binding rests on.

## Two inputs the op consumes and must never compute

**`depth_disposition`** is the PM's, from step 1.5.0. A `deep-research` cluster produces a
**directive naming the cluster and nothing else**: the op emits the directive, and the EM sizes
and fires `/research`. An op that dispatches deep research itself has taken the EM's sizing call.

**`excluded_clusters`** arrives resolved. The standing producer is the UE-internal-API
precondition: a UE cluster whose `project-rag` probe returns no hit STOPS, and no web scout is
dispatched in its place. The probe is project-rag's capability, which is exactly why it is not
this op's job — the op takes the set, it does not compute it. `never_substitute` is the part that
matters: the failure mode this guards is a scout cheerfully returning a confident web brief about
an engine-internal API it cannot see, which then grounds an OVERVIEW section.

## Measurement-derived corpus files are not scout output

A cluster the web cannot answer — this project's own schema, behaviour, or prior `/spike` output —
may have its `research-corpus/<topic-slug>.md` written by hand from first-hand measurement. That
file carries a stricter bar than scout output (explicit provenance paragraph, `file:line` or a
named run artifact per claim) and it **replaces** the scout rather than seeding it. Dispatching
over it overwrites measurement with search results, which is the one failure here that leaves no
trace: the file still exists, still looks like a corpus, and no longer says what was measured.

## The `min_bytes` floor is a grounding check, not a formatting rule

A scout returning under 2KB has not grounded its cluster, and the OVERVIEW section citing that
file will read as researched. Report the short file; do not pad it and do not silently accept it.

## Changing it

`tests/test_supplied_fragments.py` pins the preamble against the live snippet — if
`snippets/internet-research-scout.md` is edited and this inlined copy is not, the test fails
rather than letting a consumer dispatch last month's brief. It also pins the concurrency cap, the
byte floor, and every `never` rule id, since a consumer dropping one of those is invisible from
here.
