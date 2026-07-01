#!/usr/bin/env bash
# Local validation, meant to be the primary check before pushing (run via
# `pixi run validate`, which activates the environment providing hubCheck):
#   1. regenerate hub/ (this also HEAD-checks every data file URL, see build_hub.py)
#   2. run hubCheck -noTracks against it (trackDb/genomes/hub.txt structure only,
#      no network calls beyond our own local server, so it's fast and reliable)
#
# hubCheck's -udcDir (re-fetches every bigWig/bigBed) requires outbound
# HTTPS from hubCheck itself, and is secondary here -- data-file
# reachability is already covered by build_hub.py's own urllib-based check.
# Pass --full to also run it (`pixi run validate-full`); CI always runs the
# full check as the authoritative gate.
#
# (-checkSettings is deliberately not used: it fetches its spec over a
# plain-http genome.ucsc.edu URL that 302-redirects to https, and this
# hubCheck build doesn't follow that redirect cleanly -- unrelated to hub
# correctness, so it's not worth the false failures.)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

FULL=0
[[ "${1-}" == "--full" ]] && FULL=1

command -v hubCheck >/dev/null || {
    echo "hubCheck not on PATH -- run via 'pixi run validate' (or 'pixi run validate-full')" >&2
    exit 1
}

echo "==> building hub/ from the live sample sheet"
python3 scripts/build_hub.py

PORT=8791
python3 -m http.server "$PORT" --directory hub >/tmp/fire-hub-server.log 2>&1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT
sleep 1

echo "==> hubCheck: structure (primary, no network beyond localhost)"
hubCheck -noTracks "http://localhost:$PORT/hub.txt"

if [[ "$FULL" -eq 1 ]]; then
    echo "==> hubCheck: remote data files (secondary, --full)"
    mkdir -p "$REPO_ROOT/.cache/udc"
    hubCheck -udcDir="$REPO_ROOT/.cache/udc" "http://localhost:$PORT/hub.txt"
fi

echo "==> OK"
