<!-- WORDING IS PM-REVIEW-GATED before this ships to consumers (v3split-02 finding #3). -->

# Notice

This release of coordinator-claude ships **doctrine**: skills, agents, reviewer personas,
and planning conventions — the thinking layer that shapes how work gets planned, reviewed,
and executed. It also ships the **executing machinery layer** — the `bin/`, `hooks/`, and
`lib/` scripts that those skills shell out to at runtime — so the workflows described here
run as described, not merely as a preview.

What this repository does **not** contain is the **`coordinator_core` control-plane engine**:
the layer that produces and mutates work-state artifacts and drives session control. That
engine is published as a separate companion repository,
[`claude-klabauter`](https://github.com/dbc-oduffy/claude-klabauter). coordinator-claude
declares a hard dependency on it.

## What this means for you

Two repositories, one system, both publicly clonable. Install this one for the doctrine and the
machinery it drives; the control plane those workflows call into needs the engine, installed
separately from `https://github.com/dbc-oduffy/claude-klabauter`.

Everything in the doctrine layer is readable and adaptable on its own — the skills, the agent
and reviewer personas, the planning conventions — and the `bin/`, `hooks/`, and `lib/` scripts
a skill shells out to are present and functional here. The workflows that read and write
on-disk work state additionally need the engine, installed from the companion repo above.

The split is deliberate rather than transitional: the two layers version independently, and
the boundary between the doctrine that decides and the engine that executes is the same
boundary this system asks its own operators to respect.
