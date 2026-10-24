# SPDX-License-Identifier: GPL-3.0-or-later
"""Original decoration-only scalar alias history on the established ledger."""
from . import eye_bag_batch_history as COMMON, face_decoration_state as D
from . import face_style_alias_review as CLOSURE
KEY='face_decoration_alias_review'


def _entry(entry): return {**entry,COMMON.KEY:entry[KEY]}

def scalar_changes(before,candidate,refs):
    from .people_graph_patch import between
    from . import people_state as S
    changes=between(before,candidate);ids={S.check_ref(ref)['face_instance_id'] for ref in refs}
    if not 1<=len(changes)<=2 or before['association_revision']!=candidate['association_revision']:
        raise ValueError('Decoration alias authority requires a nonempty decoration-only scalar transition')
    selected=set()
    for change in changes:
        key=change['key']
        if change['collection']!='overrides' or type(key) is not list or len(key)!=4 or key[0]!='face' or key[1] not in ids or key[2]!=D.OP or key[3] not in ('/pattern','/strength'):
            raise ValueError('Decoration alias authority cannot modify support, identity, association or another effect')
        selected.add(key[1])
        for record in (change['before'],change['after']):
            if record is None:continue
            if [record[n] for n in ('scope','target_id','operation_id','parameter_path')]!=key:raise ValueError('Decoration alias scalar identity changed')
            probe=D.neutral();probe[key[3][1:]]=record['value'];D.check(probe)
    if len(selected)!=1:raise ValueError('Decoration alias authority requires one exact edited face')
    return changes



def check(entry):
    if KEY not in entry:return None
    marker=COMMON.check(_entry(entry))
    if not 2<=len(marker['targets'])<=16 or {r['people_scope'] for r in marker['targets']}!={'project'}:
        raise ValueError('Decoration alias history requires two to sixteen exact shared-owner documents')
    assets={r['source_proof']['asset_sha256'] for r in marker['targets']}
    if len(assets)!=1 or len(entry['people_scoped_changes'])!=1:
        raise ValueError('Decoration aliases cannot span independent owners or effective sources')
    keys=[]
    for change in entry['people_scoped_changes'][0]['changes']:
        key=change['key'];keys.append(key[1])
        if key[2]!=D.OP or key[3] not in ('/pattern','/strength'):
            raise ValueError('Decoration alias history cannot authorize other effects or visibility assets')
        for record in (change['before'],change['after']):
            if record is not None:
                probe=D.neutral();probe[key[3][1:]]=record['value'];D.check(probe)
    if len(set(keys))!=1:raise ValueError('One direct decoration alias edit must retain its exact selected face')
    return marker


def prepare(engine,plans,targets,ack):
    marker=COMMON.prepare(engine,plans,targets,ack)
    from .people_graph_patch import between
    entry={'ops':['lnx.people_graph.v1'],'people_changes':[],'policy':'protected_scoped_graph','targets':targets,
        'people_scoped_changes':[{'scope':scope,'document_id':p['row']['document_id'],'changes':between(p['before'],p['candidate'])} for scope,p in plans.items()],KEY:marker}
    return check(entry)


def verify_restore(engine,entry,plans,targets):
    marker=check(entry)
    if marker is None:return
    COMMON.verify_restore(engine,_entry(entry),plans,targets)
    if set(plans)!={'project'}:raise ValueError('Decoration alias restore changed graph owner')
    plan=plans['project'];asset=marker['targets'][0]['source_proof']['asset_sha256']
    current=engine._people_preset_capture()
    CLOSURE.verify_dormant(engine,plan['row'],{asset})
    members=CLOSURE._eligible(engine,plan['row'],current,asset)
    if {item[3].document_id for item in members}!={t['document_id'] for t in targets.values()}:
        raise ValueError('Decoration alias restore must include every current affected document')
    from .face_decoration_alias_authority import mint
    refs=next(iter(targets.values()))['reviewed_face_refs']
    plan['decoration_alias_authority']=mint(engine,plan['row'],plan['before'],plan['candidate'],targets,refs)


def status_summary(entry):
    marker=check(entry)
    return None if marker is None else {'version':1,'review_sha256':marker['review_sha256'],'member_count':len(marker['targets'])}
