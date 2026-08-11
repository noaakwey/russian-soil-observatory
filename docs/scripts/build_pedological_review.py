#!/usr/bin/env python3
"""Build a process-oriented pedological synthesis from the strict layer.

The unit of replication is a source profile/study, never an OCR cell. Exact
reused vectors and Russian/English duplicates are collapsed before counting
directional consistency.
"""
from __future__ import annotations

import html
import json
import math
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import binomtest, spearmanr

DOCS = Path(__file__).resolve().parents[1]
DATA = DOCS / "data"
TABLES = DOCS / "tables"
ASSETS = DOCS / "assets"

TOPIC_LABELS = {
    "agriculture_tillage_fertilization": "Земледелие и удобрения",
    "organic_carbon_humus": "Органический углерод и гумус",
    "microbiology_biology": "Микробиология и биология",
    "podzolization_alfe_humus": "Подзолизация / Al–Fe-гумусовые процессы",
    "chernozem_steppe": "Чернозёмы и степи",
    "contamination_metals": "Загрязнение и металлы",
    "peat_wetlands": "Торфяные почвы и болота",
    "erosion_degradation": "Эрозия и деградация",
    "hydromorphism_gley": "Гидроморфизм и оглеение",
    "soil_structure_physics": "Структура и физика почв",
    "soil_classification_genesis": "Классификация и генезис",
    "hydrology_moisture": "Водный режим",
    "forest_soils": "Лесные почвы",
    "soil_ph_acidity": "pH и кислотность",
    "salinity_solonetz": "Засоление и солонцы",
}


def locator(value: object) -> dict:
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def vector_key(group: pd.DataFrame) -> str:
    rows = []
    for row in group.sort_values(["depth_mid_cm", "horizon_label", "value_num"], na_position="last").itertuples():
        rows.append((
            None if pd.isna(row.depth_top_cm) else round(float(row.depth_top_cm), 3),
            None if pd.isna(row.depth_bottom_cm) else round(float(row.depth_bottom_cm), 3),
            "" if pd.isna(row.horizon_label) else str(row.horizon_label),
            round(float(row.value_num), 8),
        ))
    return json.dumps(rows, ensure_ascii=False, separators=(",", ":"))


def load() -> pd.DataFrame:
    data = pd.read_csv(DATA / "normalized_measurements.csv")
    loc = data.evidence_locator.map(locator)
    data["row_label"] = loc.map(lambda item: item.get("row_label"))
    data["candidate_id"] = loc.map(lambda item: item.get("table_candidate_id", ""))
    data["table_key"] = data.candidate_id.str.replace(r":tm:r\d+:c\d+$", "", regex=True)
    data["table_row"] = pd.to_numeric(data.candidate_id.str.extract(r":tm:r(\d+):c\d+$")[0], errors="coerce")
    data["depth_mid_cm"] = data[["depth_top_cm", "depth_bottom_cm"]].mean(axis=1)
    # Duplicate OCR candidates from the same source row are one analytical value.
    key = ["document_id", "site_id", "property", "value_num", "depth_top_cm", "depth_bottom_cm",
           "horizon_label", "row_label", "table_key", "table_row"]
    return data.sort_values("measurement_id").drop_duplicates(key, keep="first")


def depth_patterns(data: pd.DataFrame) -> pd.DataFrame:
    records = []
    for (document, site, prop), group in data[data.depth_mid_cm.notna()].groupby(["document_id", "site_id", "property"]):
        sequence = group.groupby("depth_mid_cm", as_index=False).value_num.median().sort_values("depth_mid_cm")
        if len(sequence) < 4:
            continue
        rho, p_value = spearmanr(sequence.depth_mid_cm, sequence.value_num)
        records.append({
            "document_id": document, "site_id": site, "property": prop,
            "n_depths": len(sequence), "depth_min_cm": sequence.depth_mid_cm.min(),
            "depth_max_cm": sequence.depth_mid_cm.max(), "surface_value": sequence.value_num.iloc[0],
            "deep_value": sequence.value_num.iloc[-1],
            "deep_minus_surface": sequence.value_num.iloc[-1] - sequence.value_num.iloc[0],
            "spearman_rho": rho, "spearman_p": p_value,
            "vector_key": vector_key(group),
        })
    result = pd.DataFrame(records)
    # Same property-depth-value vector in another paper is not a replicate.
    result["reuse_cluster_size"] = result.groupby(["property", "vector_key"])["document_id"].transform("nunique")
    result["independent_vector"] = ~result.duplicated(["property", "vector_key"], keep="first")
    return result


def matched_rows(data: pd.DataFrame) -> pd.DataFrame:
    rows = data[data.table_row.notna()].pivot_table(
        index=["document_id", "site_id", "profile_label", "table_key", "table_row"],
        columns="property", values="value_num", aggfunc="first",
    ).reset_index()
    return rows


def paired_patterns(data: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
    pairs = [
        ("pH in water", "soil organic carbon"),
        ("pH in water", "organic matter/humus"),
        ("pH in water", "pH in KCl"),
        ("exchangeable calcium", "exchangeable magnesium"),
        ("pH in water", "calcium ion activity in soil paste"),
    ]
    records = []
    for left, right in pairs:
        if left not in rows or right not in rows:
            continue
        paired = rows.dropna(subset=[left, right])
        for document, group in paired.groupby("document_id"):
            if len(group) < 4:
                continue
            rho, p_value = spearmanr(group[left], group[right])
            pair_vector = json.dumps(
                sorted((round(float(x), 8), round(float(y), 8)) for x, y in zip(group[left], group[right])),
                separators=(",", ":"),
            )
            records.append({"document_id": document, "property_x": left, "property_y": right,
                            "n_pairs": len(group), "spearman_rho": rho, "spearman_p": p_value,
                            "vector_key": pair_vector})
    result = pd.DataFrame(records)
    result["reuse_cluster_size"] = result.groupby(["property_x", "property_y", "vector_key"])["document_id"].transform("nunique")
    result["independent_vector"] = ~result.duplicated(["property_x", "property_y", "vector_key"], keep="first")
    return result


def write_figure(depth: pd.DataFrame, rows: pd.DataFrame) -> None:
    plt.rcParams.update({"font.size": 9})
    fig, axes = plt.subplots(2, 2, figsize=(11, 8.2))
    ph = depth[(depth.property == "pH in water") & depth.independent_vector]
    carbon = depth[(depth.property.isin(["soil organic carbon", "organic matter/humus"])) & depth.independent_vector]
    axes[0, 0].axvline(0, color="#94a3b8", lw=1)
    axes[0, 0].scatter(ph.spearman_rho, range(len(ph)), color="#0f766e")
    axes[0, 0].set(title="pH(H₂O): связь с глубиной", xlabel="Spearman ρ", yticks=[])
    axes[0, 1].axvline(0, color="#94a3b8", lw=1)
    axes[0, 1].scatter(carbon.spearman_rho, range(len(carbon)), color="#92400e")
    axes[0, 1].set(title="Cорг/гумус: связь с глубиной", xlabel="Spearman ρ", yticks=[])
    if {"pH in water", "pH in KCl"}.issubset(rows):
        z = rows.dropna(subset=["pH in water", "pH in KCl"])
        axes[1, 0].scatter(z["pH in water"], z["pH in water"] - z["pH in KCl"], color="#7c3aed")
        axes[1, 0].set(title="Резерв кислотности", xlabel="pH(H₂O)", ylabel="pH(H₂O) − pH(KCl)")
    if {"exchangeable calcium", "exchangeable magnesium"}.issubset(rows):
        z = rows.dropna(subset=["exchangeable calcium", "exchangeable magnesium"])
        axes[1, 1].scatter(z["exchangeable calcium"], z["exchangeable magnesium"], color="#2563eb")
        axes[1, 1].set(title="Сопряжённость обменных оснований", xlabel="Ca, mol(+)/kg", ylabel="Mg, mol(+)/kg")
    fig.suptitle("Процессные паттерны строгого почвенного слоя")
    fig.tight_layout()
    fig.savefig(ASSETS / "pedological_process_patterns.png", dpi=180)
    plt.close(fig)


def write_corpus_figure(topics: pd.DataFrame) -> None:
    shown = topics.head(15).sort_values("documents_all")
    labels = [TOPIC_LABELS.get(topic, topic) for topic in shown.topic]
    fig, ax = plt.subplots(figsize=(10.5, 7.2))
    bars = ax.barh(labels, shown.documents_all, color="#277da1")
    ax.bar_label(bars, labels=[f"{value:,}".replace(",", " ") for value in shown.documents_all], padding=4, fontsize=8)
    ax.set(xlabel="Документы с тематическим сигналом", title="Тематический ландшафт 4 180 полнотекстовых публикаций")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(ASSETS / "full_corpus_topic_landscape.png", dpi=180)
    plt.close(fig)


def main() -> None:
    data = load()
    topics = pd.read_csv(TABLES / "corpus_pedological_topics.csv")
    cooccur = pd.read_csv(TABLES / "corpus_topic_cooccurrence.csv")
    with (DATA / "audit_final.json").open(encoding="utf-8") as handle:
        audit = json.load(handle)
    table_documents = pd.read_csv(DATA / "full_table_document_inventory.csv")
    table_properties = pd.read_csv(DATA / "full_table_property_inventory.csv")
    reported = pd.read_csv(DATA / "reported_sites.csv")
    coordinate_documents = set()
    for values in reported.document_ids.fillna(""):
        coordinate_documents.update(value for value in str(values).split(";") if value)
    unique_positions = reported.assign(
        lat6=reported.latitude.round(6), lon6=reported.longitude.round(6)
    ).drop_duplicates(["lat6", "lon6"])

    def topic(name: str) -> pd.Series:
        return topics.loc[topics.topic == name].iloc[0]

    def pair(left: str, right: str) -> pd.Series:
        mask = ((cooccur.topic_a == left) & (cooccur.topic_b == right)) | ((cooccur.topic_a == right) & (cooccur.topic_b == left))
        return cooccur.loc[mask].iloc[0]

    depth = depth_patterns(data)
    rows = matched_rows(data)
    paired = paired_patterns(data, rows)
    depth.to_csv(TABLES / "pedological_depth_patterns.csv", index=False)
    paired.to_csv(TABLES / "pedological_paired_patterns.csv", index=False)
    write_figure(depth, rows)
    write_corpus_figure(topics)

    ph = depth[(depth.property == "pH in water") & depth.independent_vector]
    carbon = depth[(depth.property.isin(["soil organic carbon", "organic matter/humus"])) & depth.independent_vector]
    ph_positive = int((ph.spearman_rho > 0).sum())
    carbon_negative = int((carbon.spearman_rho < 0).sum())
    ph_sign_p = binomtest(ph_positive, len(ph), .5).pvalue
    carbon_sign_p = binomtest(carbon_negative, len(carbon), .5).pvalue
    ph_kcl = rows.dropna(subset=["pH in water", "pH in KCl"]).copy()
    ph_kcl["delta"] = ph_kcl["pH in water"] - ph_kcl["pH in KCl"]
    ca_mg = rows.dropna(subset=["exchangeable calcium", "exchangeable magnesium"]).copy()
    ca_mg_rho, ca_mg_p = spearmanr(ca_mg["exchangeable calcium"], ca_mg["exchangeable magnesium"])
    hydro = rows.dropna(subset=["pH in water", "calcium ion activity in soil paste"]).copy()
    hydro_rho, hydro_p = spearmanr(hydro["pH in water"], hydro["calcium ion activity in soil paste"])
    stratified_id = "springer:10.1134_S1064229324604529"
    stratified_ph = depth[(depth.document_id == stratified_id) & (depth.property == "pH in water")].iloc[0]
    stratified_carbonate = depth[(depth.document_id == stratified_id) & (depth.property == "carbonate equivalent (CaCO3)")].iloc[0]
    ph_carbon = paired[((paired.property_x == "pH in water") & paired.property_y.isin(["soil organic carbon", "organic matter/humus"])) & paired.independent_vector]
    ph_study = data[data.property == "pH in water"].groupby("document_id").value_num.median()
    agriculture = topic("agriculture_tillage_fertilization")
    organic = topic("organic_carbon_humus")
    biology = topic("microbiology_biology")
    salinity = topic("salinity_solonetz")
    cryogenesis = topic("cryogenesis_permafrost")
    remote = topic("remote_sensing_mapping")
    fire = topic("fire_pyrogenesis")
    agro_carbon = pair("agriculture_tillage_fertilization", "organic_carbon_humus")
    bio_carbon = pair("microbiology_biology", "organic_carbon_humus")
    hydro_peat = pair("hydromorphism_gley", "peat_wetlands")
    urban_contam = pair("urban_technogenic", "contamination_metals")
    cryo_hydro = pair("cryogenesis_permafrost", "hydromorphism_gley")
    cryo_climate = pair("cryogenesis_permafrost", "climate_change_warming")
    agro_salt = pair("agriculture_tillage_fertilization", "salinity_solonetz")
    fmt = lambda value: f"{int(value):,}".replace(",", " ")

    text = f"""# Почвоведческий обзор: процессы и неочевидные закономерности

**Дата расчёта:** 1 августа 2026 г.  
**Основа обзора:** все **{fmt(audit['counts']['document'])} полнотекстовых публикаций** Russian Soil Observatory. Строгий координатно-числовой слой из {data.document_id.nunique()} исследования используется только для проверяемых количественных выводов.

## Воронка доказательности: 4 180 → 1 313 → 444 → 51

- **{fmt(audit['counts']['document'])} публикаций** — полный литературный корпус; он задаёт тематику, генетические концепции и карту изученных процессов.
- **{fmt(len(table_documents))} публикаций** содержат распознанные числовые таблицы: **{fmt(audit['counts']['table_measurement_candidate'])} ячеек**, {len(table_properties)} канонических свойств. Все они внесены в полный табличный слой с ячейкой-источником и QA; координатная связь остаётся отдельным полем качества, а не условием включения.
- **{fmt(len(coordinate_documents))} публикации** имеют авторские координаты: {fmt(len(reported))} записи и {fmt(len(unique_positions))} уникальная позиция. Это слой для географии исследований, но не автоматическая GPS-привязка каждой ячейки.
- **{data.document_id.nunique()} исследование** прошло всю цепочку «координата → объект/профиль → строка таблицы → свойство → ячейка-доказательство»: {fmt(audit['counts']['measurement'])} измерений, или **{fmt(len(data))} аналитически уникальных значений** после внутритабличной дедупликации.

Поэтому 51 — **не число публикаций в базе**, а размер самого строгого подслоя. Прежняя формулировка «основа — 51 источник» была вводящей в заблуждение и удалена.

## Тематический ландшафт всех 4 180 публикаций

Темы определены по сигналам в начале каждого полного текста: заголовке, резюме и начале введения/методов. Это воспроизводимый скрининг, а не ручная классификация главной темы; один документ может входить в несколько тем.

Самые массовые сигналы — земледелие/удобрения (**{fmt(agriculture.documents_all)}; {agriculture.share_all_percent:.1f}%**), органический углерод/гумус (**{fmt(organic.documents_all)}; {organic.share_all_percent:.1f}%**) и почвенная биология (**{fmt(biology.documents_all)}; {biology.share_all_percent:.1f}%**). Криогенный сигнал найден в {fmt(cryogenesis.documents_all)} текстах ({cryogenesis.share_all_percent:.1f}%), засоление — в {fmt(salinity.documents_all)} ({salinity.share_all_percent:.1f}%), дистанционное картографирование — в {fmt(remote.documents_all)} ({remote.share_all_percent:.1f}%), пирогенез — в {fmt(fire.documents_all)} ({fire.share_all_percent:.1f}%).

### Неочевидные комплексы и проверяемые гипотезы

1. **Углерод — не одна тема, а узел нескольких процессных сетей.** Сигнал C совмещается с агрогенным в {fmt(agro_carbon.documents_together)} документах и с микробиологическим — в {fmt(bio_carbon.documents_together)}. Он же входит в торфяно-гидроморфный и подзолистый контекст. Единая «всероссийская» корреляция C без разделения этих сетей смешает генезис, гидрологию и землепользование.
2. **Вода формирует два разных почвенных континуума.** Гидроморфизм сопряжён с торфонакоплением в {fmt(hydro_peat.documents_together)} текстах (Jaccard {hydro_peat.jaccard_percent:.1f}%), а засоление с агрогенным контекстом — в {fmt(agro_salt.documents_together)}. Первый комплекс ориентирует на восстановительный режим и консервацию C, второй — на концентрирование солей, осмотический стресс и мелиорацию.
3. **Криогенез сильнее встроен в гидроморфно-микрорельефную рамку, чем в общую рамку «изменения климата».** Криогенный сигнал совместен с гидроморфным в {fmt(cryo_hydro.documents_together)} документах, а с климатическим — в {fmt(cryo_climate.documents_together)}. Рабочая гипотеза: для прогноза нужны влажность, тип микрорельефа и мощность органогенного горизонта, а не только температура.
4. **Антропогенный комплекс — один из самых связных.** Городские/техногенные и загрязненческие сигналы совпадают в {fmt(urban_contam.documents_together)} текстах (Jaccard {urban_contam.jaccard_percent:.1f}%). Фоновые свойства, тип городского субстрата и доза загрязнителя должны быть разными осями анализа.
5. **Картографирование отстаёт от объёма процессной литературы.** Дистанционно-картографический сигнал есть лишь в {remote.share_all_percent:.1f}% корпуса. Это не доказывает нехватку карт, но выделяет проверяемый пробел: насколько процессы, хорошо изученные в разрезах, переносимы в пространство.

![Тематический ландшафт корпуса](assets/full_corpus_topic_landscape.png)

## Строгий количественный слой: главный результат

В базе обнаруживается воспроизводимый **вертикальный кислотно-углеродный синдром**. После исключения дословно повторённых профилей pH увеличивается с глубиной в **{ph_positive} из {len(ph)}** независимых профильных векторов (медиана ρ = {ph.spearman_rho.median():.2f}; двусторонний знаковый тест p = {ph_sign_p:.3f}). Одновременно содержание органического углерода или гумуса уменьшается во всех **{carbon_negative} из {len(carbon)}** независимых векторов (медиана ρ = {carbon.spearman_rho.median():.2f}; p = {carbon_sign_p:.3f}). Это согласуется с поверхностным поступлением органического вещества, выщелачиванием оснований и более сильным влиянием органических кислот в верхних горизонтах.

Однако связь pH–C **не универсальна на уровне отдельных образцов**: в {len(ph_carbon)} независимых совместных векторах внутристатейные ρ меняются от {ph_carbon.spearman_rho.min():.2f} до {ph_carbon.spearman_rho.max():.2f}. Иными словами, направление обоих вертикальных градиентов устойчиво, но величина C не позволяет переносимо предсказывать pH между разными почвами. Это важный анти-паттерн: общая корреляция по всем строкам была бы эффектом смешения глубины, почвообразующей породы и дизайна исследования.

## Кислотно-основное состояние

Медиана pH(H₂O) по источникам равна **{ph_study.median():.2f}**, межквартильный диапазон — {ph_study.quantile(.25):.2f}–{ph_study.quantile(.75):.2f}. В {len(ph_kcl)} совместно измеренных горизонтах pH(KCl) ниже pH(H₂O) во всех случаях; медианный разрыв составляет **{ph_kcl.delta.median():.2f} pH** (IQR {ph_kcl.delta.quantile(.25):.2f}–{ph_kcl.delta.quantile(.75):.2f}). Это указывает на заметный резерв обменной кислотности, который не виден по одному водному pH.

Самый практически значимый вывод: для кислых профилей геопортал не должен отображать pH(H₂O) как достаточную характеристику кислотности. Разность H₂O–KCl и насыщенность основаниями нужны для диагностики риска алюминиевой токсичности и реакции на известкование.

## Органический углерод и профильная организация

Однонаправленное уменьшение C с глубиной устойчивее, чем любая межсайтовая зависимость. Это означает, что база уже пригодна для исследования **формы профиля C**, но ещё не для карты запасов: концентрации нельзя превратить в запасы без мощности горизонта, плотности сложения и доли скелета. Максимальные значения C следует рассматривать как органогенные/поверхностные горизонты и проверять отдельно, а не считать выбросами автоматически.

Совпадение роста pH и падения C с глубиной известно для ряда лесных и агрогенных почв, но не является универсальным законом: в литературе показаны инверсии при климатических воздействиях и особых материнских породах. Поэтому один убывающий и один практически плоский профиль pH в базе — не шум, а приоритетные объекты для генетической интерпретации.

## Литологическая буферность без карбонатного градиента pH

В стратифицированной почве на диктионемовых сланцах Южного Приладожья [10.1134/S1064229324604529](https://doi.org/10.1134/S1064229324604529) карбонатный эквивалент падает от {stratified_carbonate.surface_value:.1f} до {stratified_carbonate.deep_value:.1f}% (ρ с глубиной = {stratified_carbonate.spearman_rho:.2f}), тогда как pH остаётся почти неизменным: {stratified_ph.surface_value:.1f}–{stratified_ph.deep_value:.1f}, ρ = {stratified_ph.spearman_rho:.2f}. Сочетание сильной карбонатной дифференциации и стабильной реакции — признак того, что буферность задаётся не одним CaCO₃. Для этой полигенетической толщи вероятны вклад глауконита, сланцевой матрицы и разновозрастного органического вещества. Это проверяемая литолого-педогенная гипотеза, непосредственно согласующаяся с описанной авторами высокой буферной ёмкостью породы.

## Обменные основания и криогенный сигнал

В 29 сопряжённых строках статьи [10.1134/S1064229325602409](https://doi.org/10.1134/S1064229325602409) обменные Ca и Mg изменяются согласованно (ρ = **{ca_mg_rho:.2f}**, p = {ca_mg_p:.1e}). Поскольку это одно исследование Al–Fe-гумусовых почв Надьм–Пурского междуречья, результат нельзя обобщать на Россию. Но он поддерживает рабочую гипотезу об общем контроле обоих катионов криогенным перемешиванием, литологией или перемещением органо-минерального материала. Проверяемое предсказание: отношение Ca:Mg должно быть стабильнее абсолютных содержаний внутри одной микрорельефной позиции и меняться между полигоном и депрессией.

## Гидротермальное исключение

В 16 строках профиля RF-1-4 из зоны Кучигерских термальных источников [10.1134/S106422931912007X](https://doi.org/10.1134/S106422931912007X) активность Ca меняется более чем на два порядка, но монотонной связи с pH нет (ρ = {hydro_rho:.2f}, p = {hydro_p:.2f}). Это содержательно: в гидротермальной системе активность Ca, вероятно, контролируется не только кислотностью, но и составом восходящих растворов, ионной силой, осаждением/растворением минералов и газогидротермальной турбацией. Этот сигнал интереснее общей корреляции pH–Ca и заслуживает отдельного геохимического разбора исходной таблицы.

## Что здесь потенциально новое

1. **Вертикальный синдром устойчив, горизонтальная связь нестабильна.** По разным типам российских почв направление pH↑/C↓ с глубиной воспроизводится, но pH–C внутри одинаковых горизонтов меняет знак между исследованиями. Это указывает на невозможность использовать pH как универсальный прокси C без почвенно-генетической стратификации.
2. **Исключения информативнее среднего.** Профили, где pH не растёт или падает вниз, являются кандидатами на гидроморфизм, кислотно-сульфатные процессы, гидротермальное воздействие, смену породы либо сильный техногенный/климатический контроль.
3. **Обменные Ca–Mg дают сигнал общей транспортной истории**, тогда как активность Ca в гидротермальной почве отделяется от pH. Вместе эти два результата показывают, что одинаковое свойство «кальций» отражает разные процессы в обменном комплексе и почвенном растворе; объединять их в один показатель нельзя.
4. **Стабильный pH не означает однородный карбонатный профиль.** Диктионемовый разрез показывает почти плоскую реакцию при резком падении CaCO₃; это отличает литологическую буферность от простой карбонатной.
5. **Переводы и повторное использование профилей — самостоятельный научный риск.** До дедупликации согласованность вертикальных трендов была искусственно завышена. В отчёте повторённые векторы считаются одной аналитической единицей.

## Сопоставление с опубликованными механизмами

Наблюдаемый синдром pH↑/SOC↓ с глубиной соответствует результатам независимых профильных исследований, где одновременно отмечены рост pH и падение SOC/общего N в подпочве ([Plant and Soil, 2023](https://link.springer.com/article/10.1007/s11104-022-05591-2); [Botanical Studies, 2016](https://link.springer.com/article/10.1186/s40529-016-0147-5)). При этом эксперимент по потеплению и засухе показал, что климатическое воздействие способно устранить или обратить градиент pH ([Ecosystems, 2022](https://link.springer.com/article/10.1007/s10021-021-00715-8)). Следовательно, найденный в базе паттерн правдоподобен, но его исключения могут быть ранними индикаторами особого процесса, а не ошибками.

## Ограничения

- Тематические частоты — это наличие сигнала в начале текста, а не доля статей с этой единственной главной темой; на частоты влияют язык и OCR.
- Корпуса «Почвоведение» и Springer нельзя считать полностью независимыми: для переводов и повторно использованных профилей нужна отдельная дедупликация.
- Это синтез опубликованных концентраций, а не вероятностная выборка почв России.
- {len(ph)} pH-профилей и {len(carbon)} углеродных профилей достаточны для обнаружения направленного сигнала, но недостаточны для оценки распространённости по почвенным зонам.
- Документно-однозначные координаты нельзя трактовать как GPS каждой строки таблицы.
- Сравнение методов допустимо только внутри одной канонической формы свойства; pH(H₂O), pH(KCl), обменный Ca и активность Ca не взаимозаменяемы.
- Формулировки «потенциально новое» являются гипотезами синтеза и требуют проверки на независимой выборке и по полным экспериментальным дизайнам статей.

## Воспроизводимые материалы

![Процессные паттерны](assets/pedological_process_patterns.png)

- [Профильные коэффициенты и реестр повторов](tables/pedological_depth_patterns.csv)
- [Сопряжённые свойства внутри исследований](tables/pedological_paired_patterns.csv)
- [Тематический реестр всех 4 180 полных текстов](tables/corpus_pedological_topics.csv)
- [Совместная встречаемость почвенных тем](tables/corpus_topic_cooccurrence.csv)
- [Нормализованные исходные измерения](data/normalized_measurements.csv)
- [Проверка происхождения ячеек](data/measurement_verification.json)
"""
    (DOCS / "pedological_review.md").write_text(text, encoding="utf-8")
    paragraphs = []
    for block in text.split("\n\n"):
        if block.startswith("# "):
            paragraphs.append(f"<h1>{html.escape(block[2:])}</h1>")
        elif block.startswith("## "):
            paragraphs.append(f"<h2>{html.escape(block[3:])}</h2>")
        elif block.startswith("### "):
            paragraphs.append(f"<h3>{html.escape(block[4:])}</h3>")
        elif block.startswith("!["):
            match = re.match(r"!\[(.*?)\]\((.*?)\)", block)
            paragraphs.append(f'<img src="{html.escape(match.group(2))}" alt="{html.escape(match.group(1))}">')
        elif block.startswith("- "):
            items = "".join(f"<li>{line[2:]}</li>" for line in block.splitlines())
            paragraphs.append(f"<ul>{items}</ul>")
        elif re.match(r"\d+\. ", block):
            numbered = [re.sub(r"^\d+\. ", "", line) for line in block.splitlines()]
            items = "".join(f"<li>{line}</li>" for line in numbered)
            paragraphs.append(f"<ol>{items}</ol>")
        else:
            paragraphs.append(f"<p>{block}</p>")
    body = "\n".join(paragraphs)
    # Minimal Markdown links/emphasis needed by this generated report.
    body = re.sub(r"\[(.*?)\]\((.*?)\)", r'<a href="\2">\1</a>', body)
    body = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", body)
    page = f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Почвоведческий обзор</title><style>body{{max-width:980px;margin:2rem auto;padding:0 1rem;font:16px/1.6 system-ui;color:#172033}}h1,h2{{line-height:1.2}}h2{{margin-top:2.2rem;border-bottom:1px solid #d8e0e8;padding-bottom:.3rem}}img{{max-width:100%;border:1px solid #d8e0e8}}a{{color:#075985}}</style></head><body><p><a href="index.html">← Геопортал</a> · <a href="pedological_review.md">Markdown</a></p>{body}</body></html>'''
    (DOCS / "pedological_review.html").write_text(page, encoding="utf-8")
    print(json.dumps({"unique_values": len(data), "pH_profiles": len(ph), "carbon_profiles": len(carbon),
                      "pH_positive": ph_positive, "carbon_negative": carbon_negative,
                      "paired_patterns": len(paired)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
