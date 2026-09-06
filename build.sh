#!/bin/bash

# Build executable with PyInstaller on Windows
# Note: the zapret bundle is NOT shipped in the exe - the app downloads it
# from Flowseal releases on first run.
pyinstaller --onedir --noconsole --name Moonstone --add-data "icons;icons" --icon=icons/moonstone.ico --version-file=version.py src/main.py