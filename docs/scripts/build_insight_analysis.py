#!/usr/bin/env python3
"""Spatial, componential and temporal analysis of the observation layer.

Produces every figure, table and number quoted in ``docs/insights.md``.

Three methodological commitments run through all of it:

*Aggregate before you regress.*  One article can contribute 400 values from a
single field site; treating those as independent observations manufactures
significance out of nothing.  Every spatial and temporal statistic here is
computed on document-level means.

*Say which spatial tier you used.*  A coordinate printed in the article
(median error 0.2 km against the curated layer) and a regional centroid
inferred from prose (median 174 km) cannot answer the same questions.  Fine
gradients use precise tiers only; zonal composition uses all of them.

*Separate what changed in the soil from what changed in the literature.*  A
trend in reported values is a trend in what was studied and published, not
necessarily in the ground.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from itertools import combinations
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

EARTH_RADIUS_KM = 6371.0

# Two palettes so every figure has a light and a dark rendering; the report
# swaps them with prefers-color-scheme.
THEMES = {
    'light': dict(bg='#fcfcfb', fg='#22211c', muted='#6b6a60', grid='#e3e2dc',
                  series=['#2a6fd6', '#e0632a', '#12946a', '#9a5bd6', '#c9a227']),
    'dark': dict(bg='#16161a', fg='#e9e8e3', muted='#9d9c93', grid='#2e2e34',
                 series=['#5b9bf0', '#f08050', '#2fc191', '#b482ea', '#e0bd45']),
}

PH_IDS = ('ph_h2o', 'ph_kcl', 'ph_unspecified')


def apply_theme(theme: dict) -> None:
    plt.rcParams.update({
        'figure.facecolor': theme['bg'], 'axes.facecolor': theme['bg'],
        'savefig.facecolor': theme['bg'],
        'text.color': theme['fg'], 'axes.labelcolor': theme['fg'],
        'xtick.color': theme['muted'], 'ytick.color': theme['muted'],
        'axes.edgecolor': theme['grid'], 'grid.color': theme['grid'],
        'font.size': 10.5, 'axes.titlesize': 12, 'axes.titleweight': '600',
        'axes.spines.top': False, 'axes.spines.right': False,
        'figure.dpi': 130, 'savefig.bbox': 'tight', 'savefig.pad_inches': 0.28,
    })


def save(fig, output: Path, name: str, theme_name: str) -> None:
    fig.savefig(output / f'{name}_{theme_name}.png')
    plt.close(fig)


def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    inner = (np.sin((lat2 - lat1) / 2) ** 2
             + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(inner))


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

QUERY = """
SELECT o.observation_id, o.document_id, o.artifact_id, o.property_id,
       p.canonical_name AS property, p.category,
       o.value_num_raw, o.value_normalized, o.unit_normalized,
       o.normalization_status, f.header_match_kind, f.value_plausibility,
       o.depth_top_cm, o.depth_bottom_cm, o.row_label_raw,
       y.publication_year, y.year_confidence, d.corpus,
       t.latitude, t.longitude, t.tier, t.radius_km
FROM table_observation o
JOIN property_definition p ON p.property_id = o.property_id
JOIN observation_quality_flag f ON f.observation_id = o.observation_id
JOIN document d ON d.document_id = o.document_id
LEFT JOIN document_publication_year y ON y.document_id = o.document_id
LEFT JOIN document_spatial_tier t ON t.document_id = o.document_id
"""


# Coordinates read out of article prose are not always Russian: the journals
# publish Antarctic, Vietnamese, Chilean and Israeli fieldwork too.  Those are
# real studies, not parse errors, but they cannot enter a zonal analysis of
# Russian soils, so every spatial statistic is computed inside these bounds.
RUSSIA_BOUNDS = dict(lat=(41.0, 82.0), lon=(19.0, 190.0))


def load(db: Path) -> pd.DataFrame:
    with sqlite3.connect(db) as con:
        frame = pd.read_sql(QUERY, con)
    frame['trusted'] = ((frame.header_match_kind != 'symbol_embedded')
                        & (frame.value_plausibility == 'ok'))
    frame['metric'] = frame.normalization_status.isin(['exact', 'converted'])
    frame['in_russia'] = (
        frame.latitude.between(*RUSSIA_BOUNDS['lat'])
        & frame.longitude.between(*RUSSIA_BOUNDS['lon']))
    # Outside the bounds a coordinate is still a coordinate, but it is not part
    # of the domestic record; drop it from the spatial columns rather than let
    # Antarctica anchor a latitude regression.
    frame.loc[~frame.in_russia, ['latitude', 'longitude']] = np.nan
    frame['precise'] = frame.tier.isin(['reported', 'dms']) & frame.in_russia
    return frame


# --------------------------------------------------------------------------
# 1. Where the science happens
# --------------------------------------------------------------------------

def figure_effort_map(frame: pd.DataFrame, output: Path, theme_name: str,
                      theme: dict) -> dict:
    apply_theme(theme)
    located = frame[frame.latitude.notna() & frame.trusted]
    per_doc = located.groupby('document_id').agg(
        lat=('latitude', 'first'), lon=('longitude', 'first'),
        tier=('tier', 'first'), n=('observation_id', 'size')).reset_index()

    fig, (ax, ax2) = plt.subplots(
        1, 2, figsize=(12.6, 4.9), gridspec_kw={'width_ratios': [2.15, 1]})

    for tier, colour, label, size in [
            ('region', theme['series'][2], 'региональный центроид', 22),
            ('dms', theme['series'][1], 'координата из текста', 34),
            ('reported', theme['series'][0], 'сообщённая координата', 34)]:
        part = per_doc[per_doc.tier == tier]
        ax.scatter(part.lon, part.lat, s=size, c=colour, alpha=.55,
                   edgecolors='none', label=f'{label} ({len(part)})')
    ax.set_xlim(18, 182); ax.set_ylim(40, 78)
    ax.set_xlabel('в. д.'); ax.set_ylabel('с. ш.')
    ax.set_title('География исследованных площадок')
    ax.legend(frameon=False, fontsize=8.6, loc='lower right')
    ax.grid(alpha=.35, linewidth=.6)

    # Longitude is the axis along which Russian soil science actually thins out.
    bins = np.arange(20, 190, 10)
    counts, _ = np.histogram(per_doc.lon, bins=bins)
    area_share = np.full(len(counts), 1.0)  # equal 10-degree slices
    ax2.barh(bins[:-1] + 5, counts, height=8.4, color=theme['series'][0], alpha=.85)
    ax2.set_ylabel('в. д.'); ax2.set_xlabel('публикаций')
    ax2.set_title('Долготное распределение усилий')
    ax2.grid(axis='x', alpha=.35, linewidth=.6)
    fig.tight_layout()
    save(fig, output, 'fig1_effort', theme_name)

    european = per_doc[per_doc.lon < 60]
    return {
        'documents_located': int(len(per_doc)),
        'observations_located': int(located.observation_id.nunique()),
        'european_documents_pct': round(100 * len(european) / len(per_doc), 1),
        'european_area_pct': 23.0,
        'documents_east_of_100E': int((per_doc.lon > 100).sum()),
        'by_tier': per_doc.tier.value_counts().to_dict(),
    }


# --------------------------------------------------------------------------
# 2. Zonal gradients
# --------------------------------------------------------------------------

def figure_zonal(frame: pd.DataFrame, output: Path, theme_name: str,
                 theme: dict) -> dict:
    apply_theme(theme)
    result: dict = {}
    fig, axes = plt.subplots(1, 3, figsize=(13.4, 4.3))

    # (a) pH against latitude, document means, precise tiers only.
    ph = frame[(frame.property_id.isin(PH_IDS)) & frame.trusted
               & frame.precise & frame.latitude.notna()]
    doc_ph = ph.groupby('document_id').agg(
        v=('value_num_raw', 'mean'), lat=('latitude', 'first')).dropna()
    ax = axes[0]
    ax.scatter(doc_ph.lat, doc_ph.v, s=26, c=theme['series'][0], alpha=.6,
               edgecolors='none')
    slope = stats.linregress(doc_ph.lat, doc_ph.v)
    grid = np.linspace(doc_ph.lat.min(), doc_ph.lat.max(), 40)
    ax.plot(grid, slope.intercept + slope.slope * grid,
            color=theme['series'][1], linewidth=2)
    rho, pval = stats.spearmanr(doc_ph.lat, doc_ph.v)
    ax.set_xlabel('широта, °с. ш.'); ax.set_ylabel('pH')
    ax.set_title(f'pH падает к северу\nρ={rho:+.2f}, p={pval:.1e}, n={len(doc_ph)}')
    ax.grid(alpha=.35, linewidth=.6)
    result['ph_latitude'] = {
        'n_documents': int(len(doc_ph)), 'spearman_rho': round(rho, 3),
        'p_value': float(f'{pval:.3g}'), 'slope_per_degree': round(slope.slope, 4),
        'r_squared': round(slope.rvalue ** 2, 3)}

    # (b) pH by latitude band, all tiers — the zonal picture needs the volume.
    ph_all = frame[(frame.property_id.isin(PH_IDS)) & frame.trusted
                   & frame.latitude.notna()]
    doc_all = ph_all.groupby('document_id').agg(
        v=('value_num_raw', 'mean'), lat=('latitude', 'first')).dropna()
    doc_all['band'] = (doc_all.lat // 4 * 4).astype(int)
    band = doc_all.groupby('band').agg(n=('v', 'size'), mean=('v', 'mean'),
                                       sd=('v', 'std'))
    band = band[band.n >= 5]
    ax = axes[1]
    ax.errorbar(band['mean'], band.index + 2, xerr=band.sd, fmt='o',
                color=theme['series'][0], ecolor=theme['grid'],
                elinewidth=2.4, capsize=0, markersize=7)
    ax.axvline(7, color=theme['muted'], linestyle=':', linewidth=1.2)
    ax.set_xlabel('pH'); ax.set_ylabel('широта, °с. ш.')
    ax.set_title('Зональность реакции среды\n(средние по публикациям)')
    ax.grid(alpha=.35, linewidth=.6)
    result['ph_bands'] = [
        {'band': f'{int(b)}–{int(b)+4}', 'n_documents': int(r.n),
         'mean_ph': round(r['mean'], 2),
         'sd': None if np.isnan(r.sd) else round(r.sd, 2)}
        for b, r in band.iterrows()]

    # (c) organic carbon against latitude — the opposite expectation to pH.
    soc = frame[(frame.property_id == 'soil_organic_carbon') & frame.trusted
                & frame.metric & frame.latitude.notna()
                & (frame.unit_normalized == 'g/kg')]
    top = soc[(soc.depth_top_cm.isna()) | (soc.depth_top_cm < 30)]
    doc_soc = top.groupby('document_id').agg(
        v=('value_normalized', 'median'), lat=('latitude', 'first')).dropna()
    ax = axes[2]
    ax.scatter(doc_soc.lat, doc_soc.v, s=26, c=theme['series'][2], alpha=.6,
               edgecolors='none')
    rho_s, p_s = stats.spearmanr(doc_soc.lat, doc_soc.v)
    ax.set_xlabel('широта, °с. ш.'); ax.set_ylabel('C$_{орг}$, г/кг')
    ax.set_yscale('log')
    ax.set_title(f'Органический углерод, 0–30 см\nρ={rho_s:+.2f}, p={p_s:.2f}, n={len(doc_soc)}')
    ax.grid(alpha=.35, linewidth=.6)
    result['soc_latitude'] = {
        'n_documents': int(len(doc_soc)), 'spearman_rho': round(rho_s, 3),
        'p_value': float(f'{p_s:.3g}'),
        'median_g_per_kg': round(float(doc_soc.v.median()), 1)}

    fig.tight_layout()
    save(fig, output, 'fig2_zonal', theme_name)
    return result


# --------------------------------------------------------------------------
# 3. What gets measured together
# --------------------------------------------------------------------------

def figure_cooccurrence(frame: pd.DataFrame, output: Path, theme_name: str,
                        theme: dict) -> dict:
    apply_theme(theme)
    trusted = frame[frame.trusted]
    # A table is the unit of co-measurement: properties printed in one table
    # were measured on one set of samples.
    tables = trusted.groupby('artifact_id').property.unique()
    tables = tables[tables.map(len) > 1]

    counts: Counter = Counter()
    pairs: Counter = Counter()
    for props in tables:
        unique = sorted(set(props))
        counts.update(unique)
        pairs.update(combinations(unique, 2))

    top = [name for name, _ in counts.most_common(22)]
    index = {name: position for position, name in enumerate(top)}
    matrix = np.zeros((len(top), len(top)))
    for (first, second), shared in pairs.items():
        if first in index and second in index:
            jaccard = shared / (counts[first] + counts[second] - shared)
            matrix[index[first], index[second]] = jaccard
            matrix[index[second], index[first]] = jaccard
    np.fill_diagonal(matrix, np.nan)

    fig, ax = plt.subplots(figsize=(9.4, 8.2))
    cmap = plt.get_cmap('BuPu' if theme_name == 'light' else 'viridis')
    image = ax.imshow(matrix, cmap=cmap, vmin=0, vmax=np.nanmax(matrix))
    ax.set_xticks(range(len(top))); ax.set_yticks(range(len(top)))
    ax.set_xticklabels(top, rotation=55, ha='right', fontsize=8.4)
    ax.set_yticklabels(top, fontsize=8.4)
    ax.set_title('Что измеряют в одной таблице (индекс Жаккара)', pad=14)
    bar = fig.colorbar(image, ax=ax, fraction=.045, pad=.03)
    bar.outline.set_visible(False)
    fig.tight_layout()
    save(fig, output, 'fig3_cooccurrence', theme_name)

    strongest = sorted(
        ((a, b, shared / (counts[a] + counts[b] - shared), shared)
         for (a, b), shared in pairs.items() if shared >= 25),
        key=lambda row: -row[2])[:20]
    return {
        'tables_with_multiple_properties': int(len(tables)),
        'strongest_pairs': [
            {'a': a, 'b': b, 'jaccard': round(j, 3), 'tables': int(n)}
            for a, b, j, n in strongest],
    }


# --------------------------------------------------------------------------
# 4. Depth
# --------------------------------------------------------------------------

def figure_depth(frame: pd.DataFrame, output: Path, theme_name: str,
                 theme: dict) -> dict:
    apply_theme(theme)
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.6))
    result: dict = {}

    soc = frame[(frame.property_id == 'soil_organic_carbon') & frame.trusted
                & frame.metric & (frame.unit_normalized == 'g/kg')
                & frame.depth_top_cm.notna() & (frame.depth_top_cm < 200)].copy()
    soc['mid'] = soc.depth_top_cm + (
        (soc.depth_bottom_cm - soc.depth_top_cm).fillna(10) / 2)

    ax = axes[0]
    for zone, low, high, colour in [
            ('север (>58°)', 58, 90, theme['series'][0]),
            ('юг (<54°)', 0, 54, theme['series'][1])]:
        part = soc[(soc.latitude >= low) & (soc.latitude < high)]
        if len(part) < 30:
            continue
        binned = part.groupby(pd.cut(part.mid, np.arange(0, 210, 20)),
                              observed=True).value_normalized.agg(['median', 'size'])
        # A depth interval carried by three profiles is noise, not a trend.
        binned = binned[binned['size'] >= 8]
        centres = [interval.mid for interval in binned.index]
        ax.plot(binned['median'], centres, 'o-', color=colour,
                label=f'{zone}, n={len(part)}', markersize=5, linewidth=1.8)
        valid = part[part.value_normalized > 0]
        if len(valid) > 20:
            fit = stats.linregress(valid.mid, np.log(valid.value_normalized))
            result[f'soc_decay_{"north" if low == 58 else "south"}'] = {
                'n': int(len(valid)),
                'e_folding_depth_cm': round(-1 / fit.slope, 1) if fit.slope else None,
                'r_squared': round(fit.rvalue ** 2, 3)}
    ax.invert_yaxis(); ax.set_xscale('log')
    ax.set_xlabel('C$_{орг}$, г/кг'); ax.set_ylabel('глубина, см')
    ax.set_title('Убывание углерода по профилю')
    ax.legend(frameon=False, fontsize=9); ax.grid(alpha=.35, linewidth=.6)

    ph = frame[frame.property_id.isin(PH_IDS) & frame.trusted
               & frame.depth_top_cm.notna() & (frame.depth_top_cm < 200)]
    ax = axes[1]
    for pid, label, colour in [('ph_h2o', 'pH(H₂O)', theme['series'][0]),
                               ('ph_kcl', 'pH(KCl)', theme['series'][1])]:
        part = ph[ph.property_id == pid]
        if len(part) < 30:
            continue
        binned = part.groupby(pd.cut(part.depth_top_cm, np.arange(0, 210, 20)),
                              observed=True).value_num_raw.agg(['median', 'size'])
        binned = binned[binned['size'] >= 8]
        centres = [interval.mid for interval in binned.index]
        ax.plot(binned['median'], centres, 'o-', color=colour,
                label=f'{label}, n={len(part)}', markersize=5, linewidth=1.8)
    ax.invert_yaxis()
    ax.axvline(7, color=theme['muted'], linestyle=':', linewidth=1.2)
    ax.set_xlabel('pH'); ax.set_ylabel('глубина, см')
    ax.set_title('Подщелачивание с глубиной')
    ax.legend(frameon=False, fontsize=9); ax.grid(alpha=.35, linewidth=.6)

    fig.tight_layout()
    save(fig, output, 'fig4_depth', theme_name)

    offset = (ph[ph.property_id == 'ph_h2o'].value_num_raw.mean()
              - ph[ph.property_id == 'ph_kcl'].value_num_raw.mean())
    result['ph_h2o_minus_kcl'] = round(float(offset), 2)
    return result


# --------------------------------------------------------------------------
# 5. Time
# --------------------------------------------------------------------------

def figure_time(frame: pd.DataFrame, output: Path, theme_name: str,
                theme: dict) -> dict:
    apply_theme(theme)
    fig, axes = plt.subplots(1, 2, figsize=(12.6, 4.4))
    dated = frame[frame.publication_year.notna() & frame.trusted
                  & frame.publication_year.between(2006, 2025)]

    groups = {
        'кислотно-основные': ['acid_base'], 'органическое вещество': ['organic'],
        'гранулометрия и физика': ['particle_size', 'physical', 'hydrophysical'],
        'микроэлементы и загрязнители': ['microelement', 'contaminant'],
        'питательные элементы': ['macronutrient', 'exchange'],
    }
    years = sorted(dated.publication_year.unique())
    shares = {}
    for label, categories in groups.items():
        per_year = []
        for year in years:
            slice_ = dated[dated.publication_year == year]
            per_year.append(100 * slice_.category.isin(categories).sum() / max(len(slice_), 1))
        shares[label] = per_year

    ax = axes[0]
    ax.stackplot(years, shares.values(), labels=shares.keys(),
                 colors=theme['series'], alpha=.9)
    ax.set_xlim(min(years), max(years)); ax.set_ylim(0, 100)
    ax.set_xlabel('год'); ax.set_ylabel('% наблюдений')
    ax.set_title('Смена тематики: состав измеряемых свойств')
    ax.legend(frameon=False, fontsize=8.2, loc='lower center', ncol=2)

    # Has the research frontier moved east?
    located = dated[dated.latitude.notna()]
    per_doc = located.groupby('document_id').agg(
        year=('publication_year', 'first'), lon=('longitude', 'first'),
        lat=('latitude', 'first'))
    yearly = per_doc.groupby('year').agg(lon=('lon', 'median'), lat=('lat', 'median'),
                                         n=('lon', 'size'))
    yearly = yearly[yearly.n >= 8]
    ax = axes[1]
    ax.plot(yearly.index, yearly.lon, 'o-', color=theme['series'][0],
            markersize=5, linewidth=1.8, label='долгота')
    fit = stats.linregress(yearly.index, yearly.lon)
    ax.plot(yearly.index, fit.intercept + fit.slope * yearly.index,
            color=theme['series'][1], linewidth=1.6, linestyle='--',
            label=f'{fit.slope:+.2f}°/год, p={fit.pvalue:.2f}')
    ax.set_xlabel('год'); ax.set_ylabel('медианная долгота, °в. д.')
    ax.set_title('Смещается ли география исследований')
    ax.legend(frameon=False, fontsize=9); ax.grid(alpha=.35, linewidth=.6)

    fig.tight_layout()
    save(fig, output, 'fig5_time', theme_name)

    early = dated[dated.publication_year <= 2010]
    late = dated[dated.publication_year >= 2020]
    metals = ['microelement', 'contaminant']
    return {
        'metal_share_2006_2010': round(100 * early.category.isin(metals).mean(), 1),
        'metal_share_2020_2025': round(100 * late.category.isin(metals).mean(), 1),
        'longitude_drift_per_year': round(fit.slope, 3),
        'longitude_drift_p': float(f'{fit.pvalue:.3g}'),
        'median_longitude_2006_2010': round(float(
            per_doc[per_doc.year <= 2010].lon.median()), 1),
        'median_longitude_2020_2025': round(float(
            per_doc[per_doc.year >= 2020].lon.median()), 1),
    }


# --------------------------------------------------------------------------

def regional_table(frame: pd.DataFrame, output: Path) -> list[dict]:
    trusted = frame[frame.trusted & frame.latitude.notna()]
    grouped = trusted.groupby('document_id').agg(
        lat=('latitude', 'first'), lon=('longitude', 'first'),
        tier=('tier', 'first'), n=('observation_id', 'size'))
    rows = []
    for (low, high, name) in [
            (66, 90, 'Арктика и субарктика (>66°)'),
            (60, 66, 'Северная тайга (60–66°)'),
            (56, 60, 'Средняя тайга (56–60°)'),
            (52, 56, 'Южная тайга и лесостепь (52–56°)'),
            (48, 52, 'Степь (48–52°)'),
            (40, 48, 'Сухая степь и предгорья (<48°)')]:
        part = grouped[(grouped.lat >= low) & (grouped.lat < high)]
        obs = trusted[trusted.document_id.isin(part.index)]
        rows.append({
            'zone': name, 'documents': int(len(part)),
            'observations': int(len(obs)),
            'properties': int(obs.property.nunique()),
            'precise_pct': round(100 * part.tier.isin(['reported', 'dms']).mean(), 0)
            if len(part) else 0,
        })
    pd.DataFrame(rows).to_csv(output / 'table_zones.csv', index=False)
    return rows


# A 15-category palette, not the 5-series theme: the property landscape figure
# needs one distinguishable colour per canonical category, not per chart series.
CATEGORY_PALETTE = {
    'light': ['#2a6fd6', '#e0632a', '#12946a', '#9a5bd6', '#c9a227', '#d6486f',
              '#2aa6c9', '#7a8c1f', '#a15c2a', '#5c6bd6', '#c94f9e', '#3d9e3d',
              '#8c6b4a', '#4a7ba1', '#a1524a'],
    'dark': ['#5b9bf0', '#f08050', '#2fc191', '#b482ea', '#e0bd45', '#f07aa0',
             '#5fc9e8', '#a8c14a', '#d68a4f', '#8f9af0', '#e884c8', '#6bcf6b',
             '#c2a37e', '#7aa8d6', '#d68078'],
}


def property_landscape(frame: pd.DataFrame, output: Path) -> dict:
    """Census every recognised property, not only the ones prose covers.

    62 805 -> 106 286 observations came from teaching the header matcher four
    new non-word forms (ions, Kachinsky fractions, oxides, ratios); this table
    is what makes every one of the resulting 101 properties auditable, not
    just the handful pH/SOC discussion singles out.
    """
    def pct(series: pd.Series) -> float:
        return round(100 * series.mean(), 1) if len(series) else 0.0

    rows = []
    for pid, group in frame.groupby('property_id'):
        rows.append({
            'property_id': pid,
            'property': group.property.iloc[0],
            'category': group.category.iloc[0],
            'observations': len(group),
            'documents': int(group.document_id.nunique()),
            'header_trusted_pct': pct(group.header_match_kind != 'symbol_embedded'),
            'value_plausible_pct': pct(group.value_plausibility == 'ok'),
            'unit_proven_pct': pct(group.metric),
            'depth_pct': pct(group.depth_top_cm.notna()),
            'spatial_pct': pct(group.latitude.notna()),
        })
    census = pd.DataFrame(rows).sort_values('observations', ascending=False)
    census.to_csv(output / 'table_property_census.csv', index=False)

    for theme_name, theme in THEMES.items():
        apply_theme(theme)
        categories = sorted(census.category.unique())
        palette = dict(zip(categories, CATEGORY_PALETTE[theme_name]))
        ordered = census.sort_values('observations')
        fig, ax = plt.subplots(figsize=(9.6, max(9, 0.16 * len(ordered))))
        ax.barh(ordered.property, ordered.observations,
               color=[palette[c] for c in ordered.category], height=0.72)
        ax.set_xscale('log')
        ax.set_xlabel(('число наблюдений (лог. шкала)' if theme_name == 'light'
                       else 'число наблюдений (лог. шкала)'))
        ax.set_title('Все 101 распознанных свойства', pad=12)
        ax.tick_params(axis='y', labelsize=7.2)
        handles = [plt.Rectangle((0, 0), 1, 1, color=palette[c]) for c in categories]
        ax.legend(handles, categories, loc='lower right', fontsize=7.4, frameon=False, ncol=1)
        fig.tight_layout()
        save(fig, output, 'fig6_property_landscape', theme_name)

    proven = census[census.observations >= 200]
    return {
        'total_properties': int(len(census)),
        'best_unit_proven': proven.nlargest(5, 'unit_proven_pct')[
            ['property', 'unit_proven_pct', 'observations']].to_dict('records'),
        'worst_unit_proven': proven.nsmallest(5, 'unit_proven_pct')[
            ['property', 'unit_proven_pct', 'observations']].to_dict('records'),
        'best_depth_coverage': proven.nlargest(5, 'depth_pct')[
            ['property', 'depth_pct', 'observations']].to_dict('records'),
        'best_spatial_coverage': proven.nlargest(5, 'spatial_pct')[
            ['property', 'spatial_pct', 'observations']].to_dict('records'),
        'median_unit_proven_pct': round(float(census.unit_proven_pct.median()), 1),
        'properties_over_1000_obs': int((census.observations >= 1000).sum()),
        'properties_under_50_obs': int((census.observations < 50).sum()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    frame = load(args.db)

    with sqlite3.connect(args.db) as con:
        foreign = con.execute("""
            SELECT COUNT(*) FROM document_precise_coordinate
            WHERE latitude NOT BETWEEN 41 AND 82
               OR longitude NOT BETWEEN 19 AND 190
        """).fetchone()[0]

    findings: dict = {'layer': {
        'observations': int(len(frame)),
        'trusted': int(frame.trusted.sum()),
        'metric': int((frame.trusted & frame.metric).sum()),
        'located': int(frame.latitude.notna().sum()),
        'precise': int(frame.precise.sum()),
        'documents_outside_russia': int(foreign),
    }}

    for theme_name, theme in THEMES.items():
        findings['effort'] = figure_effort_map(frame, args.output, theme_name, theme)
        findings['zonal'] = figure_zonal(frame, args.output, theme_name, theme)
        findings['cooccurrence'] = figure_cooccurrence(frame, args.output, theme_name, theme)
        findings['depth'] = figure_depth(frame, args.output, theme_name, theme)
        findings['time'] = figure_time(frame, args.output, theme_name, theme)

    findings['zones'] = regional_table(frame, args.output)
    findings['landscape'] = property_landscape(frame, args.output)

    (args.output / 'insights.json').write_text(
        json.dumps(findings, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(findings, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
