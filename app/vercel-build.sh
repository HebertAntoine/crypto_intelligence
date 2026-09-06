#!/usr/bin/env bash
# Build the Flutter web app on Vercel.
#
# Vercel's build image has no Flutter SDK, so it is fetched here. The download
# is pinned to an exact version: an unpinned "stable" would silently change the
# toolchain between two deploys of identical source.
set -euo pipefail

FLUTTER_VERSION="3.27.1"
FLUTTER_DIR="${HOME}/flutter"

if [ ! -x "${FLUTTER_DIR}/bin/flutter" ]; then
  echo "Fetching Flutter ${FLUTTER_VERSION}..."
  curl -fsSL -o /tmp/flutter.tar.xz \
    "https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/flutter_linux_${FLUTTER_VERSION}-stable.tar.xz"
  mkdir -p "${HOME}"
  tar xf /tmp/flutter.tar.xz -C "${HOME}"
  rm /tmp/flutter.tar.xz
fi

export PATH="${FLUTTER_DIR}/bin:${PATH}"
# Vercel's checkout is not a Flutter-owned directory; without this, newer
# Flutter versions refuse to run over the "dubious ownership" git check.
git config --global --add safe.directory "${FLUTTER_DIR}" || true

flutter --version
flutter config --enable-web --no-analytics
flutter pub get

# API_BASE_URL can point at a live backend. If it is missing, the app renders
# the bundled read-only snapshots generated into assets/static_api/.
if [ -z "${API_BASE_URL:-}" ]; then
  echo "API_BASE_URL is not set. Building with bundled static API snapshots." >&2
fi

flutter build web --release \
  --dart-define=API_BASE_URL="${API_BASE_URL:-}" \
  --pwa-strategy=none

echo "Built to build/web"
