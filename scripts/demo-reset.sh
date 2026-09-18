#!/usr/bin/env bash
# Delete the demo project so the next "Explore the demo galaxy" re-parses NovaCart from
# scratch. Useful when you have been editing the sample specifications.
set -euo pipefail
PORT="${API_GALAXY_PORT:-8099}"
BASE="http://127.0.0.1:${PORT}/api/v1"

if ! curl -sf "${BASE}/health" >/dev/null; then
  echo "The API is not running on port ${PORT}. Start it with 'make dev-api'." >&2
  exit 1
fi

curl -sf -X DELETE "${BASE}/projects/demo-novacart" >/dev/null \
  && echo "Demo project removed." \
  || echo "No demo project to remove."

curl -sf -X DELETE "${BASE}/cache" >/dev/null && echo "Caches cleared."
echo "Next 'Explore the demo galaxy' will re-parse the sample estate."
