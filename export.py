# scripts/export_for_origin.py
"""
Экспорт данных для Origin Pro — отдельный скрипт
Запуск: python scripts/export_for_origin.py
"""

import pandas as pd
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATA_PATHS, ZONE_ORDER

MONTH_NAMES = {5: "Май", 6: "Июнь", 7: "Июль", 8: "Август", 9: "Сентябрь"}


def main():
    # Загрузка данных
    input_csv = Path(DATA_PATHS["tables"]) / "zonal_stats_monthly.csv"
    output_dir = Path(DATA_PATHS["tables_output"])
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Загрузка: {input_csv}")
    df = pd.read_csv(input_csv, encoding="utf-8-sig")

    # Фильтрация
    df = df[
        (df["month"].isin([5, 6, 7, 8, 9]))
        & (~df["mean"].isna())
        & (df["pixel_count"] > 0)
    ]
    print(f"[OK] Загружено {len(df)} записей")

    # === СЕЗОННАЯ ДИНАМИКА ===
    print("\n[1/3] Сезонная динамика...")
    seasonal_file = output_dir / "seasonal_dynamics.xlsx"

    with pd.ExcelWriter(seasonal_file, engine="openpyxl") as writer:
        for product in ["LST", "NDVI"]:
            seasonal = (
                df[df["product"] == product]
                .groupby(["zone_name", "month"])["mean"]
                .agg(["mean", "std"])
                .reset_index()
            )

            pivot_mean = seasonal.pivot(
                index="month", columns="zone_name", values="mean"
            )
            pivot_std = seasonal.pivot(index="month", columns="zone_name", values="std")

            pivot_mean.index = [MONTH_NAMES.get(m, m) for m in pivot_mean.index]
            pivot_std.index = [MONTH_NAMES.get(m, m) for m in pivot_std.index]

            pivot_mean = pivot_mean.reindex(
                columns=[z for z in ZONE_ORDER if z in pivot_mean.columns]
            )
            pivot_std = pivot_std.reindex(
                columns=[z for z in ZONE_ORDER if z in pivot_std.columns]
            )

            pivot_mean.to_excel(writer, sheet_name=f"{product}_mean")
            pivot_std.to_excel(writer, sheet_name=f"{product}_std")
            print(f"  [OK] {product}: mean/std")

    print(f"[OK] {seasonal_file}")

    # === МЕЖГОДОВАЯ ДИНАМИКА ===
    print("\n[2/3] Межгодовая динамика...")
    interannual_file = output_dir / "interannual_dynamics.xlsx"

    with pd.ExcelWriter(interannual_file, engine="openpyxl") as writer:
        for product in ["LST", "NDVI"]:
            interannual = (
                df[df["product"] == product]
                .groupby(["zone_name", "year"])["mean"]
                .agg(["mean", "std"])
                .reset_index()
            )

            pivot_mean = interannual.pivot(
                index="year", columns="zone_name", values="mean"
            )
            pivot_std = interannual.pivot(
                index="year", columns="zone_name", values="std"
            )

            pivot_mean = pivot_mean.reindex(
                columns=[z for z in ZONE_ORDER if z in pivot_mean.columns]
            )
            pivot_std = pivot_std.reindex(
                columns=[z for z in ZONE_ORDER if z in pivot_std.columns]
            )

            pivot_mean.to_excel(writer, sheet_name=f"{product}_mean")
            pivot_std.to_excel(writer, sheet_name=f"{product}_std")
            print(f"  [OK] {product}: mean/std")

    print(f"[OK] {interannual_file}")

    # === АМПЛИТУДА ===
    print("\n[3/3] Сезонная амплитуда...")
    amp_file = output_dir / "seasonal_amplitude.xlsx"

    rows = []
    for product in ["LST", "NDVI"]:
        for zone in ZONE_ORDER:
            subset = df[(df["product"] == product) & (df["zone_name"] == zone)]
            if subset.empty:
                continue
            means = subset["mean"]
            if len(means) > 0:
                rows.append(
                    {
                        "zone": zone,
                        "product": product,
                        "amplitude": means.max() - means.min(),
                        "max_val": means.max(),
                        "min_val": means.min(),
                    }
                )

    if rows:
        pd.DataFrame(rows).to_excel(amp_file, index=False, sheet_name="Amplitude")
        print(f"[OK] {amp_file}")

    print(f"\n✅ Готово! Файлы для Origin в: {output_dir}")
    print("\n📊 Как строить графики в Origin Pro:")
    print("  1. Откройте seasonal_dynamics.xlsx")
    print("  2. Перейдите на лист 'LST_mean'")
    print("  3. Выделите все данные (включая заголовки)")
    print("  4. Plot → Line + Symbol")
    print(
        "  5. Для error bars: скопируйте значения из листа 'LST_std' в колонку Y Error"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback

        traceback.print_exc()
