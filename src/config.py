"""Configuration constants for Moonstone application."""
import sys
from pathlib import Path

# Service and Task names
SERVICE_NAME = "MoonstoneZapret"
TASK_NAME = "MoonstoneAutostart"

# Base directory detection (works for both frozen and development)
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

# Paths
ICON_PATH = BASE_DIR / "icons" / "moonstone.ico"
CHECK_ICON_PATH = BASE_DIR / "icons" / "check.ico"
BAT_DIR = BASE_DIR / "zapret"
LOG_FILE = BASE_DIR / "moonstone.log"
STATE_FILE = BASE_DIR / "moonstone_state.json"

# Encoding
ENCODING = "cp866"

