#!/usr/bin/env python3
"""Normalize safe units while preserving raw candidate evidence."""
from __future__ import annotations
import argparse,json,sqlite3
from pathlib import Path

def norm_unit(raw: str | None) -> str | None:
    if not raw: return None
    v=raw.casefold().replace(' ','').replace('³','3').replace('мг','mg').replace('г','g').replace('кг','kg')
    v=v.replace('см','cm')
    return {'mg/kg':'mg/kg','g/kg':'g/kg','%':'%','ds/m':'dS/m','g/cm3':'g/cm3','cmol(c)/kg':'cmolc/kg','cmolc/kg':'cmolc/kg'}.get(v,raw)

def convert(value: float | None, raw: str | None, canonical: str | None, property_id: str | None):
    if value is None: return None,None,'missing_value','No numeric source value.'
    unit=norm_unit(raw)
    if not unit:return None,None,'missing_unit','Source candidate has no recognized unit.'
    if not canonical or unit==canonical:return value,unit,'exact',None
    # Dimensionally safe conversions. Percent -> g/kg is limited to SOC and
    # total-N/P/K style mass fractions; it remains visibly marked converted.
    if unit=='g/kg' and canonical=='mg/kg': return value*1000,'mg/kg','converted','Converted g/kg to mg/kg.'
    if unit=='mg/kg' and canonical=='g/kg': return value/1000,'g/kg','converted','Converted mg/kg to g/kg.'
    if unit=='%' and canonical=='g/kg' and property_id in {'soil_organic_carbon','total_nitrogen','total_phosphorus','total_potassium','inorganic_carbon'}:
        return value*10,'g/kg','converted','Converted mass percent to g/kg.'
    if unit=='g/kg' and canonical=='%' and property_id in {'organic_matter','carbonate_equivalent','base_saturation','porosity','sand','silt','clay','field_capacity','wilting_point','water_holding_capacity'}:
        return value/10,'%', 'converted','Converted g/kg to percent.'
    return None,None,'incompatible',f'Raw unit {unit!r} cannot be safely converted to canonical unit {canonical!r}.'

def main() -> None:
 p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True);a=p.parse_args();stats={}
 with sqlite3.connect(a.db) as c:
  rows=c.execute('SELECT mc.candidate_id,mc.value_num,mc.unit_raw,mc.property_id,pd.canonical_unit FROM measurement_candidate mc LEFT JOIN property_definition pd ON pd.property_id=mc.property_id').fetchall()
  for cid,value,raw,pid,canonical in rows:
   out,unit,status,warning=convert(value,raw,canonical,pid);stats[status]=stats.get(status,0)+1
   c.execute('INSERT INTO measurement_candidate_normalization(candidate_id,value_normalized,unit_normalized,normalization_status,warning,normalizer_version) VALUES(?,?,?,?,?,?) ON CONFLICT(candidate_id) DO UPDATE SET value_normalized=excluded.value_normalized,unit_normalized=excluded.unit_normalized,normalization_status=excluded.normalization_status,warning=excluded.warning,normalizer_version=excluded.normalizer_version,normalized_at=CURRENT_TIMESTAMP',(cid,out,unit,status,warning,'v1'))
  c.commit()
 print(json.dumps({'candidates':len(rows),'by_status':stats},ensure_ascii=False))
if __name__=='__main__':main()
