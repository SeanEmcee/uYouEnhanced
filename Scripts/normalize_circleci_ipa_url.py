#!/usr/bin/env python3
"""Normalize owner-supplied signed IPA URLs without logging their contents.

Only ASCII whitespace at the *edges* may be removed. Interior whitespace,
copied Markdown wrappers and non-HTTPS URLs are errors, never silently fixed.
Print the normalized URL only to stdout so Bash can capture it without logs.
"""
import os
import sys
from urllib.parse import urlsplit


class InvalidIPAURL(ValueError):
    """A deliberately token-free diagnostic."""


def normalize_ipa_url(raw: str) -> str:
    if not isinstance(raw, str):
        raise InvalidIPAURL("IPA URL is not a string")
    url = raw.strip(" \t\r\n")
    if not url:
        raise InvalidIPAURL("CircleCI YOUTUBE_IPA_URL is missing")
    if len(url) > 16384:
        raise InvalidIPAURL("IPA URL exceeds the supported length")
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in url):
        raise InvalidIPAURL(
            "IPA URL contains whitespace or control characters within the URL; "
            "set the CircleCI secret to a single unbroken direct HTTPS link"
        )
    if not url.startswith("https://"):
        raise InvalidIPAURL(
            "IPA URL must start directly with https:// (without labels or quotes)"
        )
    try:
        parts = urlsplit(url)
        hostname = parts.hostname
        port = parts.port
        username = parts.username
        password = parts.password
    except ValueError:
        raise InvalidIPAURL("IPA URL has an invalid HTTPS host") from None
    if parts.scheme != "https" or not hostname or not parts.netloc:
        raise InvalidIPAURL("IPA URL must have a valid HTTPS hostname")
    if username is not None or password is not None:
        raise InvalidIPAURL("IPA URL must not include credentials in its host")
    if parts.fragment:
        raise InvalidIPAURL("IPA URL must not include a fragment")
    if port is not None and not 1 <= port <= 65535:
        raise InvalidIPAURL("IPA URL has an invalid port")
    return url


if __name__ == "__main__":
    try:
        normalized = normalize_ipa_url(os.environ.get("YOUTUBE_IPA_URL", ""))
    except InvalidIPAURL as exc:
        print("Invalid CircleCI source URL: " + str(exc), file=sys.stderr)
        raise SystemExit(2) from None
    # Do NOT print this value to job logs; it is captured by Bash.
    sys.stdout.write(normalized)
