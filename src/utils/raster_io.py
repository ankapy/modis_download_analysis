# -*- coding: utf-8 -*-
"""Утилиты для чтения и записи растровых данных через GDAL."""

import os
import numpy as np
from osgeo import gdal, ogr, osr
from .. import messages as M
from .. import logger

gdal.UseExceptions()


def open_raster(raster_path):
    """Открывает растровый файл GDAL. Возвращает dataset или None."""
    if not os.path.exists(raster_path):
        logger.warning(M.ERR_FILE_NOT_FOUND.format(path=raster_path))
        return None
    try:
        dataset = gdal.Open(raster_path)
        return dataset
    except Exception as exc:
        logger.warning(M.ERR_RASTER_OPEN.format(path=raster_path, error=exc))
        return None


def read_as_masked_array(dataset, nodata_value):
    """Читает первый канал растра в массив, маскируя невалидные значения."""
    band = dataset.GetRasterBand(1)
    raster_array = band.ReadAsArray().astype(np.float32)
    if nodata_value is not None:
        raster_array[raster_array == nodata_value] = np.nan
    invalid_mask = np.isnan(raster_array) | np.isinf(raster_array)
    raster_array[invalid_mask] = np.nan
    return raster_array


def save_geotiff(data, raster_path, geotransform, projection, metadata=None):
    """Атомарно сохраняет массив в GeoTIFF с заданной геоинформацией."""
    rows, cols = data.shape
    driver = gdal.GetDriverByName("GTiff")
    temp_path = f"{raster_path}.tmp"
    try:
        out_dataset = driver.Create(
            temp_path,
            cols,
            rows,
            1,
            gdal.GDT_Float32,
            options=["COMPRESS=LZW", "TILED=YES"],
        )
        out_dataset.SetGeoTransform(geotransform)
        out_dataset.SetProjection(projection)
        out_band = out_dataset.GetRasterBand(1)
        out_band.WriteArray(data)
        out_band.SetNoDataValue(-9999.0)
        if metadata:
            for key, val in metadata.items():
                out_dataset.SetMetadataItem(key, val)
        out_band.FlushCache()
        out_dataset = None
        os.replace(temp_path, raster_path)
    except Exception as exc:
        logger.error(M.ERR_SAVE_RASTER.format(path=raster_path, error=exc))
        if os.path.exists(temp_path):
            os.remove(temp_path)


def check_intersection(polygon_wkt, raster_path):
    """Проверяет пересечение полигона зоны с экстендом растра."""
    dataset = open_raster(raster_path)
    if not dataset:
        return False
    try:
        gt = dataset.GetGeoTransform()
        cols, rows = dataset.RasterXSize, dataset.RasterYSize
        dataset = None
        raster_lon_min = gt[0]
        raster_lon_max = gt[0] + cols * gt[1]
        raster_lat_max = gt[3]
        raster_lat_min = gt[3] + rows * gt[5]

        ring = ogr.Geometry(ogr.wkbLinearRing)
        ring.AddPoint(raster_lon_min, raster_lat_max)
        ring.AddPoint(raster_lon_max, raster_lat_max)
        ring.AddPoint(raster_lon_max, raster_lat_min)
        ring.AddPoint(raster_lon_min, raster_lat_min)
        ring.AddPoint(raster_lon_min, raster_lat_max)
        raster_poly = ogr.Geometry(ogr.wkbPolygon)
        raster_poly.AddGeometry(ring)

        zone_geom = ogr.CreateGeometryFromWkt(polygon_wkt)
        return zone_geom.Intersects(raster_poly)
    except Exception:
        return False
