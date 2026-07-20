"""
Анализ и визуализация результатов зональной статистики.
Включает: сезонную динамику, тренды, корреляцию, широтный градиент, амплитуду.
"""

import warnings
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams
from scipy import stats
from pathlib import Path
from datetime import datetime

from config import DATA_PATHS, LOG_DATE_FORMAT
from utils.logger import setup_logger
from utils.geo_utils import generate_zone_colors
from utils import messages

try:
    rcParams["font.family"] = "DejaVu Sans"
    rcParams["font.size"] = 10
    rcParams["axes.unicode_minus"] = False
    rcParams["figure.dpi"] = 300
    rcParams["savefig.dpi"] = 300
    rcParams["savefig.bbox"] = "tight"
    rcParams["savefig.pad_inches"] = 0.1
except RuntimeError:
    pass

warnings.filterwarnings("ignore")
logger = setup_logger(__name__)


class MODISAnalyzer:
    """Анализ и визуализация данных MODIS."""

    def __init__(self, data_path: Path, output_dir: Path):
        """Инициализация анализатора."""
        self.data_path = data_path
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(messages.MSG_LOADING.format(self.data_path))
        if not self.data_path.exists():
            raise FileNotFoundError(messages.ERR_FILE_NOT_FOUND.format(self.data_path))

        try:
            self.df = pd.read_csv(
                self.data_path, sep=";", decimal=",", encoding="utf-8-sig"
            )
            self.df.columns = self.df.columns.str.strip().str.replace(
                "\ufeff", "", regex=False
            )
        except (pd.errors.EmptyDataError, pd.errors.ParserError) as e:
            raise ValueError(
                messages.ERR_CSV_READ_FAILED.format(self.data_path, str(e))
            )

        numeric_cols = [
            "mean",
            "std",
            "median",
            "min",
            "max",
            "pixel_count",
            "lat_center",
            "lon_center",
        ]
        for col in numeric_cols:
            if col in self.df.columns:
                self.df[col] = pd.to_numeric(self.df[col], errors="coerce")

        self._preprocess_data()
        zone_names = self.df["zone_name"].unique().tolist()
        self.zone_colors = generate_zone_colors(zone_names)
        self.zone_order = sorted(zone_names)
        logger.info(messages.MSG_LOADED.format(len(self.df)))

    def _preprocess_data(self):
        """Фильтрация и подготовка данных."""
        if "month" in self.df.columns:
            self.df["month"] = (
                pd.to_numeric(self.df["month"], errors="coerce").fillna(0).astype(int)
            )
        if "year" in self.df.columns:
            self.df["year"] = pd.to_numeric(self.df["year"], errors="coerce")

        required_cols = ["month", "mean", "pixel_count"]
        if not all(col in self.df.columns for col in required_cols):
            logger.warning(messages.WARN_MISSING_COLS.format(required_cols))
            return

        mask = (
            self.df["month"].isin(range(1, 13))
            & (~self.df["mean"].isna())
            & (self.df["pixel_count"] > 0)
        )
        self.df = self.df[mask].copy()

    def _get_color(self, zone_name: str) -> str:
        """Возврат цвета для зоны."""
        return self.zone_colors.get(zone_name, "gray")

    def plot_seasonal_dynamics(self, product: str, save: bool = True):
        """Сезонная динамика по месяцам."""
        if "zone_name" not in self.df.columns or "month" not in self.df.columns:
            logger.warning(
                messages.LOG_ANALYSIS_WARN.format(
                    "Сезонная динамика", "zone_name или month"
                )
            )
            return

        agg = (
            self.df[self.df["product"] == product]
            .groupby(["zone_name", "month"])["mean"]
            .agg(["mean", "std", "count"])
            .reset_index()
        )
        agg = agg[agg["count"] >= 1]

        fig, ax = plt.subplots(figsize=(10, 6))
        for zone in self.zone_order:
            data = agg[agg["zone_name"] == zone]
            if data.empty:
                continue
            ax.errorbar(
                data["month"],
                data["mean"],
                yerr=data["std"],
                label=zone,
                color=self._get_color(zone),
                marker="o",
                capsize=3,
                linewidth=1.5,
            )

        ax.set_title(f"Сезонная динамика ({product})")
        ax.set_xlabel("Месяц")
        ax.set_ylabel("Температура, °C" if product == "LST" else "NDVI")
        ax.legend(title="Зона", frameon=True)
        ax.grid(axis="y", alpha=0.3)

        if save:
            path = self.output_dir / f"seasonal_{product.lower()}.png"
            fig.savefig(path)
            logger.info(messages.LOG_ANALYSIS_OK.format(path))
        plt.close(fig)

    def plot_interannual_trends(self, product: str, save: bool = True):
        """Межгодовые тренды."""
        if "zone_name" not in self.df.columns or "year" not in self.df.columns:
            logger.warning(
                messages.LOG_ANALYSIS_WARN.format("Тренды", "zone_name или year")
            )
            return

        fig, ax = plt.subplots(figsize=(11, 6))
        for zone in self.zone_order:
            subset = self.df[
                (self.df["product"] == product) & (self.df["zone_name"] == zone)
            ]
            if subset.empty:
                continue

            yearly = subset.groupby("year")["mean"].mean()
            if len(yearly) < 2:
                continue

            x = yearly.index.astype(float)
            y = yearly.values
            color = self._get_color(zone)
            ax.plot(x, y, label=zone, color=color, marker="o")

            if len(yearly) >= 3:
                slope, intercept, _, p_val, _ = stats.linregress(x, y)
                ax.plot(x, x * slope + intercept, linestyle=":", alpha=0.5, color=color)

        ax.set_title(f"Межгодовая динамика ({product})")
        ax.set_xlabel("Год")
        ax.set_ylabel("Темп., °C" if product == "LST" else "NDVI")
        ax.legend(title="Зона", ncol=2)
        ax.grid(alpha=0.3)

        if save:
            path = self.output_dir / f"trend_{product.lower()}.png"
            fig.savefig(path)
            logger.info(messages.LOG_ANALYSIS_OK.format(path))
        plt.close(fig)

    def plot_lst_ndvi_correlation(self, month: int = 7, save: bool = True):
        """Корреляция LST и NDVI."""
        if "zone_name" not in self.df.columns or "year" not in self.df.columns:
            logger.warning(
                messages.LOG_ANALYSIS_WARN.format("Корреляция", "zone_name или year")
            )
            return

        lst = self.df[(self.df["product"] == "LST") & (self.df["month"] == month)][
            ["zone_name", "year", "mean"]
        ].copy()
        ndvi = self.df[(self.df["product"] == "NDVI") & (self.df["month"] == month)][
            ["zone_name", "year", "mean"]
        ].copy()

        if lst.empty or ndvi.empty:
            logger.warning("Недостаточно данных для корреляции LST-NDVI.")
            return

        lst.columns = ["zone_name", "year", "LST"]
        ndvi.columns = ["zone_name", "year", "NDVI"]
        merged = pd.merge(lst, ndvi, on=["zone_name", "year"], how="inner")
        merged = merged[merged["LST"].notna() & merged["NDVI"].notna()]

        if merged.empty:
            logger.warning("Нет общих точек для корреляции.")
            return

        fig, ax = plt.subplots(figsize=(8, 7))
        for zone in self.zone_order:
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

            if len(data) >= 3:
                r, _ = stats.pearsonr(data["LST"], data["NDVI"])
                ax.text(
                    0.05,
                    0.95 - 0.1 * self.zone_order.index(zone),
                    f"{zone}: r={r:.2f}",
                    transform=ax.transAxes,
                    fontsize=8,
                    color=color,
                    va="top",
                )

        ax.set_xlabel("Температура, °C")
        ax.set_ylabel("NDVI")
        ax.set_title(f"Корреляция LST-NDVI (месяц {month})")
        ax.legend(frameon=True)
        ax.grid(alpha=0.3)

        if save:
            path = self.output_dir / f"correlation_m{month}.png"
            fig.savefig(path)
            logger.info(messages.LOG_ANALYSIS_OK.format(path))
        plt.close(fig)

    def plot_latitudinal_gradient(
        self, product: str, month: int = 7, save: bool = True
    ):
        """Широтный градиент."""
        if "lat_center" not in self.df.columns:
            logger.warning(messages.LOG_ANALYSIS_NO_LAT)
            return

        subset = self.df[
            (self.df["product"] == product)
            & (self.df["month"] == month)
            & (self.df["lat_center"].notna())
        ]
        if subset.empty:
            logger.warning(messages.LOG_ANALYSIS_NO_DATA.format(product, month))
            return

        subset = subset.copy()
        subset["lat_bin"] = (subset["lat_center"] // 2) * 2
        agg = (
            subset.groupby("lat_bin")["mean"]
            .agg(["mean", "std", "count"])
            .reset_index()
        )
        agg = agg[agg["count"] >= 1]

        fig, ax = plt.subplots(figsize=(9, 6))
        ax.errorbar(
            agg["lat_bin"],
            agg["mean"],
            yerr=agg["std"],
            fmt="o",
            capsize=3,
            label="Данные",
            color="blue",
        )

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
        ax.set_title(f"Широтный градиент (месяц {month})")
        ax.legend()
        ax.grid(alpha=0.3)

        if save:
            path = self.output_dir / f"gradient_{product.lower()}_m{month}.png"
            fig.savefig(path, dpi=300)
            logger.info(messages.LOG_ANALYSIS_OK.format(path))
        plt.close()

    def plot_seasonal_amplitude(self, product: str, save: bool = True):
        """Амплитуда сезонных колебаний."""
        agg = (
            self.df[self.df["product"] == product]
            .groupby("zone_name")["mean"]
            .agg(["min", "max"])
            .reset_index()
        )
        agg["amplitude"] = agg["max"] - agg["min"]
        agg = agg[agg["zone_name"].isin(self.zone_order)]

        fig, ax = plt.subplots(figsize=(10, 6))
        bars = ax.barh(
            agg["zone_name"],
            agg["amplitude"],
            color=[self._get_color(z) for z in agg["zone_name"]],
        )
        ax.set_xlabel("Амплитуда, °C" if product == "LST" else "NDVI")
        ax.set_title(f"Сезонная амплитуда ({product})")
        ax.grid(axis="x", alpha=0.3)

        for bar in bars:
            ax.text(
                bar.get_width() + 0.1,
                bar.get_y() + bar.get_height() / 2,
                f"{bar.get_width():.2f}",
                va="center",
                fontsize=9,
            )

        if save:
            path = self.output_dir / f"amplitude_{product.lower()}.png"
            fig.savefig(path, dpi=300, bbox_inches="tight")
            logger.info(messages.LOG_ANALYSIS_OK.format(path))
        plt.close()

    def export_summary_table(self, save: bool = True):
        """Экспорт сводной таблицы."""
        rows = []
        products = self.df["product"].unique().tolist()
        for product in products:
            for zone in self.zone_order:
                subset = self.df[
                    (self.df["product"] == product) & (self.df["zone_name"] == zone)
                ]
                if subset.empty:
                    continue

                yearly = subset.groupby("year")["mean"].mean()
                trend, p_val = np.nan, np.nan
                if len(yearly) >= 3:
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
            logger.info(messages.LOG_ANALYSIS_OK.format(path))
        return df_out

    def export_trend_significance(self, save: bool = True):
        """Экспорт таблицы значимости трендов."""
        rows = []
        products = self.df["product"].unique().tolist()
        for product in products:
            for zone in self.zone_order:
                subset = self.df[
                    (self.df["product"] == product) & (self.df["zone_name"] == zone)
                ]
                if subset.empty:
                    continue

                yearly = subset.groupby("year")["mean"].mean()
                if len(yearly) < 3:
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
            logger.info(messages.LOG_ANALYSIS_OK.format(path))
        return df_out

    def export_monthly_aggregated(self, save: bool = True):
        """Экспорт ежемесячных средних."""
        agg = (
            self.df.groupby(["zone_name", "year", "month", "product"])["mean"]
            .agg(["mean", "std", "count", "min", "max"])
            .reset_index()
        )
        if save:
            path = self.output_dir / "monthly_aggregated.csv"
            agg.to_csv(path, index=False, encoding="utf-8-sig", sep=";", decimal=",")
            logger.info(messages.LOG_ANALYSIS_OK.format(path))
        return agg

    def run_all(self, products: list = None):
        """Запуск всех визуализаций и экспорта."""
        if products is None:
            products = ["LST", "NDVI"]

        available_products = self.df["product"].unique().tolist()
        products = [p for p in products if p in available_products]

        if not products:
            logger.warning("Нет данных для выбранных продуктов.")
            return

        logger.info("\n[1/7] Сезонная динамика...")
        for product in products:
            self.plot_seasonal_dynamics(product)

        logger.info("[2/7] Межгодовые тренды...")
        for product in products:
            self.plot_interannual_trends(product)

        logger.info("[3/7] Широтный градиент...")
        for product in products:
            self.plot_latitudinal_gradient(product, month=7)

        logger.info("[4/7] Сезонная амплитуда...")
        for product in products:
            self.plot_seasonal_amplitude(product)

        logger.info("[5/7] Корреляция LST-NDVI...")
        if "LST" in products and "NDVI" in products:
            self.plot_lst_ndvi_correlation(month=7)
        else:
            logger.info(messages.INFO_SKIP_CORRELATION)

        logger.info("[6/7] Сводные таблицы...")
        self.export_summary_table()
        self.export_trend_significance()
        self.export_monthly_aggregated()

        logger.info("\nЗавершено.")
        logger.info(f"Графики: {self.output_dir}")


def main(args):
    """Главная функция анализа."""
    logger.info(messages.SEPARATOR)
    logger.info(messages.HEADER_ANALYZER)
    logger.info(messages.SEPARATOR)

    logger.info(
        messages.STATUS_START_TIME.format(datetime.now().strftime(LOG_DATE_FORMAT))
    )

    input_csv = DATA_PATHS["tables"] / "zonal_stats_flat.csv"
    output_dir = (
        args.output_dir if args.output_dir else DATA_PATHS["figures"] / "analysis"
    )

    if not input_csv.exists():
        logger.error(messages.ERR_FILE_NOT_FOUND.format(input_csv))
        return

    products = ["LST", "NDVI"] if args.product == "all" else [args.product]

    try:
        analyzer = MODISAnalyzer(input_csv, output_dir)
        analyzer.run_all(products=products)
        logger.info(
            messages.STATUS_END_TIME.format(datetime.now().strftime(LOG_DATE_FORMAT))
        )
    except (FileNotFoundError, ValueError, pd.errors.EmptyDataError) as e:
        logger.error(messages.ERR_CRITICAL.format(str(e)))
        import traceback

        traceback.print_exc()
