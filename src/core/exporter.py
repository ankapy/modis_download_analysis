# -*- coding: utf-8 -*-
"""Экспорт результатов с атомарной записью для гарантии целостности."""

import os
import pandas as pd
from src import messages as M
from src import logger


def save_csv_atomic(data, path, fields):
    """Атомарно сохраняет список словарей в CSV файл."""
    temp_path = "{}.tmp".format(path)
    try:
        df = pd.DataFrame(data, columns=fields)
        df.to_csv(temp_path, index=False, encoding="utf-8-sig")
        os.replace(temp_path, path)
        logger.info(M.MSG_SAVED.format(path=path))
    except Exception as e:
        logger.error(M.ERR_SAVE_FAILED.format(path=path, error=e))
        if os.path.exists(temp_path):
            os.remove(temp_path)


def save_excel_atomic(dataframes, path):
    """Атомарно сохраняет словарь DataFrame в Excel файл."""
    temp_path = "{}.tmp".format(path)
    try:
        with pd.ExcelWriter(temp_path, engine="openpyxl") as writer:
            for sheet_name, df in dataframes.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)
        os.replace(temp_path, path)
        logger.info(M.MSG_SAVED.format(path=path))
    except Exception as e:
        logger.error(M.ERR_SAVE_FAILED.format(path=path, error=e))
        if os.path.exists(temp_path):
            os.remove(temp_path)
