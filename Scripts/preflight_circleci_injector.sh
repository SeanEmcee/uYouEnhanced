#!/usr/bin/env bash
# Fail before costly Homebrew/Theos/codec compilation if modern YouTube's
# executable cannot accept a verified Mach-O load command.
set -Eeuo pipefail
set +x
cd "$(dirname "$0")/.."
ROOT="$PWD"
PB=/usr/libexec/PlistBuddy
INPUT="$ROOT/.circleci-build/source/Payload/YouTube.app"
[[ "$(uname -s)" == Darwin ]] || { echo "IPA injector probe requires macOS" >&2; exit 2; }
[[ -f "$INPUT/Info.plist" ]] || { echo "Validated host IPA not unpacked" >&2; exit 2; }
executable="$("$PB" -c 'Print :CFBundleExecutable' "$INPUT/Info.plist")"
[[ "$executable" != */* && -n "$executable" ]] || {
  echo "Invalid source IPA executable name" >&2; exit 2;
}
[[ -f "$INPUT/$executable" ]] || { echo "Host IPA executable missing" >&2; exit 2; }

# Modern LIEF has cp315 arm64-macOS wheels; refuse source compilation in CI.
VENV="$ROOT/.circleci-build/lief-venv"
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip --disable-pip-version-check install -q \
  --only-binary=:all: 'lief==1.0.0'
"$VENV/bin/python" -c 'import lief; assert lief.MachO' || {
  echo "Modern LIEF Mach-O runtime unavailable" >&2; exit 2;
}

# A disposable executable copy is modified; the original host app remains
# untouched. This verifies real binary rewriting before the expensive build.
probe="$ROOT/.circleci-build/inject-probe"
cp -p "$INPUT/$executable" "$probe"
trap 'rm -f "$probe"' EXIT
echo "Probing modern Mach-O injection on original host executable (private source untouched)."
"$VENV/bin/python" Scripts/macho_lief_inject.py \
  --inplace --weak --no-strip-codesig \
  '@rpath/uYouEnhanced.dylib' "$probe"
# Validate the output using Apple's independent Mach-O reader as well.
if ! otool -L "$probe" | grep -F '@rpath/uYouEnhanced.dylib' >/dev/null; then
  echo "Mach-O load command not visible to Apple otool" >&2
  exit 2
fi
echo "Modern IPA injector preflight passed before native compilation."
