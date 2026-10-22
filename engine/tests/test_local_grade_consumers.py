"""Retained local-grade consumers. Authored statically; execution is deferred.

The raster stub isolates consumer ordering/tiling from Rust's separate LMR2
acceptance suite. It is not evidence that semantic models or LMR2 were executed.
"""
import copy
import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest

from lumaretouch_engine import local_grade_layers as L
from lumaretouch_engine import local_grade_source as Source
from lumaretouch_engine import local_mask_state as M
from lumaretouch_engine import project as P, manual_liquify_state as ML


def groups(path, shape=(20, 32), *, disabled=False):
    h, w = shape
    mask = M.empty()
    mask['source'] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'width': w, 'height': h}
    mask['recipe']['objects'] = [dict(id='selection', name='Selection', enabled=True,
        operation='add', kind='radial', opacity=1., feather=0., center=[.5, .5],
        axes=[[.4, 0], [0, .4]])]
    return L.check({'version': 1, 'layers': [
        dict(id='first', name='First adjustment', enabled=True, grade=[.012, -.13, .15, .7], mask=mask),
        dict(id='second', name='Second adjustment', enabled=not disabled,
             grade=[-.018, .1, -.08, .8], mask=copy.deepcopy(mask))]})


def source(tmp_path):
    path = tmp_path / 'source.bin'
    path.write_bytes(b'independent-source-binding')
    return path


def test_project_v5_roundtrip_keeps_groups_independent_and_owned(tmp_path):
    path = source(tmp_path)
    retained = groups(path)
    retained['layers'][1]['mask']['recipe']['objects'][0]['operation'] = 'intersect'
    state = {'_manual_liquify': ML.empty(), '_grade': [0, 0, 0, 1], '_local_grade_layers': retained,
             '_hist': [{'_manual_liquify': ML.empty(), '_local_grade_layers': copy.deepcopy(retained)}]}
    project = P.new_project('Independent adjustments')
    P.add_doc(project, str(path), state)
    saved = tmp_path / 'local.lrproject.json'
    P.save(project, str(saved))
    restored = P.load(str(saved))
    assert restored['schema_version'] == P.SCHEMA
    value, dropped = P.active_recipe(restored, str(path))
    assert dropped == [] and value['_local_grade_layers'] == retained
    assert value['_hist'][0]['_local_grade_layers'] == retained
    value['_local_grade_layers']['layers'][0]['grade'][0] = 0
    assert value['_hist'][0]['_local_grade_layers']['layers'][0]['grade'][0] == .012


@pytest.mark.parametrize('schema', [P.LEGACY_SCHEMA, P.WB_SCHEMA, P.REPAIR_SCHEMA, P.MASK_SCHEMA])
def test_each_legacy_schema_migrates_without_converting_scalar_grade(tmp_path, schema):
    path = source(tmp_path)
    state = {'_grade': [0, .1, .1, .7], '_grade_scope': 'all',
             '_hist': [{'_grade': [0, 0, 0, 1], '_grade_scope': 'all'}]}
    project = P.new_project('Legacy grade')
    project['schema_version'] = schema
    P.add_doc(project, str(path), state)
    before = copy.deepcopy(project)
    saved = tmp_path / 'legacy.lrproject.json'
    saved.write_text(json.dumps(project))
    restored = P.load(str(saved))
    value, dropped = P.active_recipe(restored, str(path))
    assert dropped == [] and project == before
    assert value['_grade'] == state['_grade']
    assert value['_local_grade_layers'] == L.empty()
    assert value['_hist'][0]['_local_grade_layers'] == L.empty()


@pytest.mark.parametrize('schema', [P.LEGACY_SCHEMA, P.WB_SCHEMA, P.REPAIR_SCHEMA, P.MASK_SCHEMA])
def test_pretending_groups_are_pre_v5_is_rejected(tmp_path, schema):
    path = source(tmp_path)
    project = P.new_project('No silent downgrade')
    P.add_doc(project, str(path), {'_manual_liquify': ML.empty(), '_local_grade_layers': groups(path)})
    project['schema_version'] = schema
    with pytest.raises(P.ProjectError, match='pre-v5'):
        P.validate(project)


@pytest.mark.parametrize('location', ['live', 'inactive', 'history'])
@pytest.mark.parametrize('mutation', ['null', 'version', 'missing_mask', 'grade_nan', 'duplicate_id'])
def test_corrupt_groups_anywhere_reject_before_save(tmp_path, location, mutation):
    path = source(tmp_path)
    project = P.new_project('Fail closed')
    P.add_doc(project, str(path), {'_manual_liquify': ML.empty(), '_local_grade_layers': groups(path)}, version_id='live')
    root = project['docs'][0]['versions'][0]['recipe']
    if location == 'inactive':
        inactive = copy.deepcopy(project['docs'][0]['versions'][0])
        inactive['id'] = 'inactive'
        project['docs'][0]['versions'].append(inactive)
        root = inactive['recipe']
    elif location == 'history':
        root['_hist'] = [copy.deepcopy(root)]
        root = root['_hist'][0]
    value = root['_local_grade_layers']
    if mutation == 'null': root['_local_grade_layers'] = None
    elif mutation == 'version': value['version'] = 999
    elif mutation == 'missing_mask': del value['layers'][0]['mask']
    elif mutation == 'grade_nan': value['layers'][0]['grade'][0] = float('nan')
    elif mutation == 'duplicate_id': value['layers'][1]['id'] = value['layers'][0]['id']
    with pytest.raises(P.ProjectError):
        P.validate(project)


def test_decode_guard_rejects_dimensions_hash_and_decode_race(tmp_path):
    path = source(tmp_path)
    snap = {'local_grade_groups': groups(path)}
    stamp = M.file_stamp(str(path))
    Source.check_export_decode(snap, str(path), stamp, (20, 32))
    assert snap['local_grade_source_stamp'] == list(stamp)
    assert snap['local_mask_source_path'] == str(path)
    with pytest.raises(ValueError, match='dimensions'):
        Source.check_export_decode(snap, str(path), stamp, (32, 20))
    path.write_bytes(b'replaced-source-binding')
    with pytest.raises(ValueError, match='decoding'):
        Source.check_export_decode(snap, str(path), stamp, (20, 32))
    with pytest.raises(ValueError, match='content'):
        Source.verify_snapshot(snap, str(path), (20, 32))


def test_fields_require_every_enabled_group_in_exact_order(tmp_path):
    from lumaretouch_engine.local_grade_stage import check_fields
    value = groups(source(tmp_path))
    fields = [{'id': l['id'], 'grade': l['grade'], 'weight': np.zeros((20, 32), np.uint8)}
              for l in value['layers']]
    check_fields(fields, (20, 32), groups=value)
    for bad in (fields[:1], fields[::-1], [dict(fields[0], weight=None), fields[1]],
                [dict(fields[0], weight=np.zeros((20, 32), np.float32)), fields[1]]):
        with pytest.raises(ValueError): check_fields(bad, (20, 32), groups=value)


def test_stage_is_float_sequential_owned_and_counts_all_resident_bytes():
    torch = pytest.importorskip('torch')
    from lumaretouch_engine.local_grade_stage import LocalGradeStage
    from lumaretouch_engine.ops.grade import grade_t
    from lumaretouch_engine.ops.guided import mix_masked
    pixels = torch.tensor([.721234, .461234, .301234], dtype=torch.float32).reshape(1, 3, 1, 1).expand(1, 3, 5, 7).clone()
    stage = LocalGradeStage(torch.device('cpu'), (5, 7))
    assert stage.apply(pixels, lambda x: x) is pixels
    masks = [np.full((5, 7), 128, np.uint8), np.full((5, 7), 192, np.uint8)]
    values = [[.012, -.13, .15, .7], [-.018, .1, -.08, .8]]
    fields = [dict(id=str(i), grade=v, weight=w) for i, (v, w) in enumerate(zip(values, masks))]
    stage.set(fields)
    assert stage.resident_bytes() == 70
    expected = pixels
    for values_i, mask in zip(values, masks):
        expected = mix_masked(expected, grade_t(expected, *values_i[:3], amount=values_i[3]),
                              1., torch.tensor(mask, dtype=torch.float32)[None, None] / 255.)
    masks[0][:] = 0  # Mutation outside the stage must not alter owned weights.
    got = stage.apply(pixels, lambda x: x)
    assert torch.equal(got, expected) and got.dtype == torch.float32
    assert not torch.equal(got, torch.round(got * 255) / 255)
    stage.set([], reason='Required mask unavailable')
    assert stage.apply(pixels, lambda x: x) is pixels and stage.resident_bytes() == 0


@pytest.mark.parametrize('precise', [False, True])
def test_pipeline_uses_image_warp_before_sequential_grade_not_after(precise):
    torch = pytest.importorskip('torch')
    from lumaretouch_engine.vram import PreviewPipeline
    from lumaretouch_engine.ops.grade import grade_t
    from lumaretouch_engine.ops.guided import mix_masked
    pipe = PreviewPipeline('cpu', 32, 20, high_precision_warp=precise)
    pixels = np.empty((20, 32, 3), np.float32)
    pixels[:] = [.72, .46, .30]
    pixels[:, 16:] = [.52, .32, .20]
    pipe.load_rgb_f32(pixels)
    delta = torch.zeros((1, 20, 32, 2))
    delta[..., 0] = 1.25
    pipe.adopt_deform_field(delta)
    mask = np.zeros((20, 32), np.uint8)
    mask[:, 13:19] = 255
    grade = [0., .1, .15, .8]
    pipe.local_grade_layers.set([dict(id='group', grade=grade, weight=mask)])
    moved = pipe.apply_deform(pipe.src_f32)
    moved_mask = pipe.align_source_grade_mask(torch.tensor(mask, dtype=torch.float32)[None, None] / 255.)
    expected = mix_masked(moved, grade_t(moved, *grade[:3], amount=grade[3]), 1., moved_mask)
    actual = pipe.retouch(0, radius=0, texture_radius=0)
    assert torch.equal(actual, expected)
    assert pipe.grade_resident_bytes() == mask.nbytes


@pytest.mark.parametrize('bits', [8, 16])
def test_tiled_export_and_inspection_share_all_groups_without_rgb8_roundtrip(tmp_path, monkeypatch, bits):
    torch = pytest.importorskip('torch')
    from lumaretouch_engine import export as E
    from lumaretouch_engine import local_grade_runtime as Runtime
    from lumaretouch_engine.full_quality import render_inspection_roi
    h, w = 270, 520
    path = source(tmp_path)
    retained = groups(path, (h, w))
    mask1 = np.tile(np.arange(w, dtype=np.uint16) % 256, (h, 1)).astype(np.uint8)
    mask2 = np.flip(mask1, axis=1).copy()
    fields = [dict(id=layer['id'], grade=layer['grade'], weight=mask)
              for layer, mask in zip(retained['layers'], [mask1, mask2])]
    monkeypatch.setattr(Runtime, 'rasters', lambda *args, **kw: fields)
    delta = torch.zeros((1, h, w, 2)); delta[..., 0] = 1.25
    monkeypatch.setattr(E, 'composed_delta', lambda *args: (delta, 1.25))
    rgb = np.empty((h, w, 3), np.uint16 if bits == 16 else np.uint8)
    rgb[:] = [47123, 30123, 20123] if bits == 16 else [183, 117, 78]
    def spec():
        return E.ExportSpec(strength=0, radius=0, texture_radius=0, deform_amounts={'slim_face': .2},
                            local_grade_groups=retained, local_mask_source_path=str(path))
    render = E.export_image16 if bits == 16 else E.export_image
    tiled, stats = render(rgb, spec(), device='cpu', tile=256)
    whole, _ = render(rgb, spec(), device='cpu', tile=1024)
    assert np.abs(tiled.astype(np.int32)-whole.astype(np.int32)).max() <= 1
    assert stats['local_grade_mask_cpu_bytes'] == 2*h*w and stats['local_grade_groups'] == 2
    decoded = SimpleNamespace(rgb=rgb, w=w, h=h, src_w=w, src_h=h, src_bits=bits,
        draft_used=False, raw=None, source_icc=None, fmt='TIFF' if bits == 16 else 'PNG', notes=[])
    roi = (250, 5, 24, 20)
    inspected = render_inspection_roi(decoded, spec(), roi, max_source_pixels=h*w,
        max_display_pixels=1000, device='cpu', tile=256)
    expected = tiled[5:25, 250:274]
    if bits == 16: expected = ((expected.astype(np.uint32)+128)//257).astype(np.uint8)
    np.testing.assert_array_equal(inspected.rgba[..., :3], expected)


def test_export_rejects_missing_enabled_raster_even_if_other_groups_are_available(tmp_path, monkeypatch):
    from lumaretouch_engine import export as E
    from lumaretouch_engine import local_grade_runtime as Runtime
    path = source(tmp_path)
    retained = groups(path)
    fields = [dict(id='first', grade=retained['layers'][0]['grade'], weight=np.zeros((20, 32), np.uint8))]
    monkeypatch.setattr(Runtime, 'rasters', lambda *args, **kw: fields)
    with pytest.raises(ValueError, match='missing, stale or reordered'):
        E.export_image(np.zeros((20, 32, 3), np.uint8), E.ExportSpec(strength=0,
            local_grade_groups=retained, local_mask_source_path=str(path)), device='cpu', tile=256)
