# Widget Loader Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use /execute-plan to implement this plan task-by-task.

**Goal:** Add a UUserWidget-based loader overlay to the main HUD.

**Status:** Pending review

**Architecture:** Create a new UWidgetBlueprint-backed loader class, add it to the HUD's widget stack on begin-play, show/hide via a GameplayTag event.

**Tech Stack:** Unreal Engine 5.7, UMG, GameplayTags

---

## Assumptions

- [ ] UHUDBase class exists and has a widget stack we can extend.
- [ ] GameplayTag GE.Loader.Show is not yet registered — we need to add it.
- [ ] No existing loader widget — must be created from scratch.

## Open Questions (Blocking)

- [ ] What is the exact header path for UHUDBase? Scout has not confirmed.
- [ ] Does the project use a shared tag table or per-module tag declaration?

## Open Questions (Non-blocking)

- [ ] Should the loader animate in, or appear instantly? Decide before Phase 2.

## Execution Phases

### Phase 1 — Create loader widget class

- [ ] Create `Source/UI/Widgets/LoaderWidget.h` and `.cpp`
- [ ] Commit

**Gate: PM/EM approval before Phase 2.**
