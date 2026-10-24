#!/usr/bin/env bash
# Source-only macOS build patch rehearsal on CircleCI's inexpensive Linux image.
# Never download the copyrighted host IPA, build tools, or consume macOS credits.
set -Eeuo pipefail
set +x
cd "$(dirname "$0")/.."
unset YOUTUBE_IPA_URL
[[ "${CIRCLE_BRANCH:-}" == "pip-lab-v12" || "${CIRCLE_BRANCH:-}" == "fix/youtube-controls-playback-v14" ]] || {
  echo "Refusing to replay sources outside pip-lab-v12" >&2
  exit 2
}
echo "Initializing pinned PiP, dislike, and header source dependencies."
git submodule update --init -- Tweaks/YouTubeHeader Tweaks/YouPiP Tweaks/Return-YouTube-Dislikes Tweaks/YouSpeed Tweaks/YTHoldForSpeed
python3 Scripts/check_circleci_headers.py

# This smoke clone intentionally avoids the large native decoder submodules:
# patch generators touch only the modern YTUHD Objective-C source and settings.
[[ ! -e Tweaks/YTUHD/Tweak.xm ]] || {
  echo "Unexpected pre-initialized YTUHD source checkout" >&2
  exit 2
}
revision="$(grep -E '^[0-9a-f]{40}$' Scripts/ytuhd_source_revision.txt)"
[[ "$revision" =~ ^[0-9a-f]{40}$ ]] || { echo "Missing pinned YTUHD SHA" >&2; exit 2; }
git init --quiet Tweaks/YTUHD
git -C Tweaks/YTUHD remote add origin https://github.com/PoomSmart/YTUHD.git
git -C Tweaks/YTUHD fetch --quiet --depth=1 origin "$revision"
git -C Tweaks/YTUHD checkout --quiet --detach FETCH_HEAD
python3 Scripts/prepare_circleci_ytuhd.py --folder Tweaks/YTUHD --source-only

echo "Rehearsing the macOS patch order on throwaway CI source files."
python3 Scripts/apply_lc_hwvp9.py
for script in   apply_lc_pip.py apply_lc_shorts.py apply_lc_preview.py   apply_lc_counts.py apply_lc_playback.py apply_lc_miniplayer.py   apply_lc_miniplayer_v9.py apply_lc_performance_v10.py   apply_lc_hardware_diagnostic.py; do
  python3 "Scripts/$script"
done
python3 Scripts/apply_lc_decoder_path_v11.py
python3 Scripts/apply_lc_av1_priority_v12.py
python3 Scripts/apply_lc_streaming_v11.py
python3 Scripts/apply_lc_controls_v14.py
python3 Scripts/check_circleci_patched_sources.py
echo "Source patch rehearsal succeeded (not an Xcode compilation)."
