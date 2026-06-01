"""
test_setup_templates_manifest_sync.py — parity test for setup-templates-manifest.sh.

Placement: this test lives at tests/install/ (install-specific concern) rather than
the tests/sibling-parity/ convention in docs/wiki/sibling-surface-parity-testing.md —
if you are auditing the parity-test inventory, this surface's parity test is HERE.

Spec backlink: archive/specs/2026-05-27-cqcs-cluster7-lib-consolidation.md § File D

Purpose: Assert that lib/setup-templates-manifest.sh is the single source of truth
         for the ~/.claude/setup/ percolation file list and that no consumer retains
         a divergent inline copy. Five assertion groups:
           1. Parse manifest arrays via bash subprocess.
           2. install-substrate.sh: source + array-iteration assertions.
           3. dist/publish-repo-setup/install.sh: source + array-iteration assertions.
           4. Manifest ↔ disk relpath set-equality (templates/setup/).
           5. SETUP_TEMPLATE_EXEC_FILES ⊆ SETUP_TEMPLATE_FILES (orthogonal subset check).

Negative-spec: does NOT run an actual install; no filesystem writes outside repo.
"""

import os
import pathlib
import subprocess
import sys
import unittest

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

PLUGIN_COORDINATOR = pathlib.Path(__file__).resolve().parents[2]  # coordinator/
REPO_ROOT = PLUGIN_COORDINATOR.parents[2]  # ~/.claude
MANIFEST = PLUGIN_COORDINATOR / "lib" / "setup-templates-manifest.sh"
INSTALL_SUBSTRATE = PLUGIN_COORDINATOR / "lib" / "install-substrate.sh"
INSTALL_SH = PLUGIN_COORDINATOR / "dist" / "publish-repo-setup" / "install.sh"
TEMPLATES_SETUP = PLUGIN_COORDINATOR / "templates" / "setup"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bash_available() -> bool:
    """Return True if bash is on PATH."""
    try:
        result = subprocess.run(
            ["bash", "--version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _read_manifest_array(array_name: str) -> list[str]:
    """Source the manifest in bash and return the named array's elements.

    The manifest path is injected via the MANIFEST_PATH env var so that
    Windows-style paths (forward slashes, spaces) survive without quoting
    gymnastics in the bash -c string.
    """
    # Use forward slashes — bash on Windows (Git-Bash / MSYS) handles them.
    manifest_posix = MANIFEST.as_posix()
    script = (
        'source "$MANIFEST_PATH"; '
        f'printf "%s\\n" "${{{array_name}[@]}}"'
    )
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        timeout=10,
        env={**os.environ, "MANIFEST_PATH": manifest_posix},
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"bash failed sourcing manifest for {array_name}: {result.stderr}"
        )
    lines = [line for line in result.stdout.splitlines() if line]
    return lines


# ---------------------------------------------------------------------------
# Bash-independent test class — manifest existence must be detectable even
# when bash is absent (F4: this assertion previously lived inside the
# bash-guarded class, so a missing manifest went undetected without bash).
# ---------------------------------------------------------------------------

class TestManifestExists(unittest.TestCase):

    def test_manifest_file_exists(self):
        self.assertTrue(MANIFEST.exists(), f"Manifest not found: {MANIFEST}")


# ---------------------------------------------------------------------------
# Test class — bash-dependent parity assertions (guarded)
# ---------------------------------------------------------------------------

class TestSetupTemplatesManifestSync(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Skip entire class if bash unavailable — explicit, greppable reason."""
        if not _bash_available():
            raise unittest.SkipTest(
                "SKIP: bash unavailable — manifest parity NOT verified"
            )

    # --- Assertion group 1: parse manifest arrays ---

    def test_manifest_arrays_parseable(self):
        """Manifest sources cleanly and all three arrays are non-empty."""
        files = _read_manifest_array("SETUP_TEMPLATE_FILES")
        exec_files = _read_manifest_array("SETUP_TEMPLATE_EXEC_FILES")
        hook_files = _read_manifest_array("SETUP_TEMPLATE_HOOK_FILES")

        self.assertGreater(len(files), 0, "SETUP_TEMPLATE_FILES is empty")
        self.assertGreater(len(exec_files), 0, "SETUP_TEMPLATE_EXEC_FILES is empty")
        self.assertGreater(len(hook_files), 0, "SETUP_TEMPLATE_HOOK_FILES is empty")

    # --- Assertion group 2: install-substrate.sh ---

    def test_install_substrate_sources_manifest(self):
        """(a) install-substrate.sh contains a source of setup-templates-manifest.sh."""
        text = INSTALL_SUBSTRATE.read_text(encoding="utf-8")
        self.assertIn(
            "setup-templates-manifest.sh",
            text,
            "install-substrate.sh does not source setup-templates-manifest.sh",
        )

    def test_install_substrate_iterates_array(self):
        """(b) install-substrate.sh Step 3d drives its loop from the array token."""
        text = INSTALL_SUBSTRATE.read_text(encoding="utf-8")
        self.assertIn(
            '"${SETUP_TEMPLATE_FILES[@]}"',
            text,
            "install-substrate.sh Step 3d does not iterate SETUP_TEMPLATE_FILES array",
        )

    def test_install_substrate_no_inline_literal_list(self):
        """(c) Supplementary: old space-joined literal list absent from install-substrate.sh."""
        text = INSTALL_SUBSTRATE.read_text(encoding="utf-8")
        inline_literal = "publish.sh publish_sync.py publish-targets.example.sh .percolate-identity.example"
        self.assertNotIn(
            inline_literal,
            text,
            "install-substrate.sh still contains the old inline literal file list — "
            "remove it and use the manifest arrays",
        )

    # --- Assertion group 3: dist/publish-repo-setup/install.sh ---

    def test_install_sh_sources_manifest(self):
        """(a) install.sh deliver_setup_templates() sources setup-templates-manifest.sh."""
        text = INSTALL_SH.read_text(encoding="utf-8")
        self.assertIn(
            "setup-templates-manifest.sh",
            text,
            "dist/publish-repo-setup/install.sh does not source setup-templates-manifest.sh",
        )

    def test_install_sh_iterates_array(self):
        """(b) install.sh deliver_setup_templates() drives its loop from the array token."""
        text = INSTALL_SH.read_text(encoding="utf-8")
        self.assertIn(
            '"${SETUP_TEMPLATE_FILES[@]}"',
            text,
            "install.sh deliver_setup_templates() does not iterate SETUP_TEMPLATE_FILES array",
        )

    def test_install_sh_no_inline_literal_list(self):
        """(c) Supplementary: old space-joined literal list absent from install.sh."""
        text = INSTALL_SH.read_text(encoding="utf-8")
        inline_literal = "publish.sh publish_sync.py publish-targets.example.sh .percolate-identity.example"
        self.assertNotIn(
            inline_literal,
            text,
            "dist/publish-repo-setup/install.sh still contains the old inline literal file list — "
            "remove it and use the manifest arrays",
        )

    # --- Assertion group 4: manifest ↔ disk relpath set-equality ---

    def test_manifest_disk_relpath_set_equality(self):
        """
        disk_set     = { relpath(f, templates/setup) for each file in recursive walk }
        manifest_set = set(SETUP_TEMPLATE_FILES) ∪ set(SETUP_TEMPLATE_HOOK_FILES)
        assert disk_set == manifest_set  (bidirectional: catches additions AND removals)

        Comparison key is RELPATH-from-templates/setup/, never basename, so that
        templates/setup/percolate-hooks/README.md and a hypothetical templates/setup/README.md
        stay distinct.

        SETUP_TEMPLATE_EXEC_FILES is NOT part of this union — it is an orthogonal
        subset check in assertion group 5.
        """
        self.assertTrue(
            TEMPLATES_SETUP.exists(),
            f"templates/setup/ directory not found: {TEMPLATES_SETUP}",
        )

        # Walk disk
        disk_set: set[str] = set()
        for root, dirs, files in os.walk(TEMPLATES_SETUP):
            # Prune Python bytecode caches: __pycache__/*.pyc are gitignored build
            # artifacts regenerated by the test runner itself (it imports publish_sync.py),
            # never template files — they must not enter the disk set or the walk
            # fails against its own side effects on the second run.
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for fname in files:
                if fname.endswith(".pyc"):
                    continue
                abs_path = pathlib.Path(root) / fname
                rel = abs_path.relative_to(TEMPLATES_SETUP)
                # Normalise to forward slashes for cross-platform string comparison
                disk_set.add(rel.as_posix())

        # Parse manifest arrays
        manifest_files = set(_read_manifest_array("SETUP_TEMPLATE_FILES"))
        manifest_hook_files = set(_read_manifest_array("SETUP_TEMPLATE_HOOK_FILES"))
        manifest_set = manifest_files | manifest_hook_files

        missing_from_manifest = disk_set - manifest_set
        missing_from_disk = manifest_set - disk_set

        errors: list[str] = []
        if missing_from_manifest:
            errors.append(
                f"Files on disk under templates/setup/ NOT in manifest "
                f"(added a template file but forgot the manifest?): "
                f"{sorted(missing_from_manifest)}"
            )
        if missing_from_disk:
            errors.append(
                f"Files in manifest NOT on disk under templates/setup/ "
                f"(removed a template file but left it in the manifest?): "
                f"{sorted(missing_from_disk)}"
            )

        self.assertFalse(errors, "\n".join(errors))

    # --- Assertion group 5: EXEC_FILES ⊆ TEMPLATE_FILES ---

    def test_exec_files_subset_of_template_files(self):
        """
        Assert SETUP_TEMPLATE_EXEC_FILES ⊆ SETUP_TEMPLATE_FILES.
        No exec flag should be set for a file that is not in the delivery list.
        """
        template_files = set(_read_manifest_array("SETUP_TEMPLATE_FILES"))
        exec_files = set(_read_manifest_array("SETUP_TEMPLATE_EXEC_FILES"))

        not_in_template = exec_files - template_files
        self.assertFalse(
            not_in_template,
            f"SETUP_TEMPLATE_EXEC_FILES contains entries not in SETUP_TEMPLATE_FILES: "
            f"{sorted(not_in_template)}",
        )


if __name__ == "__main__":
    unittest.main()
