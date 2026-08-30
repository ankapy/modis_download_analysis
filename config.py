"""
Конфигурация пайплайна MODIS.
Единственный файл, который нужно править под свою задачу:
пути, период, продукты и параметры загрузки.
"""

from pathlib import Path
from datetime import datetime
from utils import messages

# === ПУТИ ===

# Базовая директория проекта (корень репозитория).
# Все остальные пути строятся относительно неё, поэтому проект можно
# переносить между машинами без правок конфигурации.
BASE_DIR = Path(__file__).parent.resolve()

# Пути к данным и результатам (все внутри BASE_DIR).
# Меняйте только при необходимости; директории создаются автоматически.
DATA_PATHS = {
    "raw": BASE_DIR / "data" / "raw",  # скачанные HDF-гранулы
    "processed": BASE_DIR / "data" / "processed",  # конвертированные GeoTIFF
    "tables": BASE_DIR / "data" / "tables",  # CSV-статистика и отчёты
    "gis": BASE_DIR / "gis",  # входные ГИС-файлы (зоны)
    "figures": BASE_DIR / "output" / "figures",  # графики анализа
    "tables_output": BASE_DIR / "output" / "tables",  # Excel и сводки
    "logs": BASE_DIR / "output" / "logs",  # логи и provenance
    "gis_output": BASE_DIR / "output" / "gis",  # Mosaic Dataset (gdb)
}

# Создание директорий при импорте конфига.
for path in DATA_PATHS.values():
    path.mkdir(parents=True, exist_ok=True)

# Путь к GeoPackage с полигонами зон (обязательный входной файл).
# Положите файл сюда либо передавайте --zones в командах CLI.
ZONES_GPKG = DATA_PATHS["gis"] / "zones.gpkg"

# === ВРЕМЕННОЙ ДИАПАЗОН ===

# Период по умолчанию; переопределяется флагами CLI (--start-year и т.д.).
# start_year = 2000 — начало архива MODIS, end_year — текущий год.
TEMPORAL_RANGE = {
    "start_year": 2000,
    "end_year": datetime.now().year,
    "months": list(range(1, 13)),
}

# === ПАРАМЕТРЫ ЗАГРУЗКИ ===

# Гранул в одном пакете скачивания.
DOWNLOAD_BATCH_SIZE = 15
# Повторных попыток для одной гранулы при сбое.
DOWNLOAD_MAX_RETRIES = 3
# Пауза между пакетами, сек — защита от ограничений сервера NASA.
DOWNLOAD_PAUSE_BATCH = 5
# Пауза между гранулами внутри пакета, сек.
DOWNLOAD_PAUSE_GRANULE = 2
# Пауза между продуктами, сек.
DOWNLOAD_PAUSE_PRODUCT = 5
# Пауза между годами, сек.
DOWNLOAD_PAUSE_YEAR = 10

# Максимум гранул в одном поисковом запросе к NASA.
SEARCH_MAX_RESULTS = 20000

# Ожидаемое число гранул за год по продуктам (для типовой области).
# Эвристика пропуска «полностью скачанных» лет; значения приблизительные,
# реальное число зависит от вашей области. Нет продукта — проверка не идёт.
EXPECTED_GRANULES = {
    "MOD11A2": 120,
    "MOD13Q1": 77,
    "MOD10A2": 46,
    "MOD10A1": 365,
    "MCD12Q1": 1,
    "MOD14A1": 365,
    "MCD43A3": 365,
}

# === ВАЛИДАЦИЯ И КОНВЕРТАЦИЯ ===

# Минимальный размер HDF-файла в байтах: файлы меньше считаются недокачанными.
MIN_HDF_SIZE = 500_000

# Число потоков конвертации HDF -> GeoTIFF.
CONVERT_MAX_WORKERS = 4

# Настройки GDAL: кэш памяти (МБ) и потоки чтения/записи.
GDAL_CACHE_MAX = "1024"
GDAL_NUM_THREADS = "ALL_CPUS"

# === ФОРМАТЫ ВЫВОДА ===

# Формат CSV-таблиц: разделитель и десятичный знак.
# По умолчанию — русская локаль Excel («;» и «,»).
CSV_SEPARATOR = ";"
CSV_DECIMAL = ","

# Служебные форматы дат и чисел — менять не нужно.
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"  # даты в консоли и логах
DATE_FORMAT_FILE = "%Y%m%d"  # даты в именах файлов логов
DATE_FORMAT_ISO = "%Y-%m-%d"  # даты в метаданных и таблицах
TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"  # метки времени в именах отчётов
BYTES_TO_MB = 1 / (1024 * 1024)  # байты -> мегабайты

# Формат строки логирования (служебный).
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# === ПРОДУКТЫ MODIS =======
# Ключ словаря — внутреннее имя продукта в пайплайне (CLI: --products LST,NDVI;
# имена папок в data/processed).
#
# Обязательные поля:
#   product             — код коллекции NASA (short name для earthaccess);
#   version             — версия коллекции (для MODIS сейчас «061»);
#   band                — имя поддатасета (бэнда) для извлечения;
#   resolution          — разрешение, м (справочно);
#   temporal_resolution — периодичность съёмки (справочно);
#   scale_factor        — множитель перевода DN в физические величины;
#   offset              — слагаемое: значение = DN * scale_factor + offset;
#   no_data_value       — fill-значение сырых данных; маскируется ДО масштаба;
#   unit                — единица измерения; идёт в метаданные и подписи осей.
#
# Необязательные поля (QA-фильтрация облаков и плохих пикселей):
#   qa_band — имя QA-поддатасета; qa_mask — битовая маска; qa_good — значение
#   после маски, означающее «хороший» пиксель: (qa & qa_mask) == qa_good.
#   Нет полей — QA-фильтрация для продукта не применяется.
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
    # === СНЕЖНЫЙ ПОКРОВ ===
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
    # === ЗЕМЛЕЛЬНЫЙ ПОКРОВ ===
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
    # === ПОЖАРЫ ===
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

# Обязательные ключи конфигурации продукта: проверяются при старте.
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


# Выполняется при импорте: ошибка в конфиге падает сразу, а не в глубине GDAL.
validate_config()
