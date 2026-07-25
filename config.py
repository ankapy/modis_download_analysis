"""
Конфигурация пайплайна MODIS.
"""

from pathlib import Path

# Базовая директория проекта.
BASE_DIR = Path(__file__).parent.resolve()

# Форматы дат.
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"  # Для логов
DATE_FORMAT_FILE = "%Y%m%d_%H%M%S"  # Для имен файлов
DATE_FORMAT_ISO = "%Y-%m-%d"  # Для дат в метаданных

# Временной диапазон (переопределяется через CLI).
TEMPORAL_RANGE = {
    "start_year": 2015,
    "end_year": 2025,
    "months": list(range(1, 13)),
}

# Пути к данным.
DATA_PATHS = {
    "raw": BASE_DIR / "data" / "raw",
    "processed": BASE_DIR / "data" / "processed",
    "tables": BASE_DIR / "data" / "tables",
    "gis": BASE_DIR / "gis",
    "figures": BASE_DIR / "output" / "figures",
    "tables_output": BASE_DIR / "output" / "tables",
    "logs": BASE_DIR / "output" / "logs",
}

for path in DATA_PATHS.values():
    path.mkdir(parents=True, exist_ok=True)

ZONES_GPKG = DATA_PATHS["gis"] / "zones.gpkg"

# Параметры загрузки и валидации (вынесены для гибкости).
DOWNLOAD_BATCH_SIZE = 15
DOWNLOAD_MAX_RETRIES = 3
DOWNLOAD_PAUSE_BATCH = 5
DOWNLOAD_PAUSE_GRANULE = 2

EXPECTED_GRANULES = {
    "MOD11A2": 120,
    "MOD13Q1": 77,
}

MIN_FILE_SIZE = {
    "MOD11A2": 500_000,
    "MOD13Q1": 500_000,
}

# Настройки GDAL.
GDAL_CACHE_MAX = "1024"
GDAL_NUM_THREADS = "ALL_CPUS"

# Формат CSV.
CSV_SEPARATOR = ";"
CSV_DECIMAL = ","

# MODIS продукты.
MODIS_PRODUCTS = {
    "LST": {
        "product": "MOD11A2",
        "version": "061",
        "band": "LST_Day_1km",
        "resolution": 1000,
        "temporal_resolution": "8-day",
        "scale_factor": 0.02,
        "offset": -273.15,
        "no_data_value": 0,
    },
    "NDVI": {
        "product": "MOD13Q1",
        "version": "061",
        "band": "NDVI",
        "resolution": 250,
        "temporal_resolution": "16-day",
        "scale_factor": 0.0001,
        "offset": 0,
        "no_data_value": -3000,
    },
    "EVI": {
        "product": "MOD13Q1",
        "version": "061",
        "band": "EVI",
        "resolution": 250,
        "temporal_resolution": "16-day",
        "scale_factor": 0.0001,
        "offset": 0,
        "no_data_value": -3000,
    },
    "LST_Night": {
        "product": "MOD11A2",
        "version": "061",
        "band": "LST_Night_1km",
        "resolution": 1000,
        "temporal_resolution": "8-day",
        "scale_factor": 0.02,
        "offset": -273.15,
        "no_data_value": 0,
    },
    "Snow": {
        "product": "MOD10A2",
        "version": "061",
        "band": "Snow_Cover",
        "resolution": 500,
        "temporal_resolution": "8-day",
        "scale_factor": 1,
        "offset": 0,
        "no_data_value": 250,
    },
    "Land_Cover": {
        "product": "MCD12Q1",
        "version": "061",
        "band": "LC_Type1",
        "resolution": 500,
        "temporal_resolution": "yearly",
        "scale_factor": 1,
        "offset": 0,
        "no_data_value": 255,
    },
}
