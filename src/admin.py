"""Admin privilege checking and elevation functions."""
import sys
import ctypes
import logging


def is_admin():
    """Check if the current process is running with administrator privileges."""
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
        logging.info(f"Проверка прав администратора: {is_admin}")
        return is_admin
    except Exception as e:
        logging.error(f"Ошибка при проверке прав администратора: {e}")
        return False


def run_as_admin():
    """Restart the current script with administrator privileges."""
    logging.info("Попытка перезапуска с правами администратора")
    script = sys.executable
    params = ' '.join(f'"{x}"' for x in sys.argv)
    try:
        ctypes.windll.shell32.ShellExecuteW(None, "runas", script, params, None, 1)
        logging.info("Перезапуск успешен, завершение текущего процесса")
        sys.exit(0)
    except Exception as e:
        logging.error(f"Ошибка при перезапуске с правами администратора: {e}")
        sys.exit(1)

