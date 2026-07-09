"""
Загрузчик и валидатор конфигурации.
"""

import sys
from pathlib import Path
from typing import List, Dict
from config import MODIS_PRODUCTS


def parse_year_range(year_str: str) -> List[int]:
    """Парсинг строки годов в список."""
    year_str = year_str.strip()

    if "-" in year_str:
        parts = year_str.split("-")
        if len(parts) == 2:
            start, end = int(parts[0]), int(parts[1])
            return list(range(start, end + 1))

    if "," in year_str:
        return [int(y.strip()) for y in year_str.split(",")]

    return [int(year_str)]


def parse_months(month_str: str) -> List[int]:
    """Парсинг строки месяцев в список."""
    month_str = month_str.strip()

    if "-" in month_str:
        parts = month_str.split("-")
        if len(parts) == 2:
            start, end = int(parts[0]), int(parts[1])
            return list(range(start, end + 1))

    if "," in month_str:
        return [int(m.strip()) for m in month_str.split(",")]

    return [int(month_str)]


def prompt_temporal_range() -> Dict:
    """Интерактивный запрос временного диапазона."""

    print("\n=== Временной диапазон ===")
    print("Формат ввода:")
    print("  Годы: 2015-2025 или 2015,2017,2020")
    print("  Месяцы: 1-12 или 5,6,7,8,9")

    while True:
        try:
            year_input = input("\nВведите диапазон годов [2015-2025]: ").strip()
            if not year_input:
                year_input = "2015-2025"

            years = parse_year_range(year_input)
            start_year = min(years)
            end_year = max(years)

            month_input = input("Введите месяцы [1-12]: ").strip()
            if not month_input:
                month_input = "1-12"

            months = parse_months(month_input)

            return {
                "start_year": start_year,
                "end_year": end_year,
                "months": months,
            }
        except Exception as e:
            print(f"[ERROR] Ошибка ввода: {e}. Попробуйте снова.")


def prompt_products() -> List[str]:
    """Интерактивный выбор продуктов MODIS."""
    print("\n=== Выбор продуктов MODIS ===")
    print("Доступные продукты:")
    for i, (key, config) in enumerate(MODIS_PRODUCTS.items(), 1):
        print(f"  {i}. {key} ({config['product']})")

    while True:
        try:
            choice = input("\nВведите номера через запятую [1,2]: ").strip()
            if not choice:
                choice = "1,2"

            indices = [int(x.strip()) for x in choice.split(",")]
            products = []
            keys = list(MODIS_PRODUCTS.keys())

            for idx in indices:
                if 1 <= idx <= len(keys):
                    products.append(keys[idx - 1])
                else:
                    print(f"[WARN] Неверный номер: {idx}")

            if products:
                return products
        except Exception as e:
            print(f"[ERROR] Ошибка ввода: {e}. Попробуйте снова.")


def prompt_zones_path() -> Path:
    """Интерактивный запрос пути к GeoPackage с зонами."""
    print("\n=== Путь к зонам ===")

    while True:
        path_str = input("Введите путь к zones.gpkg: ").strip()
        path = Path(path_str)

        if path.exists() and path.suffix == ".gpkg":
            return path
        else:
            print(f"[ERROR] Файл не найден или неверный формат: {path}")
