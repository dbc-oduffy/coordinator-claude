# Enricher Survey Fragment — Unreal Engine

Domain-specific survey steps for UE projects. Included in enricher dispatch prompts when `project_type` includes `unreal` or `game-docs`.

## UE Survey Steps

1. Read the `.uproject` file to determine:
   - Unreal Engine version
   - Plugin list (which are enabled, which are code plugins vs Blueprint-only)
   - Whether the project has C++ modules or is Blueprint-only

2. Map the `Content/` directory tree:
   - Count assets by type (Blueprints, Materials, StaticMeshes, SkeletalMeshes, Textures, Sounds, Animations, DataTables, etc.)
   - Identify naming conventions in use
   - Flag any unusual structures or unexpected asset locations

3. Read `Config/` files:
   - `DefaultEngine.ini` — renderer settings, plugin config, asset manager entries
   - `DefaultGame.ini` — game mode, default maps, project-level settings
   - Any other ini files relevant to the stub's domain

4. Inventory Blueprints relevant to the stub:
   - Parent classes, component lists, event graph summary (what events are handled)
   - Variable names and types if relevant to the task

5. Inventory meshes, materials, and animations relevant to the stub:
   - File paths, LOD counts, skeleton names, animation sequences available
