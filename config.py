"""
Конфигурация пайплайна MODIS.
"""

from pathlib import Path

# Базовая директория проекта (корень репозитория).
BASE_DIR = Path(__file__).parent.resolve()

# Временной диапазон (может быть переопределён через CLI).
TEMPORAL_RANGE = {
    "start_year": 2015,
    "end_year": 2025,
    "months": list(range(1, 13)),
}

# Пространственный диапазон (рассчитывается автоматически из zones.gpkg).
SPATIAL_RANGE = None

# Пути к данным (все внутри BASE_DIR).
DATA_PATHS = {
    "raw": BASE_DIR / "data" / "raw",
    "processed": BASE_DIR / "data" / "processed",
    "tables": BASE_DIR / "data" / "tables",
    "gis": BASE_DIR / "gis",
    "figures": BASE_DIR / "output" / "figures",
    "tables_output": BASE_DIR / "output" / "tables",
    "logs": BASE_DIR / "output" / "logs",
}

# Создание директорий.
for path in DATA_PATHS.values():
    path.mkdir(parents=True, exist_ok=True)

# Путь к GeoPackage с зонами (обязательный параметр).
ZONES_GPKG = DATA_PATHS["gis"] / "zones.gpkg"

# MODIS продукты (расширяемый словарь).
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
    # === ВЕГЕТАЦИОННЫЕ ИНДЕКСЫ ===
    # "EVI": {
    #     "product": "MOD13Q1",
    #     "version": "061",
    #     "band": "EVI",
    #     "resolution": 250,
    #     "temporal_resolution": "16-day",
    #     "scale_factor": 0.0001,
    #     "offset": 0,
    #     "no_data_value": -3000,
    # },
    # "EVI2": {
    #     "product": "MOD13Q1",
    #     "version": "061",
    #     "band": "EVI2",
    #     "resolution": 250,
    #     "temporal_resolution": "16-day",
    #     "scale_factor": 0.0001,
    #     "offset": 0,
    #     "no_data_value": -3000,
    # },
    # === ТЕМПЕРАТУРА ПОВЕРХНОСТИ ===
    # "LST_Night": {
    #     "product": "MOD11A2",
    #     "version": "061",
    #     "band": "LST_Night_1km",
    #     "resolution": 1000,
    #     "temporal_resolution": "8-day",
    #     "scale_factor": 0.02,
    #     "offset": -273.15,
    #     "no_data_value": 0,
    # },
    # === СНЕЖНЫЙ ПОКРОВ ===
    # "Snow": {
    #     "product": "MOD10A2",
    #     "version": "061",
    #     "band": "Snow_Cover",
    #     "resolution": 500,
    #     "temporal_resolution": "8-day",
    #     "scale_factor": 1,
    #     "offset": 0,
    #     "no_data_value": 250,
    # },
    # "Snow_Daily": {
    #     "product": "MOD10A1",
    #     "version": "061",
    #     "band": "Snow_Cover",
    #     "resolution": 500,
    #     "temporal_resolution": "daily",
    #     "scale_factor": 1,
    #     "offset": 0,
    #     "no_data_value": 250,
    # },
    # === ЗЕМЛЕПОКРОВ ===
    # "Land_Cover": {
    #     "product": "MCD12Q1",
    #     "version": "061",
    #     "band": "LC_Type1",
    #     "resolution": 500,
    #     "temporal_resolution": "yearly",
    #     "scale_factor": 1,
    #     "offset": 0,
    #     "no_data_value": 255,
    # },
    # === АТМОСФЕРНЫЕ ПРОИЗВЕДЕНИЯ ===
    # "AOD": {
    #     "product": "MOD04_L2",
    #     "version": "061",
    #     "band": "AOD_550",
    #     "resolution": 1000,
    #     "temporal_resolution": "daily",
    #     "scale_factor": 0.001,
    #     "offset": 0,
    #     "no_data_value": -999,
    # },
    # === ПОЖАРЫ ===
    # "Fire": {
    #     "product": "MOD14A1",
    #     "version": "061",
    #     "band": "FireMask",
    #     "resolution": 1000,
    #     "temporal_resolution": "daily",
    #     "scale_factor": 1,
    #     "offset": 0,
    #     "no_data_value": 255,
    # },
    # === ОТРАЖАТЕЛЬНАЯ СПОСОБНОСТЬ ===
    # "Albedo": {
    #     "product": "MCD43A3",
    #     "version": "061",
    #     "band": "Albedo_BSA",
    #     "resolution": 500,
    #     "temporal_resolution": "daily",
    #     "scale_factor": 0.001,
    #     "offset": 0,
    #     "no_data_value": 32767,
    # },
}

# Константы для логирования.
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

"""
- NATURAL_ZONES заменить нейм на ZONES да и вообще убрать эти зоны. 
если нужны эти значения в словаре - все брать из графики.
- в коментах перечислить все MODIS_PRODUCTS и настроить интерактивный
выбор при запуске модуля
- 02_1_validate_and_cleanup должен быть вторым этапом, остальные
должны сдвинуться. 
- классы должны быть везде абстрактные в коде а не конкретные (степь, лесостепь и тд)
- 
"""
