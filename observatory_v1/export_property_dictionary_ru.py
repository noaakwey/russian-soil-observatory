#!/usr/bin/env python3
"""Export the public Russian glossary for normalized soil properties."""
from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path


RU = {
 'ph_h2o':'pH водной суспензии','ph_kcl':'pH солевой (KCl) суспензии','ph_unspecified':'pH (экстрагент не указан автором)','exchangeable_acidity':'обменная кислотность','exchangeable_hydrogen':'обменный водород',
 'electrical_conductivity':'электропроводность','total_dissolved_solids':'сумма растворённых веществ','sodium_adsorption_ratio':'коэффициент адсорбции натрия (SAR)','exchangeable_sodium_percentage':'доля обменного натрия (ESP)',
 'soil_organic_carbon':'органический углерод почвы (SOC)','organic_matter':'органическое вещество / гумус','inorganic_carbon':'неорганический углерод','carbonate_equivalent':'эквивалент карбоната кальция (CaCO3)',
 'total_nitrogen':'общий азот','nitrate_n':'нитратный азот','ammonium_n':'аммонийный азот','mineral_nitrogen':'минеральный азот','total_phosphorus':'общий фосфор','available_phosphorus':'доступный фосфор','total_potassium':'общий калий','available_potassium':'доступный калий','sulfur':'сера','available_sulfur':'доступная сера',
 'calcium':'кальций','magnesium':'магний','sodium':'натрий','potassium_exchangeable':'обменный калий','aluminium_exchangeable':'обменный алюминий','cation_exchange_capacity':'ёмкость катионного обмена (ЕКО)','base_saturation':'степень насыщенности основаниями',
 'sand':'песчаная фракция','coarse_sand':'крупный песок','fine_sand':'мелкий песок','silt':'пылеватая фракция','clay':'глинистая фракция','physical_clay':'физическая глина',
 'bulk_density':'плотность сложения','particle_density':'плотность твёрдой фазы','porosity':'общая пористость','aggregate_stability':'водопрочность агрегатов','penetration_resistance':'сопротивление пенетрации',
 'gravimetric_water_content':'массовая влажность','field_capacity':'наименьшая влагоёмкость','wilting_point':'влажность завядания','water_holding_capacity':'водоудерживающая способность','saturated_hydraulic_conductivity':'коэффициент фильтрации при насыщении',
 'zinc':'цинк','copper':'медь','iron':'железо','manganese':'марганец','boron':'бор','molybdenum':'молибден','cobalt':'кобальт','nickel':'никель','chromium':'хром','lead':'свинец','cadmium':'кадмий','arsenic':'мышьяк','mercury':'ртуть','selenium':'селен',
 'microbial_biomass_carbon':'углерод микробной биомассы','microbial_biomass_nitrogen':'азот микробной биомассы','basal_respiration':'базальное дыхание','dehydrogenase_activity':'активность дегидрогеназы','urease_activity':'активность уреазы','phosphatase_activity':'активность фосфатазы','redox_potential':'окислительно-восстановительный потенциал','soil_temperature':'температура почвы',
 'calcium_ion_activity_paste':'активность ионов кальция в почвенной пасте','exchangeable_calcium':'обменный кальций','exchangeable_magnesium':'обменный магний','phosphorus_pentoxide':'пентаоксид фосфора (P2O5)','potassium_oxide':'оксид калия (K2O)',
}
UNIT_RU = {'pH':'безразмерная шкала pH','%':'процент по массе','mg/kg':'мг/кг','g/kg':'г/кг','g/L':'г/л','cmolc/kg':'смоль(+) / кг','mol(+)/kg':'моль(+) / кг','dS/m':'дСм/м','g/cm3':'г/см³','MPa':'МПа','cm/day':'см/сут','mV':'мВ','C':'°C','mg CO2/kg/day':'мг CO₂/кг/сут','mg TPF/kg/h':'мг TPF/кг/ч','mg NH4-N/kg/h':'мг NH₄-N/кг/ч','mg PNP/kg/h':'мг PNP/кг/ч','mmol/L':'ммоль/л'}

def main() -> None:
    p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with sqlite3.connect(a.db) as c:
        rows=c.execute("""WITH table_counts AS (
             SELECT property_id,count(*) numeric_cells,count(distinct artifact_id) ocr_tables
             FROM table_measurement_candidate GROUP BY property_id
           ), measurement_counts AS (
             SELECT property_id,count(*) operational_measurements FROM measurement GROUP BY property_id
           )
           SELECT pd.property_id,pd.canonical_name,pd.category,pd.canonical_unit,
             coalesce(t.numeric_cells,0),coalesce(t.ocr_tables,0),coalesce(m.operational_measurements,0)
           FROM property_definition pd
           LEFT JOIN table_counts t ON t.property_id=pd.property_id
           LEFT JOIN measurement_counts m ON m.property_id=pd.property_id
           ORDER BY numeric_cells DESC,pd.property_id""").fetchall()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    fields=['property_id','property_ru','property_en','category','canonical_unit','unit_ru','numeric_ocr_cells','ocr_tables','operational_measurements','note']
    with a.output.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for pid,en,cat,unit,cells,tables,measurements in rows:
            w.writerow({'property_id':pid,'property_ru':RU.get(pid,en),'property_en':en,'category':cat,'canonical_unit':unit or '', 'unit_ru':UNIT_RU.get(unit or '',unit or ''),'numeric_ocr_cells':cells,'ocr_tables':tables,'operational_measurements':measurements,'note':'Каноническая единица применяется только к значениям с подтверждённой совместимостью; исходная единица и ячейка сохраняются.'})
    print({'properties':len(rows),'output':str(a.output)})

if __name__=='__main__':main()
