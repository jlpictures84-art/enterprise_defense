#!/usr/bin/env bash
# Download the latest APK from GitHub Releases and serve it on port 8766.
# Run once to refresh the APK, then keep the HTTP server running.
#
# Usage:
#   ./scripts/serve_apk.sh          # download latest + start server
#   ./scripts/serve_apk.sh --update # re-download then exit (for cron)

set -euo pipefail

REPO="jlpictures84-art/enterprise_defense"
SERVE_DIR="$HOME/enterprise_apk"
PORT=8766

mkdir -p "$SERVE_DIR"

echo "[*] Fetching latest release from GitHub..."
RELEASE_JSON=$(curl -sf "https://api.github.com/repos/$REPO/releases/latest")
APK_URL=$(echo "$RELEASE_JSON" | python3 -c \
  "import sys,json; assets=json.load(sys.stdin)['assets']; \
   print(next(a['browser_download_url'] for a in assets if a['name'].endswith('.apk')))")
APK_NAME=$(basename "$APK_URL")

if [ -f "$SERVE_DIR/$APK_NAME" ]; then
    echo "[*] Already up to date: $APK_NAME"
else
    echo "[*] Downloading $APK_NAME..."
    # Remove old APKs
    rm -f "$SERVE_DIR"/*.apk
    curl -L --progress-bar -o "$SERVE_DIR/$APK_NAME" "$APK_URL"
    echo "[*] Saved to $SERVE_DIR/$APK_NAME"
fi

# Write a simple index page so the phone browser can tap-to-download
cat > "$SERVE_DIR/index.html" << EOF
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Enterprise Defense</title>
  <style>
    body { background:#000; color:#f90; font-family:monospace; text-align:center; padding:40px; }
    a.btn { display:inline-block; margin-top:20px; padding:20px 40px;
            background:#f90; color:#000; font-size:1.4em; text-decoration:none;
            border-radius:8px; font-weight:bold; }
    p { color:#9cf; }
  </style>
</head>
<body>
  <h1>USS Enterprise<br>Tactical Defense</h1>
  <p>Tap the button to install on your Android device.<br>
     You may need to allow "Install unknown apps" in Settings.</p>
  <a class="btn" href="$APK_NAME">DOWNLOAD APK</a>
  <p style="margin-top:30px;font-size:0.8em">Build: $APK_NAME</p>
</body>
</html>
EOF

if [[ "${1:-}" == "--update" ]]; then
    echo "[*] Update complete. APK at $SERVE_DIR/$APK_NAME"
    exit 0
fi

# Get Pi's local IP for easy sharing
LOCAL_IP=$(hostname -I | awk '{print $1}')
echo ""
echo "======================================================"
echo "  On your phone, open:"
echo "  http://$LOCAL_IP:$PORT"
echo "======================================================"
echo ""

cd "$SERVE_DIR"
exec python3 -m http.server $PORT
