# SPDX-License-Identifier: GPL-3.0-or-later
"""Operation-specific observed hair strips, never inherited hair-colour consent.

The standard immutable {version,face_ref,source,row} envelope lets the canonical
people graph retain just a content reference. Source semantic evidence remains
in its existing lossless bank. It is not an instance/crown/ear segmentation.
AUTHORED / UNRUN.
"""
from copy import deepcopy
import json
import math
import numpy as np
from . import people_state as P, hair_colour_assets as A
from . import hair_colour_analysis as E, hair_colour_evidence as SAVED
from . import hair_volume_state as S

KIND = S.SUPPORT_KIND
MODEL_SHA256 = A.MODEL_SHA256
MODEL_BYTES = 16_371_837
digest = A.digest
source = A.source
MAX_ASSETS = 4096
MAX_STORE_BYTES = 16 * 1024 * 1024


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def box(value):
    if (type(value) is not list or len(value) != 4 or not all(_number(v) for v in value)
            or not (0 <= value[0] < value[2] <= 1 and 0 <= value[1] < value[3] <= 1)):
        raise ValueError('Hair protection requires an actual nonempty normalized source rectangle')
    return [float(v) for v in value]


def _points(value):
    if (type(value) is not list or not 3 <= len(value) <= 33
            or any(type(p) is not list or len(p) != 2 or not all(_number(n) and 0 < n < 1 for n in p) for p in value)):
        raise ValueError('Mark 3–33 actual source contour points and paired interior/exterior samples')
    return [[float(n) for n in p] for p in value]


def patch(value, region, binding):
    if region not in S.REGIONS:
        raise ValueError('Unknown observed hair strip')
    if type(value) is not dict or set(value) != {'x', 'y', 'contour', 'hair_samples', 'background_samples'}:
        raise ValueError('Hair strip needs explicit observed contour, paired evidence and fixed transition bounds')
    out = {}
    for axis, extent in (('x', binding['width']), ('y', binding['height'])):
        p = value[axis]
        if (type(p) is not list or len(p) != 4 or not all(_number(n) for n in p)
                or not 0 < p[0] < p[1] < p[2] < p[3] < 1):
            raise ValueError('Hair profile requires strictly ordered normalized a<b<c<d breakpoints')
        px = [n * (extent - 1) for n in p]
        if (px[0] < 1 - 1e-8 or px[3] > extent - 2 + 1e-8 or px[1]-px[0] < 4 - 1e-8
                or px[3]-px[2] < 4 - 1e-8 or px[2]-px[1] < 2 - 1e-8):
            raise ValueError('Hair profile is clipped or lacks original-pixel fade/plateau margins')
        out[axis] = [float(n) for n in p]
    for name in ('contour', 'hair_samples', 'background_samples'):
        out[name] = _points(value[name])
    if len({len(out[name]) for name in ('contour', 'hair_samples', 'background_samples')}) != 1:
        raise ValueError('Every observed boundary point needs its own measured hair and background pair')
    tangent, normal = (0, 1) if region == 'crown' else (1, 0)
    direction = -1 if region == 'right' else 1  # From boundary into hair.
    scale = (binding['width']-1, binding['height']-1)
    last = -1.
    for contour, hair, background in zip(out['contour'], out['hair_samples'], out['background_samples']):
        if contour[tangent] <= last:
            raise ValueError('Observed contour points must be strictly ordered along the strip')
        last = contour[tangent]
        for point in (contour, hair):
            if any(not out[axis][1] <= point[i] <= out[axis][2] for i, axis in enumerate(('x', 'y'))):
                raise ValueError('Observed boundary and real hair interior must lie inside the moving plateau')
        if any(not out[axis][0] <= background[i] <= out[axis][3] for i, axis in enumerate(('x', 'y'))):
            raise ValueError('Background sample must be inside its reviewed source transition')
        if (hair[tangent] != contour[tangent] or background[tangent] != contour[tangent]
                or direction*(hair[normal]-contour[normal])*scale[normal] < 1 - 1e-8
                or direction*(contour[normal]-background[normal])*scale[normal] < 1 - 1e-8):
            raise ValueError('Hair/background samples must straddle the actually observed boundary along its normal')
    t = out['x' if tangent == 0 else 'y']
    if out['contour'][-1][tangent]-out['contour'][0][tangent] < .5*(t[2]-t[1]) - 1e-12:
        raise ValueError('Observed contour samples must cover at least half of the plateau tangent interval')
    return out


def regions(value, binding):
    if type(value) is not dict or set(value) != set(S.REGIONS):
        raise ValueError('Crown, image-left and image-right support must be independent')
    return {name: None if value[name] is None else patch(value[name], name, binding) for name in S.REGIONS}


def protection(value):
    if (type(value) is not dict or set(value) != {'ears', 'neck', 'other_people', 'visible_anatomy_reviewed', 'whole_source_reviewed'}
            or value['visible_anatomy_reviewed'] is not True or value['whole_source_reviewed'] is not True):
        raise ValueError('Separately review all exposed ears/neck and the whole source for other people or contacts')
    out = deepcopy(value)
    for name, limit in (('ears', 2), ('neck', 1), ('other_people', 64)):
        if type(value[name]) is not list or len(value[name]) > limit:
            raise ValueError('Invalid explicit protected anatomy/person region count')
        out[name] = [box(b) for b in value[name]]
    return out


def source_faces_digest(state, binding):
    """Include retained disabled/manual/unresolved faces; detection is no census."""
    values = []
    for key, face in sorted(state['faces'].items()):
        if face['asset_sha256'] == binding['sha256']:
            ev = face['evidence']
            if (ev['source_width'], ev['source_height']) != (binding['width'], binding['height']):
                raise ValueError('A retained face has uncertain current-source extent')
            values.append({'face_ref': P.face_ref(face), 'box': face['box'],
                           'evidence': ev, 'manual': face['manual']})
    return digest(values)


def check_record(value):
    if (type(value) is not dict or set(value) != {'version', 'face_ref', 'source', 'row'}
            or type(value['version']) is not int or value['version'] != 1):
        raise ValueError('Invalid hair geometry support envelope')
    ref, binding = P.check_ref(value['face_ref']), source(value['source'])
    if min(binding['width'], binding['height']) < 2 or binding['sha256'] != ref['asset_sha256']:
        raise ValueError('Hair geometry belongs to another or degenerate source')
    row = value['row']
    fields = {'target', 'operation_id', 'semantic_model_sha256', 'semantic_evidence_sha256',
              'source_faces_sha256', 'regions', 'protection', 'review'}
    if (type(row) is not dict or set(row) != fields or row['target'] != KIND
            or row['operation_id'] != S.OPERATION_ID or row['semantic_model_sha256'] != MODEL_SHA256):
        raise ValueError('Hair geometry requires its own operation and pinned actual hair producer')
    P.digest(row['semantic_evidence_sha256']); P.digest(row['source_faces_sha256'])
    out = {'version': 1, 'face_ref': ref, 'source': binding, 'row': {
        **deepcopy(row), 'regions': regions(row['regions'], binding), 'protection': protection(row['protection'])}}
    content = deepcopy(out); del content['row']['review']
    expected = {'method': 'explicit_source_hair_geometry_review', 'operation_id': S.OPERATION_ID,
                'confirmed': True, 'review_key': digest(content)}
    if (type(row['review']) is not dict or row['review'] != expected
            or type(row['review'].get('confirmed')) is not bool):
        raise ValueError('Confirm this operation’s exact source, owner, contours, protections and evidence')
    return out


check = check_record


def _sample(weight, points):
    """Bilinear evidence lookup only, not displacement or image resampling."""
    xy = np.asarray(points, np.float64) * np.array([weight.shape[1]-1, weight.shape[0]-1])
    low = np.floor(xy).astype(np.int64)
    high = np.minimum(low + 1, np.array([weight.shape[1]-1, weight.shape[0]-1]))
    f = xy-low
    return ((1-f[:, 0])*(1-f[:, 1])*weight[low[:, 1], low[:, 0]]
            + f[:, 0]*(1-f[:, 1])*weight[low[:, 1], high[:, 0]]
            + (1-f[:, 0])*f[:, 1]*weight[high[:, 1], low[:, 0]]
            + f[:, 0]*f[:, 1]*weight[high[:, 1], high[:, 0]])


def verify_evidence(value, evidence):
    value = check_record(value)
    weight = E.check(evidence, value['source'])
    if SAVED.identity(evidence) != value['row']['semantic_evidence_sha256']:
        raise ValueError('Hair geometry references different retained measured semantic evidence')
    for name, part in value['row']['regions'].items():
        if part is None:
            continue
        if np.any(_sample(weight, part['hair_samples']) < .20):
            raise ValueError(name + ': marked hair interior lacks actual measured hair evidence')
        if np.any(_sample(weight, part['background_samples']) > .05):
            raise ValueError(name + ': exterior transition is not supported as clear non-hair background')
    return value


def verify_current(state, value):
    value = check_record(value)
    face = A.verify_face(state, value['face_ref'], value['source'])
    if face['manual']:
        raise ValueError('Hair geometry needs an actual verified retained face, not an invented landmark box')
    if source_faces_digest(state, value['source']) != value['row']['source_faces_sha256']:
        raise ValueError('Retained face ownership/boundaries changed; review hair geometry again')
    return face


def reviewed(state, face_ref, binding, region_data, protection_data, hair_evidence, *, confirmed):
    if confirmed is not True:
        raise ValueError('Confirm crown/side hair ownership and clear source transitions for this operation')
    state = P.check(state); binding = source(binding); ref = P.check_ref(face_ref)
    A.verify_face(state, ref, binding)
    E.check(hair_evidence, binding)
    value = {'version': 1, 'face_ref': ref, 'source': binding, 'row': {
        'target': KIND, 'operation_id': S.OPERATION_ID, 'semantic_model_sha256': MODEL_SHA256,
        'semantic_evidence_sha256': SAVED.identity(hair_evidence),
        'source_faces_sha256': source_faces_digest(state, binding),
        'regions': regions(region_data, binding), 'protection': protection(protection_data)}}
    value['row']['review'] = {'method': 'explicit_source_hair_geometry_review',
                             'operation_id': S.OPERATION_ID, 'confirmed': True, 'review_key': digest(value)}
    verify_current(state, value)
    return verify_evidence(value, hair_evidence)


def check_store(assets):
    """Mixed standard support bank; foreign operation validators remain owned by host."""
    if (type(assets) is not dict or len(assets) > MAX_ASSETS
            or len(json.dumps(assets, allow_nan=False).encode()) > MAX_STORE_BYTES):
        raise ValueError('Hair geometry support bank exceeds the retained-vector budget')
    for key, value in assets.items():
        P.digest(key)
        if type(value) is not dict or type(value.get('row')) is not dict or digest(value) != key:
            raise ValueError('Support content digest mismatch')
        if value.get('row', {}).get('target') == KIND:
            check_record(value)
    return deepcopy(assets)


def retain(state, assets, value):
    out = P.check(state); value = check_record(value)
    face = verify_current(out, value); assets = check_store(assets); key = digest(value)
    if key in assets and assets[key] != value:
        raise ValueError('Hair geometry support digest collision')
    assets[key] = value; assets = check_store(assets)
    descriptor = {'owner': value['face_ref'], 'content_sha256': key, 'kind': KIND}
    if face['local_assets'].get(KIND) != descriptor:
        face['local_assets'][KIND] = descriptor; out['revision'] += 1
    return P.check(out), assets


def resolve(state, assets, face_ref):
    ref = P.check_ref(face_ref); face = A.verify_face(state, ref)
    descriptor = face['local_assets'].get(KIND)
    if descriptor is None:
        return None
    key = descriptor['content_sha256']; value = assets.get(key)
    if value is None:
        raise ValueError('Retained hair geometry support is missing; not silently ignored')
    value = check_record(value)
    if (digest(value) != key or value['face_ref'] != ref
            or descriptor != {'owner': ref, 'kind': KIND, 'content_sha256': key}):
        raise ValueError('Hair geometry reference changed or belongs to another face')
    verify_current(state, value)
    return value


def detach(state, face_ref):
    out = P.check(state); ref = P.check_ref(face_ref)
    face = out['faces'].get(ref['face_instance_id'])
    if face is None or P.face_ref(face) != ref:
        raise ValueError('Hair geometry owner changed')
    if KIND in face['local_assets']:
        del face['local_assets'][KIND]; out['revision'] += 1
    return P.check(out)


def validate_project(state, assets, evidence_bank=None, *, source_frame=None):
    state = P.check(state); assets = check_store(assets)
    binding = None if source_frame is None else source(source_frame)
    for value in assets.values():
        if value.get('row', {}).get('target') != KIND:
            continue
        value = check_record(value)
        if evidence_bank is not None:
            saved = evidence_bank.get(value['row']['semantic_evidence_sha256'])
            if saved is None:
                raise ValueError('Project lost the immutable measured evidence for reviewed hair geometry')
            verify_evidence(value, SAVED.decode(saved))
    for face in state['faces'].values():
        if KIND not in face['local_assets']:
            continue
        value = resolve(state, assets, P.face_ref(face))
        if binding is not None and face['asset_sha256'] == binding['sha256'] and value['source'] != binding:
            raise ValueError('Hair geometry dimensions differ from the effective original/derived source')
    return assets


def support_vector(value, recipe):
    value = check_record(value); result = []
    for region, amount in zip(S.REGIONS, S.amounts(recipe)):
        part = value['row']['regions'][region]
        if amount != 0 and part is None:
            raise ValueError(region + ': nonneutral geometry needs its own reviewed observed contour')
        result.extend([0.] * 8 if amount == 0 else part['x'] + part['y'])
    return result
