"""
Скачивание данных MODIS через earthaccess.
Стабильная версия с пакетной загрузкой и паузами.
"""

import time
import traceback
from pathlib import Path
from datetime import datetime

from config import MODIS_PRODUCTS, DATA_PATHS
from utils.logger import setup_logger
from utils.geo_utils import calculate_bbox_from_gpkg, load_zones, check_modis_coverage
from utils.config_loader import (
    parse_year_range,
    parse_months,
    prompt_temporal_range,
    prompt_products,
    prompt_zones_path,
)
from utils import messages

try:
    import earthaccess
except ImportError:
    raise ImportError(messages.ERR_EARTHACCESS_NOT_FOUND)


logger = setup_logger(__name__)


def count_hdf_files(output_dir: Path) -> int:
    """Подсчёт HDF-файлов в директории."""
    if not output_dir.exists():
        return 0
    return len(list(output_dir.glob("*.hdf")))


def authenticate():
    """Авторизация в NASA Earthdata."""
    logger.info(messages.LOG_AUTH_START)
    try:
        earthaccess.login(strategy="netrc", persist=True)
        logger.info(messages.LOG_AUTH_OK)
    except Exception as e:
        logger.warning(messages.LOG_AUTH_WARN.format(e))
        earthaccess.login(strategy="environment", persist=True)


def download_granules(
    results_to_download: list, output_dir: Path, batch_size: int = 15
):
    """
    Скачивание гранул с паузами и повторными попытками.
    """
    pause_batch = 5
    pause_granule = 2
    max_retries = 3

    downloaded = 0
    failed = 0
    batch_num = 0

    for i in range(0, len(results_to_download), batch_size):
        batch = results_to_download[i : i + batch_size]
        batch_num += 1

        try:
            logger.info(
                messages.LOG_BATCH_START.format(
                    batch_num, i + 1, min(i + batch_size, len(results_to_download))
                )
            )

            for granule_idx, granule in enumerate(batch, 1):
                success = False
                for attempt in range(max_retries):
                    try:
                        result = earthaccess.download([granule], str(output_dir))
                        if result and len(result) > 0:
                            downloaded += 1
                            logger.info(
                                messages.LOG_DOWNLOAD_OK.format(
                                    downloaded, len(results_to_download)
                                )
                            )
                            success = True
                            break
                        else:
                            logger.warning(
                                messages.LOG_DOWNLOAD_WARN.format(attempt + 1)
                            )
                    except Exception as e:
                        error_msg = str(e)[:80]
                        logger.error(
                            messages.LOG_DOWNLOAD_ERROR.format(
                                attempt + 1, max_retries, error_msg
                            )
                        )
                        if attempt < max_retries - 1:
                            wait_time = (attempt + 1) * 5
                            logger.info(messages.LOG_DOWNLOAD_PAUSE.format(wait_time))
                            time.sleep(wait_time)

                if not success:
                    failed += 1
                    logger.warning(messages.LOG_DOWNLOAD_FAIL.format(max_retries))

                if granule_idx < len(batch):
                    time.sleep(pause_granule)

            if batch_num < (len(results_to_download) // batch_size) + 1:
                logger.info(messages.LOG_BATCH_PAUSE.format(pause_batch))
                time.sleep(pause_batch)

        except KeyboardInterrupt:
            logger.warning(messages.LOG_INTERRUPT.format(batch_num))
            break
        except Exception as e:
            logger.error(messages.LOG_BATCH_ERROR.format(batch_num, str(e)[:80]))
            failed += len(batch)
            time.sleep(10)

    return downloaded, failed


def process_product_year(
    product_key: str, year: int, bbox: tuple, temporal_range: dict
):
    """Обработка одного продукта за один год."""
    config = MODIS_PRODUCTS[product_key]
    product_code = config["product"]

    output_dir = DATA_PATHS["raw"] / product_code / str(year)
    output_dir.mkdir(parents=True, exist_ok=True)

    existing_hdf = count_hdf_files(output_dir)
    expected_granules = 120 if product_code == "MOD11A2" else 77

    if existing_hdf >= expected_granules * 0.95:
        logger.info(
            messages.INFO_EXISTING_FILES.format(existing_hdf, expected_granules)
        )
        return 0, 0

    months = temporal_range["months"]
    start_date = f"{year}-{min(months):02d}-01"
    end_date = f"{year}-{max(months):02d}-28"

    logger.info(messages.INFO_PERIOD.format(start_date, end_date))
    logger.info(messages.INFO_DIRECTORY.format(output_dir))
    logger.info(messages.INFO_EXISTING_FILES.format(existing_hdf, expected_granules))

    try:
        logger.info(messages.LOG_SEARCH_START)
        results = earthaccess.search_data(
            short_name=product_code,
            temporal=(start_date, end_date),
            bounding_box=bbox,
            count=2000,
        )
    except Exception as e:
        logger.error(f"Ошибка поиска: {e}")
        return 0, 1

    if not results:
        logger.warning(messages.LOG_GRANULES_NOT_FOUND)
        return 0, 0

    logger.info(messages.LOG_GRANULES_FOUND.format(len(results)))

    existing_files = {f.name for f in output_dir.glob("*.hdf")}
    results_to_download = []
    for granule in results:
        granule_id = granule.get("meta", {}).get("native-id", "")
        expected_filename = granule_id.split(":")[-1] + ".hdf"
        if expected_filename not in existing_files:
            results_to_download.append(granule)

    if not results_to_download:
        logger.info(messages.INFO_SKIP_ALL_DOWNLOADED)
        return 0, 0

    logger.info(
        messages.LOG_DOWNLOAD_START.format(len(results_to_download), len(results))
    )

    downloaded, failed = download_granules(results_to_download, output_dir)

    logger.info(messages.LOG_RESULT.format(product_code, year, downloaded, failed))

    return downloaded, failed


def main(args):
    """Главная функция скачивания."""
    logger.info(messages.SEPARATOR)
    logger.info(messages.HEADER_DOWNLOADER)
    logger.info(messages.SEPARATOR)
    logger.info(
        messages.STATUS_START_TIME.format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )

    try:
        # Определение пути к зонам.
        zones_path = args.zones if args.zones else prompt_zones_path()
        if not zones_path.exists():
            raise FileNotFoundError(messages.ERR_GPKG_NOT_FOUND.format(zones_path))

        # Расчёт пространственного диапазона.
        bbox = calculate_bbox_from_gpkg(zones_path)
        logger.info(f"Bounding box: {bbox}")

        if not check_modis_coverage(bbox):
            raise ValueError(messages.WARN_NO_COVERAGE)

        # Временной диапазон.
        if args.start_year and args.end_year:
            years = list(range(args.start_year, args.end_year + 1))
            months = parse_months(args.months) if args.months else list(range(1, 13))
            temporal_range = {
                "start_year": args.start_year,
                "end_year": args.end_year,
                "months": months,
            }
        else:
            temporal_range = prompt_temporal_range()
            years = list(
                range(temporal_range["start_year"], temporal_range["end_year"] + 1)
            )

        # Выбор продуктов.
        if args.products:
            products = [p.strip() for p in args.products.split(",")]
        else:
            products = prompt_products()

        logger.info(messages.MSG_ZONES_PATH.format(zones_path))
        logger.info(messages.MSG_PRODUCTS.format(products))

        authenticate()

        total_success = 0
        total_failed = 0
        total_skipped = 0

        for year_idx, year in enumerate(years, 1):
            logger.info(messages.SEPARATOR)
            logger.info(f">>> ГОД {year} ({year_idx}/{len(years)})")
            logger.info(messages.SEPARATOR)

            for product_idx, product_key in enumerate(products, 1):
                config = MODIS_PRODUCTS[product_key]
                logger.info(
                    f"[{product_idx}/{len(products)}] {config['product']} v{config['version']}"
                )

                downloaded, failed = process_product_year(
                    product_key, year, bbox, temporal_range
                )

                if downloaded > 0:
                    total_success += 1
                if failed > 0:
                    total_failed += 1
                if downloaded == 0 and failed == 0:
                    total_skipped += 1

                time.sleep(5)

            time.sleep(10)

        logger.info(messages.SEPARATOR)
        logger.info("ИТОГИ ЗАГРУЗКИ")
        logger.info(messages.SEPARATOR)
        logger.info(messages.STATUS_SUCCESS.format(total_success))
        logger.info(messages.STATUS_SKIPPED.format(total_skipped))
        logger.info(messages.STATUS_FAILED.format(total_failed))
        logger.info(
            messages.STATUS_END_TIME.format(
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        )
        logger.info(messages.SEPARATOR)

    except KeyboardInterrupt:
        logger.warning("\n[INTERRUPT] Программа прервана пользователем")
        logger.info("[INFO] Запустите снова для продолжения")
    except Exception as e:
        logger.error(messages.ERR_CRITICAL.format(e))
        traceback.print_exc()
