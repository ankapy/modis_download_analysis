"""
CLI интерфейс для пайплайна MODIS.
Единая точка входа с подкомандами для каждого этапа.
"""

import sys
import argparse
import importlib
from pathlib import Path

from utils import messages
from config import MODIS_PRODUCTS, ZONES_GPKG


def _add_download_parser(subparsers):
    """Добавление парсера для команды 01_download."""
    parser = subparsers.add_parser(
        "01_download",
        help="Скачивание данных MODIS",
        description="Загрузка HDF-гранул через earthaccess.",
    )
    parser.add_argument("--zones", type=Path, help="Путь к GeoPackage с зонами")
    parser.add_argument("--start-year", type=int, help="Начальный год (пример: 2015)")
    parser.add_argument("--end-year", type=int, help="Конечный год (пример: 2025)")
    parser.add_argument("--months", type=str, help="Месяцы: 1-12 или 5,6,7,8,9")
    parser.add_argument(
        "--products",
        type=str,
        help=f"Продукты через запятую: {','.join(list(MODIS_PRODUCTS.keys())[:2])}",
    )


def _add_validate_parser(subparsers):
    """Добавление парсера для команды 02_validate."""
    product_choices = list(MODIS_PRODUCTS.keys()) + ["all"]
    parser = subparsers.add_parser(
        "02_validate",
        help="Валидация HDF файлов",
        description="Проверка целостности HDF и удаление битых.",
    )
    parser.add_argument(
        "--product",
        choices=product_choices,
        default="all",
        help="Продукт для проверки",
    )
    parser.add_argument("--year", type=int, help="Проверить только указанный год")
    parser.add_argument(
        "--dry-run", action="store_true", help="Только проверка, без удаления"
    )
    parser.add_argument(
        "--workers", type=int, default=8, help="Количество потоков для удаления"
    )
    parser.add_argument("--quiet", action="store_true", help="Тихий режим")


def _add_convert_parser(subparsers):
    """Добавление парсера для команды 03_convert."""
    product_choices = list(MODIS_PRODUCTS.keys()) + ["all"]
    parser = subparsers.add_parser(
        "03_convert",
        help="Конвертация HDF -> GeoTIFF",
        description="Преобразование HDF в GeoTIFF с пересчётом значений.",
    )
    parser.add_argument(
        "--product",
        choices=product_choices,
        default="all",
        help="Продукт для конвертации",
    )
    parser.add_argument("--year", type=int, help="Только указанный год")
    parser.add_argument("--workers", type=int, default=4, help="Количество потоков")
    parser.add_argument(
        "--mosaic", action="store_true", help="Сборка Mosaic Dataset (arcpy)"
    )
    parser.add_argument(
        "--cog",
        action="store_true",
        help="Запись в формате Cloud Optimized GeoTIFF",
    )
    parser.add_argument(
        "--reproject",
        type=int,
        default=None,
        help="Целевая EPSG для репроекции (пример: 4326)",
    )


def _add_stats_parser(subparsers):
    """Добавление парсера для команды 04_stats."""
    parser = subparsers.add_parser(
        "04_stats",
        help="Зональная статистика",
        description="Расчёт статистики по полигонам зон.",
    )
    parser.add_argument(
        "--zones", type=Path, required=True, help="Путь к GeoPackage с зонами"
    )
    parser.add_argument("--workers", type=int, default=4, help="Количество потоков")
    parser.add_argument(
        "--test", action="store_true", help="Тестовый режим (1 файл на продукт)"
    )


def _add_analyze_parser(subparsers):
    """Добавление парсера для команды 05_analyze."""
    product_choices = list(MODIS_PRODUCTS.keys()) + ["all"]
    parser = subparsers.add_parser(
        "05_analyze",
        help="Анализ и визуализация",
        description="Построение графиков и экспорт таблиц.",
    )
    parser.add_argument(
        "--product",
        choices=product_choices,
        default="all",
        help="Продукт для анализа",
    )
    parser.add_argument("--output-dir", type=Path, help="Директория для графиков")
    parser.add_argument(
        "--excel",
        action="store_true",
        help="Экспорт всех таблиц в один .xlsx (листы: flat, monthly, summary, trends)",
    )


def _add_run_all_parser(subparsers):
    """Добавление парсера для команды run-all."""
    parser = subparsers.add_parser(
        "run-all",
        help="Полный пайплайн: 01 -> 05",
        description="Последовательный запуск всех этапов.",
    )
    parser.add_argument(
        "--zones", type=Path, required=True, help="Путь к GeoPackage с зонами"
    )
    parser.add_argument("--start-year", type=int, required=True, help="Начальный год")
    parser.add_argument("--end-year", type=int, required=True, help="Конечный год")
    parser.add_argument("--months", type=str, help="Месяцы: 1-12 или 5,6,7,8,9")
    parser.add_argument("--products", type=str, help="Продукты через запятую")
    parser.add_argument("--workers", type=int, default=4, help="Количество потоков")
    parser.add_argument(
        "--mosaic", action="store_true", help="Сборка Mosaic Dataset (arcpy)"
    )
    parser.add_argument(
        "--cog",
        action="store_true",
        help="Запись в формате Cloud Optimized GeoTIFF",
    )
    parser.add_argument(
        "--reproject",
        type=int,
        default=None,
        help="Целевая EPSG для репроекции (пример: 4326)",
    )
    parser.add_argument(
        "--excel",
        action="store_true",
        help="Экспорт всех таблиц в один .xlsx",
    )


def _add_selftest_parser(subparsers):
    """Добавление парсера для команды selftest."""
    subparsers.add_parser(
        "selftest",
        help="Самодиагностика окружения",
        description="Проверка импортов, GDAL, авторизации и наличия зон.",
    )


def _selftest():
    """Быстрая проверка окружения и конфигурации."""
    print(messages.INFO_SELFTEST_START)

    # 1. Проверка обязательных Python-зависимостей.
    for module_name in (
        "numpy",
        "pandas",
        "matplotlib",
        "scipy",
        "earthaccess",
        "tqdm",
    ):
        try:
            importlib.import_module(module_name)
            print(messages.SELFTEST_OK.format(module_name))
        except ImportError as e:
            print(messages.SELFTEST_FAIL.format(f"{module_name}: {str(e)[:80]}"))

    # 2. Опциональная зависимость для Excel-экспорта.
    try:
        importlib.import_module("openpyxl")
        print(messages.SELFTEST_OK.format("openpyxl"))
    except ImportError:
        print(messages.SELFTEST_WARN.format("openpyxl (нужен только для --excel)"))

    # 3. Проверка GDAL.
    try:
        from osgeo import gdal

        print(messages.SELFTEST_OK.format(f"GDAL {gdal.__version__}"))
    except ImportError as e:
        print(messages.SELFTEST_FAIL.format(f"GDAL: {str(e)[:80]}"))

    # 4. Конфигурация продуктов (validate_config() уже вызван при импорте config.py).
    try:
        import config  # noqa: F401

        print(messages.SELFTEST_OK.format("config (MODIS_PRODUCTS)"))
    except ValueError as e:
        print(messages.SELFTEST_FAIL.format(f"config: {str(e)[:80]}"))

    # 5. Авторизация в NASA Earthdata.
    try:
        import earthaccess

        earthaccess.login(strategy="netrc", persist=True)
        print(messages.SELFTEST_OK.format("earthaccess (netrc)"))
    except Exception as e:
        print(messages.SELFTEST_WARN.format(f"earthaccess: {str(e)[:80]}"))

    # 6. Наличие файла зон.
    if ZONES_GPKG.exists():
        print(messages.SELFTEST_OK.format(str(ZONES_GPKG)))
    else:
        print(messages.SELFTEST_WARN.format(f"zones.gpkg не найден: {ZONES_GPKG}"))

    print(messages.INFO_SELFTEST_DONE)


def _run_all(args):
    """Последовательный запуск всех этапов пайплайна."""
    from argparse import Namespace

    stage_args = {
        "01_downloader": Namespace(
            zones=args.zones,
            start_year=args.start_year,
            end_year=args.end_year,
            months=args.months,
            products=args.products,
        ),
        "02_validator": Namespace(
            product="all",
            year=None,
            dry_run=False,
            workers=args.workers,
            quiet=True,
        ),
        "03_converter": Namespace(
            product="all",
            year=None,
            workers=args.workers,
            mosaic=args.mosaic,
            cog=args.cog,
            reproject=args.reproject,
        ),
        "04_zonal_stats": Namespace(zones=args.zones, workers=args.workers, test=False),
        "05_analyzer": Namespace(product="all", output_dir=None, excel=args.excel),
    }

    print(messages.INFO_RUN_ALL_START)
    for stage, s_args in stage_args.items():
        print(messages.INFO_RUN_ALL_STAGE.format(stage))
        module = importlib.import_module(f"core.{stage}")
        module.main(s_args)


def _dispatch(args):
    """Диспетчеризация команды на соответствующий модуль."""
    module_map = {
        "01_download": "core.01_downloader",
        "02_validate": "core.02_validator",
        "03_convert": "core.03_converter",
        "04_stats": "core.04_zonal_stats",
        "05_analyze": "core.05_analyzer",
    }

    if args.command not in module_map:
        raise ValueError(messages.ERR_INVALID_INPUT.format(args.command))

    module = importlib.import_module(module_map[args.command])
    module.main(args)


def main():
    """Главная точка входа CLI."""
    parser = argparse.ArgumentParser(
        prog="modis_pipeline",
        description=messages.HEADER_PIPELINE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Доступные команды")

    _add_download_parser(subparsers)
    _add_validate_parser(subparsers)
    _add_convert_parser(subparsers)
    _add_stats_parser(subparsers)
    _add_analyze_parser(subparsers)
    _add_run_all_parser(subparsers)
    _add_selftest_parser(subparsers)

    if len(sys.argv) < 2:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        if args.command == "run-all":
            _run_all(args)
        elif args.command == "selftest":
            _selftest()
        else:
            _dispatch(args)
    except KeyboardInterrupt:
        print(f"\n{messages.INFO_INTERRUPT}")
        sys.exit(0)
    except (ValueError, RuntimeError, FileNotFoundError) as e:
        print(messages.ERR_CRITICAL.format(str(e)))
        sys.exit(1)


if __name__ == "__main__":
    main()
