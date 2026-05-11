"""
Скачивание данных MODIS через earthaccess — СТАБИЛЬНАЯ ВЕРСИЯ
Минимальный параллелизм для избежания разрывов соединения.
"""

import os
import sys
import time
import traceback
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    TEMPORAL_RANGE,
    SPATIAL_RANGE,
    MODIS_PRODUCTS,
    DATA_PATHS,
)

try:
    import earthaccess
except ImportError:
    print("ОШИБКА: Установите earthaccess")
    sys.exit(1)


def count_hdf_files(output_dir):
    """Подсчёт только HDF-файлов данных"""
    if not output_dir.exists():
        return 0
    files = list(output_dir.glob("*.hdf"))
    return len(files)


def download_with_earthaccess_stable():
    """
    Скачивание MODIS через earthaccess.
    По 5 гранул за раз + паузы между запросами.
    """

    print("=" * 60)
    print("MODIS Downloader via earthaccess")
    print("=" * 60)
    print(f"Время начала: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Авторизация
    print("\n[AUTH] Авторизация в NASA Earthdata...")
    try:
        earthaccess.login(strategy="netrc", persist=True)
        print("  [OK] Авторизация через .netrc успешна")
    except Exception as e:
        print(f"  [WARN] .netrc не найден: {e}")
        earthaccess.login(strategy="environment", persist=True)

    # Границы области
    bbox = (
        SPATIAL_RANGE["lon_min"],
        SPATIAL_RANGE["lat_min"],
        SPATIAL_RANGE["lon_max"],
        SPATIAL_RANGE["lat_max"],
    )

    # Все годы из config.py
    years = list(range(TEMPORAL_RANGE["start_year"], TEMPORAL_RANGE["end_year"] + 1))
    products = ["LST", "NDVI"]

    # НАСТРОЙКИ СТАБИЛЬНОСТИ (уменьшены для избежания разрывов)
    BATCH_SIZE = 15  # Гранул за один вызов (было 20)
    PAUSE_BATCH = 5  # Пауза после каждого пакета (сек)
    PAUSE_GRANULE = 2  # Пауза после каждой гранулы (сек)
    MAX_RETRIES = 3  # Повторных попыток при ошибке

    total_success = 0
    total_failed = 0
    total_skipped = 0

    for year_idx, year in enumerate(years, 1):
        print(f"\n{'=' * 60}")
        print(f">>> ГОД {year} ({year_idx}/{len(years)})")
        print(f"{'=' * 60}")

        for product_idx, product_key in enumerate(products, 1):
            config = MODIS_PRODUCTS[product_key]
            product_code = config["product"]

            print(
                f"\n  [{product_idx}/{len(products)}] {product_code} v{config['version']}"
            )

            start_date = f"{year}-{TEMPORAL_RANGE['veg_start']}"
            end_date = f"{year}-{TEMPORAL_RANGE['veg_end']}"

            output_dir = Path(DATA_PATHS["raw"]) / product_code / str(year)
            output_dir.mkdir(parents=True, exist_ok=True)

            # Проверка уже скачанных
            existing_hdf = count_hdf_files(output_dir)
            expected_granules = 120 if product_code == "MOD11A2" else 77

            if existing_hdf >= expected_granules * 0.95:
                print(
                    f"  [SKIP] Уже скачано {existing_hdf}/{expected_granules} HDF-файлов"
                )
                total_skipped += 1
                continue

            print(f"    Период: {start_date} – {end_date}")
            print(f"    Директория: {output_dir}")
            print(f"    Уже скачано: {existing_hdf}/{expected_granules} HDF-файлов")

            # Поиск гранул
            try:
                print(f"  [SEARCH] Поиск гранул...")
                results = earthaccess.search_data(
                    short_name=product_code,
                    temporal=(start_date, end_date),
                    bounding_box=bbox,
                    count=2000,
                )
            except Exception as e:
                print(f"  [ERROR] Ошибка поиска: {e}")
                total_failed += 1
                continue

            if not results:
                print(f"  [WARN] Гранулы не найдены")
                total_skipped += 1
                continue

            print(f"  [INFO] Найдено гранул: {len(results)}")

            # Фильтрация уже скачанных гранул
            existing_files = {f.name for f in output_dir.glob("*.hdf")}
            results_to_download = []

            for granule in results:
                granule_id = granule.get("meta", {}).get("native-id", "")
                expected_filename = granule_id.split(":")[-1] + ".hdf"
                if expected_filename not in existing_files:
                    results_to_download.append(granule)

            if not results_to_download:
                print(f"  [SKIP] Все файлы уже скачаны")
                total_skipped += 1
                continue

            print(
                f"  [DOWNLOAD] К загрузке: {len(results_to_download)} из {len(results)}"
            )

            # Скачивание ПО ОДНОЙ ГРАНУЛЕ с паузами
            downloaded = 0
            failed = 0
            batch_num = 0

            for i in range(0, len(results_to_download), BATCH_SIZE):
                batch = results_to_download[i : i + BATCH_SIZE]
                batch_num += 1

                try:
                    print(
                        f"    [BATCH {batch_num}] Загрузка гранул {i + 1}-{min(i + BATCH_SIZE, len(results_to_download))}..."
                    )

                    # Скачиваем по одной грануле внутри пакета для контроля
                    for granule_idx, granule in enumerate(batch, 1):
                        success = False

                        for attempt in range(MAX_RETRIES):
                            try:
                                result = earthaccess.download(
                                    [granule], str(output_dir)
                                )
                                if result and len(result) > 0:
                                    downloaded += 1
                                    print(
                                        f"      [{downloaded}/{len(results_to_download)}] OK"
                                    )
                                    success = True
                                    break
                                else:
                                    print(
                                        f"      [WARN] Пустой результат (попытка {attempt + 1})"
                                    )
                            except Exception as e:
                                error_msg = str(e)[:80]
                                print(
                                    f"      [ERROR {attempt + 1}/{MAX_RETRIES}] {error_msg}..."
                                )

                                if attempt < MAX_RETRIES - 1:
                                    wait_time = (attempt + 1) * 5  # 5, 10, 15 сек
                                    print(f"      [PAUSE] Ожидание {wait_time} сек...")
                                    time.sleep(wait_time)

                        if not success:
                            failed += 1
                            print(f"      [FAIL] Пропущено после {MAX_RETRIES} попыток")

                        # Пауза между гранулами
                        if granule_idx < len(batch):
                            time.sleep(PAUSE_GRANULE)

                    # Пауза после каждого пакета
                    if batch_num < (len(results_to_download) // BATCH_SIZE) + 1:
                        print(f"    [PAUSE] Пауза {PAUSE_BATCH}с...")
                        time.sleep(PAUSE_BATCH)

                except KeyboardInterrupt:
                    print(f"\n  [INTERRUPT] Прервано на пакете {batch_num}")
                    break
                except Exception as e:
                    print(f"    [ERROR] Пакет {batch_num}: {str(e)[:80]}")
                    failed += len(batch)
                    time.sleep(10)

            # Итоги по продукту
            print(
                f"\n  [RESULT] {product_code}/{year}: скачано {downloaded}, ошибок {failed}"
            )

            if downloaded > 0:
                total_success += 1
            if failed > len(results_to_download) * 0.5:
                total_failed += 1

            # Пауза между продуктами
            time.sleep(5)

        # Пауза между годами
        time.sleep(10)

    # Итоги
    print("\n" + "=" * 60)
    print("ИТОГИ ЗАГРУЗКИ")
    print("=" * 60)
    print(f"  Успешно: {total_success}")
    print(f"  Пропущено: {total_skipped}")
    print(f"  Ошибок: {total_failed}")
    print(f"  Время окончания: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)


if __name__ == "__main__":
    try:
        download_with_earthaccess_stable()
    except KeyboardInterrupt:
        print("\n\n[INTERRUPT] Программа прервана пользователем")
        print("[INFO] Запустите снова для продолжения")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] Критическая ошибка: {e}")
        traceback.print_exc()
        sys.exit(1)
