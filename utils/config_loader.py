"""
Загрузчик и валидатор конфигурации.
"""

from pathlib import Path
from typing import List, Dict

from config import MODIS_PRODUCTS, TEMPORAL_RANGE
from utils import messages


def parse_year_range(year_str: str) -> List[int]:
    """Парсинг строки годов в список."""
    year_str = year_str.strip()

    if "-" in year_str:
        parts = year_str.split("-")
        if len(parts) == 2:
            start, end = int(parts[0]), int(parts[1])
            if start < TEMPORAL_RANGE["start_year"] or end > TEMPORAL_RANGE["end_year"]:
                raise ValueError(
                    messages.ERR_YEAR_RANGE.format(
                        TEMPORAL_RANGE["start_year"], TEMPORAL_RANGE["end_year"]
                    )
                )
            return list(range(start, end + 1))

    if "," in year_str:
        years = [int(y.strip()) for y in year_str.split(",")]
        for y in years:
            if y < TEMPORAL_RANGE["start_year"] or y > TEMPORAL_RANGE["end_year"]:
                raise ValueError(
                    messages.ERR_YEAR_RANGE.format(
                        TEMPORAL_RANGE["start_year"], TEMPORAL_RANGE["end_year"]
                    )
                )
        return years

    year = int(year_str)
    if year < TEMPORAL_RANGE["start_year"] or year > TEMPORAL_RANGE["end_year"]:
        raise ValueError(
            messages.ERR_YEAR_RANGE.format(
                TEMPORAL_RANGE["start_year"], TEMPORAL_RANGE["end_year"]
            )
        )
    return [year]


def parse_months(month_str: str) -> List[int]:
    """Парсинг строки месяцев в список."""
    month_str = month_str.strip()

    if "-" in month_str:
        parts = month_str.split("-")
        if len(parts) == 2:
            start, end = int(parts[0]), int(parts[1])
            if start < 1 or end > 12:
                raise ValueError(messages.ERR_MONTH_RANGE.format(1, 12))
            return list(range(start, end + 1))

    if "," in month_str:
        months = [int(m.strip()) for m in month_str.split(",")]
        for m in months:
            if m < 1 or m > 12:
                raise ValueError(messages.ERR_MONTH_RANGE.format(1, 12))
        return months

    month = int(month_str)
    if month < 1 or month > 12:
        raise ValueError(messages.ERR_MONTH_RANGE.format(1, 12))
    return [month]


def prompt_temporal_range() -> Dict:
    """Интерактивный запрос временного диапазона."""
    print(f"\n{messages.INFO_TEMPORAL_HEADER}")
    print(messages.INFO_TEMPORAL_FORMAT)

    # Ввод годов
    while True:
        try:
            year_input = input(
                messages.INFO_INPUT_YEAR.format(
                    TEMPORAL_RANGE["start_year"], TEMPORAL_RANGE["end_year"]
                )
            ).strip()
            if not year_input:
                year_input = (
                    f"{TEMPORAL_RANGE['start_year']}-{TEMPORAL_RANGE['end_year']}"
                )

            years = parse_year_range(year_input)
            start_year = min(years)
            end_year = max(years)
            break  # Годы введены успешно
        except ValueError as e:
            print(f"[ERROR] {e}. Попробуйте снова.")
        except Exception as e:
            print(messages.INFO_ERROR_INPUT.format(str(e)))

    # Ввод месяцев (отдельно от годов)
    while True:
        try:
            month_input = input(messages.INFO_INPUT_MONTHS).strip()
            if not month_input:
                month_input = "1-12"

            months = parse_months(month_input)
            break  # Месяцы введены успешно
        except ValueError as e:
            print(f"[ERROR] {e}. Попробуйте снова.")
        except Exception as e:
            print(messages.INFO_ERROR_INPUT.format(str(e)))

    return {
        "start_year": start_year,
        "end_year": end_year,
        "months": months,
    }


def prompt_products() -> List[str]:
    """Интерактивный выбор продуктов MODIS."""
    print(f"\n{messages.INFO_PRODUCTS_HEADER}")
    print(messages.INFO_AVAILABLE_PRODUCTS)
    for i, (key, config) in enumerate(MODIS_PRODUCTS.items(), 1):
        print(messages.INFO_PRODUCT_OPTION.format(i, key, config["product"]))

    while True:
        try:
            choice = input(messages.INFO_INPUT_PRODUCTS).strip()
            if not choice:
                choice = "1,2"

            indices = [int(x.strip()) for x in choice.split(",")]
            products = []
            keys = list(MODIS_PRODUCTS.keys())

            for idx in indices:
                if 1 <= idx <= len(keys):
                    products.append(keys[idx - 1])
                else:
                    print(messages.WARN_INVALID_NUMBER.format(idx))

            if products:
                return products
        except ValueError as e:
            print(messages.INFO_ERROR_INPUT.format(str(e)))


def prompt_zones_path() -> Path:
    """Интерактивный запрос пути к GeoPackage с зонами."""
    print(f"\n{messages.INFO_ZONES_HEADER}")

    while True:
        path_str = input(messages.INFO_INPUT_ZONES).strip()
        path = Path(path_str)

        if path.exists() and path.suffix == ".gpkg":
            return path
        else:
            print(messages.ERR_FILE_NOT_GPKG.format(path))


def parse_products(products_str: str) -> List[str]:
    """Парсинг и валидация списка продуктов из CLI."""
    names = [p.strip() for p in products_str.split(",")]
    unknown = [p for p in names if p not in MODIS_PRODUCTS]
    if unknown:
        raise ValueError(
            messages.ERR_UNKNOWN_PRODUCTS.format(
                ", ".join(unknown), ", ".join(MODIS_PRODUCTS.keys())
            )
        )
    return names
