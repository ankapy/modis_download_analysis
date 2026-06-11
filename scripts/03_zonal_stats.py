# -*- coding: utf-8 -*-
"""
Zonal Statistics: Pure GDAL + NumPy Approach (OPTIMIZED)
Оптимизации:
1. Кэширование растеризованной маски зон (ускорение в 5-10 раз).
2. Поддержка многопоточности через ThreadPoolExecutor.
3. Флаг --flat для выгрузки плоской таблицы без агрегации.
"""

import os
import sys
import time
import argparse
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATA_PATHS, TEMPORAL_RANGE

try:
    from osgeo import gdal, ogr, osr

    gdal.UseExceptions()
    gdal.SetConfigOption("GDAL_CACHEMAX", "1024")
    gdal.SetConfigOption("GDAL_NUM_THREADS", "ALL_CPUS")
except ImportError:
    print("[ERROR] GDAL not found. Run in ArcGIS Pro env.")
    sys.exit(1)

ZONES_GPKG = os.path.join(DATA_PATHS["gis"], "zones.gpkg")
TABLES_DIR = Path(DATA_PATHS["tables"])
TABLES_DIR.mkdir(parents=True, exist_ok=True)

MASK_CACHE = {}  # Кэш для хранения растеризованных масок


def load_zones(gpkg_path: str):
    """Чтение зон из GeoPackage."""
    if not os.path.exists(gpkg_path):
        raise FileNotFoundError(f"GeoPackage not found: {gpkg_path}")

    ds = ogr.Open(gpkg_path)
    layer = ds.GetLayer("natural_zones")
    if layer is None:
        layer = ds.GetLayerByIndex(0)

    zones = []
    for i, feat in enumerate(layer):
        name = feat.GetField("target_zone")
        if name:
            geom = feat.GetGeometryRef()
            centroid = geom.Centroid()
            zones.append(
                {
                    "id": i + 1,
                    "name": str(name).strip(),
                    "wkt": geom.ExportToWkt(),
                    "lat_center": float(centroid.GetY()),
                    "lon_center": float(centroid.GetX()),
                }
            )
    ds = None
    return zones


def get_zone_mask(raster_path: str, zones: list):
    """
    Получение маски зон для растра.
    Использует кэш, чтобы не растеризовать одни и те же полигоны повторно.
    """
    ds = gdal.Open(raster_path)
    if ds is None:
        return None, None, None, None

    cols, rows = ds.RasterXSize, ds.RasterYSize
    geotransform = ds.GetGeoTransform()
    projection = ds.GetProjection()
    ds = None

    cache_key = f"{cols}_{rows}_{geotransform[0]:.4f}_{geotransform[3]:.4f}"

    if cache_key in MASK_CACHE:
        return MASK_CACHE[cache_key], cols, rows, geotransform

    print(f"  [INFO] Растеризация маски зон (первый раз для этого формата растра)...")
    mem_driver = ogr.GetDriverByName("Memory")
    v_ds = mem_driver.CreateDataSource("mem")
    srs = osr.SpatialReference()
    srs.ImportFromWkt(projection)
    v_layer = v_ds.CreateLayer("zones", srs=srs, geom_type=ogr.wkbPolygon)

    field_def = ogr.FieldDefn("zone_id", ogr.OFTInteger)
    v_layer.CreateField(field_def)

    for zone in zones:
        feat = ogr.Feature(v_layer.GetLayerDefn())
        feat.SetField("zone_id", zone["id"])
        feat.SetGeometry(ogr.CreateGeometryFromWkt(zone["wkt"]))
        v_layer.CreateFeature(feat)
        feat = None

    mask_ds = gdal.GetDriverByName("MEM").Create("mask", cols, rows, 1, gdal.GDT_Int32)
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


def doy_to_month(date_str: str) -> int:
    """Конвертация дня года в месяц."""
    if date_str == "unknown":
        return 0
    try:
        doy = int(date_str.split("-")[1])
        if doy <= 59:
            return 2
        if doy <= 90:
            return 3
        if doy <= 120:
            return 4
        if doy <= 151:
            return 5
        if doy <= 181:
            return 6
        if doy <= 212:
            return 7
        if doy <= 243:
            return 8
        if doy <= 273:
            return 9
        return 10
    except Exception:
        return 0


def process_single_raster(raster_path: str, zones: list):
    """
    Обработка одного растра с использованием кэшированной маски.
    Возвращает список словарей с результатами.
    """
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
    date_str = extract_date(os.path.basename(raster_path))
    month = doy_to_month(date_str)

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
                    "zone_name": zone["name"],
                    "year": year,
                    "month": month,
                    "product": product,
                    "date": date_str,
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


def main():
    parser = argparse.ArgumentParser(
        description="Zonal Statistics Pure GDAL (Optimized)"
    )
    parser.add_argument(
        "--test", action="store_true", help="Быстрый тест: 1 файл на продукт"
    )
    parser.add_argument(
        "--flat",
        action="store_true",
        help="Плоская таблица без агрегации (для Origin Pro)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Количество потоков (по умолчанию 1, рекомендуется 4-8)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Zonal Statistics: Pure GDAL + NumPy (OPTIMIZED)")
    if args.flat:
        print(">>> РЕЖИМ: ПЛОСКАЯ ТАБЛИЦА (БЕЗ АГРЕГАЦИИ) <<<")
    if args.workers > 1:
        print(f">>> РЕЖИМ: МНОГОПОТОЧНОСТЬ ({args.workers} потоков) <<<")
    print("=" * 60)

    start_time = time.time()

    print("[1/4] Loading zones from GeoPackage...")
    try:
        zones = load_zones(ZONES_GPKG)
        if not zones:
            print("[ERROR] No zones loaded.")
            return
        print(f"[OK] Loaded {len(zones)} zones.")
    except Exception as e:
        print(f"[ERROR] {e}")
        return

    print("[2/4] Scanning for rasters...")
    products = ["LST", "NDVI"]
    years = list(range(TEMPORAL_RANGE["start_year"], TEMPORAL_RANGE["end_year"] + 1))
    tasks = []

    for product in products:
        for year in years:
            prod_dir = Path(DATA_PATHS["processed"]) / product / str(year)
            if prod_dir.exists():
                tifs = sorted(prod_dir.glob("*.tif"))
                if args.test:
                    if tifs:
                        tasks.append(str(tifs[0]))
                        print(f"  [TEST] Found {tifs[0].name}")
                else:
                    for tif in tifs:
                        tasks.append(str(tif))

    print(f"[OK] Found {len(tasks)} rasters to process.")

    output_filename = "zonal_stats_flat.csv" if args.flat else "zonal_stats_full.csv"
    output_csv = TABLES_DIR / output_filename

    processed_keys = set()
    if output_csv.exists():
        print(f"[INFO] Найден существующий файл: {output_csv}")
        print("[INFO] Загрузка индексов для пропуска сделанного...")
        try:
            cols_to_read = ["zone_name", "date", "product"]
            existing_df = pd.read_csv(output_csv, usecols=cols_to_read)
            for _, row in existing_df.iterrows():
                key = f"{row['zone_name']}_{row['date']}_{row['product']}"
                processed_keys.add(key)
            print(f"[OK] Пропущено {len(processed_keys)} уже готовых записей.")
        except Exception as e:
            print(f"[WARN] Не удалось прочитать файл: {e}. Начинаем с нуля.")

    print("[3/4] Processing rasters...")

    def worker_task(raster_path):
        try:
            return process_single_raster(raster_path, zones)
        except Exception as e:
            print(f"[WARN] Error on {raster_path}: {e}")
            return []

    all_results = []

    if args.workers > 1:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(worker_task, path): path for path in tasks}
            for i, future in enumerate(as_completed(futures), 1):
                res = future.result()
                for row in res:
                    unique_key = f"{row['zone_name']}_{row['date']}_{row['product']}"
                    if unique_key not in processed_keys:
                        df_row = pd.DataFrame([row])
                        df_row.to_csv(
                            output_csv,
                            mode="a",
                            header=not output_csv.exists(),
                            index=False,
                            encoding="utf-8-sig",
                        )
                        all_results.append(row)
                        processed_keys.add(unique_key)
                if not args.test and i % 20 == 0:
                    print(f"  Processed {i}/{len(tasks)} rasters...")
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
                        header=not output_csv.exists(),
                        index=False,
                        encoding="utf-8-sig",
                    )
                    all_results.append(row)
                    processed_keys.add(unique_key)
            if not args.test and i % 20 == 0:
                print(f"  Processed {i}/{len(tasks)} rasters...")

    print("[4/4] Saving results...")
    if args.flat:
        print(f"[OK] Flat data saved to: {output_csv}")
    elif all_results:
        df = pd.DataFrame(all_results)
        df.to_csv(output_csv, index=False, encoding="utf-8-sig")
        print(f"[OK] Saved {len(df)} records to {output_csv}")

        agg_df = (
            df.groupby(["zone_name", "year", "month", "product"])["mean"]
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
        agg_df.to_csv(agg_path, index=False, encoding="utf-8-sig")
        print(f"[OK] Saved aggregated summary to {agg_path}")
    else:
        print("[WARN] No new data extracted. Check if zones intersect rasters.")

    print(f"\n[OK] Finished in {time.time() - start_time:.1f} sec")


if __name__ == "__main__":
    main()
