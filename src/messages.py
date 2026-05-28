# -*- coding: utf-8 -*-
"""Тексты сообщений для логирования и вывода. Только русский язык."""

# Инициализация и конфигурация
MSG_CONFIG_LOADED = "Конфигурация загружена"
MSG_CONFIG_VALIDATED = "Конфигурация прошла валидацию"
ERR_CONFIG_INVALID = "Ошибка валидации конфигурации: {reason}"
ERR_DIR_NOT_FOUND = "Директория не найдена: {path}"
ERR_FILE_NOT_FOUND = "Файл не найден: {path}"

# Загрузка данных
MSG_DOWNLOAD_START = "Начало загрузки {product} за {year}"
MSG_DOWNLOAD_FOUND = "Найдено гранул: {count}"
MSG_DOWNLOAD_SKIPPED = "Пропущено (уже скачано): {count}"
MSG_DOWNLOAD_COMPLETE = "Загрузка завершена: скачано {downloaded}, ошибок {failed}"
ERR_DOWNLOAD_FAILED = "Ошибка загрузки {filename}: {error}"

# Конвертация
MSG_CONVERT_START = "Конвертация {product}/{year}: {total_files} файлов"
MSG_CONVERTED = "Конвертирован файл {filename} [{product}/{year}]"
MSG_CONVERT_SKIP = "Пропущен (уже существует): {filename}"
ERR_CONVERT_FAILED = "Ошибка конвертации {filename}: {error}"

# Зональная статистика
MSG_ZONAL_START = "Расчёт зональной статистики: {zones_count} зон"
MSG_ZONAL_PROCESSED = "Обработан растр {filename}: {valid_pixels} валидных пикселей"
MSG_ZONAL_NO_INTERSECTION = "Нет пересечения: зона {zone} и растр {raster}"
ERR_ZONAL_FAILED = "Ошибка расчёта статистики для {filename}: {error}"

# Экспорт и сохранение
MSG_SAVED = "Сохранено: {path}"
MSG_EXPORT_COMPLETE = "Экспорт завершён: {count} записей"
ERR_SAVE_FAILED = "Ошибка сохранения {path}: {error}"

# Общие ошибки
ERR_UNKNOWN_PRODUCT = "Неизвестный продукт: {product}"
ERR_INVALID_COORDS = "Некорректные координаты: {reason}"
ERR_INVALID_DATE_RANGE = "Некорректный временной диапазон: {reason}"

# Пайплайн и CLI
MSG_DRY_RUN_START = "Запуск режима проверки (dry-run)"
MSG_DRY_RUN_COMPLETE = "Проверка завершена. Конфигурация и пути валидны."
MSG_STAGE_START = "Запуск этапа {stage}"
MSG_STAGE_END = "Этап {stage} завершён"
MSG_STAGE_SKIPPED = "Этап {stage} пропущен (не реализован или не требуется)"
WARN_MISSING_DEPS = (
    "Предупреждение: отсутствуют входные данные для этапа {stage} в {path}"
)
ERR_UNKNOWN_STAGE = "Неизвестный этап: {stage}"
ERR_STAGE_FAILED = "Ошибка выполнения этапа {stage}: {error}"
ERR_DIR_PERMISSION = "Нет прав на запись в директорию: {path}"
WARN_LOW_DISK_SPACE = "Мало места на диске: свободно {free_mb} МБ"
ERR_PIPELINE_FAILED = "Пайплайн прерван: {error}"
MSG_DRY_RUN_CREATE_DIR = "Будет создана директория: {path}"
MSG_BBOX_COMPUTED = "Вычислена общая граница зон: {bbox}"
MSG_ZONES_LOADED = "Загружено {count} зон из {path}"
MSG_CONVERT_SKIP = "Пропущен валидный файл: {filename}"
