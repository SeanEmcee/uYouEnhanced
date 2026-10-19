"""Offline header layout regressions for the low-credit CircleCI preflight."""
from pathlib import Path
import tempfile
import unittest

from Scripts.check_circleci_headers import (
    REQUIRED_HEADERS, THEOS_INCLUDE, validate_header_layout
)

ROOT = Path(__file__).resolve().parents[1]


class YouTubeHeaderPreflightTests(unittest.TestCase):
    def fixture(self, include_path=True, headers=None):
        context = tempfile.TemporaryDirectory()
        self.addCleanup(context.cleanup)
        root = Path(context.name)
        (root / "Tweaks" / "YouTubeHeader").mkdir(parents=True)
        (root / "Makefile").write_text(
            "export ADDITIONAL_CFLAGS = " +
            (THEOS_INCLUDE if include_path else "-Iwrong/path") + "\n",
            encoding="utf-8",
        )
        for filename in (REQUIRED_HEADERS if headers is None else headers):
            (root / "Tweaks" / "YouTubeHeader" / filename).write_text(
                "// simulated public header\n", encoding="utf-8"
            )
        return root

    def test_valid_layout_passes(self):
        self.assertEqual(validate_header_layout(self.fixture()), [])

    def test_missing_like_status_is_reported(self):
        root = self.fixture(headers=("YTSettingsCell.h",))
        self.assertIn(
            "Missing Tweaks/YouTubeHeader/YTLikeStatus.h",
            validate_header_layout(root),
        )

    def test_missing_settings_cell_is_reported(self):
        root = self.fixture(headers=("YTLikeStatus.h",))
        self.assertIn(
            "Missing Tweaks/YouTubeHeader/YTSettingsCell.h",
            validate_header_layout(root),
        )

    def test_missing_theos_search_path_is_reported(self):
        root = self.fixture(include_path=False)
        self.assertIn(
            "Makefile is missing the Theos Tweaks include search path",
            validate_header_layout(root),
        )

    def test_missing_makefile_is_reported(self):
        root = self.fixture()
        (root / "Makefile").unlink()
        self.assertIn("Root Makefile missing", validate_header_layout(root))

    def test_real_build_script_initializes_headers_before_compile(self):
        source = (ROOT / "Scripts" / "build_circleci_ipa.sh").read_text()
        self.assertIn("Tweaks/YouTubeHeader", source)
        self.assertLess(
            source.index("Tweaks/YouTubeHeader Tweaks/protobuf"),
            source.index('git submodule update --init --recursive -- "$@"'),
        )
        self.assertLess(
            source.index("Scripts/check_circleci_headers.py"),
            source.index("bash Scripts/install_circleci_macos_deps.sh"),
        )

    def test_cheap_preflight_checks_checkout_and_header_layout(self):
        config = (ROOT / ".circleci" / "config.yml").read_text()
        preflight = (ROOT / "Scripts" / "preflight_circleci_patch_chain.sh").read_text()
        self.assertIn("bash Scripts/preflight_circleci_patch_chain.sh", config)
        self.assertIn(
            "git submodule update --init -- Tweaks/YouTubeHeader", preflight
        )
        self.assertIn("python3 Scripts/check_circleci_headers.py", preflight)
        self.assertIn('test_circleci_ipa*.py', config)


if __name__ == "__main__":
    unittest.main()
