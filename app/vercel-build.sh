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

# API_BASE_URL must be set in the Vercel project's environment variables and
# point at the backend, which runs elsewhere - Vercel's serverless runtime
# cannot host it (see docs/deployment.md). Building without it produces an app
# that calls its own origin and fails visibly rather than silently.
if [ -z "${API_BASE_URL:-}" ]; then
  echo "WARNING: API_BASE_URL is not set. The app will call its own origin," >&2
  echo "         which on Vercel has no API and will return 404s." >&2
fi

flutter build web --release \
  --dart-define=API_BASE_URL="${API_BASE_URL:-}"

echo "Built to build/web"
