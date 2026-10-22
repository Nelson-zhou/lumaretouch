"""Versioned anonymous people graph. Pure data; no detection or identity inference.

This is an integration contract, not a claim that existing renderers consume it.
Instance IDs are project-assigned UUIDs, NEVER detector order or landmark hashes.
"""
from copy import deepcopy
import json
import math
import re
import uuid

VERSION = 2
MAX_FACES = 4096
MAX_OVERRIDES = 65536
SCOPES = ('all_people', 'group', 'person', 'face')
LINK_STATES = ('candidate', 'confirmed', 'rejected', 'unresolved')


def token(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', value):
        raise ValueError('Invalid people identifier')
    return value


def digest(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('Expected actual SHA-256 digest')
    return value


def revision(value):
    if type(value) is not int or not 0 <= value < 2**63:
        raise ValueError('Invalid people revision')
    return value


def parameter_path(value):
    # JSON pointer, with canonical escaping. Never a filesystem path.
    if type(value) is not str or len(value) > 512 or not value.startswith('/'):
        raise ValueError('Parameter path must be a JSON pointer')
    if any(not part or re.search(r'~(?![01])', part) for part in value[1:].split('/')):
        raise ValueError('Invalid parameter pointer')
    return value


def scalar(value):
    if type(value) not in (bool, int, float, str) or (type(value) in (int, float) and not math.isfinite(value)):
        raise ValueError('An override must be one finite scalar leaf, not an asset or recipe')
    if type(value) is str and len(value) > 256:
        raise ValueError('Override text exceeds budget')
    return value


def empty():
    return {'version': VERSION, 'revision': 0, 'association_revision': 0,
            'faces': {}, 'persons': {}, 'groups': {}, 'links': [],
            'overrides': [], 'unresolved_legacy': [], 'analysis_runs': {}}


def face_ref(face):
    return {key: face[key] for key in ('asset_sha256', 'face_instance_id', 'analysis_revision')}


def check_ref(value):
    if type(value) is not dict or set(value) != {'asset_sha256', 'face_instance_id', 'analysis_revision'}:
        raise ValueError('FaceRef must pin source, stable instance and analysis revision')
    digest(value['asset_sha256']); token(value['face_instance_id']); revision(value['analysis_revision'])
    return deepcopy(value)


def check_evidence(value):
    fields = {'backend', 'detector_model_sha256', 'semantic_model_sha256',
              'landmark_digest', 'status', 'source_width', 'source_height', 'orientation'}
    if type(value) is not dict or set(value) != fields:
        raise ValueError('Face evidence must distinguish detector bytes from semantic mask model')
    token(value['backend'])
    if value['status'] not in ('verified', 'unresolved', 'synthetic'):
        raise ValueError('Invalid face evidence status')
    for key in ('detector_model_sha256', 'semantic_model_sha256', 'landmark_digest'):
        if value[key] is not None: digest(value[key])
    for key in ('source_width', 'source_height'):
        if type(value[key]) is not int or not 1 <= value[key] <= 1000000:
            raise ValueError('Canonical source dimensions are required')
    if value['orientation'] != 'exif_normalized_once':
        raise ValueError('Analysis must name the canonical orientation convention')
    if value['status'] == 'verified' and (value['detector_model_sha256'] is None or value['landmark_digest'] is None):
        raise ValueError('Verified analysis needs actual loaded detector bytes and landmark digest')
    return deepcopy(value)


def new_face(asset_sha256, box, evidence, *, manual=False):
    digest(asset_sha256); evidence = check_evidence(evidence)
    if type(manual) is not bool: raise ValueError('Manual status must be explicit')
    if type(box) not in (list, tuple) or len(box) != 4 or any(type(x) not in (int, float) or not math.isfinite(x) for x in box):
        raise ValueError('Face region needs four finite coordinates')
    if not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1):
        raise ValueError('Face region must be nonempty normalized bounds')
    return {'face_instance_id': uuid.uuid4().hex, 'asset_sha256': asset_sha256,
            'analysis_revision': 0, 'box': list(box), 'evidence': evidence,
            'manual': manual, 'enabled': True, 'labels': {}, 'local_assets': {}}


def check(state):
    """Bounded structural validation; operation-specific ranges belong to registry."""
    if type(state) is not dict or set(state) != set(empty()) or type(state['version']) is not int or state['version'] != VERSION:
        raise ValueError('Unsupported people state')
    revision(state['revision']); revision(state['association_revision'])
    for key in ('faces', 'persons', 'groups', 'analysis_runs'):
        if type(state[key]) is not dict or len(state[key]) > MAX_FACES:
            raise ValueError('People graph exceeds budget')
    for key, face in state['faces'].items():
        token(key)
        if type(face) is not dict or set(face) != {'face_instance_id', 'asset_sha256', 'analysis_revision', 'box', 'evidence', 'manual', 'enabled', 'labels', 'local_assets'}:
            raise ValueError('Invalid face instance')
        check_ref(face_ref(face))
        if key != face['face_instance_id']: raise ValueError('Face key mismatch')
        check_evidence(face['evidence'])
        # Validate without allocating an ID or replacing existing identity.
        b = face['box']
        if type(b) is not list or len(b) != 4 or any(type(x) not in (int, float) or not math.isfinite(x) for x in b) or not (0 <= b[0] < b[2] <= 1 and 0 <= b[1] < b[3] <= 1):
            raise ValueError('Invalid face box')
        if type(face['manual']) is not bool or type(face['enabled']) is not bool:
            raise ValueError('Invalid face status')
        if type(face['labels']) is not dict or len(face['labels']) > 32:
            raise ValueError('Invalid editable grouping labels')
        for label, value in face['labels'].items(): token(label); scalar(value)
        if type(face['local_assets']) is not dict or len(face['local_assets']) > 128:
            raise ValueError('Invalid face-local assets')
        for asset in face['local_assets'].values():
            if type(asset) is not dict or set(asset) != {'owner', 'content_sha256', 'kind'} or check_ref(asset['owner']) != face_ref(face):
                raise ValueError('Face-local support cannot move to another analysis or person')
            digest(asset['content_sha256']); token(asset['kind'])
    for key, person in state['persons'].items():
        token(key)
        if person != {'anonymous': True}: raise ValueError('Persons are anonymous links, not identity facts')
    for key, group in state['groups'].items():
        token(key)
        if type(group) is not dict or set(group) != {'label', 'priority', 'face_ids'}:
            raise ValueError('Invalid user group')
        scalar(group['label'])
        if type(group['label']) is not str or type(group['priority']) is not int:
            raise ValueError('Group label/precedence must be explicit')
        if type(group['face_ids']) is not list or len(set(group['face_ids'])) != len(group['face_ids']) or any(x not in state['faces'] for x in group['face_ids']):
            raise ValueError('Group members must be known unique instances')
    if type(state['links']) is not list or len(state['links']) > MAX_OVERRIDES: raise ValueError('Too many person links')
    confirmed = set(); pairs = set()
    for link in state['links']:
        if type(link) is not dict or set(link) != {'face_instance_id', 'person_id', 'state', 'confirmation_revision'}:
            raise ValueError('Invalid person link')
        f, p = link['face_instance_id'], link['person_id']
        if f not in state['faces'] or p not in state['persons'] or (f, p) in pairs or link['state'] not in LINK_STATES:
            raise ValueError('Unknown, duplicate or invalid link')
        pairs.add((f, p))
        r = link['confirmation_revision']
        if r is not None and revision(r) > state['association_revision']: raise ValueError('Future association confirmation')
        if link['state'] == 'confirmed':
            if r is None or f in confirmed: raise ValueError('A face needs one explicitly confirmed person')
            confirmed.add(f)
    if type(state['overrides']) is not list or len(state['overrides']) > MAX_OVERRIDES: raise ValueError('Too many overrides')
    keys = set()
    for entry in state['overrides']:
        if type(entry) is not dict or set(entry) != {'scope', 'target_id', 'operation_id', 'parameter_path', 'value'}:
            raise ValueError('Invalid sparse override')
        scope, target = entry['scope'], entry['target_id']
        if scope not in SCOPES: raise ValueError('Invalid override scope')
        if scope == 'all_people': digest(target)
        elif target not in state[{'face':'faces','person':'persons','group':'groups'}[scope]]:
            raise ValueError('Override target does not exist')
        token(entry['operation_id']); parameter_path(entry['parameter_path']); scalar(entry['value'])
        key = (scope, target, entry['operation_id'], entry['parameter_path'])
        if key in keys: raise ValueError('Duplicate sparse override')
        keys.add(key)
    for asset, run in state['analysis_runs'].items():
        digest(asset)
        if type(run) is not dict or set(run) != {'detector_limit', 'limit_reached', 'census_complete', 'notice'}:
            raise ValueError('Invalid detection run disclosure')
        if type(run['detector_limit']) is not int or not 1 <= run['detector_limit'] <= MAX_FACES or type(run['limit_reached']) is not bool or run['census_complete'] is not False:
            raise ValueError('Detection must not claim a complete census')
        scalar(run['notice'])
    if type(state['unresolved_legacy']) is not list or len(state['unresolved_legacy']) > MAX_OVERRIDES:
        raise ValueError('Invalid unresolved intent archive')
    archive_ids = set()
    for record in state['unresolved_legacy']:
        if type(record) is not dict or set(record) != {'id', 'legacy_key', 'asset_sha256', 'intent', 'owner_evidence', 'history_ref', 'status', 'binding'}:
            raise ValueError('Invalid legacy archive record')
        token(record['id']); token(record['legacy_key']); digest(record['asset_sha256'])
        if record['id'] in archive_ids or record['status'] not in ('unresolved', 'confirmed', 'retained'):
            raise ValueError('Invalid legacy archive identity/status')
        archive_ids.add(record['id'])
        if record['status'] in ('unresolved', 'retained') and record['binding'] is not None:
            raise ValueError('Unresolved legacy intent cannot carry an active binding')
        if record['status'] == 'confirmed':
            ref = check_ref(record['binding'])
            if ref['asset_sha256'] != record['asset_sha256'] or ref['face_instance_id'] not in state['faces']:
                raise ValueError('Legacy archive cannot change source ownership')
    # Only JSON data belongs here; masks/arrays remain in source-owned asset storage.
    try: encoded = json.dumps(state, allow_nan=False)
    except (TypeError, ValueError) as exc: raise ValueError('People state must be portable JSON') from exc
    if len(encoded) > 16 * 1024 * 1024: raise ValueError('People state exceeds serialized budget')
    return deepcopy(state)


def set_override(state, scope, target_id, operation_id, path, value, *, unset=False):
    out = check(state)
    if scope not in SCOPES: raise ValueError('Invalid override scope')
    token(operation_id); parameter_path(path)
    if type(unset) is not bool: raise ValueError('Unset must be explicit')
    if scope == 'all_people':
        digest(target_id)
    elif target_id not in out[{'face': 'faces', 'person': 'persons', 'group': 'groups'}[scope]]:
        raise ValueError('Override target does not exist')
    key = (scope, target_id, operation_id, path)
    out['overrides'] = [x for x in out['overrides'] if (x['scope'], x['target_id'], x['operation_id'], x['parameter_path']) != key]
    if not unset:
        out['overrides'].append(dict(zip(('scope', 'target_id', 'operation_id', 'parameter_path', 'value'), (*key, value))))
    out['revision'] += 1
    return check(out)
