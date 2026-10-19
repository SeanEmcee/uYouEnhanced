"""Prevent additional missing dylib and case-sensitive packaging regressions."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RootPackagingWiring(unittest.TestCase):
    def test_every_declared_tweak_dylib_has_a_build_subproject(self):
        make = (ROOT / "Makefile").read_text()
        libs = set(re.findall(r"\$\(THEOS_OBJ_DIR\)/([\w-]+)\.dylib", make))
        dynamic = {"libcolorpicker", "libFLEX", "YouTubeDislikesReturn",
                   "iSponsorBlock", "YTUHD"}
        subprojects = make.split("SUBPROJECTS += ", 1)[1].split("\n", 1)[0]
        for library in sorted(libs - dynamic):
            with self.subTest(library=library):
                self.assertIn("Tweaks/" + library, subprojects)
        self.assertIn("Tweaks/Return-YouTube-Dislikes", subprojects)
        self.assertIn("Tweaks/FLEXing/libflex", subprojects)
        self.assertIn("Tweaks/iSponsorBlock", make)
        self.assertIn("Tweaks/YTUHD", make)

    def test_youmute_module_is_compiled_and_checked_out(self):
        make = (ROOT / "Makefile").read_text()
        build = (ROOT / "Scripts/build_circleci_ipa.sh").read_text()
        self.assertIn("Tweaks/YouMute", build)
        self.assertIn("SUBPROJECTS += Tweaks/Alderis", make)
        self.assertIn("Tweaks/YouMute", make)
        self.assertIn("$(THEOS_OBJ_DIR)/YouMute.dylib", make)

    def test_packager_uses_real_case_sensitive_stage_script(self):
        make = (ROOT / "Makefile").read_text()
        self.assertTrue((ROOT / "Tools/stage-ffmpeg.sh").is_file())
        self.assertEqual(make.count("bash Tools/stage-ffmpeg.sh"), 2)
        self.assertNotIn("bash tools/stage-ffmpeg.sh", make)

    def test_sideload_package_requires_iSponsorBlock_and_YTUHD(self):
        script = (ROOT / "Scripts/build_circleci_ipa.sh").read_text()
        self.assertIn("SPONSORBLOCK_ENABLED=1 SIDELOAD=1", script)
        self.assertIn("YTUHD_ENABLED=1", script)
        verify = (ROOT / "Scripts/verify_ipa.py").read_text()
        for filename in ("YouPiP.dylib", "YouTubeDislikesReturn.dylib",
                         "YTUHD.dylib", "iSponsorBlock.dylib"):
            self.assertIn(filename, verify)


if __name__ == "__main__":
    unittest.main()
