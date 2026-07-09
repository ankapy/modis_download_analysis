"""
Конвертация данных MODIS из HDF в GeoTIFF.
Продукты: LST (°C), NDVI (безразмерный).
"""

import numpy as np
from pathlib import Path
from datetime import datetime

from osgeo import gdal, osr, ogr
from config import MODIS_PRODUCTS, DATA_PATHS, TEMPORAL_RANGE
from utils.logger import setup_logger
from utils import messages

gdal.UseExceptions()
ogr.UseExceptions()


logger = setup_logger(__name__)


class MODISConverter:
    """Класс для конвертации MODIS HDF -> GeoTIFF через GDAL."""

    def __init__(self):
        """Инициализация конвертера."""
        self.input_dir = DATA_PATHS["raw"]
        self.output_dir = DATA_PATHS["processed"]

        self.modis_srs = osr.SpatialReference()
        self.modis_srs.ImportFromProj4(
            "+proj=sinu +lon_0=0 +x_0=0 +y_0=0 +R=6371007.181 +units=m +no_defs"
        )

        self.target_srs = osr.SpatialReference()
        self.target_srs.ImportFromEPSG(4326)

    def convert_lst(self, hdf_path: Path, output_path: Path) -> bool:
        """Конвертация LST данных."""
        try:
            hdf_dataset = gdal.Open(str(hdf_path))
            if hdf_dataset is None:
                logger.error(messages.ERR_OPEN_FILE.format(hdf_path.name))
                return False

            subdatasets = hdf_dataset.GetSubDatasets()
            lst_subdataset = None
            for name, desc in subdatasets:
                if "LST_Day_1km" in name:
                    lst_subdataset = name
                    break

            if lst_subdataset is None:
                logger.error(messages.ERR_MISSING_DATASETS.format(["LST_Day_1km"]))
                return False

            lst_band = gdal.Open(lst_subdataset)
            lst_dn = lst_band.ReadAsArray().astype(np.float32)

            scale_factor = 0.02
            offset = -273.15
            lst_celsius = lst_dn * scale_factor + offset
            lst_celsius[lst_dn == 0] = np.nan

            self._save_geotiff(
                lst_celsius, output_path, lst_band, "LST", "°C", nodata=-9999
            )
            return True

        except Exception as e:
            logger.error(f"Конвертация LST {hdf_path.name}: {e}")
            return False

    def convert_ndvi(self, hdf_path: Path, output_path: Path) -> bool:
        """Конвертация NDVI данных."""
        try:
            hdf_dataset = gdal.Open(str(hdf_path))
            if hdf_dataset is None:
                logger.error(messages.ERR_OPEN_FILE.format(hdf_path.name))
                return False

            subdatasets = hdf_dataset.GetSubDatasets()
            ndvi_subdataset = None
            for name, desc in subdatasets:
                if "NDVI" in name and "250m" in desc:
                    ndvi_subdataset = name
                    break

            if ndvi_subdataset is None:
                for name, desc in subdatasets:
                    if "NDVI" in name:
                        ndvi_subdataset = name
                        break

            if ndvi_subdataset is None:
                logger.error(messages.ERR_MISSING_DATASETS.format(["NDVI"]))
                return False

            ndvi_band = gdal.Open(ndvi_subdataset)
            ndvi_dn = ndvi_band.ReadAsArray().astype(np.float32)

            scale_factor = 0.0001
            ndvi = ndvi_dn * scale_factor
            ndvi[ndvi_dn == -3000] = np.nan

            self._save_geotiff(
                ndvi, output_path, ndvi_band, "NDVI", "index", nodata=-9999
            )
            return True

        except Exception as e:
            logger.error(f"Конвертация NDVI {hdf_path.name}: {e}")
            return False

    def _save_geotiff(
        self,
        data: np.ndarray,
        output_path: Path,
        source_band,
        product_name: str,
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

            out_band.SetDescription(product_name)
            out_dataset.SetMetadataItem("PRODUCT", product_name)
            out_dataset.SetMetadataItem("UNIT", unit)
            out_dataset.SetMetadataItem(
                "PROCESSING_DATE", datetime.now().strftime("%Y-%m-%d")
            )
            out_dataset.SetMetadataItem("SOURCE", "MODIS Terra/Aqua")

            out_band.FlushCache()
            out_dataset = None

            logger.info(messages.LOG_CONVERSION_FILE_OK.format(output_path.name))

        except Exception as e:
            logger.error(messages.ERR_SAVE_GEOTIFF.format(e))

    def process_year(self, product_name: str, year: int):
        """Обработка всех файлов за год."""
        product_config = MODIS_PRODUCTS[product_name]
        product_code = product_config["product"]

        input_dir = self.input_dir / product_code / str(year)
        output_dir = self.output_dir / product_name / str(year)
        output_dir.mkdir(parents=True, exist_ok=True)

        hdf_files = list(input_dir.glob("*.hdf"))
        if not hdf_files:
            logger.warning(messages.LOG_CONVERSION_WARN.format(input_dir))
            return

        logger.info(
            messages.LOG_CONVERSION_START.format(product_code, year, len(hdf_files))
        )

        converted = 0
        skipped = 0
        failed = 0

        for hdf_file in hdf_files:
            output_name = hdf_file.name.replace(".hdf", ".tif")
            output_path = output_dir / output_name

            if output_path.exists():
                skipped += 1
                continue

            if product_name == "LST":
                success = self.convert_lst(hdf_file, output_path)
            else:
                success = self.convert_ndvi(hdf_file, output_path)

            if success:
                converted += 1
            else:
                failed += 1

        logger.info(f"Сконвертировано: {converted}/{len(hdf_files)}")
        if skipped > 0:
            logger.info(f"Пропущено (уже существует): {skipped}")
        if failed > 0:
            logger.info(messages.LOG_CONVERSION_ERROR.format(failed))


def main(args):
    """Главная функция конвертации."""
    logger.info(messages.SEPARATOR)
    logger.info(messages.HEADER_CONVERTER)
    logger.info(messages.SEPARATOR)
    logger.info(f"GDAL версия: {gdal.__version__}")

    converter = MODISConverter()

    products = ["LST", "NDVI"] if args.product == "all" else [args.product]
    years = (
        [args.year]
        if args.year
        else range(TEMPORAL_RANGE["start_year"], TEMPORAL_RANGE["end_year"] + 1)
    )

    for year in years:
        logger.info(f"\n>>> Год: {year}")
        for product in products:
            converter.process_year(product, year)

    logger.info(messages.SEPARATOR)
    logger.info("Конвертация завершена")
    logger.info(messages.SEPARATOR)
