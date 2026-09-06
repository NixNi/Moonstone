"""Download and update the bundled zapret strategy bundle (Flowseal)."""
import logging
import re
import shutil
import tarfile
import tempfile
from pathlib import Path

import requests

try:
    from .config import (
        BAT_DIR,
        BACKUP_DIR,
        BUNDLE_VERSION_FILE,
        PRESERVE_FILES,
        RELEASE_DOWNLOAD_URL,
        VERSION_URL,
    )
    from . import service
except ImportError:
    from src.config import (
        BAT_DIR,
        BACKUP_DIR,
        BUNDLE_VERSION_FILE,
        PRESERVE_FILES,
        RELEASE_DOWNLOAD_URL,
        VERSION_URL,
    )
    from src import service


class UpdateError(Exception):
    """Custom exception for update failures."""


def _notify(tray_notify, title, message, is_error=False):
    """Send a tray notification if callback provided."""
    if tray_notify:
        tray_notify(title, message, is_error)


def _version_key(version):
    """Convert a version string like '1.10.2' into a numeric tuple for comparison."""
    parts = re.findall(r"\d+", version or "")
    return tuple(int(p) for p in parts[:4]) + (0,) * (4 - len(parts))


def is_update_available(current, latest):
    """True when the latest version is newer than the installed one."""
    try:
        return _version_key(latest) > _version_key(current)
    except (TypeError, ValueError):
        return latest != current


def get_bundle_version():
    """Return the version of the installed zapret bundle.

    Reads the marker written after each update (zapret_version.txt) and falls
    back to the LOCAL_VERSION= line in zapret/service.bat.
    """
    try:
        if BUNDLE_VERSION_FILE.exists():
            version = BUNDLE_VERSION_FILE.read_text(encoding="utf-8").strip()
            if version:
                return version
    except OSError as e:
        logging.error(f"Ошибка чтения маркера версии {BUNDLE_VERSION_FILE}: {e}")

    service_bat = BAT_DIR / "service.bat"
    if service_bat.exists():
        try:
            text = service_bat.read_text(encoding="utf-8", errors="replace")
            match = re.search(r'LOCAL_VERSION="?([^\s"\]\[]+)', text)
            if match:
                return match.group(1)
        except OSError as e:
            logging.error(f"Ошибка чтения service.bat: {e}")
    return "0.0.0"


def get_latest_version():
    """Return the newest bundle version from the Flowseal repository."""
    logging.info(f"Запрос последней версии пакета: {VERSION_URL}")
    resp = requests.get(VERSION_URL, timeout=30)
    if resp.status_code != 200:
        raise UpdateError(f"Ошибка получения версии: {resp.status_code} {resp.text}")
    version = resp.text.strip()
    if not version:
        raise UpdateError("Upstream вернул пустую версию")
    logging.info(f"Последняя версия: {version}")
    return version


def _download(url: str, dst: Path):
    """Download a file with streaming to destination."""
    logging.info(f"Скачивание: {url}")
    with requests.get(url, stream=True, timeout=120) as r:
        if r.status_code != 200:
            raise UpdateError(f"Ошибка загрузки: {r.status_code} {r.text}")
        with open(dst, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    logging.info(f"Сохранено: {dst} ({dst.stat().st_size} байт)")


def _extract_tar_gz(archive: Path, extract_to: Path):
    """Extract a .tar.gz archive safely into extract_to."""
    logging.info(f"Распаковка: {archive}")
    with tarfile.open(archive, "r:gz") as tf:
        if hasattr(tarfile, "data_filter"):
            tf.extractall(extract_to, filter="data")
        else:
            tf.extractall(extract_to)
    logging.info(f"Архив распакован в {extract_to}")


def _find_bundle_root(extract_to: Path) -> Path:
    """Return the directory containing the bundle contents."""
    subdirs = [p for p in extract_to.iterdir() if p.is_dir()]
    if len(subdirs) == 1:
        return subdirs[0]
    return extract_to


def _validate_bundle(root: Path):
    """Raise UpdateError if the extracted release is missing expected parts."""
    if not (root / "service.bat").exists():
        raise UpdateError("В архиве не найден service.bat")
    if not (root / "bin").is_dir():
        raise UpdateError("В архиве не найдена папка bin/")
    if not (root / "bin" / "winws.exe").exists():
        raise UpdateError("В архиве не найден winws.exe")
    if not (root / "lists").is_dir():
        raise UpdateError("В архиве не найдена папка lists/")
    if not any(p.name.lower().endswith(".bat") and not p.name.lower().startswith("service")
               for p in root.glob("*.bat")):
        raise UpdateError("В архиве не найдены стратегии (*.bat)")
    logging.info("Структура релиза проверена")


def _preserve_files(staging: Path) -> int:
    """Copy PRESERVE_FILES (relative to BAT_DIR) into a staging dir."""
    count = 0
    for rel in PRESERVE_FILES:
        src = BAT_DIR / rel
        if src.exists():
            dst = staging / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            count += 1
            logging.info(f"Сохранён файл пользователя: {rel}")
    return count


def _backup_existing():
    """Backup the current bundle dir, keeping only one backup."""
    if BACKUP_DIR.exists():
        logging.info(f"Удаление старой резервной копии: {BACKUP_DIR}")
        shutil.rmtree(BACKUP_DIR, ignore_errors=True)
    if BAT_DIR.exists():
        logging.info(f"Создание резервной копии: {BACKUP_DIR}")
        shutil.copytree(BAT_DIR, BACKUP_DIR)


def _restore_backup():
    """Restore the bundle dir from backup."""
    if not BACKUP_DIR.exists():
        logging.error("Резервная копия отсутствует, восстановление невозможно")
        return
    if BAT_DIR.exists():
        shutil.rmtree(BAT_DIR, ignore_errors=True)
    logging.info("Восстановление пакета из резервной копии")
    shutil.copytree(BACKUP_DIR, BAT_DIR)


def _swap_bundle(root: Path):
    """Replace the current bundle with the extracted release."""
    if BAT_DIR.exists():
        logging.info(f"Очистка текущего пакета: {BAT_DIR}")
        shutil.rmtree(BAT_DIR, ignore_errors=True)
    BAT_DIR.mkdir(parents=True, exist_ok=True)
    for item in root.iterdir():
        dst = BAT_DIR / item.name
        if item.is_dir():
            shutil.copytree(item, dst)
        else:
            shutil.copy2(item, dst)
    logging.info(f"Новый пакет скопирован в {BAT_DIR}")


def _write_bundle_version(tag: str):
    """Write the installed bundle version marker."""
    try:
        BUNDLE_VERSION_FILE.write_text(f"{tag}\n", encoding="utf-8")
        logging.info(f"Записана версия пакета: {tag}")
    except OSError as e:
        logging.error(f"Ошибка записи маркера версии {BUNDLE_VERSION_FILE}: {e}")


def _tag_from_archive_name(name: str) -> str:
    """Extract the tag from a release archive name.

    zapret-discord-youtube-1.10.2.tar.gz -> 1.10.2
    """
    match = re.search(r"zapret-discord-youtube-(.+?)\.tar\.gz$", name, re.IGNORECASE)
    if not match:
        raise UpdateError(f"Не удалось определить версию по имени архива: {name}")
    return match.group(1)


def update_bundled(tray_notify=None, archive_path=None, initial=False):
    """
    Update (or install) the zapret bundle from the latest Flowseal release.

    tray_notify: callable(title, message, is_error) used for tray messages.
    archive_path: optional local .tar.gz used instead of downloading it
        (useful for tests). Returns the installed version tag.
    initial: True when the bundle is missing and this is a first-run install
        (skips stopping the service and uses install phrasing in messages).
    """
    action = "Установка пакета" if initial else "Обновление пакета"
    _notify(tray_notify, action, "Скачивание zapret..." if initial else "Остановка службы...", False)
    try:
        if not initial:
            service.stop_service()

        with tempfile.TemporaryDirectory() as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)

            if archive_path:
                archive = Path(archive_path)
                tag = _tag_from_archive_name(archive.name)
                logging.info(f"Используется локальный архив: {archive} (версия {tag})")
            else:
                tag = get_latest_version()
                archive = tmp_dir / f"zapret-discord-youtube-{tag}.tar.gz"
                _download(f"{RELEASE_DOWNLOAD_URL}/{tag}/zapret-discord-youtube-{tag}.tar.gz", archive)

            extracted = tmp_dir / "extracted"
            extracted.mkdir()
            _extract_tar_gz(archive, extracted)
            root = _find_bundle_root(extracted)
            _validate_bundle(root)

            preserved_staging = tmp_dir / "preserved"
            _preserve_files(preserved_staging)

            _backup_existing()
            try:
                _swap_bundle(root)
                # Restore user files into the fresh bundle.
                for rel in PRESERVE_FILES:
                    staged = preserved_staging / rel
                    if staged.exists():
                        dst = BAT_DIR / rel
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(staged, dst)
                        logging.info(f"Восстановлен файл пользователя: {rel}")
            except Exception:
                _restore_backup()
                raise

            _write_bundle_version(tag)

        done_title = "Установка завершена" if initial else "Обновление завершено"
        _notify(tray_notify, done_title, f"Установлена версия {tag}", False)
        logging.info("Установка пакета завершена успешно" if initial else "Обновление пакета завершено успешно")
        return tag
    except Exception as exc:  # noqa: BLE001
        logging.error(f"Ошибка {('установки' if initial else 'обновления')}: {exc}")
        _restore_backup()
        _notify(tray_notify, "Ошибка установки" if initial else "Ошибка обновления", str(exc), True)
        raise