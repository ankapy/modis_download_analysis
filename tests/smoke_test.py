"""
Быстрый смоук-тест проекта: конфигурация, чистые функции, связность модулей.
Запуск: python tests/smoke_test.py
Не требует сети; отсутствующие артефакты пропускаются.
"""

import importlib
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

RESULTS = []


def check(name):
    """Регистрация проверки."""

    def decorator(fn):
        RESULTS.append((name, fn))
        return fn

    return decorator


@check("Импорт всех модулей пайплайна")
def test_imports():
    for module in (
        "cli.main",
        "core.01_downloader",
        "core.02_validator",
        "core.03_converter",
        "core.04_zonal_stats",
        "core.05_analyzer",
    ):
        importlib.import_module(module)


@check("Конфигурация продуктов полная")
def test_config():
    from config import MODIS_PRODUCTS

    required = ("product", "band", "scale_factor", "offset", "no_data_value", "unit")
    for name, cfg in MODIS_PRODUCTS.items():
        missing = [key for key in required if key not in cfg]
        assert not missing, f"Продукт {name}: нет ключей {missing}"


@check("Парсинг годов и месяцев")
def test_parsers():
    from utils.config_loader import parse_months, parse_year_range

    assert parse_year_range("2015") == [2015]
    assert parse_year_range("2015-2016") == [2015, 2016]
    assert parse_year_range("2015,2020") == [2015, 2020]
    assert parse_months("1-3") == [1, 2, 3]
    assert parse_months("5,7") == [5, 7]
    for bad, fn in (
        ("1990", parse_year_range),
        ("13", parse_months),
        ("abc", parse_months),
    ):
        try:
            fn(bad)
            raise AssertionError(f"Значение {bad} должно быть отклонено")
        except ValueError:
            pass


@check("Валидация списка продуктов")
def test_parse_products():
    from utils.config_loader import parse_products

    assert parse_products("LST, NDVI") == ["LST", "NDVI"]
    try:
        parse_products("FAKE")
        raise AssertionError("Продукт FAKE должен быть отклонён")
    except ValueError:
        pass


@check("Даты DOY и извлечение даты из имени файла")
def test_dates():
    stats = importlib.import_module("core.04_zonal_stats")

    assert stats.parse_doy("2015-001") == ("2015-01-01", 1)
    assert stats.parse_doy("2015-329") == ("2015-11-25", 11)
    assert stats.parse_doy("unknown") == ("", 0)
    assert stats.extract_date("MOD11A2.A2015001.h20v02.061.x.hdf") == "2015-001"
    assert stats.extract_date("broken.hdf") == "unknown"


@check("BBox из zones.gpkg и проверка покрытия")
def test_bbox():
    from config import ZONES_GPKG
    from utils.geo_utils import calculate_bbox_from_gpkg, check_modis_coverage

    if not ZONES_GPKG.exists():
        print("  пропуск: нет gis/zones.gpkg")
        return
    bbox = calculate_bbox_from_gpkg(ZONES_GPKG)
    assert len(bbox) == 4
    assert check_modis_coverage(bbox), f"Некорректный bbox: {bbox}"


@check("Загрузка зон из GeoPackage")
def test_zones():
    from config import ZONES_GPKG
    from utils.geo_utils import load_zones

    if not ZONES_GPKG.exists():
        print("  пропуск: нет gis/zones.gpkg")
        return
    zones = load_zones(ZONES_GPKG)
    assert zones, "Зоны не загрузились"
    for zone in zones:
        assert {"id", "name", "wkt", "lat_center", "lon_center"} <= set(zone)


@check("Анализатор загружает таблицу статистики")
def test_analyzer():
    import tempfile
    from config import DATA_PATHS

    csv_path = DATA_PATHS["tables"] / "zonal_stats_flat.csv"
    if not csv_path.exists():
        print("  пропуск: нет data/tables/zonal_stats_flat.csv")
        return
    analyzer_mod = importlib.import_module("core.05_analyzer")
    with tempfile.TemporaryDirectory() as tmp:
        analyzer = analyzer_mod.MODISAnalyzer(csv_path, Path(tmp))
        assert not analyzer.df.empty, "Таблица пустая после фильтрации"


def main():
    """Запуск всех проверок и вывод итога."""
    passed = 0
    failed = 0
    for name, fn in RESULTS:
        try:
            fn()
            passed += 1
            print(f"[OK] {name}")
        except Exception as error:
            failed += 1
            print(f"[FAIL] {name}: {error}")
            traceback.print_exc()

    print("-" * 60)
    print(f"Проверок: {passed + failed}, успешно: {passed}, падений: {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
