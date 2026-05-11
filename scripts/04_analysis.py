"""
Анализ и визуализация результатов Zonal Statistics
Включает: сезонную динамику, тренды, корреляцию, широтный градиент,
амплитуду колебаний, таблицы значимости и агрегированные данные.
"""

import matplotlib

matplotlib.use("Agg")

import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import rcParams
from scipy import stats

# Настройка шрифтов и DPI для публикации
try:
    rcParams["font.family"] = "DejaVu Sans"
    rcParams["font.size"] = 10
    rcParams["axes.unicode_minus"] = False
    rcParams["figure.dpi"] = 300
    rcParams["savefig.dpi"] = 300
    rcParams["savefig.bbox"] = "tight"
    rcParams["savefig.pad_inches"] = 0.1
except Exception:
    pass

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATA_PATHS

# Текстовые константы
MSG_LOADING = "[INFO] Загрузка данных: {}"
MSG_LOADED = "[OK] Загружено {} записей"
MSG_SAVED = "[OK] Сохранено: {}"
MSG_ERROR_FILE = "[ERROR] Файл не найден: {}"
MSG_ERROR = "[ERROR] {}"

# Цветовая палитра для 9 природных зон
ZONE_COLORS = {
    "Степь": "#F5F57A",
    "Лесостепь": "#F5CA7A",
    "Южная тайга": "#55944F",
    "Средняя тайга": "#5DAD51",
    "Северная тайга": "#C9E2B1",
    "Подтайга": "#A3C74A",
    "Горная тайга": "#41A98C",
    "Лесотундра": "#7DD2EC",
    "Тундра": "#7AB6F5",
}

# Порядок зон для легенды (с юга на север)
ZONE_ORDER = [
    "Степь",
    "Лесостепь",
    "Подтайга",
    "Южная тайга",
    "Средняя тайга",
    "Северная тайга",
    "Горная тайга",
    "Лесотундра",
    "Тундра",
]

MONTH_NAMES = {5: "Май", 6: "Июнь", 7: "Июль", 8: "Август", 9: "Сентябрь"}


class MODISAnalyzer:
    """Анализ и визуализация данных MODIS"""

    def __init__(self, data_path: str, output_dir: str):
        """Инициализация анализатора"""
        self.data_path = Path(data_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        print(MSG_LOADING.format(self.data_path))
        if not self.data_path.exists():
            raise FileNotFoundError(MSG_ERROR_FILE.format(self.data_path))

        # Загрузка с автоопределением разделителя и кодировки utf-8-sig
        self.df = pd.read_csv(
            self.data_path, sep=None, engine="python", encoding="utf-8-sig"
        )

        # Очистка названий колонок
        self.df.columns = self.df.columns.str.strip().str.replace(
            "\ufeff", "", regex=False
        )

        print(f"[DEBUG] Доступные колонки: {list(self.df.columns)}")
        self._preprocess_data()

        print(MSG_LOADED.format(len(self.df)))

    def _preprocess_data(self):
        """Фильтрация и подготовка данных"""
        if "month" in self.df.columns:
            self.df["month"] = (
                pd.to_numeric(self.df["month"], errors="coerce").fillna(0).astype(int)
            )

        # Гарантируем, что год тоже числовой (защита от строковых лет в CSV)
        if "year" in self.df.columns:
            self.df["year"] = pd.to_numeric(self.df["year"], errors="coerce")

        required_cols = ["month", "mean", "pixel_count"]
        if not all(col in self.df.columns for col in required_cols):
            print(
                f"[WARN] В файле отсутствуют колонки: {required_cols}. Фильтрация пропущена."
            )
            return

        mask = (
            self.df["month"].isin([5, 6, 7, 8, 9])
            & (~self.df["mean"].isna())
            & (self.df["pixel_count"] > 0)
        )
        self.df = self.df[mask].copy()

    def _get_color(self, zone_name: str) -> str:
        """Возврат цвета для зоны"""
        return ZONE_COLORS.get(zone_name, "gray")

    def plot_seasonal_dynamics(self, product: str, save: bool = True):
        """Сезонная динамика по месяцам"""
        if "zone_name" not in self.df.columns or "month" not in self.df.columns:
            print("[WARN] Пропуск Сезонной динамики: нет zone_name или month")
            return

        agg = (
            self.df[self.df["product"] == product]
            .groupby(["zone_name", "month"])["mean"]
            .agg(["mean", "std", "count"])
            .reset_index()
        )
        agg = agg[agg["count"] >= 3]

        fig, ax = plt.subplots(figsize=(10, 6))

        for zone in ZONE_ORDER:
            data = agg[agg["zone_name"] == zone]
            if data.empty:
                continue
            ax.errorbar(
                [MONTH_NAMES[m] for m in data["month"]],
                data["mean"],
                yerr=data["std"],
                label=zone,
                color=self._get_color(zone),
                marker="o",
                capsize=3,
                linewidth=1.5,
            )

        ylabel = "Температура, °C" if product == "LST" else "NDVI"
        ax.set_title(f"Сезонная динамика ({product})")
        ax.set_xlabel("Месяц")
        ax.set_ylabel(ylabel)
        ax.legend(title="Зона", frameon=True)
        ax.grid(axis="y", alpha=0.3)
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")

        if save:
            path = self.output_dir / f"seasonal_{product.lower()}.png"
            fig.savefig(path)
            print(MSG_SAVED.format(path))
        plt.close(fig)

    def plot_interannual_trends(self, product: str, save: bool = True):
        """Межгодовые тренды"""
        if "zone_name" not in self.df.columns or "year" not in self.df.columns:
            print("[WARN] Пропуск Трендов: нет zone_name или year")
            return

        fig, ax = plt.subplots(figsize=(11, 6))

        for zone in ZONE_ORDER:
            subset = self.df[
                (self.df["product"] == product) & (self.df["zone_name"] == zone)
            ]
            if subset.empty:
                continue

            yearly = subset.groupby("year")["mean"].mean()
            if len(yearly) < 3:
                continue

            x = yearly.index.astype(float)
            y = yearly.values

            color = self._get_color(zone)
            ax.plot(x, y, label=zone, color=color, marker="o")

            if len(yearly) >= 5:
                slope, intercept, _, p_val, _ = stats.linregress(x, y)
                trend = x * slope + intercept
                ax.plot(x, trend, linestyle=":", alpha=0.5, color=color)

        ax.set_title(f"Межгодовая динамика ({product})")
        ax.set_xlabel("Год")
        ax.set_ylabel("Темп., °C" if product == "LST" else "NDVI")
        ax.legend(title="Зона", ncol=2)
        ax.grid(alpha=0.3)

        if save:
            path = self.output_dir / f"trend_{product.lower()}.png"
            fig.savefig(path)
            print(MSG_SAVED.format(path))
        plt.close(fig)

    def plot_lst_ndvi_correlation(self, month: int = 7, save: bool = True):
        """Корреляция LST и NDVI"""
        if "zone_name" not in self.df.columns or "year" not in self.df.columns:
            print("[WARN] Пропуск Корреляции: нет zone_name или year")
            return

        lst = self.df[(self.df["product"] == "LST") & (self.df["month"] == month)][
            ["zone_name", "year", "mean"]
        ].copy()
        ndvi = self.df[(self.df["product"] == "NDVI") & (self.df["month"] == month)][
            ["zone_name", "year", "mean"]
        ].copy()

        lst.columns = ["zone_name", "year", "LST"]
        ndvi.columns = ["zone_name", "year", "NDVI"]

        merged = pd.merge(lst, ndvi, on=["zone_name", "year"], how="inner")
        merged = merged[merged["LST"].notna() & merged["NDVI"].notna()]

        fig, ax = plt.subplots(figsize=(8, 7))

        for zone in ZONE_ORDER:
            data = merged[merged["zone_name"] == zone]
            if data.empty:
                continue

            color = self._get_color(zone)
            ax.scatter(
                data["LST"],
                data["NDVI"],
                label=zone,
                color=color,
                alpha=0.6,
                s=20,
                edgecolors="white",
            )

            if len(data) >= 5:
                r, _ = stats.pearsonr(data["LST"], data["NDVI"])
                ax.text(
                    0.05,
                    0.95 - 0.1 * ZONE_ORDER.index(zone),
                    f"{zone}: r={r:.2f}",
                    transform=ax.transAxes,
                    fontsize=8,
                    color=color,
                    va="top",
                )

        ax.set_xlabel("Температура, °C")
        ax.set_ylabel("NDVI")
        ax.set_title(f"Корреляция LST–NDVI ({MONTH_NAMES.get(month, month)})")
        ax.legend(frameon=True)
        ax.grid(alpha=0.3)

        if save:
            path = self.output_dir / f"correlation_m{month}.png"
            fig.savefig(path)
            print(MSG_SAVED.format(path))
        plt.close(fig)

    def plot_latitudinal_gradient(
        self, product: str, month: int = 7, save: bool = True
    ):
        """Широтный градиент: зависимость от центральной широты зоны"""
        if "lat_center" not in self.df.columns:
            print("[WARN] Широтный градиент пропущен: нет колонки lat_center в данных.")
            return

        subset = self.df[
            (self.df["product"] == product)
            & (self.df["month"] == month)
            & (self.df["lat_center"].notna())
        ]
        if subset.empty:
            print(f"[WARN] Нет данных для градиента {product} в месяц {month}")
            return

        # Группировка по широтным интервалам (биннинг по 2°)
        subset = subset.copy()
        subset["lat_bin"] = (subset["lat_center"] // 2) * 2
        agg = (
            subset.groupby("lat_bin")["mean"]
            .agg(["mean", "std", "count"])
            .reset_index()
        )
        agg = agg[agg["count"] >= 10]  # Минимум 10 наблюдений на бин

        fig, ax = plt.subplots(figsize=(9, 6))
        ax.errorbar(
            agg["lat_bin"],
            agg["mean"],
            yerr=agg["std"],
            fmt="o",
            capsize=3,
            label="Данные",
            color=ZONE_COLORS.get("Северная тайга", "blue"),
        )

        # Линия тренда
        if len(agg) >= 3:
            slope, intercept, r, p, _ = stats.linregress(agg["lat_bin"], agg["mean"])
            x_fit = np.array([agg["lat_bin"].min(), agg["lat_bin"].max()])
            ax.plot(
                x_fit, intercept + slope * x_fit, "r--", label=f"Тренд: {slope:.2f}"
            )
            ax.text(
                0.05,
                0.95,
                f"R²={r**2:.2f}\np={p:.3g}",
                transform=ax.transAxes,
                bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.3),
            )

        ax.set_xlabel("Широта, ° с.ш.")
        ax.set_ylabel("Темп., °C" if product == "LST" else "NDVI")
        ax.set_title(f"Широтный градиент ({MONTH_NAMES.get(month, month)})")
        ax.legend()
        ax.grid(alpha=0.3)

        if save:
            path = self.output_dir / f"gradient_{product.lower()}_m{month}.png"
            fig.savefig(path, dpi=300)
            print(MSG_SAVED.format(path))
        plt.close()

    def plot_seasonal_amplitude(self, product: str, save: bool = True):
        """Амплитуда сезонных колебаний (max - min по месяцам)"""
        agg = (
            self.df[self.df["product"] == product]
            .groupby("zone_name")["mean"]
            .agg(["min", "max"])
            .reset_index()
        )
        agg["amplitude"] = agg["max"] - agg["min"]
        agg = agg[agg["zone_name"].isin(ZONE_ORDER)]

        # Сортировка по порядку зон
        agg["order"] = agg["zone_name"].apply(
            lambda x: ZONE_ORDER.index(x) if x in ZONE_ORDER else 99
        )
        agg = agg.sort_values("order")

        fig, ax = plt.subplots(figsize=(10, 6))
        bars = ax.barh(
            agg["zone_name"],
            agg["amplitude"],
            color=[ZONE_COLORS.get(z, "gray") for z in agg["zone_name"]],
        )
        ax.set_xlabel("Амплитуда, °C" if product == "LST" else "NDVI")
        ax.set_title(f"Сезонная амплитуда ({product})")
        ax.grid(axis="x", alpha=0.3)

        # Подписи значений
        for bar in bars:
            width = bar.get_width()
            ax.text(
                width + 0.1,
                bar.get_y() + bar.get_height() / 2,
                f"{width:.2f}",
                va="center",
                fontsize=9,
            )

        if save:
            path = self.output_dir / f"amplitude_{product.lower()}.png"
            fig.savefig(path, dpi=300, bbox_inches="tight")
            print(MSG_SAVED.format(path))
        plt.close()

    def export_summary_table(self, save: bool = True):
        """Экспорт сводной таблицы"""
        rows = []
        for product in ["LST", "NDVI"]:
            for zone in ZONE_ORDER:
                subset = self.df[
                    (self.df["product"] == product) & (self.df["zone_name"] == zone)
                ]
                if subset.empty:
                    continue

                yearly = subset.groupby("year")["mean"].mean()
                trend, p_val = np.nan, np.nan
                if len(yearly) >= 5:
                    x = yearly.index.astype(float)
                    slope, _, _, p_val, _ = stats.linregress(x, yearly.values)
                    trend = slope * 10

                rows.append(
                    {
                        "product": product,
                        "zone": zone,
                        "mean": subset["mean"].mean(),
                        "std": subset["mean"].std(),
                        "trend_10yr": trend,
                        "p_value": p_val,
                        "n": len(subset),
                    }
                )

        df_out = pd.DataFrame(rows)
        if save:
            path = self.output_dir / "summary_statistics.csv"
            df_out.to_csv(path, index=False, encoding="utf-8-sig", sep=";", decimal=",")
            print(MSG_SAVED.format(path))
        return df_out

    def export_trend_significance(self, save: bool = True):
        """Экспорт таблицы со значимостью трендов"""
        rows = []
        for product in ["LST", "NDVI"]:
            for zone in ZONE_ORDER:
                subset = self.df[
                    (self.df["product"] == product) & (self.df["zone_name"] == zone)
                ]
                if subset.empty:
                    continue

                yearly = subset.groupby("year")["mean"].mean()
                if len(yearly) < 5:
                    continue

                x = yearly.index.astype(float)
                slope, _, r, p_val, _ = stats.linregress(x, yearly.values)
                rows.append(
                    {
                        "product": product,
                        "zone": zone,
                        "trend_per_year": slope,
                        "trend_per_10yr": slope * 10,
                        "r_squared": r**2,
                        "p_value": p_val,
                        "significant_0.05": p_val < 0.05,
                        "significant_0.1": p_val < 0.1,
                        "n_years": len(yearly),
                    }
                )

        df_out = pd.DataFrame(rows)
        if save:
            path = self.output_dir / "trend_significance.csv"
            df_out.to_csv(path, index=False, encoding="utf-8-sig", sep=";", decimal=",")
            print(MSG_SAVED.format(path))
        return df_out

    def export_monthly_aggregated(self, save: bool = True):
        """Экспорт ежемесячных средних для всех зон"""
        agg = (
            self.df.groupby(["zone_name", "year", "month", "product"])["mean"]
            .agg(["mean", "std", "count", "min", "max"])
            .reset_index()
        )

        if save:
            path = self.output_dir / "monthly_aggregated.csv"
            agg.to_csv(path, index=False, encoding="utf-8-sig", sep=";", decimal=",")
            print(MSG_SAVED.format(path))
        return agg

    def run_all(self):
        """Запуск всех визуализаций"""
        print("\n[1/8] Сезонная динамика...")
        self.plot_seasonal_dynamics("LST")
        self.plot_seasonal_dynamics("NDVI")

        print("[2/8] Межгодовые тренды...")
        self.plot_interannual_trends("LST")
        self.plot_interannual_trends("NDVI")

        print("[3/8] Широтный градиент (Июль)...")
        self.plot_latitudinal_gradient("LST", month=7)
        self.plot_latitudinal_gradient("NDVI", month=7)

        print("[4/8] Сезонная амплитуда...")
        self.plot_seasonal_amplitude("LST")
        self.plot_seasonal_amplitude("NDVI")

        print("[5/8] Корреляция LST–NDVI...")
        self.plot_lst_ndvi_correlation(month=7)

        print("[6/8] Сводная таблица...")
        self.export_summary_table()

        print("[7/8] Таблица значимости трендов...")
        self.export_trend_significance()

        print("[8/8] Экспорт агрегированных данных...")
        self.export_monthly_aggregated()

        print("\nЗавершено. Все графики и таблицы в:", self.output_dir)


def main():
    """Точка входа"""
    input_csv = os.path.join(DATA_PATHS["tables"], "zonal_stats_monthly.csv")
    output_dir = os.path.join(DATA_PATHS["figures"], "analysis")

    if not os.path.exists(input_csv):
        print(MSG_ERROR_FILE.format(input_csv))
        sys.exit(1)

    try:
        analyzer = MODISAnalyzer(input_csv, output_dir)
        analyzer.run_all()
    except Exception as e:
        print(MSG_ERROR.format(e))
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
