"""Анализ и визуализация результатов зональной статистики.

Включает: сезонную динамику, тренды, корреляцию, широтный градиент, амплитуду.
"""

import warnings

import matplotlib
import numpy as np
import pandas as pd
from matplotlib.ticker import MultipleLocator

matplotlib.use('Agg')
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import rcParams
from scipy import stats

from config import DATA_PATHS, LOG_DATE_FORMAT, MODIS_PRODUCTS

from utils import messages
from utils.geo_utils import generate_zone_colors
from utils.logger import setup_logger
from utils.provenance import save_run_provenance

try:
    rcParams['font.family'] = 'DejaVu Sans'
    rcParams['font.size'] = 10
    rcParams['axes.unicode_minus'] = False
    rcParams['figure.dpi'] = 300
    rcParams['savefig.dpi'] = 300
    rcParams['savefig.bbox'] = 'tight'
    rcParams['savefig.pad_inches'] = 0.1
except RuntimeError:
    pass

warnings.filterwarnings('ignore')
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
            raise FileNotFoundError(
                messages.ERR_FILE_NOT_FOUND.format(self.data_path),
            )

        try:
            self.df = pd.read_csv(
                self.data_path,
                sep=';',
                decimal=',',
                encoding='utf-8-sig',
            )
            self.df.columns = self.df.columns.str.strip().str.replace(
                '\ufeff',
                '',
                regex=False,
            )
        except (pd.errors.EmptyDataError, pd.errors.ParserError) as e:
            raise ValueError(
                messages.ERR_CSV_READ_FAILED.format(self.data_path, str(e)),
            )

        numeric_cols = [
            'mean',
            'std',
            'median',
            'min',
            'max',
            'pixel_count',
            'lat_center',
            'lon_center',
        ]
        for col in numeric_cols:
            if col in self.df.columns:
                self.df[col] = pd.to_numeric(self.df[col], errors='coerce')

        self._preprocess_data()
        zone_names = self.df['zone_name'].unique().tolist()
        self.zone_colors = generate_zone_colors(zone_names)
        self.zone_order = sorted(zone_names)
        logger.info(messages.MSG_LOADED.format(len(self.df)))

    def _get_unit(self, product: str) -> str:
        """Получение единицы измерения продукта из конфигурации."""
        return MODIS_PRODUCTS.get(product, {}).get('unit', 'значение')

    def _preprocess_data(self):
        """Фильтрация и подготовка данных."""
        if 'month' in self.df.columns:
            self.df['month'] = (
                pd.to_numeric(self.df['month'], errors='coerce')
                .fillna(0)
                .astype(int)
            )
        if 'year' in self.df.columns:
            self.df['year'] = pd.to_numeric(self.df['year'], errors='coerce')

        required_cols = ['month', 'mean', 'pixel_count']
        if not all(col in self.df.columns for col in required_cols):
            logger.warning(messages.WARN_MISSING_COLS.format(required_cols))
            return

        mask = (
            self.df['month'].isin(range(1, 13))
            & (~self.df['mean'].isna())
            & (self.df['pixel_count'] > 0)
        )
        self.df = self.df[mask].copy()

    def _get_color(self, zone_name: str) -> str:
        """Возврат цвета для зоны."""
        return self.zone_colors.get(zone_name, 'gray')

    def plot_seasonal_dynamics(self, product: str, save: bool = True):
        """Сезонная динамика по месяцам."""
        if (
            'zone_name' not in self.df.columns
            or 'month' not in self.df.columns
        ):
            logger.warning(
                messages.LOG_ANALYSIS_WARN.format(
                    'Сезонная динамика',
                    'zone_name или month',
                ),
            )
            return

        agg = (
            self.df[self.df['product'] == product]
            .groupby(['zone_name', 'month'])['mean']
            .agg(['mean', 'std', 'count'])
            .reset_index()
        )
        agg = agg[agg['count'] >= 1]

        fig, ax = plt.subplots(figsize=(10, 6))
        for zone in self.zone_order:
            data = agg[agg['zone_name'] == zone]
            if data.empty:
                continue
            ax.errorbar(
                data['month'],
                data['mean'],
                yerr=data['std'],
                label=zone,
                color=self._get_color(zone),
                marker='o',
                capsize=3,
                linewidth=1.5,
            )

        ax.set_title(f'Сезонная динамика ({product})')
        ax.set_xlabel('Месяц')
        ax.set_ylabel(f'{product} ({self._get_unit(product)})')
        ax.legend(title='Зона', frameon=True)
        ax.grid(axis='y', alpha=0.3)
        ax.xaxis.set_major_locator(MultipleLocator(1))

        if save:
            path = self.output_dir / f'seasonal_{product.lower()}.png'
            fig.savefig(path)
            logger.info(messages.LOG_ANALYSIS_OK.format(path))
        plt.close(fig)

    def plot_interannual_trends(self, product: str, save: bool = True):
        """Межгодовые тренды."""
        if 'zone_name' not in self.df.columns or 'year' not in self.df.columns:
            logger.warning(
                messages.LOG_ANALYSIS_WARN.format(
                    'Тренды',
                    'zone_name или year',
                ),
            )
            return

        fig, ax = plt.subplots(figsize=(11, 6))
        for zone in self.zone_order:
            subset = self.df[
                (self.df['product'] == product)
                & (self.df['zone_name'] == zone)
            ]
            if subset.empty:
                continue

            yearly = subset.groupby('year')['mean'].mean()
            if len(yearly) < 2:
                continue

            x = yearly.index.astype(float)
            y = yearly.values
            color = self._get_color(zone)
            ax.plot(x, y, label=zone, color=color, marker='o')

            if len(yearly) >= 3:
                slope, intercept, _, p_val, _ = stats.linregress(x, y)
                ax.plot(
                    x,
                    x * slope + intercept,
                    linestyle=':',
                    alpha=0.5,
                    color=color,
                )

        ax.set_title(f'Межгодовая динамика ({product})')
        ax.set_xlabel('Год')
        ax.set_ylabel(f'{product} ({self._get_unit(product)})')
        ax.legend(title='Зона', ncol=2)
        ax.grid(alpha=0.3)

        if save:
            path = self.output_dir / f'trend_{product.lower()}.png'
            fig.savefig(path)
            logger.info(messages.LOG_ANALYSIS_OK.format(path))
        plt.close(fig)

    def plot_product_correlation(
        self,
        product_x: str,
        product_y: str,
        month: int = 7,
        save: bool = True,
    ):
        """Универсальная корреляция двух продуктов."""
        if 'zone_name' not in self.df.columns or 'year' not in self.df.columns:
            logger.warning(
                messages.LOG_ANALYSIS_WARN.format(
                    'Корреляция',
                    'zone_name или year',
                ),
            )
            return

        df_x = self.df[
            (self.df['product'] == product_x) & (self.df['month'] == month)
        ][['zone_name', 'year', 'mean']].copy()
        df_y = self.df[
            (self.df['product'] == product_y) & (self.df['month'] == month)
        ][['zone_name', 'year', 'mean']].copy()

        if df_x.empty or df_y.empty:
            logger.warning(
                messages.INFO_SKIP_CORRELATION.format(product_x, product_y),
            )
            return

        df_x.columns = ['zone_name', 'year', f'val_{product_x}']
        df_y.columns = ['zone_name', 'year', f'val_{product_y}']

        merged = pd.merge(df_x, df_y, on=['zone_name', 'year'], how='inner')
        merged = merged[
            merged[f'val_{product_x}'].notna()
            & merged[f'val_{product_y}'].notna()
        ]

        if merged.empty:
            logger.warning(messages.WARN_CORRELATION_NO_DATA)
            return

        fig, ax = plt.subplots(figsize=(8, 7))
        for zone in self.zone_order:
            data = merged[merged['zone_name'] == zone]
            if data.empty:
                continue

            color = self._get_color(zone)
            ax.scatter(
                data[f'val_{product_x}'],
                data[f'val_{product_y}'],
                label=zone,
                color=color,
                alpha=0.6,
                s=20,
                edgecolors='white',
            )

            if len(data) >= 3:
                r, _ = stats.pearsonr(
                    data[f'val_{product_x}'],
                    data[f'val_{product_y}'],
                )
                ax.text(
                    0.05,
                    0.95 - 0.1 * self.zone_order.index(zone),
                    f'{zone}: r={r:.2f}',
                    transform=ax.transAxes,
                    fontsize=8,
                    color=color,
                    va='top',
                )

        ax.set_xlabel(f'{product_x} ({self._get_unit(product_x)})')
        ax.set_ylabel(f'{product_y} ({self._get_unit(product_y)})')
        ax.set_title(f'Корреляция {product_x} - {product_y} (месяц {month})')
        ax.legend(frameon=True)
        ax.grid(alpha=0.3)

        if save:
            path = (
                self.output_dir
                / f'correlation_{product_x.lower()}_{product_y.lower()}_m{month}.png'
            )
            fig.savefig(path)
            logger.info(messages.LOG_ANALYSIS_OK.format(path))
        plt.close(fig)

    def plot_latitudinal_gradient(
        self,
        product: str,
        month: int = 7,
        save: bool = True,
    ):
        """Широтный градиент."""
        if 'lat_center' not in self.df.columns:
            logger.warning(messages.LOG_ANALYSIS_NO_LAT)
            return

        subset = self.df[
            (self.df['product'] == product)
            & (self.df['month'] == month)
            & (self.df['lat_center'].notna())
        ]
        if subset.empty:
            logger.warning(
                messages.LOG_ANALYSIS_NO_DATA.format(product, month),
            )
            return

        subset = subset.copy()
        subset['lat_bin'] = (subset['lat_center'] // 2) * 2
        agg = (
            subset.groupby('lat_bin')['mean']
            .agg(['mean', 'std', 'count'])
            .reset_index()
        )
        agg = agg[agg['count'] >= 1]

        fig, ax = plt.subplots(figsize=(9, 6))
        ax.errorbar(
            agg['lat_bin'],
            agg['mean'],
            yerr=agg['std'],
            fmt='o',
            capsize=3,
            label='Данные',
            color='blue',
        )

        if len(agg) >= 3:
            slope, intercept, r, p, _ = stats.linregress(
                agg['lat_bin'],
                agg['mean'],
            )
            x_fit = np.array([agg['lat_bin'].min(), agg['lat_bin'].max()])
            ax.plot(
                x_fit,
                intercept + slope * x_fit,
                'r--',
                label=f'Тренд: {slope:.2f}',
            )
            ax.text(
                0.05,
                0.95,
                f'R²={r**2:.2f}\np={p:.3g}',
                transform=ax.transAxes,
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.3),
            )

        ax.set_xlabel('Широта, ° с.ш.')
        ax.set_ylabel(f'{product} ({self._get_unit(product)})')
        ax.set_title(f'Широтный градиент {product} (месяц {month})')
        ax.legend()
        ax.grid(alpha=0.3)

        if save:
            path = self.output_dir / f'gradient_{product.lower()}_m{month}.png'
            fig.savefig(path, dpi=300)
            logger.info(messages.LOG_ANALYSIS_OK.format(path))
        plt.close()

    def plot_seasonal_amplitude(self, product: str, save: bool = True):
        """Амплитуда сезонных колебаний."""
        agg = (
            self.df[self.df['product'] == product]
            .groupby('zone_name')['mean']
            .agg(['min', 'max'])
            .reset_index()
        )
        agg['amplitude'] = agg['max'] - agg['min']
        agg = agg[agg['zone_name'].isin(self.zone_order)]

        fig, ax = plt.subplots(figsize=(10, 6))
        bars = ax.barh(
            agg['zone_name'],
            agg['amplitude'],
            color=[self._get_color(z) for z in agg['zone_name']],
        )
        ax.set_xlabel(f'Амплитуда ({self._get_unit(product)})')
        ax.set_title(f'Сезонная амплитуда ({product})')
        ax.grid(axis='x', alpha=0.3)

        for bar in bars:
            ax.text(
                bar.get_width() + 0.1,
                bar.get_y() + bar.get_height() / 2,
                f'{bar.get_width():.2f}',
                va='center',
                fontsize=9,
            )

        if save:
            path = self.output_dir / f'amplitude_{product.lower()}.png'
            fig.savefig(path, dpi=300, bbox_inches='tight')
            logger.info(messages.LOG_ANALYSIS_OK.format(path))
        plt.close()

    def export_summary_table(self, save: bool = True):
        """Экспорт сводной таблицы."""
        rows = []
        products = self.df['product'].unique().tolist()
        for product in products:
            for zone in self.zone_order:
                subset = self.df[
                    (self.df['product'] == product)
                    & (self.df['zone_name'] == zone)
                ]
                if subset.empty:
                    continue

                yearly = subset.groupby('year')['mean'].mean()
                trend, p_val = np.nan, np.nan
                if len(yearly) >= 3:
                    x = yearly.index.astype(float)
                    slope, _, _, p_val, _ = stats.linregress(x, yearly.values)
                    trend = slope * 10

                rows.append(
                    {
                        'product': product,
                        'zone': zone,
                        'mean': subset['mean'].mean(),
                        'std': subset['mean'].std(),
                        'trend_10yr': trend,
                        'p_value': p_val,
                        'n': len(subset),
                    },
                )

        df_out = pd.DataFrame(rows)
        if save:
            path = self.output_dir / 'summary_statistics.csv'
            df_out.to_csv(
                path,
                index=False,
                encoding='utf-8-sig',
                sep=';',
                decimal=',',
            )
            logger.info(messages.LOG_ANALYSIS_OK.format(path))
        return df_out

    def export_trend_significance(self, save: bool = True):
        """Экспорт таблицы значимости трендов."""
        rows = []
        products = self.df['product'].unique().tolist()
        for product in products:
            for zone in self.zone_order:
                subset = self.df[
                    (self.df['product'] == product)
                    & (self.df['zone_name'] == zone)
                ]
                if subset.empty:
                    continue

                yearly = subset.groupby('year')['mean'].mean()
                if len(yearly) < 3:
                    continue

                x = yearly.index.astype(float)
                slope, _, r, p_val, _ = stats.linregress(x, yearly.values)
                rows.append(
                    {
                        'product': product,
                        'zone': zone,
                        'trend_per_year': slope,
                        'trend_per_10yr': slope * 10,
                        'r_squared': r**2,
                        'p_value': p_val,
                        'significant_0.05': p_val < 0.05,
                        'significant_0.1': p_val < 0.1,
                        'n_years': len(yearly),
                    },
                )

        df_out = pd.DataFrame(rows)
        if save:
            path = self.output_dir / 'trend_significance.csv'
            df_out.to_csv(
                path,
                index=False,
                encoding='utf-8-sig',
                sep=';',
                decimal=',',
            )
            logger.info(messages.LOG_ANALYSIS_OK.format(path))
        return df_out

    def export_monthly_aggregated(self, save: bool = True):
        """Экспорт ежемесячных средних."""
        agg = (
            self.df.groupby(['zone_name', 'year', 'month', 'product'])['mean']
            .agg(['mean', 'std', 'count', 'min', 'max'])
            .reset_index()
        )
        if save:
            path = self.output_dir / 'monthly_aggregated.csv'
            agg.to_csv(
                path,
                index=False,
                encoding='utf-8-sig',
                sep=';',
                decimal=',',
            )
            logger.info(messages.LOG_ANALYSIS_OK.format(path))
        return agg

    def export_excel(self, path: Path):
        """Экспорт всех таблиц в один Excel-файл с несколькими листами."""
        logger.info(messages.INFO_CREATING_EXCEL.format(path))
        sheets = {
            'flat': self.df,
            'monthly': self.export_monthly_aggregated(save=False),
            'summary': self.export_summary_table(save=False),
            'trends': self.export_trend_significance(save=False),
        }
        logger.info(messages.INFO_EXCEL_SHEETS.format(', '.join(sheets)))
        try:
            with pd.ExcelWriter(path, engine='openpyxl') as writer:
                for sheet, df in sheets.items():
                    df.to_excel(writer, sheet_name=sheet, index=False)
            logger.info(messages.INFO_EXCEL_SAVED.format(path))
        except ImportError:
            logger.error(messages.ERR_EXCEL_NO_OPENPYXL)

    def run_all(self, products: list = None):
        """Запуск всех визуализаций и экспорта."""
        available_products = self.df['product'].unique().tolist()
        if products is None:
            products = available_products
        else:
            products = [p for p in products if p in available_products]

        if not products:
            logger.warning(messages.INFO_NO_PRODUCTS)
            return

        # Репрезентативный месяц: июль если доступен.
        available_months = sorted(self.df['month'].unique())
        if 7 in available_months:
            target_month = 7
        elif available_months:
            target_month = available_months[len(available_months) // 2]
        else:
            target_month = 7

        logger.info(messages.ANALYSIS_STEP_SEASONAL)
        for product in products:
            self.plot_seasonal_dynamics(product)

        logger.info(messages.ANALYSIS_STEP_TRENDS)
        for product in products:
            self.plot_interannual_trends(product)

        logger.info(messages.ANALYSIS_STEP_GRADIENT.format(target_month))
        for product in products:
            self.plot_latitudinal_gradient(product, month=target_month)

        logger.info(messages.ANALYSIS_STEP_AMPLITUDE)
        for product in products:
            self.plot_seasonal_amplitude(product)

        logger.info(messages.ANALYSIS_STEP_CORRELATION.format(target_month))
        if len(products) >= 2:
            self.plot_product_correlation(
                products[0],
                products[1],
                month=target_month,
            )
        else:
            logger.info(messages.INFO_SKIP_CORRELATION.format('N/A', 'N/A'))

        logger.info(messages.ANALYSIS_STEP_TABLES)
        self.export_summary_table()
        self.export_trend_significance()
        self.export_monthly_aggregated()

        logger.info(f'\n{messages.INFO_ANALYSIS_DONE}')
        logger.info(messages.INFO_FIGURES_DIR.format(self.output_dir))


def main(args):
    """Главная функция анализа."""
    logger.info(messages.SEPARATOR)
    logger.info(messages.HEADER_ANALYZER)
    logger.info(messages.SEPARATOR)
    logger.info(
        messages.STATUS_START_TIME.format(
            datetime.now().strftime(LOG_DATE_FORMAT),
        ),
    )

    # 1. Сначала определяем пути и продукты
    input_csv = DATA_PATHS['tables'] / 'zonal_stats_flat.csv'
    output_dir = args.output_dir if args.output_dir else DATA_PATHS['figures']

    if not input_csv.exists():
        logger.error(messages.ERR_FILE_NOT_FOUND.format(input_csv))
        return

    products = (
        list(MODIS_PRODUCTS.keys())
        if args.product == 'all'
        else [args.product]
    )

    # 2. Сохраняем провенанс (теперь переменные существуют)
    save_run_provenance(
        '05_analyze',
        {
            'product': args.product,
            'output_dir': str(output_dir),
            'excel': args.excel,
        },
    )

    # 3. Запускаем анализ
    try:
        analyzer = MODISAnalyzer(input_csv, output_dir)
        analyzer.run_all(products=products)

        if args.excel:
            analyzer.export_excel(
                DATA_PATHS['tables_output'] / 'modis_analysis.xlsx',
            )

        logger.info(
            messages.STATUS_END_TIME.format(
                datetime.now().strftime(LOG_DATE_FORMAT),
            ),
        )
    except (FileNotFoundError, ValueError, pd.errors.EmptyDataError) as e:
        logger.error(messages.ERR_CRITICAL.format(str(e)))
