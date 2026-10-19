#!/usr/bin/env bash
# Theos Jailed's insert_dylib CLI shim. LIEF is installed and smoke-tested
# before any expensive dependencies or compilation. Do not expose IPA URLs.
set -Eeuo pipefail
set +x
: "${CIRCLECI_LIEF_PYTHON:?LIEF injector Python was not initialized}"
: "${CIRCLECI_LIEF_SCRIPT:?LIEF injector script was not initialized}"
exec "$CIRCLECI_LIEF_PYTHON" "$CIRCLECI_LIEF_SCRIPT" "$@"
