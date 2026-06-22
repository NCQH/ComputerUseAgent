#!/usr/bin/env bash
set -e

Xvfb :99 -screen 0 1280x800x24 &
sleep 1
fluxbox >/dev/null 2>&1 &
x11vnc -display :99 -nopw -forever -shared -rfbport 5900 >/dev/null 2>&1 &

exec python /app/agent.py
