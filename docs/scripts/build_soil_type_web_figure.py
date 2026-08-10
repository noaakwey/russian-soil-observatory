#!/usr/bin/env python3
"""Light/dark web versions of the soil-type panel (figR9_soil_type) for the
portal insights page. The print version (build_manuscript_figures.py) is
Arial/600dpi/single-color and lives in docs/figures_print/; the portal needs
the usual theme-aware _light/_dark pair in docs/figures/, which was missing
entirely (insights.md referenced figures/figR9_soil_type with no matching
files ever generated for the web)."""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_insight_analysis import THEMES, apply_theme, save


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--tables', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    census = pd.read_csv(args.tables / 'table_soil_type_census.csv')
    comparison = pd.read_csv(args.tables / 'table_soil_type_comparison.csv')

    con = sqlite3.connect(f'file:{args.db}?mode=ro', uri=True)
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

    ph_groups = sorted(set(comparison.loc[comparison.property_id == 'ph_h2o',
                                          ['group_a', 'group_b']].to_numpy().ravel()),
                       key=lambda g: obs.loc[(obs.property_id == 'ph_h2o')
                                             & (obs.wrb_reference_group == g),
                                             'value_normalized'].median())
    om_groups = sorted(set(comparison.loc[comparison.property_id == 'organic_matter',
                                          ['group_a', 'group_b']].to_numpy().ravel()))

    for theme_name, theme in THEMES.items():
        apply_theme(theme)
        fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.3),
                                 gridspec_kw={'width_ratios': [1.3, 1.5, 1]})

        ax = axes[0]
        top = census.sort_values('observations', ascending=True).tail(8)
        positions = np.arange(len(top))
        ax.barh(positions, top.observations, height=.68, color=theme['series'][0], alpha=.85)
        ax.set_yticks(positions)
        ax.set_yticklabels(top.wrb_reference_group)
        ax.set_xlabel('Наблюдений (эталонный уровень)')
        ax.grid(axis='x', alpha=.35, color=theme['grid'])
        ax.set_axisbelow(True)

        panels = [('ph_h2o', 'pH водной вытяжки', ph_groups, axes[1]),
                 ('organic_matter', 'Органическое вещество, %', om_groups, axes[2])]
        for pid, title, groups, pax in panels:
            data = [obs.loc[(obs.property_id == pid) & (obs.wrb_reference_group == g),
                            'value_normalized'].dropna().to_numpy() for g in groups]
            bp = pax.boxplot(data, tick_labels=groups, showfliers=False, patch_artist=True,
                             widths=.55)
            for i, patch in enumerate(bp['boxes']):
                patch.set_facecolor(theme['series'][i % len(theme['series'])])
                patch.set_alpha(.55)
            for element in ('whiskers', 'caps', 'medians'):
                for line in bp[element]:
                    line.set_color(theme['fg'])
            pax.set_xlabel(title)
            pax.tick_params(axis='x', labelrotation=20)
            pax.grid(axis='y', alpha=.35, color=theme['grid'])
            pax.set_axisbelow(True)

        fig.tight_layout()
        save(fig, args.output, 'figR9_soil_type', theme_name)

    print('Готово: figR9_soil_type_light.png, figR9_soil_type_dark.png')


if __name__ == '__main__':
    main()
