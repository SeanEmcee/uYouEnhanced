#!/usr/bin/env bash
# Build verified arm64 iOS static decoder libraries before compiling any tweak.
# This is intentionally explicit: the nested Theos subproject's object
# prerequisite rules may not fire when invoked from a parent aggregate.mk.
set -Eeuo pipefail
set +x
cd "$(dirname "$0")/.."
folder="Tweaks/YTUHD"
[[ -f "$folder/Makefile" ]] || { echo "Missing modern YTUHD checkout" >&2; exit 2; }

python3 Scripts/prepare_circleci_ytuhd.py --folder "$folder"
for cmd in xcrun make meson ninja; do
  command -v "$cmd" >/dev/null || { echo "Missing decoder build tool: $cmd" >&2; exit 2; }
done
xcrun --sdk iphoneos --show-sdk-path >/dev/null || {
  echo "Xcode iPhoneOS SDK unavailable for decoder cross-compilation" >&2
  exit 2
}
# Confirm host and destination before invoking untrusted third-party scripts.
[[ "$(uname -s)" == Darwin ]] || { echo "Decoder archives require macOS/Xcode" >&2; exit 2; }

for entry in "libvpx:libvpx_ios/libvpx.a" "dav1d:dav1d_ios/libdav1d.a"; do
  library="${entry%%:*}"
  archive="$folder/vendor/${entry#*:}"
  if [[ ! -s "$archive" ]]; then
    echo "Building pinned $library arm64 iOS static library (one-time setup)."
    bash "$folder/vendor/build_$library.sh"
  else
    echo "Using existing $library arm64 iOS static library."
  fi
  [[ -s "$archive" ]] || { echo "Decoder archive missing: $archive" >&2; exit 2; }
  archs="$(xcrun lipo -archs "$archive" 2>/dev/null)" || {
    echo "Decoder archive failed lipo verification: $archive" >&2; exit 2;
  }
  case " $archs " in
    *" arm64 "*) ;;
    *) echo "Decoder archive is not built for arm64 iOS: $archive" >&2; exit 2 ;;
  esac
done
python3 Scripts/prepare_circleci_ytuhd.py --folder "$folder" --check-archives
echo "Modern YTUHD static decoder dependencies ready before tweak compilation."
