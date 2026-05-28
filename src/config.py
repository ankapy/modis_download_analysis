# -*- coding: utf-8 -*-
"""Конфигурация проекта: параметры, пути, валидация."""

import os
from pathlib import Path
from src import messages as M


class ConfigError(Exception):
    """Исключение для ошибок валидации конфигурации."""

    pass


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

TEMPORAL_RANGE = {
    "start_year": 2015,
    "end_year": 2025,
    "veg_start": "05-01",
    "veg_end": "09-30",
}

SPATIAL_RANGE = {
    "lat_min": 52.0,
    "lat_max": 76.0,
    "lon_min": 89.5,
    "lon_max": 95.5,
}

# Убраны лишние папки. Пути строго относительно PROJECT_ROOT
DATA_PATHS = {
    "raw": PROJECT_ROOT / "data" / "raw",
    "processed": PROJECT_ROOT / "data" / "processed",
    "tables": PROJECT_ROOT / "data" / "tables",
    "gis": PROJECT_ROOT / "gis",
    "figures": PROJECT_ROOT / "output" / "figures",
    "tables_output": PROJECT_ROOT / "output" / "tables",
}

ZONE_FIELD_NAME = "target_zone"
ZONES_GPKG = DATA_PATHS["gis"] / "zones.gpkg"


def validate_config():
    """Валидация конфигурации при старте. Создаёт директории при необходимости."""
    errors = []

    # Проверка диапазонов координат
    lat_min = SPATIAL_RANGE["lat_min"]
    lat_max = SPATIAL_RANGE["lat_max"]
    lon_min = SPATIAL_RANGE["lon_min"]
    lon_max = SPATIAL_RANGE["lon_max"]

    if not (-90 <= lat_min <= 90):
        errors.append(M.ERR_INVALID_COORDS.format(reason=f"lat_min={lat_min}"))
    if not (-90 <= lat_max <= 90):
        errors.append(M.ERR_INVALID_COORDS.format(reason=f"lat_max={lat_max}"))
    if not (-180 <= lon_min <= 180):
        errors.append(M.ERR_INVALID_COORDS.format(reason=f"lon_min={lon_min}"))
    if not (-180 <= lon_max <= 180):
        errors.append(M.ERR_INVALID_COORDS.format(reason=f"lon_max={lon_max}"))
    if lat_min >= lat_max:
        errors.append(M.ERR_INVALID_COORDS.format(reason="lat_min >= lat_max"))
    if lon_min >= lon_max:
        errors.append(M.ERR_INVALID_COORDS.format(reason="lon_min >= lon_max"))
    if TEMPORAL_RANGE["start_year"] > TEMPORAL_RANGE["end_year"]:
        errors.append(M.ERR_INVALID_DATE_RANGE.format(reason="start_year > end_year"))

    for name, path in DATA_PATHS.items():
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            errors.append(M.ERR_DIR_NOT_FOUND.format(path=path) + f": {e}")

    if errors:
        raise ConfigError(M.ERR_CONFIG_INVALID.format(reason="; ".join(errors)))
