#!/usr/bin/env bash
# Fetches the Contra_1.tsl reference file used by the structural-conformance
# tests in tests/test_writer.py.
#
# The file lives in the community-maintained `johnsrude/BossToneStudio` repo.
# That repo does not currently include a LICENSE — by default this means the
# author retains all rights and we cannot redistribute the file inside this
# repository. This script lets each developer pull it into their local working
# copy at their own discretion.
#
# Alternative: export your own .tsl from BOSS TONE STUDIO and save it as
# data/reference.tsl, then update REFERENCE_TSL in tests/test_writer.py.
#
# Tests that depend on this file will skip cleanly if it isn't present.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$REPO_ROOT/data/Contra_1.tsl"
URL="https://raw.githubusercontent.com/johnsrude/BossToneStudio/master/Contra_1.tsl"

mkdir -p "$REPO_ROOT/data"
echo "Fetching $URL"
echo "  → $DEST"
curl -fsSL "$URL" -o "$DEST"
echo "Done. Re-run tests to enable the reference-anchored cases."
