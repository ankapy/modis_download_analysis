"""
CLI интерфейс для пайплайна MODIS.
Единая точка входа с подкомандами для каждого этапа.
"""

import sys
import argparse
import importlib
from pathlib import Path

from utils import messages


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
    parser.add_argument("--products", type=str, help="Продукты через запятую: LST,NDVI")


def _add_validate_parser(subparsers):
    """Добавление парсера для команды 02_validate."""
    parser = subparsers.add_parser(
        "02_validate",
        help="Валидация HDF файлов",
        description="Проверка целостности HDF и удаление битых.",
    )
    parser.add_argument(
        "--product",
        choices=["LST", "NDVI", "all"],
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
    parser = subparsers.add_parser(
        "03_convert",
        help="Конвертация HDF -> GeoTIFF",
        description="Преобразование HDF в GeoTIFF с пересчётом значений.",
    )
    parser.add_argument(
        "--product",
        choices=["LST", "NDVI", "all"],
        default="all",
        help="Продукт для конвертации",
    )
    parser.add_argument("--year", type=int, help="Только указанный год")


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
    parser = subparsers.add_parser(
        "05_analyze",
        help="Анализ и визуализация",
        description="Построение графиков и экспорт таблиц.",
    )
    parser.add_argument(
        "--product",
        choices=["LST", "NDVI", "all"],
        default="all",
        help="Продукт для анализа",
    )
    parser.add_argument("--output-dir", type=Path, help="Директория для графиков")


def _dispatch(args):
    """Диспетчеризация команды на соответствующий модуль."""
    command = args.command
    module_map = {
        "01_download": "core.01_downloader",
        "02_validate": "core.02_validator",
        "03_convert": "core.03_converter",
        "04_stats": "core.04_zonal_stats",
        "05_analyze": "core.05_analyzer",
    }

    if command not in module_map:
        raise ValueError(messages.ERR_INVALID_INPUT.format(command))

    module = importlib.import_module(module_map[command])
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

    if len(sys.argv) < 2:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        _dispatch(args)
    except KeyboardInterrupt:
        print("\n[INTERRUPT] Прервано пользователем.")
        sys.exit(0)
    except (ValueError, RuntimeError, FileNotFoundError) as e:
        print(f"[ERROR] {str(e)}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
