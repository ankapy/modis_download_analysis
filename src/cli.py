# -*- coding: utf-8 -*-
"""Интерфейс командной строки (CLI) для управления пайплайном."""

import argparse
import sys
import logging
from src import logger
from src import messages as M
from src.orch.pipeline import run_pipeline, PipelineError
from src.config import ConfigError


def main(argv=None):
    """Обработка аргументов и запуск оркестратора."""
    parser = argparse.ArgumentParser(description="MODIS Pipeline CLI")
    parser.add_argument(
        "--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"]
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Режим проверки без вычислений"
    )

    subparsers = parser.add_subparsers(dest="command", help="Доступные команды")
    for cmd in [
        "init",
        "download",
        "convert",
        "validate",
        "stats",
        "plot",
        "export",
        "dry-run",
    ]:
        subparsers.add_parser(cmd, help="Запустить этап: {}".format(cmd))

    args = parser.parse_args(argv)

    level = getattr(logging, args.log_level.upper(), logging.INFO)
    logger.setLevel(level)

    if args.dry_run or args.command == "dry-run":
        run_pipeline(
            ["download", "convert", "stats", "plot", "export"], config={}, dry_run=True
        )
        return

    if not args.command:
        parser.print_help()
        return

    command_map = {
        "init": [],
        "download": ["download"],
        "convert": ["convert"],
        "validate": ["validate"],
        "stats": ["stats"],
        "plot": ["plot"],
        "export": ["export"],
    }

    stages = command_map.get(args.command, [])
    try:
        run_pipeline(stages, config={}, dry_run=False)
    except (PipelineError, ConfigError) as e:
        logger.error(M.ERR_PIPELINE_FAILED.format(error=e))
        sys.exit(1)


if __name__ == "__main__":
    main()
