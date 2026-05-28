# -*- coding: utf-8 -*-
"""Предобработка данных: загрузка зон, расчёт границ, фильтрация пикселей."""

import numpy as np
from osgeo import ogr
from src import constants as C
from src import messages as M
from src import logger


def load_zones(gpkg_path, zone_field=C.ZONE_FIELD_NAME):
    """Загружает полигоны зон из векторного файла. Возвращает список словарей."""
    if not ogr.Open(gpkg_path):
        raise FileNotFoundError(M.ERR_FILE_NOT_FOUND.format(path=gpkg_path))
    ds = ogr.Open(gpkg_path)
    layer = ds.GetLayer()
    zones = []
    for feat in layer:
        geom = feat.GetGeometryRef()
        if not geom or geom.IsEmpty():
            continue
        name = feat.GetField(zone_field)
        if name is None:
            continue
        centroid = geom.Centroid()
        zones.append(
            {
                "name": str(name).strip(),
                "wkt": geom.ExportToWkt(),
                "lat_center": centroid.GetY(),
                "lon_center": centroid.GetX(),
            }
        )
    ds = None
    logger.info(M.MSG_ZONES_LOADED.format(count=len(zones), path=gpkg_path))
    return zones


def compute_bounding_box(zones):
    """Вычисляет общую ограничивающую рамку для списка зон. Возвращает кортеж (minx, miny, maxx, maxy)."""
    if not zones:
        raise ValueError(M.ERR_NO_ZONES.format())
    minx = miny = float("inf")
    maxx = maxy = float("-inf")
    for zone in zones:
        geom = ogr.CreateGeometryFromWkt(zone["wkt"])
        x_min, x_max, y_min, y_max = geom.GetEnvelope()
        minx = min(minx, x_min)
        maxx = max(maxx, x_max)
        miny = min(miny, y_min)
        maxy = max(maxy, y_max)
    return minx, miny, maxx, maxy


def filter_valid_pixels(array, nodata_value):
    """Заменяет невалидные значения в массиве на NaN. Возвращает np.ndarray."""
    array = np.asarray(array, dtype=np.float32)
    invalid = (array == nodata_value) | np.isnan(array) | np.isinf(array)
    array[invalid] = np.nan
    return array
