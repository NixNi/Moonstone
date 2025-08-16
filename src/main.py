import subprocess
import sys
import threading
from pathlib import Path
import ctypes
import re
import logging
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QAction
from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtCore import Qt
import win32com.client
from datetime import datetime
import json

# ----- CONFIG -----
SERVICE_NAME = "MoonstoneZapret"
TASK_NAME = "MoonstoneAutostart"
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
ICON_PATH = BASE_DIR / "icons" / "moonstone.ico"
BAT_DIR = BASE_DIR / "zapret"
ENCODING = "cp866"
LOG_FILE = BASE_DIR / "moonstone.log"
STATE_FILE = BASE_DIR / "moonstone_state.json"
CHECK_ICON_PATH = BASE_DIR / "icons" / "check.ico"
# ------------------

# Настройка логирования
logging.basicConfig(
    filename=LOG_FILE,
    filemode="w",
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

def get_service_display_name():
    if not service_exists():
        return None
    result = run_cmd(f'sc.exe qc "{SERVICE_NAME}"')
    if result and result.returncode == 0:
        match = re.search(r'DISPLAY_NAME\s*:\s*(.+)', result.stdout)
        if match:
            display_name = match.group(1).strip()
            logging.info(f"Получено отображаемое имя службы: {display_name}")
            return display_name
    logging.error("Не удалось получить отображаемое имя службы")
    return None

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
        f'sc.exe create "{SERVICE_NAME}" start= auto '
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
        #Дополнительно останавливаем Windivert если вдруг запущена
        logging.info(f"Остановка службы 'WinDivert'...")
        run_cmd(f'sc.exe stop "WinDivert"')

def delete_service():
    if service_exists():
        logging.info(f"Удаление службы '{SERVICE_NAME}'...")
        run_cmd(f'sc.exe delete "{SERVICE_NAME}"')

# ---- Autostart Functions (Task Scheduler) ----
def enable_autostart():
    try:
        scheduler = win32com.client.Dispatch('Schedule.Service')
        scheduler.Connect()
        root_folder = scheduler.GetFolder('\\')
        
        # Создаём задачу
        task_def = scheduler.NewTask(0)
        task_def.RegistrationInfo.Description = 'Autostart Moonstone DPI Bypass Application'
        task_def.RegistrationInfo.Author = 'Nixni Co.'  # Замените на ваше имя компании
        
        # Настраиваем триггер на запуск при входе в систему
        trigger = task_def.Triggers.Create(9)  # 1 = TASK_TRIGGER_LOGON
        trigger.Id = 'LogonTrigger'
        trigger.StartBoundary = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        
        # Настраиваем действие для запуска Moonstone.exe
        action = task_def.Actions.Create(0)  # 0 = TASK_ACTION_EXEC
        action.ID = 'MoonstoneStart'
        action.Path = str(Path(sys.executable).resolve())
        
        # Настраиваем параметры задачи
        task_def.Settings.Enabled = True
        task_def.Settings.Hidden = False
        task_def.Settings.RunOnlyIfIdle = False
        task_def.Settings.DisallowStartIfOnBatteries = False
        task_def.Settings.StopIfGoingOnBatteries = False
        task_def.Settings.ExecutionTimeLimit = 'PT0S'  # Без ограничения времени
        task_def.Principal.RunLevel = 1  # 1 = TASK_RUNLEVEL_HIGHEST (запуск с правами администратора)
        task_def.Principal.LogonType = 3  # 3 = TASK_LOGON_INTERACTIVE_TOKEN
        
        # Регистрируем задачу
        root_folder.RegisterTaskDefinition(
            TASK_NAME,
            task_def,
            6,  # TASK_CREATE_OR_UPDATE
            None,  # Пользователь (None = текущий пользователь)
            None,  # Пароль
            3   # TASK_LOGON_INTERACTIVE_TOKEN
        )
        logging.info(f"Автозапуск включён через Планировщик задач: {TASK_NAME}")
    except Exception as e:
        logging.error(f"Ошибка при включении автозапуска: {e}")

def disable_autostart():
    try:
        scheduler = win32com.client.Dispatch('Schedule.Service')
        scheduler.Connect()
        root_folder = scheduler.GetFolder('\\')
        root_folder.DeleteTask(TASK_NAME, 0)
        logging.info("Автозапуск отключён через Планировщик задач")
    except Exception as e:
        logging.error(f"Ошибка при отключении автозапуска: {e}")

def is_autostart_enabled():
    try:
        scheduler = win32com.client.Dispatch('Schedule.Service')
        scheduler.Connect()
        root_folder = scheduler.GetFolder('\\')
        root_folder.GetTask(TASK_NAME)
        return True
    except Exception:
        return False

# ---- Tray Actions ----
def save_state(last_bat=None, stopped=False):
    try:
        data = {"last_bat": last_bat, "stopped": stopped}
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
        logging.info(f"Сохранено состояние: {data}")
    except Exception as e:
        logging.error(f"Ошибка при сохранении состояния: {e}")

def load_state():
    try:
        if STATE_FILE.exists():
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            logging.info(f"Загружено состояние: {data}")
            return data
    except Exception as e:
        logging.error(f"Ошибка при загрузке состояния: {e}")
    return {"last_bat": None, "stopped": True}

def open_config_folder():
    try:
        subprocess.Popen(f'explorer "{BASE_DIR}"')
        logging.info(f"Открыта папка конфигурации: {BASE_DIR}")
    except Exception as e:
        logging.error(f"Ошибка при открытии папки конфигурации: {e}")


def create_start_handler(batch_path, start_menu, actions):
    def handler():
        display_version = batch_path.stem
        save_state(last_bat=batch_path.stem, stopped=False)
        threading.Thread(target=lambda: start_service(batch_path, display_version), daemon=True).start()
        update_menu_styles(start_menu, actions, batch_path.stem)
    return handler

def on_stop(start_menu, actions):
    save_state(last_bat=None, stopped=True) 
    threading.Thread(target=lambda: (stop_service(), delete_service(), update_menu_styles(start_menu, actions, None)), daemon=True).start()

def on_exit(tray, start_menu, actions):
    stop_service()
    delete_service()
    update_menu_styles(start_menu, actions, None)
    tray.hide()
    QApplication.quit()

def update_menu_styles(start_menu, actions, active_version):
    try:
        for bat, action in actions.items():
            base_text = bat.stem
            if bat.stem == active_version:
                font = QFont()
                font.setBold(True)
                action.setFont(font)
                if CHECK_ICON_PATH.exists():
                    action.setIcon(QIcon(str(CHECK_ICON_PATH)))
                else:
                    logging.warning(f"Иконка проверки не найдена: {CHECK_ICON_PATH}")
            else:
                action.setText(base_text)
                action.setFont(QFont())
                action.setIcon(QIcon())
        start_menu.update()
        logging.info(f"Обновлены стили меню, активная версия: {active_version}")
    except Exception as e:
        logging.error(f"Ошибка при обновлении стилей меню: {e}")

# ---- Main Tray App ----
def main():
    logging.info("Запуск основного приложения")
    if not ICON_PATH.exists():
        logging.error(f"Иконка не найдена: {ICON_PATH}")
        sys.exit(f"Icon not found: {ICON_PATH}")
    bat_files = list(BAT_DIR.glob("*.bat"))
    if not bat_files:
        logging.error(f"Файлы .bat не найдены в директории zapret")
        sys.exit("No .bat files found in zapret directory.")
    logging.info(f"Найдено {len(bat_files)} .bat файлов: {[f.name for f in bat_files]}")
    logging.info(f"Загрузка иконки из: {ICON_PATH}")

    try:
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)

        tray = QSystemTrayIcon(QIcon(str(ICON_PATH)))
        tray.setToolTip("Moonstone")

        menu = QMenu()
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

        actions = {}
        for bat in bat_files:
            action = start_menu.addAction(bat.stem)
            action.triggered.connect(create_start_handler(bat, start_menu, actions))
            actions[bat] = action

        menu.addMenu(start_menu)
        stop_action = menu.addAction("Stop")
        stop_action.triggered.connect(lambda: on_stop(start_menu, actions))

        config_action = menu.addAction("Config")
        config_action.triggered.connect(open_config_folder)

        autostart_action = menu.addAction("Autostart")
        autostart_action.setCheckable(True)
        autostart_action.setChecked(is_autostart_enabled())
        def toggle_autostart(checked):
            if checked:
                enable_autostart()
            else:
                disable_autostart()
        autostart_action.toggled.connect(toggle_autostart)

        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(lambda: on_exit(tray, start_menu, actions))

        display_name = get_service_display_name()
        active_version = None
        if display_name:
            match = re.search(r'version\[([^\]]+)\]', display_name)
            if match:
                active_version = match.group(1)
        update_menu_styles(start_menu, actions, active_version)

        tray.setContextMenu(menu)
        tray.show()
        tray.showMessage("Moonstone", "Приложение запущено", QSystemTrayIcon.Information, 2000)
        logging.info("Системный трей отображён")

        state = load_state()
        if state["last_bat"] and not state["stopped"]:
            for bat in bat_files:
                if bat.stem == state["last_bat"]:
                    logging.info(f"Автозапуск последнего использованного bat: {bat.stem}")
                    threading.Thread(target=lambda: start_service(bat, bat.stem), daemon=True).start()
                    update_menu_styles(start_menu, actions, bat.stem)
                    break

        logging.info("Запуск главного цикла приложения")
        return app.exec_()

    except Exception as e:
        logging.error(f"Ошибка в главном приложении: {e}")
        sys.exit(1)

if __name__ == "__main__":
    logging.info("Начало выполнения скрипта")
    if not is_admin():
        logging.info("Требуются права администратора, перезапуск...")
        run_as_admin()
    logging.info("Вызов функции main()")
    sys.exit(main())