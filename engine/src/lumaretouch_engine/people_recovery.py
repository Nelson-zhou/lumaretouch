"""Selected-face recovery editing over the canonical, all-face render bank.

Only the two existing facial recovery producers are admitted. Vectors stay in
source coordinates and immutable storage; the normal people pipeline attenuates
their own operator delta before its one shared geometry map. This module owns
neither a geometry solver nor another history/association store.
"""
from copy import deepcopy

from . import effect_recovery_state as R, facial_wrinkle_recovery as FACE
from . import people_state as S, people_support_assets as SUPPORT


def managed(engine):
    return bool(getattr(engine, '_people_managed', lambda: False)())


def handles(engine, target):
    return managed(engine) and target in FACE.FACE_TARGETS


def global_value(engine, recovery=None):
    """Legacy face rows remain saved, but never feed the all-face render path."""
    result = R.check(getattr(engine, '_effect_recovery', None) if recovery is None else recovery)
    if managed(engine):
        result['targets'] = [row for row in result['targets'] if row['target'] not in FACE.FACE_TARGETS]
        if not result['targets']:
            result['source'] = None
    return R.check(result)


def selection(engine, *, editing=False):
    source = engine._people_source()
    state = engine._people_owner().snapshot()
    key = engine._people_cursors.get(source['sha256'])
    face = state['faces'].get(key)
    if face is None or face['asset_sha256'] != source['sha256']:
        raise ValueError('请先选择此照片中一个确切的人物，再编辑人物局部恢复')
    ref = S.face_ref(face)
    if editing and engine._people_targets.get(source['sha256']) != {
            'scope': 'face', 'target_id': key, 'face_ref': ref}:
        raise ValueError('人物恢复只属于选中的单个人脸，不能写入人物、分组或全部人物继承范围')
    evidence = face['evidence']
    if (evidence['status'] != 'verified' or evidence['backend'] != 'mediapipe'
            or (source['width'], source['height'])
            != (evidence['source_width'], evidence['source_height'])):
        raise ValueError('人物恢复缺少与当前源照片一致的真实分析证据')
    return source, state, face, ref


def value(engine):
    """Editing view only: global operators plus this selected face's rows."""
    legacy = R.check(getattr(engine, '_effect_recovery', None))
    if not managed(engine):
        return legacy
    rows = [row for row in legacy['targets'] if row['target'] not in FACE.FACE_TARGETS]
    source = engine._people_source()
    if rows and legacy['source'] != source:
        raise ValueError('整图恢复笔迹不属于当前源照片')
    state = engine._people_owner().snapshot()
    selected = engine._people_cursors.get(source['sha256'])
    face = state['faces'].get(selected)
    if face is not None:
        if face['asset_sha256'] != source['sha256']:
            raise ValueError('人物恢复选择属于另一张源照片')
        for target in sorted(FACE.FACE_TARGETS):
            record = SUPPORT.resolve(state, engine._people_support, S.face_ref(face), target)
            if record is not None:
                if record['source'] != source:
                    raise ValueError('人物恢复源照片身份或尺寸发生变化')
                rows.extend(record['targets'])
    return R.check({'version': R.VERSION, 'source': source if rows else None, 'targets': rows})


def context(engine):
    source, state, face, ref = selection(engine, editing=True)
    from .creative_derived_source import record
    if record(engine) is not None:
        from .creative_derived_recovery import source_binding
        if source_binding(engine)!=source:raise ValueError('Recovery analysis belongs to another composite')
    # No detector index or person/group association can substitute for these
    # actual bytes. Selecting another face must invalidate a reviewed gesture.
    actual = FACE.owner(source, engine._precompute)
    if (actual['landmarks_sha256'] != face['evidence']['landmark_digest']
            or actual['backend'] != face['evidence']['backend']):
        raise ValueError('当前选中人物与保留的关键点证据不一致')
    return {'face_ref': ref, 'graph_fence': engine._people_owner().fence,
            'source': source, 'evidence': deepcopy(face['evidence'])}


def assert_context(engine, expected):
    if context(engine) != expected:
        raise ValueError('人物、源照片、分析或人物配方在恢复预览后改变，请重新查看本笔')


def prepare(engine, recovery, target, *, expected=None):
    """Prepare a real all-face candidate without publishing its state or bytes."""
    if not handles(engine, target):
        return None
    engine._people_sync(strict=True)
    captured = context(engine)
    if expected is not None and captured != expected:
        raise ValueError('人物恢复预览的确切归属已过期')
    current = value(engine)
    recovery = R.check(recovery)
    # This reviewed gesture can change one family only, never an unrelated
    # operator, another face, or the original retained legacy record.
    other = lambda state: [row for row in state['targets'] if row['target'] != target]
    if other(current) != other(recovery):
        raise ValueError('人物恢复预览包含未审核的其他功能族修改')
    before = engine._people_owner().snapshot()
    assets = deepcopy(engine._people_support)
    row = next((row for row in recovery['targets'] if row['target'] == target), None)
    if row is None:
        candidate = SUPPORT.detach(before, captured['face_ref'], target)
    else:
        if recovery['source'] != captured['source']:
            raise ValueError('人物恢复不能重新绑定源照片')
        candidate, assets = SUPPORT.retain(before, assets, captured['face_ref'], captured['source'], row)
    SUPPORT.check_store(assets)
    from .cpu_memory_budget import available_estimate
    from .people_engine_runtime import prepare_preview
    pipe = engine._vram
    asset = captured['source']['sha256']
    fields = SUPPORT.raster(candidate, assets, asset, (pipe.h, pipe.w))
    from .people_owned_inputs import preview as owned_inputs
    prepared = prepare_preview(pipe, candidate, asset, engine._people_analyses.get(asset, {}),
                               byte_budget=available_estimate(), recovery_assets=fields,**owned_inputs(engine,candidate,support_bank=assets))
    assert_context(engine, captured)
    return {'context': captured, 'before': before, 'candidate': candidate,
            'assets': assets, 'prepared': prepared, 'target': target,
            'no_change': candidate == before}


def availability(engine):
    reason = getattr(engine._vram, 'people_suspended', None)
    try:
        _, _, face, ref = selection(engine, editing=True)
        if not face['enabled']:
            raise ValueError('请先启用选中的人物，再绘制人物恢复笔迹')
        context(engine)
    except ValueError as error:
        reason = str(error)
        ref = None
    prepared = getattr(engine._vram, 'people_prepared', None)
    result = {}
    for target in FACE.FACE_TARGETS:
        active = bool(not reason and ref is not None and prepared is not None and any(
            record.face_ref == ref and record.stage == target and record.delta is not None
            and bool(record.delta.any()) for record in prepared.effects))
        result[target] = {'active': active, 'reason': reason or (None if active else
            '请先启用选中人物的此功能族；恢复笔不会擦除其他人物或其他效果')}
    return result


def commit(engine, transaction, *, verified_source_key, recovery):
    """Use the host's canonical publication and the dispatcher's one history step."""
    from .effect_recovery_runtime import stage_key
    assert_context(engine, transaction['context'])
    if stage_key(engine, recovery) != verified_source_key:
        raise ValueError('人物恢复提交前源图改变')
    if transaction['no_change']:
        frame = engine._write_current_frame('effect_recovery_unchanged')
        if stage_key(engine, recovery) != verified_source_key:
            raise ValueError('人物恢复渲染期间源图改变')
        return frame
    owner = engine._people_owner()
    old_assets = engine._people_support
    candidate_assets = transaction['assets']
    if any(candidate_assets.get(key) != record for key, record in old_assets.items()):
        raise ValueError('人物恢复不能删除或覆盖撤销历史仍引用的原始向量')
    try:
        engine._people_support = candidate_assets
        frame = engine._people_publish_graph(transaction['candidate'],
                                             {transaction['context']['source']['sha256']})
        if stage_key(engine, recovery) != verified_source_key:
            raise ValueError('人物恢复渲染期间源图改变，撤回本笔')
        return frame
    except Exception:
        # The host normally already rolled back. A post-render source check may
        # fail later, so also cover that path without rewinding monotonic fences.
        try:
            before = deepcopy(transaction['before'])
            before['association_revision'] = owner.association_fence
            current = owner.snapshot()
            if any(current[key] != before[key] for key in before if key != 'revision'):
                owner.commit(before, expected_fence=owner.fence)
            engine._people_support = old_assets
            engine._people_analysis_key = None
            engine._people_sync(strict=True)
        except Exception:
            # If canonical rollback itself failed, keep all candidate bytes.
            # Do not render a partial state or claim that the gesture reverted.
            engine._vram = None
        raise
