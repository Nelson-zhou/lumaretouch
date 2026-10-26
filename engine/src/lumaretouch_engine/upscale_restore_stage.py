# SPDX-License-Identifier: GPL-3.0-or-later
"""Full-frame single-tile neural restoration → canonical review, AUTHORED / UNRUN.

This stage reuses the existing complete current-edited source and immutable
new-photo asset contracts. Display PNGs are review only, never inference input.
Neither sharpen nor identity/fallback is accepted as a model result.
"""
from dataclasses import dataclass, field
import hashlib
import json
import uuid
from . import lens_blur_stage as shared
from . import light_glow_source as sources
from .upscale_v2 import adapter
from .upscale_v2.source import CanonicalSource, validate_source

OPERATION = 'lnx.upscale_restore.v1'
PROTOCOL = 1
MODEL = 'Swin2SR-classical-sr-x2-64'
Budget = shared.Budget
_SEAL = object()
MAX_SIDE = 1024
MAX_PIXELS = 1_048_576


def capability():
    value = adapter.capability(MODEL)
    return {'version': PROTOCOL, 'operation_id': OPERATION, 'model_id': MODEL,
            'status': 'available' if value.available else 'unavailable',
            'reason': '; '.join(value.blockers), 'acceptance': 'unrun',
            'output_mode': 'restore_native_dimensions'}


def recipe(value):
    if (type(value) is not dict or set(value) != {'version', 'model_id'}
            or type(value['version']) is not int or value['version'] != 1
            or value['model_id'] != MODEL):
        raise ValueError('AI restoration supports only the pinned native-dimension classical SR x2 profile')
    return dict(value)


def admit_source(source, budget):
    sources.require(source)
    owner = source.owner['source']
    pixels = owner['width'] * owner['height']
    if not 16 <= owner['width'] <= MAX_SIDE or not 16 <= owner['height'] <= MAX_SIDE or pixels > MAX_PIXELS:
        raise ValueError('首个 AI 超清档仅支持宽、高各 16–1024 像素（最多 1,048,576 像素）的完整单帧；更大照片不可用，不会降采样或分块替代')
    # Retained source + immutable result/asset validation/display staging. The
    # adapter independently enforces isolated worker CPU/address-space limits;
    # this bookkeeping is not a measured combined machine memory guarantee.
    shared._admit(source.retained_bytes + pixels * 64 + shared.DISPLAY_RESERVE
                  + 32 * 1024 * 1024, budget)


def context(source, session_id, cap):
    sources.require(source)
    if not shared._token(session_id):
        raise ValueError('Restoration context requires an issued source session')
    return {'version': PROTOCOL, 'operation_id': OPERATION, 'session_id': session_id,
            'owner': source.owner, 'source_evidence': source.evidence,
            'before': source.pixels.source_image, 'capability': cap,
            'message': 'Swin2SR 经典超分完整单帧神经处理后回到原尺寸，不是 2 倍尺寸导出。非盲复原、非人脸重建；AI 可能改变纹理或生成细节；须审阅前后图，仅另存新图，原图和原历史不改。仅宽、高各 16–1024 像素完整单帧；实机画质及性能验收未运行。'}


def _preview(command, source):
    if (not shared._exact(command, ('version', 'operation_id', 'action', 'request_id', 'session_id', 'owner', 'recipe'))
            or type(command['version']) is not int or command['version'] != PROTOCOL
            or command['operation_id'] != OPERATION or command['action'] != 'preview'
            or not shared._token(command['request_id']) or not shared._token(command['session_id'])
            or command['owner'] != source.owner):
        raise ValueError('Restoration preview needs its exact retained source and session')
    recipe(command['recipe'])
    return json.loads(shared._json(command))


def write_command(command):
    base = {'version', 'operation_id', 'action', 'request_id', 'session_id', 'owner', 'token'}
    if (type(command) is not dict or type(command.get('version')) is not int or command['version'] != PROTOCOL
            or command.get('operation_id') != OPERATION
            or not shared._token(command.get('request_id')) or not shared._token(command.get('session_id'))):
        raise ValueError('Restoration writes need exact versioned request/session identities')
    shared._owner(command.get('owner'))
    if command.get('action') == 'apply':
        hashes = {'recipe_sha256', 'result_source_sha256', 'before_sha256', 'after_sha256'}
        if (set(command) != base | hashes | {'reviewed', 'return_mode'}
                or not shared._token(command['token']) or command['reviewed'] is not True
                or command['return_mode'] != 'new_image' or any(not shared._sha(command[k]) for k in hashes)):
            raise ValueError('Restoration apply needs exact before/after review and explicit new-image return')
    elif command.get('action') == 'cancel':
        if set(command) != base or command['token'] is not None and not shared._token(command['token']):
            raise ValueError('Malformed restoration cancellation')
    else:
        raise ValueError('Unsupported restoration write action')
    raw = shared._json(command)
    if len(raw) > 16 * 1024:
        raise ValueError('Restoration write exceeds bounded identity budget')
    return json.loads(raw)


@dataclass(frozen=True, slots=True)
class Candidate:
    review_json: bytes
    asset_header: bytes
    content: bytes = field(repr=False)
    original: bytes = field(repr=False)
    icc: bytes = field(repr=False)
    no_change: bool
    _seal: object = field(repr=False, compare=False)

    @property
    def review(self):
        return json.loads(self.review_json)

    @property
    def output_asset(self):
        return shared._asset_record(self.asset_header, self.content, self.original, self.icc)

    @property
    def token(self):
        return self.review['token']

    @property
    def retained_bytes(self):
        return sum(map(len, (self.review_json, self.asset_header, self.content, self.original, self.icc)))

    def validate_apply(self, command):
        command = write_command(command)
        value = self.review
        if (self._seal is not _SEAL or command['action'] != 'apply'
                or any(command[k] != value[k] for k in ('session_id', 'owner', 'token', 'recipe_sha256', 'result_source_sha256'))
                or command['before_sha256'] != value['before']['sha256']
                or command['after_sha256'] != value['after']['sha256']):
            raise ValueError('Restoration apply does not match the immutable full-source candidate')
        return True


def prepare(command, source, *, budget, cancelled=lambda: False):
    sources.require(source)
    command = _preview(command, source)
    admit_source(source, budget)
    extent = source.owner['source']
    width, height = extent['width'], extent['height']
    with shared._job(budget, cancelled) as poll:
        # Asset identity includes format/dimensions; adapter's digest deliberately
        # proves raw pixel bytes instead. Never substitute one for the other.
        content = source.pixels.content
        raw_sha = hashlib.sha256(content).hexdigest()
        canonical = CanonicalSource(width, height, content, raw_sha)
        result = adapter.restore_native_candidate(source=canonical, model_id=MODEL, check_cancelled=poll)
        poll()
        if (result.status != 'review_required' or result.model_id != MODEL or result.network_scale != 2
                or result.width != width or result.height != height or result.source_sha256 != raw_sha):
            raise ValueError('AI worker result does not belong to the full canonical source/profile')
        validate_source(CanonicalSource(width, height, result.rgba_f32le, result.result_sha256), check_cancelled=poll)
        content = result.rgba_f32le
        no_change = content == source.pixels.content
        from .creative_document_assets import make_asset
        from .creative_document_host import require_photo_return
        asset = source.pixels.asset if no_change else make_asset('rgba', width, height, content,
                    original=source.pixels.original, icc=source.pixels.icc)
        require_photo_return(asset)
        if no_change:
            content, after = source.pixels.content, source.pixels.source_image
        else:
            png, dw, dh = shared._display_png(content, width, height, poll)
            after = shared._png_record(png, dw, dh)
        review = {'version': PROTOCOL, 'operation_id': OPERATION, 'request_id': command['request_id'],
                  'session_id': command['session_id'], 'owner': source.owner, 'source_evidence': source.evidence,
                  'token': uuid.uuid4().hex, 'recipe': command['recipe'],
                  'recipe_sha256': shared._hash(b'lrt-upscale-restore-recipe-v1\0' + shared._json(command['recipe'])),
                  'result_source_sha256': asset['id'][7:], 'before': source.pixels.source_image,
                  'after': after, 'no_change': no_change,
                  'notes': ['完整当前编辑结果参与真实完整单帧模型推理，结果仍为原尺寸；无锐化或缩略图替代。',
                            'AI 可能改变人脸与纹理，请逐张审阅；本源码未经过画质、接缝或性能实机验收。',
                            '前后 PNG 仅用于完整画面显示，另存新图保留完整线性浮点候选。',
                            '另存后可使用现有项目保存与导出；此操作不自动保存磁盘、导出或覆盖原文件。']}
        header, content, original, icc = shared._asset_parts(asset)
        poll()
        return Candidate(shared._json(review), header, content, original, icc, no_change, _SEAL)
