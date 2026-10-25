# SPDX-License-Identifier: GPL-3.0-or-later
"""Immutable full-source glow candidate and actual before/after/green review.

AUTHORED / UNRUN. Shared canonical image ownership/display primitives are reused;
all glow math and affected coverage come exclusively from the versioned Rust core.
"""
from dataclasses import dataclass, field
import json
import struct
import uuid
import zlib
from . import lens_blur_stage as shared
from . import light_glow_native as core
from . import light_glow_source as sources

OPERATION = core.OPERATION
PROTOCOL = 1
Budget = shared.Budget
capability = core.capability
_SEAL = object()
MAX_COMMAND_BYTES = 16 * 1024
DISPLAY_RESERVE = shared.DISPLAY_RESERVE


def _preview(command, source):
    if (not shared._exact(command, ('version', 'operation_id', 'action', 'request_id', 'session_id', 'owner', 'recipe'))
            or type(command['version']) is not int or command['version'] != PROTOCOL
            or command['operation_id'] != OPERATION or command['action'] != 'preview'
            or not shared._token(command['request_id']) or not shared._token(command['session_id'])
            or command['owner'] != source.owner):
        raise ValueError('Glow preview requires its exact current full-source/session owner')
    core.recipe(command['recipe'])
    raw = shared._json(command)
    if len(raw) > MAX_COMMAND_BYTES:
        raise ValueError('Glow preview exceeds its bounded exact command budget')
    return json.loads(raw)


def write_command(command):
    base = {'version', 'operation_id', 'action', 'request_id', 'session_id', 'owner', 'token'}
    if (type(command) is not dict or type(command.get('version')) is not int or command['version'] != PROTOCOL
            or command.get('operation_id') != OPERATION
            or not shared._token(command.get('request_id')) or not shared._token(command.get('session_id'))):
        raise ValueError('Glow writes require exact versioned request and session identities')
    shared._owner(command.get('owner'))
    if command.get('action') == 'apply':
        hashes = {'recipe_sha256', 'result_source_sha256', 'coverage_sha256',
                  'before_sha256', 'after_sha256', 'coverage_image_sha256'}
        if (set(command) != base | hashes | {'reviewed', 'return_mode'}
                or not shared._token(command['token']) or command['reviewed'] is not True
                or command['return_mode'] != 'new_image' or any(not shared._sha(command[k]) for k in hashes)):
            raise ValueError('Glow apply needs exact full-image/actual-coverage review and explicit new-image return')
    elif command.get('action') == 'cancel':
        if set(command) != base or command['token'] is not None and not shared._token(command['token']):
            raise ValueError('Malformed exact glow cancellation')
    else:
        raise ValueError('Unsupported glow write action')
    raw = shared._json(command)
    if len(raw) > MAX_COMMAND_BYTES:
        raise ValueError('Glow write exceeds its receipt identity budget')
    return json.loads(raw)


def _working(source, recipe, budget, poll):
    sources.require(source)
    s = source.owner['source']
    settings = core.recipe(recipe)
    schedule = core.plans(s['width'], s['height'], settings,
                          max_work_bytes=min(core.MAX_NATIVE_BYTES, budget.max_bytes), cancelled=poll)
    peak = max(plan.required_bytes + geometry.tile_width * geometry.tile_height * 20
               for geometry, plan in schedule)
    # Source + full output and native coverage + immutable freezes, native
    # transactional tile workspace, validation/array headers, and display JSON.
    required = source.retained_bytes + s['width'] * s['height'] * 40 + peak + 8 * 1024 * 1024 + DISPLAY_RESERVE
    shared._admit(required, budget)
    return required


def admit_source(source, budget):
    """A usable nonzero default must fit; no session that only saves identity."""
    value = {'version': 1, 'operation_id': OPERATION, 'math_identity': core.MATH,
             'mode': 'black_mist', 'strength': .3, 'radius_px': 24, 'threshold': .65,
             'exposure_ev': 0, 'scattering': 0,
             'tint': {'hue_deg': 0, 'saturation': 0, 'lightness': 0}}
    _working(source, value, budget, lambda: False)


def context(source, session_id, cap):
    sources.require(source)
    if not shared._token(session_id):
        raise ValueError('Glow context requires its issued session')
    return {'version': PROTOCOL, 'operation_id': OPERATION, 'session_id': session_id,
            'owner': source.owner, 'source_evidence': source.evidence,
            'before': source.pixels.source_image, 'capability': cap,
            'message': '本地确定性光扩散近似，不声称 AI 受光面分析或物理折射复刻。完整当前编辑结果参与计算；仅不透明 SDR，确认后另存新图，原图不改。'}


def _coverage_png(content, width, height, poll):
    """Real native affected-RGB-delta coverage, green RGB + coverage alpha.

    Samples exactly the same source-centre full-frame grid as before/after. No
    synthetic threshold selection, crop substitute or full-image RGBA allocation.
    """
    import numpy as np
    dw, dh = shared._extent(width, height, shared.MAX_IMAGE_EDGE, shared.MAX_DISPLAY_PIXELS)
    source = np.frombuffer(content, dtype='<f4').reshape(height, width)
    xs = (2 * np.arange(dw, dtype=np.int64) + 1) * width // (2 * dw)
    row = np.zeros((dw, 4), dtype=np.uint8)
    row[:, 1] = 255
    compressor, pieces, size = zlib.compressobj(level=6), [], 0
    for y in range(dh):
        poll()
        sy = (2 * y + 1) * height // (2 * dh)
        row[:, 3] = np.floor(source[sy, xs] * 255 + .5).astype(np.uint8)
        piece = compressor.compress(b'\0' + row.tobytes(order='C'))
        size += len(piece)
        if size > shared.MAX_IMAGE_BYTES - 128:
            raise MemoryError('Glow actual coverage PNG exceeds transport budget')
        pieces.append(piece)
    payload = b''.join(pieces) + compressor.flush()
    png = (b'\x89PNG\r\n\x1a\n' + shared._chunk(b'IHDR', struct.pack('>IIBBBBB', dw, dh, 8, 6, 0, 0, 0))
           + shared._chunk(b'sRGB', b'\0') + shared._chunk(b'IDAT', payload) + shared._chunk(b'IEND', b''))
    if len(png) > shared.MAX_IMAGE_BYTES:
        raise MemoryError('Glow actual coverage PNG exceeds transport budget')
    poll()
    return shared._png_record(png, dw, dh)


@dataclass(frozen=True, slots=True)
class Candidate:
    review_json: bytes
    asset_header: bytes
    content: bytes = field(repr=False)
    original: bytes = field(repr=False)
    icc: bytes = field(repr=False)
    coverage_content: bytes = field(repr=False)
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
        return sum(map(len, (self.review_json, self.asset_header, self.content,
                             self.original, self.icc, self.coverage_content)))

    def validate_apply(self, command):
        command = write_command(command)
        r = self.review
        if (self._seal is not _SEAL or command['action'] != 'apply'
                or any(command[k] != r[k] for k in
                       ('session_id', 'owner', 'token', 'recipe_sha256', 'result_source_sha256', 'coverage_sha256'))
                or command['before_sha256'] != r['before']['sha256']
                or command['after_sha256'] != r['after']['sha256']
                or command['coverage_image_sha256'] != r['coverage']['sha256']):
            raise ValueError('Glow apply does not match the immutable full image and actual coverage candidate')
        return True


def prepare(command, source, *, budget, cancelled=lambda: False):
    sources.require(source)
    command = _preview(command, source)
    s = source.owner['source']
    width, height = s['width'], s['height']
    with shared._job(budget, cancelled) as poll:
        cap = capability()
        if cap['status'] != 'available':
            raise core.Unavailable(cap['reason'])
        _working(source, command['recipe'], budget, poll)
        # Reserve final immutable copies plus display before native allocation.
        remaining = budget.max_bytes - source.retained_bytes - width * height * 20 - DISPLAY_RESERVE
        output, affected = core.render(source.pixels.content, width, height, command['recipe'],
                                       max_bytes=remaining, cancelled=poll)
        poll()
        content = output.astype('<f4', copy=False).tobytes(order='C')
        coverage_content = affected.astype('<f4', copy=False).tobytes(order='C')
        del output, affected
        no_change = content == source.pixels.content
        from .creative_document_assets import make_asset
        from .creative_document_host import require_photo_return
        asset = source.pixels.asset if no_change else make_asset('rgba', width, height, content,
                    original=source.pixels.original, icc=source.pixels.icc)
        require_photo_return(asset)
        if no_change:
            content = source.pixels.content
            after = source.pixels.source_image
        else:
            png, dw, dh = shared._display_png(content, width, height, poll)
            after = shared._png_record(png, dw, dh)
        before = source.pixels.source_image
        coverage = _coverage_png(coverage_content, width, height, poll)
        recipe_hash = shared._hash(b'lrt-light-glow-recipe-v1\0' + shared._json(command['recipe']))
        coverage_hash = shared._hash(coverage_content)
        review = {'version': PROTOCOL, 'operation_id': OPERATION, 'request_id': command['request_id'],
                  'session_id': command['session_id'], 'owner': source.owner, 'source_evidence': source.evidence,
                  'token': uuid.uuid4().hex, 'recipe': command['recipe'], 'recipe_sha256': recipe_hash,
                  'result_source_sha256': asset['id'][7:], 'coverage_sha256': coverage_hash,
                  'before': before, 'after': after, 'coverage': coverage, 'no_change': no_change,
                  'notes': ['完整当前编辑结果经版本化本地原生光扩散处理，未修改原图或历史。',
                            '绿色透明度来自原生每像素最大 RGB 实际变化量，不是 AI 受光面或阈值选区。',
                            '对比图仅为完整画面显示采样；候选始终保留完整尺寸线性浮点源，不以预览图替代。',
                            '本地预设与数值范围是本软件校准，不声称复刻参考软件的未披露参数。']}
        header, content, original, icc = shared._asset_parts(asset)
        poll()
        return Candidate(shared._json(review), header, content, original, icc,
                         coverage_content, no_change, _SEAL)
