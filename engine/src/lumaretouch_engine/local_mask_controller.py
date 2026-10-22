"""Capture-bound retained mask edits with one post-history terminal receipt."""
from collections import OrderedDict
from copy import deepcopy
from hashlib import sha256
import json
from . import local_mask_state as S
from .source_patch_controller import PROOF_KEYS
from .white_balance_controller import identity, error_text

KEYS = {'cmd', 'action', 'request_id', 'mutation', *PROOF_KEYS}
GEOMETRY = {'brush': ('points', 'axes'), 'linear': ('start', 'end', 'cross'),
            'radial': ('center', 'axes')}


def prepare_mutation(engine, capture, mutation, *, accepted_prompted=False, semantic_owner=None):
    if type(mutation) is not dict: raise ValueError('Mask mutation must be an object')
    action = mutation.get('action')
    fields = {'upsert': {'action', 'object', 'coordinate_space'}, 'delete': {'action', 'id'},
              'move': {'action', 'id', 'index'}, 'bind': {'action', 'enabled'}, 'clear': {'action'}}
    if action not in fields or set(mutation) != fields[action]: raise ValueError('Invalid mask mutation fields')
    old = S.check(engine._local_masks)
    new = deepcopy(old)
    objects = new['recipe']['objects']
    scope = engine._grade_scope
    if action == 'upsert':
        obj = mutation['object']
        normalized = S.R.check_stack({'version': 1, 'domain': 'source-normalized', 'objects': [obj]})['objects'][0]
        index = next((i for i, row in enumerate(objects) if row['id'] == normalized['id']), None)
        if normalized['kind'] == 'prompted' and not accepted_prompted:
            if (index is None or objects[index]['kind'] != 'prompted'
                    or normalized['selection'] != objects[index]['selection']
                    or mutation['coordinate_space'] != 'source'):
                raise ValueError('New AI selections require an explicitly reviewed engine candidate')
        if mutation['coordinate_space'] == 'capture':
            from .local_mask_geometry import inverse_object
            normalized = inverse_object(capture['spec'], normalized, capture['valid'], capture['descriptor']['full_source'])
        elif mutation['coordinate_space'] == 'source':
            if index is None or normalized['kind'] != objects[index]['kind']:
                raise ValueError('Source edits require an existing retained object')
            if any(normalized[k] != objects[index][k] for k in GEOMETRY.get(normalized['kind'], ())):
                raise ValueError('Redraw geometry on a newly reviewed source capture')
        else: raise ValueError('Unknown mask coordinate domain')
        source = S.bind_source(engine)
        if objects and old['source'] != source: raise ValueError('Source changed; retained masks cannot be rebound silently')
        new['source'] = source
        if normalized['kind'] == 'semantic':
            owner = semantic_owner or S.current_owner(engine)
            if owner is None: raise ValueError('Analyze this photo before choosing a semantic channel')
            existing = any(o['kind'] == 'semantic' for o in old['recipe']['objects'])
            if existing and old['semantic_owner'] != owner:
                raise ValueError('Existing semantic masks belong to another analysis backend')
            new['semantic_owner'] = owner
        if index is None: objects.append(normalized)
        else: objects[index] = normalized
        scope = 'objects'
    elif action in ('delete', 'move'):
        index = next((i for i, row in enumerate(objects) if row['id'] == mutation['id']), None)
        if index is None: raise ValueError('Mask object no longer exists')
        if objects[index]['kind'] == 'full': raise ValueError('The full-image mask cannot be moved or deleted')
        if action == 'delete': objects.pop(index)
        else:
            target = mutation['index']
            if type(target) is not int or not 0 <= target < len(objects): raise ValueError('Invalid mask order')
            objects.insert(target, objects.pop(index))
    elif action == 'bind':
        if type(mutation['enabled']) is not bool: raise ValueError('Mask binding must be boolean')
        scope = 'objects' if mutation['enabled'] else 'all'
    else:
        # The handbook's full-image object is immutable, not an ordinary layer.
        objects[:] = [obj for obj in objects if obj['kind'] == 'full']
    new['recipe'] = S.R.check_transition(old['recipe'], new['recipe'])
    if not objects:
        new['source'] = None
        new['semantic_owner'] = None
    if not any(o['kind'] == 'semantic' for o in objects): new['semantic_owner'] = None
    full = capture['descriptor']['full_source']
    S.R.validate_budget(new['recipe'], (full[1], full[0]))
    return S.check(new), scope


class MaskController:
    def __init__(self, engine, emit):
        self.engine, self.emit = engine, emit
        self.pending = None
        self.cache = OrderedDict()

    def prepare(self, p):
        result = {'event': 'local_masks_result', 'protocol': 1, 'action': 'apply',
                  'request_id': identity(p.get('request_id'), 128),
                  **{k: identity(p.get(k), 128) for k in PROOF_KEYS},
                  'success': False, 'outcome_unknown': False, 'requires_reload': False}
        self.pending = {'result': result, 'digest': None, 'started': False}
        try:
            if set(p) != KEYS or p['cmd'] != 'local_masks' or p['action'] != 'apply':
                raise ValueError('Invalid local-mask command')
            if result['request_id'] is None or any(result[k] is None for k in PROOF_KEYS):
                raise ValueError('Invalid local-mask request identity')
            raw = json.dumps(p, sort_keys=True, allow_nan=False).encode()
            if len(raw) > 131072: raise ValueError('Mask mutation exceeds 128 KiB')
            digest = self.pending['digest'] = sha256(raw).hexdigest()
            if result['request_id'] in self.cache:
                previous, receipt = self.cache[result['request_id']]
                if previous != digest: raise ValueError('Mask request ID reused with different content')
                self.pending['result'] = {**deepcopy(receipt), 'replayed': True}
                return False
            e = self.engine
            reason = e._guard_editable('local masks')
            if reason: raise ValueError(reason)
            owner = e._source_patch_controller().capture
            capture = owner._matching(p, recipe=True)
            if not capture['eligible'] or capture['descriptor']['domain'] != 'source-input':
                raise ValueError('Review an immutable original-source capture before editing masks')
            mutation = p['mutation']
            group_edit = type(mutation) is dict and str(mutation.get('action','')).startswith('layer_')
            group_id = mutation.get('id') if group_edit else None
            if (group_edit and type(group_id) is not str) or capture['descriptor'].get('mask_group_id') != group_id:
                raise ValueError('Captured mask coverage belongs to another group; capture the target group again')
            if group_edit:
                from .local_grade_edit import prepare
                self.pending['layers'] = prepare(e, capture, mutation)
                self.pending['state'], self.pending['scope'] = e._local_masks, e._grade_scope
                owner.invalidate()
                return True
            accepted = type(mutation) is dict and mutation.get('action') == 'accept_prompted'
            if accepted:
                from .prompted_mask_controller import controller
                obj = controller(e, self.emit).accepted_object(mutation, {k: p[k] for k in PROOF_KEYS})
                mutation = {'action': 'upsert', 'object': obj, 'coordinate_space': 'capture'}
            value, scope = prepare_mutation(e, capture, mutation, accepted_prompted=accepted)
            self.pending['state'], self.pending['scope'] = value, scope
            owner.invalidate()
            return True
        except Exception as error:
            result['error'] = error_text(error)
            return False

    def apply(self, p):
        pending = self.pending
        if pending is None or 'state' not in pending: raise ValueError('Mask mutation has no prepared capture proof')
        e = self.engine
        from . import local_grade_layers as L, local_grade_runtime as LR
        previous = (e._local_masks, e._grade_scope, L.check(getattr(e, '_local_grade_layers', None)))
        pipe_before = dict(vars(e._vram))
        result = pending['result']
        try:
            pending['started'] = True
            e._local_masks, e._grade_scope = pending['state'], pending['scope']
            e._local_grade_layers = pending.get('layers', previous[2])
            if 'layers' in pending: LR.sync(e, strict=True)
            if e._grade_scope == 'objects': S.sync(e, strict=True)
            else: e._vram.set_grade_scope(e._grade_scope)
            frame = e._write_current_frame('local_masks')
            frame['doc_state'] = e.doc_state()
            self.emit(frame)
            result.update(success=True, no_change=(previous == (e._local_masks, e._grade_scope, e._local_grade_layers)))
        except Exception as error:
            e._local_masks, e._grade_scope, e._local_grade_layers = previous
            vars(e._vram).clear(); vars(e._vram).update(pipe_before)
            # The stage owns nested tensors; restoring the outer pipeline dict
            # cannot restore an in-place stage.set. Rebuild the old group set.
            e._vram._local_grade_layers_key = None
            try:
                LR.sync(e, strict=True)
                frame = e._write_current_frame('local_masks_rollback')
                frame['doc_state'] = e.doc_state(); self.emit(frame)
            except Exception:
                result.update(outcome_unknown=True, requires_reload=True)
                e._vram = None
            result['error'] = error_text(error)

    def finish(self, p, dispatch_error=None):
        pending, self.pending = self.pending, None
        if pending is None: return
        result = pending['result']
        if dispatch_error:
            result.update(success=False, error=error_text(dispatch_error), outcome_unknown=pending['started'])
        if result['success'] and not result.get('replayed'):
            try:
                state = self.engine.doc_state()
                if state['document_id'] != result['document_id']: raise ValueError('Mask document changed before receipt')
                result['history'] = {k: state['history'][k] for k in ('undo_steps', 'redo_steps')}
            except Exception as error:
                result.update(success=False, outcome_unknown=True, error=error_text(error))
        rid, digest = result.get('request_id'), pending['digest']
        if rid and digest and rid not in self.cache:
            self.cache[rid] = (digest, deepcopy(result))
            while len(self.cache) > 64: self.cache.popitem(last=False)
        self.emit(result)


def controller(engine, emit):
    owner = engine.__dict__.get('_local_mask_owner')
    if owner is None:
        owner = engine._local_mask_owner = MaskController(engine, emit)
    return owner
