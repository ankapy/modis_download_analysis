"""Зональная статистика: Pure GDAL + NumPy.

Оптимизации: кэширование масок зон, многопоточность,
безопасная и быстрая запись в CSV.
"""

import csv
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from osgeo import gdal, ogr, osr

from config import (
    CSV_DECIMAL,
    CSV_SEPARATOR,
    DATA_PATHS,
    DATE_FORMAT_ISO,
    MODIS_PRODUCTS,
)

from utils import messages
from utils.geo_utils import load_zones
from utils.logger import setup_logger
from utils.provenance import save_run_provenance

gdal.UseExceptions()
ogr.UseExceptions()
gdal.SetConfigOption('GDAL_CACHEMAX', '1024')
gdal.SetConfigOption('GDAL_NUM_THREADS', 'ALL_CPUS')

logger = setup_logger(__name__)

MASK_CACHE = {}
MASK_CACHE_LOCK = threading.Lock()
CSV_WRITE_LOCK = threading.Lock()

# Явно задаем ожидаемые колонки для корректной записи в CSV
EXPECTED_COLUMNS = [
    'zone_id',
    'zone_name',
    'year',
    'month',
    'product',
    'date',
    'date_formatted',
    'lat_center',
    'lon_center',
    'pixel_count',
    'mean',
    'std',
    'median',
    'min',
    'max',
]


def get_zone_mask(raster_path: str, zones: list):
    """Получение маски зон для растра с потокобезопасным кэшированием."""
    ds = gdal.Open(raster_path)
    if ds is None:
        return None, None, None, None

    cols, rows = ds.RasterXSize, ds.RasterYSize
    geotransform = ds.GetGeoTransform()
    projection = ds.GetProjection()
    ds = None

    cache_key = f'{cols}_{rows}_{geotransform[0]:.4f}_{geotransform[3]:.4f}'

    with MASK_CACHE_LOCK:
        if cache_key in MASK_CACHE:
            return MASK_CACHE[cache_key], cols, rows, geotransform

        logger.info(messages.LOG_RASTERIZE_START)

        mem_driver = ogr.GetDriverByName('MEM') or ogr.GetDriverByName(
            'Memory'
        )
        v_ds = mem_driver.CreateDataSource('mem')
        srs = osr.SpatialReference()
        srs.ImportFromWkt(projection)
        srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        v_layer = v_ds.CreateLayer(
            'zones',
            srs=srs,
            geom_type=ogr.wkbPolygon,
        )

        field_def = ogr.FieldDefn('zone_id', ogr.OFTInteger)
        v_layer.CreateField(field_def)

        wgs84_srs = osr.SpatialReference()
        wgs84_srs.ImportFromEPSG(4326)
        wgs84_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        transform = osr.CoordinateTransformation(wgs84_srs, srs)

        for zone in zones:
            geom = ogr.CreateGeometryFromWkt(zone['wkt'])
            try:
                geom.Transform(transform)
            except RuntimeError as e:
                logger.warning(
                    messages.ERR_GEOM_TRANSFORM.format(
                        zone['name'],
                        str(e)[:80],
                    ),
                )
                continue

            feat = ogr.Feature(v_layer.GetLayerDefn())
            feat.SetField('zone_id', zone['id'])
            feat.SetGeometry(geom)
            v_layer.CreateFeature(feat)
            feat = None

        mask_ds = gdal.GetDriverByName('MEM').Create(
            'mask',
            cols,
            rows,
            1,
            gdal.GDT_Int32,
        )
        mask_ds.SetGeoTransform(geotransform)
        mask_ds.SetProjection(projection)

        gdal.RasterizeLayer(
            mask_ds,
            [1],
            v_layer,
            burn_values=[0],
            options=['ATTRIBUTE=zone_id', 'ALL_TOUCHED=TRUE'],
        )

        mask_data = mask_ds.ReadAsArray()
        v_ds = None
        mask_ds = None

        logger.info(messages.LOG_RASTERIZE_OK)
        MASK_CACHE[cache_key] = mask_data

    return mask_data, cols, rows, geotransform


def extract_date(filename: str) -> str:
    """Извлечение YYYY-DOY из имени файла MODIS."""
    try:
        parts = filename.split('.')
        if len(parts) >= 2 and parts[1].startswith('A'):
            return f'{parts[1][1:5]}-{parts[1][5:8]}'
    except ValueError:
        pass
    return 'unknown'


def parse_doy(date_str: str) -> tuple:
    """Конвертация YYYY-DOY в YYYY-MM-DD и номер месяца.

    Возвращает кортеж (date_formatted, month).
    """
    if date_str == 'unknown':
        return '', 0
    try:
        year, doy = map(int, date_str.split('-'))
        dt = datetime(year, 1, 1) + timedelta(days=doy - 1)
        return dt.strftime(DATE_FORMAT_ISO), dt.month
    except (ValueError, OverflowError):
        return '', 0


def build_aggregated_table(flat_csv: Path, agg_csv: Path) -> int:
    """Построение агрегированной сводки из полной плоской таблицы."""
    try:
        df = pd.read_csv(
            flat_csv,
            sep=CSV_SEPARATOR,
            decimal=CSV_DECIMAL,
            encoding='utf-8-sig',
        )
    except (
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
        FileNotFoundError,
    ):
        return 0

    if df.empty:
        return 0

    agg = (
        df.groupby(
            ['zone_id', 'zone_name', 'year', 'month', 'product'],
        )['mean']
        .agg(['mean', 'std', 'min', 'max', 'count'])
        .reset_index()
        .rename(
            columns={
                'mean': 'mean_val',
                'std': 'std_val',
                'min': 'min_val',
                'max': 'max_val',
                'count': 'n_observations',
            },
        )
    )
    agg.to_csv(
        agg_csv,
        index=False,
        encoding='utf-8-sig',
        sep=CSV_SEPARATOR,
        decimal=CSV_DECIMAL,
    )
    return len(agg)


def process_single_raster(raster_path: str, zones: list):
    """Обработка одного растра с использованием кэшированной маски."""
    mask_data, cols, rows, geotransform = get_zone_mask(
        raster_path,
        zones,
    )
    if mask_data is None:
        return []

    ds = gdal.Open(raster_path)
    band = ds.GetRasterBand(1)
    raster_data = band.ReadAsArray().astype(np.float32)

    nodata = band.GetNoDataValue()
    if nodata is None:
        nodata = -9999
    ds = None

    results = []
    unique_ids = np.unique(mask_data[mask_data > 0])
    date_str = extract_date(Path(raster_path).name)
    date_formatted, month = parse_doy(date_str)

    path_obj = Path(raster_path)
    product = path_obj.parent.parent.name
    year = int(path_obj.parent.name)

    for uid in unique_ids:
        zone = next((z for z in zones if z['id'] == uid), None)
        if not zone:
            continue

        zone_mask = mask_data == uid
        values = raster_data[zone_mask]
        valid_values = values[(values != nodata) & (~np.isnan(values))]

        if len(valid_values) > 0:
            results.append(
                {
                    'zone_id': zone['id'],
                    'zone_name': zone['name'],
                    'year': year,
                    'month': month,
                    'product': product,
                    'date': date_str,
                    'date_formatted': date_formatted,
                    'lat_center': zone['lat_center'],
                    'lon_center': zone['lon_center'],
                    'pixel_count': int(len(valid_values)),
                    'mean': float(valid_values.mean()),
                    'std': float(valid_values.std()),
                    'median': float(np.median(valid_values)),
                    'min': float(valid_values.min()),
                    'max': float(valid_values.max()),
                },
            )

    return results


# ─── Вспомогательные функции, вынесенные из main ──────────────


def _load_zones_safe(zones_path: Path) -> list:
    """Загрузка зон с логированием; возвращает [] при ошибке."""
    try:
        zones = load_zones(zones_path)
        if not zones:
            logger.error(messages.ERR_NO_ZONES)
            return []
        logger.info(messages.LOG_ZONES_LOADED.format(len(zones)))
        for z in zones:
            logger.info(
                messages.LOG_ZONE_INFO.format(z['id'], z['name']),
            )
        return zones
    except (FileNotFoundError, RuntimeError) as e:
        logger.error(str(e))
        return []


def _collect_tasks(processed_dir: Path, test_mode: bool) -> list:
    """Сбор списка растров для обработки."""
    tasks = []
    available_products = [
        key for key in MODIS_PRODUCTS if (processed_dir / key).exists()
    ]

    for product in available_products:
        product_dir = processed_dir / product
        available_years = sorted(
            int(d.name)
            for d in product_dir.iterdir()
            if d.is_dir() and d.name.isdigit()
        )

        for year in available_years:
            tifs = sorted(
                (product_dir / str(year)).glob('*.tif'),
            )
            if test_mode and tifs:
                tasks.append(str(tifs[0]))
                logger.info(
                    messages.INFO_TEST_FILE.format(tifs[0].name),
                )
                break
            if not test_mode:
                tasks.extend(str(tif) for tif in tifs)

    return tasks


def _load_processed_keys(csv_path: Path) -> set:
    """Загрузка уже посчитанных ключей для resume."""
    processed_keys = set()
    if not csv_path.exists():
        return processed_keys

    logger.info(messages.INFO_EXISTING_FILE_FOUND.format(csv_path))
    logger.info(messages.INFO_LOADING_INDICES)
    try:
        existing_df = pd.read_csv(
            csv_path,
            usecols=['zone_name', 'date', 'product'],
            sep=';',
        )
        for _, row in existing_df.iterrows():
            processed_keys.add(
                f'{row["zone_name"]}_{row["date"]}_{row["product"]}',
            )
        logger.info(
            messages.INFO_SKIPPED_RECORDS.format(len(processed_keys)),
        )
    except (
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
        FileNotFoundError,
    ) as e:
        logger.warning(
            messages.WARN_READ_FILE_FAILED.format(str(e)),
        )
    return processed_keys


def _format_row(row: dict) -> dict:
    """Форматирование float-значений для CSV (русская локаль)."""
    return {
        k: (f'{v:.6f}'.replace('.', ',') if isinstance(v, float) else v)
        for k, v in row.items()
    }


def _ensure_csv_header(csv_path: Path, file_exists: list) -> None:
    """Запись заголовка CSV, если файл ещё не создан."""
    if not file_exists[0]:
        with open(
            csv_path,
            'a',
            newline='',
            encoding='utf-8-sig',
        ) as f:
            writer = csv.DictWriter(
                f,
                fieldnames=EXPECTED_COLUMNS,
                delimiter=';',
            )
            writer.writeheader()
        file_exists[0] = True


def _append_csv_row(csv_path: Path, row: dict) -> None:
    """Дозапись одной строки в CSV."""
    with open(
        csv_path,
        'a',
        newline='',
        encoding='utf-8-sig',
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=EXPECTED_COLUMNS,
            delimiter=';',
        )
        writer.writerow(_format_row(row))


def _process_results(
    results: list,
    processed_keys: set,
    csv_path: Path,
    file_exists: list,
    all_results: list,
):
    """Фильтрация дублей, запись в CSV и накопление результатов."""
    for row in results:
        unique_key = f'{row["zone_name"]}_{row["date"]}_{row["product"]}'
        if unique_key in processed_keys:
            continue
        with CSV_WRITE_LOCK:
            _ensure_csv_header(csv_path, file_exists)
            _append_csv_row(csv_path, row)
        all_results.append(row)
        processed_keys.add(unique_key)


def _run_parallel(
    tasks,
    zones,
    workers,
    test_mode,
    processed_keys,
    csv_path,
    file_exists,
    all_results,
):
    """Обработка растров в несколько потоков."""
    logger.info(messages.STATUS_MULTITHREAD.format(workers))

    def worker_task(raster_path):
        """Обработка одного растра с защитой от исключений."""
        try:
            return process_single_raster(raster_path, zones)
        except (RuntimeError, ValueError) as e:
            logger.warning(
                messages.ERR_RASTER_PROCESS.format(
                    raster_path,
                    str(e),
                ),
            )
            return []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(worker_task, path): path for path in tasks}
        for i, future in enumerate(as_completed(futures), 1):
            _process_results(
                future.result(),
                processed_keys,
                csv_path,
                file_exists,
                all_results,
            )
            if not test_mode and i % 20 == 0:
                logger.info(
                    messages.INFO_PROCESSED_RASTERS.format(
                        i,
                        len(tasks),
                    ),
                )


def _run_sequential(
    tasks,
    zones,
    test_mode,
    processed_keys,
    csv_path,
    file_exists,
    all_results,
):
    """Обработка растров в один поток."""

    def worker_task(raster_path):
        """Обработка одного растра с защитой от исключений."""
        try:
            return process_single_raster(raster_path, zones)
        except (RuntimeError, ValueError) as e:
            logger.warning(
                messages.ERR_RASTER_PROCESS.format(
                    raster_path,
                    str(e),
                ),
            )
            return []

    for i, raster_path in enumerate(tasks, 1):
        _process_results(
            worker_task(raster_path),
            processed_keys,
            csv_path,
            file_exists,
            all_results,
        )
        if not test_mode and i % 20 == 0:
            logger.info(
                messages.INFO_PROCESSED_RASTERS.format(
                    i,
                    len(tasks),
                ),
            )


# ─── Главная функция ──────────────────────────────────────────


def main(args):
    """Главная функция зональной статистики."""
    logger.info(messages.SEPARATOR)
    logger.info(messages.HEADER_ZONAL_STATS)
    logger.info(messages.SEPARATOR)

    start_time = time.time()

    save_run_provenance(
        '04_stats',
        {
            'zones': args.zones,
            'workers': args.workers,
            'test': args.test,
        },
    )

    # [1/4] Загрузка зон
    logger.info(messages.STATS_STEP_ZONES)
    zones = _load_zones_safe(args.zones)
    if not zones:
        return

    # [2/4] Поиск растров
    logger.info(messages.STATS_STEP_SCANNING)
    tasks = _collect_tasks(DATA_PATHS['processed'], args.test)
    logger.info(messages.INFO_RASTERS_FOUND.format(len(tasks)))
    if not tasks:
        logger.error(messages.ERR_NO_RASTERS)
        return

    # Resume: загрузка уже посчитанных ключей
    output_csv = DATA_PATHS['tables'] / 'zonal_stats_flat.csv'
    processed_keys = _load_processed_keys(output_csv)

    # [3/4] Обработка растров
    logger.info(messages.STATS_STEP_PROCESSING)
    all_results = []
    file_exists = [output_csv.exists()]

    if args.workers > 1:
        _run_parallel(
            tasks,
            zones,
            args.workers,
            args.test,
            processed_keys,
            output_csv,
            file_exists,
            all_results,
        )
    else:
        _run_sequential(
            tasks,
            zones,
            args.test,
            processed_keys,
            output_csv,
            file_exists,
            all_results,
        )

    # [4/4] Сохранение результатов
    logger.info(messages.STATS_STEP_SAVING)
    if all_results:
        logger.info(
            messages.LOG_SAVED_OK.format(
                len(all_results),
                output_csv,
            ),
        )

    agg_path = output_csv.parent / f'{output_csv.stem}_agg.csv'
    if build_aggregated_table(output_csv, agg_path) > 0:
        logger.info(messages.LOG_SAVED_AGG.format(agg_path))
    else:
        logger.warning(messages.LOG_NO_DATA)

    logger.info(
        messages.LOG_FINISHED.format(time.time() - start_time),
    )
