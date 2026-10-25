# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN native admission and parity fixtures.

The real-native fixture skips an absent library, never substitutes Python.
A skip is not acceptance. No library was built or loaded while authoring.
"""
from pathlib import Path
import pytest
from lumaretouch_engine import portrait_crop_native as N
from lumaretouch_engine import portrait_crop_planner as P


def sample():
    return ({'version': 1, 'crown': [40., 28.5], 'chin': [40., 60.5], 'face_center': [43., 44.5]},
            {'version': 1, 'aspect_ratio': 65/64, 'headroom_fraction': .125,
             'head_fraction': .5, 'horizontal_position': .5})


def test_unavailable_capability_without_build_or_fallback(monkeypatch):
    def absent(): raise RuntimeError('Not installed in protocol fixture')
    monkeypatch.setattr(N, 'native', absent)
    assert N.capability() == {'version': 1, 'backend': 'rust-portrait-crop-v1', 'available': False,
        'abi': None, 'capabilities': 0, 'reason': 'Not installed in protocol fixture'}
    with pytest.raises(RuntimeError, match='Not installed'): N.solve(128, 128, *sample())


def test_loader_requires_symbols_without_compilation(monkeypatch):
    N.native.cache_clear()
    monkeypatch.setattr(N.Path, 'is_file', lambda self: True)
    monkeypatch.setattr(N.C, 'CDLL', lambda path: object())
    try:
        with pytest.raises(RuntimeError, match='version-1 contract'): N.native()
    finally:
        N.native.cache_clear()


@pytest.fixture
def real_core():
    path = Path(N.__file__).parent / 'bin' / 'liblrt_portrait_crop.so'
    if not path.is_file():
        pytest.skip('Portrait crop Rust library absent; numerical parity remains UNRUN')
    N.native.cache_clear()
    return N.native()  # Installed ABI errors fail, never skip.


def test_installed_rust_matches_reference_and_achieved_rounding(real_core):
    anchors, rules = sample()
    actual = P.plan(128, 128, anchors, rules)
    reference = P.reference_plan(128, 128, anchors, rules)
    assert actual['backend'] == 'rust-portrait-crop-v1'
    assert reference['backend'] == 'python-reference-unrun'
    assert {k: v for k, v in actual.items() if k != 'backend'} == {
        k: v for k, v in reference.items() if k != 'backend'}
    assert actual['pixel_bounds'] == [10, 20, 76, 84]
    assert actual['requested']['aspect_ratio'] != actual['achieved']['aspect_ratio']


def test_installed_rust_failure_is_transactional(real_core):
    anchors = (N.C.c_double * 6)(500, 100, 500, 700, 500, 400)
    rules = (N.C.c_double * 4)(2, .1, .6, .5)
    out = (N.C.c_double * N.RESULT_LENGTH)(*([73.25] * N.RESULT_LENGTH))
    assert real_core.lrt_portrait_crop_plan_v1(1000, 1000, anchors, 6, rules, 4, out, N.RESULT_LENGTH) == 3
    assert list(out) == [73.25] * N.RESULT_LENGTH
