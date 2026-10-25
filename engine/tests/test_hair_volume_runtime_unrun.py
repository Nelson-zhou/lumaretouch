# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN admission fixtures; mocked geometry is not numeric/visual QA."""
from copy import deepcopy
from unittest import mock
import numpy as np
import pytest
from lumaretouch_engine import hair_volume_runtime as R, hair_volume_state as S, hair_volume_support as A
from lumaretouch_engine.hair_volume_field import binding_digest
from test_hair_volume_contract_unrun import fixture


class AdmissionField:
    """Only an admission-test stand-in; never retained as real product evidence."""
    operation_id = S.OPERATION_ID

    def __init__(self, record, recipe, shape):
        self.record = deepcopy(record); self.source = record['source']; self.recipe = recipe
        self.face_instance_id = record['face_ref']['face_instance_id']
        self.input_binding_sha256 = binding_digest(record, recipe); self.shape = tuple(shape)
        self.regions = [part for part, amount in zip(record['row']['regions'].values(), S.amounts(recipe)) if amount]

    def envelopes(self):
        h, w = self.shape
        return tuple((np.array([p['x'][0], p['y'][0]])*[w-1, h-1]-10,
                      np.array([p['x'][3], p['y'][3]])*[w-1, h-1]+10) for p in self.regions)

    def resident_bytes(self):
        return 512


def call(people, bank, source, evidence, recipe, **kwargs):
    return R.prepare_fields(people, source['sha256'], (1001, 1001), recipes={'owner': recipe},
                            support_assets=bank, hair_evidence=evidence, source_frame=source,
                            byte_budget=1_048_576, **kwargs)


def test_clear_current_photo_passes_admission_and_missing_or_stale_fields_fail():
    people, bank, source, evidence, _ = fixture()
    recipe = S.neutral(); recipe['crown']['amount'] = 1
    with mock.patch.object(R, 'HairVolumeField', AdmissionField):
        fields = call(people, bank, source, evidence, recipe)
    R.require_prepared(people, source['sha256'], fields, recipes={'owner': recipe}, support_assets=bank, source_frame=source)
    with pytest.raises(ValueError):
        R.require_prepared(people, source['sha256'], (), recipes={'owner': recipe}, support_assets=bank, source_frame=source)
    changed = deepcopy(recipe); changed['crown']['amount'] = -.5
    with pytest.raises(ValueError):
        R.require_prepared(people, source['sha256'], fields, recipes={'owner': changed}, support_assets=bank, source_frame=source)


@pytest.mark.parametrize('obstacle', [[.3, .1, .4, .2], [.75, .1, .8, .2], [.1, .35, .4, .36]])
def test_additional_observed_body_or_person_contact_refuses_entire_request(obstacle):
    people, bank, source, evidence, _ = fixture()
    recipe = S.neutral(); recipe['crown']['amount'] = 1
    with mock.patch.object(R, 'HairVolumeField', AdmissionField):
        with pytest.raises(R.HairVolumeRefused, match='protected'):
            call(people, bank, source, evidence, recipe, protected_regions=[obstacle])


def test_own_face_protection_is_not_erased_by_manual_support():
    people, _, source, evidence, record = fixture()
    # Move canonical face into the reviewed crown, then independently re-review.
    people['faces']['owner']['box'] = [.4, .25, .6, .7]
    record = A.reviewed(people, record['face_ref'], source, record['row']['regions'],
                        record['row']['protection'], evidence, confirmed=True)
    people, bank = A.retain(people, {}, record)
    recipe = S.neutral(); recipe['crown']['amount'] = 1
    with mock.patch.object(R, 'HairVolumeField', AdmissionField):
        with pytest.raises(R.HairVolumeRefused, match='protected'):
            call(people, bank, source, evidence, recipe)


def test_original_support_cannot_be_reused_under_derived_pixel_identity():
    people, bank, source, evidence, _ = fixture()
    derived = {**source, 'sha256': 'f'*64}
    recipe = S.neutral(); recipe['crown']['amount'] = 1
    with pytest.raises(ValueError):
        call(people, bank, derived, evidence, recipe)
