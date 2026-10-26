# SPDX-License-Identifier: GPL-3.0-or-later
"""Authenticated transient full-source/repair resolver, never caller RGB + SHA.

Factories bind existing source owners and producer-grid analysis. Fitting does
not borrow an RGB8 delivery raster or resample a display proxy twice. UNRUN.
"""
from copy import deepcopy
from dataclasses import dataclass
from .neck_wrinkle_source_capture import poll

_TOKEN = object()


@dataclass(frozen=True)
class Packet:
    rgb: object
    analysis: dict
    resident_bytes: int
    proof: dict


class SourceResolver:
    def __init__(self, token, *, state, source, analyses, operations, proof, repair_sha256, loader, guard):
        if token is not _TOKEN:
            raise ValueError('Hair smoothing source resolvers require an existing immutable-source owner')
        self._token = token
        self.state = deepcopy(state)
        self.source = deepcopy(source)
        self.analyses = analyses
        self.operations = tuple(operations)
        self.proof = deepcopy(proof)
        self.repair_sha256 = repair_sha256
        self.loader = loader
        self.guard = guard
        self.captured = None


def from_engine(engine, *, state, source):
    from . import portrait_fit_source as F, creative_derived_source as D, creative_derived_repairs as R
    from .optics_candidate_identity import fingerprint
    source = F._binding(source)
    row, token = F._active(engine)
    path = row['path']
    base = D.record(engine)
    if base is not None:
        raise ValueError('Hair smoothing initially supports authenticated original files only, never derived composites')
    proof = D.row_proof({'path': path, 'state': {'_creative_base': base}})
    if proof['asset_sha256'] != source['sha256']:
        raise ValueError('Hair smoothing source belongs to another current document')
    D.verify(source, engine)
    operations = tuple(getattr(engine, '_repair_ops', ()))
    repair = R.stack_digest(engine)
    analyses = engine._people_analyses.get(source['sha256'], {})
    analysis_key = fingerprint(analyses)
    def guard():
        F._assert_active(engine, row, token)
        D.verify(source, engine)
        D.verify_row({'path': row['path'], 'state': {'_creative_base': D.record(engine)}}, proof)
        if row['path'] != path or R.stack_digest(engine) != repair:
            raise ValueError('Hair smoothing source or ordered repair stack changed during measurement')
        if fingerprint(engine._people_analyses.get(source['sha256'], {})) != analysis_key:
            raise ValueError('Hair smoothing measured analysis changed during source capture')
    def loader(**kwargs):
        return F.capture(engine, expected_source=source, **kwargs)
    guard()
    return SourceResolver(_TOKEN, state=state, source=source, analyses=analyses,
        operations=operations, proof=proof, repair_sha256=repair, loader=loader, guard=guard)


def from_export(spec, snapshot):
    from .hair_smoothing_inputs import KEY, needed
    if not needed(snapshot['state'], snapshot['asset_sha256']):
        return None
    from . import portrait_fit_source as F, creative_derived_source as D, creative_derived_repairs as R
    from .local_mask_state import file_stamp
    from .optics_candidate_identity import fingerprint
    info = deepcopy(snapshot.get(KEY))
    required = {'version', 'source', 'source_proof', 'path', 'stamp', 'repair_sha256', 'active_sha256'}
    if (type(info) is not dict or set(info) != required
            or type(info['version']) is not int or info['version'] != 1):
        raise ValueError('Frozen hair smoothing export lacks source/repair metadata')
    from .people_state import digest
    digest(info['repair_sha256']); digest(info['active_sha256'])
    source = F._binding(info['source']); proof = D.check_row_proof(info['source_proof'])
    if source['sha256'] != snapshot['asset_sha256'] or source['sha256'] != proof['asset_sha256']:
        raise ValueError('Frozen hair smoothing export names another source')
    base = D.record({'creative_base': getattr(spec, 'creative_base', None)})
    if base is not None or proof['creative_source'] is not None or snapshot.get('creative_source') is not None:
        raise ValueError('Hair smoothing cannot reinterpret a derived composite as an original source')
    derived = None if base is None else {'sha256': base['id'][7:], 'width': base['width'], 'height': base['height']}
    if derived != snapshot.get('creative_source') or derived != proof['creative_source']:
        raise ValueError('Hair smoothing export cannot reinterpret original and derived source ownership')
    operations = getattr(spec, '_hair_smoothing_repair_inputs', None)
    if operations is None:
        raise ValueError('Hair smoothing export requires frozen pre-materialization repair inputs')
    operations = tuple(operations)
    analyses = snapshot['analyses']; analysis_key = fingerprint(analyses)
    def guard():
        if R.digest_ops(operations, [], derived) != info['active_sha256']:
            raise ValueError('Hair smoothing frozen repair replay inputs changed')
        if fingerprint(analyses) != analysis_key:
            raise ValueError('Hair smoothing frozen producer-grid evidence changed')
        if list(file_stamp(info['path'])) != info['stamp']:
            raise ValueError('Hair smoothing original provenance file changed')
        D.verify_row({'path': info['path'], 'state': {'_creative_base': base}}, proof)
    def loader(*, byte_budget, cancelled):
        return F.capture_original(info['path'], expected_source=source,
            expected_stamp=info['stamp'], byte_budget=byte_budget, cancelled=cancelled)
    guard()
    return SourceResolver(_TOKEN, state=snapshot['state'], source=source, analyses=analyses,
        operations=operations, proof=proof, repair_sha256=info['repair_sha256'], loader=loader, guard=guard)


def resolve(resolver, *, face_ref, source, analysis, byte_budget, cancelled=None):
    import numpy as np
    from . import people_state as P, people_snapshot as SNAP
    from .optics_candidate_identity import fingerprint
    from .neck_wrinkle_source_capture import capture
    if type(resolver) is not SourceResolver or resolver._token is not _TOKEN:
        raise ValueError('Hair smoothing fitting rejects arbitrary source callbacks or pixels plus caller hashes')
    if type(byte_budget) is not int or byte_budget < 1:
        raise ValueError('Hair smoothing full-source capture requires a positive byte budget')
    poll(cancelled); resolver.guard()
    ref = P.check_ref(face_ref)
    if type(analysis) is not dict:
        raise ValueError('Hair smoothing source requires retained measured face analysis')
    if source != resolver.source or ref['asset_sha256'] != source['sha256']:
        raise ValueError('Hair smoothing face and canonical source disagree')
    raw = resolver.analyses.get(ref['face_instance_id'])
    if type(raw) is not dict or raw.get('face_ref') != ref or analysis.get('face_ref') != ref:
        raise ValueError('Hair smoothing source requires exact original producer-grid face evidence')
    # The caller may be rendering a resized grid. Its metadata and landmarks,
    # not its resized masks, must still name the original measured observation.
    for key in ('evidence', 'landmarks', 'face_skin_observation', 'body_skin_observation'):
        if fingerprint(raw.get(key)) != fingerprint(analysis.get(key)):
            raise ValueError('Hair smoothing render and producer-grid analysis provenance disagree')
    h, w = source['height'], source['width']; n = h*w
    if n > 32_000_000:
        raise ValueError('Hair smoothing original source exceeds 32 MP; no proxy fallback')
    if resolver.proof['creative_source'] is not None or resolver.proof['original_sha256'] != source['sha256']:
        raise ValueError('Hair smoothing measurement requires actual original-source provenance')
    planes = sum(raw.get(key) is not None for key in ('skin', 'excluded', 'face_skin', 'body_skin'))
    raw_bytes = sum(value.nbytes for value in raw.values() if isinstance(value, np.ndarray))
    # Canonical destination, immutable bytes copy, interpolation scratch and raw
    # retained evidence all charged before allocation. No inferred mask upgrades.
    analysis_peak = raw_bytes + (8*planes+16)*n + 8*1024**2
    resident_source = 12*n
    if byte_budget < analysis_peak+resident_source:
        raise MemoryError('Hair smoothing source and canonical semantic evidence exceed remaining budget')
    if resolver.captured is None:
        captured = capture(resolver.loader, resolver.operations, source,
            byte_budget=byte_budget-analysis_peak, cancelled=cancelled)
        resolver.guard(); poll(cancelled)
        resolver.captured = captured
    frozen = {'state': resolver.state, 'asset_sha256': source['sha256'],
              'analyses': {ref['face_instance_id']: raw}}
    _, _, canonical = SNAP.at_dimensions(frozen, (h, w), byte_budget=analysis_peak-raw_bytes)
    row = canonical[ref['face_instance_id']]
    # Bytes-backed arrays cannot be made writable through setflags by consumers.
    for key, value in list(row.items()):
        if isinstance(value, np.ndarray):
            row[key] = np.frombuffer(value.tobytes(order='C'), dtype=value.dtype).reshape(value.shape)
        elif isinstance(value, (dict, list)):
            row[key] = deepcopy(value)
    resident = resident_source + raw_bytes + sum(value.nbytes for value in row.values() if isinstance(value, np.ndarray))
    if resident > byte_budget:
        raise MemoryError('Hair smoothing immutable packet exceeds its admitted resident budget')
    resolver.guard(); poll(cancelled)
    captured = resolver.captured
    proof = {'version': 1, 'source': deepcopy(source), 'source_proof': deepcopy(resolver.proof),
        'input_sha256': captured.input_sha256, 'repair_sha256': resolver.repair_sha256,
        'encoding': 'encoded-srgb-f32-v1', 'source_bits': captured.source_bits,
        'orientation': 'exif_normalized_once',
        'stage': 'verified-repair-base' if resolver.operations else 'immutable-source'}
    rgb = np.frombuffer(captured.content, dtype=np.float32).reshape(h, w, 3)
    return Packet(rgb, row, resident, proof)
