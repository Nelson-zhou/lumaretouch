# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN complete-head/hair source ownership fixtures.

No product imports, test collection/execution, native load, build, typecheck,
inference or model download occurred during authoring. Synthetic observations
carry expected manifest identifiers solely for schema/ownership routing. They
are not detector outputs, an anatomy demonstration or photographic acceptance.
Native-boundary doubles below are adapter fixtures, NOT Rust numeric evidence.
"""
from copy import deepcopy
from unittest.mock import patch
import numpy as np
import pytest

from lumaretouch_engine import body_pose_evidence as E, body_pose_manifest as M
from lumaretouch_engine import body_pose_state as B, people_state as PEOPLE
from lumaretouch_engine import head_size_state as S, head_size_native as N
from lumaretouch_engine import head_size_runtime as R
from lumaretouch_engine.head_size_field import HeadSizeField

BUDGET = 16 * 1024 * 1024
SOURCE = {'sha256': 'a' * 64, 'width': 1024, 'height': 1024, 'orientation': E.ORIENTATION}


def synthetic_record(*, source=None, observed=True):
    source = deepcopy(SOURCE if source is None else source)
    points = [dict(index=i, x=.5, y=.9, z=0., visibility=.99 if observed else 0.,
                   presence=.99 if observed else 0.) for i in range(33)]
    head = [(0.5, .40), (.49, .38), (.48, .38), (.47, .38), (.51, .38),
            (.52, .38), (.53, .38), (.46, .40), (.54, .40), (.49, .43), (.51, .43)]
    positions = {**dict(enumerate(head)), 11: (.35, .83), 12: (.65, .83)}
    for index, (x, y) in positions.items():
        points[index].update(x=x, y=y)
    return E.create(source_frame=source, values=points,
        backend_version='synthetic-routing-fixture', backend_code_sha256='b' * 64,
        model_id=M.MODEL_ID, model_sha256=M.MODEL_SHA256, input_rgb_sha256='c' * 64,
        input_dimensions=(source['width'], source['height']))


def geometry():
    """Explicit synthetic marks only; never used to propose production anatomy."""
    return {'version': 1, 'method': S.METHOD,
            'head_box': [.44, .35, .56, .45],
            'transition_box': [.04, .04, .96, .76], 'pivot': [.5, .4],
            'confirmations': {flag: True for flag in S.FLAGS}}


def fixture(*, amount=.5, review=True, source=None):
    record = synthetic_record(source=source)
    source = record['source']
    state = B.add_run(B.empty(), {'source': source, 'records': [record],
        'detector_limit': 4, 'limit_reached': False, 'census_complete': False},
        initial_operations=(S.OPERATION_ID,), operation_policies=S.policies())
    ref = record['body_ref']
    evidence = {'backend': 'synthetic-routing-fixture', 'detector_model_sha256': 'd' * 64,
                'semantic_model_sha256': None, 'landmark_digest': 'e' * 64, 'status': 'verified',
                'source_width': source['width'], 'source_height': source['height'],
                'orientation': source['orientation']}
    face = PEOPLE.new_face(source['sha256'], [.455, .365, .545, .435], evidence)
    people = PEOPLE.empty()
    people['faces'][face['face_instance_id']] = face
    people['persons']['synthetic-person'] = {'anonymous': True}
    people['revision'] = people['association_revision'] = 1
    people['links'] = [{'face_instance_id': face['face_instance_id'], 'person_id': 'synthetic-person',
                       'state': 'confirmed', 'confirmation_revision': 1}]
    state = B.associate(state, ref, 'synthetic-person', people, user_confirmed=True)
    data = R.bind_support_review(geometry(), B.target(state, ref), people)
    if review:
        state = B.set_support(state, ref, S.OPERATION_ID, S.SUPPORT_KIND, data,
                              operation_policies=S.policies())
        state = B.review(state, ref, operation_id=S.OPERATION_ID,
            points_sha256=record['points_sha256'], visible_anchors=list(S.REQUIRED_ANCHORS),
            ownership_confirmed=True, support_sha256=B.operation(state, ref, S.OPERATION_ID)['support_sha256'],
            operation_policies=S.policies())
    state = B.set_recipe(state, ref, {'version': 1, 'amount': amount},
                         operation_id=S.OPERATION_ID, operation_policies=S.policies())
    return state, people, ref, data, source


def native_prepare_double(points, values, support, shape):
    """ABI-layout-only double: does not exercise Rust admission or inversion."""
    h, w = shape
    head, outer, pivot = support[:4], support[4:8], support[8:10]
    return np.frombuffer(np.array([
        outer[0] * (w - 1), head[0] * (w - 1), head[2] * (w - 1), outer[2] * (w - 1),
        outer[1] * (h - 1), head[1] * (h - 1), head[3] * (h - 1), outer[3] * (h - 1),
        pivot[0] * (w - 1), pivot[1] * (h - 1), .08 * values[1], w, h],
        np.float64).tobytes(), np.float64)


def native_facts_double(state):
    """Synthetic report fields, not measured numerical or image acceptance."""
    radius = np.hypot(max(state[8] - state[0], state[3] - state[8]),
                      max(state[9] - state[4], state[7] - state[9]))
    gradient = state[10] * (1 + 1.875 * radius * np.hypot(
        1 / min(state[1] - state[0], state[3] - state[2]),
        1 / min(state[5] - state[4], state[7] - state[6])))
    return {'support_box': [state[0], state[4], state[3], state[7]],
            'plateau_box': [state[1], state[5], state[2], state[6]],
            'pivot': state[8:10].tolist(), 'scale': float(1 - state[10]),
            'max_displacement': float(state[10] * radius), 'gradient_bound': float(gradient),
            'forward_jacobian_lower_bound': float((1 - gradient) ** 2),
            'inverse_residual_tolerance': 1e-7, 'inverse_max_iterations': 64,
            'runtime_quality_accepted': False}


def prepare(data, *, shape=(512, 512), native=None, **kwargs):
    bank, people, _, _, source = data
    with patch.object(N, 'prepare', side_effect=native or native_prepare_double), \
            patch.object(N, 'facts', side_effect=native_facts_double):
        return R.prepare_fields(bank, source['sha256'], shape, people_state=people,
                                 byte_budget=BUDGET, source_frame=source, **kwargs)


def test_exact_control_hair_scope_and_independent_abi():
    assert S.OPERATION_ID == 'lnx.head_size.v1'
    assert S.IDS == {'amount': 'LNX-REF-PC-32473-C-dc1b0ba40a'}
    assert S.REQUIRED_ANCHORS == tuple(range(13))
    assert S.SUPPORT_KIND == 'head-size-complete-head-hair-review-v1'
    support = fixture()[3]
    assert S.support_vector(support) == support['head_box'] + support['transition_box'] + support['pivot']
    assert len(S.support_vector(support)) == 10
    assert S.vector({'version': 1, 'amount': .5}) == [1, .5]
    assert not set(S.FACE_BINDING_KEYS).intersection({'head_box', 'transition_box', 'pivot'})


@pytest.mark.parametrize('amount', [0., .001, .5, 1.])
def test_only_amount_and_version_are_portable_and_positive_shrinks(amount):
    recipe = {'version': 1, 'amount': amount}
    assert S.portable(recipe) == recipe == S.adjust(S.neutral(), 'amount', amount)
    for extra in ('body_ref', 'face_ref', 'head_box', 'transition_box', 'pivot', 'support', 'neck_length'):
        with pytest.raises(ValueError):
            S.portable({**recipe, extra: None})


@pytest.mark.parametrize('amount', [True, None, -.001, -1, 1.001, float('nan'), float('inf'), 10**1000])
def test_invalid_amount_is_refused_not_clamped_or_reversed(amount):
    with pytest.raises(ValueError):
        S.check({'version': 1, 'amount': amount})


@pytest.mark.parametrize('flag', S.FLAGS)
@pytest.mark.parametrize('value', [False, None, 1, 'true'])
def test_every_manual_visibility_ownership_and_background_confirmation_is_explicit(flag, value):
    bank, _, ref, support, _ = fixture()
    support['confirmations'][flag] = value
    with pytest.raises(ValueError):
        S.check_support(support, B.target(bank, ref)['record'])


@pytest.mark.parametrize('key', [*S.BOXES, 'pivot', *S.FACE_BINDING_KEYS, 'method'])
def test_no_missing_manual_geometry_or_current_face_binding(key):
    support = fixture()[3]
    del support[key]
    with pytest.raises(ValueError):
        S.check_support(support)


@pytest.mark.parametrize('key', S.BOXES)
@pytest.mark.parametrize('value', [None, [], [.2, .3], [.1, .2, .3, True],
                                  [0., .2, .3, .4], [.1, .2, 1., .4],
                                  [.1, float('nan'), .3, .4], [.1, .2, float('inf'), .4]])
def test_geometry_is_finite_interior_normalized_source_boxes(key, value):
    support = fixture()[3]
    support[key] = value
    with pytest.raises(ValueError):
        S.check_support(support)


@pytest.mark.parametrize('pivot', [None, [], [.5], [.5, .4, .6], [True, .4],
                                   [float('nan'), .4], [.44, .4], [.56, .4], [.5, .45]])
def test_pivot_must_be_explicit_and_strictly_inside_head(pivot):
    support = fixture()[3]
    support['pivot'] = pivot
    with pytest.raises(ValueError):
        S.check_support(support)


@pytest.mark.parametrize('index', S.REQUIRED_ANCHORS)
@pytest.mark.parametrize('fault', ['visibility', 'presence', 'cropped'])
def test_review_never_promotes_hidden_or_cropped_actual_head_and_shoulders(index, fault):
    bank, _, ref, support, _ = fixture()
    record = deepcopy(B.target(bank, ref)['record'])
    record['points'][index].update({'x': 0.} if fault == 'cropped' else {fault: .79})
    record['points_sha256'] = E.content_digest(record['points'])
    with pytest.raises(ValueError):
        S.check_support(support, record)


@pytest.mark.parametrize('index', range(11))
def test_all_eleven_real_head_points_must_be_inside_full_head_plateau(index):
    bank, _, ref, support, _ = fixture()
    record = deepcopy(B.target(bank, ref)['record'])
    record['points'][index]['x'] = support['head_box'][0]
    record['points_sha256'] = E.content_digest(record['points'])
    with pytest.raises(ValueError, match='Every actual'):
        S.check_support(support, record)


@pytest.mark.parametrize('index', [11, 12])
def test_each_shoulder_is_strictly_below_transition_even_at_contact(index):
    bank, _, ref, support, _ = fixture()
    record = deepcopy(B.target(bank, ref)['record'])
    record['points'][index]['y'] = support['transition_box'][3]
    record['points_sha256'] = E.content_digest(record['points'])
    with pytest.raises(ValueError, match='shoulders'):
        S.check_support(support, record)


@pytest.mark.parametrize('key,value', [
    ('transition_box', [.44, .04, .96, .76]),  # coincident plateau/transition edge
    ('transition_box', [.43, .04, .96, .76]),  # less than 16 source px margin
    ('transition_box', [.0001, .04, .96, .76]),  # source edge clearance
    ('head_box', [.44, .35, .56, .84]),  # long hair/shoulders cannot be invented away
    ('associated_face_box', [.44, .365, .545, .435]),  # whole face touches plateau
])
def test_contour_review_cannot_bypass_full_enclosure_margins_or_source_clearance(key, value):
    bank, _, ref, support, _ = fixture()
    support[key] = value
    with pytest.raises(ValueError):
        S.check_support(support, B.target(bank, ref)['record'])


def test_no_old_operation_support_or_review_is_reused():
    from lumaretouch_engine import neck_shape_state as NECK, waist_length_state as WAIST
    bank, _, ref, support, _ = fixture()
    assert S.SUPPORT_KIND not in (NECK.SUPPORT_KIND, WAIST.SUPPORT_KIND)
    wrong = deepcopy(B.support(bank, ref, S.OPERATION_ID))
    wrong['operation_id'] = WAIST.OPERATION_ID
    with pytest.raises(ValueError, match='cannot cross'):
        HeadSizeField(B.target(bank, ref), wrong, (512, 512))
    wrong_row = deepcopy(B.target(bank, ref))
    wrong_row['operations'][S.OPERATION_ID]['review']['operation_id'] = NECK.OPERATION_ID
    with pytest.raises(ValueError, match='own complete'):
        HeadSizeField(wrong_row, B.support(bank, ref, S.OPERATION_ID), (512, 512))


def test_neutral_has_no_native_or_source_review_dependency():
    bank, _, ref, _, _ = fixture(amount=0, review=False)
    with patch.object(N, 'prepare', side_effect=AssertionError('neutral native prepare')), \
            patch.object(N, 'evaluate', side_effect=AssertionError('neutral native evaluate')):
        field = HeadSizeField(B.target(bank, ref), None, (512, 512))
        points = np.array([[12.125, 45.75], [200.3, 300.6]])
        np.testing.assert_array_equal(field.evaluate(points), np.zeros_like(points))
        assert not field.contains(points).any() and field.supports == ()
        assert field.max_displacement == 0 and field.resident_bytes() == field.render_scale.nbytes
        assert field.facts['hidden_anatomy_inferred'] is False
        assert field.facts['runtime_quality_accepted'] is False


def test_neutral_runtime_does_not_require_current_face_or_association():
    bank, people, ref, support, source = fixture(amount=0)
    bank = B.unlink(bank, ref)
    people['faces'].clear(); people['links'].clear(); people['association_revision'] += 1
    with patch.object(R, 'associated_face', side_effect=AssertionError('neutral associated face')), \
            patch.object(N, 'prepare', side_effect=AssertionError('neutral native')):
        assert R.prepare_fields(bank, source['sha256'], (512, 512), people_state=people,
                                 byte_budget=BUDGET, source_frame=source) == ()


def test_active_without_independent_review_refuses_before_native():
    with pytest.raises(R.HeadSizeRefused, match='independently reviewed'):
        prepare(fixture(review=False), native=lambda *args: pytest.fail('unreviewed native call'))


def test_active_missing_native_is_unapplied_and_never_falls_back():
    data = fixture()
    with patch.object(N, 'prepare', side_effect=RuntimeError('Head size Rust core is not installed')):
        with pytest.raises(R.HeadSizeRefused, match='not installed') as refused:
            R.prepare_fields(data[0], data[4]['sha256'], (512, 512), people_state=data[1],
                             byte_budget=BUDGET, source_frame=data[4])
    assert all(item['applied'] is False for item in refused.value.refusals)


def test_native_failure_is_one_exact_requested_amount_without_attenuation():
    seen = []
    def refuse(points, values, support, shape):
        seen.append(values)
        raise ValueError('synthetic native contraction refusal')
    with pytest.raises(R.HeadSizeRefused, match='contraction'):
        prepare(fixture(amount=1), native=refuse)
    assert seen == [[1, 1.]]


@pytest.mark.parametrize('fault', ['missing', 'stale-link', 'unconfirmed', 'manual', 'unresolved',
                                 'face-analysis', 'face-box', 'face-evidence', 'face-source-size'])
def test_current_actual_associated_face_is_required_before_native(fault):
    bank, people, ref, support, source = fixture()
    face = people['faces'][support['associated_face_ref']['face_instance_id']]
    if fault == 'missing': people = None
    elif fault == 'stale-link': people['association_revision'] += 1
    elif fault == 'unconfirmed': people['links'][0].update(state='candidate', confirmation_revision=None)
    elif fault == 'manual': face['manual'] = True
    elif fault == 'unresolved': face['evidence']['status'] = 'unresolved'
    elif fault == 'face-analysis': face['analysis_revision'] += 1
    elif fault == 'face-box': face['box'][0] += .001
    elif fault == 'face-evidence': face['evidence']['landmark_digest'] = 'f' * 64
    else: face['evidence']['source_width'] += 1
    with pytest.raises(R.HeadSizeRefused):
        prepare((bank, people, ref, support, source), native=lambda *args: pytest.fail('invalid face reached native'))


def test_source_review_binds_only_factual_identity_and_refuses_partial_or_conflicting_binding():
    bank, people, ref, support, _ = fixture()
    raw = geometry(); original = deepcopy(raw)
    assert R.bind_support_review(raw, B.target(bank, ref), people) == support
    assert raw == original
    assert R.bind_support_review(support, B.target(bank, ref), people) == support
    with pytest.raises(ValueError):
        R.bind_support_review({**raw, 'associated_face_box': support['associated_face_box']},
                              B.target(bank, ref), people)
    changed = deepcopy(support); changed['associated_face_evidence_sha256'] = 'f' * 64
    with pytest.raises(ValueError):
        R.bind_support_review(changed, B.target(bank, ref), people)


def test_two_confirmed_faces_for_same_body_person_are_not_resolved_by_distance():
    data = fixture(); people = data[1]
    own = next(iter(people['faces'].values()))
    other = PEOPLE.new_face(data[4]['sha256'], [.6, .4, .7, .5], own['evidence'])
    people['faces'][other['face_instance_id']] = other
    people['links'].append({'face_instance_id': other['face_instance_id'],
                           'person_id': 'synthetic-person', 'state': 'confirmed',
                           'confirmation_revision': 1})
    with pytest.raises(R.HeadSizeRefused, match='exactly one'):
        prepare(data, native=lambda *args: pytest.fail('ambiguous face reached native'))


def test_foreign_face_with_other_source_dimensions_is_unresolved_not_silently_ignored():
    data = fixture(); people = data[1]
    own = next(iter(people['faces'].values()))
    evidence = {**own['evidence'], 'source_width': data[4]['width'] + 1}
    other = PEOPLE.new_face(data[4]['sha256'], [.001, .90, .01, .99], evidence)
    other['enabled'] = False
    people['faces'][other['face_instance_id']] = other
    with pytest.raises(R.HeadSizeRefused, match='uncertain source bounds'):
        prepare(data)


@pytest.mark.parametrize('enabled', [True, False])
@pytest.mark.parametrize('status', ['verified', 'unresolved'])
def test_disabled_unresolved_manual_foreign_faces_still_protect_transition(enabled, status):
    data = fixture(); people = data[1]
    own = next(iter(people['faces'].values()))
    other = PEOPLE.new_face(data[4]['sha256'], [.75, .4, .85, .5],
                            {**own['evidence'], 'status': status}, manual=True)
    other['enabled'] = enabled
    people['faces'][other['face_instance_id']] = other
    with pytest.raises(R.HeadSizeRefused, match='another retained face'):
        prepare(data)


def test_boundary_contact_is_not_foreign_clearance():
    assert R._overlap((np.array([1., 2.]), np.array([5., 6.])),
                      (np.array([5., 3.]), np.array([7., 4.])))


@pytest.mark.parametrize('observed', [True, False])
def test_disabled_foreign_bodies_and_unresolved_bounds_refuse(observed):
    data = list(fixture())
    other = synthetic_record(observed=observed)
    data[0] = B.add_run(data[0], {'source': data[4], 'records': [other], 'detector_limit': 4,
        'limit_reached': False, 'census_complete': False}, initial_operations=(S.OPERATION_ID,),
        operation_policies=S.policies())
    data[0]['bodies'][other['body_ref']['body_instance_id']]['enabled'] = False
    with pytest.raises(R.HeadSizeRefused, match='body'):
        prepare(data)


def test_original_and_derived_digest_are_exact_source_owned_not_interchangeable():
    data = fixture(); bank, people, _, _, source = data
    derived = {**source, 'sha256': 'f' * 64}
    for changed in ({**source, 'width': 1032}, derived):
        with pytest.raises(ValueError):
            R.prepare_fields(bank, source['sha256'], (512, 512), people_state=people,
                             byte_budget=BUDGET, source_frame=changed)
    with pytest.raises(ValueError):
        R.prepare_fields(bank, source['sha256'], (512, 400), people_state=people,
                         byte_budget=BUDGET, source_frame=source)
    derived_data = fixture(source=derived)
    assert derived_data[3]['associated_face_ref']['asset_sha256'] == derived['sha256']
    assert prepare(derived_data)[0].record['source'] == derived


def test_field_prepares_original_shape_and_preserves_fractional_decoder_conjugation():
    data = fixture(source={**SOURCE, 'width': 1201, 'height': 1601})
    seen = []
    def admission(points, values, support, shape):
        seen.append(shape)
        return native_prepare_double(points, values, support, shape)
    field, = prepare(data, shape=(800, 600), native=admission)
    assert seen == [(1601, 1201)]
    points = np.array([[31.25, 72.125], [300., 210.]])
    def evaluate(state, source_points):
        np.testing.assert_array_equal(source_points, points / field.render_scale)
        return np.tile([3., -7.], (len(source_points), 1))
    with patch.object(N, 'evaluate', side_effect=evaluate):
        np.testing.assert_allclose(field.evaluate(points), np.tile([3., -7.], (2, 1)) * field.render_scale)
    assert field.facts['fixed_joint_indices'] == [11, 12]
    assert field.facts['complete_head_hair_uniform_scale'] is True
    assert field.facts['independent_image_resampling'] is False


def test_exact_proxy_edges_do_not_clip_nearby_interior_or_outside_queries():
    data = fixture(source={**SOURCE, 'width': 1201, 'height': 1601})
    field, = prepare(data, shape=(800, 600))
    points = np.array([[0., 0.], [599., 799.], [0., 799.], [599., 0.],
                       [598.875, 798.875], [np.nextafter(599., 0.), np.nextafter(799., 0.)]])
    expected = points[4:] / field.render_scale
    def evaluate(state, source_points):
        np.testing.assert_array_equal(source_points[:4], [[0., 0.], [1200., 1600.], [0., 1600.], [1200., 0.]])
        np.testing.assert_array_equal(source_points[4:], expected)
        return np.zeros_like(source_points)
    with patch.object(N, 'evaluate', side_effect=evaluate):
        np.testing.assert_array_equal(field.evaluate(points), np.zeros_like(points))
    with patch.object(N, 'evaluate', side_effect=AssertionError('outside reached native')):
        for outside in ([[np.nextafter(599., np.inf), 400.]], [[300., np.nextafter(799., np.inf)]],
                        [[np.nextafter(0., -np.inf), 400.]], [[300., np.nextafter(0., -np.inf)]]):
            with pytest.raises(ValueError, match='no clipping'):
                field.evaluate(outside)


def test_transition_displacement_envelope_and_radius_are_conservative():
    field, = prepare(fixture())
    low, high = field.envelope()
    np.testing.assert_allclose(low, field.bounds[0] - field.max_displacement)
    np.testing.assert_allclose(high, field.bounds[1] + field.max_displacement)
    center, radius = field.supports[0]
    assert radius >= np.linalg.norm(field.bounds[1] - field.bounds[0]) * .5 + field.max_displacement
    assert field.contains(np.array([low, high])).all()
    assert not field.contains(np.array([low - 1, high + 1])).any()
    assert field.resident_bytes() > field.state.nbytes


def test_wrong_pose_model_refuses_before_native():
    bank, people, ref, support, source = fixture()
    B.target(bank, ref)['record']['model_sha256'] = 'f' * 64
    with pytest.raises(R.HeadSizeRefused, match='model identity'):
        prepare((bank, people, ref, support, source), native=lambda *args: pytest.fail('wrong model native'))


def test_off_grid_points_must_be_finite_xy_even_when_neutral():
    data = fixture(amount=0, review=False)
    field = HeadSizeField(B.target(data[0], data[2]), None, (512, 512))
    for invalid in (np.zeros((2, 3)), np.zeros(2), [[float('nan'), 1.]], [[1., float('inf')]]):
        with pytest.raises(ValueError): field.evaluate(invalid)
        with pytest.raises(ValueError): field.contains(invalid)
