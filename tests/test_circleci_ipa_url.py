"""No-secret tests for CircleCI's protected source-URL normalization."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

from Scripts.normalize_circleci_ipa_url import InvalidIPAURL, normalize_ipa_url

SAMPLE = "https://example.invalid/YouTube.ipa?expires=123&token=SYNTHETIC"
CLI = Path(__file__).resolve().parents[1] / "Scripts" / "normalize_circleci_ipa_url.py"


class SourceURLTests(unittest.TestCase):
    def test_clean_signed_url_is_unchanged(self):
        self.assertEqual(normalize_ipa_url(SAMPLE), SAMPLE)

    def test_surrounding_ascii_whitespace_is_removed(self):
        self.assertEqual(normalize_ipa_url("  \t\r\n" + SAMPLE + "\n  \t"), SAMPLE)

    def test_encoded_whitespace_is_preserved(self):
        original = "https://example.invalid/a%20b.ipa?x=%0A&y=abc"
        self.assertEqual(normalize_ipa_url(original), original)

    def test_rejects_literal_interior_whitespace(self):
        for char in (" ", "\t", "\r", "\n", "\v", "\f", "\u00a0"):
            url = SAMPLE.replace("token=", "tok" + char + "en=")
            with self.subTest(space=repr(char)), self.assertRaises(InvalidIPAURL):
                normalize_ipa_url(url)

    def test_rejects_wrappers_and_labels(self):
        for candidate in ("URL: " + SAMPLE, "<" + SAMPLE + ">", "'" + SAMPLE + "'",
                          "[" + SAMPLE + "](https://example.invalid)"):
            with self.subTest(candidate_type=candidate[:4]), self.assertRaises(InvalidIPAURL):
                normalize_ipa_url(candidate)

    def test_rejects_non_https_and_empty_values(self):
        for value in ("", " \t\r\n", "http://example.invalid/file.ipa",
                      "ftp://example.invalid/file.ipa", "https://"):
            with self.subTest(value_class=len(value)), self.assertRaises(InvalidIPAURL):
                normalize_ipa_url(value)

    def test_rejects_embedded_credentials_and_fragments(self):
        for value in ("https://user:pass@example.invalid/file.ipa",
                      SAMPLE + "#fragment", "https://example.invalid:999999/file.ipa"):
            with self.assertRaises(InvalidIPAURL):
                normalize_ipa_url(value)

    def test_rejects_overly_long_or_control_character_url(self):
        with self.assertRaises(InvalidIPAURL):
            normalize_ipa_url("https://example.invalid/" + "a" * 17000)
        with self.assertRaises(InvalidIPAURL):
            normalize_ipa_url(SAMPLE + "\x00")

    def test_cli_returns_normalized_value_only_on_stdout(self):
        env = dict(os.environ, YOUTUBE_IPA_URL=" \n" + SAMPLE + "\r ")
        process = subprocess.run([sys.executable, str(CLI)],
                                 env=env, capture_output=True, text=True, check=False)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(process.stdout, SAMPLE)
        self.assertEqual(process.stderr, "")

    def test_cli_error_never_contains_token(self):
        secret = "HIGHLY_PRIVATE_FAKE_TOKEN"
        env = dict(os.environ, YOUTUBE_IPA_URL="https://example.invalid/file.ipa?token="
                   + secret + " literal-space")
        process = subprocess.run([sys.executable, str(CLI)],
                                 env=env, capture_output=True, text=True, check=False)
        self.assertEqual(process.returncode, 2)
        self.assertEqual(process.stdout, "")
        self.assertIn("within the URL", process.stderr)
        self.assertNotIn(secret, process.stderr)


if __name__ == "__main__":
    unittest.main()
