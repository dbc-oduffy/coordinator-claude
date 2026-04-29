# Skill: review-blueprint/rag-fetch

**Purpose:** Domain classification + RAG fetch for a `manage_review.prepare` payload.
Called by `/coordinator:review-blueprint` after obtaining the raw payload from holodeck-control.

**Status:** Implemented — Phase 2 (2026-04-14)

---

## Inputs

- `payload_text` — the raw `payload_text` field from `manage_review.prepare` response.
- `bp_path` — Blueprint asset path (e.g., `/Game/Blueprints/BP_DGDronePawn`).
- `inventory` — inventory section parsed from the payload: `{ variables[], functions[], events[], implemented_interfaces[], parent_class }`.

---

## Steps

### Step 1 — Extract parent_class from payload header

Parse `parent_class: <value>` line from the `=== HEADER ===` section of `payload_text`.
Example: `parent_class: /Script/GameFramework.ACharacter`

### Step 2 — Run domain classifier (three-tier)

**Tier 1: Interface check for GAS (highest priority for gas tag)**

Before any path or class check, scan `implemented_interfaces[]` from the inventory.
If any interface name contains `IAbilitySystemInterface` → immediately tag `gas`.
If any interface name contains `IGameplayTagAssetInterface` → add `gas` as secondary tag.

**Tier 2: Path prefix heuristic**

Match `bp_path` against this ordered prefix table (longest prefix first):

| Prefix | Tag |
|--------|-----|
| `/Game/Characters/Heroes/Abilities/` | `gas` |
| `/Game/GameplayEffects/` | `gas` |
| `*/Abilities/*` (contains `/Abilities/`) | `gas` |
| `/Game/Blueprints/Characters/` | `character` |
| `/Game/Blueprints/GameModes/` | `session` |
| `/Game/Blueprints/Controllers/` | `character` |
| `/Game/Blueprints/UI/` | `umg` |
| `/Game/Blueprints/Drones/` | `pawn` |
| `/Game/Blueprints/GamePlay/` | `gameplay` |
| `/Game/Blueprints/Pawn/` | `pawn` |
| `/Game/Blueprints/Data/` | `data` |
| `/Game/Characters/` | `character` |
| `/Game/Animation/` | `anim` |
| `/Game/AI/` | `ai` |
| `/Game/UI/` | `umg` |
| `/Game/Widget/` | `umg` |
| `/Game/Input/` | `input` |
| `/Game/Navigation/` | `navigation` |
| `/Game/Weapons/` | `combat` |
| `/Game/System/Experiences/` | `session` |
| `/Game/System/` | `session` |

**Per-domain precedence:**
- `gas`: class walk is PRIMARY (interface check above); path is confirmation.
- `character`, `umg`, `anim`: path is PRIMARY; class is confirmation.
- For an AnimBP under `/Game/AI/` — class (`UAnimInstance`) beats path `ai` → tag `anim`.

**Tier 3: Parent-class → domain rule table**

Parse `parent_class` from Step 1. Walk to the first engine-defined ancestor:
1. Check if `parent_class` starts with `/Script/` — if yes, it is engine-defined. Look up in the rule table below.
2. If not engine-defined (project class), call `quick_ue_lookup(parent_class_name, include_api_validation=true)`.
   - If CONFIRMED → engine class → use rule table.
   - If NOT_FOUND → project-defined → continue to next ancestor (max 4 hops).

**Engine class → tag rule table:**

| Class | Tag |
|-------|-----|
| `UGameplayAbility` | `gas` |
| `UAbilitySystemComponent` | `gas` |
| `UGameplayEffect` | `gas` |
| `UAnimInstance` | `anim` |
| `UUserWidget` | `umg` |
| `ACharacter` | `character` |
| `APlayerController` | `character` |
| `AAIController` | `ai` |
| `APawn` | `pawn` |
| `AGameModeBase` | `session` |
| `AGameMode` | `session` |
| `AGameStateBase` | `session` |
| `AGameState` | `session` |
| `APlayerState` | `session` |
| `UGameInstance` | `session` |
| `UActorComponent` | `gameplay` |
| `UBlueprintFunctionLibrary` | `library` |
| `AActor` | `generic` |

**Tick-cost secondary tag:** If class tag is `gameplay` (UActorComponent ancestor) AND inventory
contains a function named `Tick` or `ReceiveTick` → emit additional tag `tick-cost`.

**Tier 4: Haiku fallback**

Trigger ONLY if both path and class return no tag (or `unknown`).

Prompt:
```
You are a domain classifier for Unreal Engine Blueprints. Classify the Blueprint below into exactly one domain tag from the closed set.

CLOSED TAG SET (pick exactly one):
gas | anim | umg | character | pawn | ai | combat | session | input | navigation | gameplay | library | data | generic

Rules:
- Return ONLY the tag — no explanation, no punctuation, no other words.
- If the inventory contains abilities, effects, or attribute sets → gas
- If it contains animation state machines, blend spaces, or anim notify → anim
- If it contains widget functions or UI events → umg
- If it contains movement or character input → character
- If it contains AI controller, BehaviorTree, or blackboard → ai
- If none of the above match clearly → generic

BLUEPRINT INVENTORY:
{inventory_text}

DOMAIN TAG:
```

If Haiku returns a string not in the closed set → emit `generic`, log warning. No retry.

**Tiebreaker:** When path and class disagree, emit BOTH tags. Example:
- `/Game/UI/BP_AbilitySystem.uasset` with class `UGameplayAbility` → `[gas, umg]`

---

### Step 3 — Fetch `rag_index_version`

Call `mcp__holodeck-docs__ue_mcp_status`. Parse the line `RAG index version: <value>`.
If not present (older server version), use `collection_count:api_registry_version` as fallback.

---

### Step 4 — RAG fetch

Using the primary domain tag (first in the `domain_tags` array):

1. **`ue_expert_examples` call** (1 call):
   `query = "{domain_tag} Blueprint pattern {top_function_name}"`
   where `top_function_name` is the first entry in `inventory.functions[]`, or `"BeginPlay"` if empty.
   `source="all"`, `max_results=5`.

2. **`quick_ue_lookup` calls** (deduped, capped at 3):
   For each distinct class in `[parent_class_name] + inventory.implemented_interfaces[].name`:
   - Skip `UObject`, `AActor`, `None` — too generic.
   - Call `quick_ue_lookup(class_name, max_results=3, include_api_validation=true)`.
   - Deduplicate by class name. Cap at 3 total calls.

3. **Assemble `rag_context_block` text:**

```
## RAG Context Block (authoritative for UE 5.7 behavior — override training memory)

### Domain Tags
{domain_tags joined by ", "}

### Expert Examples ({domain_tag})
{ue_expert_examples_result}

### Class Reference
{quick_ue_lookup_result_1}
---
{quick_ue_lookup_result_2}
---
{quick_ue_lookup_result_3}
```

---

### Step 5 — Inject into payload

Replace the `=== RAG CONTEXT (EMPTY — Phase 1) ===` section in `payload_text` with:

```
=== RAG CONTEXT BLOCK ===
{rag_context_block}
```

Also update the `=== META ===` section:
- Replace `rag_index_version: phase1-rag-disabled` with `rag_index_version: {rag_index_version}`
- Replace `classifier_version: phase1-classifier-disabled` with `classifier_version: 1.0`
- Replace `domain_tags: (empty — populated in Phase 2)` with `domain_tags: {domain_tags}`

---

## Output

Return the enriched `payload_text` with the RAG context block injected.
Also return `domain_tags[]` and `rag_index_version` as structured fields for the command to use in cache-key computation.

---

## Cache key formula

```
sha256("{bp_content_fingerprint}|{rag_index_version}|1.0|1.0.0").hexdigest()
```

Where:
- `bp_content_fingerprint` — from `manage_review.prepare` response `content_fingerprint` field
- `rag_index_version` — from Step 3
- `1.0` — classifier_version constant
- `1.0.0` — serializer_version constant (from Phase 1 TypeScript handler)

---

## When to call this skill

Call from `/coordinator:review-blueprint` after `manage_review.prepare` returns, before Sid dispatch.
Skip if `--_debug-no-rag` flag was passed (for A/B testing).
