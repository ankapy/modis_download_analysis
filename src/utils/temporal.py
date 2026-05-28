# -*- coding: utf-8 -*-
"""Утилиты для работы с временными параметрами MODIS."""

import re
from .. import messages as M
from .. import logger

# Границы дней года для конвертации в месяцы
DOY_MONTH_BOUNDS = [
    (1, 59, 2),
    (60, 90, 3),
    (91, 120, 4),
    (121, 151, 5),
    (152, 181, 6),
    (182, 212, 7),
    (213, 243, 8),
    (244, 273, 9),
    (274, 304, 10),
    (305, 334, 11),
    (335, 366, 12),
]


def parse_doy(file_name):
    """Извлекает год и день года из имени файла MODIS. Возвращает кортеж или None."""
    match = re.search(r"A(\d{4})(\d{3})", file_name)
    if match:
        return int(match.group(1)), int(match.group(2))
    logger.debug(M.ERR_PARSE_DATE.format(file_name=file_name))
    return None


def doy_to_month(day_of_year):
    """Конвертирует день года в номер месяца."""
    for start, end, month in DOY_MONTH_BOUNDS:
        if start <= day_of_year <= end:
            return month
    return 0


def is_vegetation_season(month_num):
    """Проверяет, входит ли месяц в вегетационный период (май–сентябрь)."""
    return 5 <= month_num <= 9
