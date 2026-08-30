"""
Сохранение параметров запуска для воспроизводимости результатов.
"""

import json
import importlib
import platform
from datetime import datetime
from pathlib import Path

from config import DATA_PATHS, TIMESTAMP_FORMAT
from utils.logger import setup_logger
from utils import messages

logger = setup_logger(__name__)

_VERSION_MODULES = ("numpy", "pandas", "earthaccess", "osgeo.gdal")


def _module_version(name: str):
    """Версия модуля или None, если модуль недоступен."""
    try:
        module = importlib.import_module(name)
        return getattr(module, "__version__", None)
    except ImportError:
        return None


def save_run_provenance(stage: str, params: dict):
    """Сохранение JSON с параметрами запуска этапа."""
    record = {
        "stage": stage,
        "started_at": datetime.now().isoformat(),
        "params": {
            key: str(value) if isinstance(value, Path) else value
            for key, value in params.items()
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "versions": {name: _module_version(name) for name in _VERSION_MODULES},
        },
    }
    stamp = datetime.now().strftime(TIMESTAMP_FORMAT)
    path = DATA_PATHS["logs"] / f"run_{stage}_{stamp}.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2, default=str)
        logger.info(messages.INFO_PROVENANCE_SAVED.format(path))
    except OSError as e:
        logger.warning(messages.WARN_PROVENANCE_FAILED.format(str(e)))
