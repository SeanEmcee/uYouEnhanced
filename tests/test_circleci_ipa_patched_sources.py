"""Synthetic tests for the full source patch output audit (no Apple SDK)."""
from pathlib import Path
import tempfile
import unittest

from Scripts.check_circleci_patched_sources import (
    PIp_METHODS, PIp_PROPERTIES, inspect_patch_output,
)

ROOT = Path(__file__).resolve().parents[1]


class PatchedSourceAuditTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        pip_dir = root / "Tweaks" / "YouPiP"
        decoder_dir = root / "Tweaks" / "YTUHD"
        pip_dir.mkdir(parents=True)
        decoder_dir.mkdir(parents=True)
        props = "".join(
            "@property (nonatomic, retain) id " + name + ";\n"
            for name in sorted(PIp_PROPERTIES)
        )
        methods = "".join("- (void)" + name + ";\n" for name in PIp_METHODS)
        logos = "".join(
            "%property (nonatomic, retain) id " + name + ";\n"
            for name in sorted(PIp_PROPERTIES)
        )
        markers = (
            "LC_PIP_LAB_V1 LC_EDGE_HOLD_V4 LC_PLAYBACK_STABILITY_V7 "
            "LC_MINIPLAYER_GESTURE_GUARD_V8 LC_MINIPLAYER_TOUCH_FIX_V9 "
            "LC_4K_PERFORMANCE_V10"
        )
        (pip_dir / "Tweak.x").write_text(
            "@interface YTPlayerViewController (LCPiPLabCompileSurface)\n"
            + props + methods + "@end\n" + logos + markers,
            encoding="utf-8",
        )
        (pip_dir / "Settings.x").write_text(
            "static UIViewController *LCPresenter(void)", encoding="utf-8"
        )
        (decoder_dir / "Settings.x").write_text(
            "static UIViewController *LCYTUHDPresenter(void)", encoding="utf-8"
        )
        return root

    def test_complete_generated_layout_passes(self):
        self.assertEqual(inspect_patch_output(self.fixture()), [])

    def test_missing_static_controller_declaration_fails(self):
        root = self.fixture()
        path = root / "Tweaks/YouPiP/Tweak.x"
        path.write_text(path.read_text().replace(
            "(LCPiPLabCompileSurface)", "(MissingCategory)"))
        self.assertIn(
            "Missing static interface for injected PiP properties",
            inspect_patch_output(root),
        )

    def test_missing_one_property_declaration_fails(self):
        root = self.fixture()
        path = root / "Tweaks/YouPiP/Tweak.x"
        source = path.read_text()
        source = source.replace(
            "@property (nonatomic, retain) id lcEdgeAVPlayer;", "", 1
        )
        path.write_text(source)
        self.assertIn(
            "Missing PiP property declaration: lcEdgeAVPlayer",
            inspect_patch_output(root),
        )

    def test_missing_logos_accessor_fails(self):
        root = self.fixture()
        path = root / "Tweaks/YouPiP/Tweak.x"
        path.write_text(path.read_text().replace(
            "%property (nonatomic, retain) id lcRecoveryPendingV7;", "", 1
        ))
        self.assertIn(
            "Missing Logos runtime accessor: lcRecoveryPendingV7",
            inspect_patch_output(root),
        )

    def test_deprecated_key_window_fails(self):
        root = self.fixture()
        path = root / "Tweaks/YouPiP/Settings.x"
        path.write_text(path.read_text() + "\napplication.keyWindow")
        self.assertIn(
            "YouPiP calls the deprecated UIApplication.keyWindow",
            inspect_patch_output(root),
        )

    def test_cross_translation_unit_helper_error_fails(self):
        root = self.fixture()
        path = root / "Tweaks/YTUHD/Settings.x"
        path.write_text("UIViewController *vc=LCPresenter();")
        problems = inspect_patch_output(root)
        self.assertIn("YTUHD cannot call static YouPiP presenter", problems)
        self.assertIn("Missing local YTUHD presenter implementation", problems)

    def test_real_source_generators_contain_respective_helpers(self):
        playback = (ROOT / "Scripts/apply_lc_playback.py").read_text()
        pip = (ROOT / "Scripts/apply_lc_pip.py").read_text()
        streaming = (ROOT / "Scripts/apply_lc_streaming_v11.py").read_text()
        self.assertIn("@interface YTPlayerViewController (LCPiPLabCompileSurface)", playback)
        self.assertIn("static UIViewController *LCPresenter(void)", pip)
        self.assertIn("static UIViewController *LCYTUHDPresenter(void)", streaming)
        for script in ("apply_lc_decoder_path_v11.py",
                       "apply_lc_av1_priority_v12.py", "apply_lc_streaming_v11.py"):
            source = (ROOT / "Scripts" / script).read_text()
            self.assertNotIn("[UIApplication sharedApplication].keyWindow", source)


if __name__ == "__main__":
    unittest.main()
