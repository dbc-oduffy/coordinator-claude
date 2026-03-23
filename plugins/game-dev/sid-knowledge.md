# Sid's Production Knowledge Base
## Staff-Level UE5 Insights — Read at Session Start

> This file is read by Sid at session start to pre-arm with production-grade knowledge
> that is not reliably present in any LLM's training data. It covers the gap between
> "tutorial-grade" UE development (what blogs and courses teach) and "production-grade"
> UE development (what teams learn after shipping titles and debugging real failures).
>
> Not a reference manual — use MCP tools for API signatures. This is the war-stories layer.
> Stable across UE 5.x releases; revisit for major architectural changes only.

---

## The Fundamental Divide

Every piece of advice in this file falls on one side of the same divide:

**Tutorial-grade:** Code that works in a single-player PIE session with one actor and no
streaming. Simple, obvious, and wrong at scale.

**Production-grade:** Code that handles authority, streaming, respawn, GC timing,
initialization ordering, and multiplayer. Less obvious, more opinionated, and the only
thing that ships.

When reviewing or generating code, always ask: *"Will this still work when there are
200 actors, three streaming levels, lag compensation, and server-authoritative state?"*
If the answer is "I don't know," it is not production-grade.

---

## Actor Lifecycle

### The Strict Order

```
Constructor (CDO, no world)
  → PostInitProperties
  → PostActorCreated / PostLoad (spawned vs. loaded from disk — different paths!)
  → OnConstruction (runs in editor too — be careful)
  → PreInitializeComponents
  → InitializeComponent (per component)
  → PostInitializeComponents (components registered, delegate-safe)
  → BeginPlay (world exists, gameplay safe)
  → Tick (per frame)
  → EndPlay (removal)
  → BeginDestroy (GC, later)
```

### The CDO Trap (burns everyone once)

The constructor runs to create the **Class Default Object** — a template instance with no
world, no game state, nothing. It runs at class registration before any level exists.

**Never in a constructor:**
- `GetWorld()` — returns null
- `SpawnActor()` — no world to spawn into
- `FindActor()` / `GetAllActorsOfClass()` — no world
- Subsystem access
- Gameplay logic of any kind

**Constructor is only for:** `CreateDefaultSubobject<T>()` and setting default property values.

Move everything else to `BeginPlay()`. This is non-negotiable.

### Editor-placed vs. Dynamically Spawned (the initialization path split)

This is the root cause of the "works in PIE, breaks in packaged build" class of bugs:

- **Editor-placed actors:** Constructor runs at level load. `BeginPlay` runs at level
  initialization or streaming completion. There can be a multi-frame (or multi-second)
  gap between them.
- **Dynamically spawned actors:** Entire sequence runs during `SpawnActor()` within a
  single frame.

**Production trap:** Initialization logic written for "spawned" that assumes components
are ready immediately breaks for "placed" actors because BeginPlay is deferred. And
vice versa — code written for "placed" that assumes slow initialization breaks when
spun up by a runtime system.

**Rule:** Never write initialization logic that assumes *only one* creation path. Use
lifecycle stage guarantees, not "this worked when I tested it."

### Streaming adds another wrinkle

Actors in streaming levels get `BeginPlay` called when their sub-level streams in, which
can happen after other actors in the persistent level are already deep into gameplay.
References to "the player" or "the game mode" grabbed in `BeginPlay` may be valid —
or may not exist yet. Always defend these references.

---

## Tick Discipline

### The Cardinal Rule

**If it does not need to run every frame, it must not be in Tick.**

A 60fps game gives you 16.67ms per frame. Tick is not "runs a lot" — it is "runs every
single frame, unconditionally, for every registered actor." 200 actors with even a
trivial Tick each adds up to a frame budget catastrophe at scale.

### The Decision Tree

```
Does this logic need per-frame integration? (smooth movement, real-time interpolation)
  → YES: Tick is correct.
  → NO ↓

Does it need to fire when something changes?
  → YES: Delegate / event. Fire once on change, not every frame to check for change.

Does it need to fire on a schedule?
  → YES: FTimerManager. SetTimer() with the interval you actually need.

Is it proximity / overlap detection?
  → YES: Collision overlap events (OnComponentBeginOverlap). Not distance checks in Tick.

Is it UI state?
  → YES: Bind to a delegate that fires when data changes. Never poll in Tick for UI.
```

### Timers Are Not "Free Tick"

A common misunderstanding: replacing `Tick` with a 0.1s timer and calling it "optimized."
This is better, but timers are not free:
- Managed by `FTimerManager` on the Game Instance / World
- Calling `SetTimer` repeatedly creates new handles; always clear before re-setting
- `FTimerManager` is **not thread-safe** — timer callbacks are on the game thread only
- Timers tied to an object are auto-canceled on destruction (good), but only if bound
  with a `TWeakObjectPtr` or `UObject*` — raw function pointers will not be canceled

### Disabling Tick Selectively

Enable/disable Tick dynamically rather than leaving dead Tick functions:
```cpp
SetActorTickEnabled(false);  // Turn off when dormant
PrimaryActorTick.bStartWithTickEnabled = false;  // Default to off in constructor
```

---

## Blueprint / C++ Boundary

### The Hybrid Model (not optional)

Blueprint is not a toy. C++ is not the only real code. The correct mental model:
- **C++:** Core systems, performance-critical loops, replication logic, framework base classes
- **Blueprint:** Designer-facing behavior, per-asset customization, VFX/audio hooks,
  rapid-iteration logic, level scripting

This is not about aesthetics. Blueprint VM runs ~10x slower than native C++ for
compute-bound work. But Blueprint is dramatically faster to iterate on, and forcing
designers through C++ compilation loops has a real production cost.

### Blueprint VM Cost — The Actual Numbers

Each Blueprint node call incurs:
- ~1–5µs VM dispatch overhead
- UObject property reflection for function calls
- GC pressure from temporary FString/TArray allocations

**Fine:** A few Blueprint nodes handling an overlap event. Rare, low-frequency, designer logic.

**Not fine:** A Blueprint ForEachLoop over 500 actors running on Tick. This is a
frame-budget catastrophe masquerading as "it works in PIE."

### The Boundary Interface Pattern

Design the C++/Blueprint interface deliberately:
- `BlueprintCallable`: Blueprint → C++ (expose coarse operations, not fine-grained ones)
- `BlueprintImplementableEvent`: C++ → Blueprint (override points for designers)
- `BlueprintNativeEvent`: C++ default + Blueprint override (best of both for optional customization)
- `BlueprintAssignable` delegates: events Blueprint can subscribe to

**Anti-pattern:** Exposing every internal C++ function as `BlueprintCallable`. The
boundary surface area is the coupling surface. Keep it minimal and intentional.

**Anti-pattern:** Exposing fine-grained operations (`GetPosition`, `CalculateDistance`,
`CompareValue` as three separate Blueprint nodes) when a single coarse operation
(`FindNearestEnemyInRange`) would do all three with one VM dispatch.

### GetAllActorsOfClass Is a Red Flag

`GetAllActorsOfClass` iterates every actor in the level. Called from Blueprint on Tick:
catastrophic. Called once in BeginPlay and cached: acceptable. Called at all when a
subsystem or delegate could route the information: probably unnecessary.

Cache component and actor references in `BeginPlay`. Never re-fetch them per frame.

---

## Memory Management & Garbage Collection

### Two Memory Worlds

UE5 has two completely separate memory management systems that beginners conflate:

1. **UObject world (A/U prefix classes):** Garbage collected. GC runs ~every 60 seconds
   or on memory pressure. Reachability-based: objects reachable from GC roots survive.

2. **Plain C++ world (F prefix structs):** Manual or UE smart pointers. No GC.
   `TSharedPtr<T>`, `TUniquePtr<T>`, `TSharedRef<T>`.

Getting these confused causes either crashes or memory leaks.

### The Raw Pointer Trap (most common GC crash)

```cpp
UMyComponent* CachedComponent;  // RAW POINTER — invisible to GC
```

The GC **does not see raw pointers**. If nothing else holds a strong reference,
`CachedComponent` may be collected. Your pointer now points to freed memory. Crash.

**Fix:** Any UObject pointer stored as a member must be in a `UPROPERTY()`:
```cpp
UPROPERTY()
UMyComponent* CachedComponent;  // GC sees this, won't collect while this object lives
```

### Strong vs. Weak References

| Pattern | Prevents GC? | Use When |
|---------|:---:|--------|
| `UPROPERTY()` raw pointer | YES | You own this object or must keep it alive |
| `TWeakObjectPtr<T>` | NO | Cross-system reference; object may be destroyed externally |
| `TObjectPtr<T>` | YES | Modern UPROPERTY replacement (UE5+), lazy-loads |

**Use `TWeakObjectPtr`** for non-owning cross-system references. Before dereferencing:
```cpp
if (WeakRef.IsValid()) { WeakRef->DoThing(); }
```

### `IsValid()` vs `nullptr` Check

This is a subtle but critical distinction:

- `ptr != nullptr` — checks if the C++ pointer is null. Does NOT detect "pending kill" UObjects.
- `IsValid(ptr)` — checks both null AND whether the UObject has been marked for GC.
  An actor that has had `DestroyActor()` called on it is **pending kill** — its pointer
  is not null, but it is logically dead. `IsValid()` returns false. `!= nullptr` returns true.

**Always use `IsValid()`** for UObject pointers in gameplay code.

### The DestroyActor Timing Gap

`DestroyActor()` removes an actor from the world immediately but does **not** free its
memory until the next GC cycle (up to 60 seconds later). During this window:
- The pointer is not null
- `IsValid()` returns false (the right thing to check)
- Code that only checks `!= nullptr` will proceed to use a pending-kill object → crash

For high-churn scenarios (projectiles, pooled actors), consider **object pooling**
rather than repeated spawn/destroy cycles to avoid GC pressure spikes.

---

## Gameplay Ability System (GAS)

### What GAS Actually Is

GAS is not a fancy ability framework. It is a **contract-driven, state-replicating
runtime** that handles ability activation, cooldowns, attribute management, gameplay
effects, tags, and multiplayer prediction as an integrated system.

The production divide: **scripting surface** (tutorial) vs. **state-replicating contract** (production).

### Ownership: Where to Put the ASC

`UAbilitySystemComponent` goes on **one** of two places:
- **The Pawn** — correct when abilities are tied to the body; ASC destroyed on death
- **The PlayerState** — correct when abilities/loadouts survive respawn; ASC persists

This is an early architecture decision with significant replication implications.
Changing it mid-project is painful. For games with respawn and loadout persistence:
PlayerState. For games where the character dies completely: Pawn.

### The Activation Trap

AI and code generators routinely call abilities directly. This bypasses GAS entirely:

```cpp
// WRONG — bypasses GAS replication, prediction, cooldowns
GetAbility()->ActivateAbility(...);

// RIGHT — goes through the replication contract
AbilitySystemComponent->TryActivateAbility(AbilitySpec.Handle);
```

Abilities activated directly work in single-player. They silently fail to replicate
in multiplayer with no error message. This is the "AI generates single-player code"
failure mode applied to GAS.

### Event-Driven Activation

Hard-coding ability activations in Blueprint (press button → call ability class directly)
is tutorial-grade. Production pattern: systems send **gameplay events** with tags,
abilities respond to those tags. This decouples systems:

```cpp
// Producer: just fires the event
AbilitySystemComponent->HandleGameplayEvent(EventTag, &EventData);

// Consumer: the ability responds to its trigger tag
// No direct reference between trigger and ability
```

### Attributes Belong to Gameplay Effects

Modifying attributes directly is tutorial-grade. Production: all attribute changes go
through `UGameplayEffect`. This is how GAS:
- Tracks what changed attributes and why (for UI, logging, rollback)
- Handles stacking, duration, and magnitude curves
- Replicates correctly to clients

Bypassing Gameplay Effects for "simple" attribute changes creates a class of silent
replication bugs that only surfaces in multiplayer.

---

## Replication

### Six Silent Failure Modes

These six replication mistakes produce no compiler errors, no editor warnings, and
sometimes no runtime logs. They fail silently:

1. **Missing `GetLifetimeReplicatedProps`** — `UPROPERTY(Replicated)` without a
   `DOREPLIFETIME` macro silently does not replicate. No warning.

2. **Wrong authority for logic** — Clients executing logic that should only run on
   the server. Common with AI-generated code. Check `HasAuthority()`.

3. **Spawning replicated actors on clients** — Creates local ghost actors not known
   to the server. Only the server should spawn replicated actors.

4. **Naive array replication** — `TArray<T>` with `UPROPERTY(Replicated)` sends the
   entire array on any change. Use `FFastArraySerializer` for large arrays.

5. **Reliable RPCs for high-frequency events** — The reliable RPC buffer is finite.
   Flooding it with Reliable calls for every tick causes buffer overflow → disconnect.
   High-frequency events: Unreliable. Important one-shot events: Reliable.

6. **Missing `HasAuthority()` checks on server logic** — Client instances will run
   code they should not. Always gate server-only logic.

### Ownership Is Not Intuitive

Server RPCs require the calling **client to own the actor** the RPC is called on.
If a client calls `Server_DoThing()` on an actor it does not own: **silent drop**.
No error. No warning. The RPC never executes.

PlayerControllers automatically own their Pawns. For world objects (doors, pickups):
the client does not own them. Route through the PlayerController (which the client
does own) instead of calling an RPC directly on the world object.

### State Replication Over RPC

The general principle: prefer **replicated state** (UPROPERTY Replicated) over RPCs for
outcomes that all clients need to know. RPCs are for commands (client → server request)
and events (server → specific client notification). Replicated properties are for
**world state** visible to all.

An outcome that should be visible to all players (door opens, player takes damage,
enemy dies) should be driven by a replicated property change + `OnRep_` callback,
not by a multicast RPC. Multicast RPCs have ordering and reliability complexities;
replicated state is authoritative.

---

## Performance

### Measure Before Touching Anything

This is non-negotiable. Optimizing without measurement is guessing. The engine has
three parallel threads; your bottleneck is exactly one of them:

```
stat unit  →  shows Frame / Game / Draw / GPU times
```

- **Game Thread bound:** Gameplay code, AI, physics, Blueprint VM, Tick overhead
- **Render Thread bound:** Too many draw calls, complex scene traversal
- **GPU bound:** Fill rate, shader complexity, overdraw, resolution

**Profile in Test builds, not Development, not Editor.** Editor adds Slate rendering
overhead every frame. Development builds add draw thread noise. You get misleading
data and optimize the wrong thing.

### The CPU/GPU Confusion Diagnostic

When you suspect GPU is the bottleneck, run this test first:
```
r.ScreenPercentage 50
```

Half the render resolution. If BasePass time **drops dramatically** → fill-rate bound
(shader cost, overdraw, resolution). If it barely changes → **draw-call bound**
(mesh count, batch breaking, material instances).

These two problems require completely different solutions. Merging meshes to reduce
draw calls when you're actually fill-rate bound wastes effort. Reducing material
complexity when you're draw-call bound wastes effort. Run the test.

### Tick Is the First Performance Lever

Before any rendering optimization: `stat game` to see Tick costs. A few heavy Tick
functions routinely dominate game thread time. Migrate polling Tick to event-driven
patterns (see Tick Discipline section). This is usually the highest-ROI optimization.

### GetAllActorsOfClass at Scale

`GetAllActorsOfClass` O(n) across all actors. Called on Tick on 50 actors with 500
total world actors: 25,000 checks per frame. Common in tutorial code. Catastrophic
in production. Alternatives:
- Subsystem that actors register/unregister with at BeginPlay/EndPlay
- GameState list of relevant actors
- Overlap/collision queries scoped to a volume

---

## Architecture Anti-Patterns

### Monolith GameMode / PlayerController

The "tarballing" pattern: GameMode, PlayerController, and Pawn each growing to
thousands of lines of code with every system bolted on. This is the most common
large-project architectural failure mode in UE.

**Fix:** Move server-only logic out of GameMode into **server-only GameState components**.
Data and code stay together; GameMode becomes an orchestrator.

For PlayerController: extract subsystems (`ULocalPlayerSubsystem`) for input handling,
inventory, UI state. PlayerController becomes the authority router, not the logic container.

### Custom Systems for Engine Problems

GAS for abilities. Enhanced Input for input. StateTree or Behavior Trees for AI decisions.
Asset Manager for streaming. Common UI for cross-platform UI stacks.

These are production-tested subsystems from shipped Epic titles. The alternative —
rolling a custom ability system, custom input mapping, custom AI — means reimplementing
years of engine development and missing edge cases the engine already handles. The classic
"but GAS is so complex" objection is often a preference for the familiar over the correct.
GAS complexity is the complexity of the problem space it solves. Custom systems don't
eliminate that complexity; they just hide it until it ships.

### Soft References vs. Hard References

Hard references (`TSoftObjectPtr` vs. direct UPROPERTY reference) affect streaming:
- **Hard reference:** Object is loaded when the referencing object is loaded. Chain of hard
  references in a large project = most of your content loaded at startup.
- **Soft reference (`TSoftObjectPtr`):** Stores a path; load explicitly via Asset Manager
  when needed.

Production projects use soft references for any asset that should be streamed or loaded
on demand. Hard references are for small, always-needed assets. Getting this wrong means
loading everything at startup and blowing your memory budget.

### Editor vs Runtime Code Boundaries

Code that only runs in the editor must be guarded:
```cpp
#if WITH_EDITOR
// Editor-only code here
#endif
```

Editor-only APIs in packaged builds cause linker errors or crashes. Common mistake:
using `FEditorDelegates`, `GEditor`, or `UEditorActorSubsystem` in gameplay code.
Check `#if WITH_EDITOR` requirements before using any editor API.

`OnConstruction` runs in the editor (and in PIE). If it has side effects, those run
at edit time. This is intentional for visual construction scripts but dangerous for
gameplay logic.

---

## The LLM-Specific Failure Mode

> **⚠️ CRITICAL: Your entire UE5 knowledge from training data is unreliable.**
> Not just function names — everything: class hierarchies, parameter signatures, default behaviors,
> deprecation status, system interactions, Blueprint node availability, engine defaults, config
> properties, component relationships. Any of it may be wrong, stale, or hallucinated.
> You have 572K+ indexed doc chunks and 73K verified API declarations via holodeck-docs MCP.
> **Treat MCP tools as ground truth. Treat your training knowledge as unverified hypothesis.**

UE5 knowledge in training data is not merely *underrepresented* — it is **actively wrong**.
The training corpus is saturated with plausible-looking but incorrect UE5 content: tutorials
with outdated APIs, blog posts with wrong signatures, and AI-generated articles that
confidently describe functions that don't exist. This was confirmed empirically: AI-generated
UE5 content has a ~1-in-4 file error rate (see Holodeck RAG Quality Gate findings).

The danger is **misplaced confidence**. The model doesn't flag uncertainty — it presents
wrong UE5 information with the same conviction as correct information. This applies across
the board, not just to API names:

- **Hallucinated APIs** — function names that don't exist, presented confidently
- **Wrong signatures** — close enough to look right, wrong enough to not compile
- **Stale knowledge** — UE4→UE5 migrations renamed/removed many things silently
- **Incorrect default behaviors** — wrong assumptions about how engine systems behave
- **Misunderstood system interactions** — wrong mental models of how subsystems connect
- Generate code that works in PIE single-player and fails silently in multiplayer
- Bypass engine subsystems (GAS, Enhanced Input, Asset Manager) in favor of simpler custom code
- Miss `HasAuthority()` guards
- Use raw pointers instead of UPROPERTY
- Put heavy logic in Tick
- Call `GetAllActorsOfClass` in performance-sensitive paths

**Sid's job is to catch these patterns.** The MCP tools (`quick_ue_lookup`,
`check_ue_patterns`, `ue_expert_examples`) provide verification against authoritative
sources. **Use them before presenting ANY code that calls a UE API.** This document
provides orientation; the MCP tools provide ground truth.
