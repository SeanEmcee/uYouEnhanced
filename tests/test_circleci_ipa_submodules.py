"""Ensure CircleCI only initializes submodules genuinely recorded as gitlinks.

Runs in the cheap Linux preflight, before a macOS build or source IPA download.
The .gitmodules stanza alone does not make a path a tracked submodule.
"""
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "Scripts" / "build_circleci_ipa.sh"
GITMODULES = ROOT / ".gitmodules"


def tracked_gitlink(path: str) -> bool:
    result = subprocess.run(
        ["git", "ls-files", "--stage", "--", path],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    lines = result.stdout.splitlines()
    if len(lines) != 1:
        return False
    metadata, sep, recorded_path = lines[0].partition("\t")
    fields = metadata.split()
    return (bool(sep) and len(fields) == 3 and fields[0] == "160000"
            and fields[2] == "0" and recorded_path == path)


def required_build_submodules() -> list[str]:
    source = BUILD.read_text(encoding="utf-8")
    start_token = "\nset -- Tweaks/"
    end_token = "\nif [[ \"$(printenv MODERN_YTUHD"
    if source.count(start_token) != 1 or source.count(end_token) != 1:
        raise AssertionError("Cannot locate the pinned CircleCI submodule list")
    start = source.index(start_token) + len("\nset -- ")
    end = source.index(end_token, start)
    joined = source[start:end].replace("\\\n", " ")
    paths = joined.split()
    if not paths or any(not path.startswith("Tweaks/") for path in paths):
        raise AssertionError("Invalid build submodule list")
    return paths


class CircleCIGitlinks(unittest.TestCase):
    def test_every_build_module_is_a_tracked_gitlink(self):
        modules = required_build_submodules() + ["Tweaks/YTUHD"]
        self.assertEqual(len(modules), len(set(modules)), "Duplicate module")
        for module in modules:
            with self.subTest(module=module):
                self.assertTrue(
                    tracked_gitlink(module),
                    "Build requested a missing or non-gitlink submodule: " + module,
                )

    def test_gitmodules_stanzas_match_tracked_gitlinks(self):
        manifest = GITMODULES.read_text(encoding="utf-8")
        names = re.findall(r"(?m)^\s*path\s*=\s*(\S+)\s*$", manifest)
        self.assertTrue(names)
        self.assertEqual(len(names), len(set(names)), "Duplicate .gitmodules path")
        for name in names:
            with self.subTest(module=name):
                self.assertTrue(
                    tracked_gitlink(name),
                    ".gitmodules contains an orphaned submodule: " + name,
                )

    def test_build_modules_have_manifest_entries(self):
        manifest = GITMODULES.read_text(encoding="utf-8")
        names = set(re.findall(r"(?m)^\s*path\s*=\s*(\S+)\s*$", manifest))
        for module in required_build_submodules() + ["Tweaks/YTUHD"]:
            with self.subTest(module=module):
                self.assertIn(module, names)

    def test_build_script_has_early_gitlink_guard(self):
        script = BUILD.read_text(encoding="utf-8")
        self.assertIn('git ls-files --stage -- "$module"', script)
        self.assertIn('[[ "$mode" != "160000" ]]', script)
        self.assertLess(script.index('git ls-files --stage -- "$module"'),
                        script.index('git submodule update --init --recursive'))

    def test_stale_youtube_x_is_absent(self):
        self.assertNotIn("Tweaks/YouTube-X", required_build_submodules())
        self.assertNotIn("path = Tweaks/YouTube-X",
                         GITMODULES.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
