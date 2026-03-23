---
description: Look up Unreal Engine documentation
allowed-tools: ["Agent", "ToolSearch"]
argument-hint: <query>
---

# /holodeck-docs:lookup

Fetches Unreal Engine documentation, API signatures, and code examples from the holodeck-docs RAG server (572K+ indexed chunks).

## Usage

```
/holodeck-docs:lookup <query>
```

## Routing

- If the query is an exact class or method name (e.g., `AActor`, `SetMovementMode`, `UAbilitySystemComponent::GiveAbility`), call `mcp__holodeck-docs__lookup_ue_class` directly with the class name and optional method.
- If the query is a concept, pattern, or multi-word question, dispatch the `ue-docs-researcher` agent to handle it in context isolation.

## Examples

```
/holodeck-docs:lookup AActor::BeginPlay
/holodeck-docs:lookup Enhanced Input action mappings
/holodeck-docs:lookup GAS cooldown setup
/holodeck-docs:lookup UCharacterMovementComponent
/holodeck-docs:lookup replication best practices
```
