"""
Валидация и очистка битых HDF файлов MODIS.
Быстрая проверка и параллельное удаление.
"""

import json
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple

from osgeo import gdal, ogr

from config import (
    MODIS_PRODUCTS,
    DATA_PATHS,
    BYTES_TO_MB,
    LOG_DATE_FORMAT,
    TIMESTAMP_FORMAT,
    MIN_HDF_SIZE,
)
from utils.logger import setup_logger
from utils import messages
from utils.provenance import save_run_provenance

gdal.UseExceptions()
ogr.UseExceptions()

from tqdm import tqdm

logger = setup_logger(__name__)


class HDFValidator:
    """Оптимизированный валидатор HDF файлов MODIS."""

    def __init__(self, max_workers: int = 4):
        """Инициализация валидатора."""
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
        self._size_cache = {}
        gdal.SetConfigOption("GDAL_CACHEMAX", "256")
        gdal.SetConfigOption("CPL_DEBUG", "NO")

    def _get_file_size(self, filepath: Path) -> int:
        """Получение размера файла с кэшированием."""
        filepath_str = str(filepath)
        if filepath_str not in self._size_cache:
            self._size_cache[filepath_str] = filepath.stat().st_size
        return self._size_cache[filepath_str]

    def validate_file(
        self, hdf_path: Path, expected_band: str, min_size: int
    ) -> Tuple[bool, str]:
        """Быстрая валидация HDF файла."""
        if not hdf_path.exists():
            return False, messages.ERR_FILE_NOT_FOUND.format(hdf_path.name)

        file_size = self._get_file_size(hdf_path)
        if file_size < min_size:
            self.stats["too_small"] += 1
            return False, messages.WARN_FILE_TOO_SMALL.format(file_size * BYTES_TO_MB)

        try:
            dataset = gdal.Open(str(hdf_path))
            if dataset is None:
                self.stats["read_error"] += 1
                return False, messages.VALIDATION_GDAL_OPEN_FAIL

            subdatasets = dataset.GetSubDatasets()
            if not subdatasets:
                self.stats["missing_dataset"] += 1
                dataset = None
                return False, messages.ERR_NO_SUBDATASETS

            found_datasets = [sd[0].split(":")[-1] for sd in subdatasets]
            band_found = expected_band in found_datasets or any(
                expected_band in sd_name for sd_name in found_datasets
            )
            if not band_found:
                self.stats["missing_dataset"] += 1
                dataset = None
                return False, messages.ERR_MISSING_DATASETS.format([expected_band])

            dataset = None
            return True, "OK"

        except RuntimeError as e:
            error_msg = str(e).lower()
            self.stats["read_error"] += 1
            if "not recognized" in error_msg:
                return False, messages.VALIDATION_FORMAT_NOT_RECOGNIZED
            return False, messages.VALIDATION_ERROR_PREFIX.format(str(e)[:100])

    def validate_directory(
        self,
        directory: Path,
        expected_band: str,
        min_size: int,
        year: int,
        show_progress: bool = True,
    ) -> Dict:
        """Валидация всех файлов в директории."""
        hdf_files = sorted(directory.glob("*.hdf"))
        if not hdf_files:
            return {"total": 0, "valid": 0, "corrupted": 0, "files": []}

        dir_stats = {
            "total": len(hdf_files),
            "valid": 0,
            "corrupted": 0,
            "files": [],
        }
        iterator = (
            tqdm(
                hdf_files,
                desc=messages.PROGRESS_VALIDATION.format(year),
                ncols=100,
            )
            if show_progress
            else hdf_files
        )

        for hdf_path in iterator:
            self.stats["total_checked"] += 1
            is_valid, error_msg = self.validate_file(hdf_path, expected_band, min_size)

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
                        "year": year,
                        "error": error_msg,
                        "size_mb": self._get_file_size(hdf_path) * BYTES_TO_MB,
                        "path": str(hdf_path),
                    }
                )
                dir_stats["files"].append(str(hdf_path))

        return dir_stats

    def delete_files_parallel(
        self,
        file_paths: List[str],
        show_progress: bool = True,
    ) -> int:
        """Параллельное удаление файлов."""
        if not file_paths:
            return 0

        deleted = 0
        iterator = (
            tqdm(file_paths, desc=messages.PROGRESS_DELETE, ncols=100)
            if show_progress
            else file_paths
        )

        def delete_single(filepath: str) -> Tuple[str, bool]:
            try:
                Path(filepath).unlink()
                return filepath, True
            except (OSError, PermissionError) as e:
                logger.warning(messages.ERR_DELETE_FILE.format(filepath, str(e)))
                return filepath, False

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(delete_single, fp): fp for fp in iterator}
            for future in as_completed(futures):
                if future.result()[1]:
                    deleted += 1

        self.stats["deleted"] = deleted
        return deleted

    def generate_report(self, output_path: Path) -> Dict:
        """Генерация отчёта о валидации."""
        report = {
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

    def generate_redownload_list(self, output_path: Path) -> Dict:
        """Генерация списка файлов для перескачивания."""
        if not self.corrupted_files:
            return {"files": [], "total": 0}

        from collections import defaultdict

        grouped = defaultdict(list)
        for file_info in self.corrupted_files:
            grouped[f"year_{file_info['year']}"].append(file_info["file"])

        redownload_info = {
            "timestamp": datetime.now().isoformat(),
            "total_files": len(self.corrupted_files),
            "by_year": {k: len(v) for k, v in grouped.items()},
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

    save_run_provenance(
        "02_validate",
        {
            "product": args.product,
            "year": args.year,
            "dry_run": args.dry_run,
            "workers": args.workers,
        },
    )

    products_to_check = (
        list(MODIS_PRODUCTS.keys()) if args.product == "all" else [args.product]
    )
    show_progress = not args.quiet if hasattr(args, "quiet") else True

    skipped_dirs = 0
    processed_dirs = 0

    for product_key in products_to_check:
        product_config = MODIS_PRODUCTS[product_key]
        product_code = product_config["product"]
        expected_band = product_config["band"]
        min_size = MIN_HDF_SIZE

        product_raw_dir = DATA_PATHS["raw"] / product_code
        if not product_raw_dir.exists():
            skipped_dirs += 1
            logger.debug(messages.LOG_VALIDATION_SKIP.format(product_raw_dir))
            continue

        # Сканируем только существующие годы.
        if args.year:
            target_years = [args.year]
        else:
            target_years = sorted(
                int(d.name)
                for d in product_raw_dir.iterdir()
                if d.is_dir() and d.name.isdigit()
            )

        for year in target_years:
            directory = product_raw_dir / str(year)
            if not directory.exists():
                skipped_dirs += 1
                logger.debug(messages.LOG_VALIDATION_SKIP.format(directory))
                continue

            processed_dirs += 1
            logger.info(messages.SEPARATOR)
            logger.info(messages.LOG_VALIDATION_START.format(product_code, year))
            logger.info(messages.SEPARATOR)
            validator.validate_directory(
                directory,
                expected_band,
                min_size,
                year,
                show_progress=show_progress,
            )

    if skipped_dirs > 0:
        logger.info(messages.INFO_SKIPPED_DIRS.format(skipped_dirs, processed_dirs))

    if processed_dirs == 0:
        logger.warning(messages.WARN_NO_DATA_DIRS)
        return

    report_dir = DATA_PATHS["tables"]
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)
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
    logger.info(messages.INFO_FINAL_STATS)
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
