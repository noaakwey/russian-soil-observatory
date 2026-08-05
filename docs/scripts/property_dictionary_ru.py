"""Russian labels for the canonical property vocabulary used in publication."""
from __future__ import annotations

RU = {
'ph_h2o':'pH водной вытяжки','ph_kcl':'pH солевой (KCl) вытяжки','ph_unspecified':'pH (экстрагент не указан автором)','exchangeable_acidity':'обменная кислотность','exchangeable_hydrogen':'обменный водород',
'electrical_conductivity':'электропроводность','total_dissolved_solids':'общее содержание растворённых веществ','sodium_adsorption_ratio':'коэффициент адсорбции натрия (SAR)','exchangeable_sodium_percentage':'доля обменного натрия (ESP)',
'soil_organic_carbon':'органический углерод почвы','organic_matter':'органическое вещество (гумус)','inorganic_carbon':'неорганический углерод','carbonate_equivalent':'карбонатный эквивалент (CaCO₃)',
'water_soluble_organic_carbon':'водорастворимый органический углерод','silicon_dioxide':'диоксид кремния (SiO₂)','iron_oxide_fe2o3':'оксид железа (Fe₂O₃)','aluminum_oxide_al2o3':'оксид алюминия (Al₂O₃)','calcium_oxide_cao':'оксид кальция (CaO)','magnesium_oxide_mgo':'оксид магния (MgO)','potassium_oxide_k2o':'оксид калия (K₂O)','sodium_oxide_na2o':'оксид натрия (Na₂O)',
'total_nitrogen':'общий азот','nitrate_n':'нитратный азот','ammonium_n':'аммонийный азот','mineral_nitrogen':'минеральный азот',
'total_phosphorus':'общий фосфор','available_phosphorus':'подвижный фосфор','phosphorus_pentoxide':'пентаоксид фосфора (P₂O₅)','total_potassium':'общий калий','available_potassium':'подвижный калий','potassium_oxide':'оксид калия (K₂O)','sulfur':'общая сера','available_sulfur':'подвижная сера',
'calcium':'кальций','exchangeable_calcium':'обменный кальций','magnesium':'магний','exchangeable_magnesium':'обменный магний','sodium':'натрий','potassium_exchangeable':'обменный калий','aluminium_exchangeable':'обменный алюминий','cation_exchange_capacity':'ёмкость катионного обмена','base_saturation':'степень насыщенности основаниями','calcium_ion_activity_paste':'активность ионов кальция в почвенной пасте',
'sand':'песок','coarse_sand':'крупный песок','fine_sand':'мелкий песок','silt':'пылеватая фракция','clay':'глина','physical_clay':'физическая глина',
'fine_fraction_lt_0_001mm':'илистая фракция (<0,001 мм)',
'bulk_density':'плотность сложения','particle_density':'плотность твёрдой фазы','porosity':'общая пористость','aggregate_stability':'агрегатная устойчивость','penetration_resistance':'сопротивление пенетрации',
'gravimetric_water_content':'массовая влажность','field_capacity':'наименьшая влагоёмкость','wilting_point':'влажность завядания','water_holding_capacity':'водоудерживающая способность','saturated_hydraulic_conductivity':'насыщенная гидравлическая проводимость',
'zinc':'цинк','copper':'медь','iron':'железо','manganese':'марганец','boron':'бор','molybdenum':'молибден','cobalt':'кобальт','nickel':'никель','chromium':'хром',
'lead':'свинец','cadmium':'кадмий','arsenic':'мышьяк','mercury':'ртуть','selenium':'селен',
'microbial_biomass_carbon':'углерод микробной биомассы','microbial_biomass_nitrogen':'азот микробной биомассы','basal_respiration':'базальное дыхание','dehydrogenase_activity':'дегидрогеназная активность','urease_activity':'уреазная активность','phosphatase_activity':'фосфатазная активность',
'redox_potential':'окислительно-восстановительный потенциал (Eh)','soil_temperature':'температура почвы',
'titanium_dioxide':'диоксид титана (TiO₂)','coarse_silt':'крупная пыль (0.05–0.01 мм)','manganese_oxide_mno':'оксид марганца (MnO)',
'calcium_ion':'катион кальция Ca²⁺','magnesium_ion':'катион магния Mg²⁺','sodium_ion':'катион натрия Na⁺','potassium_ion':'катион калия K⁺','ammonium_ion':'катион аммония NH₄⁺','hydrogen_ion':'катион водорода H⁺','aluminium_ion':'катион алюминия Al³⁺',
'chloride_ion':'хлорид-ион Cl⁻','sulfate_ion':'сульфат-ион SO₄²⁻','bicarbonate_ion':'гидрокарбонат-ион HCO₃⁻','carbonate_ion':'карбонат-ион CO₃²⁻','nitrate_ion':'нитрат-ион NO₃⁻',
'carbon_nitrogen_ratio':'отношение C/N','carbon_phosphorus_ratio':'отношение C/P','hydrogen_carbon_ratio':'отношение H/C','oxygen_carbon_ratio':'отношение O/C',
}

CATEGORY_RU = {
'acid_base':'кислотно-основные','salinity':'засоление и минерализация','organic':'органическое вещество и углерод','macronutrient':'макроэлементы','exchange':'обменный комплекс','particle_size':'гранулометрический состав','physical':'физические свойства','hydrophysical':'гидрофизические свойства','microelement':'микроэлементы','contaminant':'потенциальные загрязнители','biological':'биологические свойства','geochemical':'геохимические свойства','elemental_oxide':'элементный и оксидный состав','soil_solution':'почвенный раствор','environmental':'условия среды',
}

CATEGORY_EN = {
'acid_base':'Acid–base properties','salinity':'Salinity and mineralization','organic':'Organic matter and carbon','macronutrient':'Macronutrients','exchange':'Exchange complex','particle_size':'Particle-size distribution','physical':'Physical properties','hydrophysical':'Hydrophysical properties','microelement':'Microelements','contaminant':'Potential contaminants','biological':'Biological properties','geochemical':'Geochemical properties','elemental_oxide':'Elemental and oxide composition','soil_solution':'Soil solution','environmental':'Environmental conditions',
}
