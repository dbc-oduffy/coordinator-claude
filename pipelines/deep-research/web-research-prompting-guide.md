# Web Research Prompting Guide

> Read by the `brief-author` stage for the web and structured pipelines. Rules for turning a research intent and a surveyed source list into questions specialists can answer with evidence.

## Scoping the question

- **One falsifiable question per topic.** "What are the enforcement mechanisms for X, and what evidence shows each works?" beats "Tell me about X". A topic whose question evidence cannot confirm or deny is not ready to assign.
- **State the decision the research serves.** Specialists weigh sources differently when they know whether the output feeds a design choice, a comparison or a status check.
- **Bound each topic against its peers.** Say what a topic should not cover; overlapping specialists duplicate effort and produce contradictory claims with no owner.
- **Default to four topics** unless the sizing names them; more than six dilutes depth.

## Fitting questions to the sources found

- **Ask only what a surveyed source can answer.** Assign each question the sources by name; a question with no source is reported as a gap, with a suggested query for the specialist's own search.
- **Prefer primary sources** (official docs, specifications, source code, peer-reviewed work, original reporting). Mark secondary and anonymous sources as weak, and require three corroborating sources before a claim rests on them.
- **Date matters.** Flag sources older than the topic's change rate and ask for the current state explicitly.

## Question wording

- **Demand citations.** Every question ends by requiring a quoted passage or figure and its source URL; claims without one are dropped.
- **Name the format of the answer** (table, ranked list, claim per line with confidence) so specialists return comparable output.
- **Include one adversarial question per topic**: "X problems", "why not X", "X versus Y failure reports". Practitioner forums and issue trackers answer these better than vendor pages.
- **Separate retrieval from judgment.** Ask the specialist to report what sources say, then mark its own inference as inference.

## Search-query craft

- **3-5 varied queries per topic**: official phrasing, practitioner phrasing, an error-message or symptom phrasing, and an adversarial phrasing.
- **Vary source types**: documentation, repositories, issue trackers, community forums, talks, papers.
- **Operators over prose**: site restrictions, quoted phrases and date filters narrow faster than longer sentences.

## Conflicts and gaps

- **Surface disagreement.** Where sources conflict, the brief tells the specialist to record both sides with evidence rather than pick one.
- **Name what is not covered.** End the brief with the gaps the survey left, so the sweep can fill or flag them.
