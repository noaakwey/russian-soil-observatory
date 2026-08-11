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
# Source-specific / auto-generated categories (2026-08-11): the properties
# below couldn't be mapped to one of the 15 curated categories above without
# losing precision, so the extraction pipeline kept the source's own label
# as the category. Translated so the portal's property table never falls
# back to a raw English/snake_case string.
'soil_measurement':'почвенные измерения','soil_chemistry':'химические свойства почвы','manual_article':'ручной ввод из статьи','soil_property':'почвенное свойство','soil_physicochemical':'физико-химические свойства','soil':'почва (общее)','soil_physical_properties':'физические свойства почвы','soil_organic_properties':'органические свойства почвы','soil_physics':'физика почвы','soil_organic_pollutants':'органические загрязнители','soil_biological_properties':'биологические свойства почвы','manual_rcsi':'ручной ввод из архива РЦСИ','soil_chemical_properties':'химические свойства почвы','soil_biological_activity':'биологическая активность почвы','soil_biochemistry':'биохимия почвы','soil_profile':'почвенный профиль','soil_mineralogy':'минералогия почвы','soil_hydrology':'гидрология почвы','soil_structure':'структура почвы','soil_geochemistry':'геохимия почвы','carbon':'углерод','urban_soil_chemistry':'химия городских почв','soil_biogeochemistry':'биогеохимия почвы','soil_gas_chemistry':'почвенные газы','soil_organic_matter':'органическое вещество почвы','soil_buffering':'буферность почвы','soil_agroecology':'агроэкология почвы','soil_microbiology':'микробиология почвы','soil_aggregate':'агрегатный состав','soil_water_extract':'водная вытяжка','soil_stock':'почвенные запасы','biomass_turnover':'оборот биомассы','soil_contamination':'загрязнение почвы','sorption':'сорбция','soil_chemical':'химия почвы','aggregate_ecosystem':'агрегированные экосистемные показатели','soil_organic_chemistry':'органическая химия почвы','physical_structure':'физическая структура','soil_pollutants':'загрязнители почвы','chemical':'химические свойства','soil_buffer_chemistry':'буферная химия почвы','soil_carbon_stock':'запасы углерода почвы','diversity_index':'индекс разнообразия','soil_solution_chemistry':'химия почвенного раствора','soil_biology':'биология почвы','climate':'климат','water':'вода','climate_context':'климатический контекст','plant_measurement':'измерения растений','soil_properties':'свойства почвы','soil_amendment_properties':'свойства почвенных мелиорантов','inorganic':'неорганические вещества','water_chemistry':'химия воды','soil_elements':'элементный состав почвы','spectroscopy':'спектроскопия','nutrient':'элементы питания','nitrogen':'азот','phosphate':'фосфаты','unclassified':'неклассифицировано',
}

# Found 2026-08-11: several of the 76 auto-generated categories above are
# near- or exact synonyms of an established one (or of each other) — an
# unavoidable side effect of each being minted independently, per source
# table, whenever a property's header didn't match anything already in the
# catalogue. Left alone, the portal's category dropdown/filter shows visibly
# duplicated entries (e.g. 'soil_chemistry' and 'soil_chemical_properties'
# both render as "химические свойства почвы"). This maps each alias to the
# one canonical slug it should be grouped and displayed under; apply via
# merged_category() before any GROUP BY, dropdown population, or per-row
# category/category_ru assignment. Genuinely distinct categories (biology
# vs. biochemistry vs. microbiology; hydrology vs. hydrophysical; etc.) are
# deliberately left unmerged — "obvious" duplicates only.
CATEGORY_MERGE = {
    'soil_chemical_properties': 'soil_chemistry', 'soil_chemical': 'soil_chemistry', 'chemical': 'soil_chemistry',
    'soil_physical_properties': 'physical', 'soil_physics': 'physical',
    'soil_properties': 'soil_property', 'soil': 'soil_property',
    'soil_biological_properties': 'biological',
    'soil_geochemistry': 'geochemical',
    'soil_elements': 'elemental_oxide',
    'soil_pollutants': 'contaminant', 'soil_contamination': 'contaminant', 'soil_organic_pollutants': 'contaminant',
    'soil_buffer_chemistry': 'soil_buffering',
    'physical_structure': 'soil_structure',
    'water_chemistry': 'water',
    'nutrient': 'macronutrient', 'nitrogen': 'macronutrient', 'phosphate': 'macronutrient',
    'climate_context': 'climate',
    'soil_carbon_stock': 'organic', 'soil_organic_properties': 'organic', 'soil_organic_matter': 'organic',
    'soil_organic_chemistry': 'organic', 'carbon': 'organic',
    'soil_solution_chemistry': 'soil_solution',
}


def merged_category(category: str) -> str:
    """The canonical category slug a raw `property_definition.category` maps
    to, after collapsing the near-duplicates in CATEGORY_MERGE. Idempotent
    and total (returns the input unchanged if it has no alias)."""
    return CATEGORY_MERGE.get(category, category)


CATEGORY_EN = {
'acid_base':'Acid–base properties','salinity':'Salinity and mineralization','organic':'Organic matter and carbon','macronutrient':'Macronutrients','exchange':'Exchange complex','particle_size':'Particle-size distribution','physical':'Physical properties','hydrophysical':'Hydrophysical properties','microelement':'Microelements','contaminant':'Potential contaminants','biological':'Biological properties','geochemical':'Geochemical properties','elemental_oxide':'Elemental and oxide composition','soil_solution':'Soil solution','environmental':'Environmental conditions',
'soil_measurement':'Soil measurements','soil_chemistry':'Soil chemical properties','manual_article':'Manual entry from article text','soil_property':'Soil property','soil_physicochemical':'Physico-chemical properties','soil':'Soil (general)','soil_physical_properties':'Soil physical properties','soil_organic_properties':'Soil organic properties','soil_physics':'Soil physics','soil_organic_pollutants':'Organic pollutants','soil_biological_properties':'Soil biological properties','manual_rcsi':'Manual entry from the RCSI archive','soil_chemical_properties':'Soil chemical properties','soil_biological_activity':'Soil biological activity','soil_biochemistry':'Soil biochemistry','soil_profile':'Soil profile','soil_mineralogy':'Soil mineralogy','soil_hydrology':'Soil hydrology','soil_structure':'Soil structure','soil_geochemistry':'Soil geochemistry','carbon':'Carbon','urban_soil_chemistry':'Urban soil chemistry','soil_biogeochemistry':'Soil biogeochemistry','soil_gas_chemistry':'Soil gas chemistry','soil_organic_matter':'Soil organic matter','soil_buffering':'Soil buffering','soil_agroecology':'Soil agroecology','soil_microbiology':'Soil microbiology','soil_aggregate':'Aggregate composition','soil_water_extract':'Water extract','soil_stock':'Soil stocks','biomass_turnover':'Biomass turnover','soil_contamination':'Soil contamination','sorption':'Sorption','soil_chemical':'Soil chemistry','aggregate_ecosystem':'Aggregated ecosystem indicators','soil_organic_chemistry':'Soil organic chemistry','physical_structure':'Physical structure','soil_pollutants':'Soil pollutants','chemical':'Chemical properties','soil_buffer_chemistry':'Soil buffer chemistry','soil_carbon_stock':'Soil carbon stock','diversity_index':'Diversity index','soil_solution_chemistry':'Soil solution chemistry','soil_biology':'Soil biology','climate':'Climate','water':'Water','climate_context':'Climate context','plant_measurement':'Plant measurements','soil_properties':'Soil properties','soil_amendment_properties':'Soil amendment properties','inorganic':'Inorganic substances','water_chemistry':'Water chemistry','soil_elements':'Soil elemental composition','spectroscopy':'Spectroscopy','nutrient':'Plant nutrients','nitrogen':'Nitrogen','phosphate':'Phosphates','unclassified':'Unclassified',
}
