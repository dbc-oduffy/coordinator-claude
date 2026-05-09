---
title: Holodeck for Your UE Project
status: stub
created: 2026-05-06
plugin: coordinator-claude (referenced from merging-to-main skill)
---

<!-- spec-backlink: skills/merging-to-main/SKILL.md §Step 1.6 customer-facing install path check -->

Customer-facing deployment guide for integrating the holodeck ecosystem into a new Unreal Engine project. Covers: plugin installation steps, `AdditionalPluginDirectories` configuration, MCP server setup, holodeck-docs RAG index initialisation, and environment assumptions (no hardcoded local paths, no project-specific path references).

<!-- TODO: expand with end-to-end install walkthrough for a new UE project consumer; mirror install-shell-utils assumptions; verified against /holodeck:setup entry-point doctrine -->

---

## UE Engineering Notes

### `__has_include` Guards Must Mirror Across `.cpp`/`.h` Pairs

When a Unreal Engine plugin conditionally includes a header using `#if __has_include(...)` in a `.cpp` file, the corresponding `.h` must carry the same guard — or the forward-declaration in the header will be compiled unconditionally while the implementation in the `.cpp` will be compiled only when the include is present.

**Failure shape:** the `.h` declares a function unconditionally; the `.cpp` implements it only under `__has_include`. On a machine where the include is absent, the linker sees the declaration but no definition — link error.

**Rule:** for every `#if __has_include(<SomeHeader.h>)` block in a `.cpp`, grep the sibling `.h` for the same guard. If the header declares anything that depends on `SomeHeader.h` being present, the declaration must also be wrapped in the same `#if __has_include(...)` guard.

```cpp
// MyPlugin.h — WRONG: unconditional declaration
void DoThingRequiringSomeHeader();

// MyPlugin.h — CORRECT: mirrored guard
#if __has_include("SomeHeader.h")
void DoThingRequiringSomeHeader();
#endif
```

**When reviewing plugin PRs:** add this to the review checklist for any PR that introduces a conditional include in a `.cpp`. The compiler won't catch the asymmetry until link time on a configuration that lacks the optional include.

**Empirical source:** `tasks/lessons.md:195`, 2026-04-28.
