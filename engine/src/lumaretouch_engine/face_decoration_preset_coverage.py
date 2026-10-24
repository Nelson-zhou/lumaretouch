# SPDX-License-Identifier: GPL-3.0-or-later
"""Target-local decoration dependencies for complete mixed-preset images."""
from copy import deepcopy
from hashlib import sha256
import json
from . import face_decoration_state as D, people_state as P
from .face_decoration_scope import resolved_recipe


def digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def checked(value, asset):
    if (type(value) is not dict or set(value) != {'version','support_transfer','targets'}
            or type(value['version']) is not int or value['version'] != 1 or value['support_transfer'] != 'none'
            or type(value['targets']) is not list or not 1 <= len(value['targets']) <= 64):
        raise ValueError('Invalid decoration target coverage')
    keys=[]
    for item in value['targets']:
        if type(item) is not dict or set(item) != {'face_ref','scope','visibility_sha256','recipe_sha256'}:
            raise ValueError('Decoration coverage cannot transport support or source data')
        ref=P.check_ref(item['face_ref']); P.digest(item['recipe_sha256'])
        if ref['asset_sha256'] != asset: raise ValueError('Decoration coverage belongs to another source')
        keys.append(ref['face_instance_id'])
        if item['scope']=='target-reviewed-visible-skin': P.digest(item['visibility_sha256'])
        elif item['scope']!='neutral-no-effect' or item['visibility_sha256'] is not None:
            raise ValueError('Invalid decoration visibility scope')
    if keys != sorted(set(keys)): raise ValueError('Decoration target coverage must be unique and ordered')
    return deepcopy(value)


def coverage(engine, row, graph, ref, before=None):
    from .face_decoration_host import support_status
    from .creative_derived_source import row_proof
    ref=P.check_ref(ref); before=graph if before is None else before
    proof=row_proof({**row,'state':engine._people_preset_capture()})
    if proof['asset_sha256'] != ref['asset_sha256']: raise ValueError('Decoration review source changed')
    targets=[]
    for key in sorted(set(graph['faces'])|set(before['faces'])):
        face=graph['faces'].get(key); old=before['faces'].get(key)
        def recipe(g,f):
            return resolved_recipe(g,key) if f and f['enabled'] and f['asset_sha256']==ref['asset_sha256'] else D.neutral()
        current=recipe(graph,face); prior=recipe(before,old)
        active=D.active(current) or D.active(prior)
        if key != ref['face_instance_id'] and not active: continue
        if face is None or not face['enabled'] or (old is not None and P.face_ref(old)!=P.face_ref(face)):
            raise ValueError('Decoration review cannot remove, disable or remap retained anatomy')
        target=P.face_ref(face); visibility=None
        if active:
            source={'sha256':target['asset_sha256'],'width':face['evidence']['source_width'],'height':face['evidence']['source_height']}
            ok,reason,visibility=support_status(engine,graph,source,target)
            if not ok: raise ValueError(reason)
            if D.active(prior):
                ok,reason,old_visibility=support_status(engine,before,source,target)
                if not ok or old_visibility!=visibility: raise ValueError(reason or 'Decoration support changed across scalar-only review')
        targets.append({'face_ref':target,'scope':'target-reviewed-visible-skin' if active else 'neutral-no-effect',
                        'visibility_sha256':visibility,'recipe_sha256':digest(current)})
    return checked({'version':1,'support_transfer':'none','targets':targets},ref['asset_sha256'])
