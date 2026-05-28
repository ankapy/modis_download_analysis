# -*- coding: utf-8 -*-
"""Инициализация пакета: настройка логгера."""

# Используем только стандартную библиотеку
import logging
import sys

# Имя логгера — единое для всего приложения
LOGGER_NAME = "modis_pipeline"

# Настройка логгера при первом импорте
# Проверка handlers предотвращает дублирование при повторном импорте
if not logging.getLogger(LOGGER_NAME).handlers:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)

    # Обработчик для вывода в консоль
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)

    # Формат сообщений: [УРОВЕНЬ] сообщение
    formatter = logging.Formatter("[%(levelname)s] %(message)s")
    handler.setFormatter(formatter)

    logger.addHandler(handler)

    # Предотвращение дублирования сообщений от дочерних логгеров
    logger.propagate = False

# Экспорт логгера для использования в других модулях
# Пример: from src import logger
logger = logging.getLogger(LOGGER_NAME)
