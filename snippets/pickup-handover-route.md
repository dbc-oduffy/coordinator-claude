## Live-session handover: holder-drop-then-rebrief

A PM-directed handover of a baton between two live sessions is holder-drop-then-rebrief:

1. The holder runs `pickup-assemble drop <path>`, which releases the claim.
2. The receiver runs `/pickup <path>` with the bare path, nothing after it.

The receiver never claims a baton the holder still holds, and the `/pickup` args are the bare path
only: a path plus rationale is refused with "args must be the bare path". Put the rationale in the
rebrief message to the receiver, not in the args.

Tripwire: `A-LIVE-SESSION-HANDOVER-IS-HOLDER-DROP-THEN-REBRIEF`.
