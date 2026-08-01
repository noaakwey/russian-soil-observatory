#!/usr/bin/env python3
"""Ingest full article text and produce reviewable property/location candidates."""
from __future__ import annotations
import argparse, json, re, sqlite3
from pathlib import Path

# Canonical properties cover chemistry, nutrients, organic matter, texture,
# hydrophysics, salinity, biology and contaminants. New raw names are retained.
PROPS = {
 "ph_h2o": ("acid_base", "pH", r"\bpH(?:\s*(?:H2O|водн(?:ый|ой)))?\b"),
 "electrical_conductivity": ("salinity", "dS/m", r"(?:electrical conductivity|электропроводност)"),
 "soil_organic_carbon": ("organic", "g/kg", r"(?:soil organic carbon|organic carbon|органическ[а-я ]{0,16}углерод|Сорг)"),
 "organic_matter": ("organic", "%", r"(?:organic matter|гумус)"),
 "total_nitrogen": ("macronutrient", "g/kg", r"(?:total nitrogen|общ(?:ий|его) азот|Nобщ)"),
 "nitrate_n": ("macronutrient", "mg/kg", r"(?:nitrate|нитрат)"),
 "ammonium_n": ("macronutrient", "mg/kg", r"(?:ammonium|аммоний)"),
 "available_phosphorus": ("macronutrient", "mg/kg", r"(?:available phosphorus|подвижн[а-я ]{0,14}фосфор|P2O5)"),
 "available_potassium": ("macronutrient", "mg/kg", r"(?:available potassium|подвижн[а-я ]{0,14}калий|K2O)"),
 "calcium": ("exchange", "cmolc/kg", r"(?:\bCa\b|кальци)"),
 "magnesium": ("exchange", "cmolc/kg", r"(?:\bMg\b|магни)"),
 "cation_exchange_capacity": ("exchange", "cmolc/kg", r"(?:cation exchange capacity|\bCEC\b|ёмкост[ьи] катионного обмена)"),
 "sand": ("particle_size", "%", r"(?:\bsand\b|пес(?:ок|чан))"),
 "silt": ("particle_size", "%", r"(?:\bsilt\b|пылеват)"),
 "clay": ("particle_size", "%", r"(?:\bclay\b|глинист)"),
 "bulk_density": ("physical", "g/cm3", r"(?:bulk density|плотност[ьи] сложения)"),
 "porosity": ("physical", "%", r"(?:porosity|пористост)"),
 "water_holding_capacity": ("hydrophysical", "%", r"(?:water holding capacity|влагоёмкост)"),
 "aggregate_stability": ("physical", "%", r"(?:aggregate stability|агрегатн[а-я ]{0,12}устойчивост)"),
 "microbial_biomass_carbon": ("biological", "mg/kg", r"(?:microbial biomass carbon|микробн[а-я ]{0,16}биомасс[а-я ]{0,8}углерод)"),
 "zinc": ("microelement", "mg/kg", r"(?:\bZn\b|цинк)"), "copper": ("microelement", "mg/kg", r"(?:\bCu\b|мед[ьи])"),
 "lead": ("contaminant", "mg/kg", r"(?:\bPb\b|свинец)"), "cadmium": ("contaminant", "mg/kg", r"(?:\bCd\b|кадми)"),
 "arsenic": ("contaminant", "mg/kg", r"(?:\bAs\b|мышьяк)"), "mercury": ("contaminant", "mg/kg", r"(?:\bHg\b|ртут)"),
}
VALUE = re.compile(r"(?<!\w)(-?\d+(?:[.,]\d+)?)\s*(mg\s*/\s*kg|мг\s*/\s*кг|g\s*/\s*kg|г\s*/\s*кг|%|cmol\(?c?\)\s*/\s*kg|dS\s*/\s*m|г\s*/\s*см[³3])", re.I)
DEPTH = re.compile(r"(\d+(?:[.,]\d+)?)\s*[–-]\s*(\d+(?:[.,]\d+)?)\s*(?:cm|см)", re.I)
# Do not accept arbitrary neighbouring decimals from a numerical table as a
# coordinate.  Operational locations require explicit cardinal directions for
# both latitude and longitude; unmarked numeric pairs stay raw OCR evidence.
COORD = re.compile(r"(\d{1,2}[.,]\d{2,7})\s*°?\s*[NSСЮ]\s*[,; ]+\s*(\d{2,3}[.,]\d{2,7})\s*°?\s*[EWВЗ]", re.I)
SAMPLE = re.compile(r"(?:разрез|профил[ьяе]|скважин[аы]?|точк[аи]?|образец)\s*(?:№|N)?\s*([A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9_-]{0,20})", re.I)
# A bare capital O in e.g. ``H 2 O`` is not a soil horizon.  For automatic
# prose extraction we require the explicit word; tables retain their own,
# separately auditable horizon parser.
HORIZON = re.compile(r"(?:горизонт|horizon)\s*([AEOBC][A-Za-z0-9+/.:-]{0,12})\b", re.I)
METHOD = re.compile(r"(?:метод(?:ом|ика)?|определял[а-я]+|измерял[а-я]+)[^.]{0,120}", re.I)

def ctx(text, a, b): return text[max(0,a-180):min(len(text),b+220)].replace('\n',' ')
def num(x): return float(x.replace(',','.'))

def value_near_property(text, match):
 """Return a value in the same short prose fragment, never a nearby table cell."""
 tail=text[match.end():match.end()+90]
 # A line break or sentence boundary normally separates a heading from a
 # table/value in pdftotext output.  Crossing it caused pH -> unrelated %.
 stop=re.search(r'[\n.!?]',tail)
 if stop: tail=tail[:stop.start()]
 return VALUE.search(tail)

def main():
 p=argparse.ArgumentParser(); p.add_argument('--source-root',type=Path,required=True); p.add_argument('--db',type=Path,required=True); p.add_argument('--commit-every',type=int,default=25); p.add_argument('--skip-locations',action='store_true'); a=p.parse_args()
 stats={'texts':0,'property_candidates':0,'coordinate_candidates':0}
 with sqlite3.connect(a.db) as c:
  c.execute('PRAGMA foreign_keys=ON')
  for pid,(cat,unit,_) in PROPS.items(): c.execute("INSERT INTO property_definition(property_id,canonical_name,category,canonical_unit,description) VALUES(?,?,?,?,NULL) ON CONFLICT(property_id) DO NOTHING",(pid,pid.replace('_',' '),cat,unit))
  for file_no, f in enumerate(sorted((a.source_root/'all_articles_text').glob('*.txt')), start=1):
   doc=f'pochvovedenie:{f.stem}'; aid=f'{doc}:text'; eid=f'{aid}:raw'; text=f.read_text(encoding='utf-8',errors='replace')
   if not c.execute('SELECT 1 FROM document WHERE document_id=?',(doc,)).fetchone(): continue
   c.execute("INSERT INTO source_artifact(artifact_id,document_id,artifact_type,source_path) VALUES(?,?,'text',?) ON CONFLICT(artifact_id) DO NOTHING",(aid,doc,str(f)))
   c.execute("INSERT INTO extraction(extraction_id,artifact_id,extractor,extractor_version,raw_text,parsed_json,status) VALUES(?,?, 'regex-candidate','v1',?,?,'parsed') ON CONFLICT(extraction_id) DO UPDATE SET raw_text=excluded.raw_text",(eid,aid,text,'{}'))
   i=0
   for prop,(_,_,pat) in PROPS.items():
    for m in re.finditer(pat,text,re.I):
     w=ctx(text,m.start(),m.end()); v=value_near_property(text,m)
     if not v: continue
     d=DEPTH.search(w); sample=SAMPLE.search(w); horizon=HORIZON.search(w); method=METHOD.search(w); cid=f'{eid}:m:{i}'; i+=1
     c.execute("INSERT OR REPLACE INTO measurement_candidate VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(cid,eid,prop,m.group(0),num(v.group(1)),None,v.group(2),method.group(0) if method else None,horizon.group(1) if horizon else None,num(d.group(1)) if d else None,num(d.group(2)) if d else None,sample.group(1) if sample else None,w,'unreviewed'))
     stats['property_candidates']+=1
   if not a.skip_locations:
    for j,m in enumerate(COORD.finditer(text)):
     lat,lon=num(m.group(1)),num(m.group(2))
     # The journal name is not proof that a point is in Russia: articles also
     # report foreign study areas.  Country assignment is done later against a
     # versioned boundary dataset by country_triage.py.
     if lat<=90 and lon<=180: c.execute("INSERT OR REPLACE INTO location_candidate VALUES(?,?,?,?,?,?,?,?,?)",(f'{eid}:l:{j}',eid,lat,lon,None,None,'decimal_degrees',ctx(text,m.start(),m.end()),'unreviewed')); stats['coordinate_candidates']+=1
   stats['texts']+=1
   if file_no % a.commit_every == 0:
    c.commit()
  c.commit()
 print(json.dumps(stats,ensure_ascii=False))
if __name__=='__main__': main()
