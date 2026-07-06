# MODIS Download & Analysis

Проект представляет собой автоматизированный пайплайн загрузки и обработки спутниковых данных MODIS (по умолчанию продукты MOD11A2 и MOD13Q1). Система реализует цикл работы с растровыми данными: автоматическую загрузку HDF-гранул через NASA Earthdata API, валидацию целостности файлов средствами GDAL, расчёт зональной статистики (mean, std, median, min, max, pixel_count), предварительная визуализация статистических данных в виде растровых графиков в формате png. Архитектура построена на модульном принципе с централизованной конфигурацией, каждый этап запускается пользователем и выполняется отдельным модулем с поддержкой CLI-флагов.

---

## Содержание

- [MODIS Download \& Analysis](#modis-download--analysis)
  - [Содержание](#содержание)
  - [Возможности](#возможности)
  - [Установка](#установка)
  - [Структура проекта](#структура-проекта)
  - [Конфигурация](#конфигурация)
  - [Пайплайн](#пайплайн)
    - [Шаг 1. Скачивание данных](#шаг-1-скачивание-данных)
    - [Шаг 2. Валидация и очистка](#шаг-2-валидация-и-очистка)
      - [Примеры](#примеры)
    - [Шаг 3. Конвертация HDF → GeoTIFF](#шаг-3-конвертация-hdf--geotiff)
    - [Шаг 4. Зональная статистика](#шаг-4-зональная-статистика)
      - [Примеры](#примеры-1)
      - [Особенности реализации](#особенности-реализации)
    - [Шаг 5. Анализ и визуализация](#шаг-5-анализ-и-визуализация)
  - [Дополнительный функционал](#дополнительный-функционал)
    - [`seasonal_dynamics.xlsx`](#seasonal_dynamicsxlsx)
    - [`interannual_dynamics.xlsx`](#interannual_dynamicsxlsx)
    - [`summary_tables.xlsx`](#summary_tablesxlsx)
  - [Описание выходных файлов](#описание-выходных-файлов)
    - [`zonal_stats_flat.csv` (сырая таблица)](#zonal_stats_flatcsv-сырая-таблица)
    - [`zonal_stats_monthly.csv`](#zonal_stats_monthlycsv)
  - [Troubleshooting](#troubleshooting)
    - [Ошибка `GDAL not found`](#ошибка-gdal-not-found)
  - [Контакты](#контакты)

---

## Возможности

- Автоматическая загрузка данных MODIS через `earthaccess` с защитой от обрывов соединения
- Валидация HDF-файлов через GDAL с возможностью удаления битых гранул
- Расчёт зональной статистики по входному полигональному слою
- Многопоточное статистическое извлечение данных с кэшированием масок зон
- Выгрузка сырых данных для статистического анализа
- Визуализация статистических данных в виде растровых графиков
- Экспорт сводных таблиц в Excel (`.xlsx`) и CSV


---

## Установка

1. **Запустите официальный Python Command Prompt ArcGIS Pro**
   ```
   "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\proenv.bat"
   ```

2. **Перейдите в проект и клонируйте изолированное окружение.**
   Мы используем флаг `--prefix` (или `-p`), чтобы указать путь прямо в папку проекта. Скрипт склонирует вашу          системную среду ArcGIS Pro (`arcgispro-py3`), но сохранит её локально.
   ```
   cd <адрес хранения проекта>\modis_download_analysis
   conda create --prefix ./venv --clone arcgispro-py3 -y
   ```

3. **Активируйте виртуальное окружение и обновите pip**
   ```
   conda activate ./venv
   python -m pip install --upgrade pip
   ```

4. **Установите Python-зависимости:**
   ```bash
   pip install -r requirements.txt
   ```

5. Для авторизации на портале urs.earthdata.nasa.gov. По адресу `C:\Users\<имя пользователя ПК>` создать файл с названием строго `.netrc` **без расширения файла**. В содержании файла через текстовый редактор указать
   ```
   machine urs.earthdata.nasa.gov
   login <ваш логин учетной записи для авторизации>
   password <ваш пароль учетной записи>
   ```

---

## Структура проекта

```
modis_download_analysis/
│
├── config.py                     # Конфигурация
├── scripts/
│   ├── 01_download_modis_earthaccess.py   # Скачивание MODIS
│   ├── 02_1_validate_and_cleanup.py       # Валидация HDF-файлов
│   ├── 02_convert_hdf.py                  # Конвертация HDF → GeoTIFF
│   ├── 03_zonal_stats.py                  # Зональная статистика
│   ├── 04_analysis.py                     # Анализ и визуализация
│   ├── export.py                          # Экспорт для Origin Pro
│   ├── ex_extract_raster_footprint.py     # Извлечение footprint (ArcPy)
├── data/
│   ├── raw/                        # Исходные HDF-файлы
│   │   ├── MOD11A2/
│   │   │   ├── 2015/
│   │   │   └── ...
│   │   └── MOD13Q1/
│   ├── processed/                  # Конвертированные GeoTIFF
│   │   ├── LST/
│   │   │   ├── 2015/
│   │   │   └── ...
│   │   └── NDVI/
│   └── tables/                     # CSV-таблицы со статистикой
│       ├── zonal_stats_flat.csv
│       ├── zonal_stats_monthly.csv
│       └── validation_report_*.json
├── gis/
│   ├── zones.gpkg                  # Полигоны зон
└── output/
    ├── figures/analysis/           # Графики PNG
    └── tables/                     # Таблицы
```

---

## Конфигурация

Все параметры вынесены в `config.py`:

```python
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

DATA_PATHS = {
    "raw": ".../data/raw",
    "processed": ".../data/processed",
    "tables": ".../data/tables",
    "gis": ".../gis",
    "figures": ".../output/figures",
    "tables_output": ".../output/tables",
}
```

---

## Пайплайн

### Шаг 1. Скачивание данных

```bash
python scripts/01_download_modis_earthaccess.py
```

Скрипт скачивает HDF-файлы MODIS через `earthaccess`. Поддерживает:
- Автоматическую авторизацию через `.netrc` или переменные окружения
- Пакетную загрузку по 15 гранул с паузами (защита от дисконектов)
- Повторные попытки при ошибках (до 3 раз)
- Пропуск уже скачанных файлов

---

### Шаг 2. Валидация и очистка

```bash
python scripts/02_1_validate_and_cleanup.py
```

| Флаг | Описание |
|------|----------|
| `--dry-run` | Режим проверки — не удалять файлы, только показать |
| `--quiet` | Тихий режим — показывать только ошибки |
| `--product {LST,NDVI,all}` | Продукт для проверки (по умолчанию: `all`) |
| `--year YEAR` | Проверить только указанный год |
| `--no-delete` | Не удалять файлы, только создать отчёт |
| `--workers N` | Количество потоков для удаления (по умолчанию: 8) |
| `--skip-progress` | Отключить прогресс-бары |

#### Примеры

```bash
# Проверка всех файлов без удаления
python scripts/02_1_validate_and_cleanup.py --dry-run

# Проверка и удаление битых файлов только для LST за 2023 год
python scripts/02_1_validate_and_cleanup.py --product LST --year 2023

# Тихая проверка с удалением
python scripts/02_1_validate_and_cleanup.py --quiet
```

---

### Шаг 3. Конвертация HDF → GeoTIFF

```bash
python scripts/02_convert_hdf.py
```

Конвертирует все HDF-файлы из `data/raw/` в GeoTIFF в `data/processed/`:
- **LST (MOD11A2):** `LST_C = DN * 0.02 - 273.15` (°C)
- **NDVI (MOD13Q1):** `NDVI = DN * 0.0001` (безразмерный)
- NoData значения маскируются в `NaN`
- Файлы сохраняются в проекции WGS 84 с LZW-сжатием

---

### Шаг 4. Зональная статистика

```bash
python scripts/03_zonal_stats.py
```
| Флаг | Описание |
|------|----------|
| `--test` | Быстрый тест функциональности: обрабатывает только 1 файл на продукт |
| `--flat` | Экспорт сырой таблицы без агрегации по месяцам |
| `--workers N` | Количество потоков (по умолчанию: 1, рекомендуется 4–8) |

#### Примеры

```bash
# Быстрый тест пайплайна (~30 секунд)
python scripts/03_zonal_stats.py --test

# Полный расчёт в однопоточном режиме
python scripts/03_zonal_stats.py

# Полный расчёт в многопоточном режиме (рекомендуется)
python scripts/03_zonal_stats.py --workers 6

# Сырая таблица (6 потоков)
python scripts/03_zonal_stats.py --flat --workers 6
```

#### Особенности реализации
- **Кэширование маски зон:** полигоны растеризуются один раз для каждого формата растра, далее применяется готовая NumPy-маска
- **Режим Resume:** при прерывании скрипт продолжает с места обрыва, пропуская уже рассчитанные записи
- **Безопасная запись:** данные дописываются в CSV по мере обработки (`append mode`)

---

### Шаг 5. Анализ и визуализация

```bash
python scripts/04_analysis.py
```

Строит следующие графики в `output/figures/analysis/`:

| График | Файл |
|--------|------|
| Сезонная динамика LST/NDVI | `seasonal_lst.png`, `seasonal_ndvi.png` |
| Межгодовые тренды | `trend_lst.png`, `trend_ndvi.png` |
| Широтный градиент (июль) | `gradient_lst_m7.png`, `gradient_ndvi_m7.png` |
| Сезонная амплитуда | `amplitude_lst.png`, `amplitude_ndvi.png` |
| Корреляция LST–NDVI | `correlation_m7.png` |

Также генерирует CSV-таблицы:
- `summary_statistics.csv` — сводная статистика по зонам
- `trend_significance.csv` — значимость трендов (p-value)
- `monthly_aggregated.csv` — помесячные агрегаты

---

## Дополнительный функционал

```bash
python scripts/export.py
```

Создаёт в `output/tables/` три Excel-файла с листами:

### `seasonal_dynamics.xlsx`
- Листы: `LST_mean`, `LST_std`, `NDVI_mean`, `NDVI_std`
- Строки: месяцы (Май–Сен), Колонки: зоны

### `interannual_dynamics.xlsx`
- Листы: `LST_mean`, `LST_std`, `NDVI_mean`, `NDVI_std`
- Строки: годы (2015–2025), Колонки: зоны

### `summary_tables.xlsx`
- Листы: `Summary`, `Trend_Significance`, `Amplitude`


---

## Описание выходных файлов

### `zonal_stats_flat.csv` (сырая таблица)

Каждая строка — одно измерение (дата × зона × продукт). Оптимально для импорта в Origin Pro.

| Колонка | Тип | Описание |
|---------|-----|----------|
| `zone_name` | str | Название природной зоны |
| `year` | int | Год |
| `month` | int | Месяц (2–10) |
| `product` | str | `LST` или `NDVI` |
| `date` | str | Дата в формате `YYYY-DOY` (например, `2023-185`) |
| `lat_center` | float | Центральная широта зоны |
| `lon_center` | float | Центральная долгота зоны |
| `pixel_count` | int | Количество валидных пикселей |
| `mean` | float | Среднее значение |
| `std` | float | Стандартное отклонение |
| `median` | float | Медиана |
| `min` | float | Минимум |
| `max` | float | Максимум |

### `zonal_stats_monthly.csv`

Агрегированная таблица со средними значениями по месяцам (для классического анализа).

---

## Troubleshooting
Подумать нужен ли этот раздел

### Ошибка `GDAL not found`

**Причина:** GDAL не установлен или не активировано окружение.  
**Решение:**
```bash
# Вариант 1: Активировать окружение ArcGIS Pro
"C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\proenv.bat"

# Вариант 2: Установить GDAL через conda
conda install -c conda-forge gdal
```

---

## Контакты

tg @crashkkm
