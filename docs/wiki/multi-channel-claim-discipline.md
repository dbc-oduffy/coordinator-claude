---
title: Multi-Channel Claim Discipline
status: active
kind: doctrine-wiki
created: 2026-06-14
provenance: example-game-workbench-repo state/lessons.md L35 (2026-06-14)
---

# Multi-Channel Claim Discipline

*Channel-scoping is one instance of a wider rule about absence claims — see § Generalization below.*

Cross-cutting infrastructure problems usually live on more than one channel — Python, TypeScript, shell, native code, CI, docs. A changelog claim like *"X is suppressed/fixed/done"* that names a *feature* without enumerating *channels* over-claims coverage at the language-agnostic altitude: readers reasonably infer the residue doesn't exist, when in fact one or more channels were never addressed. The discipline below scopes claims by channel, makes residue visible, and prevents the next reader from inheriting a false-coverage handoff.

## Rule

When claiming that a cross-cutting infrastructure problem is *fixed / suppressed / done* in a changelog, release note, completion entry, or handoff: **scope the claim by CHANNEL, not by FEATURE name.** Enumerate every channel the problem can manifest on and either (a) name it as covered with a `file:line` or commit reference, or (b) name it as explicit-deferred. Silent residue on an unnamed channel is the failure mode.

## Case — console-popup suppression (example-game-workbench-repo)

A daily-changelog claimed *"Windows console-popup suppression — 4 deployment roots."* Audit found:

- 240 unsuppressed `.sh` python/node spawns in the example-game-repo repo
- 10 more in coordinator-claude
- No `spawn-hidden.sh` helper, no shell-spawn annotation doctrine

The changelog framing was *true for the channel it named* — Python `CREATE_NO_WINDOW` and TS `windowsHide` were genuinely landed. But "console popup" is a *language-agnostic symptom*: it has three channels (Python subprocess, TS child_process, shell-spawn), and only two were addressed. The shell channel was unaddressed and invisible to readers who took the changelog at face value. The 230-site retro-fit shipped as Waves 2-5 of a separate workstream (`state/handoffs/2026-06-14_115639_example_game_repo-shell-channel-console-flash-suppression.md`). (case: example-game-workbench-repo)

## Discipline

At fix-time, enumerate the channels for any cross-cutting infrastructure claim. The general failure mode is *N-1 channels solved, framed as solved-period because the residue is invisible to the team that fixed the named channels.* A few channel taxonomies that recur:

| Symptom | Channels |
|---|---|
| Console popup on Windows | Python subprocess (`CREATE_NO_WINDOW`); TS / Node (`windowsHide`); shell-spawn (claude-klabauter `coordinator/lib/spawn-hidden.sh` / `start /b`) |
| CRLF normalization | `.gitattributes` rule; existing-tree `git add --renormalize`; editor config; CI checkout flag |
| Path resolution for sibling repos | Python helper; shell `$REPO_*` env vars; PowerShell `$env:REPO_*` |
| "All hooks fail-loud on missing dep" | PostToolUse hooks; PreToolUse hooks; SessionStart hooks; pipeline hooks |
| Secrets redaction | Logs; error messages; telemetry; crash reports; agent transcripts |

**Format for the claim:**

```
console-popup suppression — channels: Python ✓ (CREATE_NO_WINDOW, commit abc1234);
TS ✓ (windowsHide, commit def5678); shell ✗ (deferred to <handoff-path>)
```

The explicit ✗-with-pointer is what prevents the next reader from inheriting a false-coverage handoff.

## Generalization — this is one instance of a wider rule

Channel-scoping is a special case of a broader rule about absence claims: **bound every absence claim by the space you searched. Never qualify a claim you can witness.** A search that found nothing is evidence about the space searched, not about the world — "no channel X in the two files I read" is a finding; "channel X is done" is not a claim that finding licenses.

**Why:** a positive claim is licensed by a witness and is sound at any probe size. A negative claim has no witness and is licensed only over the space actually searched — no amount of additional searching converts a bounded finding into an unbounded claim. This is why "check harder" underperforms as doctrine for absence claims.

**Hedging boundary (the rule's main failure mode):** hedging qualifies a claim you hold a witness for; scoping bounds a claim whose only evidence is a search that found nothing. Bound by search space, not confidence — "I checked these three directories" is scoping, "it may be the case that" is hedging. A positive claim never gets a qualifier **once you hold the witness** — but see § The fourth quadrant below: that clause is a licence only after the witness is in hand, and it has been read as a licence to skip acquiring one.

**A failed search never overrides a positive report.** The reporter held a witness; the searcher held an empty grep — not symmetric evidence.

## The fourth quadrant — a positive claim whose witness is in the peer's tree

The rule above splits claims on one axis (positive vs. absence). There is a second axis — **where the truth-condition lives** — and crossing them gives four quadrants, not two. Three are handled. The fourth is the one that ships false claims:

| | Witness in *my* tree | Witness in *their* tree |
|---|---|---|
| **Positive claim** | assert it — the witness carries the scope | **← the unhandled quadrant** |
| **Absence claim** | bound by the space searched | bound by the space searched |

**The rule for the fourth quadrant: locate the witness before asserting, not after being corrected.** A positive claim about a fleet seam is licensed by a witness *wherever that witness lives*. If it lives on a peer's disk, read the peer's disk and cite it — `file:line` plus the branch or commit you read it at. If you cannot read it, the sentence is an **ask**, not an assertion; send it as a question.

**Why this quadrant is invisible: the grammatical subject and the truth-condition come apart.** "Our Delphi content routes through their ledger" has *our* data as its subject, so it reads as a claim about us — but nothing in it is decidable from our tree. The heuristic everyone actually runs is *"am I talking about their repo?"*, which keys on the subject. When subject and truth-condition diverge, the heuristic fires clean and the claim is still unwitnessed.

**Tell — verbs of custody and direction.** `--seed`, `project`, `land`, `publish`, `route`, `cross into`, `write into`, `hand off to`. Each *sounds* like a transfer whose destination you own, and frequently the destination-side fact is the peer's. Any sentence carrying one is a fourth-quadrant candidate: find the witness.

**Peer trees are readable — this is a detection problem, not an access problem.** Fleet repos are co-located on this machine; `git -C <peer> …`, grep, and a direct file read all work, and the cost of checking is seconds. More access changes nothing, because access was never the constraint. The entire cost sits in *noticing that a check is owed*.

**A disclosure is not a discharge.** "We have not inspected your tree and assert nothing about it," attached to a memo that then asserts things about their tree, converts *"I should check this"* into *"I have disclosed that I didn't"* — honest, and useless. Where the passive form is the only honest option, escalate it to an explicit ask the receiver can answer (*"does X still hold on your side?"*) rather than a notice they can only absorb. A scope note that fronts a fourth-quadrant claim is a signal to go read, not a licence to ship.

**Stale frontmatter reads exactly like a current fact.** A plan's `branch:` field records where it was *authored*, not the peer's current checkout; the same slippage applies to any dated field quoted as present-tense state. Resolve it live (`git -C <peer> rev-parse --abbrev-ref HEAD`) before citing it.

**Cases (`cross-repo/archive/2026-07-27-example-cockpit-repo-em-positive-claims-about-a-peer-tree-have-no-witness.md`):** four fourth-quadrant claims on one seam inside about an hour, between cockpit and project-rag — a safety premise about the peer's routing, a custody claim about which repo's store `--seed` writes into (which had reached seven code sites including two operator-facing strings before correction), a "prose is the only channel between our repos" claim made by an EM who had grepped the peer's tree four times that hour, and a fourth caught pre-send by one `git -C`. Every one was seconds from verification; none was caught by review.

**Cases:**

- MSYS `ssh.exe` absence — a sibling repo claimed "no MSYS `ssh.exe` on this machine" after checking one directory; five exist (`bash-on-windows-gotchas.md` § Superseded claim).
- Guard-regex "doesn't hold up" — the EM tested a regex in one guard file, found no match, and told the PM a subagent's bug report "doesn't hold up"; wrong file, the report was correct.
- "You've de-bashed" — the EM verified two files were Python and told a sibling repo "you've de-bashed"; 516 `.sh` files were tracked at HEAD, 29 touched that same day.

## When to invoke

- Writing a changelog entry for an infrastructure fix that crosses language/runtime boundaries.
- Drafting a release note or completion entry for a cross-cutting suppression / migration / contract change.
- Closing a workstream where the named symptom is observable in more than one runtime.
- Reviewing a peer's changelog claim that names a *feature* (console popup, secret redaction, path normalization) without naming *channels* — flag and request the channel breakdown.
- Drafting any cross-repo memo, decision record, or contract note that asserts where data, custody, or control flow *goes* — check § The fourth quadrant before sending, and read the peer's tree rather than disclosing that you didn't.

## Related

- [`completion-log-release-loop.md`](completion-log-release-loop.md) — completion entries are the canonical surface where channel-scoped claims land for downstream readers.
