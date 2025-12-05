"""Download and update bundled zapret binaries from GitHub releases."""
import logging
import shutil
import tempfile
import zipfile
from pathlib import Path

import requests

try:
    from .config import (
        BUNDLED_DIR,
        BACKUP_DIR,
        GITHUB_RELEASES_API,
    )
    from . import service
except ImportError:
    from src.config import (
        BUNDLED_DIR,
        BACKUP_DIR,
        GITHUB_RELEASES_API,
    )
    from src import service


class UpdateError(Exception):
    """Custom exception for update failures."""


def _notify(tray_notify, title, message, is_error=False):
    """Send a tray notification if callback provided."""
    if tray_notify:
        tray_notify(title, message, is_error)


def _get_latest_release_asset():
    """Return (asset_url, tag_name) for the latest .zip release."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Moonstone-Updater",
    }
    logging.info("Запрос информации о последнем релизе zapret")
    resp = requests.get(GITHUB_RELEASES_API, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise UpdateError(f"GitHub API error: {resp.status_code} {resp.text}")
    data = resp.json()
    tag = data.get("tag_name") or ""
    assets = data.get("assets", [])
    asset = next((a for a in assets if a.get("name", "").endswith(".zip")), None)
    if not asset:
        raise UpdateError("Не найден .zip ассет в последнем релизе")
    url = asset.get("browser_download_url")
    if not url:
        raise UpdateError("У ассета отсутствует ссылка загрузки")
    logging.info(f"Найден релиз {tag}, ассет: {asset.get('name')}")
    return url, tag


def _download_zip(url: str, dst: Path):
    """Download file with streaming to destination."""
    logging.info(f"Скачивание архива: {url}")
    with requests.get(url, stream=True, timeout=60) as r:
        if r.status_code != 200:
            raise UpdateError(f"Ошибка загрузки: {r.status_code} {r.text}")
        with open(dst, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    logging.info(f"Архив сохранён: {dst}")


def _extract_zip(zip_path: Path, extract_to: Path) -> Path:
    """Extract zip and return root extraction path."""
    logging.info(f"Распаковка архива: {zip_path}")
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(extract_to)
    logging.info(f"Архив распакован в {extract_to}")
    return extract_to


def _find_windows_bin(root: Path) -> Path:
    """Find windows-x86_64 binaries directory inside extracted release."""
    candidate = root / "binaries" / "windows-x86_64"
    if candidate.exists():
        return candidate
    for path in root.rglob("windows-x86_64"):
        if path.is_dir():
            return path
    raise UpdateError("Папка binaries/windows-x86_64 не найдена в архиве")


def _backup_existing():
    """Backup current bundled dir, keeping only one backup."""
    if not BUNDLED_DIR.exists():
        logging.warning(f"Папка с текущими файлами не найдена: {BUNDLED_DIR}")
        return
    if BACKUP_DIR.exists():
        logging.info(f"Удаление старой резервной копии: {BACKUP_DIR}")
        shutil.rmtree(BACKUP_DIR, ignore_errors=True)
    logging.info(f"Создание резервной копии: {BACKUP_DIR}")
    shutil.copytree(BUNDLED_DIR, BACKUP_DIR)


def _restore_backup():
    """Restore bundled dir from backup."""
    if not BACKUP_DIR.exists():
        logging.error("Резервная копия отсутствует, восстановление невозможно")
        return
    if BUNDLED_DIR.exists():
        shutil.rmtree(BUNDLED_DIR, ignore_errors=True)
    logging.info("Восстановление файлов из резервной копии")
    shutil.copytree(BACKUP_DIR, BUNDLED_DIR)


def update_bundled(tray_notify=None):
    """
    Update bundled zapret binaries from latest GitHub release.

    tray_notify: callable(title, message, is_error) used for tray messages.
    """
    _notify(tray_notify, "Обновление пакета", "Остановка службы...", False)
    try:
        service.stop_service()

        with tempfile.TemporaryDirectory() as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)
            url, tag = _get_latest_release_asset()

            zip_path = tmp_dir / "zapret_latest.zip"
            _download_zip(url, zip_path)

            extracted_root = _extract_zip(zip_path, tmp_dir)

            # If archive creates a single folder, dive into it
            subdirs = [p for p in extracted_root.iterdir() if p.is_dir()]
            if len(subdirs) == 1:
                extracted_root = subdirs[0]

            windows_bin = _find_windows_bin(extracted_root)

            _backup_existing()

            if BUNDLED_DIR.exists():
                logging.info(f"Очистка текущих файлов: {BUNDLED_DIR}")
                shutil.rmtree(BUNDLED_DIR, ignore_errors=True)
            BUNDLED_DIR.parent.mkdir(parents=True, exist_ok=True)

            logging.info(f"Копирование новых файлов из {windows_bin} в {BUNDLED_DIR}")
            shutil.copytree(windows_bin, BUNDLED_DIR)

        _notify(tray_notify, "Обновление завершено", f"Установлена версия {tag}", False)
        logging.info("Обновление завершено успешно")
    except Exception as exc:  # noqa: BLE001
        logging.error(f"Ошибка обновления: {exc}")
        _restore_backup()
        _notify(tray_notify, "Ошибка обновления", str(exc), True)
        raise

