"""Pinned original measured-brow profiles, not copied commercial materials."""
import hashlib,json
from pathlib import Path
CATALOGUE_SHA256='4635e7bbf4d69249acb696310f986bb33d3d704cd3766556849b6bad38ce978a'
def catalogue():
    raw=Path(__file__).with_name('brow_makeup_patterns.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=CATALOGUE_SHA256:raise ValueError('眉妆素材摘要不匹配')
    return json.loads(raw)['patterns']
def material(name):
    for item in catalogue():
        if item['id']==name:return item
    raise ValueError('未知眉妆素材')
