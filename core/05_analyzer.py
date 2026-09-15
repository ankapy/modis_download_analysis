"""Анализ и визуализация результатов зональной статистики.

Сезонность, тренды, градиент, амплитуда, аномалии, фенология,
корреляции, PCA и широкие таблицы.
"""

import warnings
from datetime import datetime

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import rcParams
from matplotlib.ticker import MultipleLocator
from scipy import stats

from config import (
    ANOMALY_BASELINE_YEARS,
    DATA_PATHS,
    DATA_TYPE_CATEGORICAL,
    LOG_DATE_FORMAT,
    MODIS_PRODUCTS,
    PHENOLOGY_THRESHOLD_FRACTION,
)

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

PHENOLOGY_MIN_MONTHS = 5
EXCEL_FILENAME = 'modis_analysis.xlsx'
HELP_FILENAME = 'tables_help.csv'


class ExcelExporter:
    """Экспорт данных в Excel с листом HELP."""

    def __init__(self, analyzer):
        """Инициализация экспортера."""
        self.analyzer = analyzer

    def _help_dataframe(self):
        """Создание DataFrame с описанием всех листов."""
        sheets = self.analyzer._collect_sheets()
        return pd.DataFrame(
            [
                {
                    'table': name,
                    'description': meta[1],
                    'columns': ', '.join(str(c) for c in meta[0].columns),
                    'origin_x': meta[2],
                    'origin_y': meta[3],
                }
                for name, meta in sheets.items()
            ]
        )

    def export_help_csv(self, save=True):
        """Экспорт словаря таблиц в CSV."""
        df = self._help_dataframe()
        if save:
            path = self.analyzer.output_dir / HELP_FILENAME
            df.to_csv(
                path, index=False, encoding='utf-8-sig', sep=';', decimal=','
            )
            logger.info(messages.LOG_ANALYSIS_OK.format(path))
        return df

    def export_excel(self, path):
        """Экспорт Excel-книги с листом HELP."""
        sheets = self.analyzer._collect_sheets()
        logger.info(messages.INFO_CREATING_EXCEL.format(path))

        try:
            with pd.ExcelWriter(path, engine='openpyxl') as writer:
                self._help_dataframe().to_excel(
                    writer, sheet_name='HELP', index=False
                )
                for name, meta in sheets.items():
                    meta[0].to_excel(writer, sheet_name=name[:31], index=False)
            logger.info(messages.INFO_EXCEL_SAVED.format(path))
        except ImportError:
            logger.error(messages.ERR_EXCEL_NO_OPENPYXL)


class MODISAnalyzer:
    """Анализ и визуализация данных MODIS."""

    def __init__(self, data_path, output_dir):
        """Инициализация анализатора."""
        self.data_path = data_path
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(messages.MSG_LOADING.format(self.data_path))
        if not self.data_path.exists():
            raise FileNotFoundError(
                messages.ERR_FILE_NOT_FOUND.format(self.data_path)
            )

        try:
            self.df = pd.read_csv(
                self.data_path,
                sep=';',
                decimal=',',
                encoding='utf-8-sig',
            )
            self.df.columns = self.df.columns.str.strip().str.replace(
                '\ufeff', '', regex=False
            )
        except (pd.errors.EmptyDataError, pd.errors.ParserError) as e:
            raise ValueError(
                messages.ERR_CSV_READ_FAILED.format(self.data_path, str(e))
            )

        numeric_cols = [
            'mean',
            'std',
            'median',
            'min',
            'max',
            'p10',
            'p25',
            'p75',
            'p90',
            'cv',
            'shannon',
            'dominant_class',
            'n_classes',
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

    def _get_unit(self, product):
        """Получение единицы измерения продукта из конфигурации."""
        return MODIS_PRODUCTS.get(product, {}).get('unit', 'значение')

    def _get_color(self, zone_name):
        """Возврат цвета для зоны."""
        return self.zone_colors.get(zone_name, 'gray')

    def _is_categorical(self, product):
        """True, если продукт по конфигурации категориальный."""
        return (
            MODIS_PRODUCTS.get(product, {}).get('data_type')
            == DATA_TYPE_CATEGORICAL
        )

    def _metric_column(self, product):
        """Колонка с валидной метрикой продукта: mean или shannon."""
        return 'shannon' if self._is_categorical(product) else 'mean'

    def _product_rows(self, product):
        """Строки продукта с валидными значениями его типа."""
        metric = self._metric_column(product)
        mask = (self.df['product'] == product) & self.df[metric].notna()
        return self.df[mask]

    def _validate_product(self, product, required_cols=None):
        """Проверка наличия продукта и колонок."""
        if product not in self.df['product'].values:
            return False
        if required_cols:
            if not all(col in self.df.columns for col in required_cols):
                return False
        return True

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

        required_cols = ['month', 'pixel_count']
        if not all(col in self.df.columns for col in required_cols):
            logger.warning(messages.WARN_MISSING_COLS.format(required_cols))
            return

        has_mean = 'mean' in self.df.columns
        has_shannon = 'shannon' in self.df.columns

        if has_mean and has_shannon:
            keep = ~self.df['mean'].isna() | ~self.df['shannon'].isna()
        elif has_mean:
            keep = ~self.df['mean'].isna()
        elif has_shannon:
            keep = ~self.df['shannon'].isna()
        else:
            keep = pd.Series(False, index=self.df.index)

        mask = (
            self.df['month'].isin(range(1, 13))
            & keep
            & (self.df['pixel_count'] > 0)
        )
        self.df = self.df[mask].copy()

    def _save(self, fig, name, save):
        """Сохранение рисунка в файл."""
        if save:
            path = self.output_dir / name
            fig.savefig(path, dpi=300, bbox_inches='tight')
            logger.info(messages.LOG_ANALYSIS_OK.format(path))
        plt.close(fig)

    def _plot_base(self, figsize=(10, 6), title='', xlabel='', ylabel=''):
        """Базовая настройка графика (DRY)."""
        fig, ax = plt.subplots(figsize=figsize)
        if title:
            ax.set_title(title)
        if xlabel:
            ax.set_xlabel(xlabel)
        if ylabel:
            ax.set_ylabel(ylabel)
        return fig, ax

    def _monthly(self, product):
        """Среднее за месяц по зона-годам для непрерывного продукта."""
        if 'mean' not in self.df.columns:
            return pd.DataFrame(
                columns=['zone_name', 'year', 'month', 'value']
            )
        sub = self.df[
            (self.df['product'] == product) & self.df['mean'].notna()
        ]
        return (
            sub.groupby(['zone_name', 'year', 'month'])['mean']
            .mean()
            .reset_index(name='value')
        )

    def _wide_from_agg(self, agg, index_col):
        """Широкая таблица: индекс + по паре колонок mean/std на зону."""
        out = pd.DataFrame({index_col: sorted(agg[index_col].unique())})
        for zone in self.zone_order:
            z = agg[agg['zone_name'] == zone].set_index(index_col)
            out[f'{zone} mean'] = out[index_col].map(z['mean'])
            out[f'{zone} std'] = out[index_col].map(z['std'])
        return out

    def build_seasonal_wide(self, product):
        """Сезонный цикл: строки — месяцы, колонки — зоны (mean/std/cv)."""
        m = self._monthly(product)
        if m.empty:
            return pd.DataFrame()
        agg = (
            m.groupby(['zone_name', 'month'])['value']
            .agg(['mean', 'std'])
            .reset_index()
        )
        out = self._wide_from_agg(agg, 'month')
        for zone in self.zone_order:
            mean_col = f'{zone} mean'
            std_col = f'{zone} std'
            out[f'{zone} cv'] = out[std_col] / out[mean_col].replace(0, np.nan)
        return out

    def build_annual_wide(self, product):
        """Годовые ряды: строки — годы, колонки — зоны."""
        m = self._monthly(product)
        if m.empty:
            return pd.DataFrame()
        agg = (
            m.groupby(['zone_name', 'year'])['value']
            .agg(['mean', 'std'])
            .reset_index()
        )
        return self._wide_from_agg(agg, 'year')

    def build_boxplot_wide(self, product):
        """Сырые значения для boxplot: каждая колонка — зона."""
        if 'mean' not in self.df.columns:
            return pd.DataFrame()
        sub = self.df[
            (self.df['product'] == product) & self.df['mean'].notna()
        ]
        return pd.DataFrame(
            {
                zone: sub.loc[sub['zone_name'] == zone, 'mean'].reset_index(
                    drop=True
                )
                for zone in self.zone_order
            }
        )

    def build_heatmap_xyz(self, product):
        """XYZ для heatmap: десятичное время, зона, значение."""
        m = self._monthly(product).copy()
        if m.empty:
            return m
        m['time'] = m['year'] + (m['month'] - 0.5) / 12
        return (
            m[['time', 'zone_name', 'value']]
            .sort_values(['time', 'zone_name'])
            .reset_index(drop=True)
        )

    def _anomalies_long(self, product):
        """Месячные аномалии относительно нормы базового периода."""
        m = self._monthly(product)
        if m.empty:
            return m
        present = set(m['year'])
        base = [
            y
            for y in range(
                ANOMALY_BASELINE_YEARS[0], ANOMALY_BASELINE_YEARS[1] + 1
            )
            if y in present
        ]
        if not base:
            logger.warning(
                messages.WARN_BASELINE_MISSING.format(ANOMALY_BASELINE_YEARS)
            )
            base = sorted(present)
        clim = (
            m[m['year'].isin(base)]
            .groupby(['zone_name', 'month'])['value']
            .mean()
            .rename('clim')
        )
        m = m.merge(clim, on=['zone_name', 'month'], how='left')
        m['anomaly'] = m['value'] - m['clim']
        return m

    def build_anomalies_wide(self, product):
        """Годовые аномалии: строки — годы, колонки — зоны."""
        m = self._anomalies_long(product)
        if m.empty:
            return pd.DataFrame()
        annual = (
            m.groupby(['zone_name', 'year'])['anomaly'].mean().reset_index()
        )
        out = pd.DataFrame({'year': sorted(m['year'].unique())})
        for zone in self.zone_order:
            z = annual[annual['zone_name'] == zone].set_index('year')
            out[zone] = out['year'].map(z['anomaly'])
        return out

    def build_phenology(self, product):
        """Фенологические метрики по зона-годам из месячных средних."""
        rows = []
        m = self._monthly(product)
        if m.empty:
            return pd.DataFrame()

        for (zone, year), g in m.groupby(['zone_name', 'year']):
            g = g.sort_values('month')
            v = g['value'].to_numpy()
            months = g['month'].to_numpy()
            if len(v) < PHENOLOGY_MIN_MONTHS or np.isnan(v).any():
                continue
            vmin, vmax = np.nanmin(v), np.nanmax(v)
            thr = vmin + PHENOLOGY_THRESHOLD_FRACTION * (vmax - vmin)
            above = months[v >= thr]
            if above.size == 0:
                continue
            rows.append(
                {
                    'zone_name': zone,
                    'year': year,
                    'sos_month': int(above.min()),
                    'pos_month': int(months[np.nanargmax(v)]),
                    'eos_month': int(above.max()),
                    'los_months': int(above.max() - above.min() + 1),
                    'amplitude': float(vmax - vmin),
                    'season_integral': float(np.nansum(v)),
                }
            )
        return pd.DataFrame(rows)

    def build_categorical(self):
        """Метрики категориальных продуктов из плоской таблицы."""
        cols = [
            'zone_name',
            'year',
            'month',
            'product',
            'shannon',
            'dominant_class',
            'n_classes',
        ]
        if 'shannon' not in self.df.columns:
            return pd.DataFrame(columns=cols)

        existing_cols = [c for c in cols if c in self.df.columns]
        cat = self.df[self.df['shannon'].notna()]
        return cat[existing_cols].reset_index(drop=True)

    def build_corr_matrix(self, product):
        """Матрица корреляций зоны×зоны по месячным аномалиям."""
        m = self._anomalies_long(product)
        if m.empty:
            return pd.DataFrame()
        wide = m.pivot_table(
            index=['year', 'month'], columns='zone_name', values='anomaly'
        )
        return wide.corr()

    def build_pca(self, product):
        """PCA зон по сезонному циклу: scores, loadings, дисперсия."""
        m = self._monthly(product)
        if m.empty:
            return None

        mat = m.pivot_table(index='zone_name', columns='month', values='value')
        mat = mat.loc[[z for z in self.zone_order if z in mat.index]].dropna(
            axis=1
        )

        if mat.shape[0] < 3 or mat.shape[1] < 2 or mat.isna().any().any():
            return None

        data_matrix = mat.to_numpy()
        std_dev = data_matrix.std(axis=0)
        data_matrix = (data_matrix - data_matrix.mean(axis=0)) / np.where(
            std_dev > 0, std_dev, 1
        )

        u_mat, singular_vals, vt_mat = np.linalg.svd(
            data_matrix, full_matrices=False
        )
        evr = singular_vals**2 / np.sum(singular_vals**2)

        scores = pd.DataFrame(
            u_mat[:, :2] * singular_vals[:2],
            columns=['PC1', 'PC2'],
            index=mat.index,
        ).reset_index()

        loadings = pd.DataFrame(
            vt_mat[:2].T, columns=['PC1', 'PC2'], index=mat.columns
        ).reset_index()

        return scores, loadings, evr

    def plot_seasonal_dynamics(self, product, save=True):
        """Сезонная динамика по месяцам."""
        if not self._validate_product(product, ['zone_name', 'month', 'mean']):
            logger.warning(
                messages.LOG_ANALYSIS_WARN.format(
                    'Сезонная динамика', 'zone_name, month или mean'
                )
            )
            return

        agg = (
            self.df[(self.df['product'] == product) & self.df['mean'].notna()]
            .groupby(['zone_name', 'month'])['mean']
            .agg(['mean', 'std', 'count'])
            .reset_index()
        )
        agg = agg[agg['count'] >= 1]
        if agg.empty:
            return

        fig, ax = self._plot_base(
            figsize=(10, 6),
            title=f'Сезонная динамика ({product})',
            xlabel='Месяц',
            ylabel=f'{product} ({self._get_unit(product)})',
        )

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

        ax.legend(title='Зона', frameon=True)
        ax.grid(axis='y', alpha=0.3)
        ax.xaxis.set_major_locator(MultipleLocator(1))
        self._save(fig, f'seasonal_{product.lower()}.png', save)

    def plot_interannual_trends(self, product, save=True):
        """Межгодовые тренды."""
        if not self._validate_product(product, ['zone_name', 'year', 'mean']):
            logger.warning(
                messages.LOG_ANALYSIS_WARN.format(
                    'Тренды', 'zone_name, year или mean'
                )
            )
            return

        fig, ax = self._plot_base(
            figsize=(11, 6),
            title=f'Межгодовая динамика ({product})',
            xlabel='Год',
            ylabel=f'{product} ({self._get_unit(product)})',
        )

        has_data = False
        for zone in self.zone_order:
            subset = self.df[
                (self.df['product'] == product)
                & (self.df['zone_name'] == zone)
                & self.df['mean'].notna()
            ]
            if subset.empty:
                continue

            yearly = subset.groupby('year')['mean'].mean()
            if len(yearly) < 2:
                continue

            has_data = True
            x = yearly.index.astype(float)
            y = yearly.values
            color = self._get_color(zone)
            ax.plot(x, y, label=zone, color=color, marker='o')

            if len(yearly) >= 3:
                slope, intercept, _, _, _ = stats.linregress(x, y)
                ax.plot(
                    x,
                    x * slope + intercept,
                    linestyle=':',
                    alpha=0.5,
                    color=color,
                )

        if not has_data:
            plt.close(fig)
            return

        ax.legend(title='Зона', ncol=2)
        ax.grid(alpha=0.3)
        self._save(fig, f'trend_{product.lower()}.png', save)

    def plot_product_correlation(
        self, product_x, product_y, month=7, save=True
    ):
        """Универсальная корреляция двух продуктов."""
        if 'mean' not in self.df.columns:
            return

        df_x = self.df[
            (self.df['product'] == product_x) & (self.df['month'] == month)
        ][['zone_name', 'year', 'mean']].copy()
        df_y = self.df[
            (self.df['product'] == product_y) & (self.df['month'] == month)
        ][['zone_name', 'year', 'mean']].copy()

        if df_x.empty or df_y.empty:
            logger.warning(
                messages.INFO_SKIP_CORRELATION.format(product_x, product_y)
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

        fig, ax = self._plot_base(
            figsize=(8, 7),
            title=f'Корреляция {product_x} - {product_y} (месяц {month})',
            xlabel=f'{product_x} ({self._get_unit(product_x)})',
            ylabel=f'{product_y} ({self._get_unit(product_y)})',
        )

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
                    data[f'val_{product_x}'], data[f'val_{product_y}']
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

        ax.legend(frameon=True)
        ax.grid(alpha=0.3)
        self._save(
            fig,
            f'correlation_{product_x.lower()}_{product_y.lower()}_m{month}.png',
            save,
        )

    def plot_latitudinal_gradient(self, product, month=7, save=True):
        """Широтный градиент."""
        if not self._validate_product(product, ['lat_center', 'mean']):
            logger.warning(messages.LOG_ANALYSIS_NO_LAT)
            return

        subset = self.df[
            (self.df['product'] == product)
            & (self.df['month'] == month)
            & self.df['mean'].notna()
            & (self.df['lat_center'].notna())
        ]
        if subset.empty:
            logger.warning(
                messages.LOG_ANALYSIS_NO_DATA.format(product, month)
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

        fig, ax = self._plot_base(
            figsize=(9, 6),
            title=f'Широтный градиент {product} (месяц {month})',
            xlabel='Широта, ° с.ш.',
            ylabel=f'{product} ({self._get_unit(product)})',
        )

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
                agg['lat_bin'], agg['mean']
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

        ax.legend()
        ax.grid(alpha=0.3)
        self._save(fig, f'gradient_{product.lower()}_m{month}.png', save)

    def plot_seasonal_amplitude(self, product, save=True):
        """Амплитуда сезонных колебаний."""
        if 'mean' not in self.df.columns:
            return
        agg = (
            self.df[(self.df['product'] == product) & self.df['mean'].notna()]
            .groupby('zone_name')['mean']
            .agg(['min', 'max'])
            .reset_index()
        )
        if agg.empty:
            return

        agg['amplitude'] = agg['max'] - agg['min']
        agg = agg[agg['zone_name'].isin(self.zone_order)]

        fig, ax = self._plot_base(
            figsize=(10, 6),
            title=f'Сезонная амплитуда ({product})',
            xlabel=f'Амплитуда ({self._get_unit(product)})',
        )

        bars = ax.barh(
            agg['zone_name'],
            agg['amplitude'],
            color=[self._get_color(z) for z in agg['zone_name']],
        )
        ax.grid(axis='x', alpha=0.3)

        for bar in bars:
            ax.text(
                bar.get_width() + 0.1,
                bar.get_y() + bar.get_height() / 2,
                f'{bar.get_width():.2f}',
                va='center',
                fontsize=9,
            )
        self._save(fig, f'amplitude_{product.lower()}.png', save)

    def plot_boxplots(self, product, save=True):
        """Boxplot распределения значений по зонам."""
        data = self.build_boxplot_wide(product)
        if data.empty or data.dropna(how='all').empty:
            logger.warning(
                messages.LOG_ANALYSIS_WARN.format(
                    'Boxplot', 'валидных значений'
                )
            )
            return

        fig, ax = self._plot_base(
            figsize=(10, 6),
            title=f'Распределение значений по зонам ({product})',
            ylabel=f'{product} ({self._get_unit(product)})',
        )

        ax.boxplot(
            [data[z].dropna() for z in data.columns], labels=data.columns
        )
        ax.tick_params(axis='x', rotation=45)
        ax.grid(axis='y', alpha=0.3)
        self._save(fig, f'boxplot_{product.lower()}.png', save)

    def plot_heatmap(self, product, save=True):
        """Heatmap время × зона."""
        xyz = self.build_heatmap_xyz(product)
        if xyz.empty:
            logger.warning(
                messages.LOG_ANALYSIS_WARN.format('Heatmap', 'данных')
            )
            return

        mat = xyz.pivot_table(
            index='time', columns='zone_name', values='value'
        )
        mat = mat[[z for z in self.zone_order if z in mat.columns]]

        fig, ax = self._plot_base(
            figsize=(10, 8),
            title=f'Тепловая карта время × зона ({product})',
            xlabel='Зона',
            ylabel='Время (годы)',
        )

        im = ax.pcolormesh(mat.to_numpy(), cmap='viridis')
        ax.set_aspect('auto')
        ax.set_xticks(np.arange(len(mat.columns)) + 0.5)
        ax.set_xticklabels(mat.columns, rotation=45, ha='right')
        step = max(1, len(mat) // 10)
        ax.set_yticks(np.arange(0, len(mat), step) + 0.5)
        ax.set_yticklabels([f'{t:.2f}' for t in mat.index[::step]])
        fig.colorbar(im, ax=ax, label=f'{product} ({self._get_unit(product)})')
        self._save(fig, f'heatmap_{product.lower()}.png', save)

    def plot_small_multiples(self, product, save=True):
        """Сетка мини-графиков: сезонный цикл каждой зоны."""
        m = self._monthly(product)
        if m.empty:
            logger.warning(
                messages.LOG_ANALYSIS_WARN.format('Small multiples', 'данных')
            )
            return
        m = (
            m.groupby(['zone_name', 'month'])['value']
            .agg(['mean', 'std'])
            .reset_index()
        )

        ncols = 3
        nrows = int(np.ceil(len(self.zone_order) / ncols))
        fig, axes = plt.subplots(
            nrows, ncols, figsize=(4 * ncols, 3 * nrows), sharey=True
        )
        flat_axes = np.atleast_1d(axes).ravel()

        for ax, zone in zip(flat_axes, self.zone_order):
            z = m[m['zone_name'] == zone].sort_values('month')
            color = self._get_color(zone)
            ax.plot(z['month'], z['mean'], '-o', color=color, ms=3)
            ax.fill_between(
                z['month'],
                z['mean'] - z['std'],
                z['mean'] + z['std'],
                alpha=0.2,
                color=color,
            )
            ax.set_title(zone, fontsize=9)
            ax.grid(alpha=0.3)

        for ax in flat_axes[len(self.zone_order) :]:
            ax.axis('off')

        fig.suptitle(f'Сезонный цикл по зонам ({product})')
        fig.tight_layout()
        self._save(fig, f'small_multiples_{product.lower()}.png', save)

    def plot_corr_matrix(self, product, save=True):
        """Heatmap матрицы корреляций зон."""
        corr = self.build_corr_matrix(product)
        if corr.empty or corr.shape[0] < 3:
            logger.warning(messages.WARN_CORR_ZONES.format(product))
            return

        fig, ax = self._plot_base(
            figsize=(8, 7), title=f'Корреляция зон по аномалиям ({product})'
        )

        im = ax.imshow(corr.to_numpy(), cmap='coolwarm', vmin=-1, vmax=1)
        ax.set_xticks(range(len(corr)))
        ax.set_xticklabels(corr.columns, rotation=45, ha='right')
        ax.set_yticks(range(len(corr)))
        ax.set_yticklabels(corr.index)

        for i in range(len(corr)):
            for j in range(len(corr)):
                ax.text(
                    j,
                    i,
                    f'{corr.iat[i, j]:.2f}',
                    ha='center',
                    va='center',
                    fontsize=7,
                )

        fig.colorbar(im, ax=ax, label='r')
        self._save(fig, f'corr_matrix_{product.lower()}.png', save)

    def plot_pca_biplot(self, product, save=True):
        """PCA biplot: зоны в пространстве ПК и стрелки месяцев."""
        pca = self.build_pca(product)
        if pca is None:
            logger.warning(messages.WARN_PCA_SKIPPED.format(product))
            return
        scores, loadings, evr = pca

        fig, ax = self._plot_base(
            figsize=(8, 7),
            title=f'PCA biplot сезонного цикла ({product})',
            xlabel=f'PC1 ({evr[0]:.0%})',
            ylabel=f'PC2 ({evr[1]:.0%})',
        )

        for _, r in scores.iterrows():
            ax.scatter(
                r['PC1'], r['PC2'], color=self._get_color(r['zone_name'])
            )
            ax.annotate(r['zone_name'], (r['PC1'], r['PC2']), fontsize=8)

        max_loadings = loadings[['PC1', 'PC2']].abs().max().max()
        scale = (
            scores[['PC1', 'PC2']].abs().max().max() / max_loadings
            if max_loadings > 0
            else 1.0
        )

        for _, r in loadings.iterrows():
            ax.arrow(
                0,
                0,
                r['PC1'] * scale,
                r['PC2'] * scale,
                color='gray',
                alpha=0.6,
                head_width=0.03 * scale,
            )
            ax.annotate(
                int(r['month']),
                (r['PC1'] * scale, r['PC2'] * scale),
                fontsize=8,
                color='gray',
            )

        ax.axhline(0, color='k', lw=0.5)
        ax.axvline(0, color='k', lw=0.5)
        self._save(fig, f'pca_biplot_{product.lower()}.png', save)

    def plot_anomalies(self, product, save=True):
        """Линии годовых аномалий по зонам."""
        wide = self.build_anomalies_wide(product)
        if wide.empty:
            return

        fig, ax = self._plot_base(
            figsize=(10, 6),
            title=f'Годовые аномалии относительно нормы ({product})',
            xlabel='Год',
            ylabel=f'Аномалия ({self._get_unit(product)})',
        )

        for zone in self.zone_order:
            if zone in wide:
                ax.plot(
                    wide['year'],
                    wide[zone],
                    '-o',
                    label=zone,
                    color=self._get_color(zone),
                    ms=4,
                )

        ax.axhline(0, color='k', lw=0.8)
        ax.legend(ncol=2, fontsize=8)
        ax.grid(alpha=0.3)
        self._save(fig, f'anomalies_{product.lower()}.png', save)

    def plot_phenology(self, product, save=True):
        """Средние SOS/POS/EOS по зонам."""
        ph = self.build_phenology(product)
        if ph.empty:
            logger.warning(messages.WARN_PHENOLOGY_EMPTY.format(product))
            return
        g = ph.groupby('zone_name')[
            ['sos_month', 'pos_month', 'eos_month']
        ].mean()
        g = g.loc[[z for z in self.zone_order if z in g.index]]
        if g.empty:
            return

        x = np.arange(len(g))
        width = 0.25

        fig, ax = self._plot_base(
            figsize=(10, 6),
            title=f'Фенологические метрики ({product})',
            xlabel='',
            ylabel='Месяц',
        )

        ax.bar(x - width, g['sos_month'], width, label='SOS')
        ax.bar(x, g['pos_month'], width, label='POS')
        ax.bar(x + width, g['eos_month'], width, label='EOS')
        ax.set_xticks(x)
        ax.set_xticklabels(g.index, rotation=45, ha='right')
        ax.legend()
        ax.grid(axis='y', alpha=0.3)
        self._save(fig, f'phenology_{product.lower()}.png', save)

    def export_summary_table(self, save=True):
        """Экспорт сводной таблицы."""
        if 'mean' not in self.df.columns and 'shannon' not in self.df.columns:
            return pd.DataFrame()

        rows = []
        for product in self.df['product'].unique().tolist():
            metric = self._metric_column(product)
            product_rows = self._product_rows(product)

            for zone in self.zone_order:
                subset = product_rows[product_rows['zone_name'] == zone]
                if subset.empty:
                    continue

                yearly = subset.groupby('year')[metric].mean()
                trend, p_val = np.nan, np.nan
                if len(yearly) >= 3:
                    x = yearly.index.astype(float)
                    slope, _, _, p_val, _ = stats.linregress(x, yearly.values)
                    trend = slope * 10

                rows.append(
                    {
                        'product': product,
                        'zone': zone,
                        'metric': metric,
                        'mean': subset[metric].mean(),
                        'std': subset[metric].std(),
                        'trend_10yr': trend,
                        'p_value': p_val,
                        'n': len(subset),
                    }
                )

        df_out = pd.DataFrame(rows)
        if save and not df_out.empty:
            path = self.output_dir / 'summary_statistics.csv'
            df_out.to_csv(
                path, index=False, encoding='utf-8-sig', sep=';', decimal=','
            )
            logger.info(messages.LOG_ANALYSIS_OK.format(path))
        return df_out

    def export_trend_significance(self, save=True):
        """Экспорт таблицы значимости трендов."""
        if 'mean' not in self.df.columns and 'shannon' not in self.df.columns:
            return pd.DataFrame()

        rows = []
        for product in self.df['product'].unique().tolist():
            metric = self._metric_column(product)
            product_rows = self._product_rows(product)

            for zone in self.zone_order:
                subset = product_rows[product_rows['zone_name'] == zone]
                if subset.empty:
                    continue

                yearly = subset.groupby('year')[metric].mean()
                if len(yearly) < 3:
                    continue

                x = yearly.index.astype(float)
                slope, _, r, p_val, _ = stats.linregress(x, yearly.values)

                rows.append(
                    {
                        'product': product,
                        'zone': zone,
                        'metric': metric,
                        'trend_per_year': slope,
                        'trend_per_10yr': slope * 10,
                        'r_squared': r**2,
                        'p_value': p_val,
                        'significant_0.05': p_val < 0.05,
                        'significant_0.1': p_val < 0.1,
                        'n_years': len(yearly),
                    }
                )

        df_out = pd.DataFrame(rows)
        if save and not df_out.empty:
            path = self.output_dir / 'trend_significance.csv'
            df_out.to_csv(
                path, index=False, encoding='utf-8-sig', sep=';', decimal=','
            )
            logger.info(messages.LOG_ANALYSIS_OK.format(path))
        return df_out

    def export_monthly_aggregated(self, save=True):
        """Экспорт ежемесячных средних."""
        if 'mean' not in self.df.columns:
            return pd.DataFrame()

        agg = (
            self.df[self.df['mean'].notna()]
            .groupby(['zone_name', 'year', 'month', 'product'])['mean']
            .agg(['mean', 'std', 'count', 'min', 'max'])
            .reset_index()
        )

        if save and not agg.empty:
            path = self.output_dir / 'monthly_aggregated.csv'
            agg.to_csv(
                path, index=False, encoding='utf-8-sig', sep=';', decimal=','
            )
            logger.info(messages.LOG_ANALYSIS_OK.format(path))
        return agg

    def _collect_sheets(self):
        """Сборка вкладышей книги: имя -> (df, описание, X, Y)."""
        sheets = {
            'flat': (
                self.df,
                'Плоская таблица: строка = зона x дата x продукт, все метрики',
                'date / month',
                'mean, std, p10..p90, cv, shannon',
            ),
            'monthly': (
                self.export_monthly_aggregated(save=False),
                'Месячные средние (long): база для всех агрегатов',
                'month',
                'mean',
            ),
            'summary': (
                self.export_summary_table(save=False),
                'Сводка: среднее за период и тренд за 10 лет по зонам',
                '-',
                'mean, trend_10yr',
            ),
            'trends': (
                self.export_trend_significance(save=False),
                'Значимость межгодовых трендов',
                'year',
                'trend_per_10yr, p_value',
            ),
        }

        cat = self.build_categorical()
        if not cat.empty:
            sheets['categorical'] = (
                cat,
                'Категориальные продукты: индекс Шеннона и классы',
                'year',
                'shannon, dominant_class',
            )

        for p in sorted(self.df['product'].unique()):
            if self._monthly(p).empty:
                continue

            sheets[f'seasonal_{p}'] = (
                self.build_seasonal_wide(p),
                f'Сезонный цикл {p}: строки — месяцы, колонки — зоны',
                'month',
                'колонки зон',
            )
            sheets[f'annual_{p}'] = (
                self.build_annual_wide(p),
                f'Годовые ряды {p}: строки — годы, колонки — зоны',
                'year',
                'колонки зон',
            )
            sheets[f'boxplot_{p}'] = (
                self.build_boxplot_wide(p),
                f'Сырые значения {p} для boxplot: колонки — зоны',
                '-',
                'колонки зон',
            )
            sheets[f'heatmap_{p}'] = (
                self.build_heatmap_xyz(p),
                f'XYZ для heatmap {p}: десятичное время, зона, значение',
                'time',
                'value (Z)',
            )
            sheets[f'anomalies_{p}'] = (
                self.build_anomalies_wide(p),
                f'Годовые аномалии {p} от нормы: строки — годы, колонки — зоны',
                'year',
                'колонки зон',
            )

            ph = self.build_phenology(p)
            if not ph.empty:
                sheets[f'phenology_{p}'] = (
                    ph,
                    f'Фенологические метрики {p} по зона-годам',
                    'year',
                    'sos_month, pos_month, eos_month, los_months',
                )

            cm = self.build_corr_matrix(p)
            if not cm.empty and cm.shape[0] >= 3:
                sheets[f'corr_{p}'] = (
                    cm.reset_index(),
                    f'Матрица корреляций зона x зона по аномалиям {p}',
                    '-',
                    'матрица',
                )

            pca = self.build_pca(p)
            if pca is not None:
                sc, ld, evr = pca
                sheets[f'pca_scores_{p}'] = (
                    sc,
                    f'PCA scores зон {p} (PC1={evr[0]:.0%}, PC2={evr[1]:.0%})',
                    'PC1',
                    'PC2',
                )
                sheets[f'pca_loadings_{p}'] = (
                    ld,
                    f'PCA loadings месяцев {p} (стрелки biplot)',
                    'PC1',
                    'PC2',
                )

        return sheets

    def export_origin_pivot(self, save=True):
        """Широкие таблицы период x зона для каждого непрерывного продукта."""
        if 'mean' not in self.df.columns:
            return pd.DataFrame()

        pivot_df = pd.DataFrame()
        for product in self.df['product'].unique().tolist():
            if self._is_categorical(product):
                continue

            subset = self._product_rows(product).copy()
            if subset.empty:
                continue

            subset['period'] = (
                subset['year'].astype(str)
                + '-'
                + subset['month'].astype(str).str.zfill(2)
            )

            pivot_df = (
                subset.pivot_table(
                    index='period',
                    columns='zone_name',
                    values='mean',
                    aggfunc='mean',
                )
                .reset_index()
                .sort_values('period')
            )

            if save and not pivot_df.empty:
                path = self.output_dir / f'origin_pivot_{product.lower()}.csv'
                pivot_df.to_csv(
                    path,
                    index=False,
                    encoding='utf-8-sig',
                    sep=';',
                    decimal=',',
                )
                logger.info(messages.LOG_ANALYSIS_OK.format(path))

        return pivot_df

    def run_all(self, products=None):
        """Запуск всех визуализаций и экспорта."""
        available = self.df['product'].unique().tolist()
        products = [p for p in (products or available) if p in available]

        if not products:
            logger.warning(messages.INFO_NO_PRODUCTS)
            return

        continuous = [p for p in products if not self._is_categorical(p)]
        months = sorted(self.df['month'].unique())
        target_month = (
            7 if 7 in months else (months[len(months) // 2] if months else 7)
        )

        logger.info(messages.ANALYSIS_STEP_SEASONAL)
        for p in continuous:
            self.plot_seasonal_dynamics(p)

        logger.info(messages.ANALYSIS_STEP_TRENDS)
        for p in continuous:
            self.plot_interannual_trends(p)

        logger.info(messages.ANALYSIS_STEP_GRADIENT.format(target_month))
        for p in continuous:
            self.plot_latitudinal_gradient(p, month=target_month)

        logger.info(messages.ANALYSIS_STEP_AMPLITUDE)
        for p in continuous:
            self.plot_seasonal_amplitude(p)

        logger.info(messages.ANALYSIS_STEP_CORRELATION.format(target_month))
        if len(continuous) >= 2:
            self.plot_product_correlation(
                continuous[0], continuous[1], month=target_month
            )
        else:
            logger.info(messages.INFO_SKIP_CORRELATION.format('N/A', 'N/A'))

        logger.info(messages.ANALYSIS_STEP_TABLES)
        self.export_summary_table()
        self.export_trend_significance()
        self.export_monthly_aggregated()

        logger.info(messages.ANALYSIS_STEP_WIDE)
        self.export_origin_pivot()

        logger.info(messages.ANALYSIS_STEP_ANOMALY)
        for p in continuous:
            self.plot_anomalies(p)
            self.plot_phenology(p)

        logger.info(messages.ANALYSIS_STEP_CATEGORICAL)
        if self.build_categorical().empty:
            logger.info(messages.INFO_NO_CATEGORICAL)

        logger.info(messages.ANALYSIS_STEP_EXTRA_PLOTS)
        for p in continuous:
            self.plot_boxplots(p)
            self.plot_heatmap(p)
            self.plot_small_multiples(p)
            self.plot_corr_matrix(p)
            self.plot_pca_biplot(p)

        logger.info(messages.INFO_ANALYSIS_DONE)
        logger.info(messages.INFO_FIGURES_DIR.format(self.output_dir))


def main(args):
    """Главная функция анализа."""
    logger.info(messages.SEPARATOR)
    logger.info(messages.HEADER_ANALYZER)
    logger.info(messages.SEPARATOR)
    logger.info(
        messages.STATUS_START_TIME.format(
            datetime.now().strftime(LOG_DATE_FORMAT)
        )
    )

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

    save_run_provenance(
        '05_analyze',
        {
            'product': args.product,
            'output_dir': str(output_dir),
        },
    )

    try:
        analyzer = MODISAnalyzer(input_csv, output_dir)
        analyzer.run_all(products=products)

        # Excel и Help CSV создаются всегда
        exporter = ExcelExporter(analyzer)
        exporter.export_help_csv(save=True)
        excel_path = output_dir / EXCEL_FILENAME
        exporter.export_excel(excel_path)

        logger.info(
            messages.STATUS_END_TIME.format(
                datetime.now().strftime(LOG_DATE_FORMAT)
            )
        )
    except (FileNotFoundError, ValueError, pd.errors.EmptyDataError) as e:
        logger.error(messages.ERR_CRITICAL.format(str(e)))
