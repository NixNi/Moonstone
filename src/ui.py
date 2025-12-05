"""UI/Tray interface functions."""
import subprocess
import re
import sys
import threading
import logging
from pathlib import Path

from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QAction
from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtCore import Qt

# Handle both relative and absolute imports
try:
    from .config import ICON_PATH, CHECK_ICON_PATH, BASE_DIR
    from . import service, autostart, state, updater
except ImportError:
    from src.config import ICON_PATH, CHECK_ICON_PATH, BASE_DIR
    from src import service, autostart, state, updater


def open_config_folder():
    """Open the configuration folder in Windows Explorer."""
    try:
        subprocess.Popen(f'explorer "{BASE_DIR}"')
        logging.info(f"Открыта папка конфигурации: {BASE_DIR}")
    except Exception as e:
        logging.error(f"Ошибка при открытии папки конфигурации: {e}")


def create_start_handler(batch_path, start_menu, actions):
    """Create a handler function for starting a service."""
    def handler():
        display_version = batch_path.stem
        state.save_state(last_bat=batch_path.stem, stopped=False)
        threading.Thread(
            target=lambda: service.start_service(batch_path, display_version),
            daemon=True
        ).start()
        update_menu_styles(start_menu, actions, batch_path.stem)
    return handler


def on_stop(start_menu, actions):
    """Handle stop action."""
    state.save_state(last_bat=None, stopped=True)
    threading.Thread(
        target=lambda: (
            service.stop_service(),
            service.delete_service(),
            update_menu_styles(start_menu, actions, None)
        ),
        daemon=True
    ).start()


def on_exit(tray, start_menu, actions):
    """Handle exit action."""
    service.stop_service()
    service.delete_service()
    update_menu_styles(start_menu, actions, None)
    tray.hide()
    QApplication.quit()


def update_menu_styles(start_menu, actions, active_version):
    """Update menu styles to highlight the active version."""
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


def create_tray_notifier(tray):
    """Return a function to show tray messages with unified style."""
    def _notify(title, message, is_error=False):
        icon = QSystemTrayIcon.Critical if is_error else QSystemTrayIcon.Information
        tray.showMessage(f"Moonstone - {title}", message, icon, 3000)
    return _notify


def on_update_bundled(tray):
    """Handle bundled files update."""
    notifier = create_tray_notifier(tray)

    def run_update():
        notifier("Обновление пакета", "Запуск обновления...", False)
        try:
            updater.update_bundled(tray_notify=notifier)
        except Exception as e:  # noqa: BLE001
            logging.error(f"Ошибка при обновлении пакета: {e}", exc_info=True)
    threading.Thread(target=run_update, daemon=True).start()


def create_tray_app(bat_files):
    """Create and configure the system tray application."""
    logging.info("Запуск основного приложения")
    if not ICON_PATH.exists():
        logging.error(f"Иконка не найдена: {ICON_PATH}")
        sys.exit(f"Icon not found: {ICON_PATH}")
    
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

        update_bundled_action = menu.addAction("Update bundled files")
        update_bundled_action.triggered.connect(lambda: on_update_bundled(tray))

        autostart_action = menu.addAction("Autostart")
        autostart_action.setCheckable(True)
        autostart_action.setChecked(autostart.is_autostart_enabled())
        
        def toggle_autostart(checked):
            if checked:
                autostart.enable_autostart()
            else:
                autostart.disable_autostart()
        autostart_action.toggled.connect(toggle_autostart)

        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(lambda: on_exit(tray, start_menu, actions))

        # Determine active version from service display name
        display_name = service.get_service_display_name()
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

        # Auto-start last used service if state indicates it should be running
        app_state = state.load_state()
        if app_state["last_bat"] and not app_state["stopped"]:
            for bat in bat_files:
                if bat.stem == app_state["last_bat"]:
                    logging.info(f"Автозапуск последнего использованного bat: {bat.stem}")
                    threading.Thread(
                        target=lambda: service.start_service(bat, bat.stem),
                        daemon=True
                    ).start()
                    update_menu_styles(start_menu, actions, bat.stem)
                    break

        logging.info("Запуск главного цикла приложения")
        return app.exec_()

    except Exception as e:
        logging.error(f"Ошибка в главном приложении: {e}")
        sys.exit(1)

