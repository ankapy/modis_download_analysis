"""
Конфигурация пайплайна MODIS.
"""

from pathlib import Path
from datetime import datetime
from utils import messages

# Базовая директория проекта (корень репозитория).
BASE_DIR = Path(__file__).parent.resolve()

# Минимальный допустимый размер HDF-файла (в байтах).
MIN_HDF_SIZE = 500_000

# Форматы дат и чисел.
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DATE_FORMAT_FILE = "%Y%m%d"
DATE_FORMAT_ISO = "%Y-%m-%d"
TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"
BYTES_TO_MB = 1 / (1024 * 1024)

# Константы для логирования.
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Временной диапазон (может быть переопределён через CLI).
TEMPORAL_RANGE = {
    "start_year": 2000,
    "end_year": datetime.now().year,
    "months": list(range(1, 13)),
}

# Максимальное количество гранул в одном поисковом запросе.
SEARCH_MAX_RESULTS = 20000

# Пути к данным (все внутри BASE_DIR).
DATA_PATHS = {
    "raw": BASE_DIR / "data" / "raw",
    "processed": BASE_DIR / "data" / "processed",
    "tables": BASE_DIR / "data" / "tables",
    "gis": BASE_DIR / "gis",
    "figures": BASE_DIR / "output" / "figures",
    "tables_output": BASE_DIR / "output" / "tables",
    "logs": BASE_DIR / "output" / "logs",
    "gis_output": BASE_DIR / "output" / "gis",
}

# Создание директорий.
for path in DATA_PATHS.values():
    path.mkdir(parents=True, exist_ok=True)

# Путь к GeoPackage с зонами (обязательный параметр).
ZONES_GPKG = DATA_PATHS["gis"] / "zones.gpkg"

# Параметры загрузки.
DOWNLOAD_BATCH_SIZE = 15
DOWNLOAD_MAX_RETRIES = 3
DOWNLOAD_PAUSE_BATCH = 5
DOWNLOAD_PAUSE_GRANULE = 2
DOWNLOAD_PAUSE_PRODUCT = 5  # Пауза между разными продуктами
DOWNLOAD_PAUSE_YEAR = 10  # Пауза между годами

# Ожидаемое количество гранул по продуктам.
EXPECTED_GRANULES = {
    "MOD11A2": 120,
    "MOD13Q1": 77,
    "MOD10A2": 46,
    "MOD10A1": 365,
    "MCD12Q1": 1,
    "MOD14A1": 365,
    "MCD43A3": 365,
}

# Конвертация.
CONVERT_MAX_WORKERS = 4

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
        "unit": "°C",
        "qa_band": "QC_Day",
        "qa_mask": 3,
        "qa_good": 0,
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
        "unit": "index",
        "qa_band": "VI_Quality",
        "qa_mask": 3,
        "qa_good": 0,
    },
    # === ВЕГЕТАЦИОННЫЕ ИНДЕКСЫ ===
    "EVI": {
        "product": "MOD13Q1",
        "version": "061",
        "band": "EVI",
        "resolution": 250,
        "temporal_resolution": "16-day",
        "scale_factor": 0.0001,
        "offset": 0,
        "no_data_value": -3000,
        "unit": "index",
        "qa_band": "VI_Quality",
        "qa_mask": 3,
        "qa_good": 0,
    },
    "EVI2": {
        "product": "MOD13Q1",
        "version": "061",
        "band": "EVI2",
        "resolution": 250,
        "temporal_resolution": "16-day",
        "scale_factor": 0.0001,
        "offset": 0,
        "no_data_value": -3000,
        "unit": "index",
        "qa_band": "VI_Quality",
        "qa_mask": 3,
        "qa_good": 0,
    },
    # === ТЕМПЕРАТУРА ПОВЕРХНОСТИ ===
    "LST_Night": {
        "product": "MOD11A2",
        "version": "061",
        "band": "LST_Night_1km",
        "resolution": 1000,
        "temporal_resolution": "8-day",
        "scale_factor": 0.02,
        "offset": -273.15,
        "no_data_value": 0,
        "unit": "°C",
        "qa_band": "QC_Night",
        "qa_mask": 3,
        "qa_good": 0,
    },
    # === СНЕЖНЫЙ ПОКРОВ (QA не применяется: облака и fill входят в классификацию) ===
    "Snow": {
        "product": "MOD10A2",
        "version": "061",
        "band": "Snow_Cover",
        "resolution": 500,
        "temporal_resolution": "8-day",
        "scale_factor": 1,
        "offset": 0,
        "no_data_value": 250,
        "unit": "%",
    },
    "Snow_Daily": {
        "product": "MOD10A1",
        "version": "061",
        "band": "Snow_Cover",
        "resolution": 500,
        "temporal_resolution": "daily",
        "scale_factor": 1,
        "offset": 0,
        "no_data_value": 250,
        "unit": "%",
    },
    # === ЗЕМЛЕПОКРОВ (категориальный продукт, QA не применяется) ===
    "Land_Cover": {
        "product": "MCD12Q1",
        "version": "061",
        "band": "LC_Type1",
        "resolution": 500,
        "temporal_resolution": "yearly",
        "scale_factor": 1,
        "offset": 0,
        "no_data_value": 255,
        "unit": "class",
    },
    # === ПОЖАРЫ (QA не применяется) ===
    "Fire": {
        "product": "MOD14A1",
        "version": "061",
        "band": "FireMask",
        "resolution": 1000,
        "temporal_resolution": "daily",
        "scale_factor": 1,
        "offset": 0,
        "no_data_value": 255,
        "unit": "class",
    },
    # === ОТРАЖАТЕЛЬНАЯ СПОСОБНОСТЬ ===
    "Albedo": {
        "product": "MCD43A3",
        "version": "061",
        "band": "Albedo_BSA",
        "resolution": 500,
        "temporal_resolution": "daily",
        "scale_factor": 0.001,
        "offset": 0,
        "no_data_value": 32767,
        "unit": "fraction",
        "qa_band": "Quality",
        "qa_mask": 2,
        "qa_good": 0,
    },
}

# Обязательные ключи конфигурации продукта.
REQUIRED_PRODUCT_KEYS = (
    "product",
    "band",
    "scale_factor",
    "offset",
    "no_data_value",
    "unit",
)


def validate_config():
    """Проверка целостности конфигурации продуктов MODIS."""
    for name, cfg in MODIS_PRODUCTS.items():
        for key in REQUIRED_PRODUCT_KEYS:
            if key not in cfg:
                raise ValueError(messages.ERR_CONFIG_MISSING_KEY.format(name, key))


# Выполняется при импорте: опечатка в конфиге падает сразу, а не в глубине GDAL.
validate_config()
