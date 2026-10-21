"""Ownership tests: no live aliases and budget rejection before array copies."""
import numpy as np
import pytest
from lumaretouch_engine.render_snapshot import own_render_inputs, SnapshotError
from lumaretouch_engine.vram import RepairOp, LightOp
from lumaretouch_engine.face import FacePrecompute
from lumaretouch_engine.ops.lut import bake


def test_array_budget_rejects_before_any_copy(monkeypatch):
    a = np.zeros((8, 9), np.uint8)
    def forbidden(*args, **kwargs):
        raise AssertionError('copy before admission')
    monkeypatch.setattr(np, 'array', forbidden)
    with pytest.raises(SnapshotError, match='asset budget'):
        own_render_inputs({'a': a}, max_asset_bytes=a.nbytes - 1)
    assert a.flags.writeable


def test_shared_weights_are_counted_per_actual_copy():
    a = np.ones((8, 9), np.uint8)
    result = own_render_inputs({'ops': [LightOp(1, a), LightOp(2, a)]}, max_asset_bytes=2*a.nbytes)
    assert result.asset_bytes == 2*a.nbytes and result.array_count == 2
    first, second = result.value['ops']
    assert not np.shares_memory(first.weight, a)
    assert not np.shares_memory(first.weight, second.weight)
    a[:] = 8
    assert (first.weight == 1).all() and not first.weight.flags.writeable
    assert a.flags.writeable


def test_live_nested_records_lut_and_face_assets_cannot_change_snapshot():
    weight = np.ones((8, 9), np.uint8)
    points = np.zeros((478, 3), np.float32)
    mask = np.full((8, 9), .5, np.float32)
    face = FacePrecompute(points, {'skin': mask}, 'fixture', 0., 0., all_landmarks=[points])
    lut = bake(lambda x: x*.8, 17)
    op = RepairOp(1, weight)
    source = {'repair': [op], 'face': face, 'lut': lut,
              'bg': {'matte': weight, 'color': [.1, .2, .3]}}
    result = own_render_inputs(source, max_asset_bytes=1000000)
    op.params['grow'] = 999
    points[:] = 1; mask[:] = 0; weight[:] = 0; lut.grid[:] = 0
    source['bg']['color'][0] = .9
    owned = result.value
    assert owned['repair'][0].params.get('grow') != 999
    assert not owned['face'].landmarks.any()
    assert (owned['face'].masks['skin'] == .5).all()
    assert owned['lut'].grid.max() > 0
    assert owned['bg']['color'][0] == .1
    assert (owned['bg']['matte'] == 1).all()


def test_strided_array_is_owned_and_contiguous():
    source = np.arange(24, dtype=np.float64).reshape(4, 6)[:, ::-1]
    out = own_render_inputs({'a': source}, max_asset_bytes=source.nbytes).value['a']
    np.testing.assert_array_equal(out, source)
    assert out.flags.c_contiguous and not np.shares_memory(out, source)


@pytest.mark.parametrize('value', [np.array([object()]), np.array([True]),
    np.array([(1,)], dtype=[('field', 'i4')]), np.ma.array([1]), object()])
def test_unknown_objects_and_non_numeric_arrays_are_refused(value):
    with pytest.raises(SnapshotError):
        own_render_inputs({'asset': value}, max_asset_bytes=10000)


def test_node_text_cycle_and_scalar_guards():
    for value, options in [({'a': [1]*10}, {'max_nodes': 3}),
                           ({'name': 'long'}, {'max_string_bytes': 2}),
                           ({'bad': float('nan')}, {})]:
        with pytest.raises(SnapshotError):
            own_render_inputs(value, max_asset_bytes=10000, **options)
    cycle = {}; cycle['self'] = cycle
    with pytest.raises(SnapshotError, match='Cyclic'):
        own_render_inputs(cycle, max_asset_bytes=10000)


def test_deep_containers_are_rejected_before_python_recursion_limit():
    nested = {}
    root = nested
    for _ in range(150):
        child = {}
        nested['child'] = child
        nested = child
    with pytest.raises(SnapshotError, match='depth'):
        own_render_inputs(root, max_asset_bytes=10000)


def test_numeric_dtype_metadata_cannot_smuggle_mutable_live_aliases():
    metadata = {'mutable': []}
    array = np.zeros(4, dtype=np.dtype('float32', metadata=metadata))
    with pytest.raises(SnapshotError):
        own_render_inputs({'a': array}, max_asset_bytes=10000)


def test_unknown_record_attributes_are_not_silently_dropped():
    op = LightOp(1, np.zeros((2, 2), np.uint8))
    op.unregistered_asset = object()
    with pytest.raises(SnapshotError, match='record fields'):
        own_render_inputs({'op': op}, max_asset_bytes=10000)


def test_text_budget_counts_utf8_bytes_not_only_characters():
    with pytest.raises(SnapshotError, match='text budget'):
        own_render_inputs({'a': '图'*8}, max_asset_bytes=0, max_string_bytes=10)


def test_failed_copy_does_not_mutate_live_arrays(monkeypatch):
    a = np.ones(4, np.uint8)
    b = np.ones(4, np.uint8)
    original = np.array
    calls = []
    def copying(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise MemoryError('injected allocation failure')
        return original(*args, **kwargs)
    monkeypatch.setattr(np, 'array', copying)
    with pytest.raises(MemoryError):
        own_render_inputs({'a': a, 'b': b}, max_asset_bytes=8)
    assert a.flags.writeable and b.flags.writeable
    assert (a == 1).all() and (b == 1).all()


def test_memmap_is_rejected_without_changing_backing_file(tmp_path):
    path = tmp_path / 'asset.bin'
    a = np.memmap(path, dtype='uint8', mode='w+', shape=(4,))
    a[:] = [1, 2, 3, 4]; a.flush()
    before = path.read_bytes()
    with pytest.raises(SnapshotError):
        own_render_inputs({'a': a}, max_asset_bytes=100)
    assert path.read_bytes() == before
    del a


def test_selected_face_and_metadata_are_preserved_without_aliases():
    a = np.zeros((478, 3), np.float32)
    b = np.ones((478, 3), np.float32)
    face = FacePrecompute(b, {}, 'fixture', 1., 2., face_box=(.1, .2, .3, .4),
                          num_faces=2, all_landmarks=[a, b], face_index=1,
                          manual=(1,), notes=['selected second face'])
    owned = own_render_inputs({'face': face}, max_asset_bytes=100000).value['face']
    b[:] = 0
    assert owned.face_index == 1 and owned.num_faces == 2 and owned.manual == (1,)
    assert owned.face_box == (.1, .2, .3, .4)
    assert owned.notes == ['selected second face']
    assert owned.landmarks.min() == 1 and owned.all_landmarks[1].min() == 1


def test_invalid_unicode_metadata_has_snapshot_error():
    with pytest.raises(SnapshotError, match='UTF-8'):
        own_render_inputs({'text': chr(0xd800)}, max_asset_bytes=0)
