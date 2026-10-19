#!/usr/bin/env bash
# Unsigned uYouEnhanced IPA builder for CircleCI macOS. Never log the IPA URL.
set -Eeuo pipefail
set +x
umask 077
export HOMEBREW_NO_AUTO_UPDATE=1
export HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK=1
export HOMEBREW_NO_INSTALL_UPGRADE=1
export HOMEBREW_NO_INSTALL_CLEANUP=1
export HOMEBREW_NO_ENV_HINTS=1
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
[[ "$(printenv CIRCLE_BRANCH || true)" == pip-lab-v12 ]] || { echo "Refusing unexpected branch" >&2; exit 2; }
[[ "$(printenv RUN_IPA_BUILD || true)" == true ]] || { echo "Build approval gate missing" >&2; exit 2; }
# Remove accidental leading/trailing copied whitespace, but reject any
# whitespace *within* the URL. The validator reads CircleCI's secret only
# through the environment and returns the value through captured stdout.
# Do not echo this variable, including when the source provider returns 4xx.
command -v python3 >/dev/null || { echo "Python 3 is required" >&2; exit 2; }
YOUTUBE_IPA_URL="$(python3 Scripts/normalize_circleci_ipa_url.py)" || exit 2
export YOUTUBE_IPA_URL
for tool in brew git curl unzip zip python3 xcodebuild shasum; do
  command -v "$tool" >/dev/null || { echo "Missing tool: $tool" >&2; exit 2; }
done
mkdir -p .circleci-build build-artifacts
chmod 700 .circleci-build build-artifacts
echo "Checking decrypted IPA before expensive compilation (private URL hidden)"
curl --fail --location --silent --retry 2 --retry-delay 3 \
  --connect-timeout 25 --max-time 900 --proto '=https' --proto-redir '=https' \
  -o .circleci-build/YouTube.ipa "$YOUTUBE_IPA_URL" || {
    echo "Source download failed: refresh the CircleCI project secret" >&2; exit 2;
  }
unzip -tq .circleci-build/YouTube.ipa >/dev/null || { echo "Invalid IPA archive" >&2; exit 2; }
unzip -Z1 .circleci-build/YouTube.ipa | grep -Fx 'Payload/YouTube.app/Info.plist' >/dev/null || {
  echo "Missing expected Payload/YouTube.app/Info.plist" >&2; exit 2;
}
unzip -q .circleci-build/YouTube.ipa -d .circleci-build/source
PB=/usr/libexec/PlistBuddy
YT_VERSION="$("$PB" -c 'Print :CFBundleShortVersionString' .circleci-build/source/Payload/YouTube.app/Info.plist)"
# Do not pass the signed IPA link to submodule clones, Homebrew or build tools.
unset YOUTUBE_IPA_URL
[[ "$YT_VERSION" =~ ^[0-9]+([.][0-9]+){1,3}$ ]] || { echo "Invalid YouTube version" >&2; exit 2; }
echo "Validated YouTube version $YT_VERSION"

# Fetch only compiled submodules: old unrelated pinned gitlinks may be missing.
set -- Tweaks/Alderis Tweaks/DontEatMyContent Tweaks/FLEXing \
  Tweaks/Return-YouTube-Dislikes Tweaks/YTABConfig Tweaks/YouGroupSettings \
  Tweaks/YTIcons Tweaks/YouLoop Tweaks/YouPiP Tweaks/YouQuality \
  Tweaks/YouSlider Tweaks/YouSpeed Tweaks/YouTimeStamp Tweaks/YTHoldForSpeed \
  Tweaks/YTVideoOverlay Tweaks/YTweaks Tweaks/YouTubeLegacy \
  Tweaks/iSponsorBlock Tweaks/RemoteLog Tweaks/PSHeader \
  Tweaks/YouTubeHeader Tweaks/protobuf Tweaks/libundirect
if [[ "$(printenv MODERN_YTUHD || true)" != true ]]; then set -- "$@" Tweaks/YTUHD; fi
# Catch stale .gitmodules entries and mistyped names before any network clone.
# Only an index mode 160000 gitlink is valid for git submodule update.
for module in "$@"; do
  mode="$(git ls-files --stage -- "$module" | awk 'NR == 1 { print $1 }')"
  if [[ "$mode" != "160000" ]]; then
    echo "Build submodule is not a tracked gitlink: $module" >&2
    exit 2
  fi
done
git submodule update --init --recursive -- "$@"
# The Return YouTube Dislikes tweak imports <YouTubeHeader/*.h>. Ensure the
# tracked header submodule is checked out before expensive compilation.
python3 Scripts/check_circleci_headers.py
if [[ "$(printenv MODERN_YTUHD || true)" == true ]]; then
  rm -rf Tweaks/YTUHD
  git clone --depth 1 --recurse-submodules --branch master https://github.com/PoomSmart/YTUHD.git Tweaks/YTUHD
  python3 Scripts/apply_lc_hwvp9.py
fi
for script in apply_lc_pip.py apply_lc_shorts.py apply_lc_preview.py \
  apply_lc_counts.py apply_lc_playback.py apply_lc_miniplayer.py \
  apply_lc_miniplayer_v9.py apply_lc_performance_v10.py \
  apply_lc_hardware_diagnostic.py; do
  python3 "Scripts/$script"
done
if [[ "$(printenv MODERN_YTUHD || true)" == true ]]; then
  python3 Scripts/apply_lc_decoder_path_v11.py
  python3 Scripts/apply_lc_av1_priority_v12.py
fi
python3 Scripts/apply_lc_streaming_v11.py

echo "Preparing macOS dependencies (no unrelated Homebrew upgrades)."
bash Scripts/install_circleci_macos_deps.sh
mkdir -p "$HOME/.local/bin"
export PATH="$(brew --prefix make)/libexec/gnubin:$HOME/.local/bin:$PATH"
export THEOS="$ROOT/.circleci-build/theos"
git clone --quiet --depth 1 --recurse-submodules https://github.com/theos/theos.git "$THEOS"
SDK_VERSION=26.5
git clone --quiet -n --depth 1 --filter=tree:0 https://github.com/aricloverEXTRA/sdks.git .circleci-build/sdks
git -C .circleci-build/sdks sparse-checkout set --no-cone "iPhoneOS$SDK_VERSION.sdk"
git -C .circleci-build/sdks checkout --quiet
mkdir -p "$THEOS/sdks"
mv ".circleci-build/sdks/iPhoneOS$SDK_VERSION.sdk" "$THEOS/sdks/"
git clone --quiet --depth 1 https://github.com/qnblackcat/theos-jailed.git .circleci-build/theos-jailed
.circleci-build/theos-jailed/install
while IFS= read -r -d '' file; do
  if grep -q '| head' "$file" 2>/dev/null; then
    sed -i '' 's/| head/2>\/dev\/null | head/g' "$file" 2>/dev/null || true
  fi
done < <(find "$THEOS" -type f \( -name '*.sh' -o -name '*.mk' \) -print0)
pipx install --force https://github.com/asdfzxcvbn/pyzule-rw/archive/main.zip
command -v cyan >/dev/null || { echo "Cyan unavailable" >&2; exit 2; }
curl --fail --location --silent --show-error --proto '=https' --proto-redir '=https' \
  -o "$HOME/.local/bin/tbd" https://github.com/inoahdev/tbd/releases/download/2.2/tbd-mac
chmod 755 "$HOME/.local/bin/tbd"
if [[ "$(printenv BUILD_FFMPEG || true)" == true ]]; then
  echo "Rebuilding FFmpegKit from source (may take 30-90+ macOS minutes)"
  bash Tools/fetch-ffmpegkit.sh
fi
rm -rf Payload
cp -R .circleci-build/source/Payload ./Payload
export UYOU_VERSION=3.0.4
make package THEOS_PACKAGE_SCHEME=rootless IPA=Payload/YouTube.app \
  FINALPACKAGE=1 YTUHD_ENABLED=1 SPONSORBLOCK_ENABLED=1 SIDELOAD=1 \
  SDK_VERSION="$SDK_VERSION" BUNDLE_ID=com.google.ios.youtube DISPLAY_NAME=YouTube
PACKAGE_IPA="$(find packages -maxdepth 1 -type f -name '*.ipa' -print -quit)"
[[ -n "$PACKAGE_IPA" && -s "$PACKAGE_IPA" ]] || { echo "Theos produced no IPA" >&2; exit 2; }

git clone --quiet -n --depth 1 --filter=tree:0 https://github.com/BillyCurtis/OpenYouTubeSafariExtension.git .circleci-build/Safari
git -C .circleci-build/Safari sparse-checkout set --no-cone OpenYouTubeSafariExtension.appex
git -C .circleci-build/Safari checkout --quiet
EXTENSION=.circleci-build/Safari/OpenYouTubeSafariExtension.appex
[[ -d "$EXTENSION" ]] || { echo "Missing Safari extension" >&2; exit 2; }
set -- "$EXTENSION"
for deb in packages/*.deb; do
  [[ -f "$deb" ]] && set -- "$@" "$deb"
done
[[ "$#" -gt 1 ]] || { echo "No tweak packages found" >&2; exit 2; }
TMP_IPA="$(printf '.circleci-build/uYouEnhanced_%s_v3.0.4.ipa' "$YT_VERSION")"
cyan -i "$PACKAGE_IPA" -o "$TMP_IPA" -uwef "$@" -n YouTube -b com.google.ios.youtube
[[ -s "$TMP_IPA" ]] || { echo "Cyan produced no IPA" >&2; exit 2; }
zip -q -d "$TMP_IPA" 'Payload/*/SC_Info/*' 'Payload/*/SC_Info' 2>/dev/null || true
unzip -Z1 "$TMP_IPA" | grep '\.appex/' | sed 's|^\(.*\.appex\)/.*|\1|' \
  | sort -u >.circleci-build/appex-list.txt || true
while IFS= read -r ext; do
  [[ -n "$ext" ]] || continue
  [[ "$ext" == */PlugIns/* ]] && continue
  zip -q -d "$TMP_IPA" "$ext/*" || true
done <.circleci-build/appex-list.txt
# Preserve the alternate app icons present in the original GitHub workflow.
# Validate opacity/size so iOS does not refuse malformed alternate icons.
mkdir -p .circleci-build/iconwork/icons
(
  cd .circleci-build/iconwork
  unzip -q "$ROOT/$TMP_IPA" 'Payload/YouTube.app/Info.plist'
  for source_icon in "$ROOT"/Localizations/uYouPlus.bundle/AppIcons/*.png; do
    [[ -f "$source_icon" ]] || continue
    target="icons/$(basename "$source_icon")"
    pngquant --quality=80-95 --strip --skip-if-larger "$source_icon" \
      --output "$target" >/dev/null 2>&1 || true
    [[ -f "$target" ]] || cp "$source_icon" "$target"
  done
  for icon in icons/*.png; do
    [[ -f "$icon" ]] || continue
    spec="$(sips -g pixelWidth -g pixelHeight -g hasAlpha "$icon" 2>/dev/null |
      awk '/pixelWidth/{w=$2} /pixelHeight/{h=$2} /hasAlpha/{a=$2} END{print w"x"h" alpha="a}')"
    [[ "$spec" == "1024x1024 alpha=no"* ]] || {
      echo "Bad alternate icon dimensions or alpha: $(basename "$icon")" >&2
      exit 2
    }
  done
  plist=Payload/YouTube.app/Info.plist
  for key in CFBundleIcons 'CFBundleIcons~ipad'; do
    "$PB" -c "Add :$key dict" "$plist" 2>/dev/null || true
    "$PB" -c "Add :$key:CFBundleAlternateIcons dict" "$plist" 2>/dev/null || true
  done
  for icon in icons/*.png; do
    [[ -f "$icon" ]] || continue
    name="$(basename "$icon" .png)"
    cp "$icon" "Payload/YouTube.app/$name.png"
    for key in CFBundleIcons 'CFBundleIcons~ipad'; do
      "$PB" -c "Add :$key:CFBundleAlternateIcons:$name dict" "$plist" 2>/dev/null || true
      "$PB" -c "Add :$key:CFBundleAlternateIcons:$name:CFBundleIconFiles array" "$plist" 2>/dev/null || true
      "$PB" -c "Add :$key:CFBundleAlternateIcons:$name:CFBundleIconFiles:0 string $name" "$plist" 2>/dev/null || true
    done
  done
  zip -q "$ROOT/$TMP_IPA" "$plist" Payload/YouTube.app/*.png
)
FINAL="$(printf 'build-artifacts/uYouEnhanced_%s_v3.0.5.ipa' "$YT_VERSION")"
cp "$TMP_IPA" "$FINAL"
python3 Scripts/verify_ipa.py "$FINAL"
shasum -a 256 "$FINAL" >"$FINAL.sha256"
echo "Verified unsigned SideStore-ready IPA: $(basename "$FINAL")"
