"""State management functions."""
import json
import logging

# Handle both relative and absolute imports
try:
    from .config import STATE_FILE
except ImportError:
    from src.config import STATE_FILE


def save_state(last_bat=None, stopped=False):
    """Save application state to file."""
    try:
        data = {"last_bat": last_bat, "stopped": stopped}
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
        logging.info(f"Сохранено состояние: {data}")
    except Exception as e:
        logging.error(f"Ошибка при сохранении состояния: {e}")


def load_state():
    """Load application state from file."""
    try:
        if STATE_FILE.exists():
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            logging.info(f"Загружено состояние: {data}")
            return data
    except Exception as e:
        logging.error(f"Ошибка при загрузке состояния: {e}")
    return {"last_bat": None, "stopped": True}

