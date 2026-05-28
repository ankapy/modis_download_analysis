# setup_project.py
"""
Скрипт создания структуры проекта modis_download_analysis.
Запускать из корня проекта: python setup_project.py
"""

import os
import sys
from pathlib import Path

# Константы: корневая директория проекта
PROJECT_ROOT = Path(__file__).resolve().parent

# Структура директорий относительно PROJECT_ROOT
DIR_STRUCTURE = [
    "src/utils",
    "src/core",
    "src/orch",
    "scripts",
    "data/raw/MOD11A2",
    "data/raw/MOD13Q1",
    "data/processed/LST",
    "data/processed/NDVI",
    "data/tables/validation_reports",
    "gis/temp",
    "output/figures/seasonal",
    "output/figures/trends",
    "output/figures/gradients",
    "output/figures/correlations",
    "output/tables/origin_export",
    "logs",
    "tests/unit",
    "tests/integration",
]

# Python-модули (пустые файлы .py)
PYTHON_MODULES = [
    # src/
    "src/__init__.py",
    "src/cli.py",
    "src/constants.py",
    "src/messages.py",
    "src/config.py",
    # src/utils/
    "src/utils/__init__.py",
    "src/utils/raster_io.py",
    "src/utils/temporal.py",
    "src/utils/stats.py",
    "src/utils/fs.py",
    # src/core/
    "src/core/__init__.py",
    "src/core/product_processor.py",
    "src/core/preprocessor.py",
    "src/core/stat_calculator.py",
    "src/core/plotter.py",
    "src/core/exporter.py",
    # src/orch/
    "src/orch/__init__.py",
    "src/orch/pipeline.py",
    # scripts/ (тонкие обёртки над cli.py)
    "scripts/01_download.py",
    "scripts/02_validate.py",
    "scripts/03_convert.py",
    "scripts/04_zonal_stats.py",
    "scripts/05_analysis.py",
    "scripts/06_export.py",
    # tests/
    "tests/__init__.py",
    "tests/unit/__init__.py",
    "tests/integration/__init__.py",
]

# Заголовки для новых .py-файлов
FILE_HEADERS = {
    "src/__init__.py": '# -*- coding: utf-8 -*-\n"""Инициализация пакета и настройка логгера."""\n',
    "src/constants.py": '# -*- coding: utf-8 -*-\n"""Константы: коэффициенты, пороги, имена полей."""\n',
    "src/messages.py": '# -*- coding: utf-8 -*-\n"""Тексты сообщений на русском для логирования и вывода."""\n',
    "src/config.py": '# -*- coding: utf-8 -*-\n"""Конфигурация проекта и валидация параметров."""\n',
    "src/cli.py": '# -*- coding: utf-8 -*-\n"""Интерфейс командной строки (argparse)."""\n',
}

DEFAULT_HEADER = '# -*- coding: utf-8 -*-\n"""{module_name}."""\n'


def create_directories(base_path: Path, directories: list) -> int:
    """Создание директорий. Возвращает количество созданных."""
    created = 0
    for dir_rel in directories:
        dir_path = base_path / dir_rel
        if not dir_path.exists():
            dir_path.mkdir(parents=True, exist_ok=True)
            print(f"  [DIR] {dir_rel}")
            created += 1
        else:
            print(f"  [SKIP] {dir_rel} — уже существует")
    return created


def create_python_files(base_path: Path, modules: list) -> int:
    """Создание пустых .py-файлов с заголовками. Возвращает количество созданных."""
    created = 0
    for module_rel in modules:
        file_path = base_path / module_rel
        if not file_path.exists():
            # Формируем содержимое файла
            module_name = Path(module_rel).stem
            header = FILE_HEADERS.get(
                module_rel, DEFAULT_HEADER.format(module_name=module_name)
            )
            # Записываем файл
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(header)
            print(f"  [FILE] {module_rel}")
            created += 1
        else:
            print(f"  [SKIP] {module_rel} — уже существует")
    return created


def main():
    """Точка входа: создание структуры проекта."""
    print("=" * 60)
    print("Создание структуры проекта modis_download_analysis")
    print(f"Целевая директория: {PROJECT_ROOT}")
    print("=" * 60)

    # Проверка прав записи
    if not os.access(PROJECT_ROOT, os.W_OK):
        print(f"[ERROR] Нет прав записи в {PROJECT_ROOT}")
        sys.exit(1)

    # Создание директорий
    print("\n[1/2] Создание директорий...")
    dirs_created = create_directories(PROJECT_ROOT, DIR_STRUCTURE)

    # Создание Python-файлов
    print("\n[2/2] Создание Python-модулей...")
    files_created = create_python_files(PROJECT_ROOT, PYTHON_MODULES)

    # Итоги
    print("\n" + "=" * 60)
    print("ИТОГИ")
    print("=" * 60)
    print(f"  Директорий создано: {dirs_created}")
    print(f"  Файлов .py создано: {files_created}")
    print(f"  Путь проекта: {PROJECT_ROOT}")
    print("=" * 60)
    print("\n[OK] Структура проекта готова.")
    print("Далее: наполнение модулей согласно плану реорганизации.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[INTERRUPT] Прервано пользователем")
        sys.exit(0)
    except PermissionError as e:
        print(f"\n[ERROR] Ошибка прав доступа: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Критическая ошибка: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
