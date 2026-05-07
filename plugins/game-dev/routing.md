# Routing Extension: game-dev

## Reviewers

### the Game Dev Reviewer (`game-dev:staff-game-dev`)
- **Signals:** Game dev, Unreal Engine, DroneSim, gameplay mechanics, UE5 systems, Blueprint, C++ game code, character movement, replication, GAS
- **Model:** opus
- **Effort:** Medium (escalates to High for major features / new game modes)
- **Backstop:** the Staff Engineer (`coordinator:staff-eng`) — universal reviewer
- **Agent file:** `agents/staff-game-dev.md`

### Blueprint Inspector (ue-blueprint-inspector)
- **Signals:** Blueprint inspection, Blueprint documentation, BP extraction, "inspect Blueprints", "document Blueprints", project survey
- **Model:** opus (coordinator) → sonnet (workers via ue-blueprint-worker)
- **Effort:** Low-Medium (coordinator assesses scope and makes dispatch decisions; workers are mechanical)
- **Backstop:** None (data extraction pipeline, not a judgment call)
- **Agent files:** `agents/ue-blueprint-inspector.md` (coordinator), `agents/ue-blueprint-worker.md` (worker)

## Project-Local Pairings
- DroneSim: the Game Dev Reviewer primary, the Staff Engineer backstop (default)
- claude-unreal-holodeck: the Game Dev Reviewer + the Data Science Reviewer (if data-science plugin enabled) + the Staff Engineer
