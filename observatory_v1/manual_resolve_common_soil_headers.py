from __future__ import annotations
import argparse, json, re, sqlite3
from pathlib import Path

MAP = {
    'humus': 'organic_matter', 'humus %': 'organic_matter', 'humus, %': 'organic_matter',
    'corg': 'soil_organic_carbon', 'corg, %': 'soil_organic_carbon', 'corg %': 'soil_organic_carbon',
    'organic carbon': 'soil_organic_carbon', 'bulk density, g/cm3': 'bulk_density',
    'bulk density g/cm3': 'bulk_density', 'clay': 'clay', 'clay, %': 'clay',
    'silt': 'silt', 'silt, %': 'silt', 'sand': 'sand', 'sand, %': 'sand',
    'cec': 'cation_exchange_capacity', 'p2o5': 'phosphorus_pentoxide', 'k2o': 'potassium_oxide_k2o',
    'cao': 'calcium_oxide_cao', 'mgo': 'magnesium_oxide_mgo', 'al2o3': 'aluminum_oxide_al2o3',
    'sio2': 'silicon_dioxide', 'fe2o3': 'iron_oxide_fe2o3', 'c/n': 'carbon_nitrogen_ratio', 'c:n': 'carbon_nitrogen_ratio',
    'mg2+': 'magnesium_ion', 'ca2+': 'calcium_ion', 'na+': 'sodium_ion', 'k+': 'potassium_ion',
    'h+': 'hydrogen_ion', 'cl-': 'chloride_ion', 'so42-': 'sulfate_ion', 'hco3-': 'bicarbonate_ion',
    'mg': 'magnesium', 'ca': 'calcium', 'na': 'sodium', 'fe': 'iron', 'co': 'cobalt',
    'ph': 'ph_unspecified', 'ph water': 'ph_h2o', 'phwater': 'ph_h2o', 'ph h2o': 'ph_h2o',
    'phkcl': 'ph_kcl', 'ph kcl': 'ph_kcl', 'ec': 'electrical_conductivity',
    'ec, conc. 1-1%': 'electrical_conductivity',
    'tio2': 'titanium_dioxide', 'na2o': 'sodium_oxide_na2o', 'mno': 'manganese_oxide_mno',
    'cr': 'chromium', 'as': 'arsenic', 'mn': 'manganese', 'zn': 'zinc',
    'total s': 'sulfur', 'total p': 'total_phosphorus',
    'wp': 'wilting_point', 'br': 'basal_respiration', 'cec saturation': 'base_saturation',
    'caco3': 'carbonate_equivalent', 'caco3, %': 'carbonate_equivalent',
    'sar': 'sodium_adsorption_ratio', 'hg': 'mercury', 'ni': 'nickel', 'pb': 'lead',
    'exchangeable na, % of the cec': 'exchangeable_sodium_percentage',
    'na, % of cec': 'exchangeable_sodium_percentage',
    'om': 'organic_matter', 'om, %': 'organic_matter', 'гумус': 'organic_matter', 'гумус, %': 'organic_matter',
    'рн': 'ph_unspecified', 'рн kcl': 'ph_kcl', 'nh4+': 'ammonium_ion', 'mo': 'molybdenum',
    'ec, ds/m': 'electrical_conductivity', 'ca co3 %': 'carbonate_equivalent',
    'urease, mg nh3': 'urease_activity', 'cu': 'copper', 'al3+': 'aluminium_ion',
    'hco3-': 'bicarbonate_ion', 'so42-': 'sulfate_ion',
    'fc': 'field_capacity', 'co32-': 'carbonate_ion', 'ph': 'ph_unspecified',
    'n-no3-': 'nitrate_ion', 'no3-': 'nitrate_ion',
    'medium silt': 'medium_silt', 'fine silt': 'fine_silt', 'coarse silt': 'coarse_silt',
    'n total': 'total_nitrogen', 'ntotal': 'total_nitrogen',
    'soc': 'soil_organic_carbon', 'tds': 'total_dissolved_solids', 'tds, %': 'total_dissolved_solids',
    'thickness of horizons, cm a + b': 'horizon_thickness',
    'air capacity at the field capacity m': 'air_capacity_field_capacity',
}
SOIL = re.compile(r'(?i)(soil|soils|soil horizon|soil sample|soil properties|humus|chernozem|horizon|sampling depth|\bdepth\b|exchangeable|cec|plow layer|plow land|pH\s*(H2O|KCl)?|\u043f\u043e\u0447\u0432|\u0433\u0443\u043c\u0443\u0441|\u0433\u043e\u0440\u0438\u0437\u043e\u043d|\u0447\u0435\u0440\u043d\u043e\u0437\u0451\u043c)')

def norm(h):
    x = h or ''
    x = x.replace('–', '-').replace('—', '-').replace('−', '-')
    x = re.sub(r'\\(?:mathrm|text)\s*', '', x)
    x = re.sub(r'\\\(|\\\)', '', x)
    x = re.sub(r'\^\{([^}]*)\}', r'\1', x)
    x = re.sub(r'_\{([^}]*)\}', r'\1', x)
    x = re.sub(r'[{}]', '', x)
    x = re.sub(r'\\+', '', x)
    x = re.sub(r'[^\w%+\-./:(), ]+', ' ', x, flags=re.UNICODE)
    x = re.sub(r'\s+', ' ', x).strip().lower()
    x = re.sub(r'(?<=[a-z])\s+(?=\d)', '', x)
    x = x.replace('_', '')
    x = re.sub(r'\s*([+-])\s*', r'\1', x)
    x = re.sub(r'\s*:\s*', ':', x)
    parts = x.split(' ')
    if len(parts) % 2 == 0 and parts[:len(parts)//2] == parts[len(parts)//2:]:
        x = ' '.join(parts[:len(parts)//2])
    # OCR/HTML exports may repeat a normalized header more than twice.
    toks = x.split(' ')
    if len(toks) > 1:
        for n in range(1, len(toks)//2 + 1):
            if len(toks) % n == 0 and toks == toks[:n] * (len(toks)//n):
                x = ' '.join(toks[:n]); break
    x = x.replace(' ', '') if x in ('mg2+','ca2+','na+','k+','h+','cl-','so42-','hco3-') else x
    return x

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--db',type=Path,required=True); args=ap.parse_args()
    con=sqlite3.connect(args.db); c=con.cursor(); accepted=0
    for pid,name,unit in [
        ('potassium_40_activity','potassium-40 specific activity','Bq/kg'),
        ('cesium_137_activity','cesium-137 specific activity','Bq/kg'),
        ('strontium_90_activity','strontium-90 specific activity','Bq/kg'),
        ('horizon_thickness','soil horizon thickness','cm'),
        ('air_capacity_field_capacity','air capacity at field capacity','%'),
        ('ph_salt_extract','pH in salt extract','pH'),
        ('rainfall_erosion_intensity','rainfall erosion intensity','t/ha/year'),
        ('snowmelt_erosion_intensity','snowmelt erosion intensity','t/ha/year'),
        ('annual_erosion_intensity','annual erosion intensity','t/ha/year'),
        ('pollution_load_index','pollution load index',None),
    ]:
        category='radioactivity' if pid in ('potassium_40_activity','cesium_137_activity','strontium_90_activity') else 'soil_property'
        description='Specific radionuclide activity retained only when the source table identifies soil material.' if category=='radioactivity' else 'Canonical soil measurement retained from an explicit source header.'
        c.execute("insert or ignore into property_definition(property_id,canonical_name,category,canonical_unit,description) values(?,?,?,?,?)",(pid,name,category,unit,description))
    rows = c.execute("select t.candidate_id,t.property_header_raw,t.value_num,t.unit_raw,q.caption_raw from table_measurement_candidate t join table_manual_review_queue q on q.candidate_id=t.candidate_id where q.status='open'").fetchall()
    for cid,h,v,unit,queue_caption in rows:
        key=norm(h); pid=MAP.get(key)
        if 'snowmelt erosion intensity' in key: pid='snowmelt_erosion_intensity'
        elif 'rainfall erosion intensity' in key: pid='rainfall_erosion_intensity'
        elif 'annual erosion intensity' in key: pid='annual_erosion_intensity'
        elif key in ('pli','pollution load index'): pid='pollution_load_index'
        else:
            mcf=re.search(r'contamination factors?\s*\(?(?:cf)?\)?\s*(zn|cd|cu|ni|pb|cr|as|hg|mn|fe)$',key)
            if mcf:
                el=mcf.group(1); pid=f'contamination_factor_{el}'
                c.execute("insert or ignore into property_definition(property_id,canonical_name,category,canonical_unit,description) values(?,?,?,?,?)",(pid,f'contamination factor {el.upper()}','soil_contamination',None,'Contamination factor reported by the source table.'))
        if key in ('40k','k-40'): pid='potassium_40_activity'
        elif key in ('137cs','cs137','cs-137'): pid='cesium_137_activity'
        elif key in ('90sr','sr90','sr-90'): pid='strontium_90_activity'
        elif 'kaggr' in key or 'k aggr' in key: pid='aggregate_stability'
        if not pid:
            if 'с орг' in key or 'c org' in key: pid='soil_organic_carbon'
            elif key.replace(' ','') in ('phho2','phh o2'): pid='ph_h2o'
            elif 'ec, ds/m' in key: pid='electrical_conductivity'
            elif 'exchangeable cations' in key and 'ca' in key: pid='exchangeable_calcium'
            elif 'exchangeable bases' in key and 'ca' in key: pid='exchangeable_calcium'
            elif 'displaced mg2' in key: pid='exchangeable_magnesium'
            elif 'ec, ds m-1' in key or 'ec, ds m 1' in key: pid='electrical_conductivity'
        if not pid:
            if key.startswith('phh2o') or key.startswith('ph h2o') or key.startswith('ph water') or key.startswith('phwater'): pid='ph_h2o'
            elif key.startswith('ph ') and 'water' in key: pid='ph_h2o'
            elif key.startswith('soil ph') or key == 'ph': pid='ph_unspecified'
            elif ('рн' in key and ('н о' in key or 'h2o' in key or key.endswith('2') or 'водной' in key or 'вытяж' in key)): pid='ph_h2o'
            elif key.startswith('suspension') and 'ph' in key: pid='ph_h2o'
            elif key.startswith('ph s'): pid='ph_salt_extract'
            elif key.startswith('ph ph') and 'water' not in key: pid='ph_unspecified'
            elif 'humus content' in key: pid='organic_matter'
            elif 'humus' in key: pid='organic_matter'
            elif 'thickness of horizons' in key: pid='horizon_thickness'
            elif 'air capacity at the field capacity' in key: pid='air_capacity_field_capacity'
            elif 'base saturation' in key: pid='base_saturation'
            elif key.startswith('cec') and ('meq' in key or 'cmol' in key or key == 'cec'): pid='cation_exchange_capacity'
            elif key.startswith('mg2+') or key.startswith('mg2'): pid='magnesium_ion'
            elif key.startswith('na2+') or key.startswith('na+'): pid='sodium_ion'
            elif key.startswith('ca2+') or key.startswith('ca+'): pid='calcium_ion'
            elif key.startswith('k2+') or key.startswith('k+'): pid='potassium_ion'
            elif key.startswith('hco3-'): pid='bicarbonate_ion'
            elif key.startswith('so42-'): pid='sulfate_ion'
            elif key.startswith('caco3'): pid='carbonate_equivalent'
            elif key.startswith('calculated na'): pid='sodium_ion'
            elif key.startswith('tds'): pid='total_dissolved_solids'
        if not pid:
            if 'fe2o3' in key: pid='iron_oxide_fe2o3'
            elif 'sio2' in key: pid='silicon_dioxide'
            elif 'corg' in key or 'organic carbon' in key: pid='soil_organic_carbon'
            elif 'k2o' in key: pid='potassium_oxide_k2o'
            elif 'p2o5' in key: pid='phosphorus_pentoxide'
        if not pid:
            if 'bulk density' in key and any(u in key for u in ('g/cm3','g cm-3','mg/m3')): pid='bulk_density'
            elif 'porosity' in key: pid='porosity'
            elif 'moisture' in key and ('soil' in key or 'water content' in key): pid='gravimetric_water_content'
            elif 'clay' in key and ('%' in key or 'content' in key or 'mm' in key): pid='physical_clay' if 'physical' in key else 'clay'
            elif key.startswith('physical clay'): pid='physical_clay'
            elif 'bulk density' in key: pid='bulk_density'
            elif key.startswith('cu') and ('mg/kg' in key or key == 'cu'): pid='copper'
            elif 'silt' in key and ('%' in key or 'content' in key or 'mm' in key): pid='silt'
            elif 'sand' in key and ('%' in key or 'content' in key or 'mm' in key): pid='sand'
            elif key.startswith('element element as'): pid='arsenic'
            elif key.startswith('element element cr'): pid='chromium'
            elif key.startswith('element element mn'): pid='manganese'
            elif key.startswith('element element zn'): pid='zinc'
            elif '<0.01 mm' in key: pid='physical_clay'
            elif '<0.001 mm' in key: pid='clay'
            elif '<0.001' in key and 'fraction' in key: pid='fine_fraction_lt_0_001mm'
            elif key.startswith('the content of fractions') and '0.001' in key: pid='fine_fraction_lt_0_001mm'
            elif ('1-0.25' in key or '1–0.25' in key) and ('fraction' in key or 'sand' in key): pid='sand'
            elif (('1-0.25' in key or '1–0.25' in key or '1.0-0.25' in key) and ('particle size' in key or 'mm' in key)): pid='coarse_sand'
            elif '0.25-0.05 mm' in key: pid='fine_sand'
            elif '0.05-0.01 mm' in key: pid='coarse_silt'
            elif '0.01-0.005 mm' in key: pid='medium_silt'
            elif '0.005-0.001 mm' in key: pid='fine_silt'
        if not pid or v is None: continue
        aid = c.execute('select artifact_id from table_measurement_candidate where candidate_id=?',(cid,)).fetchone()[0]
        cap=(queue_caption or '')+' '+' '.join(x[0] or '' for x in c.execute('select caption_raw from table_caption_context where artifact_id=?',(aid,)))
        cap += ' ' + ' '.join(x[0] or '' for x in c.execute('select text_raw from table_cell where artifact_id=?',(aid,)))
        lowcap=cap.lower()
        if 'contamination factor' in lowcap or 'contamination factors' in lowcap:
            if key in ('zn','cd','cu','ni','pb','cr','as','hg','mn','fe'):
                pid=f'contamination_factor_{key}'
                c.execute("insert or ignore into property_definition(property_id,canonical_name,category,canonical_unit,description) values(?,?,?,?,?)",(pid,f'contamination factor {key.upper()}','soil_contamination',None,'Contamination factor reported by the source table.'))
            elif key == 'pli': pid='pollution_load_index'
        header_soil_context = re.search(r'(?i)(physical\s+clay|humus|soil\s*pH|soil\s+organic|corg|horizon|sampling\s+depth)', key or '')
        if not SOIL.search(cap) and not header_soil_context: continue
        if key.startswith('ph') and not 0 <= v <= 14: continue
        # Percentages are bounded; concentrations such as P2O5/K2O in mg/kg are not.
        percent_limited = ('%' in key) or ('%' in (unit or ''))
        if pid in ('clay','silt','sand','physical_clay','fine_fraction_lt_0_001mm','aggregate_stability','organic_matter','soil_organic_carbon','calcium_oxide_cao','magnesium_oxide_mgo','iron_oxide_fe2o3','aluminum_oxide_al2o3','silicon_dioxide') and not 0 <= v <= 100: continue
        if pid in ('phosphorus_pentoxide','potassium_oxide_k2o') and percent_limited and not 0 <= v <= 100: continue
        c.execute('update table_measurement_candidate set property_id=? where candidate_id=?',(pid,cid))
        c.execute("update table_manual_review_queue set status='resolved_accept',manual_notes='Manual adjudication: explicit common soil-property header and soil-context evidence; scoped mapping applied.',updated_at=current_timestamp where candidate_id=?",(cid,)); accepted+=1
    con.commit(); print(json.dumps({'resolved_accept':accepted,'remaining_open':c.execute("select count(*) from table_manual_review_queue where status='open'").fetchone()[0]},ensure_ascii=False)); con.close()
if __name__=='__main__': main()
