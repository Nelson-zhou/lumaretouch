"""AUTHORED / UNRUN face-style host routing and receipt contracts.

Mocks validate orchestration, not rendering or product quality. No collection,
product imports, tests, builds, inference or downloads ran during authoring.
"""
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from lumaretouch_engine import people_state as S, people_host_commands as H
from lumaretouch_engine import face_style_review as R
from lumaretouch_engine import creative_derived_effects as D
from lumaretouch_engine import history_policy as HP
from lumaretouch_engine import project_recovery_runtime as PR


def fixture(action='face_style_catalog', payload=None):
    state=S.empty()
    evidence={'backend':'fixture','detector_model_sha256':'d'*64,'semantic_model_sha256':None,
              'landmark_digest':'e'*64,'status':'verified','source_width':128,'source_height':128,
              'orientation':'exif_normalized_once'}
    face=S.new_face('a'*64,[.1,.1,.6,.6],evidence)
    state['faces'][face['face_instance_id']]=face
    target={'scope':'face','target_id':face['face_instance_id'],'face_ref':S.face_ref(face)}
    row={'document_id':'doc-a'}
    owner=SimpleNamespace(fence=3,snapshot=lambda:deepcopy(state))
    binding={'document_id':'doc-a','document_epoch':'epoch-a','document_revision':0,'asset_sha256':'a'*64}
    engine=SimpleNamespace(_docs=[row],_doc_index=0,_people_scope_row=row,
        _people_active_context={'owner':owner},_people_graph_owner=owner,
        _guard_editable=lambda _:None,_people_binding=lambda:dict(binding),
        _people_owner=lambda:owner,_people_targets={'a'*64:deepcopy(target)},
        _people_cursors={'a'*64:target['target_id']},_vram=object(),
        _people_bind=Mock(side_effect=AssertionError('Read must never bind/migrate')),
        doc_state=Mock(return_value={'document_id':'doc-a'}),_people_receipts=OrderedDict())
    raw={'cmd':'people','action':action,'payload':{} if payload is None else payload,
         **{k:v for k,v in binding.items() if k!='asset_sha256'},
         'state_revision':state['revision'],'association_revision':state['association_revision'],
         'request_id':'request-a','target':target}
    return engine,state,raw


@pytest.mark.parametrize('action,payload',[
    ('face_style_catalog',{}),
    ('face_style_preview',{'version':1,'style':'classic','amount':.5}),
    ('face_style_image',{'token':'a'*32,'side':'before','sha256':'b'*64}),
])
def test_exact_read_routes_do_not_admit_confirm_or_extra_fields(action,payload):
    _,_,raw=fixture(action,payload)
    assert H.face_style_read_only(raw)
    assert D.is_local_command('people',raw)
    assert not H.face_style_read_only({**raw,'unexpected':True})
    assert not H.face_style_read_only({**raw,'action':[]})
    assert not H.face_style_read_only({**raw,'action':'face_style_confirm'})
    assert not H.face_style_read_only({**raw,'target':{'scope':'all_people','target_id':'a'*64,'face_ref':None}})


def test_checked_reads_never_bind_or_activate():
    engine,state,raw=fixture()
    assert H.checked(engine,raw)[0]==state
    engine._people_bind.assert_not_called()
    engine._people_active_context=None
    with pytest.raises(ValueError):H.checked(engine,raw)
    engine._people_bind.assert_not_called()


@pytest.mark.parametrize('change',['disabled','cursor','target','source','revision'])
def test_current_enabled_exact_face_required(change):
    engine,state,raw=fixture()
    if change=='disabled':state['faces'][raw['target']['target_id']]['enabled']=False
    elif change=='cursor':engine._people_cursors.clear()
    elif change=='target':engine._people_targets.clear()
    elif change=='source':raw['target']['face_ref']['asset_sha256']='f'*64
    else:raw['document_revision']+=1
    with pytest.raises(ValueError):H.checked(engine,raw)
    engine._people_bind.assert_not_called()


def test_read_result_echo_and_duplicate_without_doc_state():
    engine,_,raw=fixture();events=[]
    with patch.object(R,'catalogue',return_value={'kind':'face_style_catalog'}) as read:
        H.apply(engine,raw,events.append);H.finish(engine,raw,None,events.append)
        H.apply(engine,raw,events.append);H.finish(engine,raw,None,events.append)
    assert read.call_count==1 and len(events)==2 and events[0]==events[1]
    assert events[0]['success'] and 'doc_state' not in events[0]
    assert events[0]['face_style_request']=={k:raw[k] for k in (
        'action','document_id','document_epoch','document_revision','state_revision','association_revision','target','payload')}
    engine.doc_state.assert_not_called()


def test_publish_preverification_order_and_rejection_cleanup():
    engine,state,_=fixture();order=[]
    engine._people_source=lambda:{'sha256':'a'*64}
    engine._people_prepare_graph=lambda *args:order.append('prepare')
    engine._people_publish_graph=lambda *args:order.append('publish')
    with patch.object(H,'affected_assets',return_value=set()):
        H.publish(engine,state,state,'request-a',before_publish=lambda:order.append('verify'))
    assert order==['prepare','verify','publish']
    order.clear();engine._people_staged=object()
    def reject():
        order.append('verify');raise ValueError('changed source')
    with patch.object(H,'affected_assets',return_value=set()),pytest.raises(ValueError):
        H.publish(engine,state,state,'request-a',before_publish=reject)
    assert order==['prepare','verify'] and engine._people_staged is None


def test_postpublish_failure_is_unknown_and_request_not_reapplied():
    engine,state,raw=fixture('face_style_confirm',{'token':'a'*32,'ack':{
        'review_sha256':'b'*64,'before_sha256':'c'*64,'after_sha256':'d'*64}})
    proof={'kind':'face_style_confirm','token':'a'*32};events=[]
    def publish(*args,**kwargs):
        kwargs['before_publish']();engine._people_graph_owner.fence+=1
        return None,{'event':'image_ready'}
    with patch.object(R,'confirm',return_value=(state,proof)) as confirm, \
         patch.object(R,'verify_before_publish'),patch.object(H,'publish',side_effect=publish), \
         patch.object(R,'verify_after_publish',side_effect=ValueError('pixel mismatch')):
        with pytest.raises(ValueError):H.apply(engine,raw,events.append)
        H.finish(engine,raw,'pixel mismatch',events.append)
        H.apply(engine,raw,events.append);H.finish(engine,raw,None,events.append)
    assert confirm.call_count==1 and len(events)==2
    assert events[0]['outcome_unknown'] and not events[0]['success']
    assert events[0]==events[1] and events[0]['face_style_request']['payload']==raw['payload']


def test_read_recovery_finish_preserves_existing_taint_and_revision():
    engine,_,raw=fixture()
    runtime=SimpleNamespace(tainted=True,reason='existing',revision=7)
    engine._project_recovery_runtime=runtime
    PR.finish(engine,{'message':raw,'started':True,'returned':False,'failed':True},'read failed')
    assert vars(runtime)=={'tainted':True,'reason':'existing','revision':7}


def test_confirm_history_identity_does_not_coalesce_distinct_reviews():
    _,_,raw=fixture('face_style_confirm')
    assert HP.command_group('people',raw)!=HP.command_group('people',{**raw,'request_id':'request-b'})


def test_dispatch_read_route_remains_after_all_pending_guards():
    source=(Path(__file__).parents[1]/'src/lumaretouch_engine/server.py').read_text()
    body=source[source.index('    def _process_line('):]
    route=body.index('if face_style_read_only(msg):')
    for guard in ('recovery.host.blocks','managed.blocks','package.blocks','CDH.guard_command','relocation.blocks'):
        assert body.index(guard)<route
    for mutation in ('invalidate_other(self,name,msg)','self._arm_before_command(msg)','before = self._history_capture()'):
        assert route<body.index(mutation)
