# SPDX-License-Identifier: GPL-3.0-or-later
"""Complete same-owner/source face-style review on the existing batch ledger.

No owner migration, copied geometry, alternate graph or document undo history.
Each alias owns its full-source image pair and complete snapshot fingerprints;
only the one established graph is staged and published. Runtime acceptance UNRUN.
"""
from copy import deepcopy
from types import SimpleNamespace
import re
import time
import uuid

from . import creative_derived_source as SOURCE, virtual_copy_people as V, people_state as S
from . import people_batch_ledger as LEDGER
from .portrait_review_render import image as render_image, snapshot_key

MAX_MEMBERS = 16
MAX_REVISION = 9007199254740991
MAX_DORMANT_FRAMES = 10000


def _revision(value):
    return (type(value) is str and re.fullmatch('(0|[1-9][0-9]{0,15})',value) is not None
            and int(value)<=MAX_REVISION)


def check_ack(ack):
    from .face_style_review import _hash
    if (type(ack) is not dict or set(ack)!={'review_sha256','members'}
            or not _hash(ack['review_sha256']) or type(ack['members']) is not list
            or not 2<=len(ack['members'])<=MAX_MEMBERS):
        raise ValueError('Face-style aliases require every loaded image pair')
    seen=set()
    for member in ack['members']:
        if (type(member) is not dict or set(member)!={'document_id','revision','before_sha256','after_sha256'}
                or not _revision(member['revision']) or not _hash(member['before_sha256'])
                or not _hash(member['after_sha256'])):
            raise ValueError('Invalid face-style alias image acknowledgement')
        identity=S.token(member['document_id'])
        if identity in seen:raise ValueError('Face-style alias acknowledgement repeats a document')
        seen.add(identity)


def _current_state(engine,row,current=None):
    if row is V.current_row(engine):
        return engine._people_preset_capture() if current is None else current
    return row.get('state')


def _source_row(engine,row,current=None):
    return {**row,'state':_current_state(engine,row,current)}


def _scope_rows(engine,row):
    return V.scope_rows(engine) if row is V.current_row(engine) else V.scope_rows(engine,row)


def _pending(engine,row):
    from .virtual_copy_storage import _full_hash
    if V.scope(row)!=V.PROJECT:return
    for other in engine._docs:
        if other.get('_people_new_import') and not V.is_private(other):
            known=other.get('_people_source_sha256') or _full_hash(other.get('fingerprint'))
            if known is None:
                raise ValueError('An unclassified pending import has unknown source provenance; open or resolve it before shared review')
            S.digest(known)


def _frame_asset(frame,original):
    """Headers only: encoded versions are refusal evidence, never pixel proof."""
    if type(frame) is not dict:raise ValueError('Unreviewable retained document history frame')
    base=frame.get('_creative_base')
    if base is None:asset=original
    else:
        if (type(base) is not dict or type(base.get('id')) is not str
                or re.fullmatch('sha256:[0-9a-f]{64}',base['id']) is None
                or base.get('kind')!='rgba'
                or any(type(base.get(key)) is not int or base[key]<1 for key in ('width','height'))):
            raise ValueError('Unreviewable dormant creative-source header')
        asset=base['id'][7:]
    S.digest(asset)
    history=frame.get('_people_history')
    if history is not None and (type(history) is not dict or history.get('asset_sha256')!=asset):
        raise ValueError('Dormant portrait history disagrees with its effective source')
    return asset


def _unloaded_frames(engine,row,stored,histories,assets,budget):
    """Saved shared originals remain participants even when not in live rows.

    Validated stored headers may exclude an unrelated dormant source. They can
    never admit an unavailable affected document or substitute for its images.
    """
    from .virtual_copy_storage import _full_hash
    if not stored or V.scope(row)!=V.PROJECT:return
    live={item.get('document_id') for item in engine._docs}
    project=getattr(engine,'_project',None) or {}
    for identity,saved in stored.items():
        if identity in live or V.is_private(saved):continue
        S.token(identity)
        original=_full_hash(saved.get('fingerprint'))
        source=(project.get('source_assets') or {}).get(saved.get('source_asset_id'))
        registered=_full_hash((source or {}).get('fingerprint'))
        if registered is not None and original is not None and registered!=original:
            raise ValueError('Unavailable shared document has conflicting original-source provenance')
        original=registered if registered is not None else original
        S.digest(original)
        def inspect(frame):
            budget[0]+=1
            if budget[0]>MAX_DORMANT_FRAMES:
                raise ValueError('Unavailable shared-source history exceeds its complete review bound')
            if _frame_asset(frame,original) in assets:
                raise ValueError('An unavailable shared document retains this source; restore and review every affected alias')
        versions=saved.get('versions');active=saved.get('active_version')
        if type(versions) is not list or active is None:
            raise ValueError('Unavailable shared document has unknown effective-source provenance')
        active_matches=[version for version in versions if type(version) is dict and version.get('id')==active]
        if len(active_matches)!=1:
            raise ValueError('Unavailable shared document has an ambiguous active source version')
        for version in versions:
            if type(version) is not dict:raise ValueError('Invalid unavailable document version')
            recipe=version.get('recipe')
            inspect({} if recipe is None else recipe)
        stacks=[]
        if 'document_history' in saved:stacks.append(saved['document_history'])
        retained=histories.get('document:'+identity)
        if retained is not None:
            if (type(retained) is not dict or retained.get('document_id')!=identity
                    or retained.get('asset_sha256')!=original):
                raise ValueError('Unavailable portrait history changed its exact document/source identity')
            stacks.append(retained.get('stacks'))
        for history in stacks:
            if type(history) is not dict or set(history)!={'undo','redo'}:
                raise ValueError('Invalid unavailable document history stacks')
            for stack in history.values():
                if type(stack) is not list or len(stack)>64:
                    raise ValueError('Unavailable history exceeds its retained frame bound')
                for frame in stack:inspect(frame)


def verify_dormant(engine,row,assets):
    """Refuse source-switchable siblings, including their retained named versions.

    Runtime owned stacks supersede saved stacks, including an explicit clear.
    Only baseline-bearing frames are inspected: repair redo operations cannot
    switch a source, and unrelated nested bindings are not alias membership.
    """
    assets={S.digest(asset) for asset in assets}
    project=getattr(engine,'_project',None) or {}
    stored={}
    for item in project.get('docs',[]):
        if type(item) is not dict:raise ValueError('Invalid saved document during alias review')
        identity=item.get('document_id')
        S.token(identity)
        if identity in stored:raise ValueError('Ambiguous saved document identity during alias review')
        stored[identity]=item
    histories=project.get('people_document_history',{})
    if type(histories) is not dict:raise ValueError('Invalid retained portrait history')
    budget=[0]
    _unloaded_frames(engine,row,stored,histories,assets,budget)
    for other in _scope_rows(engine,row):
        source=SOURCE.row_proof(_source_row(engine,other))
        if source['asset_sha256'] in assets:continue
        def inspect(frame):
            budget[0]+=1
            if budget[0]>MAX_DORMANT_FRAMES:raise ValueError('Complete dormant-source review exceeds its retained frame budget; no frames were omitted')
            if _frame_asset(frame,source['original_sha256']) in assets:
                raise ValueError('An unreviewed dormant sibling retains this source in history or a named version')
        def stacks(value):
            if type(value) is not dict or set(value)!={'undo','redo'}:
                raise ValueError('Invalid dormant document history stacks')
            for stack in value.values():
                if type(stack) is not list or len(stack)>64:
                    raise ValueError('Dormant document history exceeds its complete review bound')
                for frame in stack:inspect(frame)
        is_current=other is V.current_row(engine)
        stacks({key:getattr(engine,'_'+key,other.get(key,[])) if is_current else other.get(key,[])
                for key in ('undo','redo')})
        saved=stored.get(other.get('document_id'))
        if saved is not None:
            versions=saved.get('versions',[])
            if type(versions) is not list:raise ValueError('Invalid retained document versions')
            for version in versions:
                if type(version) is not dict:raise ValueError('Invalid retained document version')
                recipe=version.get('recipe')
                inspect({} if recipe is None else recipe)
        if is_current or other.get('_history_owned'):continue
        if saved is not None and 'document_history' in saved:stacks(saved['document_history'])
        retained=histories.get('document:'+other['document_id'])
        if retained is not None:
            if (type(retained) is not dict or retained.get('document_id')!=other['document_id']
                    or retained.get('asset_sha256')!=source['original_sha256']):
                raise ValueError('Saved dormant portrait history changed document/source identity')
            stacks(retained.get('stacks'))


def has_aliases(engine,live):
    _,row,current,source,_=live
    # This narrow refusal also protects the original single-document path from
    # changing a currently dormant sibling's future effective-source recipe.
    verify_dormant(engine,row,{source['asset_sha256']})
    aliases=[other for other in _scope_rows(engine,row)
             if SOURCE.row_asset(_source_row(engine,other,current))==source['asset_sha256']]
    return len(aliases)>1


def _plans(entry):
    return {entry['scope']:{'row':entry['row'],'before':entry['before'],
        'candidate':entry['candidate'],'reviewed_face_refs':[deepcopy(entry['target']['face_ref'])]}}


def _targets(engine,batch,plans,current):
    """Run the actual ledger enumerator without remembering a read-only preview.

    Only current state is overlaid. Version checks delegate to each retained row,
    not its shallow view, so no replacement identity or private owner is created.
    """
    active=V.current_row(engine);rows=list(batch.documents.rows())
    views=[{**row,'state':current} if row is active else row for row in rows]
    original={id(view):row for view,row in zip(views,rows)}
    versions=SimpleNamespace(check_advance=lambda view:batch.versions.check_advance(original[id(view)]))
    view=SimpleNamespace(documents=SimpleNamespace(rows=lambda:views),versions=versions)
    return LEDGER._targets(view,engine,plans)


def _eligible(engine,row,current,asset,*,advance=True):
    from .people_preset_plan import require_active_owner
    _pending(engine,row)
    project=engine.__dict__.get('_people_project_context')
    if (V.scope(row)!=V.PROJECT or type(project) is not dict
            or project.get('owner') is not require_active_owner(engine)):
        raise ValueError('Face-style aliases require the exact existing shared portrait owner')
    members=[];seen=set()
    for other in _scope_rows(engine,row):
        source=SOURCE.row_proof(_source_row(engine,other,current))
        if source['asset_sha256']!=asset:continue
        path=other.get('path');state=_current_state(engine,other,current)
        if (other.get('trashed') or other.get('_people_new_import') or type(state) is not dict
                or type(path) is not str or not 1<=len(path.encode('utf-8'))<=4096 or '\0' in path):
            raise ValueError('Every affected alias must have an available, non-trashed complete document recipe')
        versions=engine._document_versions()
        version=versions.check_advance(other) if advance else versions.version(other)
        if (version.revision>MAX_REVISION-int(advance) or version.document_id in seen
                or version.document_id!=other.get('document_id')):
            raise ValueError('Face-style alias document identities or mutation revisions are invalid')
        S.token(version.document_id);seen.add(version.document_id)
        members.append((other,state,source,version))
    if not 2<=len(members)<=MAX_MEMBERS:
        raise ValueError('Review requires the complete set of two to sixteen affected face-style aliases; no document was omitted')
    members.sort(key=lambda item:item[0] is not row)
    if members[0][0] is not row:raise ValueError('Current photograph is missing from its complete alias review')
    return members


def _plan(review):
    return SimpleNamespace(token=review['token'],records={member['visual']['document_id']:member['visual'] for member in review['members']})


def _ack(review):
    return {'review_sha256':review['review_sha256'],'members':[
        {'document_id':v['document_id'],'revision':v['revision'],
         'before_sha256':v['before']['sha256'],'after_sha256':v['after']['sha256']}
        for v in (member['visual'] for member in review['members'])]}


def _proof(review):
    return {'kind':'face_style_confirm','token':review['token'],'review_sha256':review['review_sha256'],
        'ack':_ack(review),'recipe':deepcopy(review['recipe']),'patches_sha256':review['patches_sha256'],
        'alias_members':[{'document_id':member['visual']['document_id'],
            'expected_revision':member['visual']['revision'],
            'result_revision':str(int(member['visual']['revision'])+1)} for member in review['members']]}


def _available(store,review):
    plan=_plan(review)
    for visual in plan.records.values():
        for side in ('before','after'):
            store['images'].read(plan,visual['document_id'],visual['revision'],side,visual[side]['sha256'])


def _verify(engine,state,target,entry):
    from . import face_style_review as REVIEW
    owner,row,current,source,version=REVIEW._live(engine,state,target,strict=False)
    review=entry['review'];batch=engine._batch_controller()
    if (entry['claimed'] or owner is not entry['owner'] or owner.fence!=entry['fence']
            or row is not entry['row'] or engine._load_id!=entry['load_id']
            or target!=entry['target'] or state!=entry['before'] or V.scope(row)!=entry['scope']
            or batch is not entry['batch'] or engine._document_versions().workspace!=entry['workspace']
            or source!=review['owner']['source_proof'] or entry['candidate']['revision']>MAX_REVISION):
        raise ValueError('Face-style alias owner, source, target or complete graph changed; preview again')
    verify_dormant(engine,row,{target['face_ref']['asset_sha256']})
    members=_eligible(engine,row,current,target['face_ref']['asset_sha256'])
    if len(members)!=len(entry['members']):raise ValueError('Face-style alias membership changed; review every affected document')
    for actual,frozen in zip(members,entry['members']):
        other,recipe,proof,other_version=actual;visual=frozen['visual']
        if (other is not frozen['row'] or other['path']!=frozen['path']
                or other_version.document_id!=visual['document_id'] or str(other_version.revision)!=visual['revision']
                or proof!=visual['source_proof']
                or snapshot_key(engine,other,recipe,state)!=frozen['before_key']
                or snapshot_key(engine,other,recipe,entry['candidate'])!=frozen['after_key']):
            raise ValueError('Face-style alias source, crop, repair, support or complete snapshot changed; preview again')
        SOURCE.verify_row({**other,'state':recipe},proof)
    if _targets(engine,batch,_plans(entry),current)!=entry['targets']:
        raise ValueError('Face-style ledger closure changed or contains an unreviewed alias')
    return current


def preview(engine,state,target,payload,live):
    from . import face_style_review as REVIEW
    from .people_transfer_inventory import proof
    from .people_graph_patch import between
    from .people_graph_owner import affected_assets
    owner,row,current,source,version=live;fence=owner.fence
    patches,candidate=REVIEW._stage(engine,state,target,payload,row,current,source,version)
    if candidate['revision']>MAX_REVISION:
        raise ValueError('Face-style alias graph revision has no exact transport headroom; no review was claimed')
    if not between(state,candidate):raise ValueError('Face-style alias recipe has no canonical change; no review was claimed')
    if affected_assets(state,candidate)!={source['asset_sha256']}:
        raise ValueError('Face-style alias composition changed another source or association')
    members=_eligible(engine,row,current,source['asset_sha256']);batch=engine._batch_controller()
    entry={'owner':owner,'row':row,'scope':V.scope(row),'load_id':engine._load_id,'fence':fence,
        'workspace':engine._document_versions().workspace,'batch':batch,'target':deepcopy(target),
        'before':deepcopy(state),'candidate':candidate,'members':[],'claimed':False}
    targets=_targets(engine,batch,_plans(entry),current)
    if ({item['document_id'] for item in targets.values()}!={item[3].document_id for item in members}
            or len(targets)!=len(members)):
        raise ValueError('Face-style ledger includes an unreviewed affected alias')
    entry['targets']=deepcopy(targets);public=[];displays={}
    for other,recipe,source_proof,member_version in members:
        before_key=snapshot_key(engine,other,recipe,state);after_key=snapshot_key(engine,other,recipe,candidate)
        a,left,proof_a=render_image(engine,other,recipe,state,member_version.document_id,member_version.revision)
        b,right,proof_b=render_image(engine,other,recipe,candidate,member_version.document_id,member_version.revision)
        if (proof_a['source_proof']!=source_proof or proof_b['source_proof']!=source_proof
                or proof_a['source_size']!=proof_b['source_size']):
            raise ValueError('Face-style alias image pair changed effective source or provenance')
        visual={'version':1,'document_id':member_version.document_id,'revision':str(member_version.revision),
            'source_proof':source_proof,'before_state_sha256':proof_a['candidate_sha256'],
            'candidate_state_sha256':proof_b['candidate_sha256'],'before_people_sha256':proof_a['people_sha256'],
            'candidate_people_sha256':proof_b['people_sha256'],'source_size':proof_a['source_size'],
            'before_output_size':proof_a['output_size'],'after_output_size':proof_b['output_size'],'before':a,'after':b}
        public.append({'path':other['path'],'visual':visual})
        entry['members'].append({'row':other,'path':other['path'],'visual':visual,'before_key':before_key,'after_key':after_key})
        displays[member_version.document_id]={'revision':visual['revision'],'before':left,'after':right}
    token=uuid.uuid4().hex
    review={'version':2,'token':token,'recipe':deepcopy(payload),
        'owner':proof(engine,row,state,source_row={**row,'state':current}),
        'face_ref':deepcopy(target['face_ref']),'patches_sha256':REVIEW.digest(patches),
        'visual':deepcopy(public[0]['visual']),'members':public}
    review['review_sha256']=REVIEW.digest(review)
    entry.update(review=review,expires=time.monotonic()+REVIEW.TTL)
    _verify(engine,state,target,entry)
    store=REVIEW._store(engine)
    while len(store['pending'])>=REVIEW.MAX_REVIEWS:store['pending'].popitem(last=False)
    store['images'].prune(store['pending']);store['images'].attach(_plan(review),displays)
    store['pending'][token]=entry
    return {'kind':'face_style_preview','review':deepcopy(review)}


def image(engine,state,target,payload,store,entry):
    if set(payload)!={'token','document_id','side','sha256'}:
        raise ValueError('Face-style alias images require their exact document identity')
    _verify(engine,state,target,entry);review=entry['review'];visual=_plan(review).records.get(payload['document_id'])
    if visual is None or payload['sha256']!=visual[payload['side']]['sha256']:
        raise ValueError('Face-style image does not belong to this reviewed alias')
    pixels=store['images'].read(_plan(review),visual['document_id'],visual['revision'],payload['side'],payload['sha256'])
    _verify(engine,state,target,entry)
    return {'kind':'face_style_image',**deepcopy(payload),'review_sha256':review['review_sha256'],'image':pixels}


def confirm(engine,state,target,payload,store,entry):
    _verify(engine,state,target,entry);review=entry['review']
    if payload['ack']!=_ack(review):raise ValueError('Confirm every exact face-style alias image pair in reviewed order')
    _available(store,review);_verify(engine,state,target,entry)
    return deepcopy(entry['candidate']),_proof(review)


def publish(engine,state,target,payload,candidate,proof,request_id):
    from . import face_style_review as REVIEW
    from .face_style_alias_history import prepare
    store,entry=REVIEW._entry(engine,payload['token'])
    if entry['review']['version']!=2:raise ValueError('Alias publication requires its complete multi-document review')
    _verify(engine,state,target,entry)
    if candidate!=entry['candidate'] or proof!=_proof(entry['review']) or payload['ack']!=proof['ack']:
        raise ValueError('Face-style alias publication differs from its reviewed graph or acknowledgement')
    batch=entry['batch'];plans=_plans(entry);targets=deepcopy(entry['targets'])
    history=prepare(entry['review'],plans,targets)
    try:
        batch.documents.remember_current()
        if LEDGER._targets(batch,engine,plans)!=targets:
            raise ValueError('Face-style alias ledger closure changed before preparation')
        LEDGER.prepare_scoped(engine,plans,targets)
        LEDGER._verify(batch,engine,plans,targets)
        _verify(engine,state,target,entry);_available(store,entry['review'])
        _verify(engine,state,target,entry)
        # Image reads and complete snapshot checks can be expensive. This final
        # exact ledger closure check is adjacent to the one-way token claim.
        if LEDGER._targets(batch,engine,plans)!=targets:
            raise ValueError('Face-style alias ledger closure changed before claim')
        entry['claimed']=True
        result=LEDGER.commit_scoped(batch,engine,plans,request_id=request_id,
            prepare=False,prepared_targets=targets,alias_history=history)
        if result is None:raise ValueError('Reviewed alias publication unexpectedly had no canonical change')
        bid,frame=result;entry['batch_id']=bid
        return bid,frame
    finally:
        # Never rewind the owner/document fences or release a claimed token on
        # an exception. The host preserves its existing outcome-unknown receipt.
        engine._people_staged=None


def verify_after_publish(engine,candidate,proof,entry):
    from .people_preset_plan import require_active_owner
    from .face_style_alias_history import check
    owner=require_active_owner(engine);row=V.current_row(engine);review=entry['review']
    current=engine._people_preset_capture();batch=engine._batch_controller()
    if (not entry['claimed'] or owner is not entry['owner'] or owner.fence!=entry['fence']+1
            or row is not entry['row'] or V.scope(row)!=entry['scope'] or engine._load_id!=entry['load_id']
            or engine._document_versions().workspace!=entry['workspace'] or batch is not entry['batch']
            or candidate!=entry['candidate'] or owner.snapshot()!=candidate or proof!=_proof(review)):
        raise ValueError('Face-style alias publication graph/fence changed; inspect the existing request')
    verify_dormant(engine,row,{entry['target']['face_ref']['asset_sha256']})
    members=_eligible(engine,row,current,entry['target']['face_ref']['asset_sha256'],advance=False)
    if len(members)!=len(entry['members']):raise ValueError('Published alias membership changed; inspect the existing request')
    for actual,frozen in zip(members,entry['members']):
        other,recipe,source,version=actual;visual=frozen['visual']
        if (other is not frozen['row'] or other['path']!=frozen['path']
                or version.document_id!=visual['document_id'] or version.revision!=int(visual['revision'])+1
                or source!=visual['source_proof']
                or snapshot_key(engine,other,recipe,owner.snapshot())!=frozen['after_key']):
            raise ValueError('Published alias source, revision or complete snapshot differs from review; inspect the existing request')
        SOURCE.verify_row({**other,'state':recipe},source)
    expected=deepcopy(entry['targets'])
    for target in expected.values():target['revision']+=1
    receipt=batch.ledger.get(entry.get('batch_id'),{})
    marker=check(receipt)
    if (_targets(engine,batch,_plans(entry),current)!=expected or receipt.get('targets')!=entry['targets']
            or marker is None or marker['review_sha256']!=review['review_sha256']
            or marker['document_ids']!=sorted(member['visual']['document_id'] for member in review['members'])):
        raise ValueError('Published alias ledger closure differs from review; inspect the existing request')
