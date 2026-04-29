---
confidence: medium
status: ready
---

# Widget Loader Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use /execute-plan to implement this plan task-by-task.

**Goal:** Add a UUserWidget-based loader overlay to the main HUD.

**Status:** Pending review
**Confidence:** Medium — key files read, class hierarchy confirmed, tag table location verified

**Architecture:** Extend UHUDBase's widget stack with a new ULoaderWidget; show/hide via a GameplayTag GE.Loader.Show bound in the HUD's BeginPlay.

**Tech Stack:** Unreal Engine 5.7, UMG, GameplayTags

---

## Verified Facts

- [x] `UHUDBase` exists at `Source/UI/HUD/HUDBase.h:14` — has `TArray<UUserWidget*> WidgetStack`.
- [x] Tag `GE.Loader.Show` not yet registered — `Config/DefaultGameplayTags.ini` confirmed.
- [~~x~~] No existing loader widget found — must create from scratch.

## Assumptions

- [ ] UE 5.7 remains the target version through H1 (no engine upgrade mid-sprint).

## Open Questions (Blocking)

*(None — all resolved in enrichment.)*

## Open Questions (Non-blocking)

- [ ] Loader animation (fade-in vs instant) — decide before Phase 2; does not block Phase 1.

## Risks

- **Risk — UMG widget creation on GameThread:** [Context: UUserWidget::CreateWidget must be called on the game thread] → [Failure: ensure call only from BeginPlay or a GameThread delegate, not an async callback] → [Detection: add a check(IsInGameThread()) assertion in LoaderWidget::Init]

## Non-Goals

- No server-side replication of loader state — client-only overlay.

## Execution Phases

### Phase 1 — Create loader widget class

**Files:**
- Create: `Source/UI/Widgets/LoaderWidget.h`
- Create: `Source/UI/Widgets/LoaderWidget.cpp`

**Steps:**

- [ ] Write failing test for widget creation
- [ ] Implement ULoaderWidget class
- [ ] Run tests
- [ ] Commit

**Gate: PM/EM approval before Phase 2.**
