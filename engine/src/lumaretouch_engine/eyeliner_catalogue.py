"""Pinned original observed-eyelid curves, not copied commercial materials."""
import hashlib,json
from pathlib import Path
CATALOGUE_SHA256='7e92c1c83d664ea1120cb94a62cd5ef2aa952d9df6bbc034f7dafa935309d21f'
def catalogue():
    raw=Path(__file__).with_name('eyeliner_patterns.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=CATALOGUE_SHA256:raise ValueError('眼线素材摘要不匹配')
    return json.loads(raw)['patterns']
def material(name):
    for item in catalogue():
        if item['id']==name:return item
    raise ValueError('未知眼线素材')
