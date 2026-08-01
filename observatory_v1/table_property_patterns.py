"""Header patterns for the complete canonical soil-property catalog.

These patterns classify *table headers*, not arbitrary prose.  Ambiguous
one-letter chemical symbols are intentionally handled separately by the table
parser and only as standalone header tokens, never in units such as mg/kg.
"""
from __future__ import annotations

import re

# Springer OCR keeps LaTeX markup in table headers, so ``pH in water`` arrives
# as ``pH\( _{H_2O} \)``.  Matching the raw string demotes a method-specific pH
# to ``pH (method unspecified)`` and loses the very distinction the catalog
# exists to preserve.  Stripping markup is purely typographic: no token is
# added, removed or reinterpreted, only its LaTeX wrapper is dropped.
_LATEX_COMMAND = re.compile(r"\\(?:mathrm|textrm|text|mathit|left|right|rm|it)\b")


def normalize_header(header: str) -> str:
    """Return ``header`` with LaTeX wrappers removed and whitespace collapsed."""
    text = _LATEX_COMMAND.sub(" ", header)
    text = re.sub(r"\\[(){}\[\],;:!]", " ", text)
    text = re.sub(r"[\\{}$]", " ", text)
    text = text.replace("_", " ")
    # ``H_2O`` becomes ``H 2 O`` once the subscript brace is gone.
    text = re.sub(r"\bH\s*2\s*O\b", "H2O", text)
    return re.sub(r"\s+", " ", text).strip()


# A one- or two-letter chemical symbol is only trustworthy when the header says
# nothing else.  ``Zn-DTPA, mg/kg`` names an extractant and is still zinc;
# ``Excipitating minerals Ca`` and ``Thickness of horizons, cm A + B`` are not
# element columns at all.  The distinction is recorded rather than enforced:
# ``symbol_embedded`` headers stay in the database with a confidence flag, so a
# pedologist can filter them instead of trusting a silent deletion.
SYMBOL_QUALIFIERS = frozenset({
    'total', 'exchangeable', 'mobile', 'available', 'soluble', 'extractable',
    'content', 'bulk', 'gross', 'heavy', 'metals', 'metal', 'acid', 'water',
    'dtpa', 'edta', 'aab', 'hms', 'hm', 'dry', 'matter', 'soil', 'horizon',
    'of', 'in', 'the', 'and', 'per',
    'общ', 'подв', 'обм', 'вал', 'содержание', 'почв', 'сух', 'по', 'в',
})

_WORD = re.compile(r"[A-Za-zА-Яа-яЁё]+")


def symbol_match_kind(header_without_units: str, symbol_literal: str) -> str:
    """Classify how cleanly a chemical symbol stands alone in a header."""
    extra = [
        word for word in _WORD.findall(header_without_units)
        if word != symbol_literal and word.lower() not in SYMBOL_QUALIFIERS
    ]
    return 'symbol_clean' if not extra else 'symbol_embedded'


# Ordered from more specific to broader terms to avoid e.g. total/available
# nutrient variants collapsing into one property.
TABLE_PROPERTY_PATTERNS: dict[str, str] = {
    # ``рН`` is Cyrillic in most Russian PDFs; it must not be treated as the
    # Latin ``pH`` token.  OCR also splits water/KCl qualifiers across lines.
    'ph_kcl': r'(?:\b[pр]\s*[hн]\s*(?:\(?\s*KCl\s*\)?|in\s*KCl|KCl\s*solution)|[pр]\s*[hн]\s*(?:сол\w*|KCl))',
    'ph_h2o': r'(?:\b[pр]\s*[hн]\s*(?:\(?\s*H[₂2]O\s*\)?|in\s*water|water|водн\w*)|water\s+[pр]\s*[hн])',
    'ph_unspecified': r'\b[pр]\s*[hн]\b',
    'exchangeable_acidity': r'exchangeable\s+acidity|гидролитическ\w*\s+кислотност|обменн\w*\s+кислотност',
    'exchangeable_hydrogen': r'exchangeable\s+H(?:ydrogen)?|обменн\w*\s+водород',
    'electrical_conductivity': r'electrical\s+conductiv|\bEC\b|электропроводност',
    'total_dissolved_solids': r'total\s+dissolved\s+solids|\bTDS\b|сумм\w*\s+растворенн\w*\s+веществ',
    'sodium_adsorption_ratio': r'sodium\s+adsorption\s+ratio|\bSAR\b',
    'exchangeable_sodium_percentage': r'exchangeable\s+sodium\s+percentage|\bESP\b|обменн\w*\s+натри\w*\s*%',
    'soil_organic_carbon': r'soil\s+organic\s+carbon|organic\s+carbon|\bSOC\b|\bC[_ ]?org\b|органическ\w*\s+углерод|С\s*орг',
    'organic_matter': r'organic\s+matter|\bOM\b|humus|гумус|органическ\w*\s+веществ',
    'inorganic_carbon': r'inorganic\s+carbon|\bIC\b|неорганическ\w*\s+углерод',
    'carbonate_equivalent': r'carbonate\s+equivalent|CaCO[₃3]|карбонат\w*\s+эквивалент',
    'total_nitrogen': r'total\s+(?:N|nitrogen)|\bN[_ ]?total\b|общ\w*\s+азот|\bNобщ\b',
    'nitrate_n': r'nitrate(?:[- ]?N)?|\bNO[₃3][-– ]?N\b|нитрат',
    'ammonium_n': r'ammonium(?:[- ]?N)?|\bNH[₄4][-– ]?N\b|аммони',
    'mineral_nitrogen': r'mineral\s+nitrogen|минеральн\w*\s+азот',
    'total_phosphorus': r'total\s+(?:P|phosphorus)|общ\w*\s+фосфор',
    'available_phosphorus': r'available\s+(?:P|phosphorus)|mobile\s+phosphorus|P[₂2]O[₅5]|подвижн\w*\s+фосфор',
    'total_potassium': r'total\s+(?:K|potassium)|общ\w*\s+кали',
    'available_potassium': r'available\s+(?:K|potassium)|mobile\s+potassium|K[₂2]O|подвижн\w*\s+кали',
    'available_sulfur': r'available\s+sulfur|mobile\s+sulfur|подвижн\w*\s+сер',
    'sulfur': r'\btotal\s+S\b|\bsulfur\b|\bS\s*,?\s*mg|общ\w*\s+сер',
    'cation_exchange_capacity': r'cation\s+exchange\s+capacity|\bCEC\b|ёмкост\w*\s+катионн\w*\s+обмен',
    'base_saturation': r'base\s+saturation|\bBS\s*%|степен\w*\s+насыщенн\w*\s+основан',
    'potassium_exchangeable': r'exchangeable\s+(?:K|potassium)|обменн\w*\s+кали',
    'sodium': r'exchangeable\s+(?:Na|sodium)|обменн\w*\s+натри',
    'aluminium_exchangeable': r'exchangeable\s+(?:Al|aluminium|aluminum)|обменн\w*\s+алюмин',
    'coarse_sand': r'coarse\s+sand|крупн\w*\s+пес(?:ок|чан)',
    'fine_sand': r'fine\s+sand|мелк\w*\s+пес(?:ок|чан)',
    'physical_clay': r'physical\s+clay|физическ\w*\s+глин',
    'sand': r'\bsand\b|пес(?:ок|чан)',
    'silt': r'\bsilt\b|пылеват',
    'clay': r'\bclay\b|глинист',
    'bulk_density': r'bulk\s+density|dry\s+bulk\s+density|плотност\w*\s+сложения',
    'particle_density': r'particle\s+density|specific\s+gravity|плотност\w*\s+тв[её]рд\w*\s+фаз',
    'porosity': r'(?:total\s+)?porosity|пористост',
    'aggregate_stability': r'aggregate\s+stability|water[- ]stable\s+aggregates|агрегатн\w*\s+устойчивост',
    'penetration_resistance': r'penetration\s+resistance|soil\s+resistance|пенетрационн\w*\s+сопротивлен',
    'gravimetric_water_content': r'gravimetric\s+water|soil\s+moisture|влажност\w*\s+почв',
    'field_capacity': r'field\s+capacity|\bFC\b|наименьш\w*\s+влаго[её]мкост',
    'wilting_point': r'wilting\s+point|\bWP\b|влажност\w*\s+завядан',
    'water_holding_capacity': r'water[- ]holding\s+capacity|\bWHC\b|влаго[её]мкост',
    'saturated_hydraulic_conductivity': r'(?:saturated\s+)?hydraulic\s+conductivity|\bKsat\b|коэффициент\w*\s+фильтрац',
    'microbial_biomass_carbon': r'microbial\s+biomass\s+(?:C|carbon)|\bMBC\b|микробн\w*\s+биомасс\w*\s+углерод',
    'microbial_biomass_nitrogen': r'microbial\s+biomass\s+(?:N|nitrogen)|\bMBN\b|микробн\w*\s+биомасс\w*\s+азот',
    'basal_respiration': r'basal\s+(?:soil\s+)?respiration|\bBR\b|базальн\w*\s+дыхани',
    'dehydrogenase_activity': r'dehydrogenase|дегидрогеназ',
    'urease_activity': r'urease|уреаз',
    'phosphatase_activity': r'phosphatase|фосфатаз',
    'redox_potential': r'redox\s+potential|\bEh\b|окислительно[- ]восстановительн\w*\s+потенциал',
    'soil_temperature': r'soil\s+temperature|температур\w*\s+почв',
}

# Exact standalone symbols (case-sensitive); common-letter symbols are not
# used here. The parser strips known unit text before testing them.
SYMBOL_PROPERTIES = {
    'calcium': r'\bCa\b', 'magnesium': r'\bMg\b', 'zinc': r'\bZn\b',
    'copper': r'\bCu\b', 'iron': r'\bFe\b', 'manganese': r'\bMn\b',
    'boron': r'\bB\b', 'molybdenum': r'\bMo\b', 'cobalt': r'\bCo\b',
    'nickel': r'\bNi\b', 'chromium': r'\bCr\b', 'lead': r'\bPb\b',
    'cadmium': r'\bCd\b', 'arsenic': r'\bAs\b', 'mercury': r'\bHg\b',
    'selenium': r'\bSe\b',
}
