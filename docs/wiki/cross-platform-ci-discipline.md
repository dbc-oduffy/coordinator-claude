# Cross-Platform CI Discipline

<!-- spec-backlink: docs/plans/2026-06-25-cross-platform-ci-standardization.md -->

**Purpose.** Coordinator consumers that declare cross-platform support must measure it — running CI on only the developer's OS is not measurement, it is optimism. This wiki codifies the measurement discipline: how to structure the CI matrix, how to mark tests that can't be fixed from this repo, and how to skip hardware-gated tests with an honest contract signal rather than a silent pass. It is the enforcement arm of the broader doctrine in `install-surface-completeness.md` — that wiki tells you what "works on every machine" means; this one tells you how to prove it in CI.

See also: `cross-platform-shell-portability.md` — the *code* portability discipline (bash version, BSD coreutils, CRLF). This wiki is the paired *CI-measurement* discipline. They are distinct; cross-reference both.

---

## Principle (language-agnostic)

**Green on your dev OS is not green on the others.**

A CI matrix that runs only one OS lane gives a false pass signal for every OS-specific failure that happens to be invisible there. This is not a Python problem, a shell problem, or a GitHub Actions problem — it is a measurement problem, and it affects TypeScript, Rust, C++, Python, and anything else that runs on more than one platform. The primitives in this wiki are framed language-agnostically. The reference implementation section below uses pytest because that is the canonical first consumer, but the principles apply to any test runner.

**Three obligations when you declare cross-platform support:**

1. **Test on every supported OS.** The CI matrix must include a lane for each OS the project declares it supports. A missing lane is a missing measurement; a missing measurement is not a green signal.

2. **Mark cross-repo-blocked tests honestly.** When a test fails because the fix belongs in a sibling repo, deselect it with a named marker that names the sibling and the tracking memo. Do not silently skip it, do not force-pass it, and do not xfail it — `xfail` absorbs test-infrastructure exceptions silently (see `test-design-discipline.md` §25) and gives no `xpass` tripwire. The deselect is *temporary and memo-bound*, not a permanent escape hatch.

3. **Mark hardware-gated tests with a skip-with-explanation.** A test that requires a GPU or a real hardware sidecar must skip on a runner that lacks the hardware with a clear reason string — not a silent pass. Per `test-environment-discipline.md` §3: a skip-with-explanation is a contract signal ("this test was not run on this runner because it requires hardware X"); a silent pass in a CPU-only runner is a contract violation.

**Empirical basis.** project-rag's `macos-first-class-test-parity` spinoff (`docs/plans/2026-06-24-macos-first-class-test-parity.md` in the project-rag repo) surfaced 71 `tests/install/` failures on macOS that were completely invisible under a Windows+Linux-only matrix — despite the repo's own doctrine already declaring macOS first-class. The coordinator had the intuition ("green on your dev OS is not green on the others") but shipped no measurement gate, so the next consumer inherited the gap. This wiki closes that gap.

---

## The three primitives

### 1. macOS lane in the CI matrix

Every cross-platform project must include `macos-latest` in its CI matrix alongside `ubuntu-latest` and `windows-latest`. The canonical form:

```yaml
strategy:
  matrix:
    os: [ubuntu-latest, windows-latest, macos-latest]
```

**Why all three.** The support matrix inherited from `cross-platform-shell-portability.md` is the authority:

| OS | Status |
|---|---|
| macOS | P0 — must work |
| Windows (Git-Bash) | Must work |
| Linux | Likely, untested — keep it working; we don't gate on it |

`cross-platform-shell-portability.md` owns the *code* portability bar (bash version, BSD coreutils, CRLF). The CI matrix is the *measurement* mechanism that proves the code actually clears that bar on each platform. The two wikis are siblings — one specifies the code-authoring constraints, the other enforces them by running CI.

**Marker computation runs in `shell: bash`.** On all three runners — including Windows where git-bash provides bash — the same marker-computation step works identically. Specify `shell: bash` explicitly on the step that computes which markers to deselect; do not rely on the runner's default shell, which is PowerShell on Windows and may differ.

### 2. `cross_repo_fix_locus` deselection primitive

When a test fails in this repo because the fix belongs in a sibling repo, deselect it on the affected OS lane using the `cross_repo_fix_locus` marker. This is the honest-measurement primitive: the in-session green excludes exactly the tests that cannot be fixed from this repo, tracked via a cross-repo memo rather than silently passing or silently skipping.

**All three of the following closure requirements MUST be met. Without them, the primitive rots into the green-by-deselect dishonesty it exists to prevent.**

#### (a) Self-documenting reason string

The marker's `reason=` argument MUST name both the sibling repo and the tracking memo. Example:

```python
@pytest.mark.cross_repo_fix_locus(
    reason="fix lives in project-rag; tracked in cross-repo/inbox/2026-06-24-macos-first-class-test-parity.md"
)
```

The reason string IS the staleness check. A reason that does not name a memo becomes untrackable — you cannot tell when the sibling landed the fix, and the deselect silently outlives its cause.

#### (b) Re-collection trigger — deselection is temporary, never permanent

When the sibling repo lands its fix and it propagates to this repo, the `cross_repo_fix_locus` deselect MUST be removed and the test must go green. Deselection is a *temporary, memo-bound* state. A deselect that outlives its memo becomes a silently-absent decorative test — invisible debt with no `xpass` tripwire to announce when the underlying fix lands.

**Closure trigger:** when the cross-repo memo is resolved (sibling lands and propagates), the responsible party MUST remove the `cross_repo_fix_locus` marker from every test it deselected and verify those tests go green on the previously-affected lane.

#### (c) Discriminator — not a substitute for the prerequisite-absent rule

`cross_repo_fix_locus` applies **only** when **no lane** in *this* repo can make the test pass regardless of CI configuration. If any lane in this repo could install the prerequisite, the prerequisite-absent rule from `cross-repo-contract-test-discipline.md` applies instead — and under that rule, skipping is failure.

The discriminator in plain terms:

- **Fix locus is in a sibling repo** (no amount of CI configuration in this repo will make the test pass): use `cross_repo_fix_locus` + cross-repo memo.
- **Prerequisite can be installed in a CI lane in this repo** (e.g. install the addon, start a sidecar, provision an env var): `cross-repo-contract-test-discipline.md` applies; declare the lane, require the test to pass in it, and treat skipping as failure in that lane.

Do not use `cross_repo_fix_locus` to avoid setting up a lane that COULD make the test pass from here. That is green-by-deselect, not honest measurement.

### 3. Hardware-gated tests — effective coverage-equivalence

Some tests require physical hardware (a GPU, a real network sidecar, a specific device) that CI runners do not provide. On a runner that lacks the hardware, these tests MUST skip with a named marker and a clear reason string — not silently pass, and not hang.

The rationale is **coverage-equivalence**: excluding a hardware-gated test on a hardware-absent runner yields *the same coverage as every other OS lane that also lacks the hardware* — a coverage-parity argument, not a silent XFAIL. Explicitly: skipping `real_spawn` on a CPU-only runner is equivalent to all other CPU-only lanes; the coverage is the same, nothing is hidden, and the skip signal is visible in CI output.

Per `test-environment-discipline.md` §3: a skip-with-explanation is a contract signal. A silent pass achieved by forcing the environment into a degraded state (e.g. `EMBED_DEVICE=cpu` unconditionally) is a contract violation that hides production-shape regressions.

**Never use `xfail` for hardware-gated skips.** `xfail` absorbs test-infrastructure exceptions silently (test-design-discipline.md §25); a hardware-gated `xfail` will stay green even if the test is failing for an unrelated reason. Named markers with clear reason strings are the load-bearing form; `xfail(strict=True)` is safer than `xfail(strict=False)` if you must use it, but a named marker is preferred.

---

## Reference implementation (pytest)

This section shows the canonical pytest shape for the primitives above. If your project uses a different test runner or CI system, adapt the matrix and marker conventions to your toolchain — the principle in the previous section governs; the pytest code below is the worked example.

### Marker registration (`conftest.py` or `pyproject.toml`)

```python
# conftest.py
def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "cross_repo_fix_locus(reason): test whose fix locus lives in a sibling repo; "
        "deselected on the affected OS lane until the sibling lands and propagates. "
        "Temporary and memo-bound — remove this marker when the cross-repo memo is resolved.",
    )
    config.addinivalue_line(
        "markers",
        "hardware_gated(reason): test requires physical hardware (GPU, real sidecar, etc.) "
        "absent on this CI runner. Skips with explanation; yields coverage-equivalence with "
        "other hardware-absent lanes. Replace with your own hardware-gate marker names as appropriate.",
    )
```

### Marker application

```python
import pytest

# cross_repo_fix_locus: fix belongs in project-rag, not here.
# Remove this marker once cross-repo/inbox/2026-06-24-macos-first-class-test-parity.md is resolved.
@pytest.mark.cross_repo_fix_locus(
    reason="fix lives in project-rag; tracked in cross-repo/inbox/2026-06-24-macos-first-class-test-parity.md"
)
def test_install_path_resolution_macos():
    ...


# hardware_gated: requires a real GPU sidecar; skips on CPU-only runners (coverage-equivalence).
# project-rag uses 'real_spawn' and 'requires_real_sidecar' as its own hardware-gate marker names;
# use your project's equivalent names — the class, not these specific names, is the standard.
@pytest.mark.hardware_gated(
    reason="requires GPU sidecar (real_spawn); coverage-equivalence with other CPU-only lanes"
)
def test_embed_round_trip_real_sidecar():
    ...
```

### `shell: bash` marker-computation step (GitHub Actions reference)

The following CI step computes which markers to deselect and builds the `pytest -m` expression. It runs in `shell: bash` so it works identically on `ubuntu-latest`, `windows-latest` (via git-bash), and `macos-latest`:

```yaml
# shell: bash is explicit — git-bash provides bash on Windows runners.
# This step is identical on all three OS lanes; marker deselection is computed once.
- name: Compute deselect markers
  shell: bash
  run: |
    DESELECT_MARKERS=""

    # cross_repo_fix_locus: fix belongs in a sibling repo; deselect on affected lane only.
    # Closure guard: this deselect is TEMPORARY. Remove when the cross-repo memo is resolved
    # and the sibling's fix has propagated to this repo. A deselect that outlives its memo
    # is a silently-absent decorative test.
    # Discriminator: applies ONLY when no lane in THIS repo can make the test pass regardless
    # of CI configuration. If a lane could install the prerequisite, use a with/without lane
    # pair per cross-repo-contract-test-discipline.md instead.
    if [[ "${{ matrix.os }}" == "macos-latest" ]]; then
      DESELECT_MARKERS="${DESELECT_MARKERS} and not cross_repo_fix_locus"
    fi

    # hardware_gated: skip on runners without the required hardware.
    # Yields coverage-equivalence with other hardware-absent lanes — not a silent pass.
    # Your project's hardware-gate marker names go here (e.g. real_spawn, requires_real_sidecar).
    DESELECT_MARKERS="${DESELECT_MARKERS} and not hardware_gated"

    # Strip leading ' and '. DESELECT_MARKERS is always non-empty (hardware_gated is appended
    # unconditionally above), so the if/else guard is dead — always write directly.
    DESELECT_EXPR="${DESELECT_MARKERS# and }"
    echo "PYTEST_MARKER_EXPR=${DESELECT_EXPR}" >> "$GITHUB_ENV"

- name: Run tests
  shell: bash
  run: |
    pytest -m "$PYTEST_MARKER_EXPR" tests/
```

**Note on hardware-gate marker names.** `real_spawn` and `requires_real_sidecar` are project-rag's own hardware-gate marker names — they are examples of the hardware-gated class. For a new project, define your own marker names that describe your hardware constraints. `cross_repo_fix_locus` IS the intended coordinator-standard marker name and should be used verbatim across projects.

---

## When this applies

This discipline fires when a project **declares cross-platform support** — meaning it claims to work on more than one OS. Signals that imply the declaration:

- The project ships shell scripts or hooks to consumers' machines (coordinator itself is an example).
- The project's own `coordinator.local.md` sets `cross_platform: true`.
- A CI workflow already carries an `os:` matrix with multiple entries.
- The project has `*.sh` files in `bin/` and runs on Windows operators' machines.

When detected, the coordinator's repo-setup skill offers the CI reference. On accept, it points at the reference snippet at `templates/ci/cross-platform-matrix.snippet.yml` (a worked pytest example of the language-agnostic principle) and links this wiki. For non-Python repos, the offer describes the principle and the snippet as a worked example to adapt — it does not hand pytest YAML to a TypeScript or Rust project.

If your project uses a CI system other than GitHub Actions or a test runner other than pytest, the matrix and honest-measurement marker conventions adapt to your toolchain. The language-agnostic principle in the earlier section is the contract; the snippet is a reference form.

---

## A sibling's fix recommendation, reproduced on THEIR platform, may regress yours

A cross-repo finding that ships a "here's the fix" recommendation is verified on the *reporter's* platform. Before adopting it, reproduce the **original failure on your own platform** — the same code can fail in **opposite directions** across OSes, and applying the sibling's fix blind then regresses your lane.

**Empirical basis (example-game-repo live-bringup):** a finding traced CodeRankEmbed's offline load failing by bare repo-id and recommended "always resolve to the local snapshot path instead." It reproduced cleanly on the reporter's Windows/CUDA box. On macOS the **opposite** held: repo-id load *succeeds* and the raw snapshot path *fails* — passing `snapshots/<rev>` breaks `trust_remote_code` dynamic-module resolution through the HF cache's `blobs/` symlinks. Adopting the Windows fix unverified would have broken the Mac lane.

This is the fix-recommendation-level instance of "green on your dev OS is not green on the others": a fix *proven* on one OS is not proven on the others. A sibling-supplied fix is a hypothesis to reproduce per-platform, not a patch to apply. (Source: example-game-repo.)

## Cross-references

- `install-surface-completeness.md` — the broader "build for someone else's machine" doctrine; this wiki is its CI-measurement enforcement arm.
- `cross-platform-shell-portability.md` — the *code* discipline (bash version, BSD coreutils, CRLF traps). The support matrix there (macOS=P0, Windows Git-Bash=must-work, Linux=untested) is the authority the CI matrix inherits.
- `test-environment-discipline.md` §3 — skip-with-explanation vocabulary: "a skip-with-explanation is a contract signal; a silent pass is a contract violation."
- `test-design-discipline.md` §25 — rationale for named markers over `xfail`: `xfail` markers absorb test-infrastructure exceptions silently; `xfail(strict=True)` is safer but named markers with clear reason strings are the preferred pattern.
- `cross-repo-contract-test-discipline.md` — the F2 discriminator: in any lane that CAN install the prerequisite, skipping is failure. `cross_repo_fix_locus` applies only when no lane in this repo can make the test pass; the prerequisite-absent rule in that wiki governs otherwise.
- `templates/ci/cross-platform-matrix.snippet.yml` — the copyable CI reference snippet (pytest / GitHub Actions shape; adapt to your CI system and test runner).
