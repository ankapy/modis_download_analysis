"""
Конвертация данных MODIS из HDF в GeoTIFF.
Опции: QA-фильтрация, VRT-мозаика, Mosaic Dataset (arcpy), многопоточность.
"""

import numpy as np
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from osgeo import gdal
from config import (
    MODIS_PRODUCTS,
    DATA_PATHS,
    DATE_FORMAT_ISO,
    CONVERT_MAX_WORKERS,
)
from utils.logger import setup_logger
from utils import messages

gdal.UseExceptions()

logger = setup_logger(__name__)


class MODISConverter:
    """Конвертер MODIS HDF в GeoTIFF."""

    def __init__(self, max_workers: int = CONVERT_MAX_WORKERS):
        """Инициализация конвертера."""
        self.input_dir = DATA_PATHS["raw"]
        self.output_dir = DATA_PATHS["processed"]
        self.max_workers = max_workers

    def _find_subdataset(self, subdatasets: list, band_name: str):
        """Поиск поддатасета с приоритетом точного совпадения имени бэнда."""
        exact = [name for name, _ in subdatasets if name.split(":")[-1] == band_name]
        if exact:
            return exact[0]
        return next((name for name, _ in subdatasets if band_name in name), None)

    def convert_product(
        self, hdf_path: Path, output_path: Path, product_key: str
    ) -> bool:
        """Конвертация одного файла продукта с QA-фильтрацией."""
        try:
            hdf_dataset = gdal.Open(str(hdf_path))
            if hdf_dataset is None:
                logger.error(messages.ERR_OPEN_FILE.format(hdf_path.name))
                return False

            config = MODIS_PRODUCTS[product_key]
            subdatasets = hdf_dataset.GetSubDatasets()

            target_subdataset = self._find_subdataset(subdatasets, config["band"])
            if target_subdataset is None:
                logger.error(messages.ERR_MISSING_DATASETS.format([config["band"]]))
                return False

            band = gdal.Open(target_subdataset)
            raw = band.ReadAsArray().astype(np.float32)

            # Маска NoData по сырым значениям ДО масштабирования.
            data = raw * config["scale_factor"] + config["offset"]
            data[raw == config["no_data_value"]] = np.nan

            # Опциональная QA-фильтрация облачных и низкокачественных пикселей.
            qa_band_name = config.get("qa_band")
            if qa_band_name:
                qa_sub = self._find_subdataset(subdatasets, qa_band_name)
                if qa_sub is None:
                    logger.warning(
                        messages.WARN_QA_BAND_NOT_FOUND.format(
                            qa_band_name, hdf_path.name
                        )
                    )
                else:
                    qa = gdal.Open(qa_sub).ReadAsArray().astype(np.int32)
                    if qa.shape != raw.shape:
                        logger.warning(
                            messages.WARN_QA_SHAPE_MISMATCH.format(
                                qa_band_name, hdf_path.name
                            )
                        )
                    else:
                        good = (qa & config.get("qa_mask", 0)) == config.get(
                            "qa_good", 0
                        )
                        data[~good] = np.nan

            self._save_geotiff(
                data, output_path, band, product_key, config["unit"], nodata=-9999
            )
            return True

        except RuntimeError as e:
            logger.error(
                messages.ERR_CONVERSION_FAILED.format(
                    product_key, hdf_path.name, str(e)
                )
            )
            return False
        except OSError as e:
            logger.error(messages.ERR_OPEN_FILE.format(f"{hdf_path.name}: {str(e)}"))
            return False

    def _save_geotiff(
        self,
        data: np.ndarray,
        output_path: Path,
        source_band,
        product_key: str,
        unit: str,
        nodata: float,
    ):
        """Сохранение массива в GeoTIFF."""
        try:
            geotransform = source_band.GetGeoTransform()
            projection = source_band.GetProjection()
            rows, cols = data.shape

            driver = gdal.GetDriverByName("GTiff")
            out_dataset = driver.Create(
                str(output_path),
                cols,
                rows,
                1,
                gdal.GDT_Float32,
                options=["COMPRESS=LZW", "TILED=YES"],
            )

            out_band = out_dataset.GetRasterBand(1)
            out_band.WriteArray(data)
            out_band.SetNoDataValue(nodata)

            out_dataset.SetGeoTransform(geotransform)
            out_dataset.SetProjection(projection)
            out_dataset.SetMetadataItem("PRODUCT", product_key)
            out_dataset.SetMetadataItem("UNIT", unit)
            out_dataset.SetMetadataItem(
                "PROCESSING_DATE", datetime.now().strftime(DATE_FORMAT_ISO)
            )
            out_dataset.SetMetadataItem("SOURCE", "MODIS Terra/Aqua")

            out_band.FlushCache()
            out_band = None
            out_dataset = None
            logger.info(messages.LOG_CONVERSION_FILE_OK.format(output_path.name))

        except RuntimeError as e:
            logger.error(messages.ERR_SAVE_GEOTIFF.format(str(e)))

    def _convert_one(self, hdf_file: Path, output_dir: Path, product_key: str) -> str:
        """Конвертация одного файла с пропуском существующих."""
        output_path = output_dir / hdf_file.with_suffix(".tif").name
        if output_path.exists():
            return "skipped"
        return (
            "ok"
            if self.convert_product(hdf_file, output_path, product_key)
            else "failed"
        )

    def process_year(self, product_key: str, year: int):
        """Обработка всех файлов за конкретный год в несколько потоков."""
        config = MODIS_PRODUCTS[product_key]
        product_code = config["product"]
        input_dir = self.input_dir / product_code / str(year)

        hdf_files = list(input_dir.glob("*.hdf"))
        if not hdf_files:
            logger.debug(messages.LOG_CONVERSION_WARN.format(input_dir))
            return

        output_dir = self.output_dir / product_key / str(year)
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            messages.LOG_CONVERSION_START.format(product_code, year, len(hdf_files))
        )

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            statuses = list(
                executor.map(
                    lambda f: self._convert_one(f, output_dir, product_key),
                    hdf_files,
                )
            )

        converted = statuses.count("ok")
        skipped = statuses.count("skipped")
        failed = statuses.count("failed")

        logger.info(messages.LOG_CONVERSION_OK.format(converted, len(hdf_files)))
        if skipped > 0:
            logger.info(messages.INFO_SKIPPED_EXISTING.format(skipped))
        if failed > 0:
            logger.info(messages.LOG_CONVERSION_ERROR.format(failed))

        self.build_year_vrt(product_key, year, output_dir)

    def build_year_vrt(self, product_key: str, year: int, year_dir: Path):
        """Сборка VRT-мозаики тайлов года для удобного открытия в ГИС."""
        tifs = sorted(str(p) for p in year_dir.glob("*.tif"))
        if not tifs:
            return
        vrt_path = self.output_dir / product_key / f"{product_key}_{year}.vrt"
        try:
            if vrt_path.exists():
                vrt_path.unlink()
            gdal.BuildVRT(str(vrt_path), tifs)
            logger.info(messages.INFO_VRT_SAVED.format(vrt_path))
        except RuntimeError as e:
            logger.warning(messages.WARN_VRT_FAILED.format(vrt_path, str(e)))


def build_mosaic_dataset(product_key: str, year: int, year_dir: Path, gdb_dir: Path):
    """Сборка Mosaic Dataset за год в File GDB для ArcGIS Pro."""
    try:
        import arcpy
    except ImportError:
        logger.warning(messages.WARN_ARCPY_NOT_FOUND)
        return

    tifs = sorted(str(p) for p in year_dir.glob("*.tif"))
    if not tifs:
        return

    md_name = f"{product_key}_{year}"
    try:
        gdb_dir.mkdir(parents=True, exist_ok=True)
        gdb_path = gdb_dir / "modis_mosaics.gdb"
        if not arcpy.Exists(str(gdb_path)):
            arcpy.management.CreateFileGDB(str(gdb_dir), "modis_mosaics")

        md_path = f"{gdb_path}\\{md_name}"
        if arcpy.Exists(md_path):
            arcpy.management.Delete(md_path)

        srs = arcpy.Raster(tifs[0]).spatialReference
        arcpy.management.CreateMosaicDataset(str(gdb_path), md_name, srs)

        # ИСПРАВЛЕНО: явные именованные параметры вместо позиционных
        arcpy.management.AddRastersToMosaicDataset(
            in_mosaic_dataset=md_path,
            raster_type="Raster Dataset",
            input_path=str(year_dir),
            update_cellsize_ranges="UPDATE_CELL_SIZES",
            update_boundary="UPDATE_BOUNDARY",
            filter="*.tif",
        )
        logger.info(messages.INFO_MOSAIC_SAVED.format(md_path))
    except (RuntimeError, arcpy.ExecuteError) as e:
        logger.warning(messages.WARN_MOSAIC_FAILED.format(md_name, str(e)))


def main(args):
    """Главная функция конвертации."""
    logger.info(messages.SEPARATOR)
    logger.info(messages.HEADER_CONVERTER)
    logger.info(messages.SEPARATOR)
    logger.info(messages.INFO_GDAL_VERSION.format(gdal.__version__))

    converter = MODISConverter(max_workers=args.workers)
    raw_dir = DATA_PATHS["raw"]

    if args.product == "all":
        target_products = [
            key
            for key, config in MODIS_PRODUCTS.items()
            if (raw_dir / config["product"]).exists()
        ]
    else:
        target_products = [args.product]

    if not target_products:
        logger.warning(messages.LOG_CONVERSION_WARN.format(raw_dir))
        return

    for product_key in target_products:
        product_code = MODIS_PRODUCTS[product_key]["product"]
        product_raw_dir = raw_dir / product_code

        if args.year:
            target_years = [args.year]
        else:
            target_years = sorted(
                int(d.name)
                for d in product_raw_dir.iterdir()
                if d.is_dir() and d.name.isdigit()
            )

        if not target_years:
            logger.debug(messages.LOG_CONVERSION_WARN.format(product_raw_dir))
            continue

        for year in target_years:
            converter.process_year(product_key, year)
            if args.mosaic:
                build_mosaic_dataset(
                    product_key,
                    year,
                    converter.output_dir / product_key / str(year),
                    DATA_PATHS["gis_output"],
                )

    logger.info(messages.SEPARATOR)
    logger.info(messages.INFO_CONVERSION_DONE)
    logger.info(messages.SEPARATOR)
