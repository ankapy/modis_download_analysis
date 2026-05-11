# -*- coding: utf-8 -*-
"""
Zonal Statistics: Pure GDAL + NumPy Approach
Метод: Direct Memory Masking
Флаг --test для быстрой проверки пайплайна.
"""

import os
import sys
import time
import argparse
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATA_PATHS, TEMPORAL_RANGE

try:
    from osgeo import gdal, ogr, osr

    gdal.UseExceptions()
    gdal.SetConfigOption("GDAL_CACHEMAX", "1024")
except ImportError:
    print("[ERROR] GDAL not found. Run in ArcGIS Pro env.")
    sys.exit(1)

# Пути
ZONES_GPKG = os.path.join(DATA_PATHS["gis"], "zones.gpkg")
OUTPUT_CSV = os.path.join(DATA_PATHS["tables"], "zonal_stats_monthly.csv")


def load_zones(gpkg_path: str):
    """Чтение зон из GeoPackage через ogr. Вычисляет lat_center центроида."""
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
            # Вычисляем центроид напрямую через OGR
            centroid = geom.Centroid()
            lat_center = centroid.GetY()

            zones.append(
                {
                    "id": i + 1,
                    "name": str(name).strip(),
                    "wkt": geom.ExportToWkt(),
                    "lat_center": float(lat_center),
                }
            )
    ds = None
    return zones


def extract_date(filename: str) -> str:
    """Извлечение YYYY-DOY из имени файла MODIS"""
    try:
        parts = filename.split(".")
        if len(parts) >= 2 and parts[1].startswith("A"):
            return f"{parts[1][1:5]}-{parts[1][5:8]}"
    except Exception:
        pass
    return "unknown"


def doy_to_month(date_str: str) -> int:
    """Конвертация дня года в месяц"""
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


def process_raster_pure_gdal(raster_path: str, zones: list):
    """Растеризация зон в память и расчет статистики через NumPy."""
    ds = gdal.Open(raster_path)
    if ds is None:
        return []

    band = ds.GetRasterBand(1)
    raster_data = band.ReadAsArray().astype(np.float32)
    nodata = band.GetNoDataValue()
    if nodata is None:
        nodata = -9999

    cols, rows = ds.RasterXSize, ds.RasterYSize
    geotransform = ds.GetGeoTransform()
    projection = ds.GetProjection()
    ds = None

    # Векторный слой в памяти
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

    # Растеризация
    mask_driver = gdal.GetDriverByName("MEM")
    mask_ds = mask_driver.Create("mask", cols, rows, 1, gdal.GDT_Int32)
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

    # Статистика
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
    parser = argparse.ArgumentParser(description="Zonal Statistics Pure GDAL")
    parser.add_argument(
        "--test", action="store_true", help="Быстрый тест: 1 файл на продукт"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Zonal Statistics: Pure GDAL + NumPy")
    if args.test:
        print(">>> РЕЖИМ: БЫСТРЫЙ ТЕСТ (1 файл) <<<")
    print("=" * 60)
    start_time = time.time()

    # 1. Загрузка зон
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

    # 2. Поиск файлов
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

    # 3. Обработка
    print("[3/4] Processing (Direct Memory Masking)...")
    all_results = []

    for i, raster_path in enumerate(tasks):
        try:
            res = process_raster_pure_gdal(raster_path, zones)
            all_results.extend(res)
            if not args.test and (i + 1) % 10 == 0:
                print(f"  Processed {i+1}/{len(tasks)} rasters...")
        except Exception as e:
            print(f"[WARN] Error on {raster_path}: {e}")

    # 4. Сохранение и агрегация
    print("[4/4] Saving results & generating summary...")
    if all_results:
        df = pd.DataFrame(all_results)
        os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)

        # Сохраняем основные данные (включая lat_center)
        df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
        print(f"[OK] Saved {len(df)} records to {OUTPUT_CSV}")

        # Генерируем агрегированную таблицу
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

        agg_path = OUTPUT_CSV.replace(".csv", "_agg.csv")
        agg_df.to_csv(agg_path, index=False, encoding="utf-8-sig")
        print(f"[OK] Saved aggregated summary to {agg_path}")

        print(f"\nПример выходных данных:")
        print(
            df[["zone_name", "year", "month", "product", "mean", "lat_center"]].head(3)
        )
    else:
        print("[WARN] No data extracted. Check if zones intersect rasters.")

    print(f"\n[OK] Finished in {time.time() - start_time:.1f} sec")


if __name__ == "__main__":
    main()
