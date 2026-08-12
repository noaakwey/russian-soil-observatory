#!/usr/bin/env python3
"""Print-quality figures for the manuscript.

The geoportal figures were designed for a screen: dark/light pairs, titles
baked into the image, mixed Russian and English axis labels, and a tint
background. None of that survives a journal page. These are rebuilt to a
different set of constraints:

* one rendering, white background, 300 dpi;
* Russian throughout, using the published property dictionary rather than
  ad-hoc abbreviations, and no shortenings a reader has to decode;
* no title inside the image — a journal figure carries its caption in the
  text, and the space is better spent on the data;
* sized to the printed column, with font sizes chosen so that the figure is
  legible after reduction rather than at 100% on a monitor.
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from property_dictionary_ru import CATEGORY_RU, merged_category

# Печатная ширина: одна колонка и полная ширина полосы, в дюймах.
COLUMN = 3.35
FULL = 6.9

PALETTE = {
    'primary': '#1f4e8c',
    'secondary': '#c1541f',
    'tertiary': '#2f7d4f',
    'muted': '#8a8a84',
    'grid': '#d8d8d2',
    'ink': '#1a1a1a',
}
CATEGORY_COLOURS = [
    '#1f4e8c', '#c1541f', '#2f7d4f', '#7a4f9c', '#a8891f', '#b03a5b',
    '#2a8ca8', '#6d7d24', '#8c5426', '#4a5aa8', '#a8479a', '#3f8f3f',
    '#7d6244', '#5a86a8', '#a05248',
]

# Category labels (Russian) and the alias-collapsing merged_category() come
# from the shared property_dictionary_ru module — this used to be a local,
# 15-entry dict that fell back to the raw English/snake_case slug for
# anything outside that short list (soil_measurement, manual_article,
# carbon, …), which is exactly what leaked into figR2/figR3 before this
# fix (found 2026-08-12). Every DataFrame with a `category` column has it
# passed through merged_category() right after loading (see main()) so both
# the synonym-collapsing and the translation happen in one place.


def apply_print_style() -> None:
    """Style set by the «Почвоведение» figure rules, not by taste.

    The journal asks for Arial or Helvetica, letters no smaller than 5 pt,
    lines no thinner than 0.5 pt, and at least 600 dpi for line graphics.
    Every size below is chosen to clear those floors after the figure is
    scaled down to a 170 mm text width, so the smallest tick label here
    (6.5 pt at full width) stays above 5 pt in print.
    """
    plt.rcParams.update({
        'figure.facecolor': 'white', 'axes.facecolor': 'white',
        'savefig.facecolor': 'white', 'savefig.dpi': 600,
        'text.color': PALETTE['ink'], 'axes.labelcolor': PALETTE['ink'],
        'xtick.color': PALETTE['ink'], 'ytick.color': PALETTE['ink'],
        'axes.edgecolor': '#4a4a46', 'grid.color': PALETTE['grid'],
        'font.family': 'sans-serif',
        'font.sans-serif': ['Arial', 'Helvetica', 'Liberation Sans',
                            'DejaVu Sans'],
        'font.size': 8.5, 'axes.labelsize': 8.5,
        'xtick.labelsize': 7.5, 'ytick.labelsize': 7.5,
        'legend.fontsize': 7.5,
        'axes.spines.top': False, 'axes.spines.right': False,
        'axes.linewidth': 0.8, 'grid.linewidth': 0.6,
        'lines.linewidth': 1.2,
        'savefig.bbox': 'tight', 'savefig.pad_inches': 0.12,
    })



# Arial has no Unicode subscript-digit glyphs, and matplotlib resolves a font
# family to one concrete file rather than falling back per character, so
# "Fe₂O₃" prints with boxes in place of the subscripts once the journal's
# Arial requirement is enforced (see apply_print_style). Plain digits read
# fine in a figure and are standard practice where subscript formatting
# isn't available, so labels are flattened only for matplotlib text — the
# markdown tables and Word output keep the typeset subscripts.
_SUBSCRIPT_DIGITS = str.maketrans('₀₁₂₃₄₅₆₇₈₉', '0123456789')


def plain_digits(text: str) -> str:
    return text.translate(_SUBSCRIPT_DIGITS)


def russian_names(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open(encoding='utf-8') as handle:
        return {row['property_id']: plain_digits(row['property_russian'])
                for row in csv.DictReader(handle) if row.get('property_russian')}


def save(fig, output: Path, name: str) -> None:
    fig.savefig(output / f'{name}.png')
    fig.savefig(output / f'{name}.pdf')
    plt.close(fig)
    print(f'  {name}.png / .pdf')


def wrap(text: str, width: int = 26) -> str:
    """Break a label onto two lines rather than let it run off the axis."""
    if len(text) <= width:
        return text
    cut = text.rfind(' ', 0, width)
    if cut == -1:
        return text
    return text[:cut] + '\n' + text[cut + 1:]


# --------------------------------------------------------------------------

def _forest(ax, part, value_column, positions_label_column='label'):
    """Draw a forest plot, colouring significant and non-significant apart.

    Matplotlib's errorbar takes one ecolor for the whole call, so significant
    and non-significant rows are drawn as two calls over a shared y-axis
    rather than one call with a colour list.
    """
    positions = np.arange(len(part))
    for mask, colour in ((part.significant_fdr5.to_numpy(), PALETTE['primary']),
                         (~part.significant_fdr5.to_numpy(), PALETTE['muted'])):
        if not mask.any():
            continue
        chunk = part[mask]
        ax.errorbar(chunk[value_column], positions[mask],
                    xerr=[chunk[value_column] - chunk.ci_low,
                          chunk.ci_high - chunk[value_column]],
                    fmt='o', markersize=4, elinewidth=1.1, capsize=0,
                    color=colour, ecolor=colour, linestyle='none')
    ax.axvline(0, color=PALETTE['ink'], linewidth=.8)
    ax.set_yticks(positions)
    ax.set_yticklabels([wrap(v, 22) for v in part[positions_label_column]], fontsize=7)
    # Without explicit padding the first and last markers sit on the frame and
    # their error bars are clipped by it.
    ax.set_ylim(-0.75, len(part) - 0.25)
    ax.grid(axis='x', alpha=.45)
    ax.set_axisbelow(True)


def figure_categories(census: pd.DataFrame, output: Path) -> None:
    """Observation volume by property group — replaces the 101-bar chart.

    A bar per property is unreadable at column width and, more importantly,
    answers no question: what a reader needs is how the effort divides between
    kinds of analysis, with the number of distinct properties behind each.
    """
    grouped = (census.groupby('category')
               .agg(observations=('observations', 'sum'),
                    properties=('property_id', 'size'))
               .sort_values('observations'))
    labels = [CATEGORY_RU.get(c, c) for c in grouped.index]

    fig, ax = plt.subplots(figsize=(FULL, 3.6))
    positions = np.arange(len(grouped))
    ax.barh(positions, grouped.observations, height=0.68,
            color=PALETTE['primary'], alpha=.85)
    for y, (value, count) in enumerate(zip(grouped.observations, grouped.properties)):
        ax.text(value + grouped.observations.max() * 0.012, y,
                f'{value:,}'.replace(',', ' ') + f'  ({count})',
                va='center', fontsize=7.2, color=PALETTE['ink'])
    ax.set_yticks(positions)
    ax.set_yticklabels(labels)
    ax.set_xlabel('Число наблюдений; в скобках — число показателей в группе')
    ax.set_xlim(0, grouped.observations.max() * 1.25)
    ax.grid(axis='x', alpha=.5)
    ax.set_axisbelow(True)
    fig.tight_layout()
    save(fig, output, 'figR2_categories')


def figure_distribution_shape(shape: pd.DataFrame, output: Path) -> None:
    """Skewness against coefficient of variation for every described property.

    States, for the whole catalogue at once, the fact that the manuscript
    otherwise asserts about two properties: soil concentrations published in
    the literature are right-skewed, and the degree varies systematically by
    kind of property.
    """
    fig, ax = plt.subplots(figsize=(FULL, 4.0))
    categories = sorted(shape.category.unique())
    colours = {c: CATEGORY_COLOURS[i % len(CATEGORY_COLOURS)]
               for i, c in enumerate(categories)}
    for category in categories:
        part = shape[shape.category == category]
        ax.scatter(part.cv, part.skewness, s=26,
                   color=colours[category], alpha=.85, edgecolors='none',
                   label=CATEGORY_RU.get(category, category))
    ax.axhline(0, color=PALETTE['muted'], linewidth=.8, linestyle='--')
    ax.axhline(2, color=PALETTE['secondary'], linewidth=.8, linestyle=':')
    ax.text(ax.get_xlim()[1] * 0.99, 2.12, 'сильная правая асимметрия',
            ha='right', fontsize=7, color=PALETTE['secondary'])
    ax.set_xlabel('Коэффициент вариации')
    ax.set_ylabel('Коэффициент асимметрии')
    ax.grid(alpha=.45)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=6.8, ncol=3, loc='upper left',
              bbox_to_anchor=(0, -0.16))
    fig.tight_layout()
    save(fig, output, 'figR3_distribution_shape')


def figure_depth_sweep(depth: pd.DataFrame, names: dict, output: Path) -> None:
    """Depth response of every property the data supports.

    Two panels because the slopes differ by two orders of magnitude and a
    single axis would collapse the log-transformed properties onto zero.
    """
    depth = depth.copy()
    depth['label'] = depth.property_id.map(names).fillna(depth.property)
    linear = depth[~depth.log_transformed].sort_values('slope_per_cm')
    logged = depth[depth.log_transformed].sort_values('slope_per_cm')

    # Same fixed-height overlap as figure_zonal_sweep (see its comment) —
    # scale to whichever panel has more rows.
    height = max(3.4, 0.24 * max(len(linear), len(logged)))
    fig, axes = plt.subplots(1, 2, figsize=(FULL, height),
                             gridspec_kw={'width_ratios': [1, 1]})
    for ax, part, caption in (
            (axes[0], linear, 'Исходная шкала показателя,\nединиц на сантиметр'),
            (axes[1], logged, 'Логарифмическая шкала,\nна сантиметр')):
        _forest(ax, part.reset_index(drop=True), 'slope_per_cm')
        ax.set_xlabel(caption)
    fig.tight_layout()
    save(fig, output, 'figR6_depth_sweep')


def figure_zonal_sweep(zonal: pd.DataFrame, names: dict, output: Path) -> None:
    """Latitude slope for every property with enough data.

    Two properties have confidence intervals an order of magnitude wider than
    the rest and, plotted on a shared axis, flatten everything informative
    into a line at zero. They are shown on their own axis instead of being
    dropped, because a wide interval is itself the finding for them.
    """
    zonal = zonal.copy()
    zonal['label'] = zonal.property_id.map(names).fillna(zonal.property)
    zonal['width'] = zonal.ci_high - zonal.ci_low
    wide = zonal[zonal.width > 2.0].sort_values('slope_per_degree')
    narrow = zonal[zonal.width <= 2.0].sort_values('slope_per_degree')

    # A fixed figure height overlapped labels once the sweep grew past a
    # couple dozen properties (51 with the current admission rules) — the
    # left panel needs room proportional to its own row count, not a
    # constant chosen when the sweep was shorter (found 2026-08-12).
    height = max(4.3, 0.19 * len(narrow))
    fig, axes = plt.subplots(1, 2, figsize=(FULL, height),
                             gridspec_kw={'width_ratios': [2.2, 1.1]})
    # The right panel is narrow, so its x-label has to be short enough to fit
    # inside the panel width; the units are stated in the caption.
    for ax, part, caption in (
            (axes[0], narrow, 'Наклон на градус широты'),
            (axes[1], wide, 'То же, иной масштаб')):
        _forest(ax, part.reset_index(drop=True), 'slope_per_degree')
        ax.set_xlabel(caption)
    fig.tight_layout(pad=0.9)
    save(fig, output, 'figR5_zonal_sweep')


def figure_effort(db: Path, output: Path) -> None:
    """Where the studies are, and how the effort divides along longitude."""
    con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    try:
        points = pd.read_sql("""
            SELECT t.latitude AS lat, t.longitude AS lon, t.tier
            FROM document_spatial_tier t
            WHERE t.latitude BETWEEN 41 AND 82 AND t.longitude BETWEEN 19 AND 190
        """, con)
    finally:
        con.close()

    fig, axes = plt.subplots(1, 2, figsize=(FULL, 3.4),
                             gridspec_kw={'width_ratios': [2.4, 1]})
    ax = axes[0]
    styles = [
        ('region', 'центроид региона', PALETTE['tertiary'], 8),
        ('dms', 'координата из текста', PALETTE['secondary'], 16),
        ('reported', 'сообщённая координата', PALETTE['primary'], 16),
    ]
    for tier, label, colour, size in styles:
        part = points[points.tier == tier]
        ax.scatter(part.lon, part.lat, s=size, c=colour, alpha=.6,
                   edgecolors='none', label=f'{label} ({len(part)})')
    ax.set_xlim(18, 182)
    ax.set_ylim(40, 80)
    ax.set_xlabel('Восточная долгота, град.')
    ax.set_ylabel('Северная широта, град.')
    ax.grid(alpha=.45)
    ax.set_axisbelow(True)
    # Below the axes rather than inside it: every in-frame corner overlaps
    # points at some longitude.
    ax.legend(frameon=False, fontsize=6.8, ncol=3, markerscale=1.4,
              loc='upper center', bbox_to_anchor=(0.5, -0.20),
              columnspacing=1.2, handletextpad=0.4)

    ax = axes[1]
    bins = np.arange(20, 190, 10)
    counts, _ = np.histogram(points.lon, bins=bins)
    ax.barh(bins[:-1] + 5, counts, height=8.2, color=PALETTE['primary'], alpha=.85)
    ax.set_ylabel('Восточная долгота, град.')
    ax.set_xlabel('Число публикаций')
    ax.set_ylim(18, 182)
    ax.grid(axis='x', alpha=.45)
    ax.set_axisbelow(True)
    fig.tight_layout()
    save(fig, output, 'figR4_effort')


def figure_correlations(corr: pd.DataFrame, output: Path) -> None:
    """Correlation matrix between properties measured on one sample."""
    labels_ru = {
        'ph_h2o': 'pH водной вытяжки', 'ph_kcl': 'pH солевой вытяжки',
        'ph_unspecified': 'pH (метод не указан)',
        'soil_organic_carbon': 'органический углерод', 'organic_matter': 'органическое вещество',
        'clay': 'ил (< 0.002 мм)', 'sand': 'песок', 'silt': 'пыль',
        'physical_clay': 'физическая глина', 'fine_fraction_lt_0_001mm': 'ил (< 0.001 мм)',
        'base_saturation': 'насыщенность основаниями',
        'carbonate_equivalent': 'карбонаты (CaCO3)',
        'electrical_conductivity': 'электропроводность',
        'iron_oxide_fe2o3': 'оксид железа (Fe2O3)',
        'available_phosphorus': 'подвижный фосфор',
    }
    present = []
    for _, row in corr.iterrows():
        present.extend([row.a, row.b])
    order = [p for p in labels_ru if p in set(present)] or list(labels_ru)

    size = len(order)
    matrix = np.full((size, size), np.nan)
    significant = np.zeros((size, size), dtype=bool)
    index = {p: i for i, p in enumerate(order)}
    for _, row in corr.iterrows():
        if row.a in index and row.b in index:
            i, j = index[row.a], index[row.b]
            matrix[i, j] = matrix[j, i] = row.pearson_r
            significant[i, j] = significant[j, i] = bool(row.significant_fdr5)
    np.fill_diagonal(matrix, 1.0)

    fig, ax = plt.subplots(figsize=(FULL, FULL * 0.82))
    image = ax.imshow(matrix, cmap='RdBu_r', vmin=-1, vmax=1)
    ticks = [labels_ru.get(p, p) for p in order]
    ax.set_xticks(range(size)); ax.set_yticks(range(size))
    ax.set_xticklabels(ticks, rotation=48, ha='right', fontsize=7)
    ax.set_yticklabels(ticks, fontsize=7)
    for i in range(size):
        for j in range(size):
            if i == j or np.isnan(matrix[i, j]):
                continue
            weight = 'bold' if significant[i, j] else 'normal'
            colour = PALETTE['ink'] if significant[i, j] else PALETTE['muted']
            ax.text(j, i, f'{matrix[i, j]:+.2f}'.replace('-', '−'),
                    ha='center', va='center', fontsize=5.9,
                    color=colour, fontweight=weight)
    bar = fig.colorbar(image, ax=ax, fraction=.042, pad=.02)
    bar.set_label('Коэффициент корреляции Пирсона', fontsize=8)
    bar.ax.tick_params(labelsize=7)
    bar.outline.set_visible(False)
    fig.tight_layout()
    save(fig, output, 'figR7_correlations')


def figure_density_grid(cells: pd.DataFrame, output: Path) -> None:
    """Publications per 5-degree cell."""
    fig, ax = plt.subplots(figsize=(FULL, 3.2))
    sizes = 14 + 66 * (cells.documents / cells.documents.max())
    scatter = ax.scatter(cells.cell_lon + 2.5, cells.cell_lat + 2.5,
                         s=sizes, c=cells.documents, cmap='YlGnBu',
                         edgecolors='#5a5a56', linewidths=.3)
    ax.set_xlim(18, 182); ax.set_ylim(40, 80)
    ax.set_xlabel('Восточная долгота, град.')
    ax.set_ylabel('Северная широта, град.')
    ax.grid(alpha=.45)
    ax.set_axisbelow(True)
    bar = fig.colorbar(scatter, ax=ax, fraction=.03, pad=.02)
    bar.set_label('Публикаций в ячейке', fontsize=8)
    bar.ax.tick_params(labelsize=7)
    bar.outline.set_visible(False)
    fig.tight_layout()
    save(fig, output, 'figR8_density_grid')


# WRB-2022 reference-group names are Latin taxonomy, not English prose, but
# the journal's Russian text uses the standard transliterated forms
# («Подзол», not «Podzol») — found leaking untranslated into figR9 2026-08-12.
WRB_RU = {
    'Chernozem': 'Чернозём', 'Podzol': 'Подзол', 'Solonchak': 'Солончак',
    'Solonetz': 'Солонец', 'Kastanozem': 'Каштанозём', 'Fluvisol': 'Флювисоль',
    'Histosol': 'Histosol (торфяная почва)', 'Cryosol': 'Криозём',
    'Phaeozem': 'Феозём', 'Gleysol': 'Глеезём', 'Cambisol': 'Камбисоль',
    'Luvisol': 'Лювисоль', 'Arenosol': 'Ареносоль', 'Regosol': 'Регосоль',
}


def figure_soil_type(db: Path, census: pd.DataFrame, comparison: pd.DataFrame,
                     output: Path) -> None:
    """WRB-2022 reference groups: how many observations carry a reliable soil
    type, and how properties actually differ between groups — read off the
    swept comparison table, not a chosen pair, so a panel is only drawn for
    each (property, set of groups) the sweep itself found adequately sampled.
    """
    con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    try:
        obs = pd.read_sql("""
            SELECT o.property_id, o.value_normalized, st.wrb_reference_group
            FROM table_observation o
            JOIN observation_soil_type st ON st.observation_id = o.observation_id
            JOIN observation_quality_flag f ON f.observation_id = o.observation_id
            WHERE st.confidence = 'high' AND st.wrb_confidence IN ('high','medium')
              AND o.property_id IN ('ph_h2o','organic_matter')
              AND o.normalization_status IN ('exact','converted')
              AND f.header_match_kind <> 'symbol_embedded' AND f.value_plausibility = 'ok'
        """, con)
    finally:
        con.close()

    # ph_h2o was tested against every eligible group; organic_matter only had
    # two groups reach the per-comparison document minimum. Reading the group
    # set for each panel back out of the sweep, rather than hard-coding it,
    # keeps the figure from silently dropping a group the analysis kept.
    ph_groups = sorted(set(comparison.loc[comparison.property_id == 'ph_h2o',
                                          ['group_a', 'group_b']].to_numpy().ravel()),
                       key=lambda g: obs.loc[(obs.property_id == 'ph_h2o')
                                             & (obs.wrb_reference_group == g),
                                             'value_normalized'].median())
    om_groups = sorted(set(comparison.loc[comparison.property_id == 'organic_matter',
                                          ['group_a', 'group_b']].to_numpy().ravel()))

    fig, axes = plt.subplots(1, 3, figsize=(FULL, 3.1),
                             gridspec_kw={'width_ratios': [1.3, 1.5, 1]})

    ax = axes[0]
    top = census.sort_values('observations', ascending=True).tail(8)
    positions = np.arange(len(top))
    ax.barh(positions, top.observations, height=.68, color=PALETTE['primary'], alpha=.85)
    ax.set_yticks(positions)
    ax.set_yticklabels([WRB_RU.get(g, g) for g in top.wrb_reference_group])
    ax.set_xlabel('Наблюдений (эталонный уровень)')
    ax.grid(axis='x', alpha=.45)
    ax.set_axisbelow(True)

    panels = [('ph_h2o', 'pH водной вытяжки', ph_groups, axes[1]),
             ('organic_matter', 'Органическое вещество, %', om_groups, axes[2])]
    for pid, title, groups, ax in panels:
        data = [obs.loc[(obs.property_id == pid) & (obs.wrb_reference_group == g),
                        'value_normalized'].dropna().to_numpy() for g in groups]
        bp = ax.boxplot(data, tick_labels=[WRB_RU.get(g, g) for g in groups],
                        showfliers=False, patch_artist=True, widths=.55)
        for patch, colour in zip(bp['boxes'], CATEGORY_COLOURS):
            patch.set_facecolor(colour)
            patch.set_alpha(.55)
        for element in ('whiskers', 'caps', 'medians'):
            for line in bp[element]:
                line.set_color(PALETTE['ink'])
        ax.set_xlabel(title)
        ax.tick_params(axis='x', labelrotation=20)
        ax.grid(axis='y', alpha=.45)
        ax.set_axisbelow(True)

    fig.tight_layout()
    save(fig, output, 'figR9_soil_type')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--tables', type=Path, required=True)
    parser.add_argument('--dictionary', type=Path,
                        default=Path('docs/data/property_dictionary_ru_public.csv'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    apply_print_style()
    names = russian_names(args.dictionary)

    census = pd.read_csv(args.tables / 'table_property_census.csv')
    census['category'] = census['category'].map(merged_category)
    shape = pd.read_csv(args.tables / 'table_distribution_shape.csv')
    shape['category'] = shape['category'].map(merged_category)
    depth = pd.read_csv(args.tables / 'table_depth_sweep.csv')
    zonal = pd.read_csv(args.tables / 'table_zonal_sweep.csv')
    corr = pd.read_csv(args.tables / 'table_correlations.csv')
    cells = pd.read_csv(args.tables / 'table_grid_cells.csv')
    soil_type_census = pd.read_csv(args.tables / 'table_soil_type_census.csv')
    soil_type_comparison = pd.read_csv(args.tables / 'table_soil_type_comparison.csv')

    print('Печатные рисунки:')
    figure_categories(census, args.output)
    figure_distribution_shape(shape, args.output)
    figure_effort(args.db, args.output)
    figure_zonal_sweep(zonal, names, args.output)
    figure_depth_sweep(depth, names, args.output)
    figure_correlations(corr, args.output)
    figure_density_grid(cells, args.output)
    figure_soil_type(args.db, soil_type_census, soil_type_comparison, args.output)


if __name__ == '__main__':
    main()
