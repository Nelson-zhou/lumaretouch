"""AUTHORED / UNRUN: bounded transfer transport and read-only inventory routes.

Source assertions are wiring checks, not native compilation or GUI acceptance.
"""
from pathlib import Path
from types import SimpleNamespace
import pytest
from lumaretouch_engine import creative_transfer_host as H
from lumaretouch_engine import creative_document_host as C


def inventory():
    return {'cmd':'batch','action':'people_targets','request_id':'inventory-1','docs':['target-1']}


@pytest.mark.parametrize('patch',[
    {'action':'commit'},{'cmd':'people'},{'request_id':''},{'docs':[]},
    {'docs':['same','same']},{'docs':['x']*17},{'docs':[1]},
])
def test_inventory_does_not_exempt_arbitrary_commands(patch):
    assert not H.inventory_read_only({**inventory(),**patch})


def test_inventory_exact_envelope():
    assert H.inventory_read_only(inventory())
    assert not H.inventory_read_only({**inventory(),'recipe':{}})
    assert H.inventory_read_only({**inventory(),'docs':['target-'+str(i) for i in range(16)]})


@pytest.mark.parametrize('request',[
    {'cmd':'batch','action':'commit','request_id':'r','module_scope':['lnx.exposure.v1']},
    {'cmd':'batch','action':'commit','request_id':'r','preflight_token':'t','docs':['other']},
    {'cmd':'batch','action':'undo','request_id':'r','batch_id':'b','force':True},
    {'cmd':'batch','action':'preflight','request_id':'r','overwrite':True},
    {'cmd':'batch','action':'preflight'},
])
def test_unreviewed_or_overridden_batch_route_refused(request):
    with pytest.raises(ValueError):H.require_route('batch',request)


@pytest.mark.parametrize('action,extra',[
    ('preflight',{'docs':['target'],'module_scope':['lnx.exposure.v1']}),
    ('commit',{'preflight_token':'existing-token'}),
    ('undo',{'batch_id':'existing-ledger'}),('redo',{'batch_id':'existing-ledger'}),
])
def test_owned_controllers_remain_authoritative(action,extra):
    # A route is not an approval: the controller must still verify tokens,
    # actual module payload, graph/target sources and protected history.
    H.require_route('batch',{'cmd':'batch','action':action,'request_id':'r',**extra})


def test_parked_derived_row_admits_only_reviewed_transfer_route():
    engine=SimpleNamespace(_creative_base=None,_docs=[{'state':{'_creative_base':{'fixture':'route only'}}}])
    C.guard_command(engine,'batch',inventory())
    with pytest.raises(ValueError):
        C.guard_command(engine,'batch',{'cmd':'batch','action':'commit','module_scope':['lnx.exposure.v1']})


def test_unadapted_semantic_and_people_mutations_stay_guarded():
    engine=SimpleNamespace(_creative_base=None,_docs=[{'state':{'_creative_base':{'fixture':'route only'}}}])
    for name in ('semantic_colour','people'):
        with pytest.raises(ValueError):C.guard_command(engine,name,{'cmd':name,'action':'link'})


def test_native_inventory_registration_and_capture_boundary_source_wiring():
    root=Path(__file__).resolve().parents[4]
    native=root/'ui/src-tauri/src'
    api=(native/'batch_api.rs').read_text()
    assert 'pub(crate) fn read_only(command:&Value)->bool' in api
    assert 'fields.len()==4' in api and 'docs.len()<=16' in api
    assert '"people_targets"' in (native/'batch_host.rs').read_text()
    dispatch=(native/'native_dispatch.rs').read_text()
    assert dispatch.index('crate::batch_api::read_only(&cmd)')<dispatch.index('self.source_patch_capture')
    engine=(native/'engine.rs').read_text()
    assert engine.index('crate::batch_api::read_only(&cmd)')<engine.index('crate::sample_library_api::invalidate_captures(self)')


def test_engine_inventory_precedes_capture_invalidation_and_recovery_mutation():
    root=Path(__file__).resolve().parents[4]
    source=root/'engine/src/lumaretouch_engine'
    server=(source/'server.py').read_text()
    dispatch=server[server.index('    def _process_line('):]
    assert dispatch.index('if inventory_read_only(msg):')<dispatch.index("id_capture=self.__dict__.get('_id_background_capture_owner')")
    recovery=(source/'project_recovery_runtime.py').read_text()
    assert recovery.index('if inventory_read_only(message):return')<recovery.index('runtime.tainted = True')


def test_parked_people_candidate_does_not_validate_derived_masks_against_original_path():
    root=Path(__file__).resolve().parents[4]
    source=(root/'engine/src/lumaretouch_engine/full_candidate_render.py').read_text()
    assert 'M.verify_snapshot(snap,path,(h,w))' in source
    assert "M.verify_source(M.check(snap.get('local_masks'))" not in source
