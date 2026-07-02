#!/usr/bin/env bash
# macOS: double-click this file in Finder to install (first time) and launch.
cd "$(dirname "$0")"
./start.sh
echo
read -n 1 -s -r -p "Dashboard stopped. Press any key to close this window…"
