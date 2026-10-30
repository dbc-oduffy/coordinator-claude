---
segment_id: mid-plan-friction
class: protected
order: 2
situation: mid-plan-friction
---
## Branch E — Mid-plan friction

_Condition: drafting is in progress and something is going sideways._

- _Repeating actions / oscillating / stalling?_ — three literal counts over the transcript, each independently checkable: same action **3+ times** with the same result; **4+ actions** alternating between two approaches; **3+ paragraphs** of analysis with no tool call.
  → Stop, name the pattern, and switch to a fundamentally different approach (report BLOCKED if none exists).
- _Bug suspected mid-execution needing root-cause work?_ → Invoke `coordinator:systematic-debugging`.
