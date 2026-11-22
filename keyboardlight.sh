#!/bin/sh
# Spustí KeyBoardLight (potřebuje python-pyqt6 a udev pravidlo z udev/70-keyboardlight.rules)
cd "$(dirname "$(readlink -f "$0")")" && exec python3 -m keyboardlight "$@"
