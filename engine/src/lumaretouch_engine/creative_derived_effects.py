"""Narrow source-only portrait admission for an immutable creative baseline.

This is an operation/parameter contract, not a blanket tool-name exemption.
The existing people owner still validates revisions, stages every requested
face and publishes through the existing history/receipt transaction. Path-based
Body/general selection remain fenced. Reviewed makeup, manual hair support and
face-owned recovery admit only their exact source/evidence/owner contracts.
"""
import math
from . import creative_derived_makeup as MAKEUP
from . import creative_derived_hair as HAIR

OPERATIONS = frozenset((
    'lnx.deform.v1', 'lnx.enhance.v1', 'lnx.facial_wrinkles.v1', 'lnx.skin_colour.v1', 'lnx.skin_finish.v1',
    'lnx.skin_gloss.v1', 'lnx.eye_bags.v2',
    'lnx.body_face_match.v1', 'lnx.body_skin_evenness.v1', 'lnx.collarbone.v1', 'lnx.skin_evenness.v1', 'lnx.skin_texture.v1', 'lnx.face_contour.v1', 'lnx.slim_face.v2', 'lnx.face_size.v1', 'lnx.lower_face.v1', 'lnx.mid_face.v1', 'lnx.chin_shape.v1', 'lnx.chin_length.v1', 'lnx.philtrum.v1', 'lnx.eye_symmetry.v1', 'lnx.brow_enhance.v1', 'lnx.lip_texture.v1',
    'lnx.brow_shape.v1', 'lnx.nose_shape.v1', 'lnx.eye_shape.v1',
    'lnx.mouth_shape.v1', 'lnx.lip_makeup.v1', 'lnx.eye_light.v1',
)) | MAKEUP.OPERATIONS | {HAIR.OPERATION}
LEGACY = {name: 'lnx.' + name + '.v1' for name in (
    'deform', 'enhance', 'brow_shape', 'nose_shape', 'eye_shape', 'mouth_shape', 'lip_makeup')}
_CONTEXT = {'document_id','document_epoch','document_revision','state_revision','association_revision','target'}
_ENVELOPE = _CONTEXT | {'cmd','request_id','action','payload'}


def source(value):
    from .people_state import digest
    if type(value) is not dict or set(value) != {'sha256','width','height'}:
        raise ValueError('Derived portrait source needs its exact immutable binding')
    digest(value['sha256'])
    if any(type(value[key]) is not int or value[key] < 1 for key in ('width','height')):
        raise ValueError('Invalid derived portrait extent')
    return dict(value)


def _target(value):
    from . import people_state as S
    if type(value) is not dict or set(value) != {'scope','target_id','face_ref'}:
        raise ValueError('Derived portrait changes require an explicit local target')
    if value['scope'] == 'face':
        ref = S.check_ref(value['face_ref'])
        if ref['face_instance_id'] != value['target_id']:
            raise ValueError('Derived portrait face target mismatch')
    elif value['scope'] == 'all_people':
        S.digest(value['target_id'])
        if value['face_ref'] is not None: raise ValueError('Invalid photograph-wide portrait target')
    else:
        raise ValueError('Derived portrait editing does not admit shared person/group targets')
    return value


def _context(value):
    from . import people_state as S
    if type(value) is not dict or set(value) != _CONTEXT:
        raise ValueError('Derived portrait gesture needs captured document and graph revisions')
    for key in ('document_id','document_epoch'): S.token(value[key])
    for key in ('document_revision','state_revision','association_revision'): S.revision(value[key])
    _target(value['target'])
    return value


def _leaf(operation, path, value):
    from . import people_algorithms as A
    from .people_resolver import materialize
    if operation not in OPERATIONS: raise ValueError('Portrait operation is not derived-source adapted')
    neutral, validator = A.specifications()[operation]
    known = A.leaves(neutral)
    if path not in known: raise ValueError('Unknown derived portrait parameter')
    # A scalar is range-checked independently; linked equality belongs to the
    # complete staged recipe in people_edit, including inherited target intent.
    # Do not reject the first half of an atomic equal-sided edit on neutral.
    if operation in (A.CHIN_SHAPE.OP, A.BROW_ENHANCE.OP):
        neutral = {**neutral, 'linked': False}
    if operation in MAKEUP.OPERATIONS:
        MAKEUP.check_leaf(operation,path,value,neutral,validator)
        return
    if operation == HAIR.OPERATION:
        materialize({'conflicts':[], 'operations':{operation:{path:{'value':value}}}},operation,neutral,validator)
        return
    if operation == A.EYE_SYMMETRY.OP and path == '/reference':
        # Only this operation's exact reference enum is nonnumeric intent.
        # Its validator rejects arbitrary strings and source-owned evidence.
        materialize({'conflicts':[], 'operations':{operation:{path:{'value':value}}}}, operation, neutral, validator)
        return
    if type(known[path]) is bool:
        if type(value) is not bool: raise ValueError('Portrait link flag must be boolean')
    elif type(value) not in (int,float) or not math.isfinite(value):
        raise ValueError('Portrait amount must be a finite numeric scalar')
    materialize({'conflicts':[], 'operations':{operation:{path:{'value':value}}}}, operation, neutral, validator)


def _patches(payload):
    from . import people_algorithms as A
    if type(payload) is not dict or set(payload) != {'patches'} or type(payload['patches']) is not list or not 1 <= len(payload['patches']) <= 256:
        raise ValueError('Derived portrait patch list must be bounded and explicit')
    seen = set()
    for patch in payload['patches']:
        if type(patch) is not dict or type(patch.get('unset')) is not bool:
            raise ValueError('Portrait patch needs explicit unset semantics')
        fields = {'operation_id','parameter_path','unset'} | (set() if patch['unset'] else {'value'})
        if set(patch) != fields: raise ValueError('Unexpected portrait patch fields')
        op,path = patch['operation_id'],patch['parameter_path']
        if type(op) is not str or type(path) is not str or (op,path) in seen:
            raise ValueError('Invalid or duplicate portrait patch')
        seen.add((op,path))
        if op not in OPERATIONS or path not in A.defaults()[op]:
            raise ValueError('Portrait parameter has no derived-source consumer')
        if not patch['unset']: _leaf(op,path,patch['value'])


def _request(name, request):
    from . import people_state as S, people_algorithms as A
    if type(request) is not dict or request.get('cmd') != name:
        raise ValueError('Invalid derived portrait command')
    if name == 'hair_colour':
        HAIR.request(request)
        context = _context(request['people_context'])
        if context['target']['scope'] != 'face':raise ValueError('Hair review requires an exact local face')
        return context
    if name == 'people':
        if set(request) != _ENVELOPE: raise ValueError('Unexpected people command fields')
        context = _context({key:request[key] for key in _CONTEXT})
        S.token(request['request_id'])
        action,payload,target = request['action'],request['payload'],context['target']
        if action in ('face_style_catalog','face_style_preview','face_style_image','face_style_confirm'):
            from .face_style_review import check_action
            check_action(action,payload,target)
        elif action in ('eye_bag_reference','eye_bag_preview','eye_bag_image','eye_bag_confirm'):
            from .eye_bag_preserve_host import check_action
            check_action(action,payload,target)
        elif action == 'patch': _patches(payload)
        elif action in ('body_face_match_reference','body_face_match_preview','body_face_match_confirm','body_face_match_detach'):
            from .skin_colour_body_actions import check_action
            check_action(action,payload,target,family='body_face_match',operation_id='lnx.body_face_match.v1')
        elif action in ('collarbone_reference','collarbone_preview','collarbone_confirm','collarbone_detach'):
            from .skin_colour_body_actions import check_action
            check_action(action,payload,target,family='collarbone',operation_id='lnx.collarbone.v1')
        elif action in ('body_skin_evenness_reference','body_skin_evenness_preview','body_skin_evenness_confirm','body_skin_evenness_detach'):
            from .skin_colour_body_actions import check_action
            check_action(action,payload,target,family='body_skin_evenness',operation_id='lnx.body_skin_evenness.v1')
        elif action in ('skin_finish_body_reference','skin_finish_body_preview','skin_finish_body_confirm','skin_finish_body_detach'):
            from .skin_colour_body_actions import check_action
            check_action(action,payload,target,family='skin_finish')
        elif action in ('skin_body_reference','skin_body_preview','skin_body_confirm','skin_body_detach'):
            from .skin_colour_body_actions import check_action
            check_action(action,payload,target)
        elif action in MAKEUP.ACTIONS:
            MAKEUP.check_action(action,payload,target)
        elif action in ('select','target','analyse_face'):
            if payload != {} or type(payload) is not dict or (action != 'target' and target['scope'] != 'face'):
                raise ValueError('Invalid local portrait cursor/analysis request')
        elif action == 'manual_add':
            if type(payload) is not dict or set(payload) != {'box'}: raise ValueError('Manual portrait addition accepts one source region')
            box = payload['box']
            if type(box) not in (list,tuple) or len(box) != 4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in box) or not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1):
                raise ValueError('Manual portrait region must be finite normalized bounds')
        elif action == 'face_status':
            if target['scope'] != 'face' or type(payload) is not dict or not payload or set(payload)-{'enabled','labels'}:
                raise ValueError('Face status requires its exact current face')
            if 'enabled' in payload and type(payload['enabled']) is not bool: raise ValueError('Invalid face enabled flag')
            if 'labels' in payload:
                labels = payload['labels']
                if type(labels) is not dict or len(labels) > 32: raise ValueError('Invalid editable face labels')
                for key,value in labels.items(): S.token(key); S.scalar(value)
        else: raise ValueError('This people action is not derived-source adapted')
        return context
    if name not in LEGACY: raise ValueError('This command has no derived portrait adapter')
    context = _context(request.get('people_context'))
    operation = LEGACY[name]
    if name == 'deform':
        if set(request)-{'cmd','action','amounts','scope','people_context'} or request.get('action','set') not in ('set','clear','inherit'):
            raise ValueError('Invalid derived deform gesture')
        if request.get('scope','all') not in ('all','person'): raise ValueError('Invalid legacy deform scope')
        given = request.get('amounts',{})
        if type(given) is not dict or (request.get('action','set') == 'set' and not given): raise ValueError('Missing deform amounts')
        for key,value in given.items(): _leaf(operation,'/'+key,value)
    elif name == 'enhance':
        from .ops.enhance import AMOUNT_KEYS
        from .facial_wrinkle_state import INTENT_KEYS
        if set(request)-{'cmd','action','people_context',*AMOUNT_KEYS} or request.get('action','set') not in ('set','clear'):
            raise ValueError('Invalid derived enhance gesture')
        given = {key:request[key] for key in AMOUNT_KEYS if key in request}
        if request.get('action','set') == 'set' and not given: raise ValueError('Missing enhance amounts')
        for key,value in given.items(): _leaf('lnx.facial_wrinkles.v1' if key in INTENT_KEYS else operation,'/'+key,value)
    else:
        expected = {'cmd','recipe','document_id','control','people_context'}
        if name != 'lip_makeup': expected |= {'base','request_id','gesture_id','face_id'}
        if set(request) != expected: raise ValueError('Invalid derived portrait recipe gesture')
        neutral,validator = A.specifications()[operation]
        if request['recipe'] is None: raise ValueError('Missing complete portrait recipe')
        validator(request['recipe'])
        if request['control'] not in (set(neutral)-{'version'}) | {'all'}: raise ValueError('Unknown portrait control')
        S.token(request['document_id'])
        if name != 'lip_makeup':
            if request['base'] is None: raise ValueError('Missing confirmed portrait recipe base')
            validator(request['base'])
            for key in ('request_id','gesture_id','face_id'): S.token(request[key])
    return context


def is_local_command(name, request):
    """Structural predicate only. Consumers still enforce live source/fences."""
    try:
        _request(name,request)
        return True
    except (ValueError,TypeError,KeyError):
        return False


def require_command(engine, name, request):
    """Called before dispatcher mutation; never initializes analysis or a graph."""
    from .creative_derived_source import record, binding, verify_precompute
    from .people_command import validate_envelope
    context = _request(name,request)
    if record(engine) is None: return
    owned = binding(engine)
    if name == 'people' and request['action'] in ('face_style_catalog','face_style_preview','face_style_image','face_style_confirm'):
        from .people_preset_plan import require_active_owner
        state = require_active_owner(engine).snapshot()
    else:
        state = engine._people_owner().snapshot()
    current = engine._people_binding()
    target = validate_envelope({**context,'request_id':request.get('request_id','derived-legacy')},state,
        **{key:current[key] for key in ('document_id','document_epoch','document_revision')})
    if (target['scope'] == 'face' and target['face_ref']['asset_sha256'] != owned['sha256']) or (target['scope'] == 'all_people' and target['target_id'] != owned['sha256']):
        raise ValueError('Portrait target belongs to another effective pixel source')
    if name != 'people' and target != engine._people_targets.get(owned['sha256']):
        raise ValueError('Portrait editing scope changed after this gesture')
    if name in LEGACY and name not in ('deform','enhance') and request['document_id'] != engine._load_id:
        raise ValueError('Portrait document view changed')
    if name == 'people' and request['action'] in ('select','target','analyse_face','manual_add','face_status'):
        return # These can repair a suspended/unanalysed face without original pixels.
    if not engine._people_managed() or engine._precompute is None or engine._precompute.backend != 'mediapipe':
        raise ValueError('Reanalyse this composite with the actual portrait backend before editing')
    verify_precompute(engine,engine._precompute)
    require_graph(state,owned,document_id=current['document_id'])


def require_graph(state, binding, *, document_id=None):
    """Also used by replay/export: persisted recipes cannot bypass admission."""
    from . import people_state as S, people_algorithms as A
    from .people_resolver import resolve
    from .creative_derived_recovery import TARGETS
    owned = source(binding); state = S.check(state); asset = owned['sha256']
    from .people_cross_owner import validate_owner
    accepted = validate_owner(state,asset,document_id)
    faces = {key:face for key,face in state['faces'].items() if face['asset_sha256'] == asset}
    if any(link['face_instance_id'] in faces and link['person_id'] not in accepted for link in state['links']) or any(set(group['face_ids']) & set(faces) for group in state['groups'].values()):
        raise ValueError('Derived portrait graph cannot inherit shared person/group inputs')
    for key,face in faces.items():
        for kind,descriptor in face['local_assets'].items():
            if kind not in MAKEUP.SUPPORT_KINDS | {'hair_colour','skin_colour_body_visibility','skin_finish_body_visibility','body_skin_evenness_visibility','body_face_match_visibility','collarbone_visibility','eye_bag_ridge_visibility'} | set(TARGETS) or descriptor['kind'] != kind or descriptor['owner'] != S.face_ref(face):
                raise ValueError('Derived portrait graph cannot replay unadapted support/recovery assets')
        evidence = face['evidence']
        if (evidence['source_width'],evidence['source_height']) != (owned['width'],owned['height']):
            raise ValueError('Derived portrait evidence has another source extent')
        values = A.recipes(resolve(state,key,A.defaults()))
        if any(value != A.specifications()[operation][0] for operation,value in values.items() if operation not in OPERATIONS):
            raise ValueError('Derived portrait graph contains an unadapted operation')
    for row in state['overrides']:
        if (row['scope'] == 'face' and row['target_id'] in faces) or (row['scope'] == 'all_people' and row['target_id'] == asset) or (row['scope'] == 'person' and row['target_id'] in accepted):
            _leaf(row['operation_id'],row['parameter_path'],row['value'])
    return state
