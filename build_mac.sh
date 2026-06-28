#!/bin/bash

echo "Creating macOS application bundle..."

# Install exact requirements just in case
python3 -m pip install -r requirements.txt

# Clean old dist/build folders if they exist
rm -rf build dist
rm -rf *.spec

# Run PyInstaller
# --noconfirm: Overwrite output directory
# --windowed: macOS App bundle, no console
# --name: Name of the App
# --add-data: Include any static assets if needed. The images/ folder is created dynamically, so no need to package it pre-filled, but let's make sure the script can find its dir.
pyinstaller --noconfirm --windowed --name "TistoryMigrator" \
  --add-data "migrate_from_url.py:." \
  gui_main.py

echo "Build complete. App is located in the 'dist' directory."
