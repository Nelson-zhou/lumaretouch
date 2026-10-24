"""AUTHORED_UNRUN: canonical, independently owned philtrum integration.

All RGB, landmarks, observations and fields are synthetic contract fixtures,
not detector measurements, photographs or acceptance results. The ONLY patched
production boundary is philtrum_runtime.build. Its explicit vertical double
proves routing and common-map/source ownership, not the actual native inverse,
nose-to-lip geometry, fixed-nose anatomy, visibility or aesthetic quality. Prefix
cases keep real wrapper/TPS composition with named synthetic prior fields.
All 64 optional-prefix combinations retain the six preceding wrapper positions.
Philtrum adds no mutual exclusion. Existing chin-length/legacy incompatibility
is exercised separately and is never attributed to this new operation.
Host cases name their minimal host fixture; they do not claim UI/dispatcher,
disk-project, document-version or whole-application transaction acceptance.

No product import, collection/execution, native build, inference, numerical
probe, type check or download ran while authoring. Every fixture in this file
is AUTHORED_UNRUN. Source/hash assertions are future contracts, not completed
checks, pixel-parity results or claims that unchanged legacy defects were fixed.
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
from lumaretouch_engine import philtrum_state as S, philtrum_runtime as CORE
from lumaretouch_engine import philtrum_people as PORT, chin_shape_state as SHAPE
from lumaretouch_engine import chin_length_state as CHIN
from lumaretouch_engine import face_contour_state as CONTOUR, slim_face_state as SLIM
from lumaretouch_engine import face_size_state as SIZE, lower_face_state as LOWER, mid_face_state as MID
from lumaretouch_engine import people_algorithms as A, people_state as P
from lumaretouch_engine import people_binding as BIND
from lumaretouch_engine import people_associations as LINKS
from lumaretouch_engine import people_resolver as RESOLVE, people_project as PROJECT
from lumaretouch_engine import people_snapshot as SNAP, people_export as EXPORT
from lumaretouch_engine import people_render_runtime as RENDER, people_engine_runtime as ENGINE
from lumaretouch_engine import people_edit as EDIT, people_host_commands as HOST
from lumaretouch_engine import people_document_history as HISTORY
from lumaretouch_engine.people_host import PeopleHostMixin
from lumaretouch_engine.people_graph_owner import PeopleGraphOwner, affected_assets
from lumaretouch_engine import creative_derived_effects as DERIVED
from lumaretouch_engine import creative_derived_repairs as REPAIRS
from lumaretouch_engine import creative_derived_repair_runtime as REPLAY
from lumaretouch_engine.people_geometry import AutomaticField, FaceGeometry, CombinedGeometry
from lumaretouch_engine.ops import deform as D

ROOT = Path(__file__).resolve().parents[2]
BUDGET = 512 * 1024**2
DOCUMENT = 'synthetic-philtrum-document'
ACTIVE = {'version': 1, 'amount': .4}
SIGNED_RECIPES = tuple({'version': 1, 'amount': amount} for amount in (-1., -.4, .4, 1.))

# Read-only git-show bytes from the exact parent-selected baseline. This guards
# both unchanged shared native cores, old geometry, licenses and common sampler.
BASELINE = 'abcc23b076fd3673603da468fca0fc74f55e8a44'
PRIOR_SOURCE_SHA256 = {
    'LICENSE': '3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986',
    'NOTICE': '9c72edab63db61c46d1d866b6f5273ea2e502978cf495f14beccf09f0d00e622',
    'THIRD_PARTY_NOTICES': '338b0c8a100aada45f14ebe0e8d497a341313d5e38f6ed16a04e2e320e78caf0',
    'core/brow_shape/lib.rs': '04cf2c546a7c039ca3a88a64a704e71f9579a56afb802496223985d79ea65441',
    'core/chin_shape/Cargo.toml': '4c1606efee4e718562665e5e154f5a072852afcb292dc44d950ec8ae3420d1e2',
    'core/chin_shape/README.md': 'a9e9747a0d2820f25ed35452584a40c7dbd99c22fadb4707dce9a2942f1fa833',
    'core/chin_shape/chin_shape.h': '96de3aa46b87482fccceeb3487278030506e33764b50641175839f3c19697dbd',
    'core/chin_shape/lib.rs': '7803cf0021f8b07573d9d6989e2a69e7071323bd60aa8dbd6d59bccf5a769c54',
    'core/chin_shape/tests.rs': 'd18e5d0c7adb2a8b9ba1b82864c0d571bb2cf1ccff1f36d383777b4a67972a78',
    'core/eye_shape/lib.rs': '3817392fc8f44974b1fa7215c067e3fe966e813f76a2299bbc66afe142eb0a65',
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
    'core/mouth_shape/lib.rs': 'd54c251509e26db6b9151baa3af1ec44008a3705bf8541c1b134207339fb5bbc',
    'core/nose_shape/lib.rs': 'ecae8505dd4a1064857f0b6b1fece84ea8a4e79776bb64fa37d78d0c1fa3e3c9',
    'docs/model-licenses/README.md': '1353d52698f42217454ae1231a6d6cfa2405edea7738b0fb223f5417312dab8f',
    'docs/model-licenses/archive/mediapipe-LICENSE.txt': '8707eef0533987efc5b155d64761eeb6e20793f50b9bd1a68dad1cf4719d0ed8',
    'docs/model-licenses/archive/sam2-LICENSE.txt': 'c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4',
    'docs/model-licenses/archive/sam2-README.md': 'eea69ee1042fb30933c5ca5019fbf0f6f9366cec5e792109281b5023a4f1589c',
    'docs/model-licenses/archive/sam2.1-hiera-tiny-hf-tree.json': '6966c78030b9ddffc745a4c1ab030ee1cef98e740ba07ab245443ee6eee17abb',
    'docs/model-licenses/archive/sam2.1_hiera_t.yaml': 'f932eac1c6241e910031b2f000a81cd9f8a8d4896e2277ab5ffb721f378b188d',
    'docs/model-licenses/models.json': '3dcf5f9b45f0f8f6e58513b5d666a04dff6757911ec222cab270f1573ef5d43b',
    'docs/model-licenses/sam2.1-hiera-tiny-provenance.md': 'c2a7653685cde00cc148f4b26a0c58dcbb662f56fe7fa7bb7941341b26ac3018',
    'engine/src/lumaretouch_engine/brow_shape_command.py': '5da69fede2a6c8104e6e7cacbb0a0be42ad56c470a78cf599181c22cff1b370a',
    'engine/src/lumaretouch_engine/brow_shape_consumers.py': 'c947fbc72d279441c2a107cc968d805c93064eb5abf3fa5cac80db80864e2ce8',
    'engine/src/lumaretouch_engine/brow_shape_field.py': 'c1437ab499c12d0f9ab5f3e308776103f2332d66e06caaf21cc33b1742ff86ae',
    'engine/src/lumaretouch_engine/brow_shape_geometry.py': '267cbf7c2484a34b2e238445d572372f9ebb60461e3e4cd668a74c346a8863b5',
    'engine/src/lumaretouch_engine/brow_shape_native.py': 'e51d52ba00df7991ffc6b3c2571fa9bb042b90ad8ad371d5213d4d6eb1e827be',
    'engine/src/lumaretouch_engine/brow_shape_project.py': '41c8586690c9fa3a7765082275661eaefff745dd48a57292f3ee86d9bfd30f19',
    'engine/src/lumaretouch_engine/brow_shape_receipts.py': '807c5b77cfdf9ec5764373771bf79b6a393a535c5b36b3bf79aba377b8ba9bab',
    'engine/src/lumaretouch_engine/brow_shape_runtime.py': 'ad3682557c5e497d64faad441f573d876514bb2dd4068cf14c0ba8cd2911ae12',
    'engine/src/lumaretouch_engine/brow_shape_scope.py': '40b1f71a6ee4c09df11c20c9dba396dce33b535c0f2b997a35138d566112800f',
    'engine/src/lumaretouch_engine/brow_shape_state.py': 'a72ecef37656015ef3ba7ac2adae71ecb34c2d240b6fd40c31ed3017576cc95c',
    'engine/src/lumaretouch_engine/chin_length_native.py': '93cb3738e8f6a1dc03204aa8ebf9aa946f98a52792df5759686f7408586d2787',
    'engine/src/lumaretouch_engine/chin_length_people.py': 'ce5530a90ddfa3fe512d46f946d3e34bc397d70046a821711cd9b9da8fd149e6',
    'engine/src/lumaretouch_engine/chin_length_runtime.py': 'ee12d9f6670fd88893777ee786642ea2ddfba45590f6a23cd45e72cafe09e193',
    'engine/src/lumaretouch_engine/chin_length_scope.py': 'dbd09ae3efb903ef8257a8e4e96c9cb2071274641bf0af71e0f9a7e8abc6e7b7',
    'engine/src/lumaretouch_engine/chin_length_state.py': '772bcd6ca1c56b7bd65e877c140ae611bb1a2afe3191844dfc542801fc4ca8c8',
    'engine/src/lumaretouch_engine/chin_shape_native.py': 'c699eaa84906e8008398f2feff48aceeeafe01e598e4616b61898ec09ab73209',
    'engine/src/lumaretouch_engine/chin_shape_people.py': '032ab442fc9a295152d2f56ed5cb492b72a81df4f9b0be9120b3712cddbca327',
    'engine/src/lumaretouch_engine/chin_shape_runtime.py': 'e1466d2c4dadbdc51178ca5bea1d531f5f8d5d92979ab9561118a8dc1aaca3ea',
    'engine/src/lumaretouch_engine/chin_shape_scope.py': '161901a99d482d99340f0d5f0c917d2300be30a89672d43d38a543dc151f61b1',
    'engine/src/lumaretouch_engine/chin_shape_state.py': '223c4646febdcbe534b8c7853d465629a68de7f1f37345e6800ed563d3d9c8f9',
    'engine/src/lumaretouch_engine/eye_shape_command.py': 'e8791d71b1cd72a8ec4d334d97905671f3848d39569ac10d82e7098bc6f4bbbd',
    'engine/src/lumaretouch_engine/eye_shape_field.py': '0dec74c9a8f91b5d0dd10c101864964ac4c1701e28d797a37e699f22697c87d7',
    'engine/src/lumaretouch_engine/eye_shape_geometry.py': 'fbf65f20ba7cadaafa99a554f39791dd30f929e8cb169d7edec05a07bf7cd3b4',
    'engine/src/lumaretouch_engine/eye_shape_native.py': '32f3dc6925d628203e9a7b057a02a5d75af72b3a7f60a6de82a4af25c10faf3d',
    'engine/src/lumaretouch_engine/eye_shape_project.py': '661be0b7cef6a0afa8c659b6b96088114513ea543afb067c133960be1f75e6d1',
    'engine/src/lumaretouch_engine/eye_shape_receipts.py': 'e27a3d7c25fcb2dbe54ef99ed4eebafca615fcaae58044e55d8b177f8d54df41',
    'engine/src/lumaretouch_engine/eye_shape_runtime.py': 'a8d99c4a1ae090659936fa2dc4c1724114af6ca084e08cadd88f7a4068472ff7',
    'engine/src/lumaretouch_engine/eye_shape_scope.py': 'c7bf8d1f6977f6e1c33e37a8df6f581f6f74dc199a001e888e69fbae9341b0fd',
    'engine/src/lumaretouch_engine/eye_shape_state.py': 'b6861110bcd0f2b035cba9e10ff9073e14efd07719a687eee5a5e9d741497a47',
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
    'engine/src/lumaretouch_engine/mouth_shape_command.py': 'a61bf6ad4a46fdf17af54a7036db877212b1667f67ed4df68911a06dcca33720',
    'engine/src/lumaretouch_engine/mouth_shape_consumers.py': 'ffd3d53c70000adb3d346545c6429559ab41ac5b334e05290d7cfdc18322ffab',
    'engine/src/lumaretouch_engine/mouth_shape_field.py': '4252c9db63883d024c1a799dfaf0e1397263455b41eaa8c8600c88dac8cea4c9',
    'engine/src/lumaretouch_engine/mouth_shape_geometry.py': 'ff866e32296384f898a0a21bf7af55e9690c56a69c467da68b6c4ea7786d0758',
    'engine/src/lumaretouch_engine/mouth_shape_native.py': '865e69d57d9cc508a38a3f08d1534f696f2007b77979b5c13af6c1b442f4c02b',
    'engine/src/lumaretouch_engine/mouth_shape_project.py': 'daa33f1ee9639bcd51f35f98b23011e820d0956049c264217a262f842d425bae',
    'engine/src/lumaretouch_engine/mouth_shape_receipts.py': '9114a6074d57c854358f3afdf3f5480def824c423ef20d0061a76449b7ac6949',
    'engine/src/lumaretouch_engine/mouth_shape_runtime.py': 'b32f08c1d7ed876f11b029092d519b87d87e87b657f476b7b4eb02c6cba7a4f6',
    'engine/src/lumaretouch_engine/mouth_shape_scope.py': 'b2fe6b4d1eec27e4ebad603a9a238579e17ee5d2d846bfed58ba781e39d706f1',
    'engine/src/lumaretouch_engine/mouth_shape_state.py': 'c2dd57a00f1cc6b4a120bdbd5eab8b6d4397b8f7fca78e45f094e09dab101de8',
    'engine/src/lumaretouch_engine/nose_shape_command.py': 'b7618afa66e858513e7ff5cc2569a5af3e63b1ca9b4df19201eb9c716727b251',
    'engine/src/lumaretouch_engine/nose_shape_field.py': '0b1a00a3709250886f64d12dfd72d83e31314f1d7bf6acfc46390f3e743354af',
    'engine/src/lumaretouch_engine/nose_shape_geometry.py': '1643f4d0ead92e59487708e90b2bb5b5910b961063bc81b7fcfaf58dc7a162ce',
    'engine/src/lumaretouch_engine/nose_shape_native.py': '28c71c2e46c2e7ecfa58486ce3d36c3987cce4d566883d02ea3316cd420a1914',
    'engine/src/lumaretouch_engine/nose_shape_project.py': '1bdc787327e4ab3a6df5cfc3d43126cb49170534497db4e096108b9d5b194d7d',
    'engine/src/lumaretouch_engine/nose_shape_receipts.py': 'bb1b860fdab34bdf8ee4fd273dfe4406fe7b4b3f384a287e4a126c7b4824267b',
    'engine/src/lumaretouch_engine/nose_shape_runtime.py': '13483cd71eb87d37f5ebe0f436baed997fca707fcb5627bafb48760058500fdc',
    'engine/src/lumaretouch_engine/nose_shape_scope.py': 'c61c030cde14791250b6fac6acc6cfc08f148c8398706d123d27937ca0e417ba',
    'engine/src/lumaretouch_engine/nose_shape_state.py': 'dfc8d36e486f2dbb971d6b1b9211c152b57d3002b3089a8648153d1b4611a756',
    'engine/src/lumaretouch_engine/ops/deform.py': '5e0800bffa8f87f9f8e4f6cf8caa1ea782bee20d099a2232c869e0e9d53247fd',
    'engine/src/lumaretouch_engine/people_geometry.py': '554e4ea056f8c675be3b1fb859a2ca3101ca437dc1db52967e4151524955580b',
    'engine/src/lumaretouch_engine/people_legacy.py': '65af450866f8d769ac994ce3830294d355c06f151d1203d142f516dfaed6550a',
    'engine/src/lumaretouch_engine/people_legacy_review.py': '71de50b237e4eff5eb3862fb40389923f25323efbcc4e22488397d6012cf584f',
    'engine/src/lumaretouch_engine/people_migration.py': 'bfcb8feeef4f1a246ada02bf05fed6a315967b1e8208f4a1d972872b08d491ff',
    'engine/src/lumaretouch_engine/project_package_archive.py': '6a5b3210182b2a6504c538451456c11a486cca12ffe9a9c4ea2aed122651656a',
    'engine/src/lumaretouch_engine/slim_face_people.py': '6b4b8f4823bb5896a811d42d80288f87ec7c461d68982447b821e43c4815037d',
    'engine/src/lumaretouch_engine/slim_face_scope.py': '2030210fca69fbe1b555a66d182226425e09dc696fa95c760cfd39e47389da29',
    'engine/src/lumaretouch_engine/slim_face_state.py': 'af2425651ac89560b5f35632f850764e338812d2e16790eae53a7df61226ff57',
}


def set_recipe(state, key, recipe):
    for path, value in A.leaves(recipe).items():
        state = P.set_override(state, 'face', key, S.OP, path, value)
    return state


def resolved(state, ref):
    return A.recipes(RESOLVE.resolve(state, ref['face_instance_id'], A.defaults()))


def patch_command(state, ref, leaves):
    return {'document_id': DOCUMENT, 'document_epoch': 'synthetic-epoch', 'document_revision': 7,
            'state_revision': state['revision'], 'association_revision': state['association_revision'],
            'request_id': 'synthetic-philtrum-atomic-request', 'action': 'patch',
            'target': {'scope': 'face', 'target_id': ref['face_instance_id'], 'face_ref': deepcopy(ref)},
            'payload': {'patches': [{'operation_id': op, 'parameter_path': path,
                                    'unset': False, 'value': value} for op, path, value in leaves]}}


def stage(command, state, ref, *, prepare=None):
    return EDIT.stage(command, state, document_id=DOCUMENT, document_epoch='synthetic-epoch',
        document_revision=7, asset_sha256=ref['asset_sha256'], source_dimensions=(128, 128), prepare=prepare)


def fixture(*, size=128, recipe=ACTIVE):
    state, _, ref, _, analysis, _, _ = source_fixture(retained=False)
    state['links'], state['persons'] = [], {}
    for evidence in (state['faces'][ref['face_instance_id']]['evidence'], analysis['evidence']):
        evidence['source_width'] = evidence['source_height'] = size
    state = set_recipe(state, ref['face_instance_id'], recipe)
    return state, ref, analysis, {'sha256': ref['asset_sha256'], 'width': size, 'height': size}


def original_pixels(size):
    """RGB16 with genuine integer steps smaller than one RGB8 quantum."""
    yy, xx = np.indices((size, size), dtype=np.uint32)
    return np.stack(((xx*113 + yy*17) % 65536, (xx*37 + yy*101) % 65536,
                     (xx*53 + yy*61 + 12345) % 65536), axis=-1).astype(np.uint16)


def independent_target(asset, size, offset):
    """Fresh synthetic target inputs, never a donor analysis rebound at runtime.

    Separate synthetic measurements, observation records and sources are
    constructed independently before the normal owner/snapshot path is entered.
    This is a target-routing fixture, not a detector or source-authentication
    oracle. No production target evidence or rendering boundary is patched.
    """
    _, _, _, _, analysis, _, _ = source_fixture(retained=False)
    analysis['landmarks'] = np.array(analysis['landmarks'], dtype=np.float32, copy=True)
    analysis['landmarks'][:, 0] += np.float32(offset)
    evidence = deepcopy(analysis['evidence'])
    evidence.update(source_width=size, source_height=size,
                    landmark_digest=BIND.landmark_digest(analysis['landmarks']))
    face = P.new_face(asset, [.4+offset, .1, .6+offset, .3], evidence)
    state = P.empty()
    state['faces'][face['face_instance_id']] = face
    ref = P.face_ref(face)
    analysis.update(face_ref=deepcopy(ref), evidence=deepcopy(evidence))
    for name in ('face_skin_observation', 'body_skin_observation'):
        analysis[name] = {**analysis[name], 'source_sha256': asset}
    state = set_recipe(state, face['face_instance_id'], S.neutral())
    return state, ref, analysis, {'sha256': asset, 'width': size, 'height': size}


class SyntheticPhiltrumField:
    """Routing-only build double, never a native/anatomy/photo acceptance oracle."""
    def __init__(self, shape, recipe, *, constant_delta=None):
        self.shape, self.recipe = tuple(shape), deepcopy(recipe)
        self.state = {'synthetic_integration_double': True}
        self.constant_delta, self.evaluated_points = constant_delta, 0
        active = recipe['amount'] != 0.
        self.facts = {'philtrum': {
            'requested': active, 'applied': active, 'reason': None,
            'operation_id': S.OP, 'version': 1, 'amount': recipe['amount'],
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
        out = np.zeros_like(points, dtype=np.float64)
        # A tiny synthetic vertical pullback. It deliberately does not model
        # measured nose-safe support, lip plateau, or fixed-nose displacement.
        out[:, 1] = -.008*(offset[:, 1]+(h-1)*.05)*self.recipe['amount']*weight
        return out

    def resident_bytes(self):
        return 96


def philtrum_builder(received, expected_shape, expected_recipe=ACTIVE):
    def build(landmarks, recipe, source, excluded, *, backend, analysis, protected_boxes):
        assert recipe == expected_recipe and backend == 'mediapipe' and protected_boxes == ()
        assert landmarks is analysis['landmarks']
        assert source.shape == (*expected_shape, 3) and source.dtype == np.float32
        assert excluded is analysis['excluded'] and excluded.shape == expected_shape
        assert analysis['face_skin'].shape == expected_shape and not source.flags.writeable
        field = SyntheticPhiltrumField(expected_shape, recipe)
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
    assert type(face) is PORT.Philtrum
    assert type(face.automatic) is AutomaticField and not face.automatic.units
    assert face.fields[:4] == (None,)*4 and face.fields[3] is None
    assert len(face.fields) == 5 and face.fields[4] is received['field']
    assert type(face.prefix) is FaceGeometry and face.prefix.fields == (None,)*4
    assert received['field'].evaluated_points == shape[0]*shape[1]
    assert received['face_ref'] == ref
    assert received['observation']['source_sha256'] == ref['asset_sha256']
    assert set(prepared.facts[key]) == {'philtrum'}
    assert prepared.facts[key]['philtrum'] is received['field'].facts
    assert prepared.plan['sample_policy'] == 'one_original_source_sample_after_composed_field'


def prefix_fixture(*, translation=None):
    """Real original-owner geometry/TPS with explicitly synthetic controls."""
    state, ref, analysis, _ = fixture()
    source = original_pixels(128).astype(np.float32)/65535.
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


def test_registry_defaults_and_derived_transport_keep_philtrum_distinct():
    assert A.PHILTRUM is S and S.OP == 'lnx.philtrum.v1'
    assert A.GEOMETRY == ('lnx.brow_shape.v1', 'lnx.nose_shape.v1', 'lnx.eye_shape.v1', 'lnx.mouth_shape.v1')
    assert S.OP not in A.GEOMETRY and S.OP not in (A.DEFORM, CONTOUR.OP, SLIM.OP, SIZE.OP, LOWER.OP, MID.OP, SHAPE.OP, CHIN.OP)
    assert A.defaults()[S.OP] == {'/amount': 0.} and S.OP in DERIVED.OPERATIONS
    assert '/version' not in A.defaults()[S.OP] and '/small_chin' not in A.defaults()[S.OP]
    entries = json.loads((ROOT/'docs/p0/registry-extensions.json').read_text())['entries']
    matches = [entry for entry in entries if entry['operation_id'] == S.OP]
    assert len(matches) == 1 and matches[0]['neutral'] == S.neutral()
    assert matches[0]['requirement_ids'] == ['LNX-REF-PC-32466-C-2605502c27']
    assert matches[0]['range']['version'] == [1, 1] and matches[0]['range']['amount'] == [-1, 1]


@pytest.mark.parametrize('recipe', (*SIGNED_RECIPES, {'version': 1, 'amount': 0.}))
def test_exact_portable_signed_amount_survives_without_legacy_numeric_conversion(recipe):
    before = deepcopy(recipe)
    assert S.check(recipe) == recipe and recipe == before
    assert S.active(recipe) is (recipe['amount'] != 0.)
    DERIVED._leaf(S.OP, '/amount', recipe['amount'])
    state, ref, _, _ = fixture(recipe=recipe)
    restored = json.loads(json.dumps(state, sort_keys=True, allow_nan=False))
    assert resolved(restored, ref)[S.OP] == recipe
    assert resolved(restored, ref)[A.DEFORM]['small_chin'] == 0.


@pytest.mark.parametrize('path,value', [('/amount', True), ('/amount', '0.2'), ('/amount', 1.1),
    ('/amount', -1.1), ('/amount', float('nan')), ('/amount', float('inf')), ('/version', 1),
    ('/small_chin', .2), ('/left', .2), ('/linked', True), ('/mask', []), ('/source_sha256', 'a'*64)])
def test_derived_transport_rejects_coercion_aliases_and_source_payloads(path, value):
    with pytest.raises(ValueError):
        DERIVED._leaf(S.OP, path, value)


@pytest.mark.parametrize('recipe', [True, [], {'amount': .2}, {'version': True, 'amount': 0.},
    {'version': 2, 'amount': 0.}, {'version': 1, 'amount': False}, {'version': 1, 'amount': '0'},
    {'version': 1, 'amount': float('nan')}, {'version': 1, 'amount': float('-inf')},
    {'version': 1, 'amount': 1.01}, {'version': 1, 'amount': -1.01},
    {'version': 1, 'amount': 0., 'landmarks': []}])
def test_invalid_complete_recipes_refuse_before_build(recipe):
    with pytest.raises(ValueError):
        S.check(recipe)
    with patch.object(CORE, 'build') as build, pytest.raises(ValueError):
        PORT.append(object(), None, None, None, None, recipe)
    build.assert_not_called()


@pytest.mark.parametrize('legacy', [-.65, .65])
def test_old_saved_intent_does_not_inject_length_or_reinterpret_small_chin(legacy):
    state, ref, _, _ = fixture(recipe=S.neutral())
    state['overrides'] = []
    state = P.set_override(state, 'face', ref['face_instance_id'], A.DEFORM, '/small_chin', legacy)
    for module, amount in ((SIZE, .25), (LOWER, -.2), (MID, .15)):
        state = P.set_override(state, 'face', ref['face_instance_id'], module.OP, '/amount', amount)
    before = deepcopy(state)
    values = resolved(state, ref)
    assert values[S.OP] == S.neutral() and values[A.DEFORM]['small_chin'] == legacy
    assert values[SHAPE.OP] == SHAPE.neutral() and values[SIZE.OP]['amount'] == .25
    assert values[LOWER.OP]['amount'] == -.2 and values[MID.OP]['amount'] == .15
    assert state == before and all(row['operation_id'] != S.OP for row in state['overrides'])


@pytest.mark.parametrize('legacy,chin', [(-.6, 0.), (.6, 0.), (0., -.35), (0., .35)])
@pytest.mark.parametrize('amount', [-.4, .4])
def test_philtrum_only_edit_has_no_new_exclusion_and_preserves_existing_intent(legacy, chin, amount):
    state, ref, _, binding = fixture(recipe=S.neutral())
    key = ref['face_instance_id']
    state = P.set_override(state, 'face', key, A.DEFORM, '/small_chin', legacy)
    state = P.set_override(state, 'face', key, CHIN.OP, '/amount', chin)
    state = P.set_override(state, 'face', key, A.GEOMETRY[3], '/vertical', -.23)
    before, owner = deepcopy(state), PeopleGraphOwner(state)
    history_before = {'_people_history': owner.capture_document(ref['asset_sha256'])}
    command = patch_command(state, ref, [(S.OP, '/amount', amount)])
    result = stage(command, state, ref)
    values = resolved(result['state'], ref)
    A.validate_compatibility(values)
    DERIVED.require_graph(result['state'], binding, document_id=None)
    assert values[S.OP] == {'version': 1, 'amount': amount}
    assert values[A.DEFORM]['small_chin'] == legacy and values[CHIN.OP]['amount'] == chin
    assert values[A.GEOMETRY[3]]['vertical'] == -.23
    assert [row for row in result['state']['overrides'] if row['operation_id'] != S.OP] == [
        row for row in before['overrides'] if row['operation_id'] != S.OP]
    owner.commit(result['state'], expected_fence=0)
    record = HISTORY.decorate(history_before, {'_people_history': owner.capture_document(ref['asset_sha256'])})
    changes = record[HISTORY.KEY]['changes']
    assert len(changes) == 1 and tuple(changes[0]['key'][-2:]) == (S.OP, '/amount')
    undone = HISTORY.restore(owner, record[HISTORY.KEY], ref['asset_sha256'])
    assert resolved(undone, ref)[S.OP] == S.neutral()
    assert resolved(undone, ref)[A.DEFORM]['small_chin'] == legacy
    assert resolved(undone, ref)[CHIN.OP]['amount'] == chin and state == before


@pytest.mark.parametrize('amount', [-.4, 0., .4])
def test_preexisting_chin_conflict_is_readable_but_render_and_stage_still_refuse(amount):
    state, ref, analysis, binding = fixture(recipe={'version': 1, 'amount': amount})
    key = ref['face_instance_id']
    state = P.set_override(state, 'face', key, CHIN.OP, '/amount', .31)
    state = P.set_override(state, 'face', key, A.DEFORM, '/small_chin', -.6)
    before, prepared = deepcopy(state), []
    values = resolved(state, ref)
    assert values[S.OP]['amount'] == amount and values[CHIN.OP]['amount'] == .31
    assert values[A.DEFORM]['small_chin'] == -.6
    DERIVED.require_graph(state, binding, document_id=None)
    PROJECT.validate_records({'people_graph': state})
    snapshot = SNAP.capture(state, ref['asset_sha256'], {key: analysis})
    snapshot.update(document_id=DOCUMENT, support_assets={})
    original = original_pixels(128)
    with patch.object(CORE, 'build') as build:
        with pytest.raises(ValueError):
            A.validate_compatibility(values)
        with pytest.raises(ValueError):
            stage(patch_command(state, ref, [(S.OP, '/amount', 0.)]), state, ref,
                  prepare=lambda candidate: prepared.append(candidate))
        for frozen, pixels in ((snapshot, original),
                ({**snapshot, 'creative_source': binding}, original.astype(np.float32)/65535.)):
            with pytest.raises(ValueError):
                ENGINE.prepare_export(frozen, pixels, None, byte_budget=BUDGET, document_id=DOCUMENT)
    build.assert_not_called()
    assert not prepared and state == before and snapshot['state'] == before


@pytest.mark.parametrize('dormant', ['disabled_same_source', 'enabled_other_source'])
def test_dormant_existing_chin_conflict_does_not_block_current_source_philtrum_edit(dormant):
    state, ref, _, _ = fixture(recipe=S.neutral())
    own = state['faces'][ref['face_instance_id']]
    other = deepcopy(own)
    other.update(face_instance_id='dormant-prior-chin-conflict', enabled=dormant == 'enabled_other_source')
    if dormant == 'enabled_other_source':
        other['asset_sha256'] = 'f'*64
    state['faces'][other['face_instance_id']] = other
    state = P.set_override(state, 'face', other['face_instance_id'], CHIN.OP, '/amount', -.32)
    state = P.set_override(state, 'face', other['face_instance_id'], A.DEFORM, '/small_chin', .6)
    before, prepared = deepcopy(state), []
    with patch.object(CORE, 'build') as build:
        result = stage(patch_command(state, ref, [(S.OP, '/amount', -.4)]), state, ref,
                       prepare=lambda candidate: prepared.append(deepcopy(candidate)))
    build.assert_not_called()
    assert prepared == [result['state']] and state == before
    assert resolved(result['state'], ref)[S.OP]['amount'] == -.4
    assert result['state']['faces'][other['face_instance_id']] == before['faces'][other['face_instance_id']]
    prior = resolved(result['state'], P.face_ref(other))
    assert prior[CHIN.OP]['amount'] == -.32 and prior[A.DEFORM]['small_chin'] == .6
    with pytest.raises(ValueError):
        A.validate_compatibility(prior)


def test_reenabling_existing_chin_conflict_still_refuses_before_prepare_or_publication():
    state, ref, _, _ = fixture()
    key = ref['face_instance_id']
    state['faces'][key]['enabled'] = False
    state = P.set_override(state, 'face', key, CHIN.OP, '/amount', .3)
    state = P.set_override(state, 'face', key, A.DEFORM, '/small_chin', -.6)
    before, owner, prepared = deepcopy(state), PeopleGraphOwner(state), []
    command = patch_command(state, ref, [])
    command.update(action='face_status', payload={'enabled': True})
    with patch.object(CORE, 'build') as build, pytest.raises(ValueError):
        stage(command, state, ref, prepare=lambda candidate: prepared.append(candidate))
    build.assert_not_called()
    assert not prepared and state == before and owner.snapshot() == before and owner.fence == 0


@pytest.mark.parametrize('legacy,new,reverse', list(product((-.65, .65), (-.37, .37), (False, True))))
def test_explicit_independent_multioperation_edit_undo_redo_restores_both(legacy, new, reverse):
    """The command explicitly edits both leaves; philtrum never requires this."""
    state, ref, _, binding = fixture(recipe=S.neutral())
    key, asset = ref['face_instance_id'], ref['asset_sha256']
    state = P.set_override(state, 'face', key, A.DEFORM, '/small_chin', legacy)
    before, owner = deepcopy(state), PeopleGraphOwner(state)
    history_before = {'_people_history': owner.capture_document(asset)}
    leaves = [(A.DEFORM, '/small_chin', 0.), (S.OP, '/amount', new)]
    if reverse: leaves.reverse()
    command = patch_command(state, ref, leaves)
    command_before, prepared = deepcopy(command), []
    DERIVED._patches(command['payload'])
    result = stage(command, state, ref, prepare=lambda candidate: prepared.append(deepcopy(candidate)))
    assert len(prepared) == 1 and prepared[0] == result['state']
    assert result['previous_revision'] == before['revision']
    assert resolved(result['state'], ref)[S.OP] == {'version': 1, 'amount': new}
    assert resolved(result['state'], ref)[A.DEFORM]['small_chin'] == 0.
    DERIVED.require_graph(result['state'], binding, document_id=None)
    assert owner.snapshot() == before and owner.fence == 0
    assert state == before and command == command_before and abs(new) != abs(legacy)
    published = owner.commit(result['state'], expected_fence=0)
    assert owner.fence == 1
    history_after = {'_people_history': owner.capture_document(asset)}
    undo_record = HISTORY.decorate(history_before, history_after)
    changes = undo_record[HISTORY.KEY]['changes']
    assert len(changes) == 2 and all(change['collection'] == 'overrides' for change in changes)
    assert {tuple(change['key'][-2:]) for change in changes} == {(A.DEFORM, '/small_chin'), (S.OP, '/amount')}
    undo_candidate = HISTORY.restore(owner, undo_record[HISTORY.KEY], asset)
    assert owner.snapshot() == published and owner.fence == 1
    assert resolved(undo_candidate, ref)[A.DEFORM]['small_chin'] == legacy
    assert resolved(undo_candidate, ref)[S.OP] == S.neutral()
    owner.commit(undo_candidate, expected_fence=1)
    assert owner.fence == 2
    # Redo is the inverse transition in the SAME sparse history protocol.
    redo_record = HISTORY.decorate(history_after, {'_people_history': owner.capture_document(asset)})
    redo_candidate = HISTORY.restore(owner, redo_record[HISTORY.KEY], asset)
    assert resolved(redo_candidate, ref)[S.OP]['amount'] == new
    assert resolved(redo_candidate, ref)[A.DEFORM]['small_chin'] == 0.
    owner.commit(redo_candidate, expected_fence=2)
    assert owner.fence == 3 and resolved(owner.snapshot(), ref)[S.OP]['amount'] == new


def test_multioperation_undo_refuses_overwriting_later_amount_without_half_restoration():
    state, ref, _, _ = fixture(recipe=S.neutral())
    state = P.set_override(state, 'face', ref['face_instance_id'], A.DEFORM, '/small_chin', .6)
    owner, asset = PeopleGraphOwner(state), ref['asset_sha256']
    before = {'_people_history': owner.capture_document(asset)}
    command = patch_command(state, ref, [(A.DEFORM, '/small_chin', 0.), (S.OP, '/amount', -.35)])
    owner.commit(stage(command, state, ref)['state'], expected_fence=0)
    transition = HISTORY.decorate(before, {'_people_history': owner.capture_document(asset)})[HISTORY.KEY]
    later = set_recipe(owner.snapshot(), ref['face_instance_id'], {'version': 1, 'amount': .2})
    owner.commit(later, expected_fence=1)
    protected, fence = owner.snapshot(), owner.fence
    with pytest.raises(ValueError, match='protected undo refused'):
        HISTORY.restore(owner, transition, asset)
    assert owner.snapshot() == protected and owner.fence == fence
    assert resolved(protected, ref)[S.OP]['amount'] == .2
    assert resolved(protected, ref)[A.DEFORM]['small_chin'] == 0.


def test_explicit_two_leaf_edit_preserves_other_faces_and_undo_provenance():
    state, ref, _, _ = fixture(recipe=S.neutral())
    key, asset = ref['face_instance_id'], ref['asset_sha256']
    other = deepcopy(state['faces'][key])
    other['face_instance_id'] = 'unselected-inherited-legacy-face'
    state['faces'][other['face_instance_id']] = other
    other_ref = P.face_ref(other)
    state = P.set_override(state, 'all_people', asset, A.DEFORM, '/small_chin', .61)
    owner = PeopleGraphOwner(state)
    before = {'_people_history': owner.capture_document(asset)}
    command = patch_command(state, ref, [(A.DEFORM, '/small_chin', 0.), (S.OP, '/amount', -.27)])
    result = stage(command, state, ref)
    assert resolved(result['state'], ref)[S.OP]['amount'] == -.27
    assert resolved(result['state'], ref)[A.DEFORM]['small_chin'] == 0.
    assert resolved(result['state'], other_ref)[A.DEFORM]['small_chin'] == .61
    assert resolved(result['state'], other_ref)[S.OP] == S.neutral()
    assert [row for row in result['state']['overrides'] if row['scope'] == 'all_people'] == [
        row for row in state['overrides'] if row['scope'] == 'all_people']
    owner.commit(result['state'], expected_fence=0)
    record = HISTORY.decorate(before, {'_people_history': owner.capture_document(asset)})
    assert all(change['key'][:2] == ['face', key] for change in record[HISTORY.KEY]['changes'])
    restored = HISTORY.restore(owner, record[HISTORY.KEY], asset)
    effective = RESOLVE.resolve(restored, key, A.defaults())['operations'][A.DEFORM]['/small_chin']
    assert effective['value'] == .61 and effective['scope'] == 'all_people'
    assert resolved(restored, ref)[S.OP] == S.neutral()
    assert resolved(restored, other_ref)[A.DEFORM]['small_chin'] == .61


@pytest.mark.parametrize('failure', ['preparation', 'publication'])
def test_real_host_explicit_two_leaf_failure_rolls_back_without_rewinding_fences(failure):
    """Actual host/stage/export/publish/owner; fake host IO is explicit.

    An empty document table avoids filesystem/version IO. A deliberate sync
    failure exercises the real PeopleHostMixin rollback, not a fake commit.
    """
    state, ref, analysis, binding = fixture(recipe=S.neutral())
    state = P.set_override(state, 'face', ref['face_instance_id'], A.DEFORM, '/small_chin', .63)
    before, owner = deepcopy(state), PeopleGraphOwner(state)
    command = patch_command(state, ref, [(A.DEFORM, '/small_chin', 0.), (S.OP, '/amount', -.37)])
    pixels, received, prepared, syncs, events = original_pixels(128), [], [], [], []
    pixels_before = pixels.copy()
    history = {'undo': [owner.capture_document(ref['asset_sha256'])], 'redo': []}
    history_before = deepcopy(history)
    engine = SimpleNamespace(_guard_editable=lambda name: None, _people_bind=lambda: None,
        _people_binding=lambda: {**binding, 'asset_sha256': ref['asset_sha256'], 'document_id': DOCUMENT,
            'document_epoch': 'synthetic-epoch', 'document_revision': 7},
        _people_owner=lambda: owner, _people_source=lambda: binding,
        _docs=[], _doc_index=-1, _vram=object(), history=history)
    def prepare(candidate, assets):
        assert assets == {ref['asset_sha256']}
        snapshot = SNAP.capture(candidate, ref['asset_sha256'], {ref['face_instance_id']: analysis})
        snapshot.update(document_id=DOCUMENT, support_assets={})
        prepared.append(ENGINE.prepare_export(snapshot, pixels, None, byte_budget=BUDGET, document_id=DOCUMENT))
    def sync(*, strict):
        assert strict is True
        syncs.append(owner.snapshot())
        if len(syncs) == 1:
            raise ValueError('synthetic host publication sync refusal')
    engine._people_prepare_graph = prepare
    engine._people_sync = sync
    engine._people_publish_graph = lambda candidate, assets: PeopleHostMixin._people_publish_graph(engine, candidate, assets)
    options = ({'side_effect': ValueError('synthetic philtrum preparation refusal')} if failure == 'preparation'
               else {'side_effect': philtrum_builder(received, (128, 128), {'version': 1, 'amount': -.37})})
    with patch.object(CORE, 'build', **options) as build, pytest.raises(ValueError, match='synthetic'):
        HOST.apply(engine, {'cmd': 'people', **command}, events.append)
    assert build.call_count == 1 and not events and state == before
    assert engine.history is history and history == history_before
    assert engine._people_receipts[command['request_id']]['success'] is False
    current = owner.snapshot()
    assert current['overrides'] == before['overrides'] and current['faces'] == before['faces']
    assert resolved(current, ref)[S.OP] == S.neutral() and resolved(current, ref)[A.DEFORM]['small_chin'] == .63
    if failure == 'preparation':
        assert not prepared and not syncs and owner.fence == 0 and current == before
    else:
        assert len(prepared) == 1 and len(syncs) == 2 and owner.fence == 2
        assert resolved(syncs[0], ref)[S.OP]['amount'] == -.37
        assert resolved(syncs[0], ref)[A.DEFORM]['small_chin'] == 0.
        assert resolved(syncs[1], ref)[S.OP] == S.neutral() and engine._people_staged is None
        assert current['revision'] > before['revision']
    np.testing.assert_array_equal(pixels, pixels_before)


def test_history_project_and_frozen_snapshot_keep_all_parameter_owners_separate():
    neutral, ref, analysis, binding = fixture(recipe=S.neutral())
    key = ref['face_instance_id']
    old = P.set_override(neutral, 'face', key, A.DEFORM, '/small_chin', .6)
    current = set_recipe(neutral, key, ACTIVE)
    for module, amount in ((SIZE, -.3), (LOWER, .2), (MID, -.15), (CHIN, .12)):
        current = P.set_override(current, 'face', key, module.OP, '/amount', amount)
    shape_recipe = {'version': 1, 'linked': False, 'left': .2, 'right': -.1}
    for path, value in A.leaves(shape_recipe).items():
        current = P.set_override(current, 'face', key, SHAPE.OP, path, value)
    payload = {'people_graph': current, 'undo': [{'_people_state': old}], 'redo': [{'_people_state': neutral}]}
    restored = json.loads(json.dumps(payload, sort_keys=True, allow_nan=False))
    PROJECT.validate_records(restored)
    assert restored == payload
    values = resolved(restored['people_graph'], ref)
    assert values[S.OP] == ACTIVE and values[SHAPE.OP] == shape_recipe
    assert values[A.DEFORM]['small_chin'] == 0. and values[SIZE.OP]['amount'] == -.3
    assert values[LOWER.OP]['amount'] == .2 and values[MID.OP]['amount'] == -.15
    assert values[CHIN.OP]['amount'] == .12
    assert values[CONTOUR.OP] == CONTOUR.neutral() and values[SLIM.OP] == SLIM.neutral()
    assert resolved(restored['undo'][0]['_people_state'], ref)[A.DEFORM]['small_chin'] == .6
    assert resolved(restored['undo'][0]['_people_state'], ref)[S.OP] == S.neutral()
    assert resolved(restored['redo'][0]['_people_state'], ref)[S.OP] == S.neutral()
    DERIVED.require_graph(current, binding, document_id=None)
    snapshot = SNAP.capture(current, ref['asset_sha256'], {key: analysis})
    analysis['landmarks'][0, 0] += .001
    analysis['excluded'][0, 0], analysis['face_skin'][0, 0] = .4, .1
    current['overrides'].clear()
    assert resolved(snapshot['state'], ref)[S.OP] == ACTIVE
    assert resolved(snapshot['state'], ref)[SHAPE.OP] == shape_recipe
    assert snapshot['analyses'][key]['landmarks'][0, 0] != analysis['landmarks'][0, 0]
    for name in ('landmarks', 'excluded', 'skin', 'face_skin'):
        assert not snapshot['analyses'][key][name].flags.writeable
        assert not np.shares_memory(snapshot['analyses'][key][name], analysis[name])
    assert snapshot['analyses'][key]['excluded'][0, 0] == 0.
    assert snapshot['analyses'][key]['face_skin'][0, 0] != .1


@pytest.mark.parametrize('path,expected', list(PRIOR_SOURCE_SHA256.items()))
def test_preserved_legacy_geometry_native_archives_and_common_sampler_match_baseline(path, expected):
    assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == expected


def test_neutral_append_needs_no_owner_anatomy_source_or_legacy_native_build():
    original = object()
    with patch.object(CORE, 'build', side_effect=AssertionError('neutral reached new build')) as build:
        assert PORT.append(original, None, None, None, None, S.neutral()) == (original, None)
    build.assert_not_called()


def test_export_fastpath_blocks_both_signs_but_not_neutral():
    state, ref, _, _ = fixture(recipe=S.neutral())
    snapshot = {'state': state, 'asset_sha256': ref['asset_sha256']}
    assert not EXPORT.fastpath_blocker(snapshot)
    for recipe in SIGNED_RECIPES:
        changed = set_recipe(state, ref['face_instance_id'], recipe)
        assert EXPORT.fastpath_blocker({**snapshot, 'state': changed})


def test_neutral_export_without_analysis_preserves_original_rgb16():
    state, ref, _, _ = fixture(recipe=S.neutral())
    before = deepcopy(state)
    snapshot = SNAP.capture(state, ref['asset_sha256'], {})
    snapshot.update(document_id=DOCUMENT, support_assets={})
    pixels = original_pixels(128)
    with patch.object(CORE, 'build', side_effect=AssertionError('neutral reached new build')) as build:
        prepared = ENGINE.prepare_export(snapshot, pixels, None, byte_budget=BUDGET, document_id=DOCUMENT)
    build.assert_not_called()
    assert prepared.face_fields == () and prepared.effects == () and prepared.facts == {}
    assert not prepared.plan['entries'][0]['requires_analysis']
    output = prepared.geometry.warp_original(pixels)
    np.testing.assert_array_equal(output, pixels)
    assert output.dtype == np.uint16 and state == before


def test_active_missing_analysis_refuses_before_new_build_without_changing_intent():
    state, ref, _, _ = fixture()
    before = deepcopy(state)
    snapshot = SNAP.capture(state, ref['asset_sha256'], {})
    snapshot.update(document_id=DOCUMENT, support_assets={})
    with patch.object(CORE, 'build') as build, pytest.raises(RENDER.PeoplePreparationRefused) as error:
        ENGINE.prepare_export(snapshot, original_pixels(128), None, byte_budget=BUDGET, document_id=DOCUMENT)
    build.assert_not_called()
    assert len(error.value.refusals) == 1 and error.value.refusals[0]['face_instance_id'] == ref['face_instance_id']
    assert 'frozen_source_analysis_missing_or_stale' in str(error.value) and state == before


@pytest.mark.parametrize('enabled', list(product((False, True), repeat=6)))
def test_all_64_four_through_ten_slot_prefixes_keep_mouth_and_append_after_chin_length(enabled):
    """Real wrappers/TPS; prior fields are named synthetic composition doubles."""
    from lumaretouch_engine.face_contour_people import ContouredFace
    from lumaretouch_engine.face_size_people import SizedFace
    from lumaretouch_engine.lower_face_people import LowerFace
    from lumaretouch_engine.mid_face_people import MidFace
    from lumaretouch_engine.chin_shape_people import ChinShape
    from lumaretouch_engine.chin_length_people import ChinLength
    state, ref, analysis, source, base = prefix_fixture(translation='curved')
    mouth = SimpleNamespace(state=None, resident_bytes=lambda: 0)
    base = FaceGeometry(base.face_instance_id, base.shape, base.automatic, (None, None, None, mouth))
    prefix, appended = base, []
    # Corrected slim and contour share a mutually exclusive ContouredFace slot.
    # This is not a claim that both operations may be active simultaneously.
    predecessors = ((ContouredFace, 'contour_or_corrected_slim', [.003, .003]),
                    (SizedFace, 'whole_face_size', [.002, .002]),
                    (LowerFace, 'lower_face', [0., .004]),
                    (MidFace, 'mid_face', [0., .005]),
                    (ChinShape, 'chin_shape', [.006, 0.]),
                    (ChinLength, 'chin_length', [0., .007]))
    for use, (wrapper, name, gain) in zip(enabled, predecessors):
        if not use: continue
        prior = SimpleNamespace(state={'synthetic_prior_composition_fixture': name},
            evaluate=lambda q, gain=gain: (np.asarray(q, dtype=np.float64)-[63.5, 63.5])*gain,
            resident_bytes=lambda: 64)
        prefix = wrapper(base.face_instance_id, base.shape, base.automatic, (*prefix.fields, prior), prefix, ())
        appended.append(prior)
    previous_fields, source_before = prefix.fields, source.copy()
    chin = SyntheticPhiltrumField(source.shape[:2], ACTIVE)
    with patch.object(CORE, 'build', return_value=chin) as build:
        result, facts = PORT.append(prefix, state, ref, analysis, source, ACTIVE)
    assert build.call_count == 1 and type(result) is PORT.Philtrum
    assert result.prefix is prefix and result.automatic is base.automatic
    assert len(prefix.fields) == 4+len(appended) and 4 <= len(prefix.fields) <= 10
    assert prefix.fields is previous_fields and result.fields[:-1] == previous_fields
    assert result.fields[3] is mouth and result.fields[-1] is chin
    assert all(result.fields[4+i] is value for i, value in enumerate(appended))
    if enabled[-1]: assert type(result.prefix) is ChinLength
    elif enabled[-2]: assert type(result.prefix) is ChinShape
    assert facts is chin.facts and result.resident_bytes() >= prefix.resident_bytes()+chin.resident_bytes()
    assert build.call_args.args[0] is analysis['landmarks'] and build.call_args.args[2] is source
    assert build.call_args.kwargs['analysis'] is analysis and build.call_args.kwargs['protected_boxes'] == ()
    points = np.array([[58., 53.], [68., 61.], [75., 70.]])
    before = points.copy()
    chin_delta, baseline = chin.evaluate(points), prefix.evaluate(points)
    expected = chin_delta+prefix.evaluate(points-chin_delta)
    np.testing.assert_allclose(result.evaluate(points), expected, rtol=0, atol=1e-12)
    assert not np.allclose(expected, baseline+chin_delta, rtol=0, atol=1e-9)
    assert not np.allclose(expected, baseline+chin.evaluate(points-baseline), rtol=0, atol=1e-9)
    np.testing.assert_array_equal(points, before)
    np.testing.assert_array_equal(source, source_before)


@pytest.mark.parametrize('change', ['identity', 'disabled', 'digest', 'grid', 'owner', 'few_slots', 'many_slots'])
def test_stale_foreign_or_invalid_prefix_append_refuses_before_build(change):
    state, ref, analysis, source, prefix = prefix_fixture()
    if change == 'identity': ref = {**ref, 'analysis_revision': ref['analysis_revision']+1}
    elif change == 'disabled': state['faces'][ref['face_instance_id']]['enabled'] = False
    elif change == 'digest': analysis['landmarks'][0, 0] += .001
    elif change == 'grid': prefix = FaceGeometry(prefix.face_instance_id, (64, 64), prefix.automatic, prefix.fields)
    elif change == 'owner': prefix = FaceGeometry('other-face', prefix.shape, prefix.automatic, prefix.fields)
    else: prefix = FaceGeometry(prefix.face_instance_id, prefix.shape, prefix.automatic, (None,)*(3 if change == 'few_slots' else 11))
    with patch.object(CORE, 'build') as build, pytest.raises(ValueError):
        PORT.append(prefix, state, ref, analysis, source, ACTIVE)
    build.assert_not_called()


def test_repeated_length_never_acquires_a_second_geometry_owner():
    state, ref, analysis, source, prefix = prefix_fixture()
    with patch.object(CORE, 'build', return_value=SyntheticPhiltrumField(source.shape[:2], ACTIVE)) as build:
        result, _ = PORT.append(prefix, state, ref, analysis, source, ACTIVE)
        with pytest.raises(ValueError):
            PORT.append(result, state, ref, analysis, source, ACTIVE)
    assert build.call_count == 1 and prefix.fields == (None,)*4


@pytest.mark.parametrize('mode', ['missing', 'no_state', 'refused'])
def test_requested_missing_or_refused_field_never_publishes_partial_geometry(mode):
    state, ref, analysis, source, prefix = prefix_fixture()
    chin = SyntheticPhiltrumField(source.shape[:2], ACTIVE)
    if mode == 'missing': chin = None
    elif mode == 'no_state': chin.state = None
    else: chin.facts['philtrum'].update(applied=False, reason='synthetic_occlusion_refusal')
    with patch.object(CORE, 'build', return_value=chin), pytest.raises(ValueError):
        PORT.append(prefix, state, ref, analysis, source, ACTIVE)
    assert prefix.fields == (None,)*4


def test_same_source_retained_neighbors_including_disabled_are_passed_to_new_builder():
    state, ref, analysis, source, prefix = prefix_fixture()
    own = state['faces'][ref['face_instance_id']]
    for index, enabled in enumerate((False, True)):
        other = deepcopy(own)
        other.update(face_instance_id=f'neighbor-{index}', enabled=enabled, box=[.05+index*.2, .1, .15+index*.2, .4])
        state['faces'][other['face_instance_id']] = other
    foreign = deepcopy(own)
    foreign.update(face_instance_id='other-source', asset_sha256='f'*64)
    state['faces']['other-source'] = foreign
    with patch.object(CORE, 'build', return_value=SyntheticPhiltrumField(source.shape[:2], ACTIVE)) as build:
        PORT.append(prefix, state, ref, analysis, source, ACTIVE)
    assert build.call_args.kwargs['protected_boxes'] == ((.05, .1, .15, .4), (.25, .1, .35, .4))


@pytest.mark.parametrize('stage_name', ['output', 'intermediate', 'final', 'cancelled'])
def test_composed_neighbor_footprints_refuse_even_when_final_motion_cancels(stage_name):
    translation = {'output': [-10., 0.], 'intermediate': [-30., 0.], 'final': [15., 0.], 'cancelled': [-20., 0.]}[stage_name]
    point = np.array([[50. if stage_name == 'output' else 70., 50.]])
    delta = {'output': [-20., 0.], 'intermediate': [20., 0.], 'final': [5., 0.], 'cancelled': [20., 0.]}[stage_name]
    state, ref, analysis, source, prefix = prefix_fixture(translation=translation)
    neighbor = deepcopy(state['faces'][ref['face_instance_id']])
    neighbor.update(face_instance_id='protected-neighbor', enabled=False, box=[49./127, 49./127, 51./127, 51./127])
    state['faces']['protected-neighbor'] = neighbor
    chin = SyntheticPhiltrumField(source.shape[:2], ACTIVE, constant_delta=delta)
    with patch.object(CORE, 'build', return_value=chin):
        result, _ = PORT.append(prefix, state, ref, analysis, source, ACTIVE)
    with pytest.raises(ValueError, match='another retained face'):
        result.evaluate(point)


@pytest.mark.parametrize('kind', ['chin_shape', 'chin_length'])
def test_prior_chin_wrapper_guard_survives_philtrum_relocating_its_queries(kind):
    from lumaretouch_engine.chin_shape_people import ChinShape
    from lumaretouch_engine.chin_length_people import ChinLength
    state, ref, analysis, source, base = prefix_fixture()
    protected = ((49./127, 49./127, 51./127, 51./127),)
    prior = SimpleNamespace(state={'synthetic_guard_fixture': kind},
        evaluate=lambda q: np.tile([15., 0.], (len(q), 1)), resident_bytes=lambda: 64)
    wrapper = ChinShape if kind == 'chin_shape' else ChinLength
    prefix = wrapper(base.face_instance_id, base.shape, base.automatic, (*base.fields, prior), base, protected)
    chin = SyntheticPhiltrumField(source.shape[:2], ACTIVE, constant_delta=[5., 0.])
    with patch.object(CORE, 'build', return_value=chin):
        result, _ = PORT.append(prefix, state, ref, analysis, source, ACTIVE)
    assert result.prefix is prefix and prefix.protected_boxes is protected and result.protected_boxes == ()
    with pytest.raises(ValueError, match='another retained face'):
        result.evaluate(np.array([[70., 50.]]))


def test_out_of_image_composed_sampling_refuses_instead_of_border_fill():
    state, ref, analysis, source, prefix = prefix_fixture()
    chin = SyntheticPhiltrumField(source.shape[:2], ACTIVE, constant_delta=[0., 3.])
    with patch.object(CORE, 'build', return_value=chin):
        result, _ = PORT.append(prefix, state, ref, analysis, source, ACTIVE)
    with pytest.raises(ValueError, match='outside the genuine source'):
        result.evaluate(np.array([[50., 1.]]))


@pytest.mark.parametrize('recipe', SIGNED_RECIPES)
def test_original_rgb16_and_derived_float_export_share_actual_map_and_sampler(recipe):
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
    with patch.object(CORE, 'build', side_effect=philtrum_builder(received, (384, 384), recipe)) as build:
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


@pytest.mark.parametrize('derived', [False, True])
@pytest.mark.parametrize('amount', [-.4, .4])
def test_scalar_person_scope_rebuilds_each_independently_owned_target_before_publication(derived, amount):
    """Real shared staging and canonical exports; no batch/file-host IO claim."""
    targets = [independent_target('a'*64, 128, 0.), independent_target('f'*64, 160, .02)]
    state = P.empty()
    for target, _, _, _ in targets:
        state['faces'].update(deepcopy(target['faces']))
    state, person = LINKS.create_person(state)
    for _, ref, _, _ in targets:
        state = LINKS.set_link(state, ref['face_instance_id'], person, 'confirmed', user_confirmed=True)
    before, owner = deepcopy(state), PeopleGraphOwner(state)
    ref = targets[0][1]
    command = patch_command(state, ref, [(S.OP, '/amount', amount)])
    command['target'] = {'scope': 'person', 'target_id': person, 'face_ref': None}
    candidate = stage(command, state, ref)['state']
    assert affected_assets(state, candidate) == {'a'*64, 'f'*64}
    shared = [row for row in candidate['overrides'] if row['scope'] == 'person']
    assert len(shared) == 1 and shared[0]['operation_id'] == S.OP
    assert shared[0]['parameter_path'] == '/amount' and shared[0]['value'] == amount
    assert set(A.leaves(S.preset({'version': 1, 'amount': amount}))) == {'/amount'}
    retained, sources, records = [], [], []
    for _, target_ref, analysis, binding in targets:
        size = binding['width']
        assert resolved(candidate, target_ref)[S.OP] == {'version': 1, 'amount': amount}
        snapshot = SNAP.capture(candidate, target_ref['asset_sha256'], {target_ref['face_instance_id']: analysis})
        snapshot.update(document_id=DOCUMENT, support_assets={})
        if derived:
            snapshot['creative_source'] = binding
        original = original_pixels(size)
        pixels = original.astype(np.float32)/65535. if derived else original
        sources.append(pixels.copy())
        received = []
        with patch.object(CORE, 'build', side_effect=philtrum_builder(
                received, (size, size), {'version': 1, 'amount': amount})) as build:
            prepared = ENGINE.prepare_export(snapshot, pixels, None, byte_budget=BUDGET, document_id=DOCUMENT)
        assert build.call_count == 1 and len(received) == 1
        assert_canonical_result(prepared, target_ref, received[0], (size, size))
        assert snapshot['analyses'][target_ref['face_instance_id']]['evidence']['landmark_digest'] == BIND.landmark_digest(analysis['landmarks'])
        np.testing.assert_array_equal(received[0]['source'], original.astype(np.float32)/65535.)
        output = prepared.geometry.warp(pixels) if derived else prepared.geometry.warp_original(pixels)
        assert output.shape == pixels.shape and output.dtype == pixels.dtype and np.any(output != pixels)
        np.testing.assert_array_equal(pixels, sources[-1])
        retained.append(prepared)
        records.append(received[0])
        assert owner.snapshot() == before and owner.fence == 0
    assert records[0]['field'] is not records[1]['field']
    assert records[0]['face_ref'] != records[1]['face_ref']
    assert records[0]['observation']['source_sha256'] == 'a'*64
    assert records[1]['observation']['source_sha256'] == 'f'*64
    assert not np.shares_memory(retained[0].geometry.delta, retained[1].geometry.delta)
    assert not np.array_equal(targets[0][2]['landmarks'], targets[1][2]['landmarks'])
    owner.commit(candidate, expected_fence=0)
    assert owner.fence == 1 and state == before
    for _, target_ref, _, _ in targets:
        assert resolved(owner.snapshot(), target_ref)[S.OP]['amount'] == amount


@pytest.mark.parametrize('fault', ['donor_face_ref', 'donor_observation', 'landmark_digest'])
def test_target_export_refuses_donor_or_stale_analysis_before_new_build(fault):
    _, donor_ref, donor_analysis, _ = independent_target('a'*64, 128, 0.)
    state, ref, analysis, binding = independent_target('f'*64, 160, .02)
    state = set_recipe(state, ref['face_instance_id'], ACTIVE)
    before, owner = deepcopy(state), PeopleGraphOwner(state)
    if fault == 'donor_face_ref':
        analysis['face_ref'] = deepcopy(donor_ref)
    elif fault == 'donor_observation':
        analysis['face_skin_observation'] = deepcopy(donor_analysis['face_skin_observation'])
    else:
        analysis['landmarks'][0, 0] += np.float32(.001)
    with patch.object(CORE, 'build') as build, pytest.raises(ValueError):
        snapshot = SNAP.capture(state, ref['asset_sha256'], {ref['face_instance_id']: analysis})
        snapshot.update(document_id=DOCUMENT, support_assets={}, creative_source=binding)
        ENGINE.prepare_export(snapshot, original_pixels(160).astype(np.float32)/65535.,
                              None, byte_budget=BUDGET, document_id=DOCUMENT)
    build.assert_not_called()
    assert state == before and owner.snapshot() == before and owner.fence == 0


@pytest.mark.parametrize('recipe', SIGNED_RECIPES)
def test_original_and_derived_preview_keep_real_repair_proof_and_common_sampler(recipe):
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
    with patch.object(CORE, 'build', side_effect=philtrum_builder(received, (128, 128), recipe)) as build:
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


@pytest.mark.parametrize('fault', [None, 'missing', 'input_digest', 'output_digest', 'source'])
def test_derived_export_checks_real_repair_evidence_and_builds_geometry_from_owned_unrepaired_source(fault):
    """Synthetic completed repair pixels; actual proof maker/verifier/export."""
    state, ref, analysis, binding = fixture()
    before = deepcopy(state)
    snapshot = SNAP.capture(state, ref['asset_sha256'], {ref['face_instance_id']: analysis})
    snapshot.update(document_id=DOCUMENT, support_assets={}, creative_source=binding)
    working = original_pixels(128).astype(np.float32)/65535.
    repaired = (working*.9+.02).astype(np.float32)
    working_before, repaired_before = working.copy(), repaired.copy()
    proof = REPLAY.make_evidence(binding, working, repaired, REPAIRS.digest_ops([], [], binding))
    if fault == 'missing': proof = None
    elif fault == 'input_digest': proof['input']['sha256'] = 'f'*64
    elif fault == 'output_digest': proof['output']['sha256'] = 'f'*64
    elif fault == 'source': proof['source']['sha256'] = 'f'*64
    proof_before, received = deepcopy(proof), []
    with patch.object(CORE, 'build', side_effect=philtrum_builder(received, (128, 128))) as build:
        if fault is None:
            prepared = ENGINE.prepare_export(snapshot, working, repaired, byte_budget=BUDGET,
                document_id=DOCUMENT, creative_repair_evidence=proof)
            assert build.call_count == 1 and len(received) == 1
            assert_canonical_result(prepared, ref, received[0], (128, 128))
            np.testing.assert_array_equal(received[0]['source'], working)
            assert not np.array_equal(received[0]['source'], repaired)
            assert REPLAY.verify_evidence(proof, binding, working, repaired) == proof
        else:
            with pytest.raises(ValueError):
                ENGINE.prepare_export(snapshot, working, repaired, byte_budget=BUDGET,
                    document_id=DOCUMENT, creative_repair_evidence=proof)
            build.assert_not_called()
    assert state == before and snapshot['state'] == before and proof == proof_before
    np.testing.assert_array_equal(working, working_before)
    np.testing.assert_array_equal(repaired, repaired_before)


@pytest.mark.parametrize('derived', [False, True])
def test_export_rejects_wrong_source_dtype_before_new_build(derived):
    state, ref, analysis, binding = fixture()
    snapshot = SNAP.capture(state, ref['asset_sha256'], {ref['face_instance_id']: analysis})
    snapshot.update(document_id=DOCUMENT, support_assets={})
    original = original_pixels(128)
    if derived: snapshot['creative_source'], wrong = binding, original
    else: wrong = original.astype(np.float32)/65535.
    with patch.object(CORE, 'build') as build, pytest.raises(ValueError, match='creative float32' if derived else 'original RGB8/16'):
        ENGINE.prepare_export(snapshot, wrong, None, byte_budget=BUDGET, document_id=DOCUMENT)
    build.assert_not_called()


@pytest.mark.parametrize('fault', ['missing', 'input_digest', 'stack_digest'])
def test_missing_or_tampered_derived_preview_repair_proof_refuses_before_new_build(fault):
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
    with patch.object(CORE, 'build') as build, pytest.raises(ValueError):
        ENGINE.prepare_preview(pipe, state, ref['asset_sha256'], {ref['face_instance_id']: analysis},
                               byte_budget=BUDGET, document_id=DOCUMENT,
                               creative_source=binding, creative_proxy=proxy)
    build.assert_not_called()
    assert state == before
    if fault != 'missing': assert pipe._creative_repair_evidence == corrupted
    np.testing.assert_array_equal(pipe.src_f32[0].permute(1, 2, 0).numpy(), working)


@pytest.mark.parametrize('fault', ['document', 'derived_source', 'budget'])
def test_export_source_owner_or_budget_refusal_has_no_proxy_fallback(fault):
    state, ref, analysis, binding = fixture(size=384)
    snapshot = SNAP.capture(state, ref['asset_sha256'], {ref['face_instance_id']: analysis})
    snapshot.update(document_id=DOCUMENT, support_assets={})
    source, budget = original_pixels(384), BUDGET
    if fault == 'document': snapshot['document_id'] = 'another-document'
    elif fault == 'derived_source':
        snapshot['creative_source'] = {**binding, 'sha256': 'f'*64}
        source = source.astype(np.float32)/65535.
    else: budget = 1
    with patch.object(CORE, 'build') as build, pytest.raises(ValueError):
        ENGINE.prepare_export(snapshot, source, None, byte_budget=budget, document_id=DOCUMENT)
    build.assert_not_called()


@pytest.mark.parametrize('refusal', ['missing', 'raised', 'nonfinite'])
def test_requested_export_failure_preserves_source_intent_and_frozen_snapshot(refusal):
    state, ref, analysis, _ = fixture()
    before = deepcopy(state)
    snapshot = SNAP.capture(state, ref['asset_sha256'], {ref['face_instance_id']: analysis})
    snapshot.update(document_id=DOCUMENT, support_assets={})
    pixels = original_pixels(128)
    pixels_before = pixels.copy()
    if refusal == 'raised': options = {'side_effect': ValueError('explicit synthetic length refusal')}
    elif refusal == 'missing': options = {'return_value': None}
    else: options = {'return_value': SyntheticPhiltrumField((128, 128), ACTIVE, constant_delta=[0., float('nan')])}
    with patch.object(CORE, 'build', **options) as build, pytest.raises(ValueError):
        ENGINE.prepare_export(snapshot, pixels, None, byte_budget=BUDGET, document_id=DOCUMENT)
    assert build.call_count == 1 and state == before and snapshot['state'] == before
    np.testing.assert_array_equal(pixels, pixels_before)


def test_source_routing_keeps_mouth_slot_and_appends_philtrum_after_chin_length():
    text = (ROOT/'engine/src/lumaretouch_engine/people_render_runtime.py').read_text()
    tree = ast.parse(text)
    prepare = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'prepare')
    calls = [node for node in ast.walk(prepare) if isinstance(node, ast.Call)]
    names = ('build_geometry', 'append_slim', 'append_contour', 'append_size', 'append_lower', 'append_mid', 'append_chin', 'append_chin_length', 'append_philtrum')
    ordered = []
    for name in names:
        matches = [node for node in calls if
                   (isinstance(node.func, ast.Name) and node.func.id == name) or
                   (isinstance(node.func, ast.Attribute) and node.func.attr == name)]
        assert len(matches) == 1
        ordered.append(matches[0].lineno)
        if name == 'append_philtrum':
            assert len(matches[0].args) == 6
            assert matches[0].keywords == []
        elif name == 'append_chin_length':
            assert [keyword.arg for keyword in matches[0].keywords] == ['legacy_amount']
    assert ordered == sorted(ordered)
    compatibility = [node for node in calls if isinstance(node.func, ast.Attribute)
                     and isinstance(node.func.value, ast.Name) and node.func.value.id == 'A'
                     and node.func.attr == 'validate_compatibility']
    assert len(compatibility) == 1 and compatibility[0].lineno < ordered[0]
    assert 'mouth = field.fields[3]' in text and 'mouth = field.fields[-1]' not in text
    for key, name in (('philtrum', 'philtrum'), ('chin_length', 'chin_length'), ('chin_shape', 'chin'), ('mid_face', 'mid'), ('lower_face', 'lower'), ('face_size', 'size')):
        assert f"facts[key]['{key}'] = {name}_facts" in text


def test_new_runtime_owns_geometry_and_only_bridge_reuses_shared_native_without_new_library():
    runtime = (ROOT/'engine/src/lumaretouch_engine/philtrum_runtime.py').read_text()
    tree = ast.parse(runtime)
    lower_imports = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                     and node.module == 'lower_face_runtime']
    assert all(alias.name in {'_measured_order', '_inside_or_boundary', '_feature_support', '_lower_interior_support'}
               for node in lower_imports for alias in node.names)
    assert 'from .philtrum_native import canonical_frame, evaluate as native_evaluate' in runtime
    bridge = (ROOT/'engine/src/lumaretouch_engine/philtrum_native.py').read_text()
    assert 'from . import mid_face_native as _shared' in bridge
    assert 'return _shared.evaluate(points, snapshot)' in bridge
    server = (ROOT/'engine/src/lumaretouch_engine/server.py').read_text()
    assert 'from .philtrum_state import capability as philtrum_capability' in server
    assert 'philtrum_capability()' in server
    stage_source = (ROOT/'packaging/stage-engine.sh').read_text()
    assert 'build-mid-face.sh' in stage_source and 'liblrt_mid_face.so' in stage_source
    assert 'core/mid_face/mid_face.h' in stage_source and 'third_party/mid_face/' in stage_source
    assert 'build-philtrum.sh' not in stage_source and 'liblrt_philtrum.so' not in stage_source
    assert not (ROOT/'packaging/build-philtrum.sh').exists()
    assert not (ROOT/'core/philtrum').exists()


def test_integration_fixtures_patch_only_the_declared_new_runtime_build_boundary():
    """AUTHORED_UNRUN source contract, not a collection/runtime success report."""
    tree = ast.parse(Path(__file__).read_text())
    patches = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
               and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
               and node.func.value.id == 'patch' and node.func.attr == 'object']
    assert patches
    for call in patches:
        assert len(call.args) >= 2 and isinstance(call.args[0], ast.Name) and call.args[0].id == 'CORE'
        assert isinstance(call.args[1], ast.Constant) and call.args[1].value == 'build'
