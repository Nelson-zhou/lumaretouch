"""AUTHORED / UNRUN. Run by Qoder only after integration and native packaging.

These contracts cover independent modules, not product functional acceptance.
"""
import struct
from copy import deepcopy
import pytest
from lumaretouch_engine.creative_document_assets import AssetStore, make_asset
from lumaretouch_engine import creative_document_state as S
from lumaretouch_engine.creative_document_project import capture_into, restore_from, validate_history_frames
from lumaretouch_engine.creative_document_controller import CreativeController, CreativePorts


def setup_document():
    assets = AssetStore()
    asset = make_asset('rgba',1,1,struct.pack('<ffff',.25,.1,.05,.5),original=b'fixture-source')
    identity = assets.intern(asset)
    return assets,S.create('stable-source-uid',identity,assets)


def test_neutral_and_source_retained():
    assets,doc = setup_document()
    assert S.apply(doc,{'action':'opacity','opacity':1},assets) == doc
    after = S.apply(doc,{'action':'delete'},assets)
    assert after['layers'] == [] and after['source_asset'] == doc['source_asset']
    assert assets.get(doc['source_asset'])['original'] == b'fixture-source'


def test_duplicate_identity_bytes_and_undo_frame():
    assets,doc = setup_document()
    after = S.apply(doc,{'action':'duplicate'},assets)
    assert len({x['id'] for x in after['layers']}) == 2
    assert len({x['asset_id'] for x in after['layers']}) == 1
    frame = capture_into({'other_effect':{'strength':.2}},doc,assets)
    restored,store = restore_from(frame)
    assert restored == doc and store.get(doc['source_asset']) == assets.get(doc['source_asset'])
    assert frame['other_effect'] == {'strength':.2}


@pytest.mark.parametrize('command',[
    {'action':'opacity','opacity':float('nan')}, {'action':'blend','blend':'overlay'},
    {'action':'transform','transform':{'scale_x':0}}, {'action':'visibility','visible':1},
    {'action':'canvas','width':2}, {'action':'rename','name':''},
])
def test_rejection_is_atomic(command):
    assets,doc = setup_document(); before = deepcopy(doc)
    with pytest.raises((ValueError,KeyError)): S.apply(doc,command,assets)
    assert doc == before


def test_locked_ancestor_fences_edit():
    assets,doc = setup_document(); identity = doc['selected_id']
    group = S.apply(doc,{'action':'group','layer_ids':[identity],'name':'Group'},assets)
    locked = S.apply(group,{'action':'lock','locked':True},assets)
    with pytest.raises(ValueError): S.apply(locked,{'action':'rename','layer_id':identity,'name':'changed'},assets)
    with pytest.raises(ValueError): S.apply(locked,{'action':'lock','layer_id':identity,'locked':False},assets)


def test_canvas_resize_retains_original_and_alignment():
    assets,doc = setup_document(); identity = doc['selected_id']
    doc = S.apply(doc,{'action':'select','layer_id':None},assets)
    doc = S.apply(doc,{'action':'canvas','width':3,'height':4,'dpi':300},assets)
    doc = S.apply(doc,{'action':'align','layer_id':identity,'alignment':'right'},assets)
    assert doc['layers'][0]['transform']['x'] == 2
    assert assets.get(doc['source_asset'])['width'] == 1


def test_mask_real_coverage_duplicate_rejected():
    assets,doc = setup_document()
    mask = assets.intern(make_asset('mask',1,1,struct.pack('<f',.25)))
    doc = S.apply(doc,{'action':'add_mask','mask_id':mask},assets)
    with pytest.raises(ValueError): S.apply(doc,{'action':'add_mask','mask_id':mask},assets)
    assert S.apply(doc,{'action':'remove_mask'},assets)['layers'][0]['mask_id'] is None


def test_group_cycle_rejected():
    assets,doc = setup_document()
    doc = S.apply(doc,{'action':'group','name':'Outer','layer_ids':[doc['selected_id']]},assets)
    outer = doc['selected_id']
    doc = S.apply(doc,{'action':'group','name':'Inner','layer_ids':[]},assets)
    inner = doc['selected_id']
    doc = S.apply(doc,{'action':'move','layer_id':inner,'parent_id':outer,'index':1},assets)
    with pytest.raises(ValueError): S.apply(doc,{'action':'move','layer_id':outer,'parent_id':inner,'index':0},assets)


def test_project_corruption_fails_before_publish():
    assets,doc = setup_document(); frame = capture_into({},doc,assets)
    frame['_creative_asset_records'][doc['source_asset']]['content'] = bytes(16)
    with pytest.raises(ValueError): restore_from(frame)


def test_project_global_store_deduplicates_history():
    assets,doc = setup_document(); frame = capture_into({},doc,assets)
    merged = validate_history_frames([frame,deepcopy(frame)])
    assert len(merged.records(S.references(doc))) == 1


def controller_fixture():
    assets,doc = setup_document(); live = {'document':doc,'token':'owner-1','undo':[],'returns':[]}
    def commit(after,before,label):
        if label: live['undo'].append(before)
        live['document'] = after
    def returned(plan):
        live['returns'].append(plan)
        return {'status':'applied','document_id':'new-host-image'}
    ports = CreativePorts(lambda:live['document'],lambda:live['token'],lambda _:None,commit,returned,lambda:True)
    controller = CreativeController(ports,assets)
    envelope = {'request_id':'request-1','document_id':doc['document_id'],'source_uid':doc['source_uid'],
                'expected_revision':0,'ownership_token':'owner-1'}
    return controller,live,envelope,assets


def test_controller_single_history_owner_and_duplicate_receipt():
    controller,live,envelope,_ = controller_fixture()
    receipt = controller.command(envelope,{'action':'rename','name':'Edited'})
    assert receipt['status'] == 'applied' and len(live['undo']) == 1
    assert controller.command(envelope,{'action':'rename','name':'Edited'}) == receipt
    assert len(live['undo']) == 1


def test_selection_does_not_add_history():
    controller,live,envelope,_ = controller_fixture()
    controller.command(envelope,{'action':'select','layer_id':None})
    assert live['undo'] == [] and live['document']['revision'] == 1


def test_return_fences_pending_edits_and_new_owner():
    controller,live,envelope,_ = controller_fixture()
    ticket = controller.begin_return(envelope,'update_original')
    with pytest.raises(ValueError): controller.command(envelope,{'action':'rename','name':'Race'})
    live['token'] = 'owner-2'
    with pytest.raises(ValueError): controller.complete_return(ticket,live['document']['source_asset'])
    assert live['returns'] == []
    controller.cancel_return(ticket['ticket_id'])


def test_return_plan_preserves_source_not_generated(monkeypatch):
    controller,live,envelope,_ = controller_fixture()
    ticket = controller.begin_return(envelope,'new_image')
    from lumaretouch_engine import creative_document_render
    class UnitRenderer:
        def __init__(self,*args,**kwargs): pass
        def render_asset(self): return controller.assets.get(live['document']['source_asset'])
    monkeypatch.setattr(creative_document_render,'CreativeRenderer',UnitRenderer)
    identity = controller.render_return(ticket)
    result = controller.complete_return(ticket,identity)
    plan = live['returns'][0]
    assert result['returned_document_id'] == 'new-host-image'
    assert plan['unmodified_source_asset'] == live['document']['source_asset']
    assert plan['provenance'] == 'creative_composite' and plan['preserve_history']
    with pytest.raises(ValueError): controller.begin_return(envelope,'new_image')


def test_return_rejects_arbitrary_asset_without_render():
    controller,live,envelope,_ = controller_fixture()
    ticket = controller.begin_return(envelope,'new_image')
    with pytest.raises(ValueError): controller.complete_return(ticket,live['document']['source_asset'])
    assert live['returns'] == []


def test_flip_keeps_layer_center_and_canvas_position():
    assets,doc = setup_document()
    flipped = S.apply(doc,{'action':'transform','transform':{'flip_x':True,'flip_y':True}},assets)
    assert S.bounds(flipped['layers'][0],assets) == (0.0,0.0,1.0,1.0)


def test_returned_base_source_bound_commands_fail_before_dispatch():
    from types import SimpleNamespace
    from lumaretouch_engine.creative_document_host import guard_command
    engine = SimpleNamespace(_creative_base={'id':'opaque-base'})
    for name, request in (
        ('face', {'action':'select'}), ('precompute', {}),
        ('precompute', {'action':'state'}), ('set_strength', {'action':'state'}),
        ('grade', {'action':'mask'}),
        ('colour_editor', {'action':'preview','recipe':{'scope':'local'}}),
        ('preset', {'action':'apply'}),
    ):
        with pytest.raises(ValueError): guard_command(engine,name,request)
    for name, request in (
        ('exposure', {}), ('crop', {}), ('grade', {'scope':'all'}),
        ('creative_document', {'action':'command'}), ('colour_editor_state', {}),
    ):
        guard_command(engine,name,request)


def test_photo_return_rejects_alpha_hdr_without_changing_asset():
    from lumaretouch_engine.creative_document_host import require_photo_return
    for values in ((.25,.1,.05,.5),(2.,0.,0.,1.),(-.1,0.,0.,1.)):
        record = make_asset('rgba',1,1,struct.pack('<ffff',*values))
        before = deepcopy(record)
        with pytest.raises(ValueError): require_photo_return(record)
        assert record == before
    require_photo_return(make_asset('rgba',1,1,struct.pack('<ffff',.5,.25,0.,1.)))
