#!/usr/bin/env python3
"""Validate pinned YouTube headers before spending macOS compilation credits.

Theos resolves <YouTubeHeader/YTLikeStatus.h> using the root-level
ADDITIONAL_CFLAGS=-I$(THEOS_PROJECT_DIR)/Tweaks. The tracked
Tweaks/YouTubeHeader submodule must actually be initialized.
No credentials or external requests are used here.
"""
from pathlib import Path
import sys

REQUIRED_HEADERS = (
    "YTLikeStatus.h",
    "YTSettingsCell.h",
)
THEOS_INCLUDE = "-I$(THEOS_PROJECT_DIR)/Tweaks"


def validate_header_layout(root: Path) -> list[str]:
    """Return diagnostics without printing source files or private values."""
    missing = []
    root = Path(root)
    makefile = root / "Makefile"
    if not makefile.is_file():
        missing.append("Root Makefile missing")
    elif THEOS_INCLUDE not in makefile.read_text(encoding="utf-8"):
        missing.append("Makefile is missing the Theos Tweaks include search path")
    headers = root / "Tweaks" / "YouTubeHeader"
    for name in REQUIRED_HEADERS:
        if not (headers / name).is_file():
            missing.append("Missing Tweaks/YouTubeHeader/" + name)
    return missing


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors = validate_header_layout(root)
    if errors:
        for error in errors:
            print("YouTube header preflight: " + error, file=sys.stderr)
        print(
            "Initialize the tracked Tweaks/YouTubeHeader git submodule "
            "and verify the parent Makefile compiler search path.",
            file=sys.stderr,
        )
        return 2
    print(
        "YouTube header preflight passed: both Return YouTube Dislikes "
        "headers and Theos include path are present."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
