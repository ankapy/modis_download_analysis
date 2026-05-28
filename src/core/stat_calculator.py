# -*- coding: utf-8 -*-
"""Расчёт зональной статистики с проверкой пересечений."""

import os
import numpy as np
from osgeo import gdal, ogr, osr
from src import constants as C
from src import messages as M
from src import logger
from src.utils.raster_io import check_intersection
from src.utils.temporal import parse_doy, doy_to_month
from src.utils.stats import calculate_basic_stats, calculate_cv


def calculate_zonal_stats(raster_path, zones, config):
    """Извлекает значения растра по полигонам зон и рассчитывает статистику. Возвращает список записей."""
    ds = gdal.Open(raster_path)
    if not ds:
        logger.warning(M.ERR_RASTER_OPEN.format(path=raster_path))
        return []

    band = ds.GetRasterBand(1)
    raster_data = band.ReadAsArray().astype(np.float32)
    nodata = (
        band.GetNoDataValue() if band.GetNoDataValue() is not None else C.LST_NODATA
    )
    geotransform = ds.GetGeoTransform()
    projection = ds.GetProjection()
    cols, rows = ds.RasterXSize, ds.RasterYSize
    ds = None

    date_str = os.path.basename(raster_path)
    year_doy = parse_doy(date_str)
    if not year_doy:
        return []
    year, doy = year_doy
    month = doy_to_month(doy)
    product = config.get("product", "UNKNOWN")

    # Растеризация зон в память
    mem_driver = ogr.GetDriverByName("Memory")
    v_ds = mem_driver.CreateDataSource("mem_zonal")
    srs = osr.SpatialReference()
    srs.ImportFromWkt(projection)
    layer = v_ds.CreateLayer("zones", srs, ogr.wkbPolygon)
    field_def = ogr.FieldDefn("id", ogr.OFTInteger)
    layer.CreateField(field_def)

    for idx, zone in enumerate(zones, 1):
        feat = ogr.Feature(layer.GetLayerDefn())
        feat.SetField("id", idx)
        feat.SetGeometry(ogr.CreateGeometryFromWkt(zone["wkt"]))
        layer.CreateFeature(feat)

    mask_driver = gdal.GetDriverByName("MEM")
    mask_ds = mask_driver.Create("mask", cols, rows, 1, gdal.GDT_Int32)
    mask_ds.SetGeoTransform(geotransform)
    mask_ds.SetProjection(projection)
    gdal.RasterizeLayer(
        mask_ds,
        [1],
        layer,
        burn_values=[0],
        options=["ATTRIBUTE=id", "ALL_TOUCHED=TRUE"],
    )
    mask_data = mask_ds.ReadAsArray()
    v_ds = None
    mask_ds = None

    results = []
    for idx, zone in enumerate(zones, 1):
        if not check_intersection(zone["wkt"], raster_path):
            logger.info(
                M.MSG_ZONAL_NO_INTERSECTION.format(
                    zone=zone["name"], raster=os.path.basename(raster_path)
                )
            )
            continue

        zone_mask = mask_data == idx
        values = raster_data[zone_mask]
        if len(values) < C.MIN_VALID_PIXELS:
            continue

        valid_values = values[~np.isnan(values)]
        if len(valid_values) == 0:
            continue

        stats = calculate_basic_stats(valid_values)
        stats["cv"] = calculate_cv(stats["mean"], stats["std"])
        stats["zone_name"] = zone["name"]
        stats["year"] = year
        stats["month"] = month
        stats["product"] = product
        stats["lat_center"] = zone["lat_center"]
        stats["lon_center"] = zone["lon_center"]
        stats["date"] = "{:04d}-{:03d}".format(year, doy)
        results.append(stats)

    logger.info(
        M.MSG_ZONAL_PROCESSED.format(
            filename=os.path.basename(raster_path), valid_pixels=len(results)
        )
    )
    return results
