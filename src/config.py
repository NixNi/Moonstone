"""Configuration constants for Moonstone application."""
import sys
from pathlib import Path

# Service and Task names
SERVICE_NAME = "MoonstoneZapret"
TASK_NAME = "MoonstoneAutostart"

# Base directory detection (works for both frozen and development)
if getattr(sys, 'frozen', False):
    # Bundled resources (icons) live inside the PyInstaller extraction dir.
    _base_dir = Path(getattr(sys, '_MEIPASS'))
    # Writable runtime data (zapret bundle, logs, state) lives next to the
    # executable - the bundle is downloaded on first run and must not be
    # written into the read-only _MEIPASS directory.
    _data_dir = Path(sys.executable).resolve().parent
else:
    _base_dir = Path(__file__).resolve().parent.parent
    _data_dir = _base_dir

BASE_DIR = _base_dir
DATA_DIR = _data_dir

# Paths (bundled resources)
ICON_PATH = BASE_DIR / "icons" / "moonstone.ico"
CHECK_ICON_PATH = BASE_DIR / "icons" / "check.ico"

# Paths (writable runtime data)
BAT_DIR = DATA_DIR / "zapret"
BIN_DIR = BAT_DIR / "bin"
LISTS_DIR = BAT_DIR / "lists"
UTILS_DIR = BAT_DIR / "utils"
BACKUP_DIR = DATA_DIR / "zapret_backup"
LOG_FILE = DATA_DIR / "moonstone.log"
STATE_FILE = DATA_DIR / "moonstone_state.json"
BUNDLE_VERSION_FILE = DATA_DIR / "zapret_version.txt"

# Upstream repository (Flowseal/zapret-discord-youtube)
REPO_OWNER = "Flowseal"
REPO_NAME = "zapret-discord-youtube"
RELEASES_API = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
VERSION_URL = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/main/.service/version.txt"
RELEASE_DOWNLOAD_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/download"

# Files preserved across bundle updates (user data)
PRESERVE_FILES = [
    "lists/list-general-user.txt",
    "lists/list-exclude-user.txt",
    "lists/ipset-exclude-user.txt",
    "utils/game_filter.enabled",
]

# Encoding for legacy batch files (cp866); current strategy files are UTF-8.
ENCODING = "cp866"


def iter_strategy_bats():
    """Return sorted strategy .bat files, excluding service*.bat.

    service.bat is infrastructure (upstream service installer), not a
    strategy, and does not contain a winws.exe command.
    """
    return sorted(
        (path for path in BAT_DIR.glob("*.bat")
         if not path.name.lower().startswith("service")),
        key=lambda path: path.name.lower(),
    )