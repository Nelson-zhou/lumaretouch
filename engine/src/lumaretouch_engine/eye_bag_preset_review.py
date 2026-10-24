# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact mixed-preset portrait planning and image evidence. AUTHORED / UNRUN.

Runtime plans are bounded session data, not a second history or serialized asset.
Only the existing preset transaction may execute/restore their reviewed graph.
"""
from collections import OrderedDict
from copy import deepcopy
from hashlib import sha256
import json
import time

from . import collarbone_transfer_review as VISUAL
from . import eye_bag_preserve_scope as SCOPE

_ENTRIES = OrderedDict()
MAX_PLANS = 8
TTL = 30 * 60
FIELDS = {'version', 'preset_sha256', 'applies_sha256', 'load_id', 'owner', 'face_ref', 'coverage', 'visual', 'replace_legacy'}


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                             allow_nan=False).encode()).hexdigest()


def checked(value):
    from .people_transfer_inventory import check_proof
    from .people_state import check_ref
    if type(value) is not dict or set(value) != FIELDS or type(value['version']) is not int or value['version'] != 1:
        raise ValueError('Missing exact eye-bag preset review')
    for name in ('preset_sha256', 'applies_sha256'): VISUAL._hash(value[name])
    if type(value['load_id']) is not str or not 1 <= len(value['load_id']) <= 64:
        raise ValueError('Preset review requires its exact loaded document')
    if type(value['replace_legacy']) is not bool: raise ValueError('Explicit legacy replacement choice is required')
    owner = check_proof(value['owner']); ref = check_ref(value['face_ref'])
    visual = VISUAL.checked(value['visual'])
    coverage = value['coverage']
    if (visual['document_id'] != owner['document']['document_id']
            or visual['revision'] != str(owner['document']['revision'])
            or visual['source_proof'] != owner['source_proof'] or ref['asset_sha256'] != owner['source_proof']['asset_sha256']
            or type(coverage) is not dict or set(coverage) != {'version', 'support_transfer', 'targets'}
            or type(coverage['version']) is not int or coverage['version'] != 1 or coverage['support_transfer'] != 'none'
            or type(coverage['targets']) is not list or len(coverage['targets']) != 1
            or type(coverage['targets'][0]) is not dict or coverage['targets'][0].get('face_ref') != ref
            or VISUAL.coverage_digest(coverage) != visual['coverage_sha256']):
        raise ValueError('Preset visual, person, source and coverage do not have one owner')
    item = coverage['targets'][0]
    if (type(item) is not dict or set(item) != {'face_ref','scope','ridge_sha256','sides'}
            or item['scope'] not in ('target-reviewed-ridge','neutral-no-effect')
            or type(item['sides']) is not list or any(type(side) is not str or side not in ('left','right') for side in item['sides'])
            or item['sides'] != sorted(set(item['sides']))):
        raise ValueError('Invalid target-owned eye-bag coverage')
    if item['scope'] == 'neutral-no-effect':
        if item['ridge_sha256'] is not None or item['sides']: raise ValueError('Neutral review cannot claim active ridge support')
    else:
        VISUAL._hash(item['ridge_sha256'])
        if not item['sides']: raise ValueError('Active eye-bag review needs independently reviewed target sides')
    return deepcopy(value)


def acknowledgment(raw, wrapper):
    wrapper = checked(wrapper); visual = wrapper['visual']
    expected = {'document_id': visual['document_id'], 'revision': visual['revision'],
                'before_sha256': visual['before']['sha256'], 'after_sha256': visual['after']['sha256'],
                'coverage_sha256': visual['coverage_sha256'], 'preset_sha256': wrapper['preset_sha256'],
                'applies_sha256': wrapper['applies_sha256'], 'replace_legacy': wrapper['replace_legacy']}
    if type(raw) is not dict or type(raw.get('replace_legacy')) is not bool or set(raw) != set(expected) or raw != expected:
        raise ValueError('Review this complete mixed preset image pair before applying')
    return deepcopy(expected)


def _entry(wrapper, engine=None):
    wrapper = checked(wrapper); key = digest(wrapper); now = time.monotonic()
    for stale, item in list(_ENTRIES.items()):
        if now >= item['expires']: del _ENTRIES[stale]
    entry = _ENTRIES.get(key)
    if entry is None or (engine is not None and entry['engine'] is not engine):
        raise ValueError('Exact preset plan is unavailable or expired; prepare again')
    return entry


def take_images(wrapper):
    entry = _entry(wrapper)
    images = entry.pop('images', None)
    if images is None: raise ValueError('Preset image attachment was already consumed; prepare again')
    return images


def _target(engine, row, load_id, revision):
    from .virtual_copy_people import current_row
    from .people_preset_plan import require_active_owner
    if current_row(engine) is not row or getattr(engine, '_load_id', None) != load_id:
        raise ValueError('Preset target or load identity changed')
    version = engine._document_versions().version(row)
    if str(version.revision) != str(revision): raise ValueError('Preset target revision changed')
    owner = require_active_owner(engine)
    from .eye_bag_preserve_host import _live
    from .people_recovery import selection
    _, graph, _, ref = selection(engine, editing=True)
    _live(engine, graph, {'scope':'face','target_id':ref['face_instance_id'],'face_ref':ref})
    return owner, version.document_id


def _snapshot_key(*args, **kwargs):
    from .portrait_review_render import snapshot_key
    return snapshot_key(*args, **kwargs)


def _coverage(engine, row, graph, ref):
    from .eye_bag_preset_plan import coverage
    return coverage(engine, row, graph, ref)


def _image(*args, **kwargs):
    from .portrait_review_render import image
    return image(*args, **kwargs)


def prepare(engine, row, before, candidate, load_id, revision, preset, modules, replace_legacy=False):
    from .people_scope import plan_preset
    from .people_preset_plan import clone_state
    from .people_transfer_inventory import proof
    from .optics_candidate_identity import fingerprint
    from .creative_derived_source import verify_row
    owner, document = _target(engine, row, load_id, revision)
    if type(replace_legacy) is not bool: raise ValueError('Explicit eye-bag legacy choice required')
    if SCOPE.OP not in modules: raise ValueError('A eye-bag review cannot bless another preset')
    plan = plan_preset(engine, candidate, require_active=True, reviewed_eye_bag=True, replace_legacy_eye_bag=replace_legacy, strict_local=True)
    if not plan.managed or plan.owner is not owner or plan.target_ref is None:
        raise ValueError('Exact mixed preset review requires one existing explicit portrait target')
    ref = plan.target_ref
    from .eye_bag_preset_plan import admit
    admit(engine, plan.before, ref, SCOPE.S.check(candidate.get(SCOPE.FIELD)))
    if candidate.get(SCOPE.TARGET) != ref: raise ValueError('Eye-bag preset target differs from the actual mixed planner')
    owner_proof = proof(engine, row, plan.before, source_row={**row, 'state': before})
    coverage = _coverage(engine, row, plan.candidate, ref)
    before_key = _snapshot_key(engine, row, before, plan.before)
    after_key = _snapshot_key(engine, row, plan.state, plan.candidate)
    # _replay_state can install non-people state before raising; execute_plan
    # then restores its own graph. Admit only that exact frozen hybrid, not
    # arbitrary partial writes or unrelated intervening edits.
    failed_key = _snapshot_key(engine, row, plan.state, plan.before)
    a, image_a, left = _image(engine, row, before, plan.before, document, revision)
    b, image_b, right = _image(engine, row, plan.state, plan.candidate, document, revision)
    if left['source_proof'] != right['source_proof'] or left['source_size'] != right['source_size']:
        raise ValueError('Mixed preset image pair changed immutable source')
    visual = VISUAL.checked({'version': 1, 'document_id': document, 'revision': str(revision),
        'source_proof': left['source_proof'], 'before_state_sha256': left['candidate_sha256'],
        'candidate_state_sha256': right['candidate_sha256'], 'before_people_sha256': left['people_sha256'],
        'candidate_people_sha256': right['people_sha256'], 'source_size': left['source_size'],
        'before_output_size': left['output_size'], 'after_output_size': right['output_size'],
        'coverage_sha256': VISUAL.coverage_digest(coverage), 'before': a, 'after': b})
    wrapper = checked({'version': 1, 'preset_sha256': digest(preset), 'applies_sha256': digest(modules),
        'load_id': load_id, 'owner': owner_proof, 'face_ref': ref, 'coverage': coverage, 'visual': visual,
        'replace_legacy': replace_legacy})
    if (_target(engine, row, load_id, revision)[0] is not owner or owner.fence != plan.owner_fence
            or owner.snapshot() != plan.before or before_key != _snapshot_key(engine, row, before, plan.before)
            or after_key != _snapshot_key(engine, row, plan.state, plan.candidate)
            or coverage != _coverage(engine, row, plan.candidate, ref)):
        raise ValueError('Complete preset inputs changed while preparing images')
    verify_row({**row, 'state': before}, owner_proof['source_proof'])
    key = digest(wrapper)
    _ENTRIES[key] = {'engine': engine, 'row': row, 'plan': plan, 'before': clone_state(before),
        'before_key': before_key, 'after_key': after_key, 'failed_key': failed_key, 'candidate_input_sha256': fingerprint(candidate),
        'before_input_sha256': fingerprint(before), 'images': {'revision': str(revision), 'before': image_a, 'after': image_b},
        'expires': time.monotonic()+TTL, 'write_fence': None}
    _ENTRIES.move_to_end(key)
    while len(_ENTRIES) > MAX_PLANS: _ENTRIES.popitem(last=False)
    return wrapper, deepcopy(wrapper)


def verify(engine, row, before, candidate, load_id, revision, wrapper):
    from .optics_candidate_identity import fingerprint
    from .creative_derived_source import verify_row
    entry = _entry(wrapper, engine); plan = entry['plan']; owner, document = _target(engine, row, load_id, revision)
    if (entry['row'] is not row or load_id != wrapper['load_id'] or document != wrapper['visual']['document_id']
            or str(revision) != wrapper['visual']['revision'] or owner is not plan.owner
            or owner.fence != plan.owner_fence or owner.snapshot() != plan.before
            or fingerprint(before) != entry['before_input_sha256'] or fingerprint(candidate) != entry['candidate_input_sha256']
            or _snapshot_key(engine, row, before, plan.before) != entry['before_key']
            or _snapshot_key(engine, row, plan.state, plan.candidate) != entry['after_key']
            or _coverage(engine, row, plan.candidate, wrapper['face_ref']) != wrapper['coverage']):
        raise ValueError('Exact mixed preset target, state, portrait plan or support changed')
    verify_row({**row, 'state': before}, wrapper['owner']['source_proof'])


def replay(engine, row, value, load_id, revision, wrapper, rollback=False, **kwargs):
    from .people_scope import execute_plan, restore_plan
    from .optics_candidate_identity import fingerprint
    from .creative_derived_source import verify_row
    entry = _entry(wrapper, engine); plan = entry['plan']; owner, document = _target(engine, row, load_id, revision)
    if entry['row'] is not row or load_id != wrapper['load_id'] or document != wrapper['visual']['document_id'] or owner is not plan.owner:
        raise ValueError('Preset replay cannot move to another owner or document')
    actual = engine._people_preset_capture()
    verify_row({**row, 'state': actual}, wrapper['owner']['source_proof'])
    if not rollback:
        if (entry['write_fence'] is not None or owner.fence != plan.owner_fence or owner.snapshot() != plan.before
                or _snapshot_key(engine, row, actual, owner.snapshot()) != entry['before_key']
                or fingerprint(value) != entry['candidate_input_sha256']
                or _snapshot_key(engine, row, plan.state, plan.candidate) != entry['after_key']):
            raise ValueError('Current full preset dependencies changed before the reviewed write')
        entry['write_fence'] = owner.fence
        try: return execute_plan(engine, plan, **kwargs)
        finally: entry['write_fence'] = owner.fence
    if entry['write_fence'] is None or owner.fence != entry['write_fence']:
        raise ValueError('Preset rollback cannot overwrite a newer portrait edit')
    key = _snapshot_key(engine, row, actual, owner.snapshot())
    if key not in (entry['before_key'], entry['after_key'], entry['failed_key']):
        raise ValueError('Preset failed outside its exact reviewed before/candidate states; explicit recovery is required')
    if _snapshot_key(engine, row, value, plan.before) != entry['before_key']:
        raise ValueError('Preset rollback state differs from its actual frozen original')
    try: return restore_plan(engine, plan, entry['before'], expected_owner_fence=owner.fence, **kwargs)
    finally: entry['write_fence'] = owner.fence


def verify_applied(engine, row, actual, load_id, revision, wrapper, rollback=False):
    from .creative_derived_source import verify_row
    entry = _entry(wrapper, engine); plan = entry['plan']; owner, document = _target(engine, row, load_id, revision)
    if (entry['row'] is not row or load_id != wrapper['load_id'] or document != wrapper['visual']['document_id']
            or owner is not plan.owner or owner.fence != entry['write_fence']
            or _snapshot_key(engine, row, actual, owner.snapshot()) != entry['before_key' if rollback else 'after_key']):
        raise ValueError('Actual preset publication does not match the complete reviewed portrait/state plan')
    verify_row({**row, 'state': actual}, wrapper['owner']['source_proof'])
