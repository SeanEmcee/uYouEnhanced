"""Source-only safeguards for the intentionally opt-in CircleCI IPA build."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".circleci" / "config.yml"
BUILD = ROOT / "Scripts" / "build_circleci_ipa.sh"
VERIFY = ROOT / "Scripts" / "verify_ipa.py"


class CircleCIIPAGates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = CONFIG.read_text(encoding="utf-8")
        cls.script = BUILD.read_text(encoding="utf-8")

    def test_live_url_check_defaults_off_and_runs_on_linux(self):
        self.assertRegex(
            self.config,
            r"(?m)^  run_ipa_url_check:\n    type: boolean\n    default: false"
        )
        self.assertIn('run_ipa_url_check >>', self.config)
        self.assertIn('ipa-url-check:', self.config)
        self.assertIn('python3 Scripts/normalize_circleci_ipa_url.py >/dev/null', self.config)
        self.assertNotIn('echo "$YOUTUBE_IPA_URL"', self.config)

    def test_macos_build_uses_secret_safe_normalizer(self):
        self.assertIn('Scripts/normalize_circleci_ipa_url.py', self.script)
        self.assertIn('YOUTUBE_IPA_URL="$(python3', self.script)
        self.assertNotIn('Invalid URL characters', self.script)
        private_download = self.script.split("Checking decrypted IPA", 1)[1].split(
            "unzip -tq", 1
        )[0]
        self.assertNotIn('--show-error', private_download)
        self.assertIn('test_circleci_ipa*.py', self.config)

    def test_build_gate_defaults_off(self):
        self.assertRegex(
            self.config,
            r"(?m)^  run_ipa_build:\n    type: boolean\n    default: false"
        )

    def test_branch_specific_and_approval_required(self):
        self.assertRegex(
            self.config,
            r"(?s)- approve-youtube-ipa:\n"
            r"\s+type: approval.*?"
            r"- build-youtube-ipa:\n"
            r"\s+requires:\n\s+- approve-youtube-ipa"
        )
        self.assertGreaterEqual(self.config.count("- pip-lab-v12"), 2)
        self.assertIn('CIRCLE_BRANCH', self.script)

    def test_explicit_macos_executor(self):
        self.assertIn('xcode: "26.5"', self.config)
        self.assertIn('resource_class: m4pro.medium', self.config)

    def test_private_source_url_not_committed(self):
        self.assertIn("YOUTUBE_IPA_URL", self.script)
        self.assertNotRegex(
            self.script + self.config,
            r"https://[^\s\"']+\.(?:ipa|zip)\?"
        )
        self.assertNotIn("echo $YOUTUBE_IPA_URL", self.script)
        self.assertNotIn("set -x", self.script)

    def test_download_before_spending_long_build_time(self):
        self.assertLess(self.script.index("Checking decrypted IPA"),
                        self.script.index("brew install"))
        self.assertIn("unzip -tq", self.script)

    def test_mandatory_hooks_and_sidecar_preserved(self):
        self.assertIn("apply_lc_pip.py", self.script)
        self.assertIn("apply_lc_playback.py", self.script)
        self.assertIn("apply_lc_streaming_v11.py", self.script)
        self.assertIn("CFBundleAlternateIcons", self.script)
        self.assertIn("verify_ipa.py", self.script)
        self.assertTrue(VERIFY.is_file())

    def test_results_contain_only_finished_ipa_and_checksum(self):
        self.assertIn("shasum -a 256", self.script)
        self.assertIn("path: build-artifacts", self.config)
        self.assertNotIn("path: .circleci-build", self.config)

    def test_never_uses_github_actions_minutes(self):
        self.assertNotIn("workflow_dispatch", self.config)
        self.assertNotIn("actions/upload-artifact", self.config)


if __name__ == "__main__":
    unittest.main()
