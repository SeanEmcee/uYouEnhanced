"""Offline tests for macOS Homebrew bootstrap with a fake brew command."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "Scripts" / "install_circleci_macos_deps.sh"
BUILD = ROOT / "Scripts" / "build_circleci_ipa.sh"
FORMULAE = ("ldid", "dpkg", "make", "wget", "unzip", "jq", "pipx",
            "meson", "ninja", "gnu-sed", "autoconf", "automake",
            "libtool", "pkgconf", "pngquant")
COMMANDS = ("ldid", "dpkg", "gmake", "wget", "unzip", "jq", "pipx",
            "meson", "ninja", "gsed", "autoconf", "automake",
            "glibtool", "pkgconf", "pngquant")
FAKE_BREW = """#!/usr/bin/env bash
set -eu
if [[ "$1" == list ]]; then
  shift 3
  grep -Fxq -- "$1" "$FAKE_INSTALLED" || exit 1
  exit 0
fi
if [[ "$1" == install ]]; then
  printf 'install|%s|%s|%s|%s\\n' \
    "$HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK" \
    "$HOMEBREW_NO_INSTALL_UPGRADE" \
    "$HOMEBREW_NO_INSTALL_CLEANUP" \
    "$HOMEBREW_NO_AUTO_UPDATE" >>"$FAKE_CALLS"
  shift
  for formula in "$@"; do
    if [[ "$formula" != "$FAKE_SKIP_INSTALL" ]]; then
      printf '%s\\n' "$formula" >>"$FAKE_INSTALLED"
    fi
  done
  exit "$FAKE_INSTALL_EXIT"
fi
echo "Unexpected fake brew command" >&2
exit 77
"""


class HomebrewBootstrapTests(unittest.TestCase):
    def _run(self, installed=(), exit_code=0, skip_install=None):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            bin_dir = folder / "bin"
            bin_dir.mkdir()
            script = bin_dir / "brew"
            script.write_text(FAKE_BREW)
            script.chmod(0o755)
            for command in COMMANDS:
                executable = bin_dir / command
                executable.write_text("#!/bin/sh\nexit 0\n")
                executable.chmod(0o755)
            installed_file = folder / "installed.txt"
            installed_file.write_text("".join(item + "\n" for item in installed))
            calls_file = folder / "calls.txt"
            calls_file.write_text("")
            env = {
                **os.environ,
                "PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin"),
                "FAKE_INSTALLED": str(installed_file),
                "FAKE_CALLS": str(calls_file),
                "FAKE_INSTALL_EXIT": str(exit_code),
                "FAKE_SKIP_INSTALL": skip_install or "__none__",
                "HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK": "0",
                "HOMEBREW_NO_INSTALL_UPGRADE": "0",
            }
            result = subprocess.run(
                ["bash", str(BOOTSTRAP)], cwd=ROOT, env=env,
                capture_output=True, text=True, check=False, timeout=30
            )
            return result, calls_file.read_text(), installed_file.read_text()

    def test_existing_formulae_skip_install(self):
        result, calls, _ = self._run(installed=FORMULAE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, "")
        self.assertIn("skipping brew install", result.stdout)

    def test_installs_missing_formulae_without_upgrade_cascade(self):
        result, calls, installed = self._run(installed=("ldid", "dpkg"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("install|1|1|1|1", calls)
        self.assertIn("pngquant", installed.splitlines())

    def test_nonzero_install_with_verified_tools_can_continue(self):
        result, calls, _ = self._run(exit_code=1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("install|1|1|1|1", calls)
        self.assertIn("despite Homebrew warnings", result.stdout)

    def test_missing_formula_after_failed_install_aborts(self):
        result, _, installed = self._run(exit_code=1, skip_install="ldid")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("ldid", installed.splitlines())
        self.assertIn("ldid", result.stderr)
        self.assertNotIn("dependency bootstrap complete", result.stdout)

    def test_build_uses_bootstrap_and_erases_source_url(self):
        content = BUILD.read_text(encoding="utf-8")
        self.assertIn("bash Scripts/install_circleci_macos_deps.sh", content)
        self.assertIn("unset YOUTUBE_IPA_URL", content)
        self.assertLess(content.index("unset YOUTUBE_IPA_URL"),
                        content.index("install_circleci_macos_deps.sh"))
        self.assertNotIn("brew install ldid dpkg make", content)


if __name__ == "__main__":
    unittest.main()
