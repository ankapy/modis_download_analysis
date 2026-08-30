"""
Сообщения для логирования и вывода в терминал.
"""

# === ОБЩИЕ СООБЩЕНИЯ ===
MSG_CONFIG_LOADED = "Конфигурация загружена."
MSG_BASE_DIR = "BASE_DIR: {}"
MSG_ZONES_PATH = "ZONES_GPKG: {}"
MSG_PRODUCTS = "Продукты: {}"
MSG_LOADING = "Загрузка данных: {}"
MSG_LOADED = "Загружено записей: {}"

# === ЗАГОЛОВКИ ===
HEADER_PIPELINE = "MODIS Pipeline"
HEADER_DOWNLOADER = "MODIS Downloader via earthaccess"
HEADER_VALIDATOR = "MODIS HDF Validator & Cleanup"
HEADER_CONVERTER = "MODIS HDF to GeoTIFF Converter"
HEADER_ZONAL_STATS = "Zonal Statistics: Pure GDAL + NumPy (OPTIMIZED)"
HEADER_ANALYZER = "MODIS Analyzer"

# === РАЗДЕЛИТЕЛИ ===
SEPARATOR = "=" * 60
SEPARATOR_THIN = "-" * 60

# === СТАТУСЫ И ВРЕМЯ ===
STATUS_SUCCESS = "Успешно: {}"
STATUS_SKIPPED = "Пропущено: {}"
STATUS_FAILED = "Ошибок: {}"
STATUS_START_TIME = "Время начала: {}"
STATUS_END_TIME = "Время окончания: {}"
STATUS_MODE_CHECK = "РЕЖИМ ПРОВЕРКИ — файлы не будут удалены"
STATUS_MODE_CHECK_DELETE = "ПРОВЕРКА + УДАЛЕНИЕ"
STATUS_THREADS = "Потоков: {}"
STATUS_MULTITHREAD = ">>> РЕЖИМ: МНОГОПОТОЧНОСТЬ ({} потоков) <<<"

# === ЛОГИРОВАНИЕ: АВТОРИЗАЦИЯ И ЗАГРУЗКА ===
LOG_AUTH_START = "Авторизация в NASA Earthdata..."
LOG_AUTH_OK = "Авторизация через .netrc успешна."
LOG_AUTH_WARN = ".netrc не найден: {}"
LOG_SEARCH_START = "Поиск гранул..."
LOG_GRANULES_FOUND = "Найдено гранул: {}"
LOG_GRANULES_NOT_FOUND = "Гранулы не найдены."
LOG_AUTH_STRATEGY_FAIL = "Стратегия {} не удалась: {}"
LOG_DOWNLOAD_START = "К загрузке: {} из {}"
LOG_DOWNLOAD_OK = "[{}/{}] OK"
LOG_DOWNLOAD_WARN = "Пустой результат (попытка {})"
LOG_DOWNLOAD_ERROR = "[ERROR {}/{}] {}..."
LOG_DOWNLOAD_PAUSE = "[PAUSE] Ожидание {} сек..."
LOG_DOWNLOAD_FAIL = "Пропущено после {} попыток"
LOG_BATCH_START = "[BATCH {}] Загрузка гранул {}-{}..."
LOG_BATCH_PAUSE = "[PAUSE] Пауза {}с..."
LOG_BATCH_ERROR = "Пакет {}: {}"
LOG_RESULT = "[RESULT] {}/{}: скачано {}, ошибок {}"
LOG_INTERRUPT = "Прервано на пакете {}"

# === ЛОГИРОВАНИЕ: ВАЛИДАЦИЯ ===
LOG_VALIDATION_START = "Проверка {}/{}"
LOG_VALIDATION_SKIP = "Директория не найдена: {}"
LOG_REPORT_SAVED = "Отчёт сохранён: {}"
LOG_REDOWNLOAD_SAVED = "Список для перескачивания: {}"
LOG_DELETE_START = "Удаление повреждённых файлов"
LOG_DELETE_OK = "Удалено файлов: {}"

# === ЛОГИРОВАНИЕ: КОНВЕРТАЦИЯ ===
LOG_CONVERSION_START = "Обработка {} за {}: {} файлов"
LOG_CONVERSION_WARN = "Файлы не найдены: {}"
LOG_CONVERSION_OK = "Сконвертировано: {}/{}"
LOG_CONVERSION_ERROR = "Ошибок конвертации: {}"
LOG_CONVERSION_FILE_OK = "OK: {}"
INFO_SKIPPED_EXISTING = "Пропущено (уже существует): {}"

# === ЛОГИРОВАНИЕ: ЗОНАЛЬНАЯ СТАТИСТИКА ===
LOG_ZONES_LOADED = "Загружено зон: {}"
LOG_ZONE_INFO = "  {}: {}"
LOG_RASTERIZE_START = "Растеризация маски зон"
LOG_RASTERIZE_OK = "Маска зон растеризована."
INFO_RASTERS_FOUND = "Найдено {} растра для обработки."
INFO_TEST_FILE = "[TEST] Найден {}"
INFO_PROCESSED_RASTERS = "Обработано {}/{} растра..."
INFO_EXISTING_FILE_FOUND = "Найден существующий файл: {}"
INFO_LOADING_INDICES = "Загрузка индексов для пропуска сделанного..."
INFO_SKIPPED_RECORDS = "Пропущено {} уже готовых записей."
LOG_SAVED_OK = "Сохранено {} записей в {}"
LOG_SAVED_AGG = "Сохранена агрегированная сводка в {}"
LOG_NO_DATA = "Нет данных для извлечения. Проверьте пересечение зон с растрами."
LOG_FINISHED = "Завершено за {:.1f} сек"

# === ПРОГРЕСС-БАРЫ ===
PROGRESS_VALIDATION = "Валидация {}"
PROGRESS_DELETE = "Удаление"

# === QA-ФИЛЬТРАЦИЯ ===
WARN_QA_BAND_NOT_FOUND = "QA-бэнд {} не найден в файле {}: фильтрация пропущена."
WARN_QA_SHAPE_MISMATCH = (
    "Разрешение QA-бэнда {} не совпадает с данными в файле {}: фильтрация пропущена."
)

# === ГИС-ЭКСПОРТ ===
INFO_VRT_SAVED = "VRT-мозаика сохранена: {}"
WARN_VRT_FAILED = "Не удалось собрать VRT {}: {}"
INFO_MOSAIC_SAVED = "Mosaic Dataset создан: {}"
WARN_ARCPY_NOT_FOUND = "arcpy недоступен: сборка Mosaic Dataset пропущена."
WARN_MOSAIC_FAILED = "Не удалось создать Mosaic Dataset {}: {}"

# === RUN-ALL ===
INFO_RUN_ALL_START = "Запуск полного пайплайна: 01 → 05."
INFO_RUN_ALL_STAGE = ">>> ЭТАП: {}"

# === ШАГИ АНАЛИЗА ===
ANALYSIS_STEP_SEASONAL = "[1/6] Сезонная динамика..."
ANALYSIS_STEP_TRENDS = "[2/6] Межгодовые тренды..."
ANALYSIS_STEP_GRADIENT = "[3/6] Широтный градиент (месяц {})..."
ANALYSIS_STEP_AMPLITUDE = "[4/6] Сезонная амплитуда..."
ANALYSIS_STEP_CORRELATION = "[5/6] Корреляция продуктов (месяц {})..."
ANALYSIS_STEP_TABLES = "[6/6] Сводные таблицы..."

# === ЛОГИРОВАНИЕ: АНАЛИЗ ===
LOG_ANALYSIS_OK = "Сохранено: {}"
LOG_ANALYSIS_WARN = "Пропуск {}: нет {}"
LOG_ANALYSIS_NO_DATA = "Нет данных для градиента {} в месяц {}"
LOG_ANALYSIS_NO_LAT = "Широтный градиент пропущен: нет колонки lat_center в данных."
INFO_SKIP_CORRELATION = "Пропуск корреляции: недостаточно данных для продуктов {} и {}."
WARN_MISSING_COLS = "В файле отсутствуют колонки: {}. Фильтрация пропущена."

# === ОШИБКИ ===
ERR_CRITICAL = "Критическая ошибка: {}"
ERR_FILE_NOT_FOUND = "Файл не найден: {}"
ERR_GPKG_NOT_FOUND = "GeoPackage не найден: {}"
ERR_OPEN_FILE = "Не удалось открыть {}"
ERR_NO_SUBDATASETS = "Нет поддатасетов в файле"
ERR_MISSING_DATASETS = "Не найдены датасеты {}"
ERR_SAVE_GEOTIFF = "Ошибка сохранения GeoTIFF: {}"
ERR_GEOM_TRANSFORM = "Ошибка трансформации геометрии для зоны '{}': {}"
ERR_CONVERSION_LST = "Конвертация LST {}: {}"
ERR_CONVERSION_NDVI = "Конвертация NDVI {}: {}"
ERR_CSV_READ_FAILED = "Не удалось прочитать файл {}. Ошибка: {}"
ERR_INVALID_INPUT = "Неверный ввод: {}. Попробуйте снова."
ERR_NO_ZONES = "Зоны не загружены."
ERR_NO_RASTERS = "Растров не найдено."
ERR_YEAR_RANGE = "Год должен быть в диапазоне {}-{}"
ERR_MONTH_RANGE = "Месяц должен быть в диапазоне {}-{}"
ERR_FILE_NOT_GPKG = "Файл не найден или неверный формат: {}"
ERR_DELETE_FILE = "Не удалось удалить {}: {}"
ERR_AUTH_FAILED = "Ошибка авторизации. Проверьте наличие файла .netrc или переменные окружения EARTHDATA_USERNAME и EARTHDATA_PASSWORD."
ERR_CONVERSION_FAILED = "Ошибка конвертации продукта {} (файл {}): {}"
ERR_CONFIG_MISSING_KEY = "Конфигурация продукта '{}' не содержит обязательный ключ: {}"


# === ПРЕДУПРЕЖДЕНИЯ ===
WARN_FILE_TOO_SMALL = "Файл слишком мал: {:.2f} МБ"
WARN_NO_COVERAGE = "Полигоны не пересекают область покрытия MODIS"
WARN_READ_FILE_FAILED = "Не удалось прочитать файл: {}. Начинаем с нуля."
WARN_INVALID_ZONE = "Неизвестная зона: '{}', пропуск"
WARN_CORRELATION_NO_DATA = "Нет общих точек для корреляции."
WARN_CORRELATION_INSUFFICIENT = "Недостаточно данных для корреляции {} и {}."
WARN_INVALID_NUMBER = "Неверный номер: {}"
WARN_NO_DATA_DIRS = (
    "Нет директорий с данными для валидации. Сначала запустите 01_download."
)

# === ИНФОРМАЦИОННЫЕ ===
INFO_EXISTING_FILES = "Уже скачано {}/{} HDF-файлов"
INFO_SKIP_ALL_DOWNLOADED = "Все файлы уже скачаны"
INFO_PERIOD = "Период: {} – {}"
INFO_DIRECTORY = "Директория: {}"
INFO_BBOX = "Bounding box: {}"
INFO_YEAR_HEADER = ">>> ГОД {} ({}/{})"
INFO_PRODUCT_HEADER = "[{}/{}] {} v{}"
INFO_SUMMARY_HEADER = "ИТОГИ ЗАГРУЗКИ"
INFO_FINAL_STATS = "ИТОГОВАЯ СТАТИСТИКА"
INFO_CONVERSION_DONE = "Конвертация завершена"
INFO_GDAL_VERSION = "GDAL версия: {}"
INFO_YEAR_PROCESSING = ">>> Год: {}"
INFO_INTERRUPT = "Прервано пользователем"
INFO_CONTINUE = "Запустите снова для продолжения"
INFO_DELETE_FAILED = "Не удалось удалить {}: {}"
INFO_NO_PRODUCTS = "Нет данных для выбранных продуктов."
INFO_ANALYSIS_DONE = "Завершено."
INFO_FIGURES_DIR = "Графики: {}"
INFO_ZONES_HEADER = "=== Путь к зонам ==="
INFO_TEMPORAL_HEADER = "=== Временной диапазон ==="
INFO_TEMPORAL_FORMAT = (
    "Формат ввода:\n  Годы: 2015-2025 или 2015,2017,2020\n  Месяцы: 1-12 или 5,6,7,8,9"
)
INFO_PRODUCTS_HEADER = "=== Выбор продуктов MODIS ==="
INFO_AVAILABLE_PRODUCTS = "Доступные продукты:"
INFO_PRODUCT_OPTION = "  {}. {} ({})"
INFO_INPUT_MONTHS = "Введите месяцы [1-12]: "
INFO_INPUT_PRODUCTS = "Введите номера через запятую [1,2]: "
INFO_INPUT_ZONES = "Введите путь к zones.gpkg: "
INFO_ERROR_INPUT = "[ERROR] Ошибка ввода: {}. Попробуйте снова."
INFO_SKIPPED_DIRS = "Пропущено пустых директорий: {} (проверено: {})"
INFO_CTRL_C = "Нажмите Ctrl+C для принудительного прерывания"
INFO_INPUT_YEAR = "Введите диапазон годов [{}-{}]: "
ERR_SEARCH_FAILED = "Ошибка поиска гранул: {}"

# === ШАГИ ЗОНАЛЬНОЙ СТАТИСТИКИ ===
STATS_STEP_ZONES = "[1/4] Загрузка зон из GeoPackage..."
STATS_STEP_SCANNING = "[2/4] Поиск растров..."
STATS_STEP_PROCESSING = "[3/4] Обработка растров..."
STATS_STEP_SAVING = "[4/4] Сохранение результатов..."
ERR_RASTER_PROCESS = "Ошибка обработки растра {}: {}"
ERR_UNKNOWN_PRODUCTS = "Неизвестные продукты: {}. Доступные: {}"

# === СЛЕДУЮЩИЕ ШАГИ ===
NEXT_STEPS = "СЛЕДУЮЩИЕ ШАГИ:"
NEXT_STEP_1 = "1. Проверьте отчёт: {}"
NEXT_STEP_2 = "2. Запустите modis_pipeline.py 01_download"
NEXT_STEP_3 = "3. Запустите modis_pipeline.py 03_convert"

# === ВАЛИДАЦИЯ ===
VALIDATION_TOO_SMALL = "{} файлов были недокачаны (слишком малый размер)"
VALIDATION_READ_ERROR = "{} файлов имеют ошибки чтения (повреждена структура HDF)"
VALIDATION_STATS_CHECKED = "Проверено файлов: {}"
VALIDATION_STATS_VALID = "Валидных: {}"
VALIDATION_STATS_CORRUPTED = "Повреждённых: {}"
VALIDATION_STATS_DELETED = "Удалено: {}"
VALIDATION_STATS_TOO_SMALL = "└─ Слишком малые: {}"
VALIDATION_STATS_READ_ERROR = "└─ Ошибки чтения: {}"
VALIDATION_STATS_MISSING_DATASETS = "└─ Нет датасетов: {}"
VALIDATION_GDAL_OPEN_FAIL = "GDAL не может открыть файл"
VALIDATION_FORMAT_NOT_RECOGNIZED = "Формат файла не распознан (повреждён)"
VALIDATION_ERROR_PREFIX = "Ошибка: {}"

# === EXCEL-ЭКСПОРТ ===
INFO_CREATING_EXCEL = "Создание Excel-файла: {}"
INFO_EXCEL_SHEETS = "Листы: {}"
INFO_EXCEL_SAVED = "Excel сохранён: {}"
ERR_EXCEL_NO_OPENPYXL = "Для экспорта Excel установите openpyxl"

# === ГИС-ОПЦИИ КОНВЕРТЕРА ===
INFO_RASTER_MODE = "Формат растра: {}"

# === ПРОВЕНАНС ===
INFO_PROVENANCE_SAVED = "Провенанс запуска сохранён: {}"
WARN_PROVENANCE_FAILED = "Не удалось сохранить провенанс: {}"

# === SELFTEST ===
INFO_SELFTEST_START = "Запуск самодиагностики..."
INFO_SELFTEST_DONE = "Самодиагностика завершена."
SELFTEST_OK = "[OK] {}"
SELFTEST_WARN = "[WARN] {}"
SELFTEST_FAIL = "[FAIL] {}"
