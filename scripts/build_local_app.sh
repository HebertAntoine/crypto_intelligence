#!/usr/bin/env bash
# Build privée de l'application, avec l'onglet 🎬 Lexa, servie par le backend
# local sur http://127.0.0.1:8100/app/.
#
# Elle n'est jamais déployée : app/build/ est ignoré par Git, et la build
# publique (Vercel) est faite sans LEXA_ENABLED.
set -euo pipefail
cd "$(dirname "$0")/../app"
FLUTTER="${FLUTTER:-$HOME/flutter/bin/flutter}"
"$FLUTTER" build web --release \
  --base-href /app/ \
  --output build/web-local \
  --dart-define=LEXA_ENABLED=true \
  --dart-define=API_BASE_URL=http://127.0.0.1:8100 \
  --dart-define=STATIC_API_FALLBACK=false
echo "Build privée prête : http://127.0.0.1:8100/app/"
