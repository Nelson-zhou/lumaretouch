"""WB migration/transfer boundaries, independent of UI and photographic acceptance."""
import copy
import json
from pathlib import Path
import pytest
from lumaretouch_engine import white_balance_recipe as W, scope as S, project as P


def state():
    return {'_exposure': (.5,200,.1,10,20,30,40), '_exposure_ref_k':7000,
            '_wb_options':{**W.default_options(W.CORRECTED),'picked_gains':[1.2,.8,1.1]}}


def test_legacy_omission_is_stable_and_preserves_target_reference():
    old={'temperature_shift':-300}
    clean=S.check_params(S.OP_WHITE_BALANCE,old)
    assert 'options' not in clean
    assert S.check_params(S.OP_WHITE_BALANCE,json.loads(json.dumps(clean)))==clean
    target=state();W.apply_transfer(target,clean)
    assert target['_exposure']==(.5,-300,0,10,20,30,40)
    assert target['_exposure_ref_k']==7000 and target['_wb_options']==W.default_options()
    assert W.transfer_from_state(target)['options']['reference_k']==7000


def test_explicit_transfer_owns_reference_and_ev_only_isolation():
    source=state();payload=W.transfer_from_state(source)
    target=state();target['_exposure_ref_k']=5000
    W.apply_transfer(target,payload)
    assert target==source
    S.MODULES[S.OP_EXPOSURE]['write'](target,{'ev':1})
    assert target['_wb_options']==source['_wb_options'] and target['_exposure_ref_k']==7000
    payload['options']['picked_gains'][0]=9
    assert source['_wb_options']['picked_gains'][0]==1.2 and target['_wb_options']['picked_gains'][0]==1.2


@pytest.mark.parametrize('options',[None,{}, {'version':99}, {**W.neutral_transfer_options(),'reference_k':True}])
def test_malformed_explicit_options_reject_before_mutation(options):
    target=state();before=copy.deepcopy(target)
    with pytest.raises(ValueError): W.apply_transfer(target,{'options':options})
    assert target==before


def test_structured_registry_neutral_agrees_without_aliases():
    registry=Path(__file__).resolve().parents[2]/'docs/p0/registry-extensions.json'
    entries=json.loads(registry.read_text())['entries']
    neutral=next(x['neutral'] for x in entries if x['operation_id']==S.OP_WHITE_BALANCE and x['parameter_key']=='options')
    assert S._neutral_of(S.OP_WHITE_BALANCE,'options')==neutral==W.neutral_transfer_options()
    clean=S.check_params(S.OP_WHITE_BALANCE,{'options':neutral})
    clean['options']['picked_gains'][0]=2
    assert S._neutral_of(S.OP_WHITE_BALANCE,'options')['picked_gains'][0]==1


def project_file(tmp_path):
    source=tmp_path/'source';source.write_bytes(b'unchanged source')
    project=P.new_project('WB',str(tmp_path));P.add_doc(project,str(source),state())
    return project,source,tmp_path/'project.json'


def test_v1_migration_save_v4_preserves_legacy_and_caller(tmp_path):
    project,source,path=project_file(tmp_path)
    project['schema_version']=P.LEGACY_SCHEMA
    recipe=project['docs'][0]['versions'][0]['recipe'];del recipe['_wb_options']
    before=copy.deepcopy(project)
    P.save(project,str(path))
    assert project==before
    saved=json.loads(path.read_text());assert saved['schema_version']=='lrt.project.v4'
    back=P.load(str(path));recipe,_=P.active_recipe(back,str(source))
    assert recipe['_wb_options']==W.default_options() and recipe['_exposure_ref_k']==7000
    # Read a literal old file too; writer normalization is not evidence of old-reader migration.
    path.write_text(json.dumps(before));back=P.load(str(path))
    assert back['schema_version']=='lrt.project.v4' and back['migration_notes']


def test_v2_missing_or_invalid_inactive_version_rejects_without_overwrite(tmp_path):
    project,source,path=project_file(tmp_path);P.save(project,str(path));original=path.read_bytes()
    bad=copy.deepcopy(project);del bad['docs'][0]['versions'][0]['recipe']['_wb_options']
    with pytest.raises(P.ProjectError):P.save(bad,str(path))
    assert path.read_bytes()==original
    inactive=copy.deepcopy(project['docs'][0]['versions'][0]);inactive['id']='inactive'
    inactive['recipe']['_wb_options']['algorithm']='unknown'
    bad=copy.deepcopy(project);bad['docs'][0]['versions'].append(inactive)
    path.write_text(json.dumps(bad))
    with pytest.raises(P.ProjectError):P.load(str(path))


def test_invalid_wb_cannot_be_degraded_by_asset_encoder(tmp_path):
    project,source,_=project_file(tmp_path);before=copy.deepcopy(project)
    bad=state();bad['_wb_options']['picked_gains'][0]=float('nan')
    with pytest.raises(P.ProjectError):P.add_doc(project,str(source),bad)
    assert project==before


def test_neutral_legacy_reference_outside_daylight_remains_inactive():
    old={'_exposure':(0,0,0),'_exposure_ref_k':3500}
    assert W.prepare_state(old) is None
    with pytest.raises(ValueError):W.prepare_state({**old,'_exposure':(1,0,0)})


def test_picked_only_master16_is_not_neutral_passthrough():
    pytest.importorskip('torch')
    from lumaretouch_engine.server import Engine
    snap={'wb_options':{**W.default_options(),'picked_gains':[1.2,1,1]}}
    assert any('白平衡' in x for x in Engine._master16_snapshot_blockers(snap))


def test_parked_batch_overflow_rejects_all_targets_before_writes():
    from test_batch_sync_controller import fixture
    controller,rows,_,events,replays,_=fixture()
    rows[0]['state']['_exposure']=(0.,)*7
    rows[0]['state']['_wb_options']={**W.default_options(),'picked_gains':[1e308,1,1]}
    rows[2]['state']['_exposure']=(5.,0.,0.,0.,0.,0.,0.)
    before=copy.deepcopy(rows)
    controller.handle_command({'action':'commit','docs':[1,2],'module_scope':[S.OP_WHITE_BALANCE]})
    assert rows==before and not replays and controller.sequence==0 and not controller.ledger
    assert any(event.get('event')=='error' for event in events)


def test_batch_undo_invalid_cross_module_combination_is_reported_conflict():
    from test_batch_sync_controller import fixture
    controller,rows,_,events,_,_=fixture()
    rows[0]['state']['_exposure']=(0.,)*7
    rows[2]['state']['_wb_options']={**W.default_options(),'picked_gains':[1e308,1,1]}
    controller.handle_command({'action':'commit','docs':[1,2],'module_scope':[S.OP_WHITE_BALANCE]})
    batch_id=controller.summary()['last']
    rows[2]['state']['_exposure']=(5.,0.,0.,0.,0.,0.,0.)
    controller.handle_command({'action':'undo','batch_id':batch_id})
    result=controller.summary()['last_result']
    assert result['restored']==[1] and result['conflicts'][0]['index']==2
    assert rows[2]['state']['_wb_options']['picked_gains']==[1,1,1]
    assert rows[2]['state']['_exposure'][0]==5 and controller.ledger[batch_id]['undone']
