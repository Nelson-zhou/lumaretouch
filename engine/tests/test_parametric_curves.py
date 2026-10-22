"""v3 parametric stage: actual packaged Rust helper and shared recipe paths."""
import copy
import json
from pathlib import Path
import subprocess
import struct
import numpy as np
import pytest
from lumaretouch_engine.ops import curves as C
from lumaretouch_engine.ops import parametric_curves as P


def recipe(values=(0, 0, 0, 0), splits=(.25, .5, .75)):
    spec = C.default_curves()
    spec.update(version=3, luminance_space=C.LUMINANCE_SPACE, luminance=[[0., 0.], [1., 1.]],
                parametric={**P.default_parametric(), **dict(zip(P.NAMES, values)), 'splits': list(splits)})
    return spec


def test_neutral_disabled_and_old_versions_preserve_identity_and_original_objects():
    image = np.array([[[-0., -.2, 2.], [.1, .5, .9]]], np.float32)
    for splits in ((.01, .02, .99), (.97, .98, .99)):
        spec = recipe(splits=splits)
        assert C.is_identity(spec) and C.curves_np(image, spec) is image
        spec['parametric']['shadows'] = 100
        spec['parametric']['enabled'] = False
        assert C.curves_np(image, spec) is image
        spec['parametric']['enabled'] = True
        spec['enabled'] = False
        assert C.curves_np(image, spec) is image
    old = C.default_curves(); old['red'] = [[0, .1], [1, .9]]
    upgraded = recipe(); upgraded['red'] = copy.deepcopy(old['red'])
    assert np.array_equal(C.curves_np(image, old), C.curves_np(image, upgraded))
    assert C.check_curves(old) == old


def test_complete_strict_v3_schema_owns_nested_values():
    spec = recipe(); checked = C.check_curves(spec)
    checked['parametric']['splits'][0] = .1
    assert spec['parametric']['splits'][0] == .25
    for patch in ({'version': 2}, {'algorithm': 'external'}, {'grid': 'uniform'}, {'enabled': 1},
                  {'shadows': True}, {'lights': 101}, {'darks': float('nan')},
                  {'splits': [.2, .2, .8]}, {'lut': [0, 1]}):
        bad = recipe(); bad['parametric'].update(patch)
        with pytest.raises(ValueError): C.check_curves(bad)
    for key in P.default_parametric():
        bad = recipe(); del bad['parametric'][key]
        with pytest.raises(ValueError): C.check_curves(bad)
    bad = recipe(); bad['version'] = 2
    with pytest.raises(ValueError): C.check_curves(bad)
    assert C.check_curves(recipe(splits=(.28, .29, .99)))['version'] == 3


def test_compiler_binary_is_exact_correlated_and_immutable():
    spec = recipe((47, -32, 19, -8), (.01, .02, .99))
    bundle = P.compile_recipe(spec['parametric'], C._compiler_path())
    assert bundle.table.shape == (65537,) and bundle.splits == (.01, .02, .99)
    assert bundle.table[0] == 0 and bundle.table[-1] == 1
    for arr in (bundle.table, bundle.left, bundle.width):
        assert not arr.flags.writeable
        with pytest.raises(ValueError): arr.setflags(write=True)
    raw = subprocess.run([str(C._compiler_path())], input=b'parametric 1 47 -32 19 -8 .01 .02 .99', capture_output=True, check=True).stdout
    for changed in [raw[:-1], raw+b'x', b'BAD!'+raw[4:], raw[:12]+struct.pack('<I', 2)+raw[16:],
                    raw[:40]+struct.pack('<f', float('nan'))+raw[44:]]:
        with pytest.raises(ValueError): P.decode(changed, (.01, .02, .99))
    with pytest.raises(ValueError): P.decode(raw, (.25, .5, .75))
    assert P._compile.cache_info().maxsize == 16


def test_parametric_stage_precedes_existing_points_and_keeps_extended_boundary():
    image = np.repeat(np.array([-1., -0., .25, .5, .75, 1., 2.], np.float32)[:, None], 3, axis=1)
    spec = recipe((100, 0, 0, 0))
    result = C.curves_np(image, spec)
    assert result[2, 0] == np.float32(.328125)
    assert np.array_equal(result[[0, 1, 5, 6]], image[[0, 1, 5, 6]])
    assert np.signbit(result[1, 0])
    spec['master'] = [[0, .1], [1, .9]]
    only_points = C.default_curves(); only_points['master'] = copy.deepcopy(spec['master'])
    assert np.allclose(C.curves_np(image, spec), C.curves_np(result, only_points), atol=1e-7)
    assert not C.is_identity(recipe((1, 0, 0, 0)))


def test_vector_lookup_matches_rust_scalar_preview_values_without_torch():
    for values, splits in [((47, -32, 19, -8), (.25, .5, .75)), ((100, 100, 100, 100), (.01, .02, .03)),
                           ((-100, 100, -100, 100), (.01, .98, .99))]:
        spec = recipe(values, splits)
        image = np.random.default_rng(42).uniform(-.1, 1.1, (23, 31, 3)).astype(np.float32)
        xs=image.reshape(-1)[:64].astype(np.float64)
        request='parametric-reference 1 '+' '.join(repr(float(v)) for v in (*values,*splits,*xs))
        native=subprocess.run([str(C._compiler_path())],input=request,text=True,capture_output=True,timeout=3,check=True)
        reference=np.asarray(json.loads(native.stdout),np.float64)
        scalar=P.evaluate_np(xs,P.compile_recipe(spec['parametric'],C._compiler_path()))
        assert np.max(np.abs(scalar-reference[:,1]))<1e-12
        assert np.max(np.abs(scalar-reference[:,0]))<2e-6



def test_torch_parametric_parity_and_identity():
    torch = pytest.importorskip('torch')
    for values,splits in [((47,-32,19,-8),(.25,.5,.75)),((100,100,100,100),(.01,.02,.03)),((-100,100,-100,100),(.01,.98,.99))]:
        spec=recipe(values,splits);image=np.random.default_rng(42).uniform(-.1,1.1,(23,31,3)).astype(np.float32)
        tensor=torch.from_numpy(image.transpose(2,0,1)[None].copy())
        actual=C.curves_t(tensor,C.tensor_bundles(spec,'cpu',torch.float32)).numpy()[0].transpose(1,2,0)
        assert np.isfinite(actual).all() and np.max(np.abs(actual-C.curves_np(image,spec)))<2e-6
        assert C.curves_t(tensor,C.tensor_bundles(recipe(splits=splits),'cpu',torch.float32)) is tensor


def test_float32_boundaries_match_rust_sampled_reference():
    for values,splits in [((-100,100,100,100),(.01,.02,.03)),((100,-100,100,-100),(.01,.98,.99)),((47,-32,19,-8),(.49,.5,.99))]:
        base=np.asarray([0.,1.,*splits],np.float32)
        xs=np.concatenate([base,np.nextafter(base,np.float32(-np.inf)),np.nextafter(base,np.float32(np.inf)),np.array([.03002960205078125],np.float32)])
        request='parametric-reference 1 '+' '.join(repr(float(v)) for v in (*values,*splits,*xs))
        native=subprocess.run([str(C._compiler_path())],input=request,text=True,capture_output=True,timeout=3,check=True)
        reference=np.asarray(json.loads(native.stdout),np.float64)
        bundle=P.compile_recipe(recipe(values,splits)['parametric'],C._compiler_path())
        result=P.evaluate_np(xs,bundle)
        assert np.max(np.abs(result-reference[:,1]))<2e-6
        assert np.max(np.abs(result-reference[:,0]))<2e-6


def test_mutable_decoder_input_is_snapshotted():
    raw=bytearray(subprocess.run([str(C._compiler_path())],input=b'parametric 1 47 -32 19 -8 .25 .5 .75',capture_output=True,check=True).stdout)
    bundle=P.decode(raw,(.25,.5,.75));before=bundle.table.copy();raw[40:44]=struct.pack('<f',float('nan'))
    assert np.array_equal(bundle.table,before) and not bundle.table.flags.writeable


def test_compiler_failure_does_not_commit_resident_recipe(monkeypatch):
    pytest.importorskip('torch')
    from lumaretouch_engine.vram import make_pipeline
    pipe = make_pipeline('cpu', 64, 64, np.full((64, 64, 3), 64, np.uint8))
    before = copy.deepcopy(pipe.curves_spec)
    monkeypatch.setattr(C, '_compiler_path', lambda: Path('/missing/lrt-curve-compiler'))
    with pytest.raises(RuntimeError): pipe.set_curves(recipe((42, 0, 0, 0)))
    assert pipe.curves_spec == before and not pipe.has_curves()


def test_v3_survives_history_scope_and_export_snapshot_and_blocks_original_fastpath():
    from lumaretouch_engine.server import Engine
    from lumaretouch_engine import scope as S
    from lumaretouch_engine.export_recipe import build_export_spec
    from test_export_per_image_recipe import _batch_snap
    e = Engine('parametric-state'); spec = recipe((10, -20, 30, -40))
    changed = S.apply_modules(e._capture_state(), {S.OP_CURVES: {'recipe': spec}})
    e._apply_state(changed)
    assert e._curves == spec and e._history_capture()['_curves'] == spec
    assert 'RGB/master 曲线（含亮度通道）' in e._master16_blockers(scale=1, sharpen=0)
    snapshot = _batch_snap(); snapshot['curves'] = spec; snapshot['strength'] = 0
    out, skipped = build_export_spec(snapshot, 64, 64, for_document=True)
    assert out.curves == spec and skipped == []


def test_export16_uses_parametric_stage_without_eight_bit_steps():
    pytest.importorskip('torch')
    from lumaretouch_engine.export import export_image16, ExportSpec
    source = np.broadcast_to(np.linspace(0, 65535, 513, dtype=np.uint16)[None, :, None], (64, 513, 3)).copy()
    spec = recipe((24, -10, 15, -20))
    expected = np.rint(np.clip(C.curves_np(source.astype(np.float32)/65535, spec), 0, 1)*65535).astype(np.uint16)
    actual, _ = export_image16(source, ExportSpec(strength=0, curves=spec), device='cpu', tile=256)
    assert np.max(np.abs(actual.astype(np.int32)-expected.astype(np.int32))) <= 2
    assert len(np.unique(actual[0, :, 0])) > 256


def test_render_failure_restores_previous_compiled_objects_without_reallocation(monkeypatch):
    from lumaretouch_engine.server import Engine
    from lumaretouch_engine import server
    class Pipe:
        def __init__(self): self.curves_spec=C.default_curves();self.curves_compiled=object();self.calls=0
        def set_curves(self,spec): self.calls+=1;self.curves_spec=spec;self.curves_compiled=object()
    e=Engine('curve-rollback');e._vram=Pipe();before=(e._vram.curves_spec,e._vram.curves_compiled)
    monkeypatch.setattr(e,'_guard_editable',lambda _kind:None)
    monkeypatch.setattr(e,'_write_current_frame',lambda _kind:(_ for _ in ()).throw(RuntimeError('render failure')))
    events=[];monkeypatch.setattr(server,'emit',events.append)
    assert e._cmd_curves_edit({'action':'set','spec':recipe((10,0,0,0))}) is None
    assert e._vram.curves_spec is before[0] and e._vram.curves_compiled is before[1]
    assert e._vram.calls==1 and C.is_identity(e._curves)
    assert any(v['event']=='error' for v in events)


def test_v3_preset_file_roundtrip_is_lossless(tmp_path):
    from lumaretouch_engine import preset_store as store, scope as S
    spec=recipe((10,-20,30,-40),(.1,.4,.9))
    doc={'schema':S.PRESET_SCHEMA,'id':'parametric-v3','name':'Parametric v3','kind':'color',
         'author':'test','note':'roundtrip','modules':{S.OP_CURVES:{'recipe':spec}}}
    path=store.save(doc,directory=str(tmp_path));loaded=store.load_file(path)
    assert loaded['modules'][S.OP_CURVES]['recipe']==spec


def test_frozen_batch_preserves_v3_source_and_scoped_undo():
    from test_batch_sync_controller import fixture
    from lumaretouch_engine.scope import OP_CURVES
    c,rows,_,events,_,_=fixture()
    for row in rows:row['state']['_curves']=C.default_curves()
    frozen=recipe((10,-20,30,-40));rows[0]['state']['_curves']=copy.deepcopy(frozen)
    c.handle_command({'action':'preflight','docs':[1,2],'module_scope':[OP_CURVES],
                      'conflict_policy':'skip_and_report','request_id':'v3-review'})
    token=events[-1]['preflight_token']
    rows[0]['state']['_curves']['parametric']['shadows']=99;c.versions.advance(rows[0])
    c.handle_command({'action':'commit','preflight_token':token,'request_id':'v3-commit'})
    result=events[-1];assert result['success'] and result['source_changed_since_preflight']
    assert rows[1]['state']['_curves']==frozen and rows[2]['state']['_curves']==frozen
    rows[1]['state']['_exposure']=(4.,0.,0.,0.,0.,0.,0.)
    c.handle_command({'action':'undo','batch_id':result['batch_id']})
    assert C.is_identity(rows[1]['state']['_curves']) and rows[1]['state']['_exposure'][0]==4
