"""Authored UNRUN regression tests; local execution belongs to Qoder."""
from dataclasses import replace
import pytest
from lumaretouch_engine.grading_prefix_cache import GradingPrefixCache, PrefixKey


class Tensor:
    shape = (1, 3, 2, 2)
    device = 'cpu'
    dtype = 'torch.float32'

    def __init__(self, value=1):
        self.value = value

    def numel(self): return 12
    def element_size(self): return 4
    def detach(self): return self
    def clone(self): return Tensor(self.value)


def key(cache):
    return PrefixKey('doc', 1, ('source',), cache.generation, (1, 3, 2, 2),
                     'cpu', 'torch.float32', 'test-space', 'test-domain', b'all-upstream')


def test_disabled_by_default():
    cache = GradingPrefixCache()
    for _ in range(2): cache.resolve(key(cache), Tensor, lambda: True)
    assert cache.prefix_builds == 2 and cache.cache_hits == 0
    assert cache.cache_bytes == 0


def test_cached_prefix_is_private_from_in_place_suffix():
    cache = GradingPrefixCache(); cache.enabled = True
    first = cache.resolve(key(cache), Tensor, lambda: True)
    first.value = 99
    second = cache.resolve(key(cache), Tensor, lambda: True)
    assert second.value == 1
    second.value = -9
    assert cache.resolve(key(cache), Tensor, lambda: True).value == 1
    assert cache.prefix_builds == 1 and cache.cache_hits == 2
    assert cache.cache_bytes == 48


@pytest.mark.parametrize('field,value', [
    ('document', 'other'), ('revision', 2), ('source', ('reload',)),
    ('shape', (1, 3, 4, 4)), ('device', 'cuda:0'), ('dtype', 'torch.float16'),
    ('colour_space', 'other'), ('domain', 'other'), ('upstream', b'changed'),
])
def test_context_changes_never_hit(field, value):
    cache = GradingPrefixCache(); cache.enabled = True
    original = key(cache)
    cache.resolve(original, Tensor, lambda: True)
    cache.resolve(replace(original, **{field: value}), Tensor, lambda: True)
    assert cache.cache_hits == 0 and cache.prefix_builds == 2


def test_cancel_or_invalidation_during_build_never_stores():
    cache = GradingPrefixCache(); cache.enabled = True
    def build():
        cache.invalidate()
        return Tensor()
    cache.resolve(key(cache), build, lambda: True)
    assert cache.cache_bytes == 0
    cache.resolve(key(cache), Tensor, lambda: False)
    assert cache.cache_bytes == 0


def test_failure_never_stores_partial_prefix():
    cache = GradingPrefixCache(); cache.enabled = True
    def build(): raise InterruptedError('cancelled')
    with pytest.raises(InterruptedError): cache.resolve(key(cache), build, lambda: True)
    assert cache.cache_bytes == 0


def test_over_budget_uses_full_result_without_retaining():
    cache = GradingPrefixCache(47); cache.enabled = True
    assert cache.resolve(key(cache), Tensor, lambda: True).value == 1
    assert cache.cache_bytes == 0 and cache.cache_hits == 0


def test_generation_changes_are_distinct_from_slider_settings():
    cache = GradingPrefixCache(); cache.enabled = True
    baseline = key(cache)
    cache.resolve(baseline, Tensor, lambda: True)
    cache.resolve(baseline, Tensor, lambda: True)
    cache.invalidate()
    assert key(cache).generation != baseline.generation
    cache.resolve(key(cache), Tensor, lambda: True)
    assert cache.prefix_builds == 2 and cache.cache_hits == 1


def test_snapshot_clone_failure_falls_back_without_quality_change():
    class NoClone(Tensor):
        def clone(self): raise MemoryError('snapshot allocation')
    cache = GradingPrefixCache(); cache.enabled = True
    out = cache.resolve(key(cache), NoClone, lambda: True)
    assert out.value == 1 and cache.cache_bytes == 0


def test_context_changes_during_snapshot_clone_do_not_store():
    cache = GradingPrefixCache(); cache.enabled = True
    class InvalidateClone(Tensor):
        def clone(self):
            cache.invalidate()
            return Tensor()
    cache.resolve(key(cache), InvalidateClone, lambda: True)
    assert cache.cache_bytes == 0


def test_default_off_context_does_not_inspect_runtime_or_call_provider():
    from types import SimpleNamespace
    from lumaretouch_engine.grading_prefix_cache import preview_context
    def forbidden(): raise AssertionError('provider called while disabled')
    engine = SimpleNamespace(_vram=SimpleNamespace(grading_prefix_cache=GradingPrefixCache()),
                             _grading_prefix_audited_context=forbidden)
    assert preview_context(engine, 'colour_grading_preview', False) is None


def test_enabled_without_audited_provider_still_falls_back():
    from types import SimpleNamespace
    from lumaretouch_engine.grading_prefix_cache import preview_context
    cache = GradingPrefixCache(); cache.enabled = True
    engine = SimpleNamespace(_vram=SimpleNamespace(grading_prefix_cache=cache))
    assert preview_context(engine, 'colour_grading_preview', False) is None


def test_service_slider_epoch_does_not_evict_baseline():
    from types import SimpleNamespace
    from lumaretouch_engine.colour_grading_service import Service
    cache = GradingPrefixCache()
    class Owner:
        ticket = None
        host = SimpleNamespace(engine=SimpleNamespace(_vram=SimpleNamespace(grading_prefix_cache=cache)))
        def invalidate(self): pass
    service = Service(); service.owner = Owner()
    for rid in ('a', 'b'):
        service.ingress('{"cmd":"colour_grading","action":"preview","request_id":"' + rid + '"}')
    assert cache.generation == 0
    service.ingress('{"cmd":"compare","on":true}')
    assert cache.generation == 1
    service.stop()
    assert cache.generation == 2
