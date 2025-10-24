#!/usr/bin/env bash
set -e

f=tmp_blob.txt
echo "=== HEAD (first 400 bytes) ==="
head -c 400 "$f" | sed -n '1,400p'
echo

echo "=== LOOK FOR data:image/...;base64 URIs (lines) ==="
grep -n --color=always -E 'data:image\/[^;]+;base64' "$f" || echo "No data:image URIs found."
echo

echo "=== SEARCH FOR COMMON IMAGE BASE64 SIGNATURES INSIDE the TEXT ==="
grep -n --color=always -E 'iVBORw0KG|/9j/|R0lGOD' "$f" || echo "No obvious embedded PNG/JPEG/GIF base64 signatures found."
echo

echo "=== LOOK FOR ANY LONG BASE64-LIKE MATCHES (>=200 chars) ==="
grep -oE '[A-Za-z0-9+/=]{200,}' "$f" | nl -ba | head -n 10 || echo "No long base64-like chunks (>=200) found."
echo

echo "=== TRY DECODE THE FIRST LONG BASE64-LIKE CHUNK (if any) ==="
grep -oE '[A-Za-z0-9+/=]{200,}' "$f" | head -n1 > suspect.b64 || true
if [ -s suspect.b64 ]; then
  echo "Found a candidate (suspect.b64) — size:"
  ls -lh suspect.b64
  if base64 --decode suspect.b64 > suspect.bin 2>/dev/null; then
    echo "Decoded to suspect.bin. 'file' says:"
    file suspect.bin
    if command -v identify >/dev/null 2>&1; then
      echo "ImageMagick 'identify' output (if image):"
      identify suspect.bin || true
    fi
    ls -lh suspect.bin
  else
    echo "base64 decode failed for suspect.b64 (invalid base64)."
  fi
else
  echo "No suspect.b64 produced."
fi
echo

echo "=== FALLBACK: strings scan for base64-ish tokens (shorter tokens included) ==="
strings -n 80 "$f" | grep -E '[A-Za-z0-9+/=]{80,}' | nl -ba | head -n 10 || echo "No long strings found by strings."
echo

echo "=== HEX DUMP OF START (diagnostic) ==="
xxd -g1 -l 192 "$f" | sed -n '1,200p'
echo

echo "=== DONE ==="
