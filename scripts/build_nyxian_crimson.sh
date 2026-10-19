#!/usr/bin/env bash
set -Eeuo pipefail
set +x
umask 077
export HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK=1 HOMEBREW_NO_INSTALL_UPGRADE=1 HOMEBREW_NO_INSTALL_CLEANUP=1
UPSTREAM_SHA=350dd8dbeb796bc0ff5bc91ef770f1a2994432e7
BASE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$BASE"
[[ "${CIRCLE_BRANCH:-}" == nyxian-crimson-circleci ]] || { echo 'Wrong CI branch' >&2; exit 2; }
[[ "${RUN_CRIMSON_BUILD:-}" == true ]] || { echo 'Missing manual build gate' >&2; exit 2; }
[[ "$(uname -s)" == Darwin ]] || { echo 'Requires macOS / Xcode' >&2; exit 2; }
[[ -n "${CRIMSON_ASSET_URL:-}" && "$CRIMSON_ASSET_URL" == https://* ]] || { echo 'Missing HTTPS CircleCI CRIMSON_ASSET_URL secret' >&2; exit 2; }
for cmd in git python3 unzip xcodebuild brew shasum curl zip; do command -v "$cmd" >/dev/null || exit 2; done
mkdir -p .crimson-work build-artifacts
chmod 700 .crimson-work build-artifacts
echo 'Downloading approved assets (secret URL omitted)'
curl --fail --location --silent --show-error --retry 2 --output .crimson-work/approved-assets.zip "$CRIMSON_ASSET_URL"
expected="$(tr -d '[:space:]' < assets/approved-assets.sha256)"
actual="$(shasum -a 256 .crimson-work/approved-assets.zip | awk '{print $1}')"
[[ "$actual" == "$expected" ]] || { echo 'Approved asset hash mismatch' >&2; exit 2; }
python3 scripts/unpack_assets.py .crimson-work/approved-assets.zip .crimson-work/approved-assets
echo 'Fetching pinned Nyxian upstream revision'
mkdir -p .crimson-work/Nyxian
(
  cd .crimson-work/Nyxian
  git init -q
  git remote add origin https://github.com/emexlab/Nyxian.git
  git fetch --depth=1 origin "$UPSTREAM_SHA"
  git -c advice.detachedHead=false checkout --detach -q FETCH_HEAD
  [[ "$(git rev-parse HEAD)" == "$UPSTREAM_SHA" ]]
  git submodule update --init --recursive --progress
)
python3 scripts/apply_crimson_assets.py .crimson-work/Nyxian .crimson-work/approved-assets
echo 'Preparing installed Homebrew build dependencies'
for dep in ldid dpkg libarchive pkgconf cmake openssl ninja; do
  if ! brew list --versions "$dep" >/dev/null 2>&1; then brew install "$dep"; fi
done
echo 'Compiling from Nyxian source with Xcode'
(
  cd .crimson-work/Nyxian
  export SRCROOT="$PWD"
  CHECK_DEPS=0 make all
)
IPA=.crimson-work/Nyxian/Nyxian.ipa
python3 scripts/verify_unsigned_ipa.py "$IPA"
cp "$IPA" build-artifacts/Nyxian-Crimson-RedApple-UNSIGNED.ipa
shasum -a 256 build-artifacts/Nyxian-Crimson-RedApple-UNSIGNED.ipa > build-artifacts/Nyxian-Crimson-RedApple-UNSIGNED.ipa.sha256
echo 'Unsigned IPA verified. Download from CircleCI Artifacts and sign with a supported signer.'
