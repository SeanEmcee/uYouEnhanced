#!/usr/bin/env python3
"""Smoke-audit generated Logos/Objective-C sources before costly macOS builds.

Requires the pinned YouPiP/RYD checkout and source patch chain to be applied
in a throwaway CI checkout. No secrets, network, Xcode, or actual compilation.
"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]

# %property defines runtime accessors in Logos, not necessarily static
# Objective-C declarations. Clang still needs the compiler-facing category.
PIp_PROPERTIES = {
    "lcEdgeHoldGesture", "lcEdgeHoldMode", "lcEdgeSavedSpeed",
    "lcEdgeAVPlayer", "lcEdgeAVItem", "lcEdgeSpeedVideoID",
    "lcRecoveryVideoIDV7", "lcRecoveryTriedV7",
    "lcRecoveryPendingV7", "lcRecoveryNextCheckV7",
}
PIp_METHODS = (
    "lcEdgeRestorePlayback", "lcEdgeRefreshHold",
    "lcEdgeHoldChanged:", "lcCheckVisibleLoadErrorV7",
)


# Static checks should inspect executable Objective-C tokens, not prose in
# generated // and /* */ comments or NSString / C string literals. Otherwise
# e.g. a migration comment mentioning UIApplication.keyWindow is a false fail.
_NON_CODE = re.compile(
    r'''@"(?:\\.|[^"\\])*"|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|//[^\n]*|/\*.*?\*/''',
    flags=re.DOTALL,
)


def objc_code_only(source: str) -> str:
    """Blank comments and quoted literals while preserving original newlines."""
    return _NON_CODE.sub(
        lambda match: re.sub(r"[^\n]", " ", match.group(0)), source
    )


def inspect_patch_output(root: Path) -> list[str]:
    issues: list[str] = []
    pip_tweak = root / "Tweaks/YouPiP/Tweak.x"
    pip_settings = root / "Tweaks/YouPiP/Settings.x"
    decoder_settings = root / "Tweaks/YTUHD/Settings.x"
    for path in (pip_tweak, pip_settings, decoder_settings):
        if not path.is_file():
            issues.append("Missing generated source " + str(path.relative_to(root)))
    if issues:
        return issues

    tweak = pip_tweak.read_text(encoding="utf-8")
    settings = pip_settings.read_text(encoding="utf-8")
    decoder = decoder_settings.read_text(encoding="utf-8")

    match = re.search(
        r"@interface\s+YTPlayerViewController\s*\(LCPiPLabCompileSurface\)"
        r"(.*?)@end", tweak, flags=re.S
    )
    if match is None:
        issues.append("Missing static interface for injected PiP properties")
    else:
        declarations = match.group(1)
        for name in sorted(PIp_PROPERTIES):
            if not re.search(r"\b" + re.escape(name) + r"\s*;", declarations):
                issues.append("Missing PiP property declaration: " + name)
        for name in PIp_METHODS:
            if name not in declarations:
                issues.append("Missing PiP selector declaration: " + name)
    for name in sorted(PIp_PROPERTIES):
        if not re.search(r"%property\s*\([^;]+\)\s*[^;]*\b"
                         + re.escape(name) + r"\s*;", tweak):
            issues.append("Missing Logos runtime accessor: " + name)

    for label, code in (("YouPiP", settings), ("YTUHD", decoder)):
        if re.search(r"\.\s*keyWindow\b", objc_code_only(code)):
            issues.append(label + " calls the deprecated UIApplication.keyWindow")
    if "static UIViewController *LCPresenter(void)" not in settings:
        issues.append("Missing scene-safe YouPiP presenter implementation")
    if "static UIViewController *LCYTUHDPresenter(void)" not in decoder:
        issues.append("Missing local YTUHD presenter implementation")
    if "LCPresenter()" in decoder:
        issues.append("YTUHD cannot call static YouPiP presenter")
    for marker in (
        "LC_PIP_LAB_V1", "LC_EDGE_HOLD_V4", "LC_PLAYBACK_STABILITY_V7",
        "LC_MINIPLAYER_GESTURE_GUARD_V8", "LC_MINIPLAYER_TOUCH_FIX_V9",
        "LC_4K_PERFORMANCE_V10",
    ):
        if marker not in tweak:
            issues.append("Missing PiP patch marker " + marker)
    return issues


def main() -> int:
    issues = inspect_patch_output(ROOT)
    if issues:
        for issue in issues:
            print("Patched source audit: " + issue, file=sys.stderr)
        return 2
    print("Patched source audit passed: state declarations, scene-safe presenters, patch chain.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
