"""Зональная статистика: Pure GDAL + NumPy.

Оптимизации: кэширование масок зон, многопоточность,
потокобезопасная дозапись в CSV, агрегирование из полной таблицы.
"""

import csv
import threading
import time
from bisect import bisect_left
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
    MONTH_CUMDAYS,
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

PROGRESS_LOG_STEP = 20
DEFAULT_NODATA = -9999
BACKGROUND_VALUE = -1

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
        v_layer = v_ds.CreateLayer('zones', srs=srs, geom_type=ogr.wkbPolygon)
        v_layer.CreateField(ogr.FieldDefn('zone_id', ogr.OFTInteger))

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
                        zone['name'], str(e)[:80]
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
        mask_ds.GetRasterBand(1).Fill(BACKGROUND_VALUE)

        gdal.RasterizeLayer(
            mask_ds,
            [1],
            v_layer,
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


def composite_period_days(product_key: str) -> int:
    """Длина периода композита в днях по конфигу продукта."""
    config = MODIS_PRODUCTS.get(product_key, {})
    resolution = config.get('temporal_resolution', 'daily')
    if resolution in ('daily', 'yearly'):
        return 1
    return int(resolution.split('-')[0])


def nominal_month(doy: int) -> int:
    """Месяц по дню года в невисокосном календаре MODIS."""
    return bisect_left(MONTH_CUMDAYS, doy) + 1


def parse_doy(date_str: str) -> tuple:
    """Конвертация YYYY-DOY в фактическую дату и номинальный месяц.

    date_formatted — реальная дата старта периода;
    month — номинальный месяц периода (невисокосный календарь MODIS),
    чтобы месяцы загрузки и месяцы анализа всегда совпадали.
    """
    if date_str == 'unknown':
        return '', 0
    try:
        year, doy = map(int, date_str.split('-'))
        dt = datetime(year, 1, 1) + timedelta(days=doy - 1)
        return dt.strftime(DATE_FORMAT_ISO), nominal_month(doy)
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
        df.groupby(['zone_id', 'zone_name', 'year', 'month', 'product'])[
            'mean'
        ]
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
    mask_data, _, _, _ = get_zone_mask(raster_path, zones)
    if mask_data is None:
        return []

    ds = gdal.Open(raster_path)
    band = ds.GetRasterBand(1)
    raster_data = band.ReadAsArray().astype(np.float32)
    nodata = band.GetNoDataValue()
    if nodata is None:
        nodata = DEFAULT_NODATA
    ds = None

    path_obj = Path(raster_path)
    product = path_obj.parent.parent.name
    year = int(path_obj.parent.name)
    date_str = extract_date(path_obj.name)
    date_formatted, month = parse_doy(date_str)

    zones_by_id = {z['id']: z for z in zones}
    results = []
    for uid in np.unique(mask_data[mask_data >= 0]):
        zone = zones_by_id.get(int(uid))
        if zone is None:
            continue

        values = raster_data[mask_data == uid]
        valid = values[(values != nodata) & (~np.isnan(values))]
        if valid.size == 0:
            continue

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
                'pixel_count': int(valid.size),
                'mean': float(valid.mean()),
                'std': float(valid.std()),
                'median': float(np.median(valid)),
                'min': float(valid.min()),
                'max': float(valid.max()),
            },
        )

    return results


def _process_raster_safe(raster_path: str, zones: list) -> list:
    """Обработка одного растра с защитой от исключений."""
    try:
        return process_single_raster(raster_path, zones)
    except (RuntimeError, ValueError) as e:
        logger.warning(messages.ERR_RASTER_PROCESS.format(raster_path, str(e)))
        return []


def _iter_results(tasks: list, zones: list, workers: int):
    """Генерация результатов обработки: параллельно или последовательно."""
    if workers > 1:
        logger.info(messages.STATUS_MULTITHREAD.format(workers))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(_process_raster_safe, path, zones)
                for path in tasks
            ]
            for future in as_completed(futures):
                yield future.result()
    else:
        for path in tasks:
            yield _process_raster_safe(path, zones)


def _format_row(row: dict) -> dict:
    """Форматирование float-значений для CSV по локали из конфига."""
    return {
        key: (
            f'{value:.6f}'.replace('.', CSV_DECIMAL)
            if isinstance(value, float)
            else value
        )
        for key, value in row.items()
    }


class CsvAppender:
    """Потокобезопасная дозапись строк статистики в CSV."""

    def __init__(self, path: Path):
        """Запоминание пути и состояния заголовка."""
        self.path = path
        self._lock = threading.Lock()
        self._header_written = path.exists() and path.stat().st_size > 0

    def append(self, rows: list) -> None:
        """Запись пачки строк под блокировкой."""
        with self._lock:
            with open(self.path, 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=EXPECTED_COLUMNS,
                    delimiter=CSV_SEPARATOR,
                )
                if not self._header_written:
                    writer.writeheader()
                    self._header_written = True
                writer.writerows(_format_row(row) for row in rows)


def _load_zones_safe(zones_path: Path) -> list:
    """Загрузка зон с логированием; возвращает [] при ошибке."""
    try:
        zones = load_zones(zones_path)
        if not zones:
            logger.error(messages.ERR_NO_ZONES)
            return []
        logger.info(messages.LOG_ZONES_LOADED.format(len(zones)))
        for z in zones:
            logger.info(messages.LOG_ZONE_INFO.format(z['id'], z['name']))
        return zones
    except (FileNotFoundError, RuntimeError) as e:
        logger.error(str(e))
        return []


def _collect_tasks(processed_dir: Path, test_mode: bool) -> list:
    """Сбор списка растров для обработки."""
    tasks = []
    for product in MODIS_PRODUCTS:
        product_dir = processed_dir / product
        if not product_dir.exists():
            continue

        years = sorted(
            int(d.name)
            for d in product_dir.iterdir()
            if d.is_dir() and d.name.isdigit()
        )
        for year in years:
            tifs = sorted((product_dir / str(year)).glob('*.tif'))
            if not tifs:
                continue
            if test_mode:
                tasks.append(str(tifs[0]))
                logger.info(messages.INFO_TEST_FILE.format(tifs[0].name))
                break
            tasks.extend(str(tif) for tif in tifs)

    return tasks


def _load_processed_keys(csv_path: Path) -> set:
    """Загрузка уже посчитанных ключей для resume."""
    if not csv_path.exists():
        return set()

    logger.info(messages.INFO_EXISTING_FILE_FOUND.format(csv_path))
    logger.info(messages.INFO_LOADING_INDICES)
    try:
        existing = pd.read_csv(
            csv_path,
            usecols=['zone_name', 'date', 'product'],
            sep=CSV_SEPARATOR,
        )
    except (
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
        FileNotFoundError,
    ) as e:
        logger.warning(messages.WARN_READ_FILE_FAILED.format(str(e)))
        return set()

    keys = {
        f'{zone}_{date}_{product}'
        for zone, date, product in zip(
            existing['zone_name'],
            existing['date'],
            existing['product'],
        )
    }
    logger.info(messages.INFO_SKIPPED_RECORDS.format(len(keys)))
    return keys


def _process_results(
    results: list,
    processed_keys: set,
    appender: CsvAppender,
    all_results: list,
) -> None:
    """Фильтрация дублей, дозапись в CSV и накопление результатов."""
    new_rows = []
    for row in results:
        key = f'{row["zone_name"]}_{row["date"]}_{row["product"]}'
        if key in processed_keys:
            continue
        processed_keys.add(key)
        new_rows.append(row)

    if new_rows:
        appender.append(new_rows)
        all_results.extend(new_rows)


def main(args):
    """Главная функция зональной статистики."""
    logger.info(messages.SEPARATOR)
    logger.info(messages.HEADER_ZONAL_STATS)
    logger.info(messages.SEPARATOR)
    start_time = time.time()

    save_run_provenance(
        '04_stats',
        {'zones': args.zones, 'workers': args.workers, 'test': args.test},
    )

    logger.info(messages.STATS_STEP_ZONES)
    zones = _load_zones_safe(args.zones)
    if not zones:
        return

    logger.info(messages.STATS_STEP_SCANNING)
    tasks = _collect_tasks(DATA_PATHS['processed'], args.test)
    logger.info(messages.INFO_RASTERS_FOUND.format(len(tasks)))
    if not tasks:
        logger.error(messages.ERR_NO_RASTERS)
        return

    output_csv = DATA_PATHS['tables'] / 'zonal_stats_flat.csv'
    processed_keys = _load_processed_keys(output_csv)

    logger.info(messages.STATS_STEP_PROCESSING)
    all_results = []
    appender = CsvAppender(output_csv)
    for i, results in enumerate(_iter_results(tasks, zones, args.workers), 1):
        _process_results(results, processed_keys, appender, all_results)
        if not args.test and i % PROGRESS_LOG_STEP == 0:
            logger.info(messages.INFO_PROCESSED_RASTERS.format(i, len(tasks)))

    logger.info(messages.STATS_STEP_SAVING)
    if all_results:
        logger.info(messages.LOG_SAVED_OK.format(len(all_results), output_csv))

    agg_path = output_csv.parent / f'{output_csv.stem}_agg.csv'
    if build_aggregated_table(output_csv, agg_path) > 0:
        logger.info(messages.LOG_SAVED_AGG.format(agg_path))
    else:
        logger.warning(messages.LOG_NO_DATA)

    logger.info(messages.LOG_FINISHED.format(time.time() - start_time))
