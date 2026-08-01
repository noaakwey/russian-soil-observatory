"""Canonical property vocabulary for the Russian Soil Observatory.

Definitions are deliberately separate from extraction patterns: a property is
available in the database even when it occurs only in a prose description or a
table that needs later semantic review.
"""
PROPERTY_CATALOG = [
 ('ph_h2o','pH in water','acid_base','pH'), ('ph_kcl','pH in KCl','acid_base','pH'), ('ph_unspecified','pH (method unspecified)','acid_base','pH'),
 ('exchangeable_acidity','exchangeable acidity','acid_base','cmolc/kg'), ('exchangeable_hydrogen','exchangeable hydrogen','acid_base','cmolc/kg'),
 ('electrical_conductivity','electrical conductivity','salinity','dS/m'), ('total_dissolved_solids','total dissolved solids','salinity','g/L'),
 ('sodium_adsorption_ratio','sodium adsorption ratio','salinity',None), ('exchangeable_sodium_percentage','exchangeable sodium percentage','salinity','%'),
 ('soil_organic_carbon','soil organic carbon','organic','g/kg'), ('organic_matter','organic matter/humus','organic','%'),
 ('inorganic_carbon','inorganic carbon','organic','g/kg'), ('carbonate_equivalent','carbonate equivalent (CaCO3)','organic','%'),
 ('total_nitrogen','total nitrogen','macronutrient','g/kg'), ('nitrate_n','nitrate nitrogen','macronutrient','mg/kg'),
 ('ammonium_n','ammonium nitrogen','macronutrient','mg/kg'), ('mineral_nitrogen','mineral nitrogen','macronutrient','mg/kg'),
 ('total_phosphorus','total phosphorus','macronutrient','g/kg'), ('available_phosphorus','available phosphorus','macronutrient','mg/kg'),
 ('total_potassium','total potassium','macronutrient','g/kg'), ('available_potassium','available potassium','macronutrient','mg/kg'),
 ('sulfur','sulfur','macronutrient','mg/kg'), ('available_sulfur','available sulfur','macronutrient','mg/kg'),
 ('calcium','calcium','exchange','cmolc/kg'), ('magnesium','magnesium','exchange','cmolc/kg'),
 ('sodium','sodium','exchange','cmolc/kg'), ('potassium_exchangeable','exchangeable potassium','exchange','cmolc/kg'),
 ('aluminium_exchangeable','exchangeable aluminium','exchange','cmolc/kg'), ('cation_exchange_capacity','cation exchange capacity','exchange','cmolc/kg'),
 ('base_saturation','base saturation','exchange','%'),
 ('sand','sand','particle_size','%'), ('coarse_sand','coarse sand','particle_size','%'), ('fine_sand','fine sand','particle_size','%'),
 ('silt','silt','particle_size','%'), ('clay','clay','particle_size','%'), ('physical_clay','physical clay','particle_size','%'),
 ('bulk_density','bulk density','physical','g/cm3'), ('particle_density','particle density','physical','g/cm3'),
 ('porosity','total porosity','physical','%'), ('aggregate_stability','aggregate stability','physical','%'),
 ('penetration_resistance','penetration resistance','physical','MPa'),
 ('gravimetric_water_content','gravimetric water content','hydrophysical','%'), ('field_capacity','field capacity','hydrophysical','%'),
 ('wilting_point','wilting point','hydrophysical','%'), ('water_holding_capacity','water holding capacity','hydrophysical','%'),
 ('saturated_hydraulic_conductivity','saturated hydraulic conductivity','hydrophysical','cm/day'),
 ('zinc','zinc','microelement','mg/kg'), ('copper','copper','microelement','mg/kg'), ('iron','iron','microelement','mg/kg'),
 ('manganese','manganese','microelement','mg/kg'), ('boron','boron','microelement','mg/kg'), ('molybdenum','molybdenum','microelement','mg/kg'),
 ('cobalt','cobalt','microelement','mg/kg'), ('nickel','nickel','microelement','mg/kg'), ('chromium','chromium','microelement','mg/kg'),
 ('lead','lead','contaminant','mg/kg'), ('cadmium','cadmium','contaminant','mg/kg'), ('arsenic','arsenic','contaminant','mg/kg'),
 ('mercury','mercury','contaminant','mg/kg'), ('selenium','selenium','contaminant','mg/kg'),
 ('microbial_biomass_carbon','microbial biomass carbon','biological','mg/kg'), ('microbial_biomass_nitrogen','microbial biomass nitrogen','biological','mg/kg'),
 ('basal_respiration','basal respiration','biological','mg CO2/kg/day'), ('dehydrogenase_activity','dehydrogenase activity','biological','mg TPF/kg/h'),
 ('urease_activity','urease activity','biological','mg NH4-N/kg/h'), ('phosphatase_activity','phosphatase activity','biological','mg PNP/kg/h'),
 ('redox_potential','redox potential','geochemical','mV'), ('soil_temperature','soil temperature','environmental','C'),
]
