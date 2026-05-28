# -*- coding: utf-8 -*-
"""Визуализация результатов: сезонная динамика, градиенты, тренды."""

import os
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams
import numpy as np
from scipy import stats
from src import constants as C
from src import messages as M
from src import logger

rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.unicode_minus": False,
        "figure.dpi": C.PLOT_DPI,
        "savefig.dpi": C.PLOT_DPI,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.1,
    }
)


def plot_seasonal_curve(data_df, product, output_path):
    """Строит график сезонной динамики по месяцам. Сохраняет в output_path."""
    subset = data_df[data_df["product"] == product]
    if subset.empty:
        logger.warning(M.ERR_NO_DATA_PLOT.format(product=product))
        return

    agg = (
        subset.groupby(["zone_name", "month"])["mean"]
        .agg(["mean", "std", "count"])
        .reset_index()
    )
    agg = agg[agg["count"] >= 3]

    fig, ax = plt.subplots(figsize=C.PLOT_FIGSIZE_DEFAULT)
    for zone in C.ZONE_ORDER:
        zone_data = agg[agg["zone_name"] == zone]
        if zone_data.empty:
            continue
        color = C.ZONE_COLORS.get(zone, "gray")
        months = [C.MONTH_NAMES.get(m, m) for m in zone_data["month"]]
        ax.errorbar(
            months,
            zone_data["mean"],
            yerr=zone_data["std"],
            label=zone,
            color=color,
            marker="o",
            capsize=3,
            linewidth=1.5,
        )

    ax.set_xlabel("Месяц")
    ax.set_ylabel("Температура, °C" if product == "LST" else "NDVI")
    ax.set_title("Сезонная динамика ({})".format(product))
    ax.legend(title="Природная зона", frameon=True)
    ax.grid(axis="y", alpha=0.3)
    fig.savefig(output_path)
    plt.close(fig)
    logger.info(M.MSG_SAVED.format(path=output_path))


def plot_latitudinal_gradient(data_df, product, month, output_path):
    """Строит график широтного градиента для заданного месяца."""
    subset = data_df[
        (data_df["product"] == product)
        & (data_df["month"] == month)
        & data_df["lat_center"].notna()
    ]
    if subset.empty:
        return

    subset = subset.copy()
    subset["lat_bin"] = (subset["lat_center"] // 2) * 2
    agg = subset.groupby("lat_bin")["mean"].agg(["mean", "std", "count"]).reset_index()
    agg = agg[agg["count"] >= 10]

    fig, ax = plt.subplots(figsize=C.PLOT_FIGSIZE_DEFAULT)
    ax.errorbar(
        agg["lat_bin"], agg["mean"], yerr=agg["std"], fmt="o", capsize=3, label="Данные"
    )
    if len(agg) >= 3:
        slope, intercept, _, _, _ = stats.linregress(agg["lat_bin"], agg["mean"])
        x_fit = np.array([agg["lat_bin"].min(), agg["lat_bin"].max()])
        ax.plot(
            x_fit, intercept + slope * x_fit, "r--", label="Тренд: {:.2f}".format(slope)
        )
    ax.set_xlabel("Широта, ° с.ш.")
    ax.set_ylabel("Значение")
    ax.set_title(
        "Широтный градиент ({} - {})".format(product, C.MONTH_NAMES.get(month, month))
    )
    ax.legend()
    ax.grid(alpha=0.3)
    fig.savefig(output_path)
    plt.close(fig)
    logger.info(M.MSG_SAVED.format(path=output_path))


def plot_interannual_trend(data_df, product, zone, output_path):
    """Строит график межгодового тренда для конкретной зоны."""
    subset = data_df[(data_df["product"] == product) & (data_df["zone_name"] == zone)]
    if subset.empty:
        return

    yearly = subset.groupby("year")["mean"].mean()
    fig, ax = plt.subplots(figsize=C.PLOT_FIGSIZE_DEFAULT)
    ax.plot(
        yearly.index,
        yearly.values,
        label=zone,
        marker="o",
        color=C.ZONE_COLORS.get(zone, "blue"),
    )
    if len(yearly) >= 5:
        slope, intercept, _, p_val, _ = stats.linregress(
            yearly.index.astype(float), yearly.values
        )
        ax.plot(
            yearly.index,
            yearly.index * slope + intercept,
            linestyle=":",
            alpha=0.5,
            color="red",
            label="Тренд",
        )
    ax.set_xlabel("Год")
    ax.set_ylabel("Значение")
    ax.set_title("Межгодовая динамика ({}, {})".format(zone, product))
    ax.legend()
    ax.grid(alpha=0.3)
    fig.savefig(output_path)
    plt.close(fig)
    logger.info(M.MSG_SAVED.format(path=output_path))
