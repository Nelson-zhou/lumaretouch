"""AUTHORED / UNRUN: canonical bilateral chin-shape integration contracts.

All pixels, landmarks and observations here are synthetic fixtures, not detector
measurements or photographic acceptance. The ONLY patched production boundary
is chin_shape_runtime.build. Its explicit horizontal field double proves routing,
not the native inverse, anatomy, curvature, visibility or aesthetic sharpness.
Full pipeline fixtures retain actual source ownership, repair-proof verification,
the real ChinShape wrapper, common joint map and existing image sampler. Prefix
composition fixtures retain real wrappers and TPS math, with explicitly named
synthetic contour/size/lower/mid field doubles, not patched runtime builders.

No product import, test collection/execution, native build, inference, numerical
probe or type check ran while authoring this file. Source inspections are authored
test contracts, not completed checks, pixel parity or runtime acceptance.
"""
import ast
from copy import deepcopy
import hashlib
from itertools import product
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from test_skin_colour_body_render_unrun import fixture as source_fixture
from lumaretouch_engine import chin_shape_state as S, chin_shape_runtime as CORE
from lumaretouch_engine import chin_shape_people as PORT, face_contour_state as C
from lumaretouch_engine import slim_face_state as SLIM, face_size_state as SIZE
from lumaretouch_engine import lower_face_state as LOWER, mid_face_state as MID
from lumaretouch_engine import people_algorithms as A, people_state as P
from lumaretouch_engine import people_resolver as RESOLVE, people_project as PROJECT
from lumaretouch_engine import people_snapshot as SNAP, people_export as EXPORT
from lumaretouch_engine import people_render_runtime as RENDER
from lumaretouch_engine import people_engine_runtime as ENGINE
from lumaretouch_engine import people_edit as EDIT, people_host_commands as HOST
from lumaretouch_engine.people_graph_owner import PeopleGraphOwner
from lumaretouch_engine import creative_derived_effects as DERIVED
from lumaretouch_engine import creative_derived_repairs as REPAIRS
from lumaretouch_engine import creative_derived_repair_runtime as REPLAY
from lumaretouch_engine.people_geometry import AutomaticField, FaceGeometry, CombinedGeometry
from lumaretouch_engine.ops import deform as D

ROOT = Path(__file__).resolve().parents[2]
BUDGET = 512 * 1024**2
DOCUMENT = 'synthetic-chin-shape-document'
ACTIVE = {'version': 1, 'linked': False, 'left': .4, 'right': -.2}
SIGNED_RECIPES = (
    {'version': 1, 'linked': True, 'left': .4, 'right': .4},
    {'version': 1, 'linked': True, 'left': -.4, 'right': -.4},
    {'version': 1, 'linked': False, 'left': .4, 'right': 0.},
    {'version': 1, 'linked': False, 'left': 0., 'right': -.4},
    ACTIVE,
)
# Read-only git-show SHA256 values from the exact parent-selected baseline.
# These preserve legacy defects too; unchanged bytes are NOT rendered parity.
BASELINE = '4c1bea881ecdc4b2c94b88b7e99d0c7fb202aedb'
PRIOR_SOURCE_SHA256 = {
    'core/face_contour/Cargo.toml': '51846d9352c23254d649f7074a4f1883dbae075b988f0057048fc4b1bfa20c84',
    'core/face_contour/README.md': 'a593d5e46e9fd5418f73c61745d5a118b98329234c4033b76d928f5ed94e2a77',
    'core/face_contour/face_contour.h': '5b0a09073c55e0eee96c67dd379b7a4ab15544272b19c98bfb015df84482517a',
    'core/face_contour/lib.rs': '517e6a791f65918f586194fc6d1090c35b8b32b22bfc2ff0089d432f68f19210',
    'core/face_contour/tests.rs': '6e75533a318d86ce912ec20447a3956dd71dff10cd0ba4f4cdb76883638c4622',
    'core/face_size/Cargo.toml': '40b0ff7d04faeb8729fc4f2cfaae4069b553ae9b66ec3c14c076002a01a809ad',
    'core/face_size/README.md': '92d66fb098d9eebfae55661e98e715ff70be59ebd4e25a1c3eddd8d765ff0dcc',
    'core/face_size/face_size.h': '517bdee57b5615760367f45e985c276b90e2e5c13004cb1dcc7594a88e15cde3',
    'core/face_size/lib.rs': 'f53ff8f9ac88b07d7e35f49ebf48e8dd297862f4d138a10b5c140107611f7e30',
    'core/face_size/tests.rs': 'e7520cd24acd1923832a2532297c3399d57f15ab5bd8369dfbbc742f862fc52f',
    'core/lower_face/Cargo.toml': '916495b02ce40a259c7601de5b73d814b350608a1d387adab554c9ac8ffa3265',
    'core/lower_face/README.md': 'e70f3e0d7a8a0aebf300bc0a5f7f9062020f056c18ea90deda5fd2647dd93e20',
    'core/lower_face/lib.rs': '078ec2aa41b6403058208d5d3a7fd5a9b2f2519257524242b203b4cb28b20931',
    'core/lower_face/lower_face.h': 'f4d16aa55ad1176163894bd608896d4a10dd8b1a90f9483933ae256b64b780af',
    'core/lower_face/tests.rs': '57da7c6a6a83d1719b83df9b01fab2a3b2cf1d4230d6137c7ce23ce0ccf54490',
    'core/mid_face/Cargo.toml': 'a429881e5e9cdb918b5e4ce7d28b704627179372dcc27950bff9560826cb3383',
    'core/mid_face/README.md': '16aed96e819f8dcc58fe4821549a372257e252db7f56f906fae4b808a9ed81d7',
    'core/mid_face/lib.rs': 'bc69b7f6f53f43f126e0e609ad9ea454e52b5d9c26b7efccdc295ec83bf1f6c5',
    'core/mid_face/mid_face.h': '5c9b89df46db72b35b48881f6f6d784a802b52629647f4f2406eb57c7093716c',
    'core/mid_face/tests.rs': 'aaf7c7eba1f6b24936a57a30c1f4a958ce80a0f6bbe38676ae2c83b277a2deed',
    'engine/src/lumaretouch_engine/brow_shape_geometry.py': '267cbf7c2484a34b2e238445d572372f9ebb60461e3e4cd668a74c346a8863b5',
    'engine/src/lumaretouch_engine/eye_shape_geometry.py': 'fbf65f20ba7cadaafa99a554f39791dd30f929e8cb169d7edec05a07bf7cd3b4',
    'engine/src/lumaretouch_engine/face_contour_field.py': 'e735091f5c4a07a93143fbfe066d917fbe2fa7f8d474accdd053db6ed378ded1',
    'engine/src/lumaretouch_engine/face_contour_geometry.py': 'f40ce390d517dc8159ba3e74b4b949555d2b79e40daa0848ab1f36170be65f2d',
    'engine/src/lumaretouch_engine/face_contour_native.py': 'e1fb0afbed2b969eb5d5121d15992831ff94547528a7740f24da297ebccaf85a',
    'engine/src/lumaretouch_engine/face_contour_people.py': '207e6ed0687da56ba22fc75c9eddf8780c3afb65df7ce54cdbd17aa3334fc78b',
    'engine/src/lumaretouch_engine/face_contour_runtime.py': '438edbf955b70bbd104798ddbbe0833ce53fc94e0e23f19d870a8fdfbd101e1c',
    'engine/src/lumaretouch_engine/face_contour_scope.py': 'f37bb7f7d0b54ad797ad32dcaae06dc7e47688560c8af3710c2c2c6d82f2dbc4',
    'engine/src/lumaretouch_engine/face_contour_state.py': '82b3e96a443ab1f79caba3d73d652ce6126a4fb0030a84775f8f14024f651e91',
    'engine/src/lumaretouch_engine/face_size_native.py': 'f7d1cb3b77ab508055ec5f28913f550a56de221e6819276a54e8b19d382793d0',
    'engine/src/lumaretouch_engine/face_size_people.py': 'edb795d76637955f9e41fccd455c4e72e57004472ee5c1cf869b2af6a5c248be',
    'engine/src/lumaretouch_engine/face_size_runtime.py': '18566c11211f5ae902d0c79fd7d33c4b026efaa801a7ba2a2e1b4582f5fa108b',
    'engine/src/lumaretouch_engine/face_size_scope.py': '1422cdc651d82fa4888ceb03b237abdc7f8efc77d1fb8187467599269fca40d9',
    'engine/src/lumaretouch_engine/face_size_state.py': 'ac589cde812c2b146c11b78d0dd5b4087f983bf52383a439f29e509468b42ce8',
    'engine/src/lumaretouch_engine/lower_face_native.py': '3d18fc954b26ca81d11b29114492fd2a50dc4552881c9f209987dab986a5b944',
    'engine/src/lumaretouch_engine/lower_face_people.py': 'f726bca711f89d02801b7814f31854e69834deabd1bba025469bb7142ece22b0',
    'engine/src/lumaretouch_engine/lower_face_runtime.py': '6b5427db09a2c423ddf2bf8948f10a4714ac4fedbeb6858bf2f01984695619c3',
    'engine/src/lumaretouch_engine/lower_face_scope.py': 'bd235daa1e54c9df9bf8bd54f458b80eb4acc6bcd9f4d1a892c47626b9742f18',
    'engine/src/lumaretouch_engine/lower_face_state.py': '96d3328b25b5d8f0edcb4b6fb80adc13634b7a54a0bf38ed29d88a18a2a3f33c',
    'engine/src/lumaretouch_engine/mid_face_native.py': '52dd5b0a8291003ed03d8c07c2104d08eca7eb9a064ba2f144798c6d01a74cc6',
    'engine/src/lumaretouch_engine/mid_face_people.py': '025e8044809b929e45c4e4980addc7a9a86d6a088fede83cf8557204bd9611f9',
    'engine/src/lumaretouch_engine/mid_face_runtime.py': 'a55b3766af654e6f4a72b6e3320fac6afe2331e74c1a292933d85828ae07bdb2',
    'engine/src/lumaretouch_engine/mid_face_scope.py': '128d18d58391777f603657c0b0b26f81a9228bae00f12b11e010802fde2b18e3',
    'engine/src/lumaretouch_engine/mid_face_state.py': '67a4bfc3a08de6c12ff6e8a50bb061bafd167c6bf54cf948aab2bdf414bc40a2',
    'engine/src/lumaretouch_engine/mouth_shape_geometry.py': 'ff866e32296384f898a0a21bf7af55e9690c56a69c467da68b6c4ea7786d0758',
    'engine/src/lumaretouch_engine/nose_shape_geometry.py': '1643f4d0ead92e59487708e90b2bb5b5910b961063bc81b7fcfaf58dc7a162ce',
    'engine/src/lumaretouch_engine/ops/deform.py': '5e0800bffa8f87f9f8e4f6cf8caa1ea782bee20d099a2232c869e0e9d53247fd',
    'engine/src/lumaretouch_engine/people_geometry.py': '554e4ea056f8c675be3b1fb859a2ca3101ca437dc1db52967e4151524955580b',
    'engine/src/lumaretouch_engine/project_package_archive.py': '6a5b3210182b2a6504c538451456c11a486cca12ffe9a9c4ea2aed122651656a',
    'engine/src/lumaretouch_engine/slim_face_people.py': '6b4b8f4823bb5896a811d42d80288f87ec7c461d68982447b821e43c4815037d',
    'engine/src/lumaretouch_engine/slim_face_scope.py': '2030210fca69fbe1b555a66d182226425e09dc696fa95c760cfd39e47389da29',
    'engine/src/lumaretouch_engine/slim_face_state.py': 'af2425651ac89560b5f35632f850764e338812d2e16790eae53a7df61226ff57',
    'LICENSE': '3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986',
    'docs/model-licenses/README.md': '1353d52698f42217454ae1231a6d6cfa2405edea7738b0fb223f5417312dab8f',
    'docs/model-licenses/models.json': '3dcf5f9b45f0f8f6e58513b5d666a04dff6757911ec222cab270f1573ef5d43b',
    'docs/model-licenses/sam2.1-hiera-tiny-provenance.md': 'c2a7653685cde00cc148f4b26a0c58dcbb662f56fe7fa7bb7941341b26ac3018',
    'docs/model-licenses/archive/mediapipe-LICENSE.txt': '8707eef0533987efc5b155d64761eeb6e20793f50b9bd1a68dad1cf4719d0ed8',
    'docs/model-licenses/archive/sam2-LICENSE.txt': 'c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4',
    'docs/model-licenses/archive/sam2-README.md': 'eea69ee1042fb30933c5ca5019fbf0f6f9366cec5e792109281b5023a4f1589c',
    'docs/model-licenses/archive/sam2.1-hiera-tiny-hf-tree.json': '6966c78030b9ddffc745a4c1ab030ee1cef98e740ba07ab245443ee6eee17abb',
    'docs/model-licenses/archive/sam2.1_hiera_t.yaml': 'f932eac1c6241e910031b2f000a81cd9f8a8d4896e2277ab5ffb721f378b188d',
}


def set_recipe(state, key, recipe):
    for path, value in A.leaves(recipe).items():
        state = P.set_override(state, 'face', key, S.OP, path, value)
    return state


def patch_command(state, ref, leaves):
    return {'document_id': DOCUMENT, 'document_epoch': 'synthetic-epoch', 'document_revision': 7,
            'state_revision': state['revision'], 'association_revision': state['association_revision'],
            'request_id': 'synthetic-chin-atomic-request', 'action': 'patch',
            'target': {'scope': 'face', 'target_id': ref['face_instance_id'], 'face_ref': deepcopy(ref)},
            'payload': {'patches': [{'operation_id': S.OP, 'parameter_path': path,
                                    'unset': False, 'value': value} for path, value in leaves]}}


def fixture(*, size=128, recipe=ACTIVE):
    state, _, ref, _, analysis, _, _ = source_fixture(retained=False)
    state['links'], state['persons'] = [], {}
    for evidence in (state['faces'][ref['face_instance_id']]['evidence'], analysis['evidence']):
        evidence['source_width'] = evidence['source_height'] = size
    state = set_recipe(state, ref['face_instance_id'], recipe)
    return state, ref, analysis, {'sha256': ref['asset_sha256'], 'width': size, 'height': size}


def original_pixels(size):
    """RGB16 fixture with real integer steps below one RGB8 quantization step."""
    yy, xx = np.indices((size, size), dtype=np.uint32)
    return np.stack(((xx*113 + yy*17) % 65536, (xx*37 + yy*101) % 65536,
                     (xx*53 + yy*61 + 12345) % 65536), axis=-1).astype(np.uint16)


class SyntheticChinField:
    """Explicit build double, never native/geometry/photo acceptance evidence."""
    def __init__(self, shape, recipe, *, constant_delta=None):
        self.shape = tuple(shape)
        self.state = {'synthetic_integration_double': True}
        self.recipe = deepcopy(recipe)
        self.constant_delta = constant_delta
        self.evaluated_points = 0
        active = recipe['left'] != 0. or recipe['right'] != 0.
        self.facts = {'chin_shape': {
            'requested': active, 'applied': active, 'reason': None,
            'operation_id': S.OP, 'version': 1, 'linked': recipe['linked'],
            'left': recipe['left'], 'right': recipe['right'],
            'evidence': 'synthetic_build_double_not_native_or_photo_acceptance'}}

    def evaluate(self, points):
        points = np.asarray(points, dtype=np.float64)
        self.evaluated_points += len(points)
        if self.constant_delta is not None:
            return np.tile(self.constant_delta, (len(points), 1)).astype(np.float64)
        h, w = self.shape
        offset = points - [(w-1)*.5, (h-1)*.60]
        radius = np.linalg.norm(offset/[w-1, h-1], axis=1)
        t = np.clip((radius-.10)/.12, 0., 1.)
        weight = 1. - t*t*(3.-2.*t)
        # Screen-right is the fixture's subject-left. This deliberately tiny
        # horizontal pullback only exercises side transport and canonical maps;
        # it does not reproduce the native forward/inverse or measured support.
        amount = np.where(offset[:, 0] >= 0., self.recipe['left'], self.recipe['right'])
        out = np.zeros_like(points, dtype=np.float64)
        out[:, 0] = -.008*offset[:, 0]*amount*weight
        return out

    def resident_bytes(self):
        return 96


def chin_builder(received, expected_shape, expected_recipe=ACTIVE):
    def build(landmarks, recipe, source, excluded, *, backend, analysis, protected_boxes):
        assert recipe == expected_recipe
        assert backend == 'mediapipe' and protected_boxes == ()
        assert landmarks is analysis['landmarks']
        assert source.shape == (*expected_shape, 3) and source.dtype == np.float32
        assert excluded is analysis['excluded'] and excluded.shape == expected_shape
        assert analysis['face_skin'].shape == expected_shape and not source.flags.writeable
        field = SyntheticChinField(expected_shape, recipe)
        received.append({'source': source.copy(), 'field': field,
                         'face_ref': deepcopy(analysis['face_ref']),
                         'observation': deepcopy(analysis['face_skin_observation'])})
        return field
    return build


def assert_canonical_result(prepared, ref, received, shape):
    key = ref['face_instance_id']
    assert type(prepared.geometry) is CombinedGeometry
    assert prepared.geometry.delta.shape == (1, *shape, 2)
    assert prepared.geometry.owner.shape == shape and prepared.geometry.face_ids == (key,)
    assert not prepared.geometry.delta.flags.writeable and not prepared.geometry.owner.flags.writeable
    assert prepared.geometry.peak > 0 and np.any(prepared.geometry.owner == 0)
    assert len(prepared.face_fields) == 1 and prepared.effects == ()
    face = prepared.face_fields[0]
    assert type(face) is PORT.ChinShape
    assert type(face.automatic) is AutomaticField and not face.automatic.units
    assert face.fields[:4] == (None,)*4 and face.fields[3] is None
    assert len(face.fields) == 5 and face.fields[4] is received['field']
    assert type(face.prefix) is FaceGeometry and face.prefix.fields == (None,)*4
    assert received['field'].evaluated_points == shape[0]*shape[1]
    assert received['face_ref'] == ref
    assert received['observation']['source_sha256'] == ref['asset_sha256']
    assert set(prepared.facts[key]) == {'chin_shape'}
    assert prepared.facts[key]['chin_shape'] is received['field'].facts
    assert prepared.plan['sample_policy'] == 'one_original_source_sample_after_composed_field'


def prefix_fixture(*, translation=None):
    """Real geometry classes and optional real TPS with synthetic controls."""
    state, ref, analysis, _ = fixture()
    source = original_pixels(128).astype(np.float32)/65535.
    # The existing deform validator rejects an empty dictionary; explicit zeros
    # exercise the unchanged production AutomaticField without inventing a bypass.
    automatic = AutomaticField(analysis['landmarks'], dict.fromkeys(D.KINDS, 0.), source.shape[:2])
    if translation is not None:
        points = np.array([[0., 0.], [127., 0.], [0., 127.], [127., 127.], [40., 45.], [85., 80.]])
        values = (np.array([[0., 0.], [.4, 0.], [0., .3], [.2, -.2], [.7, -.3], [-.2, .5]])
                  if translation == 'curved' else np.tile(translation, (len(points), 1)))
        tps_state = D.tps_solve(points, values, scale=128.)
        automatic.units.append((tps_state, 1., np.array([63.5, 63.5]), 100., 150.))
        automatic.windows.append((np.array([63.5, 63.5]), 100., 150.))
    prefix = FaceGeometry(ref['face_instance_id'], source.shape[:2], automatic, (None,)*4)
    return state, ref, analysis, source, prefix


def test_registry_defaults_and_derived_transport_keep_chin_shape_distinct():
    assert A.CHIN_SHAPE is S and S.OP == 'lnx.chin_shape.v1'
    assert A.GEOMETRY == ('lnx.brow_shape.v1', 'lnx.nose_shape.v1', 'lnx.eye_shape.v1', 'lnx.mouth_shape.v1')
    assert S.OP not in A.GEOMETRY and S.OP not in (A.DEFORM, C.OP, SLIM.OP, SIZE.OP, LOWER.OP, MID.OP)
    assert A.defaults()[S.OP] == {'/linked': True, '/left': 0., '/right': 0.}
    assert '/version' not in A.defaults()[S.OP] and S.OP in DERIVED.OPERATIONS
    entries = json.loads((ROOT/'docs/p0/registry-extensions.json').read_text())['entries']
    matching = [entry for entry in entries if entry['operation_id'] == S.OP]
    assert len(matching) == 1 and matching[0]['neutral'] == S.neutral()
    assert matching[0]['requirement_ids'] == ['LNX-REF-PC-32466-C-ed7837df9a']
    assert matching[0]['range']['version'] == [1, 1]
    assert matching[0]['range']['left'] == matching[0]['range']['right'] == [-1, 1]


@pytest.mark.parametrize('recipe', (*SIGNED_RECIPES, {'version': 1, 'linked': True, 'left': 0., 'right': 0.},
                                  {'version': 1, 'linked': False, 'left': 0., 'right': 0.}))
def test_exact_portable_intent_preserves_both_sides_and_link_flag(recipe):
    before = deepcopy(recipe)
    assert S.check(recipe) == recipe and recipe == before
    assert S.active(recipe) is (recipe['left'] != 0. or recipe['right'] != 0.)
    for path, value in A.leaves(recipe).items():
        # Leaf checks must not fabricate linked equality against neutral while
        # an actual atomic final recipe carries both sides and the link flag.
        DERIVED._leaf(S.OP, path, value)


@pytest.mark.parametrize('path,value', [('/left', True), ('/right', False), ('/left', '0.2'),
    ('/right', 1.1), ('/left', -1.1), ('/left', float('nan')), ('/right', float('inf')),
    ('/linked', 0), ('/linked', 'false'), ('/version', 1), ('/amount', .2),
    ('/small_chin', .2), ('/mask', []), ('/source_sha256', 'a'*64)])
def test_derived_transport_rejects_coercion_aliases_and_source_payloads(path, value):
    with pytest.raises(ValueError):
        DERIVED._leaf(S.OP, path, value)


@pytest.mark.parametrize('recipe', [True, [], {'left': .2, 'right': .2},
    {'version': True, 'linked': True, 'left': 0., 'right': 0.},
    {'version': 2, 'linked': True, 'left': 0., 'right': 0.},
    {'version': 1, 'linked': 1, 'left': 0., 'right': 0.},
    {'version': 1, 'linked': True, 'left': .2, 'right': .1},
    {'version': 1, 'linked': False, 'left': False, 'right': 0.},
    {'version': 1, 'linked': False, 'left': '0', 'right': 0.},
    {'version': 1, 'linked': False, 'left': float('nan'), 'right': 0.},
    {'version': 1, 'linked': False, 'left': 0., 'right': float('-inf')},
    {'version': 1, 'linked': False, 'left': 1.01, 'right': 0.},
    {'version': 1, 'linked': False, 'left': 0., 'right': -1.01},
    {'version': 1, 'linked': False, 'left': 0., 'right': 0., 'landmarks': []}])
def test_invalid_complete_recipes_are_rejected_before_build(recipe):
    with pytest.raises(ValueError):
        S.check(recipe)
    with patch.object(CORE, 'build') as build, pytest.raises(ValueError):
        PORT.append(object(), None, None, None, None, recipe)
    build.assert_not_called()


def test_linked_mismatch_in_resolved_graph_is_not_silently_repaired():
    state, ref, _, binding = fixture(recipe={'version': 1, 'linked': True, 'left': .2, 'right': .3})
    before = deepcopy(state)
    with pytest.raises(ValueError):
        A.recipes(RESOLVE.resolve(state, ref['face_instance_id'], A.defaults()))
    with pytest.raises(ValueError):
        DERIVED.require_graph(state, binding, document_id=None)
    assert state == before


@pytest.mark.parametrize('leaves,expected', [
    ([('/linked', True), ('/left', .35), ('/right', .35)],
     {'version': 1, 'linked': True, 'left': .35, 'right': .35}),
    ([('/right', -.35), ('/left', -.35), ('/linked', True)],
     {'version': 1, 'linked': True, 'left': -.35, 'right': -.35}),
    ([('/linked', False), ('/left', .45)],
     {'version': 1, 'linked': False, 'left': .45, 'right': 0.}),
    ([('/left', .45), ('/linked', False)],
     {'version': 1, 'linked': False, 'left': .45, 'right': 0.}),
])
def test_real_atomic_stage_accepts_complete_linked_or_independent_intent(leaves, expected):
    state, ref, _, binding = fixture(recipe=S.neutral())
    before = deepcopy(state)
    owner = PeopleGraphOwner(state)
    command = patch_command(state, ref, leaves)
    command_before = deepcopy(command)
    # The real derived leaf gate and real complete-recipe stage are separate
    # contracts: scalar preflight must admit both sides of one atomic update.
    DERIVED._patches(command['payload'])
    prepared = []
    result = EDIT.stage(command, state, document_id=DOCUMENT,
        document_epoch='synthetic-epoch', document_revision=7,
        asset_sha256=ref['asset_sha256'], source_dimensions=(128, 128),
        prepare=lambda candidate: prepared.append(deepcopy(candidate)))
    assert len(prepared) == 1 and prepared[0] == result['state']
    assert A.recipes(RESOLVE.resolve(result['state'], ref['face_instance_id'], A.defaults()))[S.OP] == expected
    DERIVED.require_graph(result['state'], binding, document_id=None)
    assert result['previous_revision'] == before['revision']
    assert state == before and command == command_before
    # Staging is not publication: the existing canonical owner is untouched.
    assert owner.snapshot() == before and owner.fence == 0


@pytest.mark.parametrize('starting,leaves', [
    ({'version': 1, 'linked': True, 'left': 0., 'right': 0.}, [('/left', .4)]),
    ({'version': 1, 'linked': True, 'left': 0., 'right': 0.},
     [('/linked', True), ('/left', .4), ('/right', .3)]),
    (ACTIVE, [('/linked', True)]),
])
def test_real_host_rejects_unequal_final_link_without_graph_or_history_publication(starting, leaves):
    """Real host/stage/owner; explicit host fixture, not dispatcher acceptance."""
    state, ref, _, binding = fixture(recipe=starting)
    owner = PeopleGraphOwner(state)
    before = owner.snapshot()
    history = {'undo': [owner.capture_document(ref['asset_sha256'])], 'redo': []}
    history_before = deepcopy(history)
    command = patch_command(state, ref, leaves)
    binding = {**binding, 'asset_sha256': ref['asset_sha256'], 'document_id': DOCUMENT,
               'document_epoch': 'synthetic-epoch', 'document_revision': 7}
    prepare_calls, publish_calls, events = [], [], []
    engine = SimpleNamespace(
        _guard_editable=lambda name: None, _people_bind=lambda: None,
        _people_binding=lambda: binding, _people_owner=lambda: owner,
        _people_source=lambda: {'sha256': ref['asset_sha256'], 'width': 128, 'height': 128},
        _people_prepare_graph=lambda *args: prepare_calls.append(args),
        _people_publish_graph=lambda *args: publish_calls.append(args),
        history=history)
    # Individual leaf transport is valid; the complete final recipe is not.
    DERIVED._patches(command['payload'])
    with pytest.raises(ValueError):
        HOST.apply(engine, {'cmd': 'people', **command}, events.append)
    assert not prepare_calls and not publish_calls and not events
    assert owner.snapshot() == before and owner.fence == 0
    assert owner.capture_document(ref['asset_sha256']) == history_before['undo'][0]
    assert engine.history is history and history == history_before
    assert engine._people_receipts[command['request_id']]['success'] is False


def test_history_snapshot_and_prior_operations_retain_independent_parameter_owners():
    neutral, ref, analysis, _ = fixture(recipe=S.neutral())
    key = ref['face_instance_id']
    old = P.set_override(neutral, 'face', key, A.DEFORM, '/small_chin', .6)
    for module, value in ((SIZE, -.3), (LOWER, .2), (MID, -.15)):
        old = P.set_override(old, 'face', key, module.OP, '/amount', value)
    current = set_recipe(neutral, key, ACTIVE)
    payload = {'people_graph': current, 'undo': [{'_people_state': old}], 'redo': [{'_people_state': neutral}]}
    restored = json.loads(json.dumps(payload, sort_keys=True, allow_nan=False))
    PROJECT.validate_records(restored)
    assert restored == payload
    for graph, expected, legacy, size, lower, mid in (
            (restored['people_graph'], ACTIVE, 0., 0., 0., 0.),
            (restored['undo'][0]['_people_state'], S.neutral(), .6, -.3, .2, -.15),
            (restored['redo'][0]['_people_state'], S.neutral(), 0., 0., 0., 0.)):
        values = A.recipes(RESOLVE.resolve(P.check(graph), key, A.defaults()))
        assert values[S.OP] == expected and values[A.DEFORM]['small_chin'] == legacy
        assert values[SIZE.OP]['amount'] == size and values[LOWER.OP]['amount'] == lower
        assert values[MID.OP]['amount'] == mid
        assert values[C.OP] == C.neutral() and values[SLIM.OP] == SLIM.neutral()
    snapshot = SNAP.capture(current, ref['asset_sha256'], {key: analysis})
    analysis['landmarks'][0, 0] += .001
    analysis['excluded'][0, 0], analysis['face_skin'][0, 0] = .4, .1
    current['overrides'].clear()
    assert A.recipes(RESOLVE.resolve(snapshot['state'], key, A.defaults()))[S.OP] == ACTIVE
    assert snapshot['analyses'][key]['landmarks'][0, 0] != analysis['landmarks'][0, 0]
    for name in ('landmarks', 'excluded', 'skin', 'face_skin'):
        assert not snapshot['analyses'][key][name].flags.writeable
        assert not np.shares_memory(snapshot['analyses'][key][name], analysis[name])
    assert snapshot['analyses'][key]['excluded'][0, 0] == 0.
    assert snapshot['analyses'][key]['face_skin'][0, 0] != .1


def test_old_saved_intent_does_not_inject_chin_shape_or_migrate_small_chin():
    state, ref, _, _ = fixture(recipe=S.neutral())
    state['overrides'] = []
    state = P.set_override(state, 'face', ref['face_instance_id'], A.DEFORM, '/small_chin', -.45)
    for module, value in ((SIZE, .25), (LOWER, -.2), (MID, .15)):
        state = P.set_override(state, 'face', ref['face_instance_id'], module.OP, '/amount', value)
    before = deepcopy(state)
    values = A.recipes(RESOLVE.resolve(state, ref['face_instance_id'], A.defaults()))
    assert values[S.OP] == S.neutral() and values[A.DEFORM]['small_chin'] == -.45
    assert values[SIZE.OP]['amount'] == .25 and values[LOWER.OP]['amount'] == -.2
    assert values[MID.OP]['amount'] == .15
    assert state == before and all(row['operation_id'] != S.OP for row in state['overrides'])


@pytest.mark.parametrize('path,expected', list(PRIOR_SOURCE_SHA256.items()))
def test_preserved_source_and_licenses_match_selected_baseline(path, expected):
    assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == expected


@pytest.mark.parametrize('linked', [False, True])
def test_neutral_append_needs_no_owner_anatomy_source_or_native_build(linked):
    original = object()
    neutral = {'version': 1, 'linked': linked, 'left': 0., 'right': 0.}
    with patch.object(CORE, 'build', side_effect=AssertionError('neutral reached chin build')) as build:
        assert PORT.append(original, None, None, None, None, neutral) == (original, None)
    build.assert_not_called()


def test_export_fastpath_blocks_either_side_and_sign_but_not_canonical_neutral():
    neutral, ref, _, _ = fixture(recipe=S.neutral())
    snapshot = {'state': neutral, 'asset_sha256': ref['asset_sha256']}
    assert not EXPORT.fastpath_blocker(snapshot)
    for recipe in SIGNED_RECIPES:
        changed = set_recipe(neutral, ref['face_instance_id'], recipe)
        assert EXPORT.fastpath_blocker({**snapshot, 'state': changed})
    # Existing export ownership conservatively treats a link-only deviation as
    # noncanonical intent. Do not weaken that owner or claim neutral passthrough;
    # the direct append test independently proves zero motion needs no build.
    unlinked = set_recipe(neutral, ref['face_instance_id'],
                          {'version': 1, 'linked': False, 'left': 0., 'right': 0.})
    assert EXPORT.fastpath_blocker({**snapshot, 'state': unlinked})


def test_neutral_export_without_analysis_preserves_original_rgb16():
    state, ref, _, _ = fixture(recipe=S.neutral())
    before = deepcopy(state)
    snapshot = SNAP.capture(state, ref['asset_sha256'], {})
    snapshot.update(document_id=DOCUMENT, support_assets={})
    pixels = original_pixels(128)
    with patch.object(CORE, 'build', side_effect=AssertionError('neutral reached chin build')) as build:
        prepared = ENGINE.prepare_export(snapshot, pixels, None, byte_budget=BUDGET, document_id=DOCUMENT)
    build.assert_not_called()
    assert prepared.face_fields == () and prepared.effects == () and prepared.facts == {}
    assert not prepared.plan['entries'][0]['requires_analysis']
    output = prepared.geometry.warp_original(pixels)
    np.testing.assert_array_equal(output, pixels)
    assert output.dtype == np.uint16 and state == before


def test_active_missing_analysis_refuses_before_chin_build_without_mutating_intent():
    state, ref, _, _ = fixture()
    before = deepcopy(state)
    snapshot = SNAP.capture(state, ref['asset_sha256'], {})
    snapshot.update(document_id=DOCUMENT, support_assets={})
    with patch.object(CORE, 'build', side_effect=AssertionError('missing evidence reached chin')) as build:
        with pytest.raises(RENDER.PeoplePreparationRefused) as error:
            ENGINE.prepare_export(snapshot, original_pixels(128), None, byte_budget=BUDGET, document_id=DOCUMENT)
    build.assert_not_called()
    assert len(error.value.refusals) == 1
    assert error.value.refusals[0]['face_instance_id'] == ref['face_instance_id']
    assert 'frozen_source_analysis_missing_or_stale' in str(error.value) and state == before


def test_append_preserves_owner_slots_and_returns_separate_chin_facts():
    state, ref, analysis, source, prefix = prefix_fixture()
    chin, before = SyntheticChinField(source.shape[:2], ACTIVE), source.copy()
    with patch.object(CORE, 'build', return_value=chin) as build:
        result, facts = PORT.append(prefix, state, ref, analysis, source, ACTIVE)
    assert type(result) is PORT.ChinShape and result.prefix is prefix
    assert result.automatic is prefix.automatic and result.face_instance_id == ref['face_instance_id']
    assert prefix.fields == (None,)*4 and result.fields == (*prefix.fields, chin)
    assert facts is chin.facts and result.resident_bytes() >= chin.resident_bytes()
    assert build.call_args.args[0] is analysis['landmarks'] and build.call_args.args[2] is source
    assert build.call_args.kwargs['analysis'] is analysis and build.call_args.kwargs['protected_boxes'] == ()
    np.testing.assert_array_equal(source, before)


@pytest.mark.parametrize('with_contour,with_size,with_lower,with_mid', list(product((False, True), repeat=4)))
def test_all_four_through_eight_slot_prefixes_preserve_mouth_and_outer_chin_composition(
        with_contour, with_size, with_lower, with_mid):
    """Real wrappers/TPS; every optional prior field is an explicit double.

    Corrected slim and standalone contour share ContouredFace and are mutually
    exclusive in production. This fixture covers that actual wrapper, not a
    claim of rendered equivalence or simultaneous slim/contour admission.
    """
    from lumaretouch_engine.face_contour_people import ContouredFace
    from lumaretouch_engine.face_size_people import SizedFace
    from lumaretouch_engine.lower_face_people import LowerFace
    from lumaretouch_engine.mid_face_people import MidFace
    state, ref, analysis, source, base = prefix_fixture(translation='curved')
    mouth = SimpleNamespace(state=None, resident_bytes=lambda: 0)
    base = FaceGeometry(base.face_instance_id, base.shape, base.automatic, (None, None, None, mouth))
    prefix, appended = base, []
    for enabled, wrapper, name, gain in (
            (with_contour, ContouredFace, 'contour_or_corrected_slim', [.003, .003]),
            (with_size, SizedFace, 'whole_face_size', [.002, .002]),
            (with_lower, LowerFace, 'lower_face', [0., .004]),
            (with_mid, MidFace, 'mid_face', [0., .005])):
        if not enabled:
            continue
        prior = SimpleNamespace(state={'synthetic_prior_composition_fixture': name},
            evaluate=lambda q, gain=gain: (np.asarray(q, dtype=np.float64)-[63.5, 63.5])*gain,
            resident_bytes=lambda: 64)
        prefix = wrapper(base.face_instance_id, base.shape, base.automatic, (*prefix.fields, prior), prefix, ())
        appended.append(prior)
    previous_fields = prefix.fields
    chin = SyntheticChinField(source.shape[:2], ACTIVE)
    with patch.object(CORE, 'build', return_value=chin) as build:
        result, facts = PORT.append(prefix, state, ref, analysis, source, ACTIVE)
    assert build.call_count == 1 and type(result) is PORT.ChinShape
    assert result.prefix is prefix and result.automatic is base.automatic
    assert len(prefix.fields) == 4+len(appended) and len(prefix.fields) in (4, 5, 6, 7, 8)
    assert prefix.fields is previous_fields and result.fields[:-1] == previous_fields
    assert result.fields[3] is mouth and result.fields[-1] is chin
    assert all(result.fields[4+i] is value for i, value in enumerate(appended))
    if with_mid:
        assert type(result.prefix) is MidFace
    assert facts is chin.facts
    points = np.array([[58., 53.], [68., 61.], [75., 70.]])
    before = points.copy()
    chin_delta, baseline = chin.evaluate(points), prefix.evaluate(points)
    expected = chin_delta+prefix.evaluate(points-chin_delta)
    np.testing.assert_allclose(result.evaluate(points), expected, rtol=0, atol=1e-12)
    assert not np.allclose(expected, baseline+chin_delta, rtol=0, atol=1e-9)
    assert not np.allclose(expected, baseline+chin.evaluate(points-baseline), rtol=0, atol=1e-9)
    np.testing.assert_array_equal(points, before)


def test_all_retained_same_source_neighbors_reach_chin_builder():
    state, ref, analysis, source, prefix = prefix_fixture()
    own = state['faces'][ref['face_instance_id']]
    for index, enabled in enumerate((False, True)):
        other = deepcopy(own)
        other.update(face_instance_id=f'neighbor-{index}', enabled=enabled,
                     box=[.05+index*.2, .1, .15+index*.2, .4])
        state['faces'][other['face_instance_id']] = other
    foreign = deepcopy(own)
    foreign.update(face_instance_id='other-source', asset_sha256='f'*64)
    state['faces']['other-source'] = foreign
    with patch.object(CORE, 'build', return_value=SyntheticChinField(source.shape[:2], ACTIVE)) as build:
        PORT.append(prefix, state, ref, analysis, source, ACTIVE)
    assert build.call_args.kwargs['protected_boxes'] == ((.05, .1, .15, .4), (.25, .1, .35, .4))


@pytest.mark.parametrize('change', ['identity', 'disabled', 'digest', 'grid', 'owner', 'slots'])
def test_stale_or_foreign_source_field_refuses_before_chin_build(change):
    state, ref, analysis, source, prefix = prefix_fixture()
    if change == 'identity': ref = {**ref, 'analysis_revision': ref['analysis_revision']+1}
    elif change == 'disabled': state['faces'][ref['face_instance_id']]['enabled'] = False
    elif change == 'digest': analysis['landmarks'][0, 0] += .001
    elif change == 'grid': prefix = FaceGeometry(prefix.face_instance_id, (64, 64), prefix.automatic, prefix.fields)
    elif change == 'owner': prefix = FaceGeometry('other-face', prefix.shape, prefix.automatic, prefix.fields)
    else: prefix = FaceGeometry(prefix.face_instance_id, prefix.shape, prefix.automatic, (None,)*9)
    with patch.object(CORE, 'build') as build, pytest.raises(ValueError):
        PORT.append(prefix, state, ref, analysis, source, ACTIVE)
    build.assert_not_called()


def test_repeated_chin_shape_cannot_acquire_a_second_geometry_owner():
    state, ref, analysis, source, prefix = prefix_fixture()
    with patch.object(CORE, 'build', return_value=SyntheticChinField(source.shape[:2], ACTIVE)) as build:
        result, _ = PORT.append(prefix, state, ref, analysis, source, ACTIVE)
        with pytest.raises(ValueError):
            PORT.append(result, state, ref, analysis, source, ACTIVE)
    assert build.call_count == 1 and prefix.fields == (None,)*4


@pytest.mark.parametrize('mode', ['missing', 'no_state', 'refused'])
def test_requested_missing_or_refused_chin_never_publishes_partial_geometry(mode):
    state, ref, analysis, source, prefix = prefix_fixture()
    chin = SyntheticChinField(source.shape[:2], ACTIVE)
    if mode == 'missing': chin = None
    elif mode == 'no_state': chin.state = None
    else: chin.facts['chin_shape'].update(applied=False, reason='synthetic_occlusion_refusal')
    with patch.object(CORE, 'build', return_value=chin), pytest.raises(ValueError):
        PORT.append(prefix, state, ref, analysis, source, ACTIVE)
    assert prefix.fields == (None,)*4


@pytest.mark.parametrize('stage', ['output', 'intermediate', 'final'])
def test_actual_composed_neighbor_footprints_are_protected(stage):
    translation = {'output': [-10., 0.], 'intermediate': [-30., 0.], 'final': [15., 0.]}[stage]
    point = np.array([[50. if stage == 'output' else 70., 50.]])
    delta = {'output': [-20., 0.], 'intermediate': [20., 0.], 'final': [5., 0.]}[stage]
    state, ref, analysis, source, prefix = prefix_fixture(translation=translation)
    neighbor = deepcopy(state['faces'][ref['face_instance_id']])
    neighbor.update(face_instance_id='protected-neighbor', enabled=False,
                    box=[49./127, 49./127, 51./127, 51./127])
    state['faces']['protected-neighbor'] = neighbor
    chin = SyntheticChinField(source.shape[:2], ACTIVE, constant_delta=delta)
    with patch.object(CORE, 'build', return_value=chin):
        result, _ = PORT.append(prefix, state, ref, analysis, source, ACTIVE)
    with pytest.raises(ValueError, match='another retained face'):
        result.evaluate(point)


@pytest.mark.parametrize('name', ['contour', 'size', 'lower', 'mid'])
def test_prior_wrapper_guard_is_preserved_when_chin_relocates_queries(name):
    from lumaretouch_engine.face_contour_people import ContouredFace
    from lumaretouch_engine.face_size_people import SizedFace
    from lumaretouch_engine.lower_face_people import LowerFace
    from lumaretouch_engine.mid_face_people import MidFace
    wrappers = {'contour': ContouredFace, 'size': SizedFace, 'lower': LowerFace, 'mid': MidFace}
    state, ref, analysis, source, base = prefix_fixture()
    protected = ((49./127, 49./127, 51./127, 51./127),)
    prior = SimpleNamespace(state={'synthetic_guard_fixture': name},
        evaluate=lambda q: np.tile([15., 0.], (len(q), 1)), resident_bytes=lambda: 64)
    prefix = wrappers[name](base.face_instance_id, base.shape, base.automatic,
                            (*base.fields, prior), base, protected)
    chin = SyntheticChinField(source.shape[:2], ACTIVE, constant_delta=[5., 0.])
    with patch.object(CORE, 'build', return_value=chin):
        result, _ = PORT.append(prefix, state, ref, analysis, source, ACTIVE)
    assert result.prefix is prefix and prefix.protected_boxes is protected
    assert result.protected_boxes == ()  # The veto comes from the retained owner.
    assert result.resident_bytes() >= prefix.resident_bytes()+chin.resident_bytes()
    with pytest.raises(ValueError, match='another retained face'):
        result.evaluate(np.array([[70., 50.]]))


def test_composed_out_of_image_sampling_refuses_instead_of_border_fill():
    state, ref, analysis, source, prefix = prefix_fixture()
    chin = SyntheticChinField(source.shape[:2], ACTIVE, constant_delta=[3., 0.])
    with patch.object(CORE, 'build', return_value=chin):
        result, _ = PORT.append(prefix, state, ref, analysis, source, ACTIVE)
    with pytest.raises(ValueError, match='outside the genuine source'):
        result.evaluate(np.array([[1., 50.]]))


@pytest.mark.parametrize('recipe', SIGNED_RECIPES)
def test_original_rgb16_and_derived_float_export_share_real_map_for_signed_sides(recipe):
    state, ref, analysis, binding = fixture(size=384, recipe=recipe)
    before = deepcopy(state)
    snapshot = SNAP.capture(state, ref['asset_sha256'], {ref['face_instance_id']: analysis})
    snapshot.update(document_id=DOCUMENT, support_assets={})
    derived = {**snapshot, 'creative_source': binding}
    original = original_pixels(384)
    original_before = original.copy()
    working = original.astype(np.float32)/65535.
    working_before = working.copy()
    assert np.any(original % 257 != 0)
    received = []
    with patch.object(CORE, 'build', side_effect=chin_builder(received, (384, 384), recipe)) as build:
        old = ENGINE.prepare_export(snapshot, original, None, byte_budget=BUDGET, document_id=DOCUMENT)
        new = ENGINE.prepare_export(derived, working, None, byte_budget=BUDGET, document_id=DOCUMENT)
    assert build.call_count == len(received) == 2
    for prepared, record in zip((old, new), received):
        assert_canonical_result(prepared, ref, record, (384, 384))
        np.testing.assert_array_equal(record['source'], working)
        assert record['observation']['producer_width'] == record['observation']['producer_height'] == 128
    assert received[0]['field'] is not received[1]['field']
    np.testing.assert_array_equal(old.geometry.delta, new.geometry.delta)
    np.testing.assert_array_equal(old.geometry.owner, new.geometry.owner)
    old_output, new_output = old.geometry.warp_original(original), new.geometry.warp(working)
    assert old_output.dtype == np.uint16 and old_output.shape == original.shape
    assert np.any(old_output != original) and np.any(new_output != working)
    np.testing.assert_allclose(old_output.astype(np.float64)/65535., new_output, rtol=0, atol=1.1/65535.)
    np.testing.assert_array_equal(original, original_before)
    np.testing.assert_array_equal(working, working_before)
    assert state == before and snapshot['state'] == before


@pytest.mark.parametrize('recipe', SIGNED_RECIPES)
def test_original_and_derived_preview_retain_real_repair_proof_and_sampler(recipe):
    torch = pytest.importorskip('torch')
    state, ref, analysis, binding = fixture(recipe=recipe)
    before = deepcopy(state)
    proxy = (original_pixels(128)//257).astype(np.uint8)
    working = proxy.astype(np.float32)/255.
    pipe = SimpleNamespace(src_f32=torch.from_numpy(working.copy()).permute(2, 0, 1)[None],
                           repair_base=None, repair_ops=[], redo_ops=[])
    proof = REPLAY.make_evidence(binding, working, None, REPAIRS.digest_ops([], [], binding))
    pipe._creative_repair_source = deepcopy(binding)
    pipe._creative_repair_input = deepcopy(proof['input'])
    pipe._creative_repair_evidence = proof
    received = []
    with patch.object(CORE, 'build', side_effect=chin_builder(received, (128, 128), recipe)) as build:
        old = ENGINE.prepare_preview(pipe, state, ref['asset_sha256'], {ref['face_instance_id']: analysis},
                                     byte_budget=BUDGET, document_id=DOCUMENT)
        new = ENGINE.prepare_preview(pipe, state, ref['asset_sha256'], {ref['face_instance_id']: analysis},
                                     byte_budget=BUDGET, document_id=DOCUMENT,
                                     creative_source=binding, creative_proxy=proxy)
    assert build.call_count == len(received) == 2
    for prepared, record in zip((old, new), received):
        assert_canonical_result(prepared, ref, record, (128, 128))
        np.testing.assert_array_equal(record['source'], working)
    np.testing.assert_array_equal(old.geometry.delta, new.geometry.delta)
    np.testing.assert_array_equal(old.geometry.warp(working), new.geometry.warp(working))
    assert REPLAY.verify_pipeline(pipe, binding) == proof and state == before
    np.testing.assert_array_equal(pipe.src_f32[0].permute(1, 2, 0).numpy(), working)


@pytest.mark.parametrize('derived', [False, True])
def test_export_rejects_other_source_dtype_before_chin_build(derived):
    state, ref, analysis, binding = fixture()
    snapshot = SNAP.capture(state, ref['asset_sha256'], {ref['face_instance_id']: analysis})
    snapshot.update(document_id=DOCUMENT, support_assets={})
    original = original_pixels(128)
    if derived:
        snapshot['creative_source'], wrong = binding, original
    else:
        wrong = original.astype(np.float32)/65535.
    with patch.object(CORE, 'build', side_effect=AssertionError('wrong dtype reached chin')) as build:
        with pytest.raises(ValueError, match='creative float32' if derived else 'original RGB8/16'):
            ENGINE.prepare_export(snapshot, wrong, None, byte_budget=BUDGET, document_id=DOCUMENT)
    build.assert_not_called()


@pytest.mark.parametrize('fault', ['missing', 'input_digest', 'stack_digest'])
def test_derived_preview_missing_or_tampered_real_repair_proof_refuses_before_chin(fault):
    torch = pytest.importorskip('torch')
    state, ref, analysis, binding = fixture()
    before = deepcopy(state)
    proxy = (original_pixels(128)//257).astype(np.uint8)
    working = proxy.astype(np.float32)/255.
    pipe = SimpleNamespace(src_f32=torch.from_numpy(working.copy()).permute(2, 0, 1)[None],
                           repair_base=None, repair_ops=[], redo_ops=[])
    if fault != 'missing':
        proof = REPLAY.make_evidence(binding, working, None, REPAIRS.digest_ops([], [], binding))
        pipe._creative_repair_source = deepcopy(binding)
        pipe._creative_repair_input = deepcopy(proof['input'])
        corrupted = deepcopy(proof)
        if fault == 'input_digest': corrupted['input']['sha256'] = 'f'*64
        else: corrupted['stack_sha256'] = 'f'*64
        pipe._creative_repair_evidence = corrupted
    with patch.object(CORE, 'build', side_effect=AssertionError('unverified repair reached chin')) as build:
        with pytest.raises(ValueError):
            ENGINE.prepare_preview(pipe, state, ref['asset_sha256'], {ref['face_instance_id']: analysis},
                                   byte_budget=BUDGET, document_id=DOCUMENT,
                                   creative_source=binding, creative_proxy=proxy)
    build.assert_not_called()
    assert state == before
    if fault != 'missing': assert pipe._creative_repair_evidence == corrupted
    np.testing.assert_array_equal(pipe.src_f32[0].permute(1, 2, 0).numpy(), working)


@pytest.mark.parametrize('fault', ['document', 'derived_source', 'budget'])
def test_export_owner_or_budget_refusal_does_not_use_proxy_fallback(fault):
    state, ref, analysis, binding = fixture(size=384)
    snapshot = SNAP.capture(state, ref['asset_sha256'], {ref['face_instance_id']: analysis})
    snapshot.update(document_id=DOCUMENT, support_assets={})
    source, budget = original_pixels(384), BUDGET
    if fault == 'document': snapshot['document_id'] = 'another-document'
    elif fault == 'derived_source':
        snapshot['creative_source'] = {**binding, 'sha256': 'f'*64}
        source = source.astype(np.float32)/65535.
    else: budget = 1
    with patch.object(CORE, 'build', side_effect=AssertionError('unowned source reached chin')) as build:
        with pytest.raises(ValueError):
            ENGINE.prepare_export(snapshot, source, None, byte_budget=budget, document_id=DOCUMENT)
    build.assert_not_called()


@pytest.mark.parametrize('refusal', ['missing', 'raised', 'nonfinite'])
def test_requested_export_failure_preserves_source_intent_and_snapshot(refusal):
    state, ref, analysis, _ = fixture()
    before = deepcopy(state)
    snapshot = SNAP.capture(state, ref['asset_sha256'], {ref['face_instance_id']: analysis})
    snapshot.update(document_id=DOCUMENT, support_assets={})
    pixels = original_pixels(128)
    pixels_before = pixels.copy()
    if refusal == 'raised': options = {'side_effect': ValueError('explicit synthetic chin-shape refusal')}
    elif refusal == 'missing': options = {'return_value': None}
    else: options = {'return_value': SyntheticChinField((128, 128), ACTIVE, constant_delta=[float('nan'), 0.])}
    with patch.object(CORE, 'build', **options) as build, pytest.raises(ValueError):
        ENGINE.prepare_export(snapshot, pixels, None, byte_budget=BUDGET, document_id=DOCUMENT)
    assert build.call_count == 1 and state == before and snapshot['state'] == before
    np.testing.assert_array_equal(pixels, pixels_before)


def test_derived_snapshot_keeps_chin_mid_lower_size_and_legacy_separate():
    state, ref, analysis, binding = fixture()
    for module, value in ((SIZE, -.3), (LOWER, .2), (MID, -.1)):
        state = P.set_override(state, 'face', ref['face_instance_id'], module.OP, '/amount', value)
    before = deepcopy(state)
    DERIVED.require_graph(state, binding, document_id=None)
    snapshot = SNAP.capture(state, ref['asset_sha256'], {ref['face_instance_id']: analysis})
    snapshot['creative_source'] = deepcopy(binding)
    resolved = A.recipes(RESOLVE.resolve(snapshot['state'], ref['face_instance_id'], A.defaults()))
    assert resolved[S.OP] == ACTIVE and resolved[A.DEFORM]['small_chin'] == 0.
    assert resolved[SIZE.OP]['amount'] == -.3 and resolved[LOWER.OP]['amount'] == .2
    assert resolved[MID.OP]['amount'] == -.1 and state == before


def test_source_routing_appends_chin_after_all_prior_geometry_without_moving_mouth_slot():
    text = (ROOT/'engine/src/lumaretouch_engine/people_render_runtime.py').read_text()
    tree = ast.parse(text)
    prepare = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'prepare')
    calls = [node for node in ast.walk(prepare) if isinstance(node, ast.Call)]
    def line(name):
        selected = [node.lineno for node in calls if
                    (isinstance(node.func, ast.Name) and node.func.id == name) or
                    (isinstance(node.func, ast.Attribute) and node.func.attr == name)]
        assert len(selected) == 1
        return selected[0]
    names = ('build_geometry', 'append_slim', 'append_contour', 'append_size', 'append_lower', 'append_mid', 'append_chin')
    assert [line(name) for name in names] == sorted(line(name) for name in names)
    assert 'mouth = field.fields[3]' in text and 'mouth = field.fields[-1]' not in text
    for key, name in (('chin_shape', 'chin'), ('mid_face', 'mid'), ('lower_face', 'lower'), ('face_size', 'size')):
        assert f"facts[key]['{key}'] = {name}_facts" in text


def test_integration_fixture_patches_only_declared_build_boundary():
    """Source contract only; it does not claim collection or runtime success."""
    tree = ast.parse(Path(__file__).read_text())
    patches = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
               and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
               and node.func.value.id == 'patch' and node.func.attr == 'object']
    assert patches
    for call in patches:
        assert len(call.args) >= 2 and isinstance(call.args[0], ast.Name) and call.args[0].id == 'CORE'
        assert isinstance(call.args[1], ast.Constant) and call.args[1].value == 'build'


def test_capability_and_offline_staging_are_connected_without_building():
    server = (ROOT/'engine/src/lumaretouch_engine/server.py').read_text()
    assert 'from .chin_shape_state import capability as chin_shape_capability' in server
    assert 'chin_shape_capability()' in server
    state_source = (ROOT/'engine/src/lumaretouch_engine/chin_shape_state.py').read_text()
    assert "'chin_shape_available'" in state_source and "'chin_shape_reason'" in state_source
    stage = (ROOT/'packaging/stage-engine.sh').read_text()
    assert 'build-chin-shape.sh' in stage and 'liblrt_chin_shape.so' in stage
    assert 'core/chin_shape/chin_shape.h' in stage and 'third_party/chin_shape/' in stage
    build = (ROOT/'packaging/build-chin-shape.sh').read_text()
    assert 'rustc --edition=2021 --crate-type cdylib' in build and 'core/chin_shape/lib.rs' in build
    assert not any(command in build for command in ('cargo build', 'curl ', 'wget ', 'pip install'))
