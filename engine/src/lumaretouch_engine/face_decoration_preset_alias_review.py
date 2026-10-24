# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact mixed decoration preset review for every effective-source shared document.

Only the active document receives the planned mixed document recipe. Every
sibling keeps its own complete repair/crop state and renders the same candidate
portrait graph against its own effective source. AUTHORED / UNRUN.
"""
from copy import deepcopy
import time

from . import face_decoration_preset_review as REVIEW, face_decoration_preset_plan as PLAN
from . import face_style_alias_review as CLOSURE, virtual_copy_people as V
from . import creative_derived_source as SOURCE, collarbone_transfer_review as VISUAL
from .people_preset_plan import clone_state
from .optics_candidate_identity import fingerprint

FIELDS = REVIEW.FIELDS | {'members', 'review_sha256', 'before_bank_sha256'}
ACK_FIELDS = {'review_sha256', 'preset_sha256', 'applies_sha256', 'members'}
MEMBER_ACK_FIELDS = {'document_id', 'revision', 'before_sha256', 'after_sha256', 'coverage_sha256'}


def checked(value):
    if type(value) is not dict or set(value) != FIELDS or type(value['version']) is not int or value['version'] != 2:
        raise ValueError('Missing exact version-2 mixed preset alias review')
    REVIEW.checked({**{key: value[key] for key in REVIEW.FIELDS}, 'version': 1})
    if value['owner']['people_scope'] != V.PROJECT:
        raise ValueError('Mixed alias review requires the existing shared project owner')
    members = value['members']; current = value['visual']; seen = set()
    if type(members) is not list or not 2 <= len(members) <= CLOSURE.MAX_MEMBERS:
        raise ValueError('Mixed preset review requires all two to sixteen affected documents')
    for index, member in enumerate(members):
        if (type(member) is not dict or set(member) != {'path', 'role', 'visual'}
                or member['role'] != ('active' if index == 0 else 'sibling')
                or type(member['path']) is not str or not 1 <= len(member['path'].encode('utf-8')) <= 4096
                or '\0' in member['path']):
            raise ValueError('Invalid exact mixed preset member identity or role')
        visual = VISUAL.checked(member['visual'])
        if (visual['document_id'] in seen or int(visual['revision']) >= CLOSURE.MAX_REVISION
                or visual['source_proof']['asset_sha256'] != value['face_ref']['asset_sha256']
                or any(visual[key] != current[key] for key in
                       ('source_size', 'coverage_sha256', 'before_people_sha256', 'candidate_people_sha256'))):
            raise ValueError('Mixed preset alias images disagree on shared source, graph or coverage')
        seen.add(visual['document_id'])
        if index == 0:
            if visual != current: raise ValueError('The active image pair must be the first reviewed member')
        elif (visual['before_state_sha256'] != visual['candidate_state_sha256']
              or visual['before_output_size'] != visual['after_output_size']):
            raise ValueError('A sibling mixed preset cannot acquire another document recipe or crop')
    VISUAL._hash(value['before_bank_sha256'])
    VISUAL._hash(value['review_sha256'])
    if REVIEW.digest({key: item for key, item in value.items() if key != 'review_sha256'}) != value['review_sha256']:
        raise ValueError('Mixed preset alias review digest changed')
    return deepcopy(value)


def check_ack(raw):
    """Syntax only, useful for binding a no-write receipt, never acceptance."""
    if type(raw) is not dict or set(raw) != ACK_FIELDS:
        raise ValueError('Every mixed preset alias image pair requires exact acknowledgement')
    for key in ('review_sha256', 'preset_sha256', 'applies_sha256'): VISUAL._hash(raw[key])
    if type(raw['members']) is not list or not 2 <= len(raw['members']) <= CLOSURE.MAX_MEMBERS:
        raise ValueError('Invalid complete mixed preset acknowledgement member count')
    from .people_state import token
    seen = set()
    for member in raw['members']:
        if type(member) is not dict or set(member) != MEMBER_ACK_FIELDS or not CLOSURE._revision(member['revision']):
            raise ValueError('Invalid mixed preset member acknowledgement')
        identity = token(member['document_id'])
        if identity in seen or int(member['revision']) >= CLOSURE.MAX_REVISION:
            raise ValueError('Mixed preset acknowledgement repeats or exhausts a document revision')
        seen.add(identity)
        for key in ('before_sha256', 'after_sha256', 'coverage_sha256'): VISUAL._hash(member[key])
    return deepcopy(raw)


def acknowledgment(raw, wrapper):
    wrapper = checked(wrapper); check_ack(raw)
    expected = {key: wrapper[key] for key in ('review_sha256', 'preset_sha256', 'applies_sha256')}
    expected['members'] = [{'document_id': v['document_id'], 'revision': v['revision'],
        'before_sha256': v['before']['sha256'], 'after_sha256': v['after']['sha256'],
        'coverage_sha256': v['coverage_sha256']} for v in (member['visual'] for member in wrapper['members'])]
    if raw != expected: raise ValueError('Review every exact mixed preset image pair in the frozen member order')
    return deepcopy(expected)


def required(engine, row, load_id, revision):
    owner, _ = REVIEW._target(engine, row, load_id, revision, reviewed_aliases=True)
    current = engine._people_preset_capture(); source = SOURCE.row_proof({**row, 'state': current})
    return CLOSURE.has_aliases(engine, (owner, row, current, source, None))


def _plans(entry):
    plan = entry['plan']
    return {V.PROJECT: {'row': entry['row'], 'before': plan.before, 'candidate': plan.candidate,
                         'reviewed_face_refs': deepcopy(entry['refs']),
                         'decoration_alias_authority': entry['authority']}}


def _targets(engine, entry, current):
    """The complete source closure remains explicit even for graph no-ops."""
    ref = entry['plan'].target_ref; result = {}; batch = entry['batch']
    for index, row in enumerate(batch.documents.rows()):
        if V.scope(row) != V.PROJECT: continue
        source = SOURCE.row_proof({**row, 'state': current} if row is entry['row'] else row)
        if source['asset_sha256'] != ref['asset_sha256']: continue
        version = batch.versions.check_advance(row)
        result[str(index)] = {'path': row['path'], 'document_id': version.document_id, 'revision': version.revision,
            'asset_sha256': ref['asset_sha256'], 'people_scope': V.PROJECT, 'source_proof': source,
            'reviewed_face_refs': deepcopy(entry['refs'])}
    return result


def _dormant_key(engine, row):
    """Freeze retained closure inputs, not just currently active membership."""
    project = getattr(engine, '_project', None) or {}
    return fingerprint({'saved_docs': project.get('docs', []),
        'retained_histories': project.get('people_document_history', {}),
        'source_assets': project.get('source_assets', {}),
        'rows': [{'document_id': other.get('document_id'), 'path': other.get('path'),
                  'scope': V.scope(other), 'trashed': other.get('trashed'),
                  'new_import': other.get('_people_new_import'),
                  'undo': getattr(engine, '_undo', []) if other is row else other.get('undo', []),
                  'redo': getattr(engine, '_redo', []) if other is row else other.get('redo', [])}
                 for other in CLOSURE._scope_rows(engine, row)]})


def _verify(engine, entry, wrapper, before, candidate):
    plan = entry['plan']; row = entry['row']; visual = wrapper['visual']
    owner, document = REVIEW._target(engine, row, wrapper['load_id'], visual['revision'], reviewed_aliases=True)
    if (entry['claimed'] or owner is not plan.owner or owner.fence != plan.owner_fence or owner.snapshot() != plan.before
            or document != visual['document_id'] or V.scope(row) != V.PROJECT
            or engine._batch_controller() is not entry['batch']
            or engine._document_versions().workspace != entry['workspace']
            or fingerprint(before) != entry['before_input_sha256']
            or fingerprint(candidate) != entry['candidate_input_sha256']
            or _dormant_key(engine, row) != entry['dormant_key']
            or REVIEW.digest(_bank(engine)) != wrapper['before_bank_sha256']
            or _bank(engine) != entry['bank']):
        raise ValueError('Mixed preset owner, complete document inputs or retained source closure changed')
    ref = plan.target_ref
    PLAN.admit(engine, plan.before, ref, REVIEW.SCOPE.S.check(candidate.get(REVIEW.SCOPE.FIELD)), reviewed_aliases=True)
    entry['authority'].verify(engine,row,plan.before,plan.candidate)
    CLOSURE.verify_dormant(engine, row, {ref['asset_sha256']})
    members = CLOSURE._eligible(engine, row, before, ref['asset_sha256'])
    if len(members) != len(entry['members']): raise ValueError('Mixed preset affected membership changed')
    for actual, frozen in zip(members, entry['members']):
        other, state, source, version = actual; v = frozen['visual']
        after = plan.state if other is row else state
        if (other is not frozen['row'] or other['path'] != frozen['path']
                or version.document_id != v['document_id'] or str(version.revision) != v['revision']
                or source != v['source_proof']
                or REVIEW._snapshot_key(engine, other, state, plan.before) != frozen['before_key']
                or REVIEW._snapshot_key(engine, other, after, plan.candidate) != frozen['after_key']
                or fingerprint(state) != frozen['state_sha256']
                or PLAN.coverage(engine,other,plan.candidate,ref,plan.before,state=state) != wrapper['coverage']):
            raise ValueError('Mixed preset alias source, repair, crop, support or complete state changed')
        SOURCE.verify_row({**other, 'state': state}, source)
    if (_targets(engine, entry, before) != entry['targets']
            or PLAN.coverage(engine, row, plan.candidate, ref, plan.before, state=before) != wrapper['coverage']):
        raise ValueError('Mixed preset target closure or retained face-owned visibility support changed')


def _bank(engine):
    from .face_decoration_support_alias_transaction import bank
    return bank(engine)


def prepare(engine, row, before, candidate, load_id, revision, preset, modules):
    from .people_scope import plan_preset
    from .people_transfer_inventory import proof
    from .people_graph_owner import affected_assets
    owner, document = REVIEW._target(engine, row, load_id, revision, reviewed_aliases=True)
    from .preset_portrait_review import decoration_required
    if not decoration_required(modules,before):
        raise ValueError('No selected or retained decoration requires this complete mixed preset review')
    plan = plan_preset(engine, candidate, require_active=True, reviewed_face_decoration=True,
        reviewed_face_decoration_aliases=True, strict_local=True)
    if (not plan.managed or plan.owner is not owner or plan.target_ref is None
            or candidate.get(REVIEW.SCOPE.TARGET) != plan.target_ref
            or affected_assets(plan.before, plan.candidate) - {plan.target_ref['asset_sha256']}):
        raise ValueError('Mixed alias preset must retain one explicit source-owned portrait target')
    PLAN.admit(engine, plan.before, plan.target_ref, REVIEW.SCOPE.S.check(candidate.get(REVIEW.SCOPE.FIELD)), reviewed_aliases=True)
    members = CLOSURE._eligible(engine, row, before, plan.target_ref['asset_sha256'])
    PLAN.check_scalar_graph(plan.before,plan.candidate,plan.target_ref)
    coverage = PLAN.coverage(engine,row,plan.candidate,plan.target_ref,plan.before,state=before)
    entry = {'engine': engine, 'row': row, 'plan': plan, 'before': clone_state(before),
        'candidate_input': clone_state(candidate), 'before_input_sha256': fingerprint(before),
        'candidate_input_sha256': fingerprint(candidate), 'batch': engine._batch_controller(),
        'workspace': engine._document_versions().workspace, 'dormant_key': _dormant_key(engine, row),
        'members': [], 'claimed': False, 'served': set(), 'expires': time.monotonic() + REVIEW.TTL,
        'bank': deepcopy(_bank(engine)), 'modules': deepcopy(modules),
        'refs': [deepcopy(item['face_ref']) for item in coverage['targets']]}
    entry['targets'] = _targets(engine, entry, before)
    if ({target['document_id'] for target in entry['targets'].values()} != {item[3].document_id for item in members}
            or len(entry['targets']) != len(members)):
        raise ValueError('Mixed preset ledger closure contains an unavailable or unreviewed document')
    from .face_decoration_preset_alias_authority import mint
    entry['authority'] = mint(engine,row,plan.before,plan.candidate,entry['targets'],entry['refs'],
        selected_ref=plan.target_ref,modules=modules,before_assets=entry['bank'])
    displays = {}; public = []; encoded_bytes = 0
    for other, state, source, version in members:
        after = plan.state if other is row else state
        if PLAN.coverage(engine,other,plan.candidate,plan.target_ref,plan.before,state=state) != coverage:
            raise ValueError('Mixed preset aliases disagree on complete retained target-owned face coverage')
        before_key = REVIEW._snapshot_key(engine, other, state, plan.before)
        after_key = REVIEW._snapshot_key(engine, other, after, plan.candidate)
        a, left, proof_a = REVIEW._image(engine, other, state, plan.before, version.document_id, version.revision)
        b, right, proof_b = REVIEW._image(engine, other, after, plan.candidate, version.document_id, version.revision)
        if (proof_a['source_proof'] != source or proof_b['source_proof'] != source
                or proof_a['source_size'] != proof_b['source_size']):
            raise ValueError('Mixed preset alias image changed immutable source or provenance')
        encoded_bytes += len(left['base64']) + len(right['base64'])
        if encoded_bytes > VISUAL.MAX_TOTAL_BASE64:
            raise ValueError('Complete mixed preset images exceed the immutable preparation budget; no member was omitted')
        visual = VISUAL.checked({'version': 1, 'document_id': version.document_id, 'revision': str(version.revision),
            'source_proof': source, 'before_state_sha256': proof_a['candidate_sha256'],
            'candidate_state_sha256': proof_b['candidate_sha256'], 'before_people_sha256': proof_a['people_sha256'],
            'candidate_people_sha256': proof_b['people_sha256'], 'source_size': proof_a['source_size'],
            'before_output_size': proof_a['output_size'], 'after_output_size': proof_b['output_size'],
            'coverage_sha256': VISUAL.coverage_digest(coverage), 'before': a, 'after': b})
        public.append({'path': other['path'], 'role': 'active' if other is row else 'sibling', 'visual': visual})
        entry['members'].append({'row': other, 'path': other['path'], 'visual': visual,
            'before_key': before_key, 'after_key': after_key, 'state_sha256': fingerprint(state)})
        displays[version.document_id] = {'revision': visual['revision'], 'before': left, 'after': right}
    wrapper = {'version': 2, 'preset_sha256': REVIEW.digest(preset), 'applies_sha256': REVIEW.digest(modules),
        'load_id': load_id, 'owner': proof(engine, row, plan.before, source_row={**row, 'state': before}),
        'face_ref': plan.target_ref, 'coverage': coverage, 'visual': public[0]['visual'],
        'before_bank_sha256': REVIEW.digest(entry['bank']), 'members': public}
    wrapper['review_sha256'] = REVIEW.digest(wrapper); wrapper = checked(wrapper)
    _verify(engine, entry, wrapper, before, candidate)
    entry['images'] = displays; key = REVIEW.digest(wrapper)
    REVIEW._ENTRIES[key] = entry; REVIEW._ENTRIES.move_to_end(key)
    while len(REVIEW._ENTRIES) > REVIEW.MAX_PLANS: REVIEW._ENTRIES.popitem(last=False)
    return wrapper, deepcopy(wrapper)


def verify(engine, row, before, candidate, load_id, revision, wrapper):
    wrapper = checked(wrapper); entry = REVIEW._entry(wrapper, engine)
    if entry['row'] is not row or load_id != wrapper['load_id'] or str(revision) != wrapper['visual']['revision']:
        raise ValueError('Mixed preset alias review cannot move to another document or load')
    _verify(engine, entry, wrapper, before, candidate)


def verify_live(engine, wrapper):
    wrapper = checked(wrapper); entry = REVIEW._entry(wrapper, engine)
    _verify(engine, entry, wrapper, engine._people_preset_capture(), entry['candidate_input'])


def served(wrapper, document, side):
    entry = REVIEW._entry(wrapper)
    if side not in ('before', 'after') or document not in {item['visual']['document_id'] for item in wrapper['members']}:
        raise ValueError('Only a frozen mixed preset member can acknowledge served images')
    entry['served'].add((document, side))


def verify_served(wrapper):
    entry = REVIEW._entry(wrapper)
    required_images = {(member['visual']['document_id'], side) for member in wrapper['members'] for side in ('before', 'after')}
    if entry['served'] != required_images:
        raise ValueError('Load every affected mixed preset before/after image before applying')


def publish(engine, row, before, candidate, load_id, revision, wrapper, modules, request_id, *, ack, verify_images=None):
    from .face_decoration_preset_alias_transaction import commit
    wrapper = checked(wrapper); entry = REVIEW._entry(wrapper, engine)
    verify(engine, row, before, candidate, load_id, revision, wrapper); verify_served(wrapper)
    acknowledgment(ack,wrapper)
    if REVIEW.digest(modules) != wrapper['applies_sha256']:
        raise ValueError('Mixed preset publication cannot change its selected modules')
    if not callable(verify_images):
        raise ValueError('Mixed preset publication requires its retained immutable image verifier')
    def verify_before():
        verify_live(engine, wrapper)
        verify_served(wrapper)
        verify_images()
    try:
        result = commit(engine, review=wrapper, plans=_plans(entry), targets=deepcopy(entry['targets']),
            current_before=entry['before'], current_after=entry['plan'].state, modules=modules,
            request_id=request_id, ack=ack, verify_before=verify_before)
        entry['claimed'] = True
        return result
    except Exception as error:
        # Never permit a fresh mutation after an uncertain write, even if a
        # compensating graph restore returned to the old scalar content.
        if getattr(error, 'side_effects_started', False): entry['claimed'] = True
        raise
