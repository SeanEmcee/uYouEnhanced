#!/usr/bin/env python3
"""Repair modern YTUHD's vendor paths when nested under uYouEnhanced.

YTUHD's standalone Makefile uses THEOS_PROJECT_DIR, but the parent build
exports the uYouEnhanced root, not the nested Tweaks/YTUHD project directory.
This produces missing vpx/dav1d headers and archives even after recursive
submodule checkout. Fix both library include/link paths in the *temporary*
checkout; never modify the pinned YTUHD gitlink or bypass its decoder paths.
"""
import argparse
from pathlib import Path
import sys

MARKER = "# CIRCLECI_NESTED_YTUHD_VENDOR_ROOT"
OLD = "$(THEOS_PROJECT_DIR)/vendor/"
NEW = "$(CIRCLECI_YTUHD_DIR)/vendor/"
DECLARATION = (
    MARKER + "\n"
    "CIRCLECI_YTUHD_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))\n"
)
HEADERS = ("vendor/libvpx/vpx/vpx_decoder.h",
           "vendor/dav1d/include/dav1d/dav1d.h")
SCRIPTS = ("vendor/build_libvpx.sh", "vendor/build_dav1d.sh")
ARCHIVES = ("vendor/libvpx_ios/libvpx.a",
            "vendor/dav1d_ios/libdav1d.a")


def patched_makefile(text: str) -> str:
    if MARKER in text:
        if OLD in text or NEW not in text:
            raise ValueError("Inconsistent nested YTUHD Makefile patch")
        return text
    # Fail closed if upstream Makefile has changed rather than silently
    # producing a binary with a missing decoder or incorrect vendor paths.
    if text.count(OLD) < 5:
        raise ValueError("Unrecognized YTUHD vendor paths; re-audit upstream Makefile")
    for fragment in ("libvpx.a", "libdav1d.a",
                     "HAMVPXVideoDecoder.m", "HAMDav1dVideoDecoder.m"):
        if fragment not in text:
            raise ValueError("Unexpected YTUHD Makefile missing " + fragment)
    modified = DECLARATION + text.replace(OLD, NEW)
    if OLD in modified:
        raise AssertionError("Unreplaced YTUHD dependency path")
    return modified


def validate_vendor_sources(folder: Path) -> list[str]:
    return [p for p in HEADERS + SCRIPTS if not (folder / p).is_file()]


def validate_vendor_archives(folder: Path) -> list[str]:
    return [p for p in ARCHIVES
            if not (folder / p).is_file() or (folder / p).stat().st_size < 128]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", type=Path,
                        default=Path(__file__).resolve().parents[1] / "Tweaks/YTUHD")
    parser.add_argument("--source-only", action="store_true",
                        help="validate/rewrite Makefile without vendor submodule checkout")
    parser.add_argument("--check-archives", action="store_true")
    args = parser.parse_args()
    file = args.folder / "Makefile"
    try:
        modified = patched_makefile(file.read_text(encoding="utf-8"))
        if modified != file.read_text(encoding="utf-8"):
            file.write_text(modified, encoding="utf-8")
        if not args.source_only:
            missing = validate_vendor_sources(args.folder)
            if missing:
                raise ValueError("Missing initialized decoder sources: " + ", ".join(missing))
        if args.check_archives:
            missing = validate_vendor_archives(args.folder)
            if missing:
                raise ValueError("Missing decoder static archives: " + ", ".join(missing))
    except (ValueError, OSError) as err:
        print("YTUHD dependency check failed: " + str(err), file=sys.stderr)
        return 2
    print("YTUHD nested vendor include/link paths validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
