#!/bin/bash
# Launch Enterprise Defense.
# On systems running the NatureFrame service, it stops it before launch and restarts after.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if systemctl is-active --quiet nature_frame 2>/dev/null; then
    echo "Stopping nature_frame..."
    sudo systemctl stop nature_frame
    RESTART_NF=1
fi

echo "Launching Enterprise Defense..."
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export WAYLAND_DISPLAY=wayland-0
export SDL_VIDEODRIVER=wayland

python3 "$SCRIPT_DIR/enterprise_defense.py"

if [ "$RESTART_NF" = "1" ]; then
    echo "Restarting nature_frame..."
    sudo systemctl start nature_frame
fi
