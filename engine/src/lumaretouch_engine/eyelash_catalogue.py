"""Pinned original procedural lash definitions. No competitor assets."""
import hashlib,json
from pathlib import Path
CATALOGUE_SHA256='744d5c0b1aa5b26479ab692ae073daf93cbc96c4b54b549c3956b295eacd67f0'
def catalogue():
    raw=Path(__file__).with_name('eyelash_patterns.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=CATALOGUE_SHA256:raise ValueError('睫毛素材摘要不匹配')
    return json.loads(raw)['patterns']
def material(name):
    for item in catalogue():
        if item['id']==name:return item
    raise ValueError('未知睫毛素材')
