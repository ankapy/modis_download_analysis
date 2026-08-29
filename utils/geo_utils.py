"""
Утилиты для работы с геоданными.
"""

import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from typing import List, Dict, Tuple
from osgeo import ogr, osr

# Явно включаем исключения OGR
ogr.UseExceptions()


def calculate_bbox_from_gpkg(gpkg_path: Path) -> Tuple[float, float, float, float]:
    """
    Расчёт bounding box из GeoPackage.
    Возвращает строго (lon_min, lat_min, lon_max, lat_max).
    """
    if not gpkg_path.exists():
        raise FileNotFoundError(f"GeoPackage не найден: {gpkg_path}")

    ds = ogr.Open(str(gpkg_path))
    if ds is None:
        raise RuntimeError(f"Не удалось открыть: {gpkg_path}")

    layer = ds.GetLayerByIndex(0)
    if layer is None:
        raise RuntimeError("Слой не найден в GeoPackage")

    # GetExtent возвращает (minX, maxX, minY, maxY)
    extent = layer.GetExtent()
    ds = None

    lon_min, lon_max, lat_min, lat_max = extent

    return (lon_min, lat_min, lon_max, lat_max)


def load_zones(gpkg_path: Path) -> List[Dict]:
    """Загрузка зон из GeoPackage с автоматической нумерацией."""
    if not gpkg_path.exists():
        raise FileNotFoundError(f"GeoPackage не найден: {gpkg_path}")

    ds = ogr.Open(str(gpkg_path))
    layer = ds.GetLayerByIndex(0)

    zones = []
    auto_id = 1

    for feat in layer:
        name = None
        for field_name in ["name", "zone_name", "NAME", "ZONE_NAME"]:
            name = feat.GetField(field_name)
            if name and str(name).strip():
                name = str(name).strip()
                break

        if not name:
            name = f"zone_{auto_id}"
            auto_id += 1

        zone_id = None
        for field_name in ["id", "ID", "zone_id", "ZONE_ID"]:
            zone_id = feat.GetField(field_name)
            if zone_id is not None:
                zone_id = int(zone_id)
                break

        if zone_id is None:
            zone_id = auto_id
            auto_id += 1

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

    return zones


def check_modis_coverage(bbox: Tuple[float, float, float, float]) -> bool:
    """Проверка корректности bbox и пересечения с областью MODIS."""
    lon_min, lat_min, lon_max, lat_max = bbox

    # Проверка логической корректности
    if lon_min >= lon_max or lat_min >= lat_max:
        return False

    # Проверка географических пределов
    if lat_min < -90 or lat_max > 90:
        return False
    if lon_min < -180 or lon_max > 180:
        return False

    return True


def generate_zone_colors(zone_names: List[str]) -> Dict[str, str]:
    """Генерация контрастных цветов для зон."""
    n_zones = len(zone_names)
    colors = plt.cm.tab20(np.linspace(0, 1, n_zones))

    color_map = {}
    for i, zone_name in enumerate(zone_names):
        rgb = colors[i][:3]
        hex_color = "#{:02x}{:02x}{:02x}".format(
            int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255)
        )
        color_map[zone_name] = hex_color

    return color_map
