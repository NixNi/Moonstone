# Moonstone Development Guide

This guide explains how to run Moonstone in debug mode and how to build the application.

## Project Structure

The project has been refactored into separate modules:

- `src/config.py` - Configuration constants and paths
- `src/admin.py` - Admin privilege checking and elevation
- `src/service.py` - Windows service management functions
- `src/autostart.py` - Task Scheduler autostart functions
- `src/state.py` - Application state management
- `src/ui.py` - System tray UI and menu functions
- `src/main.py` - Main entry point

## Running in Debug Mode

### Prerequisites

1. Install Python 3.x (tested with Python 3.13)
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Running from Source

**Important:** Moonstone requires administrator privileges to manage Windows services. You must run it as administrator.

#### Option 1: Run as a module (recommended)

```bash
# From the project root directory
python -m src.main
```

#### Option 2: Run directly as a script

```bash
# From the project root directory
python src/main.py

# Or from the src directory
cd src
python main.py
```

Both methods work - the code automatically handles imports for both execution modes.

The application will automatically request administrator privileges if not already running as admin.

#### Option 2: Run with console output (for debugging)

To see console output and errors, you can temporarily modify the logging configuration or run with:

```bash
python -m src.main 2>&1 | tee debug.log
```

#### Debug Tips

1. **Check Logs**: Logs are written to `moonstone.log` in the project root directory
2. **Console Output**: By default, the application runs without a console window. To see console output:
   - Modify `Moonstone.spec` and set `console=True` in the `EXE` section
   - Or add print statements that will appear in the log file
3. **PyQt5 Debugging**: If you need to debug PyQt5 issues, you can enable Qt debug output:
   ```python
   import os
   os.environ['QT_DEBUG_PLUGINS'] = '1'
   ```

## Building the Application

### Prerequisites

1. Install PyInstaller:
   ```bash
   pip install pyinstaller
   ```

2. Ensure all dependencies are installed:
   ```bash
   pip install -r requirements.txt
   ```

### Build Methods

#### Method 1: Using the Spec File (Recommended)

The project includes a `Moonstone.spec` file that contains the build configuration:

```bash
pyinstaller Moonstone.spec
```

This will create:
- `build/Moonstone/` - Build artifacts
- `dist/Moonstone/` - Final distribution folder containing `Moonstone.exe`

#### Method 2: Using the Build Script

On Windows (PowerShell or Git Bash):

```bash
bash build.sh
```

Or manually run the PyInstaller command:

```bash
pyinstaller --onedir --noconsole --name Moonstone --add-data "icons;icons" --add-data "zapret;zapret" --icon=icons/moonstone.ico --version-file=version.py src/main.py
```

#### Method 3: Manual PyInstaller Command

```bash
pyinstaller --onedir ^
    --noconsole ^
    --name Moonstone ^
    --add-data "icons;icons" ^
    --add-data "zapret;zapret" ^
    --icon=icons/moonstone.ico ^
    --version-file=version.py ^
    src/main.py
```

### Build Options Explained

- `--onedir`: Creates a directory containing the executable and dependencies (easier to debug)
- `--noconsole`: Hides the console window (set to `--console` for debug builds)
- `--name Moonstone`: Sets the output name
- `--add-data "icons;icons"`: Includes the icons directory (Windows uses `;` as separator)
- `--add-data "zapret;zapret"`: Includes the zapret directory
- `--icon=icons/moonstone.ico`: Sets the application icon
- `--version-file=version.py`: Includes version information

### Debug Build

To create a debug build with console output:

1. Edit `Moonstone.spec` and change:
   ```python
   console=False,  # Change to True
   debug=False,   # Change to True for debug symbols
   ```

2. Or use the command line:
   ```bash
   pyinstaller --onedir --console --name Moonstone --add-data "icons;icons" --add-data "zapret;zapret" --icon=icons/moonstone.ico --version-file=version.py src/main.py
   ```

### Distribution

After building, the `dist/Moonstone/` folder contains:
- `Moonstone.exe` - The main executable
- `_internal/` - All dependencies and resources
- Icons and zapret files are included in the distribution

You can zip the entire `dist/Moonstone/` folder for distribution.

## Troubleshooting

### Import Errors

If you get import errors when running from source, ensure you're running from the project root:

```bash
# Correct
python -m src.main

# Incorrect (if run from src/)
python main.py  # May have import issues
```

### Service Creation Errors

- Ensure you're running as administrator
- Check Windows Event Viewer for detailed service errors
- Verify that zapret batch files exist in the `zapret/` directory

### Build Errors

- Ensure all paths in `Moonstone.spec` use correct separators (`\\` for Windows)
- Check that all required files exist (icons, zapret directory)
- Verify PyInstaller version compatibility

### Logging

Logs are written to `moonstone.log` in the base directory. Check this file for detailed error messages.

## Development Workflow

1. **Make changes** to source files in `src/`
2. **Test in debug mode**: `python -m src.main`
3. **Check logs**: Review `moonstone.log`
4. **Build**: `pyinstaller Moonstone.spec`
5. **Test executable**: Run `dist/Moonstone/Moonstone.exe`

## Notes

- The application automatically detects if it's running from source or as a frozen executable
- Paths are automatically adjusted based on the execution context
- Administrator privileges are required for service management

