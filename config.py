"""
Конфигурационный файл для обработки данных MODIS
"""

import os
from datetime import datetime, timedelta

# Базовая директория проекта
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)

# Временной диапазон
TEMPORAL_RANGE = {
    "start_year": 2015,
    "end_year": 2025,
    "veg_start": "05-01",
    "veg_end": "09-30",
}

# Пространственный диапазон
SPATIAL_RANGE = {
    "lat_min": 52.0,
    "lat_max": 76.0,
    "lon_min": 89.5,
    "lon_max": 95.5,
}

# Пути к данным (ОБЪЯВЛЯЕМ РАНЬШЕ, ЧТОБЫ ИСПОЛЬЗОВАТЬ В ZONES_GEOJSON)
DATA_PATHS = {
    "raw": os.path.join(PROJECT_DIR, "data", "raw"),
    "processed": os.path.join(PROJECT_DIR, "data", "processed"),
    "tables": os.path.join(PROJECT_DIR, "data", "tables"),
    "gis": os.path.join(PROJECT_DIR, "gis"),
    "figures": os.path.join(PROJECT_DIR, "output", "figures"),
    "tables_output": os.path.join(PROJECT_DIR, "output", "tables"),
}

for path in DATA_PATHS.values():
    os.makedirs(path, exist_ok=True)

# Путь к GeoJSON с полигонами зон
# ZONES_GEOJSON = os.path.join(DATA_PATHS["gis"], "zones.geojson")
ZONES_GPKG = os.path.join(DATA_PATHS["gis"], "zones.gpkg")
ZONES_LAYER = "natural_zones"  # Имя слоя в геопакете

# MODIS продукты
MODIS_PRODUCTS = {
    "LST": {
        "product": "MOD11A2",
        "version": "061",
        "collection": "061",
        "band": "LST_Day_1km",
        "qa_band": "QC_Day",
        "resolution": 1000,
        "temporal_resolution": "8-day",
        "scale_factor": 0.02,
        "offset": -273.15,
        "no_data_value": 0,
    },
    "NDVI": {
        "product": "MOD13Q1",
        "version": "061",
        "collection": "061",
        "band": "NDVI",
        "qa_band": "VI_Quality",
        "resolution": 250,
        "temporal_resolution": "16-day",
        "scale_factor": 0.0001,
        "offset": 0,
        "no_data_value": -3000,
    },
}

# Природные зоны (оставлено для совместимости, если понадобится)
NATURAL_ZONES = {
    1: {"name": "Степь", "lat_range": (52, 54)},
    2: {"name": "Лесостепь", "lat_range": (54, 56)},
    3: {"name": "Южная тайга", "lat_range": (56, 62)},
    4: {"name": "Северная тайга", "lat_range": (62, 67)},
    5: {"name": "Лесотундра", "lat_range": (67, 69)},
    6: {"name": "Тундра", "lat_range": (69, 76)},
}

if __name__ == "__main__":
    print("Конфигурация загружена успешно!")
    print(f"ZONES_GEOJSON: {ZONES_GPKG}")
