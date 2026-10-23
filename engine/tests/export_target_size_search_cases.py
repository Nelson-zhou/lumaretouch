"""AUTHORED / UNRUN. Qoder may run explicitly; no claim of executed coverage."""
import pytest
from lumaretouch_engine.export_target_size_policy import TargetSize, parse_target_size
from lumaretouch_engine.export_target_size_search import search, TargetSizeCancelled, EncodedBudgetExceeded


def policy(**kwargs):
    return TargetSize(**dict(target_bytes=1000, tolerance_bytes=0,
                             min_quality=1, max_quality=4, max_attempts=4, **kwargs))


def test_nonmonotonic_search_does_not_discard_candidate():
    sizes = {4: 1100, 3: 800, 2: 1000, 1: 900}
    result = search(policy(), lambda q: b'x'*sizes[q])
    assert result.quality == 2 and result.status == 'matched'
    assert [a['quality'] for a in result.attempts] == [4, 3, 2]


def test_tie_chooses_higher_quality_and_infeasible_is_explicit():
    result = search(policy(), lambda q: b'x'*(900 if q > 2 else 1100))
    assert result.status == 'unreachable' and result.exhaustive
    assert result.quality == 4


def test_unvisited_qualities_are_not_called_unreachable():
    p = TargetSize(1000, 0, min_quality=1, max_quality=4, max_attempts=1)
    result = search(p, lambda q: b'x'*1200)
    assert result.status == 'budget_exhausted' and not result.exhaustive


def test_metadata_overhead_counts_as_bytes():
    p = TargetSize(1000, 0, min_quality=1, max_quality=2)
    result = search(p, lambda q: b'ICC/EXIF'*150 + b'x'*q)
    assert result.status == 'unreachable' and len(result.data) > 1000


def test_cancel_after_attempt_discards_result():
    cancelled = [False]
    def encode(q):
        cancelled[0] = True
        return b'x'*1000
    with pytest.raises(TargetSizeCancelled):
        search(policy(), encode, cancelled=lambda: cancelled[0])


def test_soft_deadline_stops_before_next_attempt():
    now = [0.0]
    def encode(q):
        now[0] = 60.0
        return b'x'*1200
    result = search(policy(), encode, clock=lambda: now[0])
    assert len(result.attempts) == 1 and result.status == 'budget_exhausted'


def test_buffer_rejection_not_infeasibility_proof():
    def encode(q):
        raise EncodedBudgetExceeded('bounded')
    result = search(policy(), encode)
    assert result.status == 'encoded_budget_exhausted' and not result.exhaustive
    assert result.data is None


@pytest.mark.parametrize('value', [0, -1, 1.2, True, '1000', float('nan'), float('inf')])
def test_invalid_targets(value):
    with pytest.raises(ValueError):
        TargetSize(value, 0).check()


@pytest.mark.parametrize('fmt,bits', [('png', 8), ('tiff', 16), ('webp', 8), ('jpg', 16)])
def test_no_silent_format_or_depth_conversion(fmt, bits):
    with pytest.raises(ValueError):
        parse_target_size({'target_bytes': 1000, 'tolerance_bytes': 0}, format=fmt, bit_depth=bits)


def test_tolerance_edges_are_inclusive():
    result = search(TargetSize(1000, 50, min_quality=100), lambda q: b'x'*1050)
    assert result.status == 'matched'
