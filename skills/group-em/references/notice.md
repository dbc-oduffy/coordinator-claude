---
segment_id: notice
class: protected
order: 6
situation: box-notice
---
**Every live named session, in any repo, is told when the standing begins and ends.**
`group-em-autofire.py` cannot send, so it prints `BOX NOTICE OWED` in the entry context: one text
and the recipient list (you, `PAUSED:away` and already-introduced peers excluded). **Send that
text to each, this turn**, under the introduction rules in `references/entry.md`; the displaced holder's owed message
is separate and still owed.

**Before this session ends, run `<plugin-root>/bin/group-em-box-notice.py --kind ended --repo
<root> --session-id <your sid>`** (no `SessionEnd` hook can send): it stands the nomination down
and prints the no-Group-EM text and recipients; send it. Tripwire:
`A-GROUP-EM-STANDING-THE-BOX-WAS-NEVER-TOLD-ABOUT`.
