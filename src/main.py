import subprocess
import sys
import threading
from pathlib import Path
import ctypes
import re
import logging
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt5.QtGui import QIcon, QColor
from PyQt5.QtCore import Qt

# ----- CONFIG -----
SERVICE_NAME = "MoonstoneZapret"
BASE_DIR = Path(__file__).resolve().parent.parent
ICON_PATH = BASE_DIR / "icons" / "moonstone.ico"
BAT_DIR = BASE_DIR / "zapret"
ENCODING = "cp866"
LOG_FILE = BASE_DIR / "moonstone.log"
# ------------------

# Настройка логирования
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

def is_admin():
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
        logging.info(f"Проверка прав администратора: {is_admin}")
        return is_admin
    except Exception as e:
        logging.error(f"Ошибка при проверке прав администратора: {e}")
        return False

def run_as_admin():
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

def run_cmd(cmd):
    logging.info(f"Выполнение команды: {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding=ENCODING)
        if result.stdout:
            logging.info(f"Вывод команды: {result.stdout.strip()}")
        if result.stderr:
            logging.error(f"Ошибка команды: {result.stderr.strip()}")
        return result
    except Exception as e:
        logging.error(f"Исключение при выполнении команды: {e}")
        return None

def service_exists():
    result = run_cmd(f'sc.exe query "{SERVICE_NAME}"')
    if result and (SERVICE_NAME in result.stdout):
        logging.info(f"Служба '{SERVICE_NAME}' существует.")
        return True
    logging.info(f"Служба '{SERVICE_NAME}' не существует.")
    return False

def parse_bat_file(batch_path):
    logging.info(f"Чтение .bat файла: {batch_path}")
    if not batch_path.exists():
        logging.error(f"Файл .bat не найден: {batch_path}")
        sys.exit(f"Batch file not found: {batch_path}")
    try:
        with open(batch_path, 'r', encoding=ENCODING) as f:
            bat_content = f.read()
    except Exception as e:
        logging.error(f"Ошибка при чтении .bat файла: {e}")
        sys.exit(f"Failed to read batch file: {e}")
    bin_match = re.search(r'set "BIN=%~dp0([^"]*)"', bat_content)
    lists_match = re.search(r'set "LISTS=%~dp0([^"]*)"', bat_content)
    bin_path = Path(batch_path.parent / (bin_match.group(1) if bin_match else "bundled"))
    lists_path = Path(batch_path.parent / (lists_match.group(1) if lists_match else "lists"))
    logging.info(f"BIN путь: {bin_path}")
    logging.info(f"LISTS путь: {lists_path}")
    start_match = re.search(r'start\s+"[^"]*"\s+/min\s+"([^"]+)"\s+(.+)', bat_content, re.DOTALL)
    if not start_match:
        logging.error("Не удалось разобрать команду winws.exe из .bat файла")
        sys.exit("Could not parse winws.exe command from batch file")
    executable = start_match.group(1).strip()
    args = start_match.group(2).strip().replace('^', '').replace('\n', ' ').strip()
    executable = executable.replace("%BIN%", str(bin_path)+"\\").replace("%LISTS%", str(lists_path)+"\\")
    args = args.replace("%BIN%", str(bin_path)+"\\").replace("%LISTS%", str(lists_path)+"\\")
    logging.info(f"EXECUTABLE: {executable}")
    logging.info(f"ARGS: {args}")
    if not Path(executable).exists():
        logging.error(f"Исполняемый файл не найден: {executable}")
        sys.exit(f"Executable not found: {executable}")
    return executable, args

def create_service(batch_path, display_version):
    executable, args = parse_bat_file(batch_path)
    service_display = f"Moonstone Zapret DPI Bypass version[{display_version}]"
    cmd = (
        f'sc.exe create "{SERVICE_NAME}" start= demand '
        f'displayname= "{service_display}" '
        f'binPath= "\\"{executable}\\" {args}"'
    )
    logging.info(f"Создание службы '{SERVICE_NAME}' с отображаемым именем '{service_display}'...")
    result = run_cmd(cmd)
    if result and result.returncode != 0:
        logging.error(f"Не удалось создать службу: {result.stderr}")
        sys.exit(f"Failed to create service: {result.stderr}")
    if service_exists():
        logging.info(f"Служба '{SERVICE_NAME}' успешно создана.")
    else:
        logging.error(f"Служба '{SERVICE_NAME}' не была создана.")
        sys.exit(f"Service '{SERVICE_NAME}' was not created.")

def start_service(batch_path, display_version):
    if service_exists():
        logging.info("Служба существует, остановка и удаление для пересоздания с новым .bat...")
        stop_service()
        delete_service()
    create_service(batch_path, display_version)
    logging.info(f"Запуск службы '{SERVICE_NAME}'...")
    result = run_cmd(f'sc.exe start "{SERVICE_NAME}"')
    if result and result.returncode != 0:
        logging.error(f"Не удалось запустить службу: {result.stderr}")

def stop_service():
    if service_exists():
        logging.info(f"Остановка службы '{SERVICE_NAME}'...")
        run_cmd(f'sc.exe stop "{SERVICE_NAME}"')

def delete_service():
    if service_exists():
        logging.info(f"Удаление службы '{SERVICE_NAME}'...")
        run_cmd(f'sc.exe delete "{SERVICE_NAME}"')

# ---- Tray Actions ----
def create_start_handler(batch_path):
    def handler():
        display_version = batch_path.stem
        threading.Thread(target=lambda: start_service(batch_path, display_version), daemon=True).start()
    return handler

def on_stop():
    threading.Thread(target=lambda: (stop_service(), delete_service()), daemon=True).start()

def on_exit(tray):
    stop_service()
    delete_service()
    tray.hide()
    QApplication.quit()

# ---- Main Tray App ----
def main():
    logging.info("Запуск основного приложения")
    if not ICON_PATH.exists():
        logging.error(f"Иконка не найдена: {ICON_PATH}")
        sys.exit(f"Icon not found: {ICON_PATH}")
    bat_files = list(BAT_DIR.glob("*.bat"))
    if not bat_files:
        logging.error("Файлы .bat не найдены в директории zapret")
        sys.exit("No .bat files found in zapret directory.")
    logging.info(f"Найдено {len(bat_files)} .bat файлов: {[f.name for f in bat_files]}")
    logging.info(f"Загрузка иконки из: {ICON_PATH}")

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    tray = QSystemTrayIcon(QIcon(str(ICON_PATH)))
    tray.setToolTip("Moonstone")

    menu = QMenu()
    # Кастомизация стиля меню
    menu.setStyleSheet("""
        QMenu {
            background-color: #0d1121; 
            color: white;
            border: 1px solid #1e2647;
            font-size: 16px;
            padding: 4px;
        }
        QMenu::item:selected {
            background-color: #1e2647;
        }
    """)

    start_menu = QMenu("Start")
    start_menu.setStyleSheet("""
        QMenu {
            background-color: #0d1121;
            color: white;
            border: 1px solid #1e2647;
            font-size: 16px;
            padding: 4px;
        }
        QMenu::item:selected {
            background-color: #1e2647;
        }
    """)

    # Добавляем подменю слева (экспериментально, может не работать на всех системах)
    for bat in bat_files:
        action = start_menu.addAction(bat.stem)
        action.triggered.connect(create_start_handler(bat))

    menu.addMenu(start_menu)
    stop_action = menu.addAction("Stop")
    stop_action.triggered.connect(on_stop)
    exit_action = menu.addAction("Exit")
    exit_action.triggered.connect(lambda: on_exit(tray))

    tray.setContextMenu(menu)
    tray.show()

    sys.exit(app.exec_())

if __name__ == "__main__":
    logging.info("Начало выполнения скрипта")
    if not is_admin():
        logging.info("Требуются права администратора, перезапуск...")
        run_as_admin()
    main()