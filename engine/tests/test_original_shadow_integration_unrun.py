"""AUTHORED / UNRUN: shared original-shadow ownership and routing regressions.

Synthetic masks are schema fixtures, not proof of extraction or photo quality.
No fixture was imported, collected or run during source authoring.
"""
from copy import deepcopy
from pathlib import Path

import pytest

from lumaretouch_engine import id_background_state as I
from lumaretouch_engine import id_background_scope as ID
from lumaretouch_engine import original_shadow_state as O
from lumaretouch_engine import spill_removal_scope as SP
from lumaretouch_engine import spill_removal_state as S
from lumaretouch_engine import creative_derived_id_background as D
from lumaretouch_engine import local_mask_state as M


SOURCE = {'sha256': 'a' * 64, 'width': 32, 'height': 24}


def binding(ident, source=SOURCE):
    mask = M.empty()
    mask['source'] = deepcopy(source)
    mask['recipe']['objects'] = [{'id': ident, 'name': ident,
        'enabled': True, 'kind': 'brush', 'operation': 'add', 'opacity': 1.,
        'feather': 0., 'points': [[.5, .5]], 'axes': [[.1, 0.], [0., .1]]}]
    return O.check_binding({'version': 1, 'reviewed': True, 'mask': mask,
                            'recipe_sha256': O.digest(mask)})


def retained():
    value = I.empty(); value['source'] = deepcopy(SOURCE)
    shadow = {**O.neutral(), 'lit_floor': binding('lit'),
              'retention': binding('shadow'), 'uniform_floor_confirmed': True}
    return I.with_original_shadow(value, shadow)


def test_explicit_shadow_upgrade_preserves_legacy_shapes_and_spill():
    legacy = I.empty(); saved = deepcopy(legacy)
    assert I.check(legacy) == saved and 'original_shadow' not in legacy
    v2 = I.with_spill(legacy, {**S.neutral(), 'strength': 73.})
    saved_v2 = deepcopy(v2)
    v3 = I.with_original_shadow(v2, O.neutral())
    assert I.check(v2) == saved_v2 and v3['version'] == I.ORIGINAL_SHADOW_VERSION
    assert I.spill_of(v3)['strength'] == 73.
    assert I.with_spill(v3, S.neutral())['original_shadow'] == O.neutral()


def test_spill_scoped_restore_cannot_downgrade_or_erase_shadow_sibling():
    prior = I.empty(); prior['source'] = deepcopy(SOURCE)
    current = retained()
    current = I.with_spill(current, {**S.neutral(), 'strength': 71.})
    state = {'_id_background': current}
    SP.restore(state, {'_id_background': prior})
    assert state['_id_background']['version'] == I.ORIGINAL_SHADOW_VERSION
    assert I.original_shadow_of(state['_id_background']) == I.original_shadow_of(current)
    assert I.spill_of(state['_id_background']) == S.neutral()


def test_whole_id_cannot_export_another_photos_shadow_samples_even_disabled():
    with pytest.raises(ValueError):
        I.portable(retained())


def test_whole_id_cannot_recompute_target_retained_shadow_without_review():
    state = {'_id_background': retained(), '_id_background_bundle': None}
    before = deepcopy(state)
    proposal = I.portable(I.empty())
    proposal['background']['color'] = [20, 30, 40]
    with pytest.raises(ValueError):
        ID.install(state, {'recipe': proposal})
    assert state == before


def test_dormant_shadow_masks_still_require_exact_effective_source():
    value = retained()
    other = {**SOURCE, 'sha256': 'b' * 64}
    with pytest.raises(ValueError):
        D.validate(value, other)
    altered = deepcopy(value)
    altered['original_shadow']['retention'] = binding('other', other)
    with pytest.raises(ValueError):
        I.check(altered)


def test_source_routes_are_not_disconnected_or_mutating_previews():
    root = Path(__file__).parents[1] / 'src/lumaretouch_engine'
    controller = (root / 'id_background_controller.py').read_text()
    assert 'shadow_controller(self.engine,self.emit).handle(p)' in controller
    host = (root / 'creative_id_background_host.py').read_text()
    assert "'_original_shadow_owner'" in host and 'shadow_envelope(request)' in host
    recovery = (root / 'project_recovery_runtime.py').read_text()
    assert "'id_original_shadow_preview'" in recovery
    assert "'id_original_shadow_paint_source'" in recovery
    assert "'id_original_shadow_paint_source'" in host
    server = (root / 'server.py').read_text()
    assert '"id_original_shadow_preview"' in server
    assert '"id_original_shadow_paint_source"' in server
    export = (root / 'id_background_export.py').read_text()
    assert 'shadow_memory_estimate((h,w),spec.id_background)' in export
