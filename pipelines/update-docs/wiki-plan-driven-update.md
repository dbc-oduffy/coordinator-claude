---
name: wiki-plan-driven-update
description: "Select the wiki pages a /update-docs run refreshes by a script query over completed plans' touched files and sizing, then hand one agent only those pages and bounded plan previews. Invoked by /update-docs (Phase 2c)."
version: 1.0.0
---

# Wiki refresh — plan-driven selection

## Overview

Script first: a deterministic op selects the wiki pages and reads the plan previews; an agent is
dispatched only to write prose on those pages.
(rules 1, 2 and 6). Contract: `coordinator/docs/contracts/wiki-update-candidates.md`.

**Never a fan-out over the whole corpus.** No agent greps the wiki, lists plans or reads plans to
find what changed; the op did that. A model reads at most ~10k characters per plan (the op's
`preview`) and only the pages in `pages[]`. A page outside the set is a Phase 14 line, never a read.

---

## Mechanical layer

Run in the EM session before any dispatch. No leg dispatches an agent.

1. Run `coordinator-invoke ceremony.wiki_candidates '{}'`, resolved per
   `coordinator/snippets/resolve-coordinator-bin.md`. Default params; `since` only when the PM or
   a plan row names one.
2. Read the reply: `pages[]` (each `{page, plans[{path, commit_sha, tshirt, preview}]}`),
   `preview_chars_total`, `truncated`. Keep `preview_chars_total` for the Phase 14 cost line.
3. Outcomes:
   - `pages[]` empty: no dispatch; the cost line reads `0 agents`.
   - Op not registered: `no-producer`. Phase 14 carries a `no-producer` line, no agent is
     dispatched, and no agent substitutes a wiki grep or plan read. Memo the owner of the missing
     producer.
   - `pages[]` non-empty: continue.

The step edits no page.

---

## Narrative on listed pages

One Sonnet agent (`model: "sonnet"`) takes the listed pages in turn; a split is the EM's call,
named in Phase 14. Its brief carries only: each listed page's path, and per page each plan's
`path`, `commit_sha`, `tshirt` and `preview`. It reads the page and the previews, edits the page
where the previews show the page's cited behaviour changed, and stops. It does not read plans,
other pages or the corpus beyond what a cited path needs to resolve; a plan it wants to see in
full is a Phase 14 line.

Edits fold into the Phase 9 commit. The agent never commits or pushes.

---

## Cost line

Phase 14 `**Bookkeeping cost:**` = the agent's `total_tokens` from the Agent tool's usage result
(measured, never self-reported) plus `preview_chars_total`. With no dispatch, `0 agents` plus
`preview_chars_total`.
