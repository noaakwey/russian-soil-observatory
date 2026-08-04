#!/usr/bin/env python3
"""Analytical procedures required by the manuscript but absent from the
exploratory pipeline.

``build_insight_analysis.py`` produces the exploratory figures the geoportal
links to. A manuscript needs several things that exploration did not:

* a formal test of spatial autocorrelation, because the latitude gradients are
  estimated on points that are demonstrably clustered (Clark-Evans 0.34) and a
  gradient fitted to autocorrelated residuals has an overstated significance;
* a sensitivity analysis against uneven sampling density, because 72.7% of the
  located documents sit west of 60E and a slope driven by that mass is not a
  slope over Russia;
* an explicit missingness and duplication audit, which a reader must be able
  to check rather than take on trust;
* assumption checks for every model actually reported.

Nothing here modifies the source database: the connection is opened read-only.
Every table written to ``docs/tables`` is a computed artefact; no number in the
manuscript may be entered by hand.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import warnings
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats
from statsmodels.stats.diagnostic import het_breuschpagan
from statsmodels.stats.multitest import multipletests

EARTH_RADIUS_KM = 6371.0
RUSSIA_BOUNDS = dict(lat=(41.0, 82.0), lon=(19.0, 190.0))
RANDOM_SEED = 20260803

PH_IDS = ('ph_h2o', 'ph_kcl', 'ph_unspecified')

THEMES = {
    'light': dict(bg='#fcfcfb', fg='#22211c', muted='#6b6a60', grid='#e3e2dc',
                  series=['#2a6fd6', '#e0632a', '#12946a', '#9a5bd6', '#c9a227']),
    'dark': dict(bg='#16161a', fg='#e9e8e3', muted='#9d9c93', grid='#2e2e34',
                 series=['#5b9bf0', '#f08050', '#2fc191', '#b482ea', '#e0bd45']),
}


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


def save_figure(fig, output: Path, name: str, theme_name: str) -> None:
    fig.savefig(output / f'{name}_{theme_name}.png')
    plt.close(fig)


def haversine_matrix(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Pairwise great-circle distance in km."""
    la = np.radians(lat)[:, None]
    lo = np.radians(lon)[:, None]
    inner = (np.sin((la - la.T) / 2) ** 2
             + np.cos(la) * np.cos(la.T) * np.sin((lo - lo.T) / 2) ** 2)
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(inner, 0, 1)))


# --------------------------------------------------------------------------
# Data access
# --------------------------------------------------------------------------

QUERY = """
SELECT o.observation_id, o.document_id, o.artifact_id, o.row_index, o.column_index,
       o.property_id, p.canonical_name AS property, p.category,
       o.value_num_raw, o.value_normalized, o.unit_raw, o.unit_normalized,
       o.normalization_status, u.confidence AS unit_confidence,
       f.header_match_kind, f.value_plausibility,
       o.depth_top_cm, o.depth_bottom_cm, o.row_label_raw, o.horizon_label_raw,
       y.publication_year, y.year_confidence, d.corpus,
       t.latitude, t.longitude, t.tier,
       st.soil_type_normalized, st.confidence AS soil_type_confidence,
       st.method AS soil_type_method, st.wrb_reference_group, st.wrb_confidence
FROM table_observation o
JOIN property_definition p ON p.property_id = o.property_id
JOIN observation_quality_flag f ON f.observation_id = o.observation_id
JOIN document d ON d.document_id = o.document_id
LEFT JOIN document_publication_year y ON y.document_id = o.document_id
LEFT JOIN document_spatial_tier t ON t.document_id = o.document_id
LEFT JOIN observation_soil_type st ON st.observation_id = o.observation_id
LEFT JOIN observation_unit_inference u ON u.observation_id = o.observation_id
"""


def load(db: Path) -> pd.DataFrame:
    con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    try:
        frame = pd.read_sql(QUERY, con)
    finally:
        con.close()
    frame['trusted'] = ((frame.header_match_kind != 'symbol_embedded')
                        & (frame.value_plausibility == 'ok'))
    # normalization_status is no longer a useful "is the unit proven" signal:
    # observation_unit_inference now assigns *some* unit to every observation,
    # including low-confidence fallbacks (property's usual unit, guessed from
    # article context). Only high/medium confidence is evidence strong enough
    # for quantitative comparison; 'low' is an assumption, not a printed unit.
    frame['metric'] = frame.unit_confidence.isin(['high', 'medium'])
    frame['in_russia'] = (frame.latitude.between(*RUSSIA_BOUNDS['lat'])
                          & frame.longitude.between(*RUSSIA_BOUNDS['lon']))
    frame.loc[~frame.in_russia, ['latitude', 'longitude']] = np.nan
    frame['precise'] = frame.tier.isin(['reported', 'dms']) & frame.in_russia
    return frame


# --------------------------------------------------------------------------
# 1. Missingness audit
# --------------------------------------------------------------------------

def missingness_audit(frame: pd.DataFrame, tables: Path) -> dict:
    """Field-level and property-level completeness.

    Missingness here is structural, not random: a value has no unit because
    the source table printed the unit in a caption, and no depth because the
    source table was not a profile table. Reporting it as a rate per field
    lets a reader see which analyses are possible at all.
    """
    total = len(frame)
    fields = {
        'value_num_raw': frame.value_num_raw.isna(),
        'unit_raw': frame.unit_raw.isna() | (frame.unit_raw == ''),
        'unit_normalized (проверенная единица)': ~frame.metric,
        'depth_top_cm': frame.depth_top_cm.isna(),
        'horizon_label_raw': frame.horizon_label_raw.isna(),
        'row_label_raw': frame.row_label_raw.isna(),
        'publication_year': frame.publication_year.isna(),
        'latitude/longitude': frame.latitude.isna(),
        'cell position (row_index >= 0)': frame.row_index < 0,
    }
    rows = [{'field': name, 'missing': int(mask.sum()),
             'missing_pct': round(100 * mask.mean(), 2),
             'present': int(total - mask.sum())}
            for name, mask in fields.items()]
    table = pd.DataFrame(rows).sort_values('missing_pct', ascending=False)
    table.to_csv(tables / 'table_missingness.csv', index=False)

    return {
        'observations': total,
        'fields': table.to_dict('records'),
        'legacy_without_cell_position': int((frame.row_index < 0).sum()),
    }


# --------------------------------------------------------------------------
# 2. Duplicate audit
# --------------------------------------------------------------------------

def duplicate_audit(frame: pd.DataFrame, tables: Path) -> dict:
    """Exact and probable duplicates.

    Three different things get called "a duplicate" here and they must be kept
    apart. A repeated *cell* would be an extraction fault. A repeated
    *value within one article* is usually legitimate — replicate plots, a
    control repeated across treatments. A repeated *article* (original and its
    translation) is a real double count and is handled by document_link.
    """
    positioned = frame[frame.row_index >= 0]
    cell_groups = positioned.groupby(['artifact_id', 'row_index', 'column_index']).size()
    repeated_cells = int((cell_groups > 1).sum())

    value_key = ['document_id', 'property_id', 'value_num_raw',
                 frame.depth_top_cm.fillna(-999), frame.row_label_raw.fillna('')]
    value_groups = frame.groupby(value_key, dropna=False).size()
    repeated_values = int((value_groups > 1).sum())
    observations_in_repeated = int(value_groups[value_groups > 1].sum())

    con_note = ('Повторы значений внутри одной публикации не удаляются: '
                'повторность делянок и контрольные варианты дают одинаковые '
                'числа законно.')

    table = pd.DataFrame([
        {'уровень': 'одна и та же ячейка таблицы (артефакт извлечения)',
         'групп': repeated_cells, 'наблюдений': 0 if repeated_cells == 0 else int(
             cell_groups[cell_groups > 1].sum()),
         'трактовка': 'дефект извлечения; ожидается 0'},
        {'уровень': 'одинаковое значение показателя в пределах публикации',
         'групп': repeated_values, 'наблюдений': observations_in_repeated,
         'трактовка': con_note},
    ])
    table.to_csv(tables / 'table_duplicates.csv', index=False)

    return {
        'repeated_cell_groups': repeated_cells,
        'repeated_value_groups': repeated_values,
        'observations_in_repeated_value_groups': observations_in_repeated,
    }


# --------------------------------------------------------------------------
# 3. Spatial autocorrelation (Moran's I)
# --------------------------------------------------------------------------

def morans_i(values: np.ndarray, weights: np.ndarray,
             permutations: int = 999, seed: int = RANDOM_SEED) -> dict:
    """Moran's I with a permutation test.

    Implemented directly rather than pulled from a spatial package: the whole
    computation is six lines, and a permutation null needs no distributional
    assumption about a statistic whose analytic variance is awkward on
    irregular point sets.
    """
    n = len(values)
    deviations = values - values.mean()
    denominator = (deviations ** 2).sum()
    weight_sum = weights.sum()
    if denominator == 0 or weight_sum == 0:
        return {'I': None, 'p_value': None, 'n': n}
    observed = (n / weight_sum) * (deviations @ weights @ deviations) / denominator

    rng = np.random.default_rng(seed)
    null = np.empty(permutations)
    for i in range(permutations):
        shuffled = rng.permutation(deviations)
        null[i] = (n / weight_sum) * (shuffled @ weights @ shuffled) / denominator
    # Two-sided pseudo p-value, +1 for the observed value itself.
    p_value = (np.sum(np.abs(null) >= abs(observed)) + 1) / (permutations + 1)
    expected = -1 / (n - 1)
    return {'I': round(float(observed), 4), 'expected_I': round(expected, 4),
            'p_value': round(float(p_value), 4), 'n': n,
            'permutations': permutations}


def spatial_autocorrelation(frame: pd.DataFrame, tables: Path) -> dict:
    """Moran's I on document-level values and on latitude-model residuals.

    The unit is the document, not the observation: two values from one article
    are not two places. Weights are inverse distance with a 500 km cutoff —
    beyond that separation, two Russian study sites share no landscape context
    worth calling a neighbourhood.

    Two statistics are reported because they answer different questions. On
    the raw values, Moran's I asks whether nearby sites resemble each other at
    all. On the residuals of ``value ~ latitude``, it asks the question that
    actually licenses the regression: once the latitude trend is removed, is
    there structure left that the model treats as independent noise but is
    not? Residual autocorrelation, not raw autocorrelation, is what inflates
    the significance of a fitted gradient.
    """
    base = frame[frame.trusted & frame.metric & frame.latitude.notna()]
    results = []
    for pid, group in base.groupby('property_id'):
        per_document = group.groupby('document_id').agg(
            value=('value_normalized', 'median'),
            lat=('latitude', 'first'), lon=('longitude', 'first')).dropna()
        if len(per_document) < 20:
            continue
        distances = haversine_matrix(per_document.lat.to_numpy(),
                                     per_document.lon.to_numpy())
        with np.errstate(divide='ignore'):
            weights = np.where((distances > 0) & (distances <= 500),
                               1 / np.maximum(distances, 1.0), 0.0)
        if weights.sum() == 0:
            continue

        raw = morans_i(per_document.value.to_numpy(), weights)
        if raw['I'] is None:
            continue

        fit = stats.linregress(per_document.lat, per_document.value)
        residuals = (per_document.value
                     - (fit.intercept + fit.slope * per_document.lat)).to_numpy()
        residual = morans_i(residuals, weights)

        results.append({
            'property_id': pid,
            'property': group.property.iloc[0],
            'n_documents': raw['n'],
            'morans_I_values': raw['I'],
            'p_values': raw['p_value'],
            'morans_I_residuals': residual['I'],
            'p_residuals': residual['p_value'],
            'expected_I': raw['expected_I'],
        })

    table = pd.DataFrame(results).sort_values('morans_I_residuals', ascending=False)
    if len(table):
        _, q_values, _, _ = multipletests(table.p_values, method='fdr_bh')
        _, q_residuals, _, _ = multipletests(table.p_residuals, method='fdr_bh')
        table['q_values'] = np.round(q_values, 4)
        table['q_residuals'] = np.round(q_residuals, 4)
        table['residual_autocorrelated_fdr5'] = table.q_residuals < 0.05
    table.to_csv(tables / 'table_spatial_autocorrelation.csv', index=False)
    return {
        'properties_tested': int(len(table)),
        'values_autocorrelated_fdr5': int((table.q_values < 0.05).sum()) if len(table) else 0,
        'residuals_autocorrelated_fdr5': int(table.residual_autocorrelated_fdr5.sum()) if len(table) else 0,
        'results': table.to_dict('records'),
    }


# --------------------------------------------------------------------------
# 4. Sensitivity to uneven sampling density
# --------------------------------------------------------------------------

def density_sensitivity(frame: pd.DataFrame, tables: Path, figures: Path,
                        replicates: int = 200, cell_degrees: float = 2.0) -> dict:
    """Refit the latitude slope on spatially thinned samples.

    The full sample is dominated by European Russia. Thinning to one document
    per 2-degree cell removes that mass advantage: if the slope survives
    thinning, it is a gradient over the territory rather than a contrast
    between a dense western cluster and a sparse eastern one. Repeated with
    random draws because which document represents a cell is arbitrary.
    """
    warnings.filterwarnings('ignore')
    rng = np.random.default_rng(RANDOM_SEED)
    outcomes = {}

    targets = [
        ('ph_h2o', 'pH водный', False, lambda f: f[f.property_id.isin(PH_IDS) & f.precise]),
        ('soil_organic_carbon', 'C орг. (log)', True,
         lambda f: f[(f.property_id == 'soil_organic_carbon') & f.metric
                     & (f.unit_normalized == 'g/kg')]),
    ]

    for pid, label, use_log, selector in targets:
        subset = selector(frame[frame.trusted & frame.latitude.notna()])
        column = 'value_normalized' if use_log else 'value_num_raw'
        per_document = subset.groupby('document_id').agg(
            value=(column, 'median'), lat=('latitude', 'first'),
            lon=('longitude', 'first')).dropna()
        if len(per_document) < 25:
            continue
        if use_log:
            per_document = per_document[per_document.value > 0]
            per_document['value'] = np.log(per_document.value)

        full_fit = stats.linregress(per_document.lat, per_document.value)

        per_document['cell'] = (
            (per_document.lat // cell_degrees).astype(int).astype(str) + '_'
            + (per_document.lon // cell_degrees).astype(int).astype(str))

        slopes = []
        for _ in range(replicates):
            picked = (per_document.assign(draw=rng.random(len(per_document)))
                      .sort_values('draw').groupby('cell').head(1))
            if len(picked) < 15:
                continue
            fit = stats.linregress(picked.lat, picked.value)
            slopes.append(fit.slope)

        slopes = np.array(slopes)
        outcomes[pid] = {
            'label': label,
            'log_transformed': use_log,
            'n_documents_full': int(len(per_document)),
            'n_cells': int(per_document.cell.nunique()),
            'slope_full_sample': round(float(full_fit.slope), 4),
            'slope_thinned_median': round(float(np.median(slopes)), 4),
            # NOT a confidence interval on the slope: it is the spread of the
            # point estimate across which document happened to represent each
            # cell. It answers "is this slope an artefact of where sampling is
            # dense", not "how precisely is the slope known".
            'slope_thinned_p2.5_p97.5_across_draws': [
                round(float(np.percentile(slopes, 2.5)), 4),
                round(float(np.percentile(slopes, 97.5)), 4)],
            'share_of_thinned_slopes_below_zero': round(float((slopes < 0).mean()), 3),
            'replicates': int(len(slopes)),
        }

    pd.DataFrame(outcomes).T.to_csv(tables / 'table_density_sensitivity.csv')

    for theme_name, theme in THEMES.items():
        apply_theme(theme)
        fig, axes = plt.subplots(1, len(outcomes), figsize=(5.4 * len(outcomes), 3.6))
        if len(outcomes) == 1:
            axes = [axes]
        for ax, (pid, result) in zip(axes, outcomes.items()):
            subset = frame[frame.trusted & frame.latitude.notna()]
            ax.axvline(result['slope_full_sample'], color=theme['series'][1],
                       linewidth=2, label='полная выборка')
            ax.axvspan(result['slope_thinned_p2.5_p97.5_across_draws'][0],
                       result['slope_thinned_p2.5_p97.5_across_draws'][1],
                       color=theme['series'][0], alpha=.22,
                       label='разброс по жребиям прореживания')
            ax.axvline(result['slope_thinned_median'], color=theme['series'][0],
                       linewidth=2, linestyle='--', label='медиана прореженных')
            ax.axvline(0, color=theme['muted'], linewidth=1, linestyle=':')
            ax.set_title(f"{result['label']}\n({result['n_cells']} ячеек 2°×2°)")
            ax.set_xlabel('наклон на градус широты')
            ax.set_yticks([])
            ax.legend(frameon=False, fontsize=8)
        fig.tight_layout()
        save_figure(fig, figures, 'fig10_density_sensitivity', theme_name)

    return outcomes


# --------------------------------------------------------------------------
# 5. Model assumption checks
# --------------------------------------------------------------------------

def assumption_checks(frame: pd.DataFrame, tables: Path) -> dict:
    """Residual diagnostics for every model the manuscript reports.

    A latitude slope is only interpretable if its residuals are not wildly
    non-normal and not systematically heteroscedastic. Reporting the
    diagnostics rather than asserting the model was appropriate is the point.
    """
    warnings.filterwarnings('ignore')
    rows = []

    specifications = [
        ('pH ~ широта (документные средние)',
         lambda f: f[f.property_id.isin(PH_IDS) & f.trusted & f.precise
                     & f.latitude.notna()],
         'value_num_raw', False),
        ('log(C орг.) ~ широта (документные средние)',
         lambda f: f[(f.property_id == 'soil_organic_carbon') & f.trusted & f.metric
                     & (f.unit_normalized == 'g/kg') & f.latitude.notna()],
         'value_normalized', True),
        ('C орг. ~ широта, без логарифмирования',
         lambda f: f[(f.property_id == 'soil_organic_carbon') & f.trusted & f.metric
                     & (f.unit_normalized == 'g/kg') & f.latitude.notna()],
         'value_normalized', False),
    ]

    for label, selector, column, use_log in specifications:
        subset = selector(frame)
        per_document = subset.groupby('document_id').agg(
            value=(column, 'median'), lat=('latitude', 'first')).dropna()
        if use_log:
            per_document = per_document[per_document.value > 0]
            per_document['value'] = np.log(per_document.value)
        if len(per_document) < 20:
            continue

        model = smf.ols('value ~ lat', per_document).fit()
        residuals = model.resid
        # Shapiro-Wilk is exact for n < 5000 and these samples are far smaller.
        shapiro_stat, shapiro_p = stats.shapiro(residuals)
        bp_stat, bp_p, _, _ = het_breuschpagan(residuals, model.model.exog)
        influence = model.get_influence()
        cooks = influence.cooks_distance[0]

        rows.append({
            'модель': label,
            'n': int(len(per_document)),
            'наклон': round(float(model.params['lat']), 4),
            'p_наклона': float(f"{model.pvalues['lat']:.3g}"),
            'R2': round(float(model.rsquared), 4),
            'асимметрия остатков': round(float(stats.skew(residuals)), 3),
            'эксцесс остатков': round(float(stats.kurtosis(residuals)), 3),
            'Шапиро-Уилк p': float(f'{shapiro_p:.3g}'),
            'Бройш-Паган p': float(f'{bp_p:.3g}'),
            'набл. с D Кука > 4/n': int((cooks > 4 / len(per_document)).sum()),
        })

    table = pd.DataFrame(rows)
    table.to_csv(tables / 'table_assumption_checks.csv', index=False)
    return table.to_dict('records')


# --------------------------------------------------------------------------
# 6. Spatio-temporal representativeness
# --------------------------------------------------------------------------

DEPTH_SWEEP_MIN_DOCS = 10
DEPTH_SWEEP_MIN_OBS = 40

# Properties measured on a bounded or already-dimensionless scale stay linear;
# concentrations are log-transformed when their own skewness calls for it.
ZONAL_SWEEP_LINEAR = {'ph_h2o', 'ph_kcl', 'ph_unspecified', 'base_saturation',
                      'porosity', 'bulk_density'}


def depth_sweep(frame: pd.DataFrame, tables: Path) -> dict:
    """Profile behaviour of every property with enough depth data, not two.

    The exploratory analysis characterised depth dependence for organic carbon
    and pH because those are the properties a soil scientist expects to see.
    That is a selection made by the analyst, not by the data: 22 properties
    carry depth for a quarter or more of their values, and several of the
    granulometric fractions are far better provided with depth than carbon is.
    Running one specification across all of them turns "we looked at two" into
    "we looked at everything the data supports, and here is which ones move".
    """
    warnings.filterwarnings('ignore')
    base = frame[frame.trusted & frame.metric & frame.depth_top_cm.notna()
                 & (frame.depth_top_cm < 200)]
    rows = []
    for pid, group in base.groupby('property_id'):
        data = group[['document_id', 'depth_top_cm', 'value_normalized']].dropna()
        if len(data) < DEPTH_SWEEP_MIN_OBS or data.document_id.nunique() < DEPTH_SWEEP_MIN_DOCS:
            continue
        values = data.value_normalized
        use_log = (pid not in ZONAL_SWEEP_LINEAR and (values >= 0).all()
                   and values.skew() > 1 and (values > 0).any())
        if use_log:
            floor = values[values > 0].min() / 2
            data = data.assign(value=np.log(values.clip(lower=floor)))
        else:
            data = data.assign(value=values)
        try:
            fitted = smf.mixedlm('value ~ depth_top_cm', data,
                                 groups=data['document_id']).fit(reml=True)
        except Exception:
            continue
        low, high = fitted.conf_int().loc['depth_top_cm']
        variance_document = float(fitted.cov_re.iloc[0, 0])
        rows.append({
            'property_id': pid,
            'property': group.property.iloc[0],
            'category': group.category.iloc[0],
            'unit': group.unit_normalized.mode().iat[0] if len(group.unit_normalized.dropna()) else None,
            'n_observations': len(data),
            'n_documents': int(data.document_id.nunique()),
            'log_transformed': use_log,
            'slope_per_cm': float(fitted.params['depth_top_cm']),
            'ci_low': float(low), 'ci_high': float(high),
            'p_value': float(fitted.pvalues['depth_top_cm']),
            'icc_document': variance_document / (variance_document + float(fitted.scale)),
        })

    table = pd.DataFrame(rows)
    if len(table):
        _, qvals, _, _ = multipletests(table.p_value, method='fdr_bh')
        table['q_value'] = qvals
        table['significant_fdr5'] = table.q_value < 0.05
        table = table.sort_values('slope_per_cm')
    table.round(6).to_csv(tables / 'table_depth_sweep.csv', index=False)

    significant = table[table.significant_fdr5] if len(table) else table
    return {
        'properties_tested': int(len(table)),
        'properties_significant_fdr5': int(len(significant)),
        'increasing_with_depth': int((significant.slope_per_cm > 0).sum()) if len(significant) else 0,
        'decreasing_with_depth': int((significant.slope_per_cm < 0).sum()) if len(significant) else 0,
        'results': table.to_dict('records'),
    }


def distribution_shape(frame: pd.DataFrame, tables: Path) -> dict:
    """Skewness and dispersion for every property, not only the discussed ones.

    Whether a property needs a log scale is a property of its distribution,
    not of the analyst's habit. Tabulating skewness and the coefficient of
    variation across the whole catalogue states the rule that was applied and
    lets a reader check it for any property they intend to use.
    """
    base = frame[frame.trusted & frame.metric]
    rows = []
    for pid, group in base.groupby('property_id'):
        values = group.value_normalized.dropna()
        if len(values) < 30:
            continue
        mean = float(values.mean())
        rows.append({
            'property_id': pid,
            'property': group.property.iloc[0],
            'category': group.category.iloc[0],
            'unit': group.unit_normalized.mode().iat[0] if len(group.unit_normalized.dropna()) else None,
            'n': int(len(values)),
            'mean': round(mean, 4),
            'median': round(float(values.median()), 4),
            'sd': round(float(values.std()), 4),
            'cv': round(float(values.std() / mean), 3) if mean else None,
            'skewness': round(float(stats.skew(values)), 3),
            'mean_over_median': round(mean / float(values.median()), 3) if values.median() else None,
        })
    table = pd.DataFrame(rows).sort_values('skewness', ascending=False)
    table.to_csv(tables / 'table_distribution_shape.csv', index=False)
    return {
        'properties_described': int(len(table)),
        'strongly_right_skewed': int((table.skewness > 2).sum()),
        'approximately_symmetric': int((table.skewness.abs() <= 0.5).sum()),
        'median_cv': round(float(table.cv.median()), 3),
        'median_skewness': round(float(table.skewness.median()), 3),
    }


SOIL_TYPE_RELIABLE_CONFIDENCE = 'high'
SOIL_TYPE_RELIABLE_WRB = ('high', 'medium')
SOIL_TYPE_MIN_DOCS = 10  # for a WRB group to enter the census as "eligible"
SOIL_TYPE_MIN_DOCS_PER_COMPARISON = 5  # for that group to enter one property's test


def soil_type_stratification(frame: pd.DataFrame, tables: Path) -> dict:
    """Does the within-zone scatter the latitude sweep could not explain
    resolve once observations are grouped by soil type instead of by degree?

    ``observation_soil_type`` links a soil name to an observation with its own
    evidence tier, exactly like the spatial tiers: ``confidence`` states
    whether the name came from the specific table/profile (``high``: methods
    ``table_soil_header``, ``table_context``, ``profile_classification``) or
    only from the dominant classification mentioned anywhere in the article
    (``low``: ``dominant_article_context``, ``additional_taxonomy_context``).
    Only the high-confidence, row/table-linked tier is used here; document-level
    guesses would reintroduce exactly the pseudo-replication problem this
    manuscript's spatial analysis was built to avoid. ``wrb_reference_group``
    carries its own separate confidence for the Russian-name-to-WRB-2022
    mapping, checked the same way.
    """
    reliable = frame[(frame.soil_type_confidence == SOIL_TYPE_RELIABLE_CONFIDENCE)
                     & frame.wrb_confidence.isin(SOIL_TYPE_RELIABLE_WRB)
                     & frame.wrb_reference_group.notna()]

    census = (reliable.groupby('wrb_reference_group')
              .agg(observations=('observation_id', 'size'),
                   documents=('document_id', 'nunique'))
              .sort_values('observations', ascending=False))
    census.to_csv(tables / 'table_soil_type_census.csv')

    eligible_groups = census[census.documents >= SOIL_TYPE_MIN_DOCS].index.tolist()

    # Swept over every property with trustworthy, unit-proven values in the
    # reliable soil-type tier — not a chosen pair — for the same reason the
    # depth and latitude checks are swept: two properties chosen by the
    # analyst answer only the question the analyst thought to ask.
    rows = []
    candidate_properties = (reliable[reliable.trusted & reliable.metric
                                     & reliable.wrb_reference_group.isin(eligible_groups)]
                            .property_id.unique())
    for pid in sorted(candidate_properties):
        base = reliable[(reliable.property_id == pid) & reliable.trusted
                        & reliable.metric
                        & reliable.wrb_reference_group.isin(eligible_groups)]
        if base.empty:
            continue
        per_doc = (base.groupby(['wrb_reference_group', 'document_id'])
                   .value_normalized.median().reset_index())
        counts = per_doc.wrb_reference_group.value_counts()
        groups = counts[counts >= SOIL_TYPE_MIN_DOCS_PER_COMPARISON].index.tolist()
        if len(groups) < 2:
            continue
        # Every pairwise contrast among the adequately sampled groups for this
        # property, not just the two largest, so a third well-covered group
        # is not silently dropped.
        for i, group_a in enumerate(groups):
            for group_b in groups[i + 1:]:
                sample_a = per_doc.loc[per_doc.wrb_reference_group == group_a,
                                       'value_normalized']
                sample_b = per_doc.loc[per_doc.wrb_reference_group == group_b,
                                       'value_normalized']
                stat, p = stats.mannwhitneyu(sample_a, sample_b,
                                             alternative='two-sided')
                rows.append({
                    'property_id': pid,
                    'group_a': group_a, 'n_documents_a': int(len(sample_a)),
                    'median_a': float(sample_a.median()),
                    'group_b': group_b, 'n_documents_b': int(len(sample_b)),
                    'median_b': float(sample_b.median()),
                    'mannwhitney_u': float(stat), 'p_value': float(p),
                })

    table = pd.DataFrame(rows)
    if len(table):
        _, qvals, _, _ = multipletests(table.p_value, method='fdr_bh')
        table['q_value'] = qvals
        table['significant_fdr5'] = table.q_value < 0.05
    table.round(6).to_csv(tables / 'table_soil_type_comparison.csv', index=False)

    return {
        'reliable_tier_observations': int(len(reliable)),
        'reliable_tier_documents': int(reliable.document_id.nunique()),
        'wrb_groups_total': int(census.shape[0]),
        'wrb_groups_eligible': len(eligible_groups),
        'min_documents_per_group': SOIL_TYPE_MIN_DOCS,
        'census': census.reset_index().to_dict('records'),
        'pairwise_comparisons': table.to_dict('records'),
    }


def independent_localities(db: Path, tables: Path) -> dict:
    """How many independent places do the reported coordinates represent?

    790 distinct coordinate pairs are not 790 independent samples of the
    territory: a study area is routinely described by several pits a few
    hundred metres apart. Single-linkage agglomeration at a set of distance
    thresholds converts the point count into a locality count, which is the
    honest denominator for any statement about spatial coverage.
    """
    con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    try:
        points = pd.read_sql("""
            SELECT DISTINCT ROUND(latitude, 5) AS lat, ROUND(longitude, 5) AS lon
            FROM site
            WHERE latitude IS NOT NULL
              AND spatial_confidence IN ('exact', 'reported')
        """, con)
    finally:
        con.close()

    distances = haversine_matrix(points.lat.to_numpy(), points.lon.to_numpy())
    n = len(points)

    rows = []
    for threshold in (1, 5, 10, 25, 50, 100):
        # Single-linkage agglomeration by breadth-first search over the
        # thresholded adjacency: two points join a cluster when a chain of
        # within-threshold neighbours connects them.
        adjacency = distances <= threshold
        seen = np.zeros(n, dtype=bool)
        clusters = 0
        for start in range(n):
            if seen[start]:
                continue
            clusters += 1
            queue = [start]
            seen[start] = True
            while queue:
                current = queue.pop()
                neighbours = np.where(adjacency[current] & ~seen)[0]
                seen[neighbours] = True
                queue.extend(neighbours.tolist())
        rows.append({'threshold_km': threshold, 'localities': clusters})

    table = pd.DataFrame(rows)
    table.to_csv(tables / 'table_independent_localities.csv', index=False)
    return {'unique_positions': n, 'by_threshold': table.to_dict('records')}


def representativeness(frame: pd.DataFrame, tables: Path, figures: Path) -> dict:
    """Occupied grid cells and how observation effort is distributed in them.

    A count of documents per cell says how much was studied where; the Gini
    coefficient over cell counts says how unevenly. Both are properties of the
    literature, not of the soil cover, and are labelled as such.
    """
    located = frame[frame.trusted & frame.latitude.notna()]
    per_document = located.groupby('document_id').agg(
        lat=('latitude', 'first'), lon=('longitude', 'first'),
        observations=('observation_id', 'size'),
        year=('publication_year', 'first')).dropna(subset=['lat', 'lon'])

    per_document['cell_lat'] = (per_document.lat // 5 * 5).astype(int)
    per_document['cell_lon'] = (per_document.lon // 5 * 5).astype(int)
    cells = (per_document.groupby(['cell_lat', 'cell_lon'])
             .agg(documents=('observations', 'size'),
                  observations=('observations', 'sum')).reset_index())
    cells.to_csv(tables / 'table_grid_cells.csv', index=False)

    counts = np.sort(cells.documents.to_numpy())
    n = len(counts)
    cumulative = np.cumsum(counts)
    gini = float((n + 1 - 2 * (cumulative / cumulative[-1]).sum()) / n)

    # Temporal split: is the geography of study stable across the corpus?
    early = per_document[per_document.year <= 2013]
    late = per_document[per_document.year >= 2019]
    early_cells = set(zip(early.cell_lat, early.cell_lon))
    late_cells = set(zip(late.cell_lat, late.cell_lon))

    for theme_name, theme in THEMES.items():
        apply_theme(theme)
        fig, ax = plt.subplots(figsize=(9.6, 4.6))
        size = 12 + 58 * (cells.documents / cells.documents.max())
        scatter = ax.scatter(cells.cell_lon + 2.5, cells.cell_lat + 2.5,
                             s=size, c=cells.documents,
                             cmap='viridis' if theme_name == 'dark' else 'YlGnBu',
                             edgecolors='none', alpha=.9)
        ax.set_xlim(18, 182); ax.set_ylim(40, 80)
        ax.set_xlabel('в. д.'); ax.set_ylabel('с. ш.')
        ax.set_title('Плотность исследовательского усилия: публикаций\n'
                     'на ячейку 5°×5° (не плотность почвенных наблюдений в природе)')
        ax.grid(alpha=.3, linewidth=.6)
        bar = fig.colorbar(scatter, ax=ax, fraction=.03, pad=.02)
        bar.set_label('публикаций в ячейке')
        bar.outline.set_visible(False)
        fig.tight_layout()
        save_figure(fig, figures, 'fig11_density_grid', theme_name)

    return {
        'documents_located': int(len(per_document)),
        'occupied_cells_5deg': int(len(cells)),
        'gini_documents_per_cell': round(gini, 3),
        'max_documents_in_one_cell': int(cells.documents.max()),
        'median_documents_per_cell': float(cells.documents.median()),
        'cells_with_single_document': int((cells.documents == 1).sum()),
        'cells_2006_2013': len(early_cells),
        'cells_2019_2026': len(late_cells),
        'cells_in_both_periods': len(early_cells & late_cells),
    }


# --------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--tables', type=Path, required=True)
    parser.add_argument('--figures', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    args.tables.mkdir(parents=True, exist_ok=True)
    args.figures.mkdir(parents=True, exist_ok=True)

    frame = load(args.db)

    findings = {
        'generated_from': str(args.db),
        'observations': int(len(frame)),
        'missingness': missingness_audit(frame, args.tables),
        'duplicates': duplicate_audit(frame, args.tables),
        'depth_sweep': depth_sweep(frame, args.tables),
        'distribution_shape': distribution_shape(frame, args.tables),
        'independent_localities': independent_localities(args.db, args.tables),
        'spatial_autocorrelation': spatial_autocorrelation(frame, args.tables),
        'density_sensitivity': density_sensitivity(frame, args.tables, args.figures),
        'assumption_checks': assumption_checks(frame, args.tables),
        'representativeness': representativeness(frame, args.tables, args.figures),
        'soil_type_stratification': soil_type_stratification(frame, args.tables),
    }

    text = json.dumps(findings, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + '\n', encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
