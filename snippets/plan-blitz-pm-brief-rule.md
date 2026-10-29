<!-- Read directly by the plan-blitz planner brief; not a synced snippet, no embedding. -->

PM VERBATIMS FIRST. When the sizing that routed this baton carries `pm_verbatims`, the PM's own
words are already captured: Read the sizing and paste each `pm_verbatims[].text` VERBATIM, in
the order stored (newest first), as the `## PM brief` blockquote, one `> ` block per turn
separated by a bare `>` line. No tool step: a shell read of `state/sizings/` trips the
doctrine-surface write guard. Then set frontmatter
`pm_brief: {source: pm-verbatim, ref: "<repo-relative sizing path>"}`. Do not re-extract, trim, or
paraphrase them. When the sizing carries no `pm_verbatims`, the baton rule below applies unchanged.

CARRY THE BATON'S ASK INTO THE PLAN'S OWN BRIEF. Absent sizing `pm_verbatims`, this baton record is
the only PM utterance behind this plan, and nothing downstream of you reads the baton again — the emitter and every reviewer
read the PLAN, not this record. Copy the baton's `summary:` frontmatter line, a blank line, then
its `## What this covers` section (when present), VERBATIM — never paraphrased, trimmed, or
summarised — into a `## PM brief` section in the plan body, as a blockquote. Set frontmatter
`pm_brief: {source: baton-originating-ask, ref: "<repo-relative path to this baton record>"}`.

Give EVERY spine row a `traces_to_brief`: a short phrase, quoted verbatim from the `## PM brief`
text, naming which part of the PM's ask that row serves. A row that can quote nothing from the
brief is scope growth on this baton — say so in your summary rather than inventing a quote to fill
the field. The spine checker already reports a STRUCTURAL finding for any
non-deferred row with a missing or paraphrased trace once the plan carries a `## PM brief`
section, so this is enforced mechanically and not left to review.
