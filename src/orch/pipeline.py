# -*- coding: utf-8 -*-
"""Оркестратор этапов пайплайна: последовательный запуск, проверка зависимостей, dry-run."""

import os
import shutil
import earthaccess
import signal

from pathlib import Path
from src import logger
from src import messages as M
from src.config import validate_config, PROJECT_ROOT, DATA_PATHS, ConfigError
from src.constants import ZONES_GPKG_FILENAME, ZONE_FIELD_NAME
from src.core.preprocessor import load_zones, compute_bounding_box
from src.core.product_processor import get_processor, ProductNotFoundError
from src.core.stat_calculator import calculate_zonal_stats
from src.core.plotter import (
    plot_seasonal_curve,
    plot_latitudinal_gradient,
    plot_interannual_trend,
)
from src.core.exporter import save_csv_atomic, save_excel_atomic
from src.utils.raster_io import open_raster

stop_requested = False
STOP_REQUESTED = False


class PipelineError(Exception):
    """Исключение для ошибок оркестрации."""

    pass


def run_pipeline(stages, config, dry_run=False):
    """Последовательное выполнение этапов. Возвращает True при успешном завершении."""
    try:
        validate_config()
    except ConfigError as e:
        raise PipelineError(M.ERR_CONFIG_INVALID.format(reason=str(e)))

    if dry_run:
        _run_dry_run(config)
        return True

    for stage in stages:
        logger.info(M.MSG_STAGE_START.format(stage=stage))
        _check_dependencies(stage, config)
        _execute_stage(stage, config)
        logger.info(M.MSG_STAGE_END.format(stage=stage))
    return True


def _run_dry_run(config):
    """Проверка путей, прав доступа и места на диске без тяжёлых вычислений."""
    logger.info(M.MSG_DRY_RUN_START)
    for path in DATA_PATHS.values():
        if not os.path.exists(path):
            logger.info(M.MSG_DRY_RUN_CREATE_DIR.format(path=path))
        if os.path.exists(path) and not os.access(path, os.W_OK):
            raise PipelineError(M.ERR_DIR_PERMISSION.format(path=path))

    total, used, free = shutil.disk_usage(str(PROJECT_ROOT))
    free_mb = free // (1024 * 1024)
    if free_mb < 1024:
        logger.warning(M.WARN_LOW_DISK_SPACE.format(free_mb=free_mb))
    logger.info(M.MSG_DRY_RUN_COMPLETE)


def _check_dependencies(stage, config):
    """Проверка наличия входных директорий перед запуском этапа."""
    deps = {
        "convert": DATA_PATHS["raw"],
        "stats": DATA_PATHS["processed"],
        "plot": DATA_PATHS["tables"],
        "export": DATA_PATHS["tables"],
    }
    req_path = deps.get(stage)
    if req_path and not os.path.exists(req_path):
        logger.warning(M.WARN_MISSING_DEPS.format(stage=stage, path=req_path))


def _execute_stage(stage, config):
    """Диспетчер вызовов бизнес-модулей."""
    stage_executors = {
        "download": _exec_download,
        "convert": _exec_convert,
        "stats": _exec_stats,
        "plot": _exec_plot,
        "export": _exec_export,
    }
    executor = stage_executors.get(stage)
    if executor:
        executor(config)
    else:
        logger.info(M.MSG_STAGE_SKIPPED.format(stage=stage))


def _signal_handler(signum, frame):
    """Обработчик сигналов прерывания"""
    global STOP_REQUESTED
    logger.warning("Получен сигнал прерывания. Завершение после текущей гранулы...")
    STOP_REQUESTED = True


def _exec_download(config):
    """Загрузка гранул MODIS с поддержкой Ctrl+C"""

    # Регистрация обработчиков сигналов
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    zones_path = DATA_PATHS["gis"] / ZONES_GPKG_FILENAME
    if not zones_path.exists():
        raise PipelineError(M.ERR_FILE_NOT_FOUND.format(path=zones_path))

    zones = load_zones(zones_path, ZONE_FIELD_NAME)
    bbox = compute_bounding_box(zones)
    logger.info(M.MSG_ZONES_LOADED.format(count=len(zones), path=zones_path))
    logger.info(M.MSG_BBOX_COMPUTED.format(bbox=bbox))

    import earthaccess

    earthaccess.login(strategy="netrc", persist=True)

    years = range(config.get("start_year", 2015), config.get("end_year", 2025) + 1)
    products = ["MOD11A2", "MOD13Q1"]
    total_downloaded = 0

    for year in years:
        if STOP_REQUESTED:
            logger.info("Остановка по запросу пользователя")
            break
        for product_code in products:
            if STOP_REQUESTED:
                break
            output_dir = DATA_PATHS["raw"] / product_code / str(year)
            output_dir.mkdir(parents=True, exist_ok=True)
            start_date = f"{year}-05-01"
            end_date = f"{year}-09-30"

            try:
                results = earthaccess.search_data(
                    short_name=product_code,
                    temporal=(start_date, end_date),
                    bounding_box=(bbox[0], bbox[1], bbox[2], bbox[3]),
                    count=2000,
                )
            except Exception as e:
                logger.warning(
                    M.ERR_DOWNLOAD_FAILED.format(filename=product_code, error=e)
                )
                continue

            if not results:
                continue

            existing = {f.name for f in output_dir.glob("*.hdf")}
            to_download = []
            for granule in results:
                if STOP_REQUESTED:
                    break
                native_id = granule.get("meta", {}).get("native-id", "")
                filename = native_id.split(":")[-1] + ".hdf"
                if filename not in existing:
                    to_download.append(granule)

            if not to_download or STOP_REQUESTED:
                continue

            logger.info(f"Загрузка {len(to_download)} гранул {product_code}/{year}...")

            # Скачивание по одной грануле с проверкой флага
            for i, granule in enumerate(to_download, 1):
                if STOP_REQUESTED:
                    logger.info(f"Остановка после {i-1} гранул")
                    break
                try:
                    result = earthaccess.download([granule], str(output_dir), threads=1)
                    if result:
                        total_downloaded += 1
                        if i % 5 == 0:
                            logger.info(f"Скачано {i}/{len(to_download)} гранул...")
                except KeyboardInterrupt:
                    _signal_handler(signal.SIGINT, None)
                    break
                except Exception as e:
                    logger.warning(f"Ошибка гранулы: {e}")
                    continue

    logger.info(M.MSG_DOWNLOAD_COMPLETE.format(downloaded=total_downloaded, failed=0))
    # Сброс обработчиков
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)


def _exec_convert(config):
    """Конвертация HDF в GeoTIFF через стратегию обработки."""
    raw_dir = DATA_PATHS["raw"]
    proc_dir = DATA_PATHS["processed"]
    converted_count = 0

    for product_dir in raw_dir.iterdir():
        if not product_dir.is_dir():
            continue
        product_code = product_dir.name
        try:
            processor = get_processor(product_code)
        except ProductNotFoundError:
            logger.warning(M.ERR_UNKNOWN_PRODUCT.format(product=product_code))
            continue

        for year_dir in product_dir.iterdir():
            if not year_dir.is_dir():
                continue
            for hdf_file in year_dir.glob("*.hdf"):
                output_path = (
                    proc_dir
                    / product_code
                    / hdf_file.stem
                    / hdf_file.name.replace(".hdf", ".tif")
                )
                output_path.parent.mkdir(parents=True, exist_ok=True)

                if output_path.exists() and open_raster(output_path) is not None:
                    logger.info(M.MSG_CONVERT_SKIP.format(filename=output_path.name))
                    continue

                success = processor(
                    str(hdf_file), str(output_path), {"product": product_code}
                )
                if success:
                    converted_count += 1

    logger.info(
        M.MSG_CONVERT_START.format(
            product="ALL", year="ALL", total_files=converted_count
        )
    )


def _exec_stats(config):
    """Расчёт зональной статистики с проверкой пересечений."""
    zones_path = DATA_PATHS["gis"] / ZONES_GPKG_FILENAME
    zones = load_zones(zones_path, ZONE_FIELD_NAME)
    proc_dir = DATA_PATHS["processed"]
    tables_dir = DATA_PATHS["tables"]
    all_results = []

    for product_dir in proc_dir.iterdir():
        if not product_dir.is_dir():
            continue
        product_code = product_dir.name
        config["product"] = product_code

        for year_dir in product_dir.iterdir():
            if not year_dir.is_dir():
                continue
            for raster_file in year_dir.glob("*.tif"):
                records = calculate_zonal_stats(str(raster_file), zones, config)
                all_results.extend(records)

    if all_results:
        output_csv = tables_dir / "zonal_stats_raw.csv"
        fields = list(all_results[0].keys())
        save_csv_atomic(all_results, str(output_csv), fields)
        logger.info(M.MSG_EXPORT_COMPLETE.format(count=len(all_results)))
    else:
        logger.warning(M.WARN_MISSING_DEPS.format(stage="stats", path=proc_dir))


def _exec_plot(config):
    """Визуализация результатов."""
    tables_dir = DATA_PATHS["tables"]
    figures_dir = DATA_PATHS["figures"]
    input_csv = tables_dir / "zonal_stats_raw.csv"

    if not input_csv.exists():
        logger.warning(M.ERR_FILE_NOT_FOUND.format(path=input_csv))
        return

    data_df = pd.read_csv(input_csv)
    for product in ["LST", "NDVI"]:
        plot_seasonal_curve(
            data_df, product, str(figures_dir / "seasonal_{}.png".format(product))
        )
        plot_latitudinal_gradient(
            data_df,
            product,
            7,
            str(figures_dir / "gradient_{}_july.png".format(product)),
        )
        for zone in data_df["zone_name"].unique():
            plot_interannual_trend(
                data_df,
                product,
                zone,
                str(figures_dir / "trend_{}_{}.png".format(product, zone)),
            )


def _exec_export(config):
    """Экспорт таблиц в CSV/Excel."""
    tables_dir = DATA_PATHS["tables"]
    output_dir = DATA_PATHS["tables_output"]
    input_csv = tables_dir / "zonal_stats_raw.csv"

    if not input_csv.exists():
        logger.warning(M.ERR_FILE_NOT_FOUND.format(path=input_csv))
        return

    data_df = pd.read_csv(input_csv)
    dataframes = {
        "raw": data_df,
        "monthly": data_df.groupby(["zone_name", "year", "month", "product"])
        .mean()
        .reset_index(),
    }
    excel_path = output_dir / "modis_results.xlsx"
    save_excel_atomic(dataframes, str(excel_path))
    logger.info(M.MSG_SAVED.format(path=excel_path))
