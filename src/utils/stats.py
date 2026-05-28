# -*- coding: utf-8 -*-
"""Утилиты для расчёта статистических показателей."""

import numpy as np
import pandas as pd
from .. import logger


def calculate_basic_stats(values_array):
    """Возвращает словарь с базовыми статистиками валидных значений."""
    valid_mask = ~np.isnan(values_array)
    valid_count = int(np.sum(valid_mask))
    if valid_count == 0:
        return {
            "mean": np.nan,
            "std": np.nan,
            "median": np.nan,
            "min": np.nan,
            "max": np.nan,
            "count": 0,
        }
    valid_values = values_array[valid_mask]
    mean_val = float(np.mean(valid_values))
    return {
        "mean": mean_val,
        "std": float(np.std(valid_values)),
        "median": float(np.median(valid_values)),
        "min": float(np.min(valid_values)),
        "max": float(np.max(valid_values)),
        "count": valid_count,
    }


def calculate_cv(mean_val, std_val):
    """Рассчитывает коэффициент вариации в процентах."""
    if mean_val == 0 or np.isnan(mean_val) or np.isnan(std_val):
        return np.nan
    return float((std_val / abs(mean_val)) * 100.0)


def safe_aggregate(data_frame, group_columns, aggregation_specs):
    """Безопасная агрегация таблицы pandas с обработкой ошибок."""
    try:
        return data_frame.groupby(group_columns).agg(aggregation_specs).reset_index()
    except Exception as exc:
        logger.warning(f"Ошибка агрегации данных: {exc}")
        return pd.DataFrame()
