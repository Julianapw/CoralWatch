#!/usr/bin/env bash
# Download all NASA CORAL/PRISM L2 files listed in prism_urls.txt.
# Run from the project root with: bash downloads/download_prism_files.sh
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
URL_FILE="$PROJECT_ROOT/downloads/prism_urls.txt"
TARGET_DIR="$PROJECT_ROOT/data/raw/nasa"
COOKIE_JAR="$HOME/.urs_cookies"

if [[ ! -f "$URL_FILE" ]]; then
  echo "ERROR: URL list not found: $URL_FILE" >&2
  exit 1
fi
if [[ ! -f "$HOME/.netrc" ]]; then
  echo "ERROR: $HOME/.netrc was not found." >&2
  echo "Configure your NASA Earthdata credentials in ~/.netrc first." >&2
  exit 1
fi

mkdir -p "$TARGET_DIR"
touch "$COOKIE_JAR"

TOTAL="$(grep -cve '^[[:space:]]*$' "$URL_FILE" || true)"
COUNT=0
SKIPPED=0
FAILED=0

while IFS= read -r url || [[ -n "$url" ]]; do
  # Ignore blank lines and comments.
  [[ -z "${url//[[:space:]]/}" ]] && continue
  [[ "$url" =~ ^[[:space:]]*# ]] && continue

  COUNT=$((COUNT + 1))
  filename="${url##*/}"
  destination="$TARGET_DIR/$filename"
  temporary="$destination.part"

  if [[ -s "$destination" ]]; then
    echo "[$COUNT/$TOTAL] Already exists, skipping: $filename"
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  echo "[$COUNT/$TOTAL] Downloading: $filename"
  rm -f "$temporary"
  if curl --fail --location --netrc \
      --cookie "$COOKIE_JAR" --cookie-jar "$COOKIE_JAR" \
      --retry 3 --retry-delay 2 --connect-timeout 30 \
      --output "$temporary" "$url"; then
    if [[ -s "$temporary" ]]; then
      mv "$temporary" "$destination"
      echo "  Saved: $destination"
    else
      echo "  ERROR: empty response for $filename" >&2
      rm -f "$temporary"
      FAILED=$((FAILED + 1))
    fi
  else
    echo "  ERROR: download failed for $filename" >&2
    rm -f "$temporary"
    FAILED=$((FAILED + 1))
  fi
done < "$URL_FILE"

echo
echo "Download summary: total=$TOTAL, skipped=$SKIPPED, failed=$FAILED"
echo "NASA files folder: $TARGET_DIR"

if [[ "$FAILED" -gt 0 ]]; then
  echo "Some downloads failed. Fix authentication/network issues and run this script again; existing completed files will be skipped." >&2
  exit 1
fi
