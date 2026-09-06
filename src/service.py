"""Windows service management functions."""
import subprocess
import re
import logging
from pathlib import Path

# Handle both relative and absolute imports
try:
    from .config import SERVICE_NAME, ENCODING
except ImportError:
    from src.config import SERVICE_NAME, ENCODING


class BatParseError(Exception):
    """Raised when a strategy .bat file cannot be parsed into a service command."""


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


# ---------------------------------------------------------------------------
# Strategy batch file parsing
# The current strategies (Flowseal/zapret-discord-youtube) share one layout:
#   @echo off
#   chcp 65001 > nul
#   cd /d "%~dp0"
#   call service.bat status_zapret
#   call service.bat check_updates
#   call service.bat load_game_filter
#   call service.bat load_user_lists
#   echo:
#   set "BIN=%~dp0bin\"
#   set "LISTS=%~dp0lists\"
#   cd /d %BIN%
#   start "zapret: %~n0" /min "%BIN%winws.exe" --wf-tcp=80,... ^
#   --filter-udp=443 --hostlist="%LISTS%list-general.txt" ... ^
#   ...
# This module reimplements the variable expansion and the argument parsing
# performed by service.bat (:service_install) so the winws.exe command line
# can be installed as a Windows service by Moonstone.
# ---------------------------------------------------------------------------


def _load_bat_lines(batch_path):
    """Read a batch file, trying modern (UTF-8) then legacy encodings."""
    last_error = None
    for encoding in ("utf-8-sig", "utf-8", "cp1251", ENCODING):
        try:
            with open(batch_path, "r", encoding=encoding) as f:
                return f.read().splitlines()
        except (UnicodeDecodeError, OSError) as e:
            last_error = e
    raise BatParseError(f"Unable to read batch file '{batch_path}': {last_error}")


def _collect_set_vars(lines):
    """Collect `set "NAME=value"` assignments from batch lines."""
    variables = {}
    pattern = re.compile(r'^\s*set\s+"?([A-Za-z_][A-Za-z0-9_]*)=(.*?)"?\s*$')
    for line in lines:
        match = pattern.match(line)
        if match:
            variables[match.group(1)] = match.group(2)
            logging.debug(f"Переменная из .bat: {match.group(1)}={match.group(2)}")
    return variables


def load_user_lists(batch_dir):
    """Mirror service.bat :load_user_lists - create user list files if missing.

    The strategies reference lists/list-general-user.txt, list-exclude-user.txt
    and ipset-exclude-user.txt; winws fails to start if a referenced hostlist
    file does not exist, so the placeholders must be created before start.
    """
    lists_dir = batch_dir / "lists"
    lists_dir.mkdir(parents=True, exist_ok=True)
    defaults = {
        "ipset-exclude-user.txt": "203.0.113.113/32\n",
        "list-exclude-user.txt": "domain.example.abc\n",
        "list-general-user.txt": "# Never leave this file empty\ndomain.example.abc\n",
    }
    for name, content in defaults.items():
        path = lists_dir / name
        if not path.exists():
            try:
                path.write_text(content, encoding="utf-8")
                logging.info(f"Создан пользовательский список: {path}")
            except OSError as e:
                logging.error(f"Ошибка создания пользовательского списка {path}: {e}")


def _expand_percent_vars(text, variables, batch_path):
    r"""
    Expand %VAR% and cmd pseudo-variables (%~dp0, %~n0, %~f0).

    Pseudo-variables carry no closing percent, so they must be replaced
    literally. The loop re-applies expansion so that values which themselves
    contain pseudo-variables (e.g. BIN=%~dp0bin\) resolve to absolute paths.
    """
    batch_dir = str(batch_path.parent) + "\\"
    stem = batch_path.stem
    full = str(batch_path)
    pattern = re.compile(r'%([^%\s]+)%')

    def replace(match):
        return variables.get(match.group(1), match.group(0))

    for _ in range(5):
        text = text.replace("%~dp0", batch_dir).replace("%~n0", stem).replace("%~f0", full)
        expanded = pattern.sub(replace, text)
        if expanded == text:
            break
        text = expanded
    return text


def _get_game_filter_state(batch_dir):
    """
    Mirror service.bat :game_switch_status.

    With the game filter disabled (default) winws receives dummy port "12".
    When enabled (utils/game_filter.enabled contains all/tcp/udp) the value
    becomes "1024-65535" for the enabled protocols.
    """
    flag_file = batch_dir / "utils" / "game_filter.enabled"
    tcp, udp = "12", "12"
    if flag_file.exists():
        try:
            content = flag_file.read_text(encoding="utf-8", errors="ignore")
            mode = content.strip().splitlines()[0].strip().lower()
        except OSError as e:
            logging.error(f"Ошибка чтения game_filter.enabled: {e}")
            mode = ""
        if mode == "all":
            tcp = udp = "1024-65535"
        elif mode == "tcp":
            tcp, udp = "1024-65535", "12"
        elif mode == "udp":
            tcp, udp = "12", "1024-65535"
    logging.info(f"Game filter состояние: tcp={tcp}, udp={udp}")
    return tcp, udp


def _split_cmd_line(line):
    """
    Split a command line into tokens honoring double quotes.

    Mirrors `for %%i in (line)` tokenization in cmd.exe: space separated,
    quoted sections stay together (spaces inside quotes are literal).
    """
    tokens = []
    current = []
    in_quotes = False
    for char in line:
        if char == '"':
            in_quotes = not in_quotes
            current.append(char)
        elif char in " \t" and not in_quotes:
            if current:
                tokens.append("".join(current))
                current = []
        else:
            current.append(char)
    if current:
        tokens.append("".join(current))
    return tokens


def _convert_args(tokens, batch_dir):
    """
    Port of Flowseal service.bat :service_install argument parsing.

    Tokens containing a quoted value with a colon (absolute path) keep their
    quotes so the SCM/winws parsing keeps spaces in paths intact. Unquoted
    values are treated as relative to the strategy directory (as in the
    original, where "%BIN%" paths were already expanded before this step).

    Returns the args string to be used in the sc.exe binPath.
    """
    args_with_value = ("sni", "host", "altorder")
    merged = ""
    mergeargs = 0  # 0=default, 1=comma-merge, 2=flag processed, 3=paired value

    for token in tokens:
        arg = token

        # A new "--flag" token closes any in-progress merge.
        if arg.startswith("--") and mergeargs != 0:
            mergeargs = 0

        # Quoted value: keep quotes only for values that contain a colon
        # (drive-letter paths). "@"-prefixed values are files relative to
        # the strategy directory.
        if arg.startswith('"'):
            arg = arg[1:]
            if arg.endswith('"'):
                arg = arg[:-1]
            if ":" in arg:
                arg = f'"{arg}"'
            elif arg.startswith("@"):
                arg = f'"@{batch_dir}\\{arg[1:]}"'
            else:
                arg = f'"{batch_dir}\\{arg}"'

        if mergeargs == 1:
            merged += "," + arg
        elif mergeargs == 3:
            merged += "=" + arg
            mergeargs = 1
        else:
            merged += " " + arg

        if arg.startswith("--"):
            mergeargs = 2
        elif mergeargs >= 1:
            if mergeargs == 2:
                mergeargs = 1
            for item in args_with_value:
                if item.lower() == arg.lower():
                    mergeargs = 3

    # Restore escaped exclamation marks (Flowseal: EXCL_MARK -> ^! in the
    # final binPath, since winws receives the argument without cmd parsing).
    return merged.strip().replace("EXCL_MARK", "^!")


def parse_bat_file(batch_path):
    """
    Parse a strategy .bat file and return (executable, args) for sc.exe.

    Handles both the current Flowseal layout (bin/, lists/, %GameFilterTCP%,
    UTF-8) and the legacy layout (bundled/, configs/, cp866).
    """
    batch_path = Path(batch_path)
    logging.info(f"Чтение .bat файла: {batch_path}")
    if not batch_path.exists():
        raise BatParseError(f"Batch file not found: {batch_path}")

    lines = _load_bat_lines(batch_path)
    batch_dir = batch_path.parent

    # Strategies reference lists/list-general-user.txt, list-exclude-user.txt
    # and ipset-exclude-user.txt (created by service.bat load_user_lists at
    # runtime); create the placeholders so winws can actually start.
    load_user_lists(batch_dir)

    # Locate the "start ... winws.exe" command (may be a continuation).
    start_idx = None
    for idx, line in enumerate(lines):
        if "winws.exe" in line and line.lstrip().startswith("start"):
            start_idx = idx
            break
    if start_idx is None:
        raise BatParseError(f"Could not parse winws.exe command from batch file: {batch_path}")

    # Join continuation lines (cmb strips ^ + newline, preserving the space
    # that preceded the caret).
    command_lines = []
    for line in lines[start_idx:]:
        command_lines.append(line.rstrip())
        if not line.rstrip().endswith("^"):
            break
    joined = " ".join(line.rstrip().rstrip("^").rstrip() for line in command_lines)
    logging.debug(f"Склеенная команда: {joined}")

    # Protect escaped exclamation marks ("^!") with EXCL_MARK exactly like
    # Flowseal's service.bat does, so the caret survives tokenization and
    # gets restored into the final args string.
    joined = joined.replace("^!", "EXCL_MARK")

    # Collect set "VAR=value" assignments and game filter state.
    variables = _collect_set_vars(lines)
    game_tcp, game_udp = _get_game_filter_state(batch_dir)
    variables.setdefault("GameFilterTCP", game_tcp)
    variables.setdefault("GameFilterUDP", game_udp)
    variables.setdefault("GameFilter", game_tcp)

    expanded = _expand_percent_vars(joined, variables, batch_path)
    if "%" in expanded:
        logging.warning(f"Неразвёрнутые переменные остались в команде: {expanded}")

    # Strip the `start "title" /min ` prefix.
    start_match = re.match(r'^start\s+"[^"]*"\s+/min\s+(.*)$', expanded)
    if not start_match:
        raise BatParseError(f"Could not parse winws.exe start command: {batch_path}")
    remainder = start_match.group(1).strip()

    tokens = _split_cmd_line(remainder)
    if not tokens:
        raise BatParseError(f"Empty winws.exe command in batch file: {batch_path}")

    executable = tokens[0].strip('"')
    args = _convert_args(tokens[1:], batch_dir)

    if not Path(executable).exists():
        raise BatParseError(f"Executable not found: {executable}")
    if " " in executable:
        executable = f'"{executable}"'

    logging.info(f"EXECUTABLE: {executable}")
    logging.info(f"ARGS: {args}")
    return executable, args


# ---------------------------------------------------------------------------
# Service lifecycle
# ---------------------------------------------------------------------------


def create_service(batch_path, display_version):
    """Create a Windows service from a batch file."""
    executable, args = parse_bat_file(batch_path)
    service_display = f"Moonstone Zapret DPI Bypass version[{display_version}]"

    # binPath = quoted executable (if needed) + space + args.
    bin_path_value = f'{executable} {args}'.strip()

    cmd_args = [
        'sc.exe', 'create', SERVICE_NAME,
        'start=', 'auto',
        'displayname=', service_display,
        'binPath=', bin_path_value
    ]

    logging.info(f"Создание службы '{SERVICE_NAME}' с отображаемым именем '{service_display}'...")
    logging.info(f"Выполнение команды: {' '.join(cmd_args)}")
    try:
        result = subprocess.run(cmd_args, capture_output=True, text=True, encoding=ENCODING)
        if result.stdout:
            logging.info(f"Вывод команды: {result.stdout.strip()}")
        if result.stderr:
            logging.error(f"Ошибка команды: {result.stderr.strip()}")
        if result.returncode != 0:
            raise RuntimeError(f"Failed to create service: {result.stderr}")
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to create service: {e}") from e

    if service_exists():
        logging.info(f"Служба '{SERVICE_NAME}' успешно создана.")
    else:
        raise RuntimeError(f"Service '{SERVICE_NAME}' was not created.")


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
        raise RuntimeError(f"Failed to start service: {result.stderr}")


def stop_service():
    """Stop the service and clean up WinDivert / stray winws processes."""
    if service_exists():
        logging.info(f"Остановка службы '{SERVICE_NAME}'...")
        run_cmd(f'sc.exe stop "{SERVICE_NAME}"')
        # Дополнительно останавливаем Windivert если вдруг запущена
        logging.info(f"Остановка службы 'WinDivert'...")
        run_cmd(f'sc.exe stop "WinDivert"')
        # WinDivert 1.4 has its own service name
        logging.info(f"Остановка службы 'WinDivert14'...")
        run_cmd(f'sc.exe stop "WinDivert14"')
    # Убиваем оставшиеся процессы winws.exe (как это делает service.bat)
    logging.info("Завершение оставшихся процессов winws.exe...")
    run_cmd('taskkill /IM winws.exe /F')


def delete_service():
    """Delete the service."""
    if service_exists():
        logging.info(f"Удаление службы '{SERVICE_NAME}'...")
        run_cmd(f'sc.exe delete "{SERVICE_NAME}"')