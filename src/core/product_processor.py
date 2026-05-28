# -*- coding: utf-8 -*-
"""Стратегия обработки продуктов MODIS (HDF → GeoTIFF)."""

import os
import numpy as np
from osgeo import gdal
from .. import constants as C
from .. import messages as M
from .. import logger
from ..utils.raster_io import open_raster, save_geotiff
from ..utils.temporal import parse_doy


class ProductNotFoundError(Exception):
    """Исключение при отсутствии зарегистрированной стратегии продукта."""

    pass


def _extract_subdataset(hdf_path, target_band_name):
    """Вспомогательная функция для поиска поддатасета по имени."""
    hdf_dataset = open_raster(hdf_path)
    if not hdf_dataset:
        return None, None
    subdatasets = hdf_dataset.GetSubDatasets()
    for sds_name, _ in subdatasets:
        if target_band_name in sds_name:
            return hdf_dataset, sds_name
    logger.warning(
        M.ERR_SUBDATASET_NOT_FOUND.format(
            band=target_band_name, file=os.path.basename(hdf_path)
        )
    )
    return None, None


def _process_generic(
    hdf_path, output_path, config, scale, offset, fill_value, band_name
):
    """Универсальная логика конвертации HDF в GeoTIFF."""
    hdf_dataset, sds_path = _extract_subdataset(hdf_path, band_name)
    if hdf_dataset is None:
        return False

    try:
        sds_dataset = gdal.Open(sds_path)
        if not sds_dataset:
            return False

        raw_array = sds_dataset.ReadAsArray().astype(np.float32)
        geotransform = sds_dataset.GetGeoTransform()
        projection = sds_dataset.GetProjection()
        metadata = {"PRODUCT": config.get("product", ""), "SOURCE": "MODIS"}

        raster_array = raw_array * scale + offset
        raster_array[raw_array == fill_value] = np.nan

        save_geotiff(raster_array, output_path, geotransform, projection, metadata)

        sds_dataset = None
        hdf_dataset = None
        year_info = parse_doy(os.path.basename(hdf_path))
        year_str = year_info[0] if year_info else "unknown"
        logger.info(
            M.MSG_CONVERTED.format(
                filename=os.path.basename(output_path),
                product=config.get("product", ""),
                year=year_str,
            )
        )
        return True
    except Exception as exc:
        logger.error(
            M.ERR_CONVERT_FAILED.format(filename=os.path.basename(hdf_path), error=exc)
        )
        return False


def lst_strategy(hdf_path, output_path, config):
    """Стратегия конвертации MOD11A2 LST."""
    return _process_generic(
        hdf_path,
        output_path,
        config,
        C.LST_SCALE,
        C.LST_OFFSET,
        C.LST_NODATA,
        C.LST_BAND_NAME,
    )


def ndvi_strategy(hdf_path, output_path, config):
    """Стратегия конвертации MOD13Q1 NDVI."""
    return _process_generic(
        hdf_path,
        output_path,
        config,
        C.NDVI_SCALE,
        0.0,
        C.NDVI_NODATA,
        C.NDVI_BAND_NAME,
    )


PROCESSOR_STRATEGIES = {
    C.LST_PRODUCT_CODE: lst_strategy,
    C.NDVI_PRODUCT_CODE: ndvi_strategy,
}


def get_processor(product_code):
    """Возвращает функцию-стратегию обработки продукта или вызывает ошибку."""
    if product_code not in PROCESSOR_STRATEGIES:
        raise ProductNotFoundError(M.ERR_UNKNOWN_PRODUCT.format(product=product_code))
    return PROCESSOR_STRATEGIES[product_code]
