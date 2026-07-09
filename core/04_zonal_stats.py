"""
Зональная статистика: Pure GDAL + NumPy.
Оптимизации: кэширование масок, многопоточность, безопасная запись в CSV.
"""

import time
import threading
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from osgeo import gdal, ogr, osr
from config import DATA_PATHS, TEMPORAL_RANGE
from utils.logger import setup_logger
from utils.geo_utils import load_zones
from utils import messages

gdal.UseExceptions()
ogr.UseExceptions()
gdal.SetConfigOption("GDAL_CACHEMAX", "1024")
gdal.SetConfigOption("GDAL_NUM_THREADS", "ALL_CPUS")


logger = setup_logger(__name__)


MASK_CACHE = {}
MASK_CACHE_LOCK = threading.Lock()
CSV_WRITE_LOCK = threading.Lock()


def get_zone_mask(raster_path: str, zones: list):
    """Получение маски зон для растра с кэшированием."""
    ds = gdal.Open(raster_path)
    if ds is None:
        return None, None, None, None

    cols, rows = ds.RasterXSize, ds.RasterYSize
    geotransform = ds.GetGeoTransform()
    projection = ds.GetProjection()
    ds = None

    cache_key = f"{cols}_{rows}_{geotransform[0]:.4f}_{geotransform[3]:.4f}"

    with MASK_CACHE_LOCK:
        if cache_key in MASK_CACHE:
            return MASK_CACHE[cache_key], cols, rows, geotransform

        logger.info(messages.LOG_RASTERIZE_START)

        mem_driver = ogr.GetDriverByName("Memory")
        v_ds = mem_driver.CreateDataSource("mem")
        srs = osr.SpatialReference()
        srs.ImportFromWkt(projection)
        v_layer = v_ds.CreateLayer("zones", srs=srs, geom_type=ogr.wkbPolygon)

        field_def = ogr.FieldDefn("zone_id", ogr.OFTInteger)
        v_layer.CreateField(field_def)

        # Перепроецирование полигонов из WGS84 в проекцию растра
        wgs84_srs = osr.SpatialReference()
        wgs84_srs.ImportFromEPSG(4326)

        # Проверяем возможность трансформации
        if srs.IsProjected() or srs.IsGeographic():
            transform = osr.CoordinateTransformation(wgs84_srs, srs)
            use_transform = True
        else:
            use_transform = False

        for zone in zones:
            feat = ogr.Feature(v_layer.GetLayerDefn())
            feat.SetField("zone_id", zone["id"])

            geom = ogr.CreateGeometryFromWkt(zone["wkt"])

            if use_transform:
                try:
                    geom.Transform(transform)
                except Exception as e:
                    logger.warning(
                        f"Ошибка трансформации геометрии для зоны {zone['name']}: {e}"
                    )

            feat.SetGeometry(geom)
            v_layer.CreateFeature(feat)
            feat = None

        mask_ds = gdal.GetDriverByName("MEM").Create(
            "mask", cols, rows, 1, gdal.GDT_Int32
        )
        mask_ds.SetGeoTransform(geotransform)
        mask_ds.SetProjection(projection)

        gdal.RasterizeLayer(
            mask_ds,
            [1],
            v_layer,
            burn_values=[0],
            options=["ATTRIBUTE=zone_id", "ALL_TOUCHED=TRUE"],
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
        parts = filename.split(".")
        if len(parts) >= 2 and parts[1].startswith("A"):
            return f"{parts[1][1:5]}-{parts[1][5:8]}"
    except Exception:
        pass
    return "unknown"


def doy_to_date(date_str: str) -> str:
    """
    Конвертация даты из формата YYYY-DOY в YYYY-MM-DD.
    Пример: 2015-145 -> 2015-05-25.
    """
    try:
        if date_str == "unknown" or pd.isna(date_str):
            return None
        parts = str(date_str).split("-")
        if len(parts) != 2:
            return None
        year = int(parts[0])
        doy = int(parts[1])
        date_obj = datetime(year, 1, 1) + timedelta(days=doy - 1)
        return date_obj.strftime("%Y-%m-%d")
    except Exception:
        return None


def doy_to_month(date_str: str) -> int:
    """
    Конвертация дня года в номер месяца.
    Пример: 2015-001 -> 1 (январь), 2015-032 -> 2 (февраль).
    """
    if date_str == "unknown":
        return 0
    try:
        parts = str(date_str).split("-")
        if len(parts) != 2:
            return 0
        year = int(parts[0])
        doy = int(parts[1])

        # Используем datetime для точного определения месяца
        date_obj = datetime(year, 1, 1) + timedelta(days=doy - 1)
        return date_obj.month
    except Exception:
        return 0


def process_single_raster(raster_path: str, zones: list):
    """Обработка одного растра с использованием кэшированной маски."""
    mask_data, cols, rows, geotransform = get_zone_mask(raster_path, zones)
    if mask_data is None:
        return []

    ds = gdal.Open(raster_path)
    band = ds.GetRasterBand(1)
    raster_data = band.ReadAsArray().astype(np.float32)
    nodata = band.GetNoDataValue() or -9999
    ds = None

    results = []
    unique_ids = np.unique(mask_data[mask_data > 0])
    date_str = extract_date(Path(raster_path).name)
    month = doy_to_month(date_str)
    date_formatted = doy_to_date(date_str)

    parts = Path(raster_path).parts
    product = parts[-3]
    year = int(parts[-2])

    for uid in unique_ids:
        zone = next((z for z in zones if z["id"] == uid), None)
        if not zone:
            continue

        zone_mask = mask_data == uid
        values = raster_data[zone_mask]
        valid_values = values[(values != nodata) & (~np.isnan(values))]

        if len(valid_values) > 0:
            results.append(
                {
                    "zone_id": zone["id"],
                    "zone_name": zone["name"],
                    "year": year,
                    "month": month,
                    "product": product,
                    "date": date_str,
                    "date_formatted": date_formatted,
                    "lat_center": zone["lat_center"],
                    "lon_center": zone["lon_center"],
                    "pixel_count": int(len(valid_values)),
                    "mean": float(valid_values.mean()),
                    "std": float(valid_values.std()),
                    "median": float(np.median(valid_values)),
                    "min": float(valid_values.min()),
                    "max": float(valid_values.max()),
                }
            )

    return results


def main(args):
    """Главная функция зональной статистики."""
    logger.info(messages.SEPARATOR)
    logger.info(messages.HEADER_ZONAL_STATS)
    logger.info(messages.SEPARATOR)

    start_time = time.time()

    logger.info("[1/4] Loading zones from GeoPackage...")
    try:
        zones = load_zones(args.zones)
        if not zones:
            logger.error(messages.ERR_NO_ZONES)
            return
        logger.info(messages.LOG_ZONES_LOADED.format(len(zones)))
        for z in zones:
            logger.info(messages.LOG_ZONE_INFO.format(z["id"], z["name"]))
    except Exception as e:
        logger.error(f"{e}")
        return

    logger.info("[2/4] Scanning for rasters...")
    products = ["LST", "NDVI"]
    years = list(range(TEMPORAL_RANGE["start_year"], TEMPORAL_RANGE["end_year"] + 1))

    tasks = []
    for product in products:
        for year in years:
            prod_dir = DATA_PATHS["processed"] / product / str(year)
            if prod_dir.exists():
                tifs = sorted(prod_dir.glob("*.tif"))
                if args.test:
                    if tifs:
                        tasks.append(str(tifs[0]))
                        logger.info(messages.INFO_TEST_FILE.format(tifs[0].name))
                else:
                    for tif in tifs:
                        tasks.append(str(tif))

    logger.info(messages.INFO_RASTERS_FOUND.format(len(tasks)))

    if not tasks:
        logger.error(messages.ERR_NO_RASTERS)
        return

    output_csv = DATA_PATHS["tables"] / "zonal_stats_flat.csv"

    processed_keys = set()
    if output_csv.exists():
        logger.info(messages.INFO_EXISTING_FILE_FOUND.format(output_csv))
        logger.info(messages.INFO_LOADING_INDICES)
        try:
            cols_to_read = ["zone_name", "date", "product"]
            existing_df = pd.read_csv(output_csv, usecols=cols_to_read, sep=";")
            for _, row in existing_df.iterrows():
                key = f"{row['zone_name']}_{row['date']}_{row['product']}"
                processed_keys.add(key)
            logger.info(messages.INFO_SKIPPED_RECORDS.format(len(processed_keys)))
        except Exception as e:
            logger.warning(messages.WARN_READ_FILE_FAILED.format(e))

    logger.info("[3/4] Processing rasters...")

    def worker_task(raster_path):
        try:
            return process_single_raster(raster_path, zones)
        except Exception as e:
            logger.warning(f"Error on {raster_path}: {e}")
            return []

    all_results = []
    file_exists = output_csv.exists()

    if args.workers > 1:
        logger.info(messages.STATUS_MULTITHREAD.format(args.workers))
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(worker_task, path): path for path in tasks}
            for i, future in enumerate(as_completed(futures), 1):
                res = future.result()
                for row in res:
                    unique_key = f"{row['zone_name']}_{row['date']}_{row['product']}"
                    if unique_key not in processed_keys:
                        with CSV_WRITE_LOCK:
                            df_row = pd.DataFrame([row])
                            df_row.to_csv(
                                output_csv,
                                mode="a",
                                header=not file_exists,
                                index=False,
                                encoding="utf-8-sig",
                                sep=";",
                                decimal=",",
                            )
                            file_exists = True
                        all_results.append(row)
                        processed_keys.add(unique_key)

                if not args.test and i % 20 == 0:
                    logger.info(messages.INFO_PROCESSED_RASTERS.format(i, len(tasks)))
    else:
        for i, raster_path in enumerate(tasks, 1):
            res = worker_task(raster_path)
            for row in res:
                unique_key = f"{row['zone_name']}_{row['date']}_{row['product']}"
                if unique_key not in processed_keys:
                    df_row = pd.DataFrame([row])
                    df_row.to_csv(
                        output_csv,
                        mode="a",
                        header=not file_exists,
                        index=False,
                        encoding="utf-8-sig",
                        sep=";",
                        decimal=",",
                    )
                    file_exists = True
                    all_results.append(row)
                    processed_keys.add(unique_key)

            if not args.test and i % 20 == 0:
                logger.info(messages.INFO_PROCESSED_RASTERS.format(i, len(tasks)))

    logger.info("[4/4] Saving results...")

    if not all_results and output_csv.exists():
        try:
            existing_count = len(
                pd.read_csv(output_csv, sep=";", decimal=",", encoding="utf-8-sig")
            )
            if existing_count > 0:
                logger.info(
                    f"В CSV уже есть {existing_count} записей. Новые не добавлены."
                )
                return
        except Exception:
            pass

    if all_results:
        df = pd.DataFrame(all_results)
        logger.info(messages.LOG_SAVED_OK.format(len(df), output_csv))

        agg_df = (
            df.groupby(["zone_id", "zone_name", "year", "month", "product"])["mean"]
            .agg(["mean", "std", "min", "max", "count"])
            .reset_index()
        )
        agg_df = agg_df.rename(
            columns={
                "mean": "mean_val",
                "std": "std_val",
                "min": "min_val",
                "max": "max_val",
                "count": "n_observations",
            }
        )
        agg_path = str(output_csv).replace(".csv", "_agg.csv")
        agg_df.to_csv(agg_path, index=False, encoding="utf-8-sig", sep=";", decimal=",")
        logger.info(messages.LOG_SAVED_AGG.format(agg_path))
    else:
        logger.warning(messages.LOG_NO_DATA)

    logger.info(messages.LOG_FINISHED.format(time.time() - start_time))
