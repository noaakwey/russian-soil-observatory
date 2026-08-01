"""Gazetteer of Russian regions for study-area attribution.

The corpus is dominated by translated articles whose Methods section names the
study area in prose ("the experiment was carried out in Kursk oblast") without
ever printing a coordinate.  Those articles previously carried no location at
all, which excluded three quarters of the observation layer from any spatial
analysis.

Each entry is a **regional centroid**, not a sampling point: ``radius_km`` is
the approximate half-extent of the unit, and it is large.  A centroid is usable
for zonal questions at the scale of several degrees and for nothing finer.

Coordinates are administrative-centre or geometric-centre approximations of the
federal subject; physiographic entries ("Siberia", "the Caucasus") are coarser
still and are only used when no federal subject is found.
"""
from __future__ import annotations

# name -> (latitude, longitude, radius_km, kind)
# ``kind`` is 'subject' for a federal subject and 'macroregion' for a
# physiographic area, which the matcher treats as a weaker fallback.
REGIONS: dict[str, tuple[float, float, float, str]] = {
    # --- European Russia: centre and black-earth belt ---
    'Moscow': (55.75, 37.62, 60, 'subject'),
    'Moscow oblast': (55.5, 37.0, 130, 'subject'),
    'Tver': (57.0, 34.5, 180, 'subject'),
    'Yaroslavl': (57.9, 39.0, 120, 'subject'),
    'Kostroma': (58.3, 43.5, 190, 'subject'),
    'Ivanovo': (57.0, 41.3, 110, 'subject'),
    'Vladimir': (56.1, 40.5, 120, 'subject'),
    'Ryazan': (54.4, 40.5, 140, 'subject'),
    'Tula': (54.0, 37.6, 110, 'subject'),
    'Kaluga': (54.5, 35.5, 120, 'subject'),
    'Bryansk': (53.0, 33.5, 130, 'subject'),
    'Oryol': (52.9, 36.5, 100, 'subject'),
    'Orel': (52.9, 36.5, 100, 'subject'),
    'Kursk': (51.7, 36.2, 110, 'subject'),
    'Belgorod': (50.8, 37.8, 110, 'subject'),
    'Voronezh': (50.9, 40.2, 160, 'subject'),
    'Lipetsk': (52.6, 39.4, 100, 'subject'),
    'Tambov': (52.7, 41.4, 120, 'subject'),
    'Smolensk': (55.0, 33.0, 150, 'subject'),
    'Pskov': (57.3, 29.0, 150, 'subject'),
    'Novgorod': (58.3, 32.5, 160, 'subject'),
    'Leningrad': (59.7, 31.5, 180, 'subject'),
    'Saint Petersburg': (59.94, 30.31, 40, 'subject'),
    'St. Petersburg': (59.94, 30.31, 40, 'subject'),
    'Kaliningrad': (54.7, 21.0, 90, 'subject'),
    'Vologda': (60.0, 41.0, 250, 'subject'),
    'Arkhangelsk': (63.5, 43.0, 400, 'subject'),
    'Murmansk': (68.0, 34.0, 250, 'subject'),
    'Karelia': (63.5, 33.0, 300, 'subject'),
    'Komi': (63.5, 55.0, 400, 'subject'),
    'Nenets': (68.0, 55.0, 350, 'subject'),

    # --- Volga ---
    'Nizhny Novgorod': (56.0, 44.5, 180, 'subject'),
    'Kirov': (58.3, 49.5, 250, 'subject'),
    'Mari El': (56.6, 47.9, 120, 'subject'),
    'Chuvashia': (55.5, 47.0, 90, 'subject'),
    'Mordovia': (54.4, 44.5, 110, 'subject'),
    'Tatarstan': (55.5, 50.5, 180, 'subject'),
    'Udmurtia': (57.2, 52.8, 130, 'subject'),
    'Bashkortostan': (54.3, 56.7, 230, 'subject'),
    'Bashkiria': (54.3, 56.7, 230, 'subject'),
    'Perm': (58.5, 56.5, 260, 'subject'),
    'Ulyanovsk': (54.1, 47.7, 120, 'subject'),
    'Samara': (53.2, 50.5, 140, 'subject'),
    'Penza': (53.2, 44.5, 120, 'subject'),
    'Saratov': (51.5, 46.5, 190, 'subject'),
    'Volgograd': (49.5, 44.0, 220, 'subject'),
    'Astrakhan': (46.9, 47.5, 160, 'subject'),
    'Kalmykia': (46.3, 45.0, 200, 'subject'),
    'Orenburg': (52.0, 55.0, 300, 'subject'),

    # --- South and Caucasus ---
    'Rostov': (47.6, 41.0, 220, 'subject'),
    'Krasnodar': (45.3, 39.3, 190, 'subject'),
    'Kuban': (45.3, 39.3, 190, 'macroregion'),
    'Adygea': (44.6, 40.1, 70, 'subject'),
    'Stavropol': (45.0, 43.3, 180, 'subject'),
    'Dagestan': (42.7, 47.0, 180, 'subject'),
    'Chechnya': (43.3, 45.7, 90, 'subject'),
    'Ingushetia': (43.2, 45.0, 50, 'subject'),
    'North Ossetia': (43.0, 44.3, 70, 'subject'),
    'Kabardino-Balkaria': (43.4, 43.4, 80, 'subject'),
    'Karachay-Cherkessia': (43.7, 41.7, 90, 'subject'),
    'Crimea': (45.2, 34.3, 130, 'subject'),

    # --- Urals and West Siberia ---
    'Sverdlovsk': (58.5, 61.0, 280, 'subject'),
    'Yekaterinburg': (56.84, 60.65, 60, 'subject'),
    'Chelyabinsk': (54.5, 61.0, 200, 'subject'),
    'Kurgan': (55.5, 65.0, 180, 'subject'),
    'Tyumen': (58.0, 69.0, 300, 'subject'),
    'Khanty-Mansi': (61.5, 70.0, 450, 'subject'),
    'Yamal': (66.5, 72.0, 450, 'subject'),
    'Yamalo-Nenets': (66.5, 72.0, 450, 'subject'),
    'Omsk': (56.0, 73.4, 220, 'subject'),
    'Novosibirsk': (55.2, 79.5, 250, 'subject'),
    'Tomsk': (58.5, 82.0, 300, 'subject'),
    'Kemerovo': (54.5, 87.0, 200, 'subject'),
    'Kuznetsk': (54.5, 87.0, 200, 'macroregion'),
    'Altai': (52.0, 83.0, 250, 'subject'),
    'Altay': (52.0, 83.0, 250, 'subject'),

    # --- East Siberia ---
    'Krasnoyarsk': (61.0, 93.0, 700, 'subject'),
    'Khakassia': (53.7, 90.0, 150, 'subject'),
    'Tuva': (51.7, 94.5, 200, 'subject'),
    'Tyva': (51.7, 94.5, 200, 'subject'),
    'Irkutsk': (56.0, 105.0, 400, 'subject'),
    'Buryatia': (53.0, 109.0, 350, 'subject'),
    'Zabaikalsky': (53.0, 116.0, 400, 'subject'),
    'Transbaikal': (53.0, 116.0, 400, 'macroregion'),
    'Yakutia': (66.0, 129.0, 900, 'subject'),
    'Sakha': (66.0, 129.0, 900, 'subject'),
    'Taimyr': (73.0, 98.0, 500, 'macroregion'),

    # --- Far East ---
    'Amur': (53.0, 128.0, 350, 'subject'),
    'Khabarovsk': (52.0, 136.0, 500, 'subject'),
    'Primorsky': (45.0, 134.5, 250, 'subject'),
    'Primorye': (45.0, 134.5, 250, 'macroregion'),
    'Sakhalin': (50.0, 143.0, 350, 'subject'),
    'Kamchatka': (56.0, 159.0, 450, 'subject'),
    'Magadan': (62.5, 153.0, 450, 'subject'),
    'Chukotka': (66.0, 172.0, 500, 'subject'),
    'Jewish Autonomous': (48.6, 132.5, 130, 'subject'),

    # --- physiographic fallbacks, used only when no subject is named ---
    'Western Siberia': (58.0, 75.0, 900, 'macroregion'),
    'West Siberia': (58.0, 75.0, 900, 'macroregion'),
    'Eastern Siberia': (62.0, 110.0, 1100, 'macroregion'),
    'East Siberia': (62.0, 110.0, 1100, 'macroregion'),
    'Siberia': (60.0, 95.0, 1500, 'macroregion'),
    'Ural': (57.0, 59.0, 700, 'macroregion'),
    'Urals': (57.0, 59.0, 700, 'macroregion'),
    'Caucasus': (43.5, 43.0, 350, 'macroregion'),
    'Baikal': (53.5, 108.0, 350, 'macroregion'),
    'Kola Peninsula': (67.7, 35.0, 250, 'macroregion'),
    'Volga': (53.0, 47.0, 600, 'macroregion'),
    'Far East': (55.0, 140.0, 1200, 'macroregion'),
    'Central Chernozem': (51.5, 38.5, 250, 'macroregion'),
    'Central Russian Upland': (52.5, 37.0, 350, 'macroregion'),
    'Barabа': (55.0, 79.0, 250, 'macroregion'),
    'Meshchera': (55.4, 40.2, 120, 'macroregion'),
    'Polesie': (52.3, 30.5, 250, 'macroregion'),
    'Caspian Lowland': (47.5, 47.5, 400, 'macroregion'),
    'Trans-Ural': (55.0, 64.0, 350, 'macroregion'),
    'Cis-Ural': (56.0, 55.0, 350, 'macroregion'),
}

# Words that follow a subject name in English translations of Russian papers.
SUBJECT_SUFFIXES = (
    'oblast', 'Oblast', 'krai', 'Krai', 'region', 'Region', 'Republic',
    'republic', 'okrug', 'Okrug', 'Territory', 'territory', 'Province', 'province',
)
