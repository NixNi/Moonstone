"""Task Scheduler autostart functions."""
import sys
import logging
from datetime import datetime
from pathlib import Path
import win32com.client

# Handle both relative and absolute imports
try:
    from .config import TASK_NAME
except ImportError:
    from src.config import TASK_NAME


def enable_autostart():
    """Enable autostart via Task Scheduler."""
    try:
        scheduler = win32com.client.Dispatch('Schedule.Service')
        scheduler.Connect()
        root_folder = scheduler.GetFolder('\\')
        
        # Создаём задачу
        task_def = scheduler.NewTask(0)
        task_def.RegistrationInfo.Description = 'Autostart Moonstone DPI Bypass Application'
        task_def.RegistrationInfo.Author = 'Nixni Co.'
        
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
    """Disable autostart via Task Scheduler."""
    try:
        scheduler = win32com.client.Dispatch('Schedule.Service')
        scheduler.Connect()
        root_folder = scheduler.GetFolder('\\')
        root_folder.DeleteTask(TASK_NAME, 0)
        logging.info("Автозапуск отключён через Планировщик задач")
    except Exception as e:
        logging.error(f"Ошибка при отключении автозапуска: {e}")


def is_autostart_enabled():
    """Check if autostart is enabled."""
    try:
        scheduler = win32com.client.Dispatch('Schedule.Service')
        scheduler.Connect()
        root_folder = scheduler.GetFolder('\\')
        root_folder.GetTask(TASK_NAME)
        return True
    except Exception:
        return False

