---
title: DOM-Scraping Contract Discipline
status: active
kind: doctrine-wiki
created: 2026-06-21
provenance: state/coordinator-improvement-queue.md L61 (2026-06-08)
---

# DOM-Scraping Contract Discipline

Plan-authoring gate for any plan that introduces or modifies a DOM-scraping contract (CSS selectors, XPath expressions, structural assertions against live HTML). Single-source selector validation misses per-account and per-locale UI variations, producing contracts that are correct for one session and silently broken for another.

## Rule — Validate Against ≥2 Distinct Sources Before Locking a Selector

**A DOM-scraping selector contract must be validated against ≥2 distinct sources (different accounts, locales, or browser profiles) before being locked in a plan or implementation.**

How to apply:
- At plan-authoring time, name at least two distinct validation sources in the plan's substrate-verification section (e.g. `account-A / en-US`, `account-B / fr-FR`). A plan with a single named source is incomplete; mark the gate `INCOMPLETE` until the second source is verified.
- Treat structural variation across sources as a contract signal, not a test flake. If a selector resolves on source A but not source B, the selector is over-fitted — widen it or add a fallback selector before locking.
- AI-generated summary elements and multilingual UI decoys are a recurring false-positive class: selectors targeting structural position (`.summary-box:nth-child(2)`) are more fragile than selectors targeting semantic attributes (`[data-testid="result-item"]` or `aria-label`). Prefer semantic anchors.
- Include the two-source validation evidence in the plan (screenshot path, selector + `.textContent` output, or inline HTML snippet). Evidence is what distinguishes a locked contract from an informal guess.

Empirical source: a example-stats-repo scraping plan validated a selector against a single en-GB account and missed a multilingual AI-summary decoy element present in fr-FR locales; the selector silently matched the wrong element in production. (case: example-stats-repo DOM scraping, queue L61, 2026-06-08)

## When to invoke

- Writing any plan section that introduces a DOM selector, XPath expression, or structural HTML assertion.
- Reviewing a plan or implementation PR whose diff adds or modifies a scraping contract.
- Authoring a test fixture that pins HTML structure — the ≥2-source requirement applies to fixture capture as well.

## Related

- [`writing-plans.md`](writing-plans.md) — pre-dispatch verification discipline and the substrate-citation requirement for plans.
- [`test-design-discipline.md`](test-design-discipline.md) — avoiding vacuous-pass test shapes; the per-locale variant is a vacuous-pass risk when a single fixture covers only one UI state.
