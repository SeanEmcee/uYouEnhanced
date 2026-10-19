#!/usr/bin/env bash
# Install the minimum Homebrew formulae needed for the uYouEnhanced macOS build.
# CircleCI images include preinstalled Homebrew formulae; avoid cascade upgrades.
set -Eeuo pipefail
set +x

# Per brew(1), these settings prevent unnecessary upgrades of installed
# dependents (e.g. pyenv/ruby-build), formula upgrades, and automatic cleanup.
export HOMEBREW_NO_AUTO_UPDATE=1
export HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK=1
export HOMEBREW_NO_INSTALL_UPGRADE=1
export HOMEBREW_NO_INSTALL_CLEANUP=1
export HOMEBREW_NO_ENV_HINTS=1

command -v brew >/dev/null || {
  echo "Homebrew not present on CircleCI macOS image" >&2
  exit 2
}
formulae=(ldid dpkg make wget unzip jq pipx meson ninja gnu-sed
          autoconf automake libtool pkgconf pngquant)
missing=()
for formula in "${formulae[@]}"; do
  if ! brew list --formula --versions "$formula" >/dev/null 2>&1; then
    missing+=("$formula")
  fi
done

install_failed=false
if (( ${#missing[@]} )); then
  echo "Installing ${#missing[@]} missing Homebrew formulae (skipping installed versions and dependent upgrades)."
  # Homebrew can return nonzero when macOS CI post-install hooks fail even
  # though bottles and their executables were successfully installed.
  if ! brew install "${missing[@]}"; then
    install_failed=true
    echo "Homebrew reported an installation error; inspecting the actual dependencies." >&2
  fi
else
  echo "All requested Homebrew formulae already installed; skipping brew install."
fi

unavailable=()
for formula in "${formulae[@]}"; do
  if ! brew list --formula --versions "$formula" >/dev/null 2>&1; then
    unavailable+=("$formula")
  fi
done
if (( ${#unavailable[@]} )); then
  echo "Required Homebrew formulae unavailable: ${unavailable[*]}" >&2
  exit 2
fi

# Installed kegs alone are not enough; verify that the build commands work
# through the CircleCI image's PATH. Actual execution is verified by the
# subsequent Theos/tool installation steps.
missing_commands=()
for cmd in ldid dpkg gmake wget unzip jq pipx meson ninja gsed \
           autoconf automake glibtool pkgconf pngquant; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    missing_commands+=("$cmd")
  fi
done
if (( ${#missing_commands[@]} )); then
  echo "Homebrew installed formulae but commands were not linked: ${missing_commands[*]}" >&2
  exit 2
fi

if [[ "$install_failed" == true ]]; then
  echo "All required formulae and executable commands are present despite Homebrew warnings."
fi
echo "Homebrew dependency bootstrap complete."
