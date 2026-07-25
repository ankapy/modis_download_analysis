"""
Валидация и очистка битых HDF файлов MODIS.
Быстрая проверка и параллельное удаление.
"""

import json
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple, Any

from osgeo import gdal, ogr
from config import (
    TEMPORAL_RANGE,
    MODIS_PRODUCTS,
    DATA_PATHS,
    MIN_FILE_SIZE,
    LOG_DATE_FORMAT,
    DATE_FORMAT_FILE,
)
from utils.logger import setup_logger
from utils import messages

gdal.UseExceptions()
ogr.UseExceptions()

try:
    from tqdm import tqdm

    USE_TQDM = True
except ImportError:
    USE_TQDM = False

logger = setup_logger(__name__)


class HDFValidator:
    """Оптимизированный валидатор HDF файлов MODIS."""

    EXPECTED_DATASETS = {"MOD11A2": ["LST_Day_1km"], "MOD13Q1": ["NDVI"]}

    def __init__(self, max_workers: int = 4):
        """Инициализация валидатора."""
        self.max_workers = max_workers
        self.stats: Dict[str, int] = {
            "total_checked": 0,
            "valid": 0,
            "corrupted": 0,
            "too_small": 0,
            "read_error": 0,
            "missing_dataset": 0,
        }
        self.corrupted_files: List[Dict[str, Any]] = []
        self.valid_files: List[str] = []
        self._size_cache: Dict[str, int] = {}
        gdal.SetConfigOption("GDAL_CACHEMAX", "256")
        gdal.SetConfigOption("CPL_DEBUG", "NO")

    def _get_file_size(self, filepath: Path) -> int:
        """Получение размера файла с кэшированием."""
        filepath_str = str(filepath)
        if filepath_str not in self._size_cache:
            self._size_cache[filepath_str] = filepath.stat().st_size
        return self._size_cache[filepath_str]

    def validate_file(self, hdf_path: Path, product_code: str) -> Tuple[bool, str]:
        """Быстрая валидация HDF файла."""
        if not hdf_path.exists():
            return False, messages.ERR_FILE_NOT_FOUND.format(hdf_path)

        file_size = self._get_file_size(hdf_path)
        min_size = MIN_FILE_SIZE.get(product_code, 500_000)

        if file_size < min_size:
            self.stats["too_small"] += 1
            return False, messages.WARN_FILE_TOO_SMALL.format(file_size / 1024 / 1024)

        try:
            dataset = gdal.Open(str(hdf_path))
            if dataset is None:
                self.stats["read_error"] += 1
                return False, messages.ERR_OPEN_FILE.format(hdf_path.name)

            subdatasets = dataset.GetSubDatasets()
            if not subdatasets:
                self.stats["missing_dataset"] += 1
                dataset = None
                return False, messages.ERR_NO_SUBDATASETS

            expected = self.EXPECTED_DATASETS.get(product_code, [])
            found_datasets = [sd[0].split(":")[-1] for sd in subdatasets]
            has_expected = any(exp in " ".join(found_datasets) for exp in expected)

            if not has_expected:
                self.stats["missing_dataset"] += 1
                dataset = None
                return False, messages.ERR_MISSING_DATASETS.format(expected)

            dataset = None
            return True, "OK"

        except RuntimeError as e:
            error_msg = str(e).lower()
            self.stats["read_error"] += 1
            if "not recognized" in error_msg:
                return False, "Формат файла не распознан (повреждён)"
            return False, messages.ERR_READ_ERROR.format(str(e)[:100])

    def validate_directory(
        self, directory: Path, product_code: str, year: int, show_progress: bool = True
    ) -> Dict[str, Any]:
        """Валидация всех файлов в директории."""
        hdf_files = sorted(directory.glob("*.hdf"))
        if not hdf_files:
            return {"total": 0, "valid": 0, "corrupted": 0, "files": []}

        dir_stats: Dict[str, Any] = {
            "total": len(hdf_files),
            "valid": 0,
            "corrupted": 0,
            "files": [],
        }
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
        """Параллельное удаление файлов."""
        if not file_paths:
            return 0

        deleted = 0
        iterator = (
            tqdm(file_paths, desc="Удаление", ncols=100)
            if (show_progress and USE_TQDM)
            else file_paths
        )

        def delete_single(filepath: str) -> Tuple[str, bool]:
            try:
                Path(filepath).unlink()
                return filepath, True
            except (OSError, PermissionError) as e:
                logger.warning(messages.ERR_DELETE_FAILED.format(filepath, str(e)))
                return filepath, False

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(delete_single, fp): fp for fp in iterator}
            for future in as_completed(futures):
                if future.result()[1]:
                    deleted += 1

        self.stats["deleted"] = deleted
        return deleted

    def generate_report(self, output_path: Path) -> Dict[str, Any]:
        """Генерация отчёта о валидации."""
        report: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "statistics": self.stats,
            "corrupted_files": self.corrupted_files,
            "valid_count": len(self.valid_files),
            "corrupted_count": len(self.corrupted_files),
            "recommendations": [],
        }
        if self.stats["too_small"] > 0:
            report["recommendations"].append(
                messages.VALIDATION_TOO_SMALL.format(self.stats["too_small"])
            )
        if self.stats["read_error"] > 0:
            report["recommendations"].append(
                messages.VALIDATION_READ_ERROR.format(self.stats["read_error"])
            )

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return report

    def generate_redownload_list(self, output_path: Path) -> Dict[str, Any]:
        """Генерация списка файлов для перескачивания."""
        if not self.corrupted_files:
            return {"files": [], "total": 0}

        from collections import defaultdict

        grouped: Dict[str, List[str]] = defaultdict(list)
        for file_info in self.corrupted_files:
            grouped[f"{file_info['product']}/{file_info['year']}"].append(
                file_info["file"]
            )

        redownload_info: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "total_files": len(self.corrupted_files),
            "by_product_year": {k: len(v) for k, v in grouped.items()},
            "files": self.corrupted_files,
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(redownload_info, f, ensure_ascii=False, indent=2)
        return redownload_info


def main(args):
    """Главная функция валидации."""
    logger.info(messages.SEPARATOR)
    logger.info(messages.HEADER_VALIDATOR)
    logger.info(messages.SEPARATOR)
    logger.info(
        messages.STATUS_START_TIME.format(datetime.now().strftime(LOG_DATE_FORMAT))
    )
    logger.info(messages.STATUS_THREADS.format(args.workers))

    mode = (
        messages.STATUS_MODE_CHECK
        if args.dry_run
        else messages.STATUS_MODE_CHECK_DELETE
    )
    logger.info(mode)

    validator = HDFValidator(max_workers=args.workers)
    products = ["LST", "NDVI"] if args.product == "all" else [args.product]
    years = (
        [args.year]
        if args.year
        else range(TEMPORAL_RANGE["start_year"], TEMPORAL_RANGE["end_year"] + 1)
    )
    show_progress = not args.quiet if hasattr(args, "quiet") else True

    for product in products:
        product_code = MODIS_PRODUCTS[product]["product"]
        for year in years:
            directory = DATA_PATHS["raw"] / product_code / str(year)
            if not directory.exists():
                logger.warning(messages.LOG_VALIDATION_SKIP.format(directory))
                continue

            logger.info(messages.SEPARATOR)
            logger.info(messages.LOG_VALIDATION_START.format(product_code, year))
            logger.info(messages.SEPARATOR)
            validator.validate_directory(
                directory, product_code, year, show_progress=show_progress
            )

    report_dir = DATA_PATHS["tables"]
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime(DATE_FORMAT_FILE)
    report_path = report_dir / f"validation_report_{timestamp}.json"
    redownload_path = report_dir / f"redownload_list_{timestamp}.json"

    validator.generate_report(report_path)
    validator.generate_redownload_list(redownload_path)

    logger.info(messages.LOG_REPORT_SAVED.format(report_path))
    logger.info(messages.LOG_REDOWNLOAD_SAVED.format(redownload_path))

    if not args.dry_run and validator.corrupted_files:
        logger.info(messages.SEPARATOR)
        logger.info(messages.LOG_DELETE_START)
        logger.info(messages.SEPARATOR)
        file_paths = [f["path"] for f in validator.corrupted_files]
        deleted = validator.delete_files_parallel(
            file_paths, show_progress=show_progress
        )
        logger.info(messages.LOG_DELETE_OK.format(deleted))

    logger.info(messages.SEPARATOR)
    logger.info("ИТОГОВАЯ СТАТИСТИКА")
    logger.info(messages.SEPARATOR)
    logger.info(
        messages.VALIDATION_STATS_CHECKED.format(validator.stats["total_checked"])
    )
    logger.info(messages.VALIDATION_STATS_VALID.format(validator.stats["valid"]))
    logger.info(
        messages.VALIDATION_STATS_CORRUPTED.format(validator.stats["corrupted"])
    )

    if not args.dry_run:
        logger.info(
            messages.VALIDATION_STATS_DELETED.format(validator.stats.get("deleted", 0))
        )

    logger.info(
        messages.VALIDATION_STATS_TOO_SMALL.format(validator.stats["too_small"])
    )
    logger.info(
        messages.VALIDATION_STATS_READ_ERROR.format(validator.stats["read_error"])
    )
    logger.info(
        messages.VALIDATION_STATS_MISSING_DATASETS.format(
            validator.stats["missing_dataset"]
        )
    )
    logger.info(messages.SEPARATOR)

    if validator.stats["corrupted"] > 0:
        logger.info(messages.NEXT_STEPS)
        logger.info(messages.NEXT_STEP_1.format(report_path))
        logger.info(messages.NEXT_STEP_2)
        logger.info(messages.NEXT_STEP_3)
