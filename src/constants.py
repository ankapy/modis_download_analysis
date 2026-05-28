# -*- coding: utf-8 -*-
"""Константы проекта: коэффициенты, пороги, имена полей."""

# Продукты MODIS и их параметры
LST_PRODUCT_CODE = "MOD11A2"
LST_BAND_NAME = "LST_Day_1km"
LST_SCALE = 0.02
LST_OFFSET = -273.15
LST_NODATA = 0

NDVI_PRODUCT_CODE = "MOD13Q1"
NDVI_BAND_NAME = "NDVI"
NDVI_SCALE = 0.0001
NDVI_NODATA = -3000

# Пороговые значения
MIN_VALID_PIXELS = 10
BUFFER_DEGREES = 0.045  # ~5 км в градусах
MIN_CV_PERCENT = 0
MAX_CV_PERCENT = 100

# Имена полей и слоёв
ZONE_FIELD_NAME = "target_zone"
ZONES_LAYER_NAME = "natural_zones"
ZONES_GPKG_FILENAME = "zones.gpkg"

# Временные параметры
VEG_START_MONTH = 5
VEG_END_MONTH = 9
DOY_MONTH_MAP = {
    (1, 59): 2,
    (60, 90): 3,
    (91, 120): 4,
    (121, 151): 5,
    (152, 181): 6,
    (182, 212): 7,
    (213, 243): 8,
    (244, 273): 9,
}

# QA-флаги (заглушки, уточнить по документации продукта)
QA_CLOUD_MASK_BIT = 3
QA_SNOW_MASK_BIT = 4

# Форматы файлов
INPUT_RASTER_EXT = ".hdf"
OUTPUT_RASTER_EXT = ".tif"
OUTPUT_CSV_EXT = ".csv"
OUTPUT_GPKG_EXT = ".gpkg"

# Настройки визуализации
PLOT_DPI = 300
PLOT_FIGSIZE_DEFAULT = (10, 6)
