"""
Система логирования для пайплайна MODIS.
"""

import logging
import sys
from datetime import datetime
from config import DATA_PATHS, LOG_FORMAT, LOG_DATE_FORMAT


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Настройка логгера с выводом в консоль и файл.

    Args:
        name: Имя логгера.
        level: Уровень логирования.

    Returns:
        Настроенный логгер.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    # Консольный handler.
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_formatter = logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # Файловый handler.
    log_dir = DATA_PATHS["logs"]
    log_file = log_dir / f"pipeline_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    return logger
