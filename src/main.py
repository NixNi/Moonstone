import subprocess
import sys
import threading
from pathlib import Path
import pystray
from PIL import Image
import ctypes
import re

# ----- CONFIG -----
SERVICE_NAME = "ZapretService"
SERVICE_DISPLAY = "Zapret DPI Bypass"
BASE_DIR = Path(__file__).resolve().parent.parent
ICON_PATH = BASE_DIR / "icons" / "moonstone.ico"
BATCH_PATH = BASE_DIR / "zapret" / "general.bat"
ENCODING = "cp866"  # для русской Windows
# ------------------

def is_admin():
    """Проверка прав администратора."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    """Перезапуск скрипта с правами администратора."""
    script = sys.executable
    params = ' '.join(f'"{x}"' for x in sys.argv)
    ctypes.windll.shell32.ShellExecuteW(None, "runas", script, params, None, 1)
    sys.exit(0)

def run_cmd(cmd):
    """Выполнение команды с правильной кодировкой."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding=ENCODING)
        if result.stdout:
            print(result.stdout.strip())
        if result.stderr:
            print(f"Command error: {result.stderr.strip()}")
        return result
    except Exception as e:
        print(f"Exception running command: {e}")
        return None

def service_exists():
    """Проверка существования службы."""
    result = run_cmd(f'sc.exe query "{SERVICE_NAME}"')
    if result and (SERVICE_NAME in result.stdout):
        print(f"Service '{SERVICE_NAME}' exists.")
        return True
    print(f"Service '{SERVICE_NAME}' does not exist.")
    return False

def parse_bat_file():
    """Чтение и разбор .bat файла для извлечения пути к winws.exe и аргументов."""
    if not BATCH_PATH.exists():
        sys.exit(f"Batch file not found: {BATCH_PATH}")

    print(f"Reading batch file: {BATCH_PATH}")
    with open(BATCH_PATH, 'r', encoding=ENCODING) as f:
        bat_content = f.read()

    # Извлечение переменных BIN и LISTS
    bin_match = re.search(r'set "BIN=%~dp0([^"]*)"', bat_content)
    lists_match = re.search(r'set "LISTS=%~dp0([^"]*)"', bat_content)
    
    bin_path = Path(BATCH_PATH.parent / (bin_match.group(1) if bin_match else "bundled"))
    lists_path = Path(BATCH_PATH.parent / (lists_match.group(1) if lists_match else "lists"))
    
    print(f"BIN path: {bin_path}")
    print(f"LISTS path: {lists_path}")
    # Поиск команды запуска winws.exe
    start_match = re.search(r'start\s+"[^"]*"\s+/min\s+"([^"]+)"\s+(.+)', bat_content, re.DOTALL)

    if not start_match:
        sys.exit("Could not parse winws.exe command from batch file")
  
    executable = start_match.group(1).strip()
    args = start_match.group(2).strip().replace('^', '').replace('\n', ' ').strip()

    
    # Подстановка переменных %BIN% и %LISTS%
    executable = executable.replace("%BIN%", str(bin_path)+"\\").replace("%LISTS%", str(lists_path)+"\\")
    print(f"EXECUTABLE: {executable}")

    args = args.replace("%BIN%", str(bin_path)+"\\").replace("%LISTS%", str(lists_path)+"\\")
    print(f"ARGS: {args}")
    
    # Проверка существования исполняемого файла
    if not Path(executable).exists():
        sys.exit(f"Executable not found: {executable}")

    return executable, args

def create_service():
    """Создание службы для winws.exe."""
    executable, args = parse_bat_file()
    cmd = (
        f'sc.exe create "{SERVICE_NAME}" start= demand '
        f'displayname= "{SERVICE_DISPLAY}" '
        f'binPath= "\\"{executable}\\" {args}"'
    )
    print(f"Creating service '{SERVICE_NAME}'...")
    result = run_cmd(cmd)
    if result and result.returncode != 0:
        sys.exit(f"Failed to create service: {result.stderr}")
    if service_exists():
        print(f"Service '{SERVICE_NAME}' created successfully.")
    else:
        sys.exit(f"Service '{SERVICE_NAME}' was not created.")

def start_service():
    """Запуск службы."""
    if not service_exists():
        print("Service does not exist, creating...")
        create_service()
    print(f"Starting service '{SERVICE_NAME}'...")
    result = run_cmd(f'sc.exe start "{SERVICE_NAME}"')
    if result and result.returncode != 0:
        print(f"Failed to start service: {result.stderr}")

def stop_service():
    """Остановка службы."""
    if service_exists():
        print(f"Stopping service '{SERVICE_NAME}'...")
        run_cmd(f'sc.exe stop "{SERVICE_NAME}"')

def delete_service():
    """Удаление службы."""
    if service_exists():
        print(f"Deleting service '{SERVICE_NAME}'...")
        run_cmd(f'sc.exe delete "{SERVICE_NAME}"')

# ---- Tray Actions ----
def on_start(icon, item):
    threading.Thread(target=start_service, daemon=True).start()

def on_stop(icon, item):
    threading.Thread(target=lambda: (stop_service(), delete_service()), daemon=True).start()

def on_exit(icon, item):
    stop_service()
    delete_service()
    icon.stop()

# ---- Main Tray App ----
def main():
    if not ICON_PATH.exists():
        sys.exit(f"Icon not found: {ICON_PATH}")

    print(f"Loading icon from: {ICON_PATH}")
    image = Image.open(ICON_PATH)

    menu = pystray.Menu(
        pystray.MenuItem("Start Script", on_start),
        pystray.MenuItem("Stop Script", on_stop),
        pystray.MenuItem("Exit", on_exit)
    )

    icon = pystray.Icon("Moonstone", image, "Moonstone", menu)
    icon.run()

if __name__ == "__main__":
    if not is_admin():
        print("Требуются права администратора, перезапуск...")
        run_as_admin()
    main()