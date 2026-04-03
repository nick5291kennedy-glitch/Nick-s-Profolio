#!/bin/zsh
set -euo pipefail

ROOT="/Users/nicholaskennedy/Documents/New project"
DIST_DIR="$ROOT/dist"
APP_PATH="$DIST_DIR/Market Intelligence Dashboard.app"
APPLESCRIPT="$DIST_DIR/market_dashboard_launcher.applescript"
SERVER_LOG="/tmp/market-dashboard-app.log"

mkdir -p "$DIST_DIR"
cd "$ROOT"

/usr/bin/python3 "$ROOT/scripts/generate_icons.py"

cat > "$APPLESCRIPT" <<'APPLESCRIPT'
on run
  set dashboardURL to "http://127.0.0.1:8000"
  set apiURL to dashboardURL & "/api/dashboard"
  set projectRoot to "/Users/nicholaskennedy/Documents/New project"
  set launchCommand to "cd " & quoted form of projectRoot & " && /usr/bin/python3 server.py >> /tmp/market-dashboard-app.log 2>&1 &"

  try
    do shell script "/usr/bin/curl -sf " & quoted form of apiURL
  on error
    do shell script launchCommand
    delay 2
  end try

  do shell script "/usr/bin/open " & quoted form of dashboardURL
end run
APPLESCRIPT

rm -rf "$APP_PATH"
/usr/bin/osacompile -o "$APP_PATH" "$APPLESCRIPT"

ICON_FILE="$APP_PATH/Contents/Resources/applet.icns"
ICONSET_DIR="$DIST_DIR/marketdashboard.iconset"
rm -rf "$ICONSET_DIR"
mkdir -p "$ICONSET_DIR"

cp "$ROOT/icons/icon-180.png" "$ICONSET_DIR/icon_128x128.png"
cp "$ROOT/icons/icon-180.png" "$ICONSET_DIR/icon_128x128@2x.png"
cp "$ROOT/icons/icon-192.png" "$ICONSET_DIR/icon_256x256.png"
cp "$ROOT/icons/icon-192.png" "$ICONSET_DIR/icon_256x256@2x.png"
cp "$ROOT/icons/icon-512.png" "$ICONSET_DIR/icon_512x512.png"
cp "$ROOT/icons/icon-512.png" "$ICONSET_DIR/icon_512x512@2x.png"

/usr/bin/iconutil -c icns "$ICONSET_DIR" -o "$ICON_FILE" 2>/dev/null || true

echo "Built macOS app at: $APP_PATH"
