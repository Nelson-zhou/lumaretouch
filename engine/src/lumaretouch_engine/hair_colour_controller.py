"""Reachable review/commit controller for source-owned hair assets.

Host dispatches cmd_hair_colour + finish_hair_colour and treats ONLY commits /
clear as ordinary history mutations. Scalar colour/gloss use the existing people
patch command. Receipt IDs are idempotent; a lost acknowledgment is never resent.
"""
from collections import OrderedDict
from copy import deepcopy
import base64
import io
import uuid
import numpy as np
from . import hair_colour_assets as A, hair_colour_analysis as E, hair_colour_project as PROJECT
from . import hair_colour_state as S, people_state as P, people_resolver as R
from . import hair_colour_evidence as SAVED

ACTIONS = ('context', 'preview_support', 'preview_recovery', 'commit_support', 'commit_recovery', 'clear_recovery', 'clear_support')
MUTATIONS = ('commit_support', 'commit_recovery', 'clear_recovery', 'clear_support')


def context(engine, incoming):
    from .people_host_commands import checked
    if type(incoming) is not dict or set(incoming) != {'document_id', 'document_epoch', 'document_revision', 'state_revision', 'association_revision', 'target'}:
        raise ValueError('Hair review needs captured document and people fences')
    state, binding, target = checked(engine, {**incoming, 'request_id': 'hair-context'})
    source = engine._people_source()
    selected = engine._people_cursors.get(source['sha256'])
    if target['scope'] != 'face' or target['target_id'] != selected or target != engine._people_targets.get(source['sha256']):
        raise ValueError('头发选区与恢复笔只属于此照片中选中的单个人物，请先切换到人物独立编辑范围')
    face = A.verify_face(state, target['face_ref'], source)
    if not face['enabled']: raise ValueError('请先启用所选人物')
    from .creative_derived_source import record, verify
    derived = record(engine) is not None
    if derived:
        verify(source,engine)
        rgb(engine) # Prove the displayed pipeline source and measured proxy agree.
    capture = {'people_context': deepcopy(incoming), 'face_ref': P.face_ref(face), 'source': source,
        'graph_fence': engine._people_owner().fence, 'source_path': None if derived else engine._doc_path,
        'source_identity': id(engine._vram.src_f32), 'repair_identity': id(engine._vram.repair_base)}
    return capture, state


def assert_context(engine, expected):
    actual, state = context(engine, expected['people_context'])
    if actual != expected: raise ValueError('照片、人物、分析或配方在预览后改变，请重新审核头发选区')
    return state


def rgb(engine):
    import torch
    tensor = engine._vram.src_f32
    if tensor is None: raise ValueError('Original source-view pixels are unavailable')
    result = np.array(tensor[0].permute(1,2,0).to('cpu', torch.float32).numpy(), dtype=np.float32, order='C', copy=True)
    if result.ndim != 3 or result.shape[2] != 3 or not np.isfinite(result).all(): raise ValueError('Invalid hair source view')
    from .creative_derived_source import record, binding, verify_precompute, analysis_rgb
    if record(engine) is not None:
        owned = binding(engine); pc = getattr(engine,'_precompute',None)
        if pc is None or pc.backend != 'mediapipe': raise ValueError('Derived hair review requires actual composite analysis')
        verify_precompute(engine,pc)
        proxy = analysis_rgb(engine)
        if (engine._people_source() != owned or result.shape != proxy.shape or proxy.dtype != np.uint8
                or not np.allclose(result,proxy.astype(np.float32)/255.,rtol=0,atol=np.finfo(np.float32).eps)):
            raise ValueError('Hair source view differs from the actual derived analysis pixels')
        if engine._vram.repair_base is not None:
            raise ValueError('Derived hair review cannot use an unadapted repair source')
        if binding(engine) != owned: raise ValueError('Hair effective source changed during review capture')
    return result


def derived_record(engine, record):
    """No original-file prompted resolver may enter a derived review/replay."""
    from .creative_derived_source import record as base_record, verify
    if record is None or base_record(engine) is None: return record
    record = A.check(record); verify(record['source'],engine)
    if any(obj['kind']=='prompted' for key in ('support','recovery') for obj in record[key]['objects']):
        raise ValueError('Derived hair supports only reviewed brush/radial vectors; prompted source inference is not adapted')
    return record


def png(source, coverage=None, *, color=(.12, .85, .9)):
    """Bounded display PNG only, never used as a retained/export mask or source."""
    from PIL import Image
    shown = np.clip(source, 0, 1)
    if coverage is not None:
        if coverage.shape != source.shape[:2]: raise ValueError('Hair review overlay does not match source view')
        alpha = np.clip(coverage, 0, 1)[..., None]*.58
        shown = shown*(1-alpha)+np.array(color, dtype=np.float32)*alpha
    image = Image.fromarray(np.rint(shown*255).astype(np.uint8), 'RGB')
    image.thumbnail((1400, 1400), Image.Resampling.LANCZOS)
    stream = io.BytesIO(); image.save(stream, format='PNG'); data = stream.getvalue()
    while len(data) > 3*1024*1024 and min(image.size) > 64:
        image.thumbnail((max(1, int(image.width*.8)), max(1, int(image.height*.8))), Image.Resampling.LANCZOS)
        stream = io.BytesIO(); image.save(stream, format='PNG'); data = stream.getvalue()
    if len(data) > 3*1024*1024: raise ValueError('Hair source preview exceeds transport budget')
    return 'data:image/png;base64,' + base64.b64encode(data).decode()


def selected_record(engine, captured, state):
    return A.resolve(state, PROJECT.store(engine), captured['face_ref'])


def report(engine, captured, state):
    record = selected_record(engine, captured, state)
    from . import people_algorithms as PA
    resolved = R.resolve(state, captured['face_ref']['face_instance_id'], PA.defaults())
    recipe = R.materialize(resolved, S.OPERATION, S.neutral(), S.check)
    prepared = getattr(engine._vram, 'people_prepared', None)
    fact = None if prepared is None else prepared.facts.get(captured['face_ref']['face_instance_id'], {}).get(S.STAGE)
    return {'face_ref': captured['face_ref'], 'source': captured['source'], 'recipe': recipe,
        'support': A.empty_mask() if record is None else record['support'],
        'recovery': A.empty_mask() if record is None else record['recovery'],
        'support_reviewed': record is not None, 'facts': fact,
        'domain': 'source-normalized', 'notice': '需要本人审核完整头发归属，包括长发、遮挡与画面边缘。模型类别覆盖整张照片，单张人脸不代表只有一个人物。'}


def preview(engine, captured, state, action, payload):
    from .hair_colour_runtime import fields
    if type(payload) is not dict or set(payload) != {'mask'}: raise ValueError('Hair preview needs one source vector stack')
    from .creative_derived_source import record as base_record
    if base_record(engine) is not None:
        checked = A.mask(payload['mask'],recovery=action=='preview_recovery')
        if any(obj['kind']=='prompted' for obj in checked['objects']):
            raise ValueError('Derived hair prompted support is not source adapted')
    old = selected_record(engine, captured, state)
    derived_record(engine,old)
    evidence = SAVED.current(engine, captured['source'])
    if action == 'preview_support':
        record = A.reviewed(captured['face_ref'], captured['source'], A.mask(payload['mask']), evidence['model_sha256'],
            evidence_sha=SAVED.identity(evidence), confirmed=True, recovery=None if old is None else old['recovery'])
    else:
        if old is None: raise ValueError('请先审核此人物的头发范围，再使用效果恢复')
        record = A.check({**old, 'recovery': A.mask(payload['mask'], recovery=True)})
    record = derived_record(engine,record)
    source = rgb(engine); hair = E.at_dimensions(evidence, captured['source'], tuple(source.shape[:2]))
    weight, recovery = fields(record, source.shape[:2], hair, source_path=captured['source_path'])
    if np.count_nonzero(weight > .05) < 16: raise ValueError('选区内没有足够可信的头发，请纠正范围')
    shown = weight if action == 'preview_support' else weight*recovery
    token = uuid.uuid4().hex
    review = {'context': captured, 'record': record, 'kind': action.removeprefix('preview_')}
    reviews = engine.__dict__.setdefault('_hair_colour_reviews', OrderedDict())
    reviews[token] = review
    while len(reviews) > 8: reviews.popitem(last=False)
    assert_context(engine, captured)
    return {'preview_id': token, 'kind': review['kind'], 'face_ref': captured['face_ref'],
            'source': captured['source'], 'overlay_png': png(source, shown),
            'support_pixels': int(np.count_nonzero(weight)), 'selected_pixels': int(np.count_nonzero(shown)),
            'notice': '青色仅为源图选区审核。提交后重新渲染实际效果；不是效果成功或原片导出证据。'}


def publish(engine, captured, state, record):
    record = derived_record(engine,record)
    old_assets = PROJECT.store(engine)
    if record is None:
        candidate = A.detach(state, captured['face_ref']); assets = old_assets
    else:
        candidate, assets = A.retain(state, old_assets, record)
    if candidate == state: return None
    assert_context(engine, captured)
    # Temporarily admit new immutable vectors for complete candidate preparation;
    # the existing graph owner publishes, fences, records history and rolls back.
    engine._hair_colour_assets = assets
    try:
        affected = {captured['source']['sha256']}
        engine._people_prepare_graph(candidate, affected)
        assert_context(engine, captured)
        return engine._people_publish_graph(candidate, affected)
    except Exception:
        # Retain append-only bytes if canonical rollback is uncertain. They are
        # inert without a graph pointer, and required if a commit did occur.
        if engine._vram is not None and engine._people_owner().snapshot() == state:
            engine._hair_colour_assets = old_assets
        raise


def execute(engine, request, emit):
    if type(request) is not dict or set(request) != {'cmd', 'request_id', 'action', 'people_context', 'payload'} or request['cmd'] != 'hair_colour':
        raise ValueError('Invalid hair controller request')
    request_id = P.token(request['request_id']); action = request['action']
    if action not in ACTIONS: raise ValueError('Unknown hair action')
    records = engine.__dict__.setdefault('_hair_colour_receipts', OrderedDict())
    digest = A.digest(request)
    if request_id in records:
        if records[request_id]['digest'] != digest: raise ValueError('Hair request ID was reused with different contents')
        return  # finish emits the ORIGINAL correlated receipt.
    records[request_id] = {'digest': digest, 'success': False}
    captured, state = context(engine, request['people_context']); payload = request['payload']; frame = None
    records[request_id].update(before_fence=captured['graph_fence'], mutation=action in MUTATIONS)
    if action == 'context':
        if payload != {}: raise ValueError('Hair context takes no payload')
        result = report(engine, captured, state); result['source_png'] = png(rgb(engine))
    elif action.startswith('preview_'):
        result = preview(engine, captured, state, action, payload)
    elif action.startswith('commit_'):
        if type(payload) is not dict or set(payload) != {'preview_id', 'confirmed'} or payload['confirmed'] is not True:
            raise ValueError('请明确确认已显示的本人物源图选区')
        review = engine.__dict__.get('_hair_colour_reviews', {}).get(P.token(payload['preview_id']))
        if review is None or review['kind'] != action.removeprefix('commit_') or review['context'] != captured:
            raise ValueError('Hair preview was evicted, belongs to another target or has become stale')
        frame = publish(engine, captured, state, review['record'])
        engine._hair_colour_reviews.pop(payload['preview_id'], None)
        result = {'committed': True, 'asset_sha256': A.digest(review['record'])}
    else:
        if payload != {}: raise ValueError('Hair clear takes no payload')
        old = selected_record(engine, captured, state)
        record = None if action == 'clear_support' else (None if old is None else A.check({**old, 'recovery': A.empty_mask()}))
        frame = publish(engine, captured, state, record)
        result = {'committed': True, 'cleared': action.removeprefix('clear_')}
    if frame is not None: emit(frame)
    records[request_id].update(success=True, payload=result, frame_emitted=frame is not None)
    while len(records) > 128: records.popitem(last=False)


def finish(engine, request, error, emit):
    request_id = request.get('request_id')
    if type(request_id) is not str: return
    records = engine.__dict__.setdefault('_hair_colour_receipts', OrderedDict()); old = records.get(request_id, {})
    digest = A.digest(request)
    if old.get('digest') not in (None, digest):
        emit({'event': 'hair_colour_result', 'protocol': 1, 'request_id': request_id, 'action': request.get('action'),
            'success': False, 'outcome_unknown': False, 'error': 'Hair request ID was reused with different contents',
            'document_id': request.get('people_context', {}).get('document_id')}); return
    if 'result' in old: emit(old['result']); return
    changed_after_failure = bool(error and old.get('mutation') and old.get('before_fence') != engine._people_owner().fence)
    result = {'event': 'hair_colour_result', 'protocol': 1, 'request_id': request_id, 'action': request.get('action'),
        'document_id': request.get('people_context', {}).get('document_id'), 'success': bool(old.get('success')) and not error,
        'outcome_unknown': engine._vram is None or changed_after_failure, 'error': error, 'payload': old.get('payload'),
        'frame_emitted': old.get('frame_emitted', False)}
    if old.get('refusal'): result['refusal'] = old['refusal']
    if engine._vram is not None:
        try: result['doc_state'] = engine.doc_state()
        except Exception as state_error:
            result.update(success=False,outcome_unknown=True,error=f'{error or "Hair result state unavailable"}; {type(state_error).__name__}: {state_error}')
    records[request_id] = {'digest': digest, 'result': result}
    while len(records) > 128: records.popitem(last=False)
    emit(result)


class HairColourHostMixin:
    def cmd_hair_colour(self, request):
        from .server import emit
        try:
            return execute(self, request, emit)
        except Exception as error:
            from .hair_colour_runtime import HairColourRefused
            if isinstance(error, HairColourRefused):
                record = self.__dict__.get('_hair_colour_receipts', {}).get(request.get('request_id'))
                if record is not None:
                    record['refusal'] = {'reason': error.reason, 'face_ref': error.face_ref, 'facts': error.facts}
            raise

    def finish_hair_colour(self, request, error):
        from .server import emit
        return finish(self, request, error, emit)
