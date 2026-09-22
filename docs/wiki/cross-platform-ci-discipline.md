# Cross-Platform Validation Discipline


**Purpose.** A repo that declares cross-platform support must measure it — validating on only the developer's OS is optimism, not measurement. This fleet runs **no CI** (GitHub Actions is retired); measurement is local: the fast test tier on the operator's own Windows, macOS, and Linux boxes. This wiki codifies how to mark tests that can't be fixed from this repo, and how to skip hardware-gated tests with an honest contract signal rather than a silent pass. It is the measurement arm of `install-surface-completeness.md` — that wiki says what "works on every machine" means; this one says how to prove it.

(The filename keeps its historical `ci` stem so existing citations resolve.)

See also: `cross-platform-shell-portability.md` — the *code* portability discipline (bash version, BSD coreutils, CRLF). This wiki is the paired *measurement* discipline.

---

## Principle (language-agnostic)

**Green on your dev OS is not green on the others.**

A validation run on one OS gives a false pass signal for every OS-specific failure invisible there. This is a measurement problem, not a language or tooling problem — it affects TypeScript, Rust, C++, Python, and anything else that runs on more than one platform.

**Three obligations when you declare cross-platform support:**

1. **Run the fast tier on every supported OS before merging changes that touch OS-sensitive surfaces** (shell, paths, subprocess, install, hooks). The operator's own boxes are the lanes; a missing run is a missing measurement, and a missing measurement is not a green signal. Say which OSes a change was and was not run on.

2. **Mark cross-repo-blocked tests honestly.** When a test fails because the fix belongs in a sibling repo, deselect it with a named marker that names the sibling and the tracking memo. Do not silently skip it, do not force-pass it, and do not `xfail` it — `xfail` absorbs test-infrastructure exceptions silently (`test-design-discipline.md` §25) and gives no `xpass` tripwire. The deselect is *temporary and memo-bound*, not a permanent escape hatch.

3. **Mark hardware-gated tests with a skip-with-explanation.** A test that requires a GPU or a real hardware sidecar must skip on a box that lacks the hardware with a clear reason string — not a silent pass. Per `test-environment-discipline.md` §3: a skip-with-explanation is a contract signal; a silent pass on a hardware-less box is a contract violation.

**Empirical basis.** project-rag's `macos-first-class-test-parity` spinoff surfaced 71 `tests/install/` failures on macOS that were invisible under a Windows+Linux-only run — despite the repo's own doctrine declaring macOS first-class. "Green on your dev OS" was the intuition; no measurement existed to catch it.

---

## The two marking primitives

### 1. `cross_repo_fix_locus` deselection

When a test fails in this repo because the fix belongs in a sibling repo, deselect it on the affected OS using the `cross_repo_fix_locus` marker. The local green excludes exactly the tests that cannot be fixed from this repo, tracked via a cross-repo memo rather than silently passing or silently skipping.

**All three closure requirements MUST be met, or the primitive rots into the green-by-deselect dishonesty it exists to prevent.**

**(a) Self-documenting reason string.** The marker's `reason=` names both the sibling repo and the tracking memo:

```python
@pytest.mark.cross_repo_fix_locus(
    reason="fix lives in project-rag; tracked in cross-repo/inbox/2026-06-24-macos-first-class-test-parity.md"
)
```

The reason string IS the staleness check. A reason with no memo is untrackable — you cannot tell when the sibling landed the fix, and the deselect silently outlives its cause.

**(b) Deselection is temporary.** When the sibling lands its fix and it propagates here, the responsible party MUST remove the marker from every test it deselected and verify those tests go green on the previously-affected OS. A deselect that outlives its memo is a silently-absent decorative test with no `xpass` tripwire.

**(c) Not a substitute for the prerequisite-absent rule.** `cross_repo_fix_locus` applies **only** when no configuration in *this* repo can make the test pass. If the prerequisite could be installed here (an addon, a sidecar, an env var), `cross-repo-contract-test-discipline.md` applies instead — declare the run that provides it, require the test to pass there, and treat skipping as failure. Do not use the marker to avoid setting up a run that COULD pass from here.

### 2. Hardware-gated tests — coverage-equivalence

Some tests need hardware (a GPU, a real network sidecar, a specific device) that not every box has. On a box that lacks it, these tests MUST skip with a named marker and a clear reason — not silently pass, and not hang. Skipping `real_spawn` on a CPU-only box yields the same coverage as every other CPU-only box; nothing is hidden, and the skip is visible in the run output.

A silent pass achieved by forcing the environment into a degraded state (e.g. `EMBED_DEVICE=cpu` unconditionally) hides production-shape regressions. **Never use `xfail` for hardware-gated skips**; a named marker with a reason string is the load-bearing form (`xfail(strict=True)` if you must).

---

## Reference implementation (pytest)

Register both markers, then deselect by expression when running on the affected box:

```python
# conftest.py
def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "cross_repo_fix_locus(reason): fix locus lives in a sibling repo; deselected on the "
        "affected OS until the sibling lands and propagates. Temporary and memo-bound.",
    )
    config.addinivalue_line(
        "markers",
        "hardware_gated(reason): requires hardware absent on this box (GPU, real sidecar). "
        "Skips with explanation. Use your project's own hardware-gate marker names.",
    )
```

```bash
# on the box where the sibling-owned failure reproduces
pytest -m "not cross_repo_fix_locus and not hardware_gated" tests/
```

`real_spawn` and `requires_real_sidecar` are project-rag's own hardware-gate names — examples of the class. Define names that describe your constraints; `cross_repo_fix_locus` is the coordinator-standard name and is used verbatim across projects. Adapt to your test runner; the principle governs.

---

## A sibling's fix recommendation, reproduced on THEIR platform, may regress yours

A cross-repo finding that ships a "here's the fix" recommendation is verified on the *reporter's* platform. Before adopting it, reproduce the **original failure on your own platform** — the same code can fail in **opposite directions** across OSes, and applying the sibling's fix blind regresses your box.

**Empirical basis (example-game-repo live-bringup):** a finding traced CodeRankEmbed's offline load failing by bare repo-id and recommended "always resolve to the local snapshot path instead." It reproduced on the reporter's Windows/CUDA box. On macOS the **opposite** held: repo-id load *succeeds* and the raw snapshot path *fails* — `snapshots/<rev>` breaks `trust_remote_code` dynamic-module resolution through the HF cache's `blobs/` symlinks. Adopting the Windows fix unverified would have broken the Mac. A sibling-supplied fix is a hypothesis to reproduce per-platform, not a patch to apply.

## An unsupported or unmeasured host must not gate a measured one

Three failures of evidence-handling recur here, all one shape: a number or a verdict is treated as
authoritative when its **method** does not support the claim being decided. Each produces a
genuinely correct answer about the thing it measured, and silently wrong about the thing being
decided — nothing looks red, so the wrong scope propagates to everything downstream.

- **A dead host's RED is not a verdict.** Treating an unsupported host (one this project has
  explicitly declined to support, e.g. a legacy shell version whose own dependencies fail to
  load) as though it were a live gate lets a dead host block a working leg — a dual-host policy
  gate going RED on the unsupported host alone, and skipping emission entirely, though the
  supported host is healthy and would have passed. Don't spend effort making an out-of-scope host
  pass, don't treat its failure as a release blocker, and challenge any gate that requires an
  unsupported host to be healthy first.
- **An absent host's silence is not a verdict either.** Where a decision wants a cross-platform
  measurement and one of the declared-support platforms has no available hardware to measure on,
  do not park the decision waiting for that hardware. A multi-platform acceptance bar is the right
  standard for a fleet-wide *claim* and the wrong bar for what ships on the platform that **is**
  measured — act on the measured platform's answer and record the others as open, not as a gate.
  Guard the inverse error too: a one-platform measurement is never itself a fleet-wide verdict.
- **A prose sweep is a floor, not a count.** A hand-evaluated grep-style sweep over a surface
  systematically undercounts — it finds what *announces* itself (an explicit conditional, a
  self-labelled checkpoint) and misses conditions that read as ordinary prose (set-arithmetic
  comparisons, typed-field reads) even though they are the majority and the ones a classified,
  per-item audit would catch. A sweep-derived number quoted as "the count" can undercount a
  classified audit's number by several-fold on the same surface. Treat a sweep as a lower bound
  and run a classified, per-item audit on at least one representative surface before trusting scope
  derived from a sweep.

**The rule.** Name the method beside every number, and check the method actually covers the claim
being decided. Where the failing host is genuinely out of declared scope, say so and unblock; where
the missing host is merely absent, ship the measured leg and record the rest as open. Treat a sweep
count as a floor, never a ceiling.

## Cross-references

- `install-surface-completeness.md` — the broader "build for someone else's machine" doctrine.
- `cross-platform-shell-portability.md` — the code discipline; its support matrix is the authority for which OSes must be measured.
- `test-environment-discipline.md` §3 — skip-with-explanation vocabulary.
- `test-design-discipline.md` §25 — why named markers beat `xfail`.
- `cross-repo-contract-test-discipline.md` — in any configuration that CAN provide the prerequisite, skipping is failure.
