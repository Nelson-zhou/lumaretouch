"""AUTHORED / UNRUN. Policy fixtures, not rendered-image acceptance evidence."""
from copy import deepcopy
import pytest
from lumaretouch_engine import scope as SC
from lumaretouch_engine import creative_derived_source as SOURCE
from lumaretouch_engine.local_grade_preset_review import PresetReviews
from lumaretouch_engine.preset_transaction import apply_with_rollback, PresetApplyError


def setup(tmp_path):
    path=tmp_path/'original.bin';path.write_bytes(b'original-provenance')
    state={'_crop_rect':(0.,0.,1.,1.),'_crop_rotation':0.,'_unselected':7}
    row={'path':str(path),'document_id':'target','state':state,'src_w':640,'src_h':480}
    preset={'id':'crop','name':'crop','kind':'crop','modules':{SC.OP_CROP:{'rect_normalized':[.1,.2,.9,.8],'rotation_degrees':13.}}}
    calls=[]
    # Deliberately fake callback evidence: tests exercise token policy, not the
    # real renderer or crop proof schema. Real proof validation has its own tests.
    def prepare(row,candidate,document_id,revision):
        proof={'candidate':deepcopy(candidate),'source':SOURCE.row_proof(row)}
        calls.append(('prepare',document_id,revision))
        return proof,{'fixture_only':True}
    def verify(row,candidate,document_id,revision,record):
        calls.append(('verify',document_id,revision))
        if record is None or candidate!=record['candidate']:raise ValueError('candidate changed')
        SOURCE.verify_row(row,record['source'])
    return state,row,preset,prepare,verify,calls


def test_original_crop_requires_preview_and_verifier(tmp_path):
    state,row,preset,prepare,verify,_=setup(tmp_path)
    reviews=PresetReviews()
    for kwargs in ({},{'prepare_crop':prepare},{'verify_crop':verify}):
        with pytest.raises(ValueError):reviews.prepare(preset,state,row,'target','3',None,**kwargs)
    assert not reviews.pending


def test_crop_review_pins_unselected_candidate_and_keeps_token_on_refusal(tmp_path):
    state,row,preset,prepare,verify,_=setup(tmp_path);reviews=PresetReviews()
    result=reviews.prepare(preset,state,row,'target','3',None,prepare_crop=prepare,verify_crop=verify)
    token=result['preflight_token'];changed={**state,'_unselected':8}
    with pytest.raises(ValueError,match='candidate changed'):
        reviews.claim(token,'crop',changed,row,'target','3',verify)
    assert token in reviews.pending


@pytest.mark.parametrize('change',['source','revision','missing_proof','missing_verifier'])
def test_crop_review_cannot_rebind_or_skip_evidence(tmp_path,change):
    state,row,preset,prepare,verify,_=setup(tmp_path);reviews=PresetReviews()
    result=reviews.prepare(preset,state,row,'target','3',None,prepare_crop=prepare,verify_crop=verify)
    token=result['preflight_token'];revision='3'
    if change=='source':(tmp_path/'original.bin').write_bytes(b'replaced')
    elif change=='revision':revision='4'
    elif change=='missing_proof':reviews.pending[token]['crop']=None
    else:verify=None
    with pytest.raises(ValueError):reviews.claim(token,'crop',state,row,'target',revision,verify)
    assert token in reviews.pending


def test_crop_review_success_is_one_use_and_does_not_mutate_original(tmp_path):
    state,row,preset,prepare,verify,_=setup(tmp_path);before=deepcopy(state);reviews=PresetReviews()
    result=reviews.prepare(preset,state,row,'target','3',None,prepare_crop=prepare,verify_crop=verify)
    record=reviews.claim(result['preflight_token'],'crop',state,row,'target','3',verify)
    assert state==before and record['source_proof']['creative_source'] is None
    assert result['crop_transfer']=={'fixture_only':True}
    with pytest.raises(ValueError):reviews.claim(result['preflight_token'],'crop',state,row,'target','3',verify)


def test_post_render_provenance_failure_uses_existing_rollback_boundary():
    calls=[];events=[];before={'value':1};after={'value':2}
    def replay(state,**kwargs):
        calls.append((state,kwargs));return {'event':'fixture_frame'}
    def stale():raise ValueError('source changed during render')
    with pytest.raises(PresetApplyError) as error:
        apply_with_rollback(replay,before,after,preset_id='crop',emit=events.append,invalidate=lambda:None,
                            strict_local=True,verify_after=stale)
    assert error.value.rolled_back and [item[0] for item in calls]==[after,before]
    assert calls[0][1]['strict_local'] is True and events==[{'event':'fixture_frame'}]


def test_raw_crop_preset_apply_has_no_review_bypass():
    # Static contract assertion remains UNRUN, not proof of native reachability.
    import pathlib
    source=(pathlib.Path(__file__).parents[3]/'src/lumaretouch_engine/preset_controller.py').read_text()
    assert 'or SC.OP_CROP in mods: raise SC.ScopeError' in source
    assert 'record.get(\'crop\')' in source
    assert 'verify_after=verify_after if SC.OP_CROP in ops else None' in source


def test_native_crop_receipt_reachable_and_preflight_does_not_refresh_its_fence():
    import pathlib
    root=pathlib.Path(__file__).parents[4]
    native=(root/'ui/src-tauri/src/preset_host.rs').read_text()
    hook=(root/'ui/src/presets/usePresetWorkflow.ts').read_text()
    assert '(local||optics||crop)' in native and 'crop_review(&value["crop_transfer"]' in native
    assert "if(result.action!=='preflight')void Promise.resolve()" in hook
