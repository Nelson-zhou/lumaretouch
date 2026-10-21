import numpy as np
import pytest
from lumaretouch_engine.render_snapshot import SnapshotTransaction, SnapshotError, own_render_inputs


def test_chunked_copy_is_bounded_and_matches_reference_for_strides(monkeypatch):
    a = np.arange(120, dtype=np.float64).reshape(10, 12)[:, ::-1]
    source = {'a': a, 'nested': [a, {'n': 3}]}
    expected = own_render_inputs(source, max_asset_bytes=2*a.nbytes)
    calls = []
    original = np.copyto
    def copying(destination, chunk):
        calls.append(chunk.nbytes)
        assert chunk.nbytes <= 40
        return original(destination, chunk)
    monkeypatch.setattr(np, 'copyto', copying)
    tx = SnapshotTransaction(source, max_asset_bytes=2*a.nbytes)
    assert tx.copied_bytes == 0 and calls == []
    with pytest.raises(SnapshotError):
        tx.take_result()
    while not tx.complete:
        before = tx.copied_bytes
        tx.advance(40)
        assert tx.copied_bytes-before <= 40
    result = tx.take_result()
    assert result.asset_bytes == tx.copied_bytes == 2*a.nbytes
    np.testing.assert_array_equal(result.value['a'], expected.value['a'])
    np.testing.assert_array_equal(result.value['nested'][0], a)
    assert not np.shares_memory(a, result.value['a'])
    assert not result.value['a'].flags.writeable and a.flags.writeable
    with pytest.raises(SnapshotError):
        tx.take_result()


def test_cancel_before_mutation_prevents_mixed_recipe_publication():
    a = np.arange(100, dtype=np.uint8)
    tx = SnapshotTransaction({'a': a}, max_asset_bytes=100)
    tx.advance(10)
    tx.cancel()  # command executor must do this BEFORE its edit
    a[:] = 9
    with pytest.raises(SnapshotError):
        tx.advance(10)
    with pytest.raises(SnapshotError):
        tx.take_result()
    assert a.flags.writeable and (a == 9).all()


def test_budget_rejection_precedes_destination_reservation(monkeypatch):
    a = np.ones(20, np.uint8)
    def forbidden(*args, **kwargs):
        raise AssertionError('reserved destination before admission')
    monkeypatch.setattr(np, 'empty', forbidden)
    with pytest.raises(SnapshotError, match='budget'):
        SnapshotTransaction({'a': a}, max_asset_bytes=19)


def test_empty_assets_and_scalar_metadata_complete_without_copy():
    tx = SnapshotTransaction({'empty': np.empty(0, np.float32), 'value': 3}, max_asset_bytes=0)
    assert tx.complete and tx.copied_bytes == 0
    assert tx.take_result().value['value'] == 3


def test_failed_copy_cancels_transaction_without_modifying_source(monkeypatch):
    a = np.ones(20, np.uint8)
    tx = SnapshotTransaction({'a': a}, max_asset_bytes=20)
    def fail(*args):
        raise MemoryError('injected')
    monkeypatch.setattr(np, 'copyto', fail)
    with pytest.raises(MemoryError):
        tx.advance(10)
    assert not tx.complete and a.flags.writeable and (a == 1).all()
    with pytest.raises(SnapshotError):
        tx.take_result()


def test_tick_smaller_than_element_refuses_instead_of_livelock():
    tx = SnapshotTransaction({'a': np.ones(2, np.float64)}, max_asset_bytes=16)
    with pytest.raises(SnapshotError, match='smaller'):
        tx.advance(1)
    assert not tx.complete


def test_second_reservation_failure_cancels_private_transaction(monkeypatch):
    events = []
    class Observed(SnapshotTransaction):
        def cancel(self):
            super().cancel()
            events.append((self._cancelled, len(self._copies), self._staged))
    original = np.empty
    calls = []
    def reserve(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise MemoryError('second reservation failed')
        return original(*args, **kwargs)
    monkeypatch.setattr(np, 'empty', reserve)
    with pytest.raises(MemoryError):
        Observed({'a': np.ones(4, np.uint8), 'b': np.ones(4, np.uint8)}, max_asset_bytes=8)
    assert events == [(True, 0, None)]


def test_mixed_elements_zero_dim_and_transpose_preserve_values():
    source = {'u': np.ones(3, np.uint8), 'f': np.arange(12, dtype='>f8').reshape(3, 4).T,
              'scalar': np.array(4., np.float64)}
    tx = SnapshotTransaction(source, max_asset_bytes=1000)
    while not tx.complete:
        before = tx.copied_bytes
        tx.advance(11)
        assert tx.copied_bytes-before <= 11
    result = tx.take_result()
    for k in source:
        np.testing.assert_array_equal(source[k], result.value[k])
        assert source[k].dtype == result.value[k].dtype


def test_cancel_completed_before_take_and_cancel_twice():
    tx = SnapshotTransaction({'a': np.ones(4, np.uint8)}, max_asset_bytes=4)
    tx.advance(4)
    assert tx.complete
    tx.cancel(); tx.cancel()
    with pytest.raises(SnapshotError):
        tx.take_result()
