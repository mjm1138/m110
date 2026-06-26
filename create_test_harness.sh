#!/usr/bin/env bash
#
# create_test_harness.sh — one command to (re)build the synthetic test store and
# launch M110 against it.
#
#   * deletes any previous ~/Documents/M110-test
#   * (re)builds the corpus tarball only when it's missing, OLDER THAN THE
#     GENERATOR (tools/make_test_corpus.py changed), or >30 days old
#   * extracts a fresh ~/Documents/M110-test
#   * launches the app with M110_DATA_ROOT pointed at it
#
# The output (tarball + data root) lives outside the repo. Run from anywhere.
#
set -euo pipefail

# Repo root = directory containing this script.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GEN="$REPO/tools/make_test_corpus.py"
TARBALL="$HOME/m110-testdata/m110-test-corpus.tar.gz"
DEST="$HOME/Documents/M110-test"

# Prefer the project venv's interpreter/entry point; fall back to PATH.
PY="$REPO/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

# 1. Fresh start: drop any previous test root.
if [ -d "$DEST" ]; then
  echo "Removing existing $DEST"
  rm -rf "$DEST"
fi

# 2. (Re)build the tarball when stale.
rebuild=0
if [ ! -f "$TARBALL" ]; then
  rebuild=1
elif [ "$GEN" -nt "$TARBALL" ]; then
  echo "Generator changed since the tarball was built — rebuilding."
  rebuild=1
elif [ -n "$(find "$TARBALL" -mtime +30 -print -quit 2>/dev/null)" ]; then
  echo "Tarball older than 30 days — rebuilding."
  rebuild=1
fi

if [ "$rebuild" -eq 1 ]; then
  echo "Generating test corpus…"
  "$PY" "$GEN" --tar "$TARBALL"
else
  echo "Reusing existing tarball: $TARBALL"
fi

# 3. Populate a fresh throwaway data root from the tarball (arcname = M110-test).
echo "Extracting → $DEST"
mkdir -p "$(dirname "$DEST")"
tar xzf "$TARBALL" -C "$(dirname "$DEST")"

# 4. Stamp a fresh manual-test sheet from the template (gitignored working copies).
TEMPLATE="$REPO/tests/MANUAL_TEST_TEMPLATE.md"
if [ -f "$TEMPLATE" ]; then
  SHEET_DIR="$REPO/manual_tests"
  SHEET="$SHEET_DIR/$(date +%Y%m%d%H%M)-manual_test.md"
  mkdir -p "$SHEET_DIR"
  cp "$TEMPLATE" "$SHEET"
  echo "Manual-test sheet ready: $SHEET"
fi

# 5. Launch the app pointed at it (Refresh once inside to build derived/renders).
echo "Launching M110 (M110_DATA_ROOT=$DEST)…"
M110_BIN="$REPO/.venv/bin/m110"
if [ -x "$M110_BIN" ]; then
  exec env M110_DATA_ROOT="$DEST" "$M110_BIN"
else
  exec env M110_DATA_ROOT="$DEST" "$PY" -m m110.ui.main
fi
