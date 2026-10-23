"""AUTHORED / UNRUN: derived parked-source and scoped planner contracts.

The mocked rendering cases prove plumbing only, not inference, native float
accuracy, image quality, or functional batch acceptance. Shared transfer remains
fenced until its association/effect consumers are admitted independently.
"""
from copy import deepcopy
from types import SimpleNamespace
import struct
import numpy as np
import pytest

from lumaretouch_engine import creative_derived_source as D, people_state as S
from lumaretouch_engine.creative_document_assets import make_asset


def base(value=.5, width=2, height=1):
    return make_asset('rgba',width,height,struct.pack('<ffff',value,.25,.125,1.)*(width*height))


def row(tmp_path, value=.5, identity='derived', width=2, height=1):
    path=tmp_path/'provenance.jpg'
    if not path.exists():path.write_bytes(b'Not decoded: physical original provenance only')
    return {'document_id':identity,'path':str(path),'src_w':9000,'src_h':6000,
            'state':{'_creative_base':base(value,width,height)}}


def test_row_proof_separates_same_path_canonical_sources_and_extent(tmp_path):
    first=row(tmp_path,.5,'first');second=row(tmp_path,.50001,'second')
    a,b=D.row_proof(first),D.row_proof(second)
    assert a['original_sha256']==b['original_sha256']
    assert a['asset_sha256']!=b['asset_sha256']
    assert a['creative_source']=={'sha256':a['asset_sha256'],'width':2,'height':1}
    assert D.row_asset(first)==a['asset_sha256']
    changed=row(tmp_path,.5,'first',1,2)
    assert D.row_proof(changed)['creative_source']!=a['creative_source']
    with pytest.raises(ValueError):D.verify_row(changed,a)


def test_original_identity_does_not_require_invented_dimensions(tmp_path):
    original=row(tmp_path);original['state']={};original.pop('src_w');original.pop('src_h')
    proof=D.row_proof(original)
    assert proof['creative_source'] is None
    assert proof['asset_sha256']==proof['original_sha256']==D.row_asset(original)
    D.verify_row_target(original,{'asset_sha256':proof['asset_sha256']})


def test_changed_provenance_invalidates_unchanged_derived_canvas(tmp_path):
    target=row(tmp_path);proof=D.row_proof(target)
    (tmp_path/'provenance.jpg').write_bytes(b'Changed physical original')
    assert D.row_asset(target)==proof['asset_sha256']
    with pytest.raises(ValueError,match='provenance'):D.verify_row(target,proof)


def test_legacy_original_receipt_cannot_authorize_returned_canvas(tmp_path):
    target=row(tmp_path);proof=D.row_proof(target)
    for digest in (proof['original_sha256'],proof['asset_sha256']):
        with pytest.raises(ValueError,match='Legacy'):
            D.verify_row_target(target,{'asset_sha256':digest})
    D.verify_row_target(target,{'asset_sha256':proof['asset_sha256'],'source_proof':proof})


def test_frozen_proof_is_detached_and_rejects_conflicting_extent(tmp_path):
    target=row(tmp_path);proof=D.row_proof(target);checked=D.check_row_proof(proof)
    checked['creative_source']['width']=7
    assert proof['creative_source']['width']==2
    with pytest.raises(ValueError):D.verify_row(target,checked)
    proof['creative_source']['width']=True
    with pytest.raises(ValueError):D.check_row_proof(proof)


def test_scoped_targets_use_effective_assets_not_shared_physical_path(tmp_path,monkeypatch):
    from lumaretouch_engine import people_batch_ledger as L, virtual_copy_people as V
    first=row(tmp_path,.5,'first');second=row(tmp_path,.6,'second')
    original={**first,'document_id':'original','state':{}}
    rows=[original,first,second]
    version=lambda item:SimpleNamespace(document_id=item['document_id'],revision=0)
    owner=SimpleNamespace(documents=SimpleNamespace(rows=lambda:rows),versions=SimpleNamespace(check_advance=version))
    monkeypatch.setattr(V,'scope',lambda item:item['document_id'])
    plans={}
    for item in (first,second):
        before=S.empty()
        candidate=S.set_override(before,'all_people',D.row_asset(item),'fixture.portrait','/strength',.5)
        plans[item['document_id']]={'row':item,'before':before,'candidate':candidate}
    targets=L._targets(owner,SimpleNamespace(),plans)
    assert {target['document_id'] for target in targets.values()}=={'first','second'}
    assert len({target['asset_sha256'] for target in targets.values()})==2
    for target in targets.values():
        assert target['source_proof']['creative_source']['width']==2


def test_scoped_undo_rejects_old_receipt_before_preparing_or_publishing(tmp_path,monkeypatch):
    from lumaretouch_engine import people_batch_ledger as L, virtual_copy_people as V
    target=row(tmp_path);proof=D.row_proof(target)
    owner=SimpleNamespace(versions=SimpleNamespace(find=lambda _rows,_identity:(0,target)))
    engine=SimpleNamespace(_docs=[target],_batch_controller=lambda:owner)
    monkeypatch.setattr(V,'scope',lambda _row:'project')
    monkeypatch.setattr(L,'prepare_scoped',lambda *_args:pytest.fail('Legacy derived undo reached preparation'))
    receipt={'targets':{'0':{'document_id':target['document_id'],'path':target['path'],
        'people_scope':'project','asset_sha256':proof['original_sha256']}},'people_scoped_changes':[]}
    with pytest.raises(ValueError,match='Legacy'):L.restore_scoped(engine,receipt,False)


def test_transfer_freezes_effective_sources_and_rejects_changed_canvas(tmp_path,monkeypatch):
    from lumaretouch_engine import people_batch_transfer as T, people_candidate_render as C
    from lumaretouch_engine import virtual_copy_people as V, people_algorithms as A
    from lumaretouch_engine.batch_preflight import PreflightStore
    from lumaretouch_engine.document_versions import DocumentVersions
    source=row(tmp_path,.5,'source');target=row(tmp_path,.6,'target');rows=[source,target]
    def graph(item):
        state=S.empty()
        evidence={'backend':'authored_fixture','detector_model_sha256':None,'semantic_model_sha256':None,
            'landmark_digest':None,'status':'synthetic','source_width':2,'source_height':1,
            'orientation':'exif_normalized_once'}
        face=S.new_face(D.row_asset(item),(.1,.1,.8,.8),evidence)
        state['faces'][face['face_instance_id']]=face
        state['persons']['fixture-person']={'anonymous':True}
        state['links']=[{'face_instance_id':face['face_instance_id'],'person_id':'fixture-person',
                        'state':'confirmed','confirmation_revision':0}]
        return S.check(state),S.face_ref(face)
    source_graph,source_ref=graph(source);target_graph,_=graph(target)
    source_graph=S.set_override(source_graph,'face',source_ref['face_instance_id'],'fixture.portrait','/strength',.5)
    graphs={'source':source_graph,'target':target_graph};owner=SimpleNamespace(snapshot=lambda:source_graph,fence=0)
    versions=DocumentVersions()
    for item in rows:versions.version(item)
    documents=SimpleNamespace(remember_current=lambda:None,rows=lambda:rows,current_index=lambda:0)
    batch=SimpleNamespace(documents=documents,versions=versions,target_indices=lambda _docs:([1],[]))
    engine=SimpleNamespace(_people_bind=lambda:None,_people_owner=lambda:owner,
                           _document_versions=lambda:versions,_batch_controller=lambda:batch)
    monkeypatch.setattr(V,'row_snapshot',lambda _engine,item:deepcopy(graphs[item['document_id']]))
    monkeypatch.setattr(A,'defaults',lambda:{'fixture.portrait':{'/strength':0.}})
    # Planner contract only: synthetic evidence cannot pass real portrait render.
    prepared=[]
    monkeypatch.setattr(C,'validate',lambda _engine,item,_candidate:prepared.append(D.row_asset(item)))
    events=[];store=PreflightStore(lambda:1)
    controller=SimpleNamespace(store=store,_source=lambda _plan:{},emit=events.append,emit_result=lambda *_args:None)
    request={'cmd':'batch','action':'preflight','request_id':'fixture','docs':[1],'module_scope':['fixture.portrait'],
        'people_transfer':{'source_ref':source_ref,'selection':{'fixture.portrait':['/strength']},
                           'target_policy':'confirmed_person_only'}}
    T.preflight(engine,controller,request)
    plan=store.get(events[-1]['preflight_token'],versions.workspace)
    assert events[-1]['ok']==1 and prepared==[D.row_asset(target)]
    assert plan.params()[T.MARKER]['source_proof']==D.row_proof(source)
    target['state']['_creative_base']=base(.61)
    with pytest.raises(ValueError,match='No confirmed target'):
        T.commit(engine,controller,{'cmd':'batch','action':'commit','preflight_token':plan.token},plan)
    assert graphs['target']==target_graph


def parked_fixture(tmp_path,monkeypatch,*,stale_analysis=False,omit_candidate=False):
    from lumaretouch_engine import people_candidate_render as C, virtual_copy_people as V
    from lumaretouch_engine import creative_document_base as B, export_recipe as R, export as E
    from lumaretouch_engine import decode, cpu_memory_budget as MEMORY
    from lumaretouch_engine import local_grade_source, effect_recovery_runtime, manual_liquify_runtime
    from lumaretouch_engine import studio_background_runtime, sky_replacement_runtime, body_pose_render, id_background_runtime
    target=row(tmp_path);candidate=S.empty();context={'fixture':'exact parked context'}
    if stale_analysis:
        target['state']['_precompute']=SimpleNamespace(input_source_binding=None,masks={})
    calls=[]
    monkeypatch.setattr(V,'row_context',lambda _engine,selected:deepcopy(context) if selected is target else pytest.fail('Wrong row'))
    monkeypatch.setattr(MEMORY,'available_estimate',lambda:4_000_000_000)
    monkeypatch.setattr(decode,'load_full',lambda *_args,**_options:pytest.fail('Decoded original instead of composite'))
    monkeypatch.setattr(decode,'is_raw',lambda *_args:pytest.fail('Inspected original decoder for composite'))
    for module in (local_grade_source,effect_recovery_runtime,manual_liquify_runtime,studio_background_runtime,
                   sky_replacement_runtime,body_pose_render,id_background_runtime):
        monkeypatch.setattr(module,'check_export_decode',lambda _snap,_path,_stamp,shape: calls.append(('shape',shape)))
    def snapshot(state,**options):
        assert state is not target['state']
        assert options['people_context']==context and options['people_graph']==candidate
        people=None if omit_candidate else {'state':candidate,'asset_sha256':D.row_asset(target),
            'creative_source':D.binding(state),'analyses':{}}
        return {'creative_base':state['_creative_base'],'people':people,'grade_scope':'all',
                'crop_rect':(0.,0.,1.,1.),'crop_rotation':0.}
    def recipe(snap,h,w,**options):
        assert (h,w)==(1,2) and options=={'for_document':True}
        return SimpleNamespace(creative_base=snap['creative_base']),[]
    monkeypatch.setattr(R,'build_export_spec',recipe)
    # Exercise the real export_float -> single creative resolver route, while
    # native transfer and downstream pixels remain explicit test doubles.
    working=np.array([[[.1234567,.25,.5],[.1234568,.25,.5]]],dtype=np.float32)
    monkeypatch.setattr(B,'require_rebound_spec',lambda _spec:None)
    def resolve(record,**_options):
        assert record['id']==target['state']['_creative_base']['id']
        calls.append(('resolve',record['id']));return working
    monkeypatch.setattr(B,'export_source',resolve)
    def render(pixels,spec,**_options):
        assert pixels is working and pixels.dtype==np.float32
        assert spec._creative_source_resolved and spec.float_output
        assert pixels[0,0,0]!=pixels[0,1,0]
        calls.append(('render',pixels.dtype));return pixels,{}
    monkeypatch.setattr(E,'_export_image_impl',render)
    engine=SimpleNamespace(_document_versions=lambda:SimpleNamespace(version=lambda _row:('document',0)),
                           _state_to_export_snap=snapshot)
    return C,engine,target,candidate,calls


def test_parked_target_uses_exact_context_extent_and_single_float_resolver(tmp_path,monkeypatch):
    C,engine,target,candidate,calls=parked_fixture(tmp_path,monkeypatch)
    C.validate(engine,target,candidate)
    assert [kind for kind,_value in calls].count('resolve')==1
    assert [kind for kind,_value in calls].count('render')==1
    assert all(value==(1,2) for kind,value in calls if kind=='shape')


def test_parked_original_analysis_is_not_relabelled(tmp_path,monkeypatch):
    C,engine,target,candidate,calls=parked_fixture(tmp_path,monkeypatch,stale_analysis=True)
    with pytest.raises(ValueError,match='inference-input'):C.validate(engine,target,candidate)
    assert not calls


def test_parked_preflight_cannot_certify_omitted_candidate(tmp_path,monkeypatch):
    C,engine,target,candidate,calls=parked_fixture(tmp_path,monkeypatch,omit_candidate=True)
    with pytest.raises(ValueError,match='candidate portrait graph'):C.validate(engine,target,candidate)
    assert not calls


def test_generic_batch_admission_stays_closed_even_with_original_active(tmp_path):
    from lumaretouch_engine.creative_document_host import guard_command
    target=row(tmp_path);engine=SimpleNamespace(_creative_base=None,_docs=[target])
    with pytest.raises(ValueError):guard_command(engine,'batch',{'action':'preflight','people_transfer':{}})
