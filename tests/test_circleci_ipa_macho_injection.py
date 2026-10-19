"""Offline regressions for the modern Mach-O injector and budget guard.

These run with mock LIEF without an IPA, macOS, Apple SDK or credentials.
The actual executable is separately probed by the macOS build BEFORE brew.
"""
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from Scripts.macho_lief_inject import inject

ROOT = Path(__file__).resolve().parents[1]
DYLIB = "@rpath/uYouEnhanced.dylib"


class MockSlice:
    def __init__(self, libraries=None):
        self.libraries = [
            SimpleNamespace(name=name) for name in (libraries or [])
        ]

    def add(self, cmd):
        self.libraries.append(SimpleNamespace(name=cmd))
        return object()


class MockFat:
    def __init__(self, slices_):
        self.archs = slices_
        self.size = len(slices_)

    def at(self, index):
        return self.archs[index]

    def write(self, path):
        data = "MACHO" + "\n".join(
            ",".join(entry.name for entry in a.libraries)
            for a in self.archs
        )
        Path(path).write_bytes(data.encode().ljust(8192, b"x"))


class MockLIEF:
    @staticmethod
    def parsed(path):
        data = Path(path).read_bytes()
        if not data.startswith(b"MACHO"):
            return None
        entries = data[5:].rstrip(b"x").decode().split("\n")
        return MockFat([MockSlice(entry.split(",") if entry else [])
                        for entry in entries])

    MachO = SimpleNamespace(
        parse=parsed.__func__,
        DylibCommand=SimpleNamespace(weak_lib=lambda name: name)
    )


class MachOInjectorTests(unittest.TestCase):
    def sample(self, contents=b"MACHO"):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "HostBinary"
        path.write_bytes(contents.ljust(8192, b"x"))
        path.chmod(0o755)
        return path

    def test_load_command_injected_then_reparsed(self):
        path = self.sample()
        inject(path, DYLIB, MockLIEF)
        result = MockLIEF.parsed(path)
        self.assertIn(DYLIB, [entry.name for entry in result.at(0).libraries])
        self.assertTrue(path.stat().st_mode & 0o111)

    def test_repeated_injection_does_not_duplicate_load_command(self):
        path = self.sample()
        inject(path, DYLIB, MockLIEF)
        inject(path, DYLIB, MockLIEF)
        libs = [entry.name for entry in MockLIEF.parsed(path).at(0).libraries]
        self.assertEqual(libs.count(DYLIB), 1)

    def test_broken_macho_never_overwrites_source(self):
        path = self.sample(b"BADFILE")
        before = path.read_bytes()
        with self.assertRaises(ValueError):
            inject(path, DYLIB, MockLIEF)
        self.assertEqual(path.read_bytes(), before)

    def test_rejects_invalid_library_paths_without_mutation(self):
        path = self.sample()
        before = path.read_bytes()
        for name in ("", "foo.dylib", "@rpath/illegal space.dylib",
                     "@rpath/name\nmalicious", "../relative.dylib"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                inject(path, name, MockLIEF)
        self.assertEqual(path.read_bytes(), before)

    def test_budget_guard_runs_before_any_expensive_native_work(self):
        script = (ROOT / "Scripts/build_circleci_ipa.sh").read_text()
        probe = "bash Scripts/preflight_circleci_injector.sh"
        self.assertIn(probe, script)
        for stage in ("git submodule update --init --recursive",
                      "bash Scripts/install_circleci_macos_deps.sh",
                      "bash Scripts/build_circleci_ytuhd_deps.sh",
                      "make package THEOS_PACKAGE_SCHEME=rootless"):
            self.assertLess(script.index(probe), script.index(stage))
        self.assertIn('cp Scripts/ci_macho_injector.sh', script)
        self.assertIn('export CIRCLECI_LIEF_PYTHON=', script)

    def test_disposable_macho_probe_and_sha_free_validation(self):
        script = (ROOT / "Scripts/preflight_circleci_injector.sh").read_text()
        self.assertIn("python3 -m venv", script)
        self.assertIn("lief==1.0.0", script)
        self.assertIn('--only-binary=:all:', script)
        self.assertIn('cp -p "$INPUT/$executable" "$probe"', script)
        self.assertIn("trap 'rm -f", script)
        self.assertIn('otool -L "$probe"', script)
        self.assertNotIn("YOUTUBE_IPA_URL", script)

    def test_legacy_theos_injector_is_replaced_and_all_features_remain(self):
        script = (ROOT / "Scripts/build_circleci_ipa.sh").read_text()
        self.assertIn('"$THEOS/mod/jailed/bin/insert_dylib"', script)
        self.assertIn("Scripts/verify_ipa.py", script)
        self.assertIn("cyan -i", script)
        self.assertIn("SPONSORBLOCK_ENABLED=1 SIDELOAD=1", script)
        self.assertIn("YTUHD_ENABLED=1", script)


if __name__ == "__main__":
    unittest.main()
