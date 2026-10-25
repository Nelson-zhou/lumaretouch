# SPDX-License-Identifier: GPL-3.0-or-later
"""Crop proof adapter into the existing canonical history owner, not a new one.

No new project recipe/version is introduced: saved pixels remain the unchanged
original and saved geometry remains lnx.crop.v1. A reviewed proof is explanatory
receipt evidence, never authority to replay a write or a saved UI approval.
AUTHORED / UNRUN.
"""
from copy import deepcopy

from .portrait_crop_controller import canonical, digest

VERSION = 1
OPERATION_ID = 'lnx.crop.v1'
PROOF_FIELDS = {'version', 'operation_id', 'capture_sha256', 'binding', 'before',
                'uncropped', 'after', 'source_image_sha256', 'analysis_sha256',
                'model_sha256', 'semantic_model_sha256', 'proxy_sha256', 'face',
                'anchors', 'rules', 'anchor_review', 'plan', 'candidate_sha256'}


def non_crop_hash(state):
    from .optics_candidate_identity import fingerprint
    return fingerprint({key: value for key, value in state.items() if key not in ('_crop_rect', '_crop_rotation')})


def repair_hash(state):
    from .optics_candidate_identity import fingerprint
    # The complete state hash is authoritative. This subset is a separately
    # inspectable repair/manual-geometry chain, not an exclusion allowlist.
    keys = ('_repair_ops', '_redo_ops', '_op_seq', '_effect_recovery',
            '_manual_liquify', '_fringe_repair', '_body_pose_bank')
    return fingerprint({key: state[key] for key in keys if key in state})


def compact_proof(capture, state, plan, request, after):
    from .optics_candidate_identity import fingerprint
    face = next(row for row in capture.source['faces'] if row['face_id'] == request['face_id'])
    return check_proof({'version': VERSION, 'operation_id': OPERATION_ID,
        'capture_sha256': capture.capture_sha256, 'binding': capture.binding,
        'before': capture.before_proof, 'uncropped': capture.uncropped_proof, 'after': after,
        'source_image_sha256': capture.source['image']['sha256'],
        **{key: capture.source[key] for key in ('analysis_sha256', 'model_sha256', 'semantic_model_sha256', 'proxy_sha256')},
        'face': face, 'anchors': request['anchors'], 'rules': request['rules'],
        'anchor_review': request['anchor_review'], 'plan': plan,
        'candidate_sha256': fingerprint(state)})


def check_proof(value):
    """Only compact JSON-safe evidence; never retain display image bytes."""
    from .creative_derived_source import check_row_proof
    if (type(value) is not dict or set(value) != PROOF_FIELDS
            or type(value['version']) is not int or value['version'] != VERSION
            or value['operation_id'] != OPERATION_ID):
        raise ValueError('Portrait crop requires its exact compact reviewed proof')
    hashes = ('capture_sha256', 'source_image_sha256', 'analysis_sha256', 'model_sha256',
              'semantic_model_sha256', 'proxy_sha256', 'candidate_sha256')
    if any(not digest(value[key]) for key in hashes):
        raise ValueError('Portrait crop compact proof contains an invalid content digest')
    binding = value['binding']
    binding_keys = {'document_id', 'revision', 'document_epoch', 'load_id', 'original_sha256',
                    'source_proof', 'state_sha256', 'non_crop_sha256', 'people_sha256',
                    'repair_sha256', 'uncropped_sha256'}
    if type(binding) is not dict or set(binding) != binding_keys:
        raise ValueError('Portrait crop proof has an incomplete source/edit binding')
    if any(not digest(binding[key]) for key in binding_keys if key.endswith('_sha256')):
        raise ValueError('Portrait crop proof has an invalid source/edit digest')
    if type(binding['document_id']) is not str or not binding['document_id'] or type(binding['revision']) is not str or not binding['revision'].isdigit():
        raise ValueError('Portrait crop proof lacks canonical document identity')
    check_row_proof(binding['source_proof'])
    if binding['original_sha256'] != binding['source_proof']['original_sha256']:
        raise ValueError('Portrait crop original-file proof disagrees with canonical provenance')
    from .portrait_crop_state import check_anchors, check_rules
    size = value['plan']['source_size']
    check_anchors(value['anchors'], *size)
    check_rules(value['rules'])
    if value['plan']['anchors'] != value['anchors'] or value['plan']['rules'] != value['rules']:
        raise ValueError('Portrait crop solver altered the explicitly reviewed rule request')
    if value['anchor_review'] != {'image_sha256': value['source_image_sha256'],
            'crown_confirmed': True, 'chin_confirmed': True, 'center_confirmed': True}:
        raise ValueError('Portrait crop compact proof lacks the real source-image anchor review')
    render_keys = {'document_id', 'revision', 'source_proof', 'candidate_sha256',
                   'people_sha256', 'source_size', 'output_size', 'raster_sha256', 'image_sha256'}
    for name in ('before', 'uncropped', 'after'):
        proof = value[name]
        if type(proof) is not dict or set(proof) != render_keys:
            raise ValueError('Portrait crop compact proof lacks complete raster/image identity')
        if any(not digest(proof[key]) for key in ('candidate_sha256', 'people_sha256', 'raster_sha256', 'image_sha256')):
            raise ValueError('Portrait crop render proof has invalid image/state digests')
        if (proof['document_id'] != binding['document_id'] or proof['revision'] != binding['revision']
                or proof['source_proof'] != binding['source_proof'] or proof['people_sha256'] != binding['people_sha256']
                or proof['source_size'] != size):
            raise ValueError('Portrait crop complete renders belong to different source/edit owners')
    if value['before']['candidate_sha256'] != binding['state_sha256'] or value['after']['candidate_sha256'] != value['candidate_sha256']:
        raise ValueError('Portrait crop before/after rendering proof does not name the exact states')
    if value['uncropped']['output_size'] != size or value['after']['output_size'] != value['plan']['output_size']:
        raise ValueError('Portrait crop rendering proof is not the exact full destination/output grid')
    if (value['uncropped']['raster_sha256'] != binding['uncropped_sha256']
            or value['uncropped']['image_sha256'] != value['source_image_sha256']):
        raise ValueError('Portrait crop full edited raster and displayed source proof disagree')
    # Reject image payloads, including accidental nested transport data.
    def no_pixels(item):
        if isinstance(item, dict):
            if {'base64', 'content', 'rgba', 'rgb'}.intersection(item):
                raise ValueError('Portrait crop persisted proof must not contain image payloads')
            for child in item.values():
                no_pixels(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                no_pixels(child)
    no_pixels(value)
    canonical(value)
    return deepcopy(value)


def verify_commit(engine, before_state, candidate_state, proof):
    from .optics_candidate_identity import fingerprint
    from .full_candidate_render import identity
    from .portrait_crop_capture import file_hash, rotation_supported
    from .scope import OP_CROP, check_params
    proof = check_proof(proof)
    binding = proof['binding']
    if fingerprint(before_state) != binding['state_sha256'] or fingerprint(engine._capture_state()) != binding['state_sha256']:
        raise ValueError('Portrait crop live edits changed before canonical commit')
    if set(candidate_state) != set(before_state) or fingerprint(candidate_state) != proof['candidate_sha256']:
        raise ValueError('Portrait crop candidate state differs from the reviewed full output')
    if (non_crop_hash(before_state) != binding['non_crop_sha256']
            or non_crop_hash(candidate_state) != binding['non_crop_sha256']
            or repair_hash(candidate_state) != binding['repair_sha256']
            or fingerprint(candidate_state['_crop_rotation']) != fingerprint(before_state['_crop_rotation'])
            or not rotation_supported(before_state)):
        raise ValueError('Portrait crop must preserve all non-crop effects, repairs and existing rotation')
    params = check_params(OP_CROP, {'rect_normalized': list(candidate_state['_crop_rect']),
                                   'rotation_degrees': candidate_state['_crop_rotation']})
    if params['rect_normalized'] != proof['plan']['rect_normalized']:
        raise ValueError('Portrait crop candidate geometry differs from canonical reviewed plan')
    row = engine._docs[engine._doc_index]
    if engine._document_versions().workspace != binding['document_epoch'] or engine._load_id != binding['load_id']:
        raise ValueError('Portrait crop document load/epoch changed after full-image review')
    for state, name in ((before_state, 'before'), (candidate_state, 'after')):
        actual, _, _ = identity(engine, row, state, binding['document_id'], binding['revision'])
        if any(proof[name][key] != value for key, value in actual.items()):
            raise ValueError('Portrait crop source, analysis or candidate changed before history admission')
    uncropped = dict(before_state)
    uncropped['_crop_rect'] = (0., 0., 1., 1.)
    if fingerprint(uncropped) != proof['uncropped']['candidate_sha256']:
        raise ValueError('Portrait crop uncropped proof changed an unrelated recipe')
    if file_hash(row['path']) != binding['original_sha256']:
        raise ValueError('Portrait crop original content changed before canonical history admission')
    return proof


def commit(engine, *, before_state, candidate_state, proof, request_id):
    """Only the registered canonical host can publish one crop history step."""
    method = getattr(engine, '_commit_portrait_crop_candidate', None)
    if not callable(method):
        raise ValueError('Canonical portrait crop history integration is unavailable')
    checked = verify_commit(engine, before_state, candidate_state, proof)
    return method(before_state=before_state, candidate_state=candidate_state,
                  proof=checked, request_id=request_id)
