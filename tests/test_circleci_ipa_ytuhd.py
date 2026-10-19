"""Prevent recurring YTUHD vpx/dav1d header/link failures without a Mac."""
from pathlib import Path
import tempfile
import unittest

from Scripts.prepare_circleci_ytuhd import (
    ARCHIVES, HEADERS, MARKER, NEW, OLD, SCRIPTS,
    patched_makefile, validate_vendor_archives, validate_vendor_sources,
)

ROOT = Path(__file__).resolve().parents[1]

STANDALONE = """LIBVPX_BUILD = $(THEOS_PROJECT_DIR)/vendor/libvpx_ios
LIBVPX_A = $(LIBVPX_BUILD)/libvpx.a
DAV1D_BUILD = $(THEOS_PROJECT_DIR)/vendor/dav1d_ios
DAV1D_A = $(DAV1D_BUILD)/libdav1d.a
YTUHD_CFLAGS = -I$(THEOS_PROJECT_DIR)/vendor/libvpx -I$(THEOS_PROJECT_DIR)/vendor/dav1d/include
YTUHD_LDFLAGS = $(LIBVPX_A) $(DAV1D_A)
$(THEOS_PROJECT_DIR)/vendor/build_libvpx.sh
$(THEOS_PROJECT_DIR)/vendor/build_dav1d.sh
HAMVPXVideoDecoder.m HAMDav1dVideoDecoder.m
"""


class ModernYTUHDDependencies(unittest.TestCase):
    def test_nested_makefile_rewrites_all_paths(self):
        modified = patched_makefile(STANDALONE)
        self.assertIn(MARKER, modified)
        self.assertIn("CIRCLECI_YTUHD_DIR :=", modified)
        self.assertNotIn(OLD, modified)
        self.assertIn(NEW + "libvpx", modified)
        self.assertIn(NEW + "dav1d/include", modified)
        self.assertIn(NEW + "build_libvpx.sh", modified)
        self.assertIn(NEW + "build_dav1d.sh", modified)

    def test_makefile_rewrite_is_idempotent(self):
        transformed = patched_makefile(STANDALONE)
        self.assertEqual(transformed, patched_makefile(transformed))

    def test_changed_upstream_makefile_fails_closed(self):
        with self.assertRaises(ValueError):
            patched_makefile("YTUHD_CFLAGS = -fobjc-arc")
        with self.assertRaises(ValueError):
            patched_makefile(MARKER + "\n" + STANDALONE)

    def test_vendor_source_header_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(set(validate_vendor_sources(root)),
                             set(HEADERS + SCRIPTS))
            for rel in HEADERS + SCRIPTS:
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("fixture")
            self.assertEqual(validate_vendor_sources(root), [])

    def test_missing_or_empty_archives_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(set(validate_vendor_archives(root)), set(ARCHIVES))
            for rel in ARCHIVES:
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b"x" * 256)
            self.assertEqual(validate_vendor_archives(root), [])
            (root / ARCHIVES[0]).write_bytes(b"")
            self.assertIn(ARCHIVES[0], validate_vendor_archives(root))

    def test_macos_builder_prepares_both_archives_before_theos(self):
        build = (ROOT / "Scripts/build_circleci_ipa.sh").read_text()
        helper = (ROOT / "Scripts/build_circleci_ytuhd_deps.sh").read_text()
        self.assertLess(
            build.index("bash Scripts/build_circleci_ytuhd_deps.sh"),
            build.index('git clone --quiet --depth 1 --recurse-submodules '
                        'https://github.com/theos/theos.git'),
        )
        self.assertLess(
            build.index("bash Scripts/build_circleci_ytuhd_deps.sh"),
            build.index("make package THEOS_PACKAGE_SCHEME=rootless"),
        )
        self.assertIn("prepare_circleci_ytuhd.py", build)
        self.assertIn('bash "$folder/vendor/build_$library.sh"', helper)
        self.assertIn("libvpx:libvpx_ios/libvpx.a", helper)
        self.assertIn("dav1d:dav1d_ios/libdav1d.a", helper)
        self.assertIn('xcrun lipo -archs "$archive"', helper)

    def test_revision_pinned_on_preflight_and_macos(self):
        pin = (ROOT / "Scripts/ytuhd_source_revision.txt").read_text()
        refs = [line for line in pin.splitlines()
                if line and not line.startswith("#")]
        self.assertEqual(len(refs), 1)
        self.assertRegex(refs[0], r"^[0-9a-f]{40}$")
        for path in ("Scripts/build_circleci_ipa.sh",
                     "Scripts/preflight_circleci_patch_chain.sh"):
            content = (ROOT / path).read_text()
            self.assertIn("ytuhd_source_revision.txt", content)
            self.assertIn("checkout --quiet --detach FETCH_HEAD", content)
            self.assertNotIn(
                "--recurse-submodules --branch master https://github.com/PoomSmart/YTUHD",
                content,
            )

    def test_preflight_validates_nested_makefile(self):
        preflight = (ROOT / "Scripts/preflight_circleci_patch_chain.sh").read_text()
        self.assertIn("prepare_circleci_ytuhd.py", preflight)
        self.assertIn("--source-only", preflight)
        cfg = (ROOT / ".circleci/config.yml").read_text()
        self.assertIn("bash -n Scripts/build_circleci_ytuhd_deps.sh", cfg)
        self.assertIn('test_circleci_ipa*.py', cfg)


if __name__ == "__main__":
    unittest.main()
