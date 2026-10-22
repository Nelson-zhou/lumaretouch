"""Upgrade isolated v1/null defaults only with an unambiguous captured asset."""
from copy import deepcopy
from . import people_state as S


def upgrade(value,*,captured_asset_sha256=None):
    if type(value) is not dict:raise ValueError('People graph must be an object')
    if value.get('version')==S.VERSION:return S.check(value)
    if type(value.get('version')) is not int or value['version']!=1:raise ValueError('Unsupported people schema')
    out=deepcopy(value)
    assets={f['asset_sha256'] for f in out.get('faces',{}).values()}
    if captured_asset_sha256 is not None:S.digest(captured_asset_sha256)
    nulls=[x for x in out.get('overrides',[]) if x.get('scope')=='all_people' and x.get('target_id') is None]
    if nulls:
        if captured_asset_sha256 is None or assets-{captured_asset_sha256}:
            # Preserve the original graph outside this function. A rejection is
            # preferable to turning unknown old defaults into project-wide edits.
            raise ValueError('Legacy null all-people defaults need an unambiguous captured document asset; retain unresolved original intent')
        for entry in nulls:entry['target_id']=captured_asset_sha256
    out['version']=S.VERSION
    return S.check(out)
