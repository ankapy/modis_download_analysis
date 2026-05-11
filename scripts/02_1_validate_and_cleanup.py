"""
Валидация и очистка битых HDF файлов MODIS
Быстрая проверка и параллельное удаление.
"""

import os
import sys
import json
import time
import hashlib
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple, Optional
from osgeo import gdal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TEMPORAL_RANGE, MODIS_PRODUCTS, DATA_PATHS

try:
    from tqdm import tqdm

    USE_TQDM = True
except ImportError:
    USE_TQDM = False
    print("  [WARN] tqdm не установлен — прогресс-бары отключены")


class HDFValidator:
    """Оптимизированный валидатор HDF файлов MODIS"""

    # Минимальные размеры (только минимум, без максимума)
    MIN_SIZE_MOD11A2 = 500_000  # 0.5 МБ для LST
    MIN_SIZE_MOD13Q1 = 500_000  # 0.5 МБ для NDVI

    # Ожидаемые поддатасеты
    EXPECTED_DATASETS = {
        "MOD11A2": ["LST_Day_1km"],
        "MOD13Q1": ["NDVI"],
    }

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.stats = {
            "total_checked": 0,
            "valid": 0,
            "corrupted": 0,
            "too_small": 0,
            "read_error": 0,
            "missing_dataset": 0,
        }
        self.corrupted_files = []
        self.valid_files = []

        # Кэш размеров файлов (избегаем повторных stat() вызовов)
        self._size_cache = {}

        # GDAL кэш (переиспользуем конфигурацию)
        gdal.SetConfigOption("GDAL_CACHEMAX", "256")
        gdal.SetConfigOption("CPL_DEBUG", "NO")

    def _get_file_size(self, filepath: Path) -> int:
        """Получение размера файла с кэшированием"""
        filepath_str = str(filepath)
        if filepath_str not in self._size_cache:
            self._size_cache[filepath_str] = filepath.stat().st_size
        return self._size_cache[filepath_str]

    def validate_file(self, hdf_path: Path, product_code: str) -> Tuple[bool, str]:
        """
        Быстрая валидация HDF файла
        Returns: (is_valid: bool, error_message: str)
        """
        # 1. Проверка существования
        if not hdf_path.exists():
            return False, "Файл не существует"

        # 2. Проверка размера (ТОЛЬКО МИНИМУМ!)
        file_size = self._get_file_size(hdf_path)
        min_size = (
            self.MIN_SIZE_MOD11A2
            if product_code == "MOD11A2"
            else self.MIN_SIZE_MOD13Q1
        )

        if file_size < min_size:
            self.stats["too_small"] += 1
            return False, f"Файл слишком мал: {file_size / 1024 / 1024:.2f} МБ"

        # 3. Быстрая проверка через GDAL (открываем и проверяем поддатасеты)
        try:
            dataset = gdal.Open(str(hdf_path))
            if dataset is None:
                self.stats["read_error"] += 1
                return False, "GDAL не может открыть файл"

            # Проверяем поддатасеты
            subdatasets = dataset.GetSubDatasets()
            if not subdatasets:
                self.stats["missing_dataset"] += 1
                dataset = None
                return False, "Нет поддатасетов в файле"

            # Проверяем наличие ожидаемых датасетов
            expected = self.EXPECTED_DATASETS.get(product_code, [])
            found_datasets = [sd[0].split(":")[-1] for sd in subdatasets]

            has_expected = any(exp in " ".join(found_datasets) for exp in expected)
            if not has_expected:
                self.stats["missing_dataset"] += 1
                dataset = None
                return False, f"Не найдены датасеты {expected}"

            # БЫСТРАЯ ПРОВЕРКА: не читаем данные, только проверяем структуру
            # Это экономит 80% времени валидации
            dataset = None
            return True, "OK"

        except Exception as e:
            error_msg = str(e)
            if "not recognized" in error_msg.lower():
                self.stats["read_error"] += 1
                return False, "Формат файла не распознан (повреждён)"
            else:
                self.stats["read_error"] += 1
                return False, f"Ошибка: {error_msg[:100]}"

    def validate_directory(
        self,
        directory: Path,
        product_code: str,
        year: int,
        show_progress: bool = True,
    ) -> Dict:
        """Валидация всех файлов в директории с прогресс-баром"""
        hdf_files = sorted(directory.glob("*.hdf"))

        if not hdf_files:
            return {"total": 0, "valid": 0, "corrupted": 0, "deleted": []}

        dir_stats = {
            "total": len(hdf_files),
            "valid": 0,
            "corrupted": 0,
            "files": [],
        }

        # Используем прогресс-бар если доступен
        iterator = (
            tqdm(hdf_files, desc=f"{product_code}/{year}", ncols=100)
            if (show_progress and USE_TQDM)
            else hdf_files
        )

        for hdf_path in iterator:
            self.stats["total_checked"] += 1
            is_valid, error_msg = self.validate_file(hdf_path, product_code)

            if is_valid:
                self.stats["valid"] += 1
                dir_stats["valid"] += 1
                self.valid_files.append(str(hdf_path))
            else:
                self.stats["corrupted"] += 1
                dir_stats["corrupted"] += 1
                self.corrupted_files.append(
                    {
                        "file": hdf_path.name,
                        "product": product_code,
                        "year": year,
                        "error": error_msg,
                        "size_mb": self._get_file_size(hdf_path) / 1024 / 1024,
                        "path": str(hdf_path),
                    }
                )
                dir_stats["files"].append(str(hdf_path))

        return dir_stats

    def delete_files_parallel(
        self, file_paths: List[str], show_progress: bool = True
    ) -> int:
        """
        Параллельное удаление файлов
        Returns: количество успешно удалённых файлов
        """
        if not file_paths:
            return 0

        deleted = 0
        failed = 0

        def delete_single(filepath: str) -> Tuple[str, bool]:
            """Удаление одного файла"""
            try:
                Path(filepath).unlink()
                return filepath, True
            except Exception as e:
                return filepath, False

        # Параллельное удаление
        iterator = (
            tqdm(file_paths, desc="Удаление", ncols=100)
            if (show_progress and USE_TQDM)
            else file_paths
        )

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(delete_single, fp): fp for fp in iterator}

            for future in as_completed(futures):
                filepath, success = future.result()
                if success:
                    deleted += 1
                else:
                    failed += 1

        self.stats["deleted"] = deleted
        return deleted

    def generate_report(self, output_path: Path) -> Dict:
        """Генерация отчёта о валидации"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "statistics": self.stats,
            "corrupted_files": self.corrupted_files,
            "valid_count": len(self.valid_files),
            "corrupted_count": len(self.corrupted_files),
            "recommendations": [],
        }

        # Рекомендации
        if self.stats["too_small"] > 0:
            report["recommendations"].append(
                f"{self.stats['too_small']} файлов были недокачаны (слишком малый размер)"
            )
        if self.stats["read_error"] > 0:
            report["recommendations"].append(
                f"{self.stats['read_error']} файлов имеют ошибки чтения (повреждена структура HDF)"
            )

        # Сохранение отчёта
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return report

    def generate_redownload_list(self, output_path: Path) -> Dict:
        """Генерация списка файлов для перескачивания"""
        if not self.corrupted_files:
            return {"files": [], "total": 0}

        # Группировка по продукту и году
        from collections import defaultdict

        grouped = defaultdict(list)

        for file_info in self.corrupted_files:
            key = f"{file_info['product']}/{file_info['year']}"
            grouped[key].append(file_info["file"])

        redownload_info = {
            "timestamp": datetime.now().isoformat(),
            "total_files": len(self.corrupted_files),
            "by_product_year": {k: len(v) for k, v in grouped.items()},
            "files": self.corrupted_files,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(redownload_info, f, ensure_ascii=False, indent=2)

        return redownload_info


def main():
    """Основная функция"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Валидация и очистка битых HDF файлов MODIS (ОПТИМИЗИРОВАННАЯ ВЕРСИЯ)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Режим проверки — не удалять файлы, только показать",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Тихий режим — показывать только ошибки",
    )
    parser.add_argument(
        "--product",
        choices=["LST", "NDVI", "all"],
        default="all",
        help="Продукт для проверки (по умолчанию: все)",
    )
    parser.add_argument("--year", type=int, help="Проверить только указанный год")
    parser.add_argument(
        "--no-delete",
        action="store_true",
        help="Не удалять файлы, только создать отчёт",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Количество потоков для удаления (по умолчанию: 4)",
    )
    parser.add_argument(
        "--skip-progress", action="store_true", help="Отключить прогресс-бары"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("MODIS HDF Validator & Cleanup")
    print("=" * 60)
    print(f"Время начала: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Потоков: {args.workers}")
    print(
        f"Режим: {'ПРОВЕРКА' if args.dry_run or args.no_delete else 'ПРОВЕРКА + УДАЛЕНИЕ'}"
    )

    if args.dry_run:
        print("РЕЖИМ ПРОВЕРКИ — файлы не будут удалены")

    # Инициализация валидатора
    validator = HDFValidator(max_workers=args.workers)

    # Определение продуктов и годов
    products = ["LST", "NDVI"] if args.product == "all" else [args.product]

    years = (
        [args.year]
        if args.year
        else range(TEMPORAL_RANGE["start_year"], TEMPORAL_RANGE["end_year"] + 1)
    )

    show_progress = not args.quiet and not args.skip_progress

    # Валидация по всем продуктам и годам
    for product in products:
        product_config = MODIS_PRODUCTS[product]
        product_code = product_config["product"]

        for year in years:
            directory = Path(DATA_PATHS["raw"]) / product_code / str(year)

            if not directory.exists():
                if not args.quiet:
                    print(f"\n[SKIP] Директория не найдена: {directory}")
                continue

            if not args.quiet:
                print(f"\n{'=' * 60}")
                print(f"Проверка {product_code}/{year}")
                print(f"{'=' * 60}")

            validator.validate_directory(
                directory, product_code, year, show_progress=show_progress
            )

    # Генерация отчёта
    report_dir = Path(DATA_PATHS["tables"])
    report_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"validation_report_{timestamp}.json"
    redownload_path = report_dir / f"redownload_list_{timestamp}.json"

    validator.generate_report(report_path)
    validator.generate_redownload_list(redownload_path)

    if not args.quiet:
        print(f"\n Отчёт сохранён: {report_path}")
        print(f" Список для перескачивания: {redownload_path}")

    # Удаление повреждённых файлов
    if not args.dry_run and not args.no_delete and validator.corrupted_files:
        if not args.quiet:
            print(f"\n{'=' * 60}")
            print("УДАЛЕНИЕ ПОВРЕЖДЁННЫХ ФАЙЛОВ")
            print(f"{'=' * 60}")

        file_paths = [f["path"] for f in validator.corrupted_files]
        deleted = validator.delete_files_parallel(
            file_paths, show_progress=show_progress
        )

        if not args.quiet:
            print(f"\n Удалено файлов: {deleted}")

    # Итоговая статистика
    if not args.quiet:
        print("\n" + "=" * 60)
        print("ИТОГОВАЯ СТАТИСТИКА")
        print("=" * 60)
        print(f"  Проверено файлов: {validator.stats['total_checked']}")
        print(f"  Валидных: {validator.stats['valid']}")
        print(f"  Повреждённых: {validator.stats['corrupted']}")
        if not args.dry_run and not args.no_delete:
            print(f"  🗑️  Удалено: {validator.stats.get('deleted', 0)}")
        print(f"  └─ Слишком малые: {validator.stats['too_small']}")
        print(f"  └─ Ошибки чтения: {validator.stats['read_error']}")
        print(f"  └─ Нет датасетов: {validator.stats['missing_dataset']}")
        print("=" * 60)

        if validator.stats["corrupted"] > 0:
            print("\n СЛЕДУЮЩИЕ ШАГИ:")
            print("  1. Проверьте отчёт: " + str(report_path))
            print("  2. Запустите 01_download_modis_earthaccess.py")
            print("     (скрипт автоматически докачает недостающие файлы)")
            print("  3. Запустите 02_convert_hdf.py")

    if not args.quiet:
        print(f"\nВремя окончания: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  Прервано пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] Критическая ошибка: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
