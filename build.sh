#!/bin/bash

# Build executable with PyInstaller on Windows
pyinstaller --onedir --noconsole --name Moonstone --add-data "icons;icons" --add-data "zapret;zapret" --icon=icons/moonstone.ico --version-file=version.py src/main.py