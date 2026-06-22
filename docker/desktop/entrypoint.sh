#!/usr/bin/env bash
set -e

export DISPLAY=:99
export XAUTHORITY=/root/.Xauthority
# pyautogui -> mouseinfo -> Xlib opens XAUTHORITY on import; the file must exist.
touch "$XAUTHORITY"

# -ac disables X access control so clients connect without a magic cookie.
Xvfb :99 -screen 0 1280x800x24 -ac +extension RANDR >/dev/null 2>&1 &

# Wait for the X server socket before starting anything that needs the display.
for _ in $(seq 1 40); do
  [ -e /tmp/.X11-unix/X99 ] && break
  sleep 0.25
done

fluxbox >/dev/null 2>&1 &
x11vnc -display :99 -nopw -forever -shared -rfbport 5900 >/dev/null 2>&1 &

exec python /app/agent.py
