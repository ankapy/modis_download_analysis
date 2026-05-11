"""
Извлечение общей границы растров MODIS (footprint).
"""

import arcpy
import sys
from pathlib import Path

from config import DATA_PATHS

# Пути
PROCESSED_DIR = Path(DATA_PATHS["processed"])
OUTPUT_SHP = Path(DATA_PATHS["gis"]) / "raster_footprint.shp"

# Разрешаем перезапись выходных данных
arcpy.env.overwriteOutput = True

# 1. Сбор всех GeoTIFF
tifs = list(PROCESSED_DIR.rglob("*.tif"))
print(f"[INFO] Найдено растров: {len(tifs)}")

if not tifs:
    print("[ERROR] Растров не найдено.")
    sys.exit(1)

# Убедимся, что папка для сохранения существует
OUTPUT_SHP.parent.mkdir(parents=True, exist_ok=True)

# 2. Создание полигонов extents в памяти
# Указываем пространственную привязку WGS 84, чтобы избежать предупреждений
temp_fc = arcpy.CreateFeatureclass_management(
    "in_memory", "extents", "POLYGON", spatial_reference="4326"
)

count = 0
errors = 0

with arcpy.da.InsertCursor(temp_fc, ["SHAPE@"]) as cursor:
    for tif in tifs:
        try:
            desc = arcpy.Describe(str(tif))
            ext = desc.extent

            # Пропуск невалидных границ
            if (
                ext.XMin is None
                or ext.YMin is None
                or ext.width == 0
                or ext.height == 0
            ):
                continue

            # Спациальная референция
            sr = desc.spatialReference
            if sr is None:
                sr = arcpy.SpatialReference(4326)

            # Создание геометрии
            points = arcpy.Array(
                [
                    arcpy.Point(ext.XMin, ext.YMin),
                    arcpy.Point(ext.XMax, ext.YMin),
                    arcpy.Point(ext.XMax, ext.YMax),
                    arcpy.Point(ext.XMin, ext.YMax),
                ]
            )

            poly = arcpy.Polygon(points, sr)
            if poly.area > 0:
                cursor.insertRow([poly])
                count += 1
        except Exception:
            errors += 1
            continue

print(f"[OK] Обработано тайлов: {count}")
print(f"[WARN] Ошибки: {errors}")

if count == 0:
    print("[ERROR] Границы не извлечены.")
else:
    # 3. Слияние (Dissolve)
    arcpy.Dissolve_management(
        in_features=temp_fc,
        out_feature_class=str(OUTPUT_SHP),
        dissolve_field="",  # Слияние всех (без группировки)
        multi_part="MULTI_PART",  # Разрешить мульти-полилины
    )

    print(f"[OK] Footprint сохранён: {OUTPUT_SHP}")
