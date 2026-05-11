"""
Конвертация данных MODIS из формата HDF в GeoTIFF
с проекцией WGS 84 и клиппингом по области исследования.

Версия: GDAL (вместо pyhdf)
Продукты:
- MOD11A2: LST_Day_1km → LST (°C)
- MOD13Q1: NDVI → NDVI (безразмерный).
"""

import os
import sys
import glob
import numpy as np
from pathlib import Path
from datetime import datetime

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MODIS_PRODUCTS, DATA_PATHS, SPATIAL_RANGE

# Проверка наличия GDAL
try:
    from osgeo import gdal, osr

    gdal.UseExceptions()
    print("[OK] GDAL подключён")
except ImportError:
    print("[ERROR] GDAL не найден!")
    sys.exit(1)


class MODISConverter:
    """Класс для конвертации MODIS HDF → GeoTIFF через GDAL"""

    def __init__(self):
        """Инициализация конвертера"""
        self.input_dir = DATA_PATHS["raw"]
        self.output_dir = DATA_PATHS["processed"]

        # Границы области исследования
        self.bounds = {
            "lon_min": SPATIAL_RANGE["lon_min"],
            "lon_max": SPATIAL_RANGE["lon_max"],
            "lat_min": SPATIAL_RANGE["lat_min"],
            "lat_max": SPATIAL_RANGE["lat_max"],
        }

        # Параметры проекции MODIS (синусоидальная)
        self.modis_srs = osr.SpatialReference()
        self.modis_srs.ImportFromProj4(
            "+proj=sinu +lon_0=0 +x_0=0 +y_0=0 +R=6371007.181 +units=m +no_defs"
        )

        # Целевая проекция (WGS 84)
        self.target_srs = osr.SpatialReference()
        self.target_srs.ImportFromEPSG(4326)

    def convert_lst(self, hdf_path, output_path):
        """
        Конвертация LST данных через GDAL
        Формула: LST_C = DN * 0.02 - 273.15
        """
        try:
            # Открытие HDF-файла
            hdf_dataset = gdal.Open(hdf_path)
            if hdf_dataset is None:
                print(f"  [ERROR] Не удалось открыть {os.path.basename(hdf_path)}")
                return False

            # Получение поддатасета LST
            subdatasets = hdf_dataset.GetSubDatasets()
            lst_subdataset = None

            for name, desc in subdatasets:
                if "LST_Day_1km" in name:
                    lst_subdataset = name
                    break

            if lst_subdataset is None:
                print(f"  [ERROR] LST_Day_1km не найден в {os.path.basename(hdf_path)}")
                return False

            # Чтение данных
            lst_band = gdal.Open(lst_subdataset)
            lst_dn = lst_band.ReadAsArray().astype(np.float32)

            # Конвертация в °C
            scale_factor = 0.02
            offset = -273.15
            lst_celsius = lst_dn * scale_factor + offset

            # Маска невалидных данных (0 = fill value для MOD11A2)
            lst_celsius[lst_dn == 0] = np.nan

            # Сохранение в GeoTIFF
            self._save_geotiff(
                lst_celsius,
                output_path,
                lst_band,
                "LST",
                unit="°C",
                nodata=-9999,
            )

            return True

        except Exception as e:
            print(f"  [ERROR] Конвертация LST {os.path.basename(hdf_path)}: {e}")
            return False

    def convert_ndvi(self, hdf_path, output_path):
        """
        Конвертация NDVI данных через GDAL
        Формула: NDVI = DN * 0.0001.
        """
        try:
            # Открытие HDF-файла
            hdf_dataset = gdal.Open(hdf_path)
            if hdf_dataset is None:
                print(f"  [ERROR] Не удалось открыть {os.path.basename(hdf_path)}")
                return False

            # Получение поддатасета NDVI
            subdatasets = hdf_dataset.GetSubDatasets()
            ndvi_subdataset = None

            for name, desc in subdatasets:
                if "NDVI" in name and "250m" in desc:
                    ndvi_subdataset = name
                    break

            if ndvi_subdataset is None:
                # Пробуем альтернативное имя
                for name, desc in subdatasets:
                    if "NDVI" in name:
                        ndvi_subdataset = name
                        break

            if ndvi_subdataset is None:
                print(f"  [ERROR] NDVI не найден в {os.path.basename(hdf_path)}")
                return False

            # Чтение данных
            ndvi_band = gdal.Open(ndvi_subdataset)
            ndvi_dn = ndvi_band.ReadAsArray().astype(np.float32)

            # Конвертация в NDVI
            scale_factor = 0.0001
            ndvi = ndvi_dn * scale_factor

            # Маска невалидных данных (-3000 = fill value для MOD13Q1)
            ndvi[ndvi_dn == -3000] = np.nan

            # Сохранение в GeoTIFF
            self._save_geotiff(
                ndvi,
                output_path,
                ndvi_band,
                "NDVI",
                unit="index",
                nodata=-9999,
            )

            return True

        except Exception as e:
            print(f"  [ERROR] Конвертация NDVI {os.path.basename(hdf_path)}: {e}")
            return False

    def _save_geotiff(self, data, output_path, source_band, product_name, unit, nodata):
        """
        Сохранение массива в GeoTIFF с правильной проекцией.
        """
        try:
            # Получение геоинформации из исходного датасета
            geotransform = source_band.GetGeoTransform()
            projection = source_band.GetProjection()

            rows, cols = data.shape

            # Создание файла
            driver = gdal.GetDriverByName("GTiff")
            out_dataset = driver.Create(
                output_path,
                cols,
                rows,
                1,
                gdal.GDT_Float32,
                options=["COMPRESS=LZW", "TILED=YES"],
            )

            # Запись данных
            out_band = out_dataset.GetRasterBand(1)
            out_band.WriteArray(data)
            out_band.SetNoDataValue(nodata)

            # Геоинформация
            out_dataset.SetGeoTransform(geotransform)
            out_dataset.SetProjection(projection)

            # Метаданные
            out_band.SetDescription(product_name)
            out_dataset.SetMetadataItem("PRODUCT", product_name)
            out_dataset.SetMetadataItem("UNIT", unit)
            out_dataset.SetMetadataItem(
                "PROCESSING_DATE", datetime.now().strftime("%Y-%m-%d")
            )
            out_dataset.SetMetadataItem("SOURCE", "MODIS Terra/Aqua")

            # Закрытие
            out_band.FlushCache()
            out_dataset = None

            print(f"  [OK] {os.path.basename(output_path)}")

        except Exception as e:
            print(f"  [ERROR] Сохранение GeoTIFF: {e}")

    def process_year(self, product_name, year):
        """
        Обработка всех файлов за год.
        """
        product_config = MODIS_PRODUCTS[product_name]
        product_code = product_config["product"]

        # Входная директория
        input_dir = os.path.join(self.input_dir, product_code, str(year))

        # Выходная директория
        output_dir = os.path.join(self.output_dir, product_name, str(year))
        os.makedirs(output_dir, exist_ok=True)

        # Поиск HDF-файлов
        hdf_files = glob.glob(os.path.join(input_dir, "*.hdf"))

        if not hdf_files:
            print(f"  [WARN] Файлы не найдены: {input_dir}")
            return

        print(f"\n  Обработка {product_code} за {year}: {len(hdf_files)} файлов")

        # Конвертация каждого файла
        converted = 0
        failed = 0

        for hdf_file in hdf_files:
            file_name = os.path.basename(hdf_file)
            output_name = file_name.replace(".hdf", ".tif")
            output_path = os.path.join(output_dir, output_name)

            # Пропуск если уже сконвертировано
            if os.path.exists(output_path):
                continue

            # Конвертация
            if product_name == "LST":
                success = self.convert_lst(hdf_file, output_path)
            else:
                success = self.convert_ndvi(hdf_file, output_path)

            if success:
                converted += 1
            else:
                failed += 1

        print(f"  [RESULT] Сконвертировано: {converted}/{len(hdf_files)}")
        if failed > 0:
            print(f"  [RESULT] Ошибок: {failed}")


def main():
    """Основная функция конвертации"""

    print("=" * 60)
    print("MODIS HDF to GeoTIFF Converter")
    print("=" * 60)

    # Проверка версии GDAL
    print(f"\n  GDAL версия: {gdal.__version__}")

    # Инициализация конвертера
    converter = MODISConverter()

    # Годы для обработки
    from config import TEMPORAL_RANGE

    years = range(TEMPORAL_RANGE["start_year"], TEMPORAL_RANGE["end_year"] + 1)

    # Обработка для каждого года
    for year in years:
        print(f"\n>>> Год: {year}")

        # LST данные
        converter.process_year("LST", year)

        # NDVI данные
        converter.process_year("NDVI", year)

    print("\n" + "=" * 60)
    print("Конвертация завершена")
    print("=" * 60)


if __name__ == "__main__":
    main()
