#!/bin/bash

# Build executable with PyInstaller on Windows
pyinstaller --onedir --add-data "icons;icons" --add-data "zapret;zapret" --icon=icons/moonstone.ico src/main.py
