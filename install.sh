#!/bin/bash
# Enterprise Defense — installer for Raspberry Pi 4 (Wayland / labwc)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================"
echo "  Enterprise Defense — Pi 4 Installer"
echo "============================================"

# ── System dependencies ───────────────────────────────────────────────────────
echo ""
echo "[1/4] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y python3-pygame python3-numpy ffmpeg

# ── Desktop shortcut ──────────────────────────────────────────────────────────
echo ""
echo "[2/4] Installing desktop shortcut..."
mkdir -p "$HOME/Desktop"
cat > "$HOME/Desktop/enterprise-defense.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Enterprise Defense
Comment=USS Enterprise NCC-1701-D Tactical Defense
Exec=bash $SCRIPT_DIR/play_enterprise.sh
Icon=$SCRIPT_DIR/enterprise_defense_icon.svg
Terminal=false
Categories=Game;
EOF
chmod +x "$HOME/Desktop/enterprise-defense.desktop"

# ── Make scripts executable ───────────────────────────────────────────────────
echo ""
echo "[3/4] Setting permissions..."
chmod +x "$SCRIPT_DIR/play_enterprise.sh"

# ── Video directory ───────────────────────────────────────────────────────────
echo ""
echo "[4/4] Creating video directory..."
mkdir -p "$HOME/Downloads"

echo ""
echo "============================================"
echo "  Installation complete!"
echo "============================================"
echo ""
echo "NEXT STEP — add cutscene videos:"
echo "  ~/Downloads/1.mp4   (plays before Level 10 — the Borg fleet battle)"
echo "  ~/Downloads/2.mp4   (plays at the start of Chapter 2)"
echo ""
echo "  The game runs without these files — cutscenes are simply skipped."
echo ""
echo "Launch the game:"
echo "  Double-click 'Enterprise Defense' on the desktop"
echo "  — or —"
echo "  bash $SCRIPT_DIR/play_enterprise.sh"
echo ""
