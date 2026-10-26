"""User-named immutable checkpoints in the canonical project version/asset table.

Recall is a new edit of the existing working recipe, never a virtual copy or a
rewind of its system revision. The named row never becomes the writable active
version. No second history, asset store or receipt owner is introduced here.
"""
from copy import deepcopy
import uuid
import json
from . import project as PJ

ACTIONS = ('named_state', 'named_create', 'named_rename', 'named_select')
TAG = 'named_recipe_snapshot'
MAX_VERSIONS = 128


def name(value):
    if (type(value) is not str or not value.strip() or value != value.strip()
            or len(value.encode('utf-8')) > 160 or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError('版本名须为非空、无控制字符、首尾无空格且不超过 160 字节的文字')
    return value


def token(value):
    if type(value) is not str or not 1 <= len(value.encode('utf-8')) <= 128 or '\0' in value:
        raise ValueError('命名版本身份无效')
    return value


def _row(engine):
    if engine._project is None:
        raise ValueError('请先创建或打开工程，再保存命名版本')
    if not engine._image_loaded or not 0 <= engine._doc_index < len(engine._docs):
        raise ValueError('请先载入照片')
    return engine._docs[engine._doc_index]


def _stored(engine):
    row = _row(engine)
    return PJ.find_doc(engine._project, document_id=row['document_id'])


def _versions(engine):
    stored = _stored(engine)
    versions = [] if stored is None else stored['versions']
    result = [v for v in versions if TAG in v]
    if len(result) > MAX_VERSIONS or len({v.get('id') for v in result}) != len(result):
        raise ValueError('命名版本数量或身份无效')
    for v in result:
        token(v.get('id')); name(v.get('name'))
        if type(v[TAG]) is not dict or set(v[TAG]) != {'version', 'document_id', 'source_asset_id', 'frame'} or type(v[TAG]['version']) is not int or v[TAG]['version'] != 1:
            raise ValueError('命名版本快照格式无效')
        row = _row(engine)
        if any(v[TAG][key] != row[key] for key in ('document_id', 'source_asset_id')):
            raise ValueError('命名版本属于另一文档或源资产')
        if v['id'] == row.get('_project_version_id', row['recipe_version_id']):
            raise ValueError('命名快照不能作为可覆盖的工作版本；请重新打开已确认工程')
    return result


def _metadata(versions):
    rows = [{'id': v['id'], 'name': v['name']} for v in versions]
    # Raw native receipts have an existing 32 KiB ceiling. Account for escaping,
    # not character counts, and reserve room for exact request/reached proofs.
    if len(json.dumps(rows, ensure_ascii=True, separators=(',', ':')).encode('utf-8')) > 24000:
        raise ValueError('命名版本目录超过回执字节预算；没有修改或删除版本')
    return rows


def catalog(engine):
    from .history_navigation import exact
    versions = _versions(engine)
    # Bind the complete encoded snapshot and asset evidence, not just its label.
    return {'catalog_digest': exact((versions, engine._project.get('assets', {}))),
            'versions': _metadata(versions)}


def validate_request(request):
    from .history_navigation import validate_view
    action = request.get('action')
    if action == 'named_state':
        if set(request) != {'cmd', 'action', 'request_id'}: raise ValueError('命名版本读取字段无效')
        return None
    fields = {'cmd', 'action', 'request_id', 'view', 'catalog_digest'}
    if action in ('named_create', 'named_rename'): fields.add('name'); name(request.get('name'))
    if action in ('named_rename', 'named_select'): fields.add('version_id'); token(request.get('version_id'))
    if action not in ACTIONS or set(request) != fields: raise ValueError('命名版本请求字段无效')
    validate_view(request['view'])
    digest = request.get('catalog_digest')
    if type(digest) is not str or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('命名版本目录摘要无效')
    if int(request['view']['revision']) >= 2**64 - 1: raise ValueError('文档版本耗尽；请保存并重新打开')
    return ('named', 1)


def _stage_create(engine, request, current):
    row = _row(engine)
    if len(_versions(engine)) >= MAX_VERSIONS: raise ValueError('命名版本已达 128 个；没有删除任何版本')
    staged = deepcopy(engine._project)
    old = PJ.find_doc(staged, document_id=row['document_id'])
    active = row.get('_project_version_id', row['recipe_version_id'])
    if old is not None and old.get('active_version') != active:
        raise ValueError('工程工作版本与当前文档不一致')
    recipe = engine._capture_state()
    # Derived precompute is not history-owned. Exact accepted user assets remain.
    recipe = {**recipe, '_precompute': None}
    ident = {k: row[k] for k in ('document_id', 'source_asset_id', 'root_document_id', 'copy_number', 'recipe_version_id')}
    fp = row.get('fingerprint')
    if not fp or fp.get('hash_level') != 'full': raise ValueError('源文件尚无已确认完整指纹；请先保存工程')
    if old is None:
        PJ.add_doc(staged, row['path'], recipe, fp=fp, version_id=active, version_name='live',
                   budget=row.get('budget'), tags=row.get('tags'), trashed=bool(row.get('trashed')), **ident)
    vid = str(uuid.uuid4())
    saved = PJ.add_doc(staged, row['path'], recipe, fp=fp, version_id=vid, version_name=request['name'],
                       budget=row.get('budget'), tags=row.get('tags'), trashed=bool(row.get('trashed')), **ident)
    version = next(v for v in saved['versions'] if v['id'] == vid)
    dropped = []
    frame = PJ.encode(current, staged['assets'], dropped, 'named_recipe_snapshot.' + vid)
    if dropped or staged.get('dropped') != engine._project.get('dropped'):
        raise ValueError('命名版本无法无损保存；未创建')
    version[TAG] = {'version': 1, 'document_id': row['document_id'], 'source_asset_id': row['source_asset_id'], 'frame': frame}
    _metadata([v for v in saved['versions'] if TAG in v])
    PJ.put_active_version(staged, None, active, document_id=row['document_id'])
    return staged  # Current support banks are refreshed under the mutation fence.


def _prepare_select(engine, selected, current):
    from .history_navigation import exact
    row = _row(engine)
    staged = deepcopy(engine._project)
    PJ.put_active_version(staged, None, selected['id'], document_id=row['document_id'])
    from .vram import RepairOp, LightOp
    dc = {'RepairOp': RepairOp, 'LightOp': LightOp}
    recipe, dropped = PJ.active_recipe(staged, document_id=row['document_id'], dc_types=dc)
    frame = PJ.decode(selected[TAG]['frame'], staged['assets'], dropped, 'named_recipe_snapshot', dc_types=dc)
    if dropped or type(recipe) is not dict or type(frame) is not dict:
        raise ValueError('命名版本无法无损读取')
    if set(frame) != set(current): raise ValueError('命名版本字段与当前历史合同不同，未应用')
    expected = {k: v for k, v in recipe.items() if k not in engine.HISTORY_SKIP}
    if exact(expected) != exact({k: v for k, v in frame.items() if k != '_people_history'}):
        raise ValueError('命名版本配方与历史快照不一致')
    if tuple(frame.get('_proxy') or ()) != tuple(current.get('_proxy') or ()):
        raise ValueError('命名版本属于另一代理尺寸；请使用相同代理档重新打开工程')
    # Source switching is a separately reviewed creative transaction. A saved
    # checkpoint is not authority to bypass its immutable-source protections.
    if exact(frame.get('_creative_base')) != exact(current.get('_creative_base')):
        raise ValueError('命名版本的有效来源已变化，不能跨来源覆盖当前工作版本')
    proof = frame.get('_people_history')
    if (proof is None) != (current.get('_people_history') is None):
        raise ValueError('命名版本与当前人像历史范围不同；缺失快照不能授权保留或清空后来的编辑')
    if proof is not None:
        from .virtual_copy_people import scope, PROJECT
        if scope(row) == PROJECT and any(other is not row and scope(other) == PROJECT and other.get('source_asset_id') == row['source_asset_id'] for other in engine._docs):
            raise ValueError('该源还有共享人像文档；命名版本不能绕过多文档历史保护')
        owner = engine._people_owner()
        candidate = owner.stage_document_restore(proof, expected_asset_fence=owner.asset_fences.get(proof['asset_sha256'], 0), expected_association_fence=owner.association_fence)
        from .people_source_context import digest
        if proof.get('source_context_sha256') != digest(candidate, proof['asset_sha256']):
            raise ValueError('命名版本的有效共享人像上下文已变化；不能覆盖其他文档或假称完整恢复')
    # Validate canonical body/source monotonic guards before entering the write.
    engine._body_history_restore(frame)
    return frame


def wire_size(packet):
    # Same encoding as server.emit; native strict raw parser is bounded to 32KiB.
    return len(json.dumps(packet, ensure_ascii=True, separators=(',', ':')).encode('utf-8'))


def check_packet(packet):
    if wire_size(packet) > 32760:
        raise ValueError('命名版本完整回执超过传输预算；未提交')


def bound_error(packet):
    # Exact rejected/unknown envelope, never truncate identity or proof fields.
    while wire_size(packet) > 32760 and packet.get('error'):
        packet['error'] = packet['error'][:len(packet['error']) // 2]
    check_packet(packet)
    return packet


def _admit_applied_packet(request, before, project, row):
    from .history_navigation import packet
    saved = PJ.find_doc(project, document_id=row['document_id'])
    rows = _metadata([] if saved is None else [v for v in saved['versions'] if TAG in v])
    reached = {**before, 'revision': str(int(before['revision']) + 1), 'digest': 'f' * 64,
               'cursor': 64, 'undo_steps': 64, 'redo_steps': 64}
    proposed = packet(request)
    proposed.update(success=True, phase='applied', completed_steps=1, reached=reached,
                    last_confirmed=reached, catalog_digest='f' * 64, versions=rows)
    check_packet(proposed)


def apply(engine, request, result, emit):
    from .history_navigation import checkpoint, mark
    before = checkpoint(engine)
    if before[0] != request['view'] or catalog(engine)['catalog_digest'] != request['catalog_digest']:
        raise ValueError('照片、修订或命名版本目录已变化；请刷新后再操作')
    reason = engine._history_guard(request['action'])
    if reason: raise ValueError(reason)
    action = request['action']
    versions = _versions(engine)
    selected = None if action == 'named_create' else next((v for v in versions if v['id'] == request['version_id']), None)
    if action != 'named_create' and selected is None: raise ValueError('所选命名版本不存在')
    staged = None; frame = None
    if action == 'named_create': staged = _stage_create(engine, request, before[1])
    elif action == 'named_rename':
        staged = deepcopy(engine._project)
        saved = PJ.find_doc(staged, document_id=_row(engine)['document_id'])
        next(v for v in saved['versions'] if v['id'] == selected['id'])['name'] = request['name']
        _metadata([v for v in saved['versions'] if TAG in v])
        PJ.validate(staged)
        PJ._prepare_save(staged)
    else: frame = _prepare_select(engine, selected, before[1])
    _admit_applied_packet(request, before[0], staged if staged is not None else engine._project, _row(engine))
    engine._document_versions().check_advance(_row(engine))
    # Everything after this point may have changed live state. Exceptions are
    # unknown, never a false rollback/no-write claim. The shared owner fences it.
    mark(engine, 'unknown')
    engine._fence_current_document()
    if action == 'named_create':
        # Canonical serialization refreshes ownership bookkeeping as a save does.
        # It is inside the admitted fence: failures remain UNKNOWN, not no-write.
        engine._remember_current()
        engine._people_save(staged)
        PJ.validate(staged)
        PJ._prepare_save(staged)
    if frame is not None:
        rendered = engine._history_restore_frame(frame, 'named_version_select')
        engine._history_controller().record('named_version_select', before[1], coalesce=False)
        engine._remember_current()
        emit({'event': 'history_state', 'action': 'named_select', 'doc_state': engine.doc_state(), **engine._history_report()})
        emit(rendered)
    else:
        engine._project = staged
    engine._project_dirty = True
    after = checkpoint(engine)[0]
    if any(after[k] != before[0][k] for k in ('workspace', 'document_id', 'load_id')) or int(after['revision']) != int(before[0]['revision']) + 1:
        raise RuntimeError('命名版本提交后的文档身份或修订证明不匹配')
    result.update(success=True, phase='applied', completed_steps=1, reached=after, last_confirmed=after, **catalog(engine))
    mark(engine, 'applied')
