#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
URL_FILE="$PROJECT_ROOT/downloads/prism_urls_gbr_sample.txt"
TARGET_DIR="$PROJECT_ROOT/data/raw/nasa"
COOKIE_JAR="$HOME/.urs_cookies"

if [[ ! -f "$HOME/.netrc" ]]; then
    echo "ERRO: arquivo ~/.netrc não encontrado."
    exit 1
fi

mkdir -p "$TARGET_DIR"
touch "$COOKIE_JAR"

TOTAL=$(grep -cve '^[[:space:]]*$' "$URL_FILE")
COUNT=0

while IFS= read -r url || [[ -n "$url" ]]; do

    [[ -z "$url" ]] && continue

    COUNT=$((COUNT + 1))
    filename="${url##*/}"

    destination="$TARGET_DIR/$filename"
    temporary="$destination.part"

    if [[ -s "$destination" ]]; then
        echo "[$COUNT/$TOTAL] Arquivo já existe: $filename"
        continue
    fi

    echo "[$COUNT/$TOTAL] Baixando $filename"

    curl --http1.1 \
        --fail \
        --location \
        --netrc \
        --cookie "$COOKIE_JAR" \
        --cookie-jar "$COOKIE_JAR" \
        --retry 5 \
        --retry-all-errors \
        --retry-delay 4 \
        --continue-at - \
        --connect-timeout 30 \
        --output "$temporary" \
        "$url"

    if [[ -s "$temporary" ]]; then
        mv "$temporary" "$destination"
        echo "Concluído: $filename"
    else
        echo "ERRO: arquivo vazio: $filename"
        exit 1
    fi

done < "$URL_FILE"

echo "Download finalizado!"
