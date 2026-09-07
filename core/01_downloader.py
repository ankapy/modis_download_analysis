"""Скачивание данных MODIS через earthaccess."""

import calendar
import sys
import time
from datetime import datetime
from pathlib import Path

import earthaccess

from config import (
    DATA_PATHS,
    DOWNLOAD_BATCH_SIZE,
    DOWNLOAD_MAX_RETRIES,
    DOWNLOAD_PAUSE_BATCH,
    DOWNLOAD_PAUSE_GRANULE,
    DOWNLOAD_PAUSE_PRODUCT,
    DOWNLOAD_PAUSE_YEAR,
    EXPECTED_GRANULES,
    LOG_DATE_FORMAT,
    MODIS_PRODUCTS,
    SEARCH_MAX_RESULTS,
)

from utils import messages
from utils.config_loader import (
    parse_months,
    parse_products,
    prompt_products,
    prompt_temporal_range,
    prompt_zones_path,
)
from utils.geo_utils import calculate_bbox_from_gpkg, check_modis_coverage
from utils.logger import setup_logger
from utils.provenance import save_run_provenance

logger = setup_logger(__name__)

AUTH_STRATEGIES = ('netrc', 'environment')


def count_hdf_files(output_dir: Path) -> int:
    """Подсчёт HDF-файлов в директории (без загрузки списка в память)."""
    if not output_dir.exists():
        return 0
    return sum(1 for _ in output_dir.glob('*.hdf'))


def authenticate():
    """Авторизация в NASA Earthdata с каскадным перебором стратегий."""
    logger.info(messages.LOG_AUTH_START)
    for strategy in AUTH_STRATEGIES:
        try:
            earthaccess.login(strategy=strategy, persist=True)
            logger.info(messages.LOG_AUTH_OK)
            return
        except Exception as e:
            logger.debug(
                messages.LOG_AUTH_STRATEGY_FAIL.format(strategy, str(e)),
            )
    logger.error(messages.ERR_AUTH_FAILED)
    sys.exit(1)


def _download_one_granule(
    granule,
    output_dir: Path,
    attempt_idx: int,
    total: int,
) -> tuple:
    """Одна попытка скачивания гранулы с ретраями.

    Возвращает кортеж (downloaded_inc, failed_inc),
    где каждое значение 0 или 1. Вызывается из внешнего цикла по батчам.
    """
    for attempt in range(DOWNLOAD_MAX_RETRIES):
        try:
            result = earthaccess.download([granule], str(output_dir))
            if result and len(result) > 0:
                logger.info(
                    messages.LOG_DOWNLOAD_OK.format(attempt_idx + 1, total)
                )
                return (1, 0)
            logger.warning(messages.LOG_DOWNLOAD_WARN.format(attempt + 1))
        except (ConnectionError, RuntimeError) as e:
            error_msg = str(e)[:80]
            logger.error(
                messages.LOG_DOWNLOAD_ERROR.format(
                    attempt + 1, DOWNLOAD_MAX_RETRIES, error_msg
                )
            )
            if attempt < DOWNLOAD_MAX_RETRIES - 1:
                wait_time = (attempt + 1) * 5
                logger.info(messages.LOG_DOWNLOAD_PAUSE.format(wait_time))
                time.sleep(wait_time)
        except Exception as e:
            logger.error(
                messages.LOG_DOWNLOAD_ERROR.format(
                    attempt + 1, DOWNLOAD_MAX_RETRIES, str(e)[:80]
                )
            )
            if attempt < DOWNLOAD_MAX_RETRIES - 1:
                time.sleep(5)

    logger.warning(messages.LOG_DOWNLOAD_FAIL.format(DOWNLOAD_MAX_RETRIES))
    return (0, 1)


def download_granules(
    results_to_download: list,
    output_dir: Path,
    batch_size: int = DOWNLOAD_BATCH_SIZE,
):
    """Скачивание гранул батчами с паузами и повторными попытками."""
    downloaded = 0
    failed = 0
    total_batches = (len(results_to_download) + batch_size - 1) // batch_size

    for i in range(0, len(results_to_download), batch_size):
        batch = results_to_download[i : i + batch_size]
        batch_num = i // batch_size + 1
        try:
            logger.info(
                messages.LOG_BATCH_START.format(
                    batch_num,
                    i + 1,
                    min(i + batch_size, len(results_to_download)),
                )
            )
            for granule_idx, granule in enumerate(batch):
                attempt_idx = i + granule_idx
                d_inc, f_inc = _download_one_granule(
                    granule, output_dir, attempt_idx, len(results_to_download)
                )
                downloaded += d_inc
                failed += f_inc
                if granule_idx < len(batch) - 1:
                    time.sleep(DOWNLOAD_PAUSE_GRANULE)

            if batch_num < total_batches:
                logger.info(
                    messages.LOG_BATCH_PAUSE.format(DOWNLOAD_PAUSE_BATCH)
                )
                time.sleep(DOWNLOAD_PAUSE_BATCH)
        except KeyboardInterrupt:
            logger.warning(messages.LOG_INTERRUPT.format(batch_num))
            break
        except Exception as e:
            logger.error(
                messages.LOG_BATCH_ERROR.format(batch_num, str(e)[:80])
            )
            failed += len(batch)
            time.sleep(10)

    return downloaded, failed


def process_product_year(
    product_key: str,
    year: int,
    bbox: tuple,
    temporal_range: dict,
):
    """Обработка одного продукта за один год."""
    config = MODIS_PRODUCTS[product_key]
    product_code = str(config['product'])
    output_dir = DATA_PATHS['raw'] / product_code / str(year)
    output_dir.mkdir(parents=True, exist_ok=True)

    existing_hdf = count_hdf_files(output_dir)
    expected_granules = EXPECTED_GRANULES.get(product_code, 0)

    if expected_granules > 0 and existing_hdf >= expected_granules * 0.95:
        logger.info(
            messages.INFO_EXISTING_FILES.format(
                existing_hdf,
                expected_granules,
            ),
        )

    months = temporal_range['months']
    min_month = min(months)
    max_month = max(months)

    _, last_day = calendar.monthrange(year, max_month)

    start_date = f'{year}-{min_month:02d}-01'
    end_date = f'{year}-{max_month:02d}-{last_day}'

    logger.info(messages.INFO_PERIOD.format(start_date, end_date))
    logger.info(messages.INFO_DIRECTORY.format(output_dir))

    if expected_granules > 0:
        logger.info(
            messages.INFO_EXISTING_FILES.format(
                existing_hdf,
                expected_granules,
            ),
        )

    try:
        logger.info(messages.LOG_SEARCH_START)
        results = earthaccess.search_data(
            short_name=product_code,
            temporal=(start_date, end_date),
            bounding_box=bbox,
            count=SEARCH_MAX_RESULTS,
        )
    except Exception as e:
        logger.error(messages.ERR_SEARCH_FAILED.format(str(e)))
        return 0, 1

    if not results:
        logger.warning(messages.LOG_GRANULES_NOT_FOUND)
        return 0, 0

    logger.info(messages.LOG_GRANULES_FOUND.format(len(results)))

    existing_files = {f.name for f in output_dir.glob('*.hdf')}
    results_to_download = []

    for granule in results:
        native_id = granule.get('meta', {}).get('native-id', '')
        if native_id:
            expected_filename = native_id.split(':')[-1] + '.hdf'
            if expected_filename not in existing_files:
                results_to_download.append(granule)

    if not results_to_download:
        logger.info(messages.INFO_SKIP_ALL_DOWNLOADED)
        return 0, 0

    logger.info(
        messages.LOG_DOWNLOAD_START.format(
            len(results_to_download),
            len(results),
        ),
    )
    downloaded, failed = download_granules(results_to_download, output_dir)
    logger.info(
        messages.LOG_RESULT.format(product_code, year, downloaded, failed),
    )

    return downloaded, failed


def main(args):
    """Главная функция скачивания."""
    logger.info(messages.SEPARATOR)
    logger.info(messages.HEADER_DOWNLOADER)
    logger.info(messages.SEPARATOR)
    logger.info(
        messages.STATUS_START_TIME.format(
            datetime.now().strftime(LOG_DATE_FORMAT),
        ),
    )
    logger.info(messages.INFO_CTRL_C)

    try:
        zones_path = args.zones if args.zones else prompt_zones_path()
        if not zones_path.exists():
            raise FileNotFoundError(
                messages.ERR_GPKG_NOT_FOUND.format(zones_path),
            )

        bbox = calculate_bbox_from_gpkg(zones_path)
        logger.info(messages.INFO_BBOX.format(bbox))

        if not check_modis_coverage(bbox):
            raise ValueError(messages.WARN_NO_COVERAGE)

        authenticate()

        if args.start_year and args.end_year:
            months = (
                parse_months(args.months)
                if args.months
                else list(range(1, 13))
            )
            temporal_range = {
                'start_year': args.start_year,
                'end_year': args.end_year,
                'months': months,
            }
            years = list(range(args.start_year, args.end_year + 1))
        else:
            temporal_range = prompt_temporal_range()
            years = list(
                range(
                    temporal_range['start_year'],
                    temporal_range['end_year'] + 1,
                ),
            )

        products = (
            parse_products(args.products)
            if args.products
            else prompt_products()
        )

        logger.info(messages.MSG_ZONES_PATH.format(zones_path))
        logger.info(messages.MSG_PRODUCTS.format(products))

        total_success = 0
        total_failed = 0
        total_skipped = 0

        save_run_provenance(
            '01_download',
            {
                'zones': zones_path,
                'bbox': bbox,
                'years': years,
                'months': temporal_range['months'],
                'products': products,
            },
        )

        for product_idx, product_key in enumerate(products, 1):
            config = MODIS_PRODUCTS[product_key]
            logger.info(messages.SEPARATOR)
            logger.info(
                messages.INFO_PRODUCT_HEADER.format(
                    product_idx,
                    len(products),
                    config['product'],
                    config['version'],
                ),
            )
            logger.info(messages.SEPARATOR)

            for year_idx, year in enumerate(years, 1):
                logger.info(
                    messages.INFO_YEAR_HEADER.format(
                        year,
                        year_idx,
                        len(years),
                    ),
                )

                downloaded, failed = process_product_year(
                    product_key,
                    year,
                    bbox,
                    temporal_range,
                )

                if downloaded > 0:
                    total_success += 1
                if failed > 0:
                    total_failed += 1
                if downloaded == 0 and failed == 0:
                    total_skipped += 1

                time.sleep(DOWNLOAD_PAUSE_YEAR)
            time.sleep(DOWNLOAD_PAUSE_PRODUCT)

        logger.info(messages.SEPARATOR)
        logger.info(messages.INFO_SUMMARY_HEADER)
        logger.info(messages.SEPARATOR)
        logger.info(messages.STATUS_SUCCESS.format(total_success))
        logger.info(messages.STATUS_SKIPPED.format(total_skipped))
        logger.info(messages.STATUS_FAILED.format(total_failed))
        logger.info(
            messages.STATUS_END_TIME.format(
                datetime.now().strftime(LOG_DATE_FORMAT),
            ),
        )
        logger.info(messages.SEPARATOR)

    except KeyboardInterrupt:
        logger.warning(f'\n{messages.INFO_INTERRUPT}')
        logger.info(messages.INFO_CONTINUE)
        sys.exit(0)
    except (FileNotFoundError, ValueError, RuntimeError, SystemExit) as e:
        logger.error(messages.ERR_CRITICAL.format(str(e)))
        sys.exit(1)
    except Exception as e:
        logger.error(messages.ERR_CRITICAL.format(str(e)))
        sys.exit(1)
