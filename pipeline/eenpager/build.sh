#!/usr/bin/env sh
# Build the one-pager PDF and check that it is exactly one A4 page.
# Requires uv (https://docs.astral.sh/uv/) and the Pango libraries WeasyPrint needs.
set -eu
cd "$(dirname "$0")"

OUT=../../static/voorstel/eenpager-ozb-grondwaarde.pdf
PNG="${TMPDIR:-/tmp}/eenpager"

uv run --quiet --no-project --with weasyprint==70.0 \
  weasyprint --pdf-variant pdf/ua-1 eenpager.html "$OUT"
uv run --quiet --no-project --with pymupdf==1.28.2 \
  python -I check.py "$OUT" "$PNG" 110

echo "PDF: $OUT"
echo "Voorbeeld: $PNG.png en $PNG-grijs.png"
