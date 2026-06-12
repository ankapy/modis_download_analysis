# -*- coding: utf-8 -*-
"""
Zonal Statistics: Pure GDAL + NumPy Approach (OPTIMIZED)
Оптимизации:
1. Кэширование растеризованной маски зон.
2. Многопоточность с безопасной записью в CSV (threading.Lock).
3. Флаг --flat для выгрузки Excel-файла с 4 листами для Origin Pro.
"""

import os
import sys
import time
import argparse
import threading
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
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

MASK_CACHE = {}
MASK_CACHE_LOCK = threading.Lock()
CSV_WRITE_LOCK = threading.Lock()

ZONE_ID_MAP = {
    "Тундра": 1,
    "Лесотундра": 2,
    "Северная тайга": 3,
    "Средняя тайга": 4,
    "Южная тайга": 5,
    "Подтайга": 6,
    "Горная тайга": 7,
    "Лесостепь": 8,
    "Степь": 9,
}


def load_zones(gpkg_path: str):
    """Чтение зон из GeoPackage с присвоением zone_id по маппингу."""
    if not os.path.exists(gpkg_path):
        raise FileNotFoundError(f"GeoPackage not found: {gpkg_path}")

    ds = ogr.Open(gpkg_path)
    layer = ds.GetLayer("natural_zones")
    if layer is None:
        layer = ds.GetLayerByIndex(0)

    zones = []
    for feat in layer:
        name = feat.GetField("target_zone")
        if name:
            name = str(name).strip()
            zone_id = ZONE_ID_MAP.get(name, 0)
            if zone_id == 0:
                print(f"[WARN] Неизвестная зона: '{name}', пропуск")
                continue
            geom = feat.GetGeometryRef()
            centroid = geom.Centroid()
            zones.append(
                {
                    "id": zone_id,
                    "name": name,
                    "wkt": geom.ExportToWkt(),
                    "lat_center": float(centroid.GetY()),
                    "lon_center": float(centroid.GetX()),
                }
            )
    ds = None

    zones.sort(key=lambda z: z["id"])
    print(f"[INFO] Загружено зон: {len(zones)}")
    for z in zones:
        print(f"  {z['id']}: {z['name']}")

    return zones


def get_zone_mask(raster_path: str, zones: list):
    """Получение маски зон для растра с потокобезопасным кэшированием."""
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

    with MASK_CACHE_LOCK:
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
    """Конвертация YYYY-DOY в YYYY-MM-DD для Origin Pro."""
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
    date_str = extract_date(os.path.basename(raster_path))
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


def build_excel_from_csv(csv_path: Path, excel_path: Path):
    """
    Создание Excel-файла с 4 листами из плоского CSV:
    - zonal_stats_flat_main: все данные + date_formatted
    - zonal_stats_flat_lst_ndvi: широкий формат (LST и NDVI в разных колонках)
    - zonal_stats_flat_lst: только LST
    - zonal_stats_flat_ndvi: только NDVI
    """
    print(f"\n[INFO] Создание Excel-файла из: {csv_path}")
    df = pd.read_csv(csv_path, sep=";", decimal=",", encoding="utf-8-sig")
    print(f"  Загружено записей: {len(df)}")

    # Добавляем date_formatted если его нет (для совместимости со старыми CSV)
    if "date_formatted" not in df.columns:
        df["date_formatted"] = df["date"].apply(doy_to_date)

    # Порядок колонок для основной таблицы
    main_columns = [
        "zone_id",
        "zone_name",
        "year",
        "month",
        "product",
        "date",
        "date_formatted",
        "lat_center",
        "lon_center",
        "pixel_count",
        "mean",
        "std",
        "median",
        "min",
        "max",
    ]
    main_columns = [c for c in main_columns if c in df.columns]
    df_main = df[main_columns].copy()

    # Фильтрация по продуктам
    df_lst = df_main[df_main["product"] == "LST"].copy()
    df_ndvi = df_main[df_main["product"] == "NDVI"].copy()

    print(f"  LST записей: {len(df_lst)}")
    print(f"  NDVI записей: {len(df_ndvi)}")

    # === Широкий формат LST + NDVI ===
    # Переименование статистик для LST
    lst_rename = {
        "mean": "LST_mean",
        "std": "LST_std",
        "median": "LST_median",
        "min": "LST_min",
        "max": "LST_max",
        "pixel_count": "pixel_count_LST",
    }
    df_lst_wide = df_lst.rename(columns=lst_rename)

    # Переименование статистик для NDVI
    ndvi_rename = {
        "mean": "NDVI_mean",
        "std": "NDVI_std",
        "median": "NDVI_median",
        "min": "NDVI_min",
        "max": "NDVI_max",
        "pixel_count": "pixel_count_NDVI",
    }
    df_ndvi_wide = df_ndvi.rename(columns=ndvi_rename)

    # Ключевые колонки для слияния
    merge_keys = [
        "zone_id",
        "zone_name",
        "year",
        "month",
        "date",
        "date_formatted",
        "lat_center",
        "lon_center",
    ]
    merge_keys = [
        k for k in merge_keys if k in df_lst_wide.columns and k in df_ndvi_wide.columns
    ]

    # Колонки для каждого набора
    lst_cols = merge_keys + [
        "LST_mean",
        "LST_std",
        "LST_median",
        "LST_min",
        "LST_max",
        "pixel_count_LST",
    ]
    ndvi_cols = merge_keys + [
        "NDVI_mean",
        "NDVI_std",
        "NDVI_median",
        "NDVI_min",
        "NDVI_max",
        "pixel_count_NDVI",
    ]

    lst_cols = [c for c in lst_cols if c in df_lst_wide.columns]
    ndvi_cols = [c for c in ndvi_cols if c in df_ndvi_wide.columns]

    df_lst_wide = df_lst_wide[lst_cols]
    df_ndvi_wide = df_ndvi_wide[ndvi_cols]

    # Outer join для сохранения всех данных (LST 8-day, NDVI 16-day - даты разные)
    df_wide = pd.merge(df_lst_wide, df_ndvi_wide, on=merge_keys, how="outer")
    df_wide = df_wide.sort_values(["zone_id", "year", "month"])

    print(f"  Широкий формат записей: {len(df_wide)}")

    # === Сохранение Excel ===
    print(f"\n[INFO] Сохранение Excel: {excel_path}")
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        df_main.to_excel(writer, sheet_name="zonal_stats_flat_main", index=False)
        df_wide.to_excel(writer, sheet_name="zonal_stats_flat_lst_ndvi", index=False)
        df_lst.to_excel(writer, sheet_name="zonal_stats_flat_lst", index=False)
        df_ndvi.to_excel(writer, sheet_name="zonal_stats_flat_ndvi", index=False)

    print(f"[OK] Excel сохранён: {excel_path}")
    print(
        f"  Листы: zonal_stats_flat_main, zonal_stats_flat_lst_ndvi, zonal_stats_flat_lst, zonal_stats_flat_ndvi"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Zonal Statistics Pure GDAL (Optimized)"
    )
    parser.add_argument(
        "--test", action="store_true", help="Быстрый тест: 1 файл на продукт"
    )
    parser.add_argument(
        "--flat", action="store_true", help="Excel-файл с 4 листами для Origin Pro"
    )
    parser.add_argument(
        "--workers", type=int, default=1, help="Количество потоков (рекомендуется 4-8)"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Zonal Statistics: Pure GDAL + NumPy (OPTIMIZED)")
    if args.flat:
        print(">>> РЕЖИМ: EXCEL С 4 ЛИСТАМИ (ДЛЯ ORIGIN PRO) <<<")
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

    # Определяем файлы
    temp_csv = TABLES_DIR / "zonal_stats_flat_temp.csv"
    output_csv = TABLES_DIR / "zonal_stats_flat.csv"

    # Выбираем источник данных: temp_csv если существует, иначе output_csv
    if args.flat and temp_csv.exists():
        source_csv = temp_csv
        print(f"[INFO] Используем временный файл: {source_csv}")
    else:
        source_csv = output_csv
        print(f"[INFO] Используем основной файл: {source_csv}")

    processed_keys = set()
    if source_csv.exists():
        print(f"[INFO] Найден существующий файл: {source_csv}")
        print("[INFO] Загрузка индексов для пропуска сделанного...")
        try:
            cols_to_read = ["zone_name", "date", "product"]
            existing_df = pd.read_csv(source_csv, usecols=cols_to_read, sep=";")
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
    file_exists = source_csv.exists()

    if args.workers > 1:
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
                                source_csv,
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
                    print(f"  Processed {i}/{len(tasks)} rasters...")
    else:
        for i, raster_path in enumerate(tasks, 1):
            res = worker_task(raster_path)
            for row in res:
                unique_key = f"{row['zone_name']}_{row['date']}_{row['product']}"
                if unique_key not in processed_keys:
                    df_row = pd.DataFrame([row])
                    df_row.to_csv(
                        source_csv,
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
                print(f"  Processed {i}/{len(tasks)} rasters...")

    print("[4/4] Saving results...")

    if args.flat:
        # Создаём Excel из source_csv (тот файл, куда реально писались данные)
        if source_csv.exists():
            excel_path = TABLES_DIR / "zonal_stats_flat.xlsx"
            build_excel_from_csv(source_csv, excel_path)

            # Если данные писались в output_csv, переименовываем в temp_csv для совместимости
            if source_csv == output_csv and temp_csv != output_csv:
                try:
                    output_csv.rename(temp_csv)
                    print(f"[OK] Файл переименован: {temp_csv}")
                except Exception as e:
                    print(f"[WARN] Не удалось переименовать: {e}")
        else:
            print(f"[ERROR] Файл данных не найден: {source_csv}")
            print("[ERROR] Невозможно создать Excel без данных")
    elif all_results:
        df = pd.DataFrame(all_results)
        df.to_csv(output_csv, index=False, encoding="utf-8-sig", sep=";", decimal=",")
        print(f"[OK] Saved {len(df)} records to {output_csv}")

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
        print(f"[OK] Saved aggregated summary to {agg_path}")
    else:
        print("[WARN] No new data extracted. Check if zones intersect rasters.")

    print(f"\n[OK] Finished in {time.time() - start_time:.1f} sec")


if __name__ == "__main__":
    main()
