# MODIS Shirotnaya Zonalnost Pipeline
Автоматизированный комплекс обработки данных MODIS (LST, NDVI) для анализа широтного градиента.

## Архитектура
Проект построен по принципам SOLID, KISS, DRY. Бизнес-логика изолирована от интерфейса.
- `src/core/` — чистые функции расчётов, визуализации, экспорта (SRP)
- `src/utils/` — утилиты работы с растрами, временем, статистикой
- `src/orch/` — оркестратор этапов, управление зависимостями, dry-run
- `src/cli.py` — точка входа, парсинг аргументов
- `scripts/` — тонкие обёртки для запуска этапов нумерацией `01_...`

## Установка
1. Создайте виртуальное окружение: `python -m venv venv`
2. Активируйте: `venv\Scripts\activate` (Windows) или `source venv/bin/activate` (Linux)
3. Установите зависимости: `pip install -r requirements.txt`
   Требуемые пакеты: `earthaccess`, `gdal`, `numpy`, `pandas`, `matplotlib`, `scipy`, `openpyxl`

## Запуск пайплайна
Все этапы запускаются последовательно через `scripts/` или одной командой через `cli`:
```bash
# Проверка конфигурации и путей (без вычислений)
python scripts/01_init.py --dry-run

# Загрузка гранул MODIS (по границам зон из gis/zones.gpkg)
python scripts/02_download.py

# Валидация и очистка битых HDF
python scripts/03_validate.py

# Конвертация HDF → GeoTIFF (атомарная запись, стратегия продуктов)
python scripts/04_convert.py

# Расчёт зональной статистики (проверка пересечений, фильтрация NoData)
python scripts/05_zonal_stats.py

# Визуализация (сезонные кривые, градиенты, тренды)
python scripts/06_analysis.py

# Экспорт для Origin Pro / публикаций
python scripts/07_export.py