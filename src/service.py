"""Windows service management functions."""
import subprocess
import re
import sys
import logging
from pathlib import Path

# Handle both relative and absolute imports
try:
    from .config import SERVICE_NAME, BAT_DIR, ENCODING
except ImportError:
    from src.config import SERVICE_NAME, BAT_DIR, ENCODING


def run_cmd(cmd):
    """Execute a shell command and log the results."""
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
    """Check if the service exists."""
    result = run_cmd(f'sc.exe query "{SERVICE_NAME}"')
    if result and (SERVICE_NAME in result.stdout):
        logging.info(f"Служба '{SERVICE_NAME}' существует.")
        return True
    logging.info(f"Служба '{SERVICE_NAME}' не существует.")
    return False


def get_service_display_name():
    """Get the display name of the service."""
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
    """Parse a batch file to extract executable and arguments."""
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
    """Create a Windows service from a batch file."""
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
    """Start the service, recreating it if necessary."""
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
    """Stop the service."""
    if service_exists():
        logging.info(f"Остановка службы '{SERVICE_NAME}'...")
        run_cmd(f'sc.exe stop "{SERVICE_NAME}"')
        # Дополнительно останавливаем Windivert если вдруг запущена
        logging.info(f"Остановка службы 'WinDivert'...")
        run_cmd(f'sc.exe stop "WinDivert"')


def delete_service():
    """Delete the service."""
    if service_exists():
        logging.info(f"Удаление службы '{SERVICE_NAME}'...")
        run_cmd(f'sc.exe delete "{SERVICE_NAME}"')

