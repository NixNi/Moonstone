"""Main entry point for Moonstone application."""
import sys
import logging
from pathlib import Path

# Handle both direct execution and module execution
if __name__ == "__main__":
    # Running as script - ensure parent directory is in path
    file_path = Path(__file__).resolve()
    parent_dir = file_path.parent.parent
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))
    # Force package initialization by importing the package
    try:
        import src
        sys.modules['src'] = src
    except:
        pass
    # Use absolute imports
    from src import admin, ui, config
else:
    # Running as module - use relative imports
    from . import admin, ui, config

# Настройка логирования
logging.basicConfig(
    filename=config.LOG_FILE,
    filemode="w",
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)


def main():
    """Main entry point."""
    logging.info("Начало выполнения скрипта")
    
    # Check for admin privileges
    if not admin.is_admin():
        logging.info("Требуются права администратора, перезапуск...")
        admin.run_as_admin()
    
    logging.info("Вызов функции main()")
    
    # Get batch files
    bat_files = list(config.BAT_DIR.glob("*.bat"))
    
    # Create and run tray application
    sys.exit(ui.create_tray_app(bat_files))

if __name__ == "__main__":
    main()