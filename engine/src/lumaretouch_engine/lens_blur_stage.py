# SPDX-License-Identifier: GPL-3.0-or-later
"""Owned full-source lens review staging, with no document/history writes.

AUTHORED / UNRUN. This source is not application registration or acceptance.
Only real canonical RGBA assets enter; only the Rust aperture bridge renders.
A stage owns private immutable source/depth/recipe/output bytes, not an AssetStore.
Model-derived depth is unavailable until the optional adapter's provenance gates
are implemented and reviewed. A manual plane requires the exact explicit UI
acknowledgement command; it is never represented as measured scene depth.
"""
from __future__ import annotations

import base64
import binascii
from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import json
import math
import re
import struct
import threading
import time
import uuid
import zlib

OPERATION = 'lnx.lens_blur.v1'
WIRE_PROTOCOL = 3  # Renderer negotiation; version-1 numeric recipes/depth remain explicit.
ORIENTATION = 'exif_normalized_once'
MAPPING = 'normalized_full_frame_pixel_centres'
CONVENTION = 'near-zero-far-one'
MAX_SOURCE_PIXELS = 100_000_000
MAX_IMAGE_EDGE = 1280
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_DISPLAY_PIXELS = 1_000_000
MAX_DEPTH_EDGE = 1024
MAX_REQUEST_BYTES = 512 * 1024
DISPLAY_RESERVE = 96 * 1024 * 1024
_SEAL = object()
_JOB = threading.BoundedSemaphore(1)
_ASSET_KEYS = {'id', 'kind', 'width', 'height', 'encoding', 'alpha', 'source_hash', 'icc_hash', 'content', 'original', 'icc'}


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def _hash(value):
    return hashlib.sha256(value).hexdigest()


def _token(value):
    return type(value) is str and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value) is not None


def _sha(value):
    return type(value) is str and re.fullmatch(r'[a-f0-9]{64}', value) is not None


def _number(value, low, high):
    return type(value) in (int, float) and low <= value <= high and math.isfinite(value)


def _exact(value, keys):
    return type(value) is dict and set(value) == set(keys)


def _source(value):
    if (not _exact(value, ('sha256', 'width', 'height', 'orientation')) or not _sha(value['sha256'])
            or value['orientation'] != ORIENTATION
            or any(type(value[k]) is not int or not 2 <= value[k] <= 1_000_000 for k in ('width', 'height'))
            or value['width'] * value['height'] > MAX_SOURCE_PIXELS):
        raise ValueError('Lens source requires an exact canonical full-grid identity')


def _owner(value):
    if not _exact(value, ('document_id', 'document_epoch', 'document_revision', 'source')):
        raise ValueError('Lens owner requires exact document, epoch, revision and source')
    revision = value['document_revision']
    if (not _token(value['document_id']) or not _token(value['document_epoch'])
            or type(revision) is not str or re.fullmatch(r'0|[1-9][0-9]{0,19}', revision) is None
            or int(revision) > 18_446_744_073_709_551_615):
        raise ValueError('Invalid lens document owner/revision')
    _source(value['source'])


def _extent(width, height, edge, pixels):
    scale = min(1.0, edge / max(width, height), math.sqrt(pixels / (width * height)))
    result = (math.floor(width * scale), math.floor(height * scale))
    if min(result) < 2 or not _whole_frame(*result, width, height):
        raise ValueError('Full-frame lens review cannot represent this aspect without inventing pixels')
    return result


def _whole_frame(width, height, source_width, source_height):
    return (width <= source_width and height <= source_height
            and abs(width * source_height - height * source_width) <= max(source_width, source_height))


@dataclass(frozen=True, slots=True)
class Budget:
    """Per-job ceiling; the parent still owns aggregate retained session leases."""
    max_bytes: int
    max_candidate_taps: int = 250_000_000
    max_refinement_pixels: int = 64_000_000
    timeout_seconds: float = 120.0

    def __post_init__(self):
        if type(self.max_bytes) is not int or not 16 * 1024 * 1024 <= self.max_bytes <= 4_000_000_000:
            raise ValueError('Lens stage requires an explicit 16 MiB..4 GB memory budget')
        if any(type(x) is not int or not 1 <= x <= 10**12 for x in (self.max_candidate_taps, self.max_refinement_pixels)):
            raise ValueError('Lens work ceilings must be positive bounded integers')
        if not _number(self.timeout_seconds, .001, 600):
            raise ValueError('Lens stage needs a bounded positive timeout, at most ten minutes')


@contextmanager
def _job(budget, cancelled):
    if type(budget) is not Budget or not callable(cancelled):
        raise TypeError('Lens stage requires Budget and a cancellation predicate')
    if not _JOB.acquire(blocking=False):
        raise RuntimeError('Another lens source-stage job is active; no concurrent full-source allocation')
    deadline = time.monotonic() + budget.timeout_seconds
    def poll():
        if cancelled():
            raise InterruptedError('Lens stage cancelled; private candidate discarded')
        if time.monotonic() >= deadline:
            raise TimeoutError('Lens stage exceeded its admitted job deadline; no candidate published')
        return False
    try:
        poll()
        yield poll
        poll()
    finally:
        _JOB.release()


def _admit(needed, budget):
    if needed > budget.max_bytes:
        raise MemoryError('Full-source lens staging exceeds its explicit memory budget; no proxy fallback')
    from .cpu_memory_budget import available_estimate
    if needed > available_estimate():
        raise MemoryError('Insufficient visible CPU memory for the admitted lens stage')


def _asset_parts(asset):
    if not _exact(asset, _ASSET_KEYS) or any(type(asset[k]) is not bytes for k in ('content', 'original', 'icc')):
        raise ValueError('Lens source requires immutable canonical asset bytes')
    if (asset['kind'] != 'rgba' or asset['encoding'] != 'linear-srgb-d65' or asset['alpha'] != 'premultiplied'
            or any(type(asset[k]) is not int or not 2 <= asset[k] <= 1_000_000 for k in ('width', 'height'))
            or asset['width'] * asset['height'] > MAX_SOURCE_PIXELS
            or len(asset['content']) != asset['width'] * asset['height'] * 16
            or len(asset['original']) > 512_000_000 or len(asset['icc']) > 4_194_304
            or any(type(asset[k]) is not str or not asset[k].startswith('sha256:')
                   or not _sha(asset[k][7:]) for k in ('id', 'source_hash', 'icc_hash'))):
        raise ValueError('Lens asset metadata/precision/length violates the canonical RGBA contract')
    return _json({k: asset[k] for k in _ASSET_KEYS - {'content', 'original', 'icc'}}), asset['content'], asset['original'], asset['icc']


def _asset_record(header, content, original, icc):
    return {**json.loads(header), 'content': content, 'original': original, 'icc': icc}


def _png_record(png, width, height):
    return {'mime': 'image/png', 'width': width, 'height': height,
            'sha256': _hash(png), 'base64': base64.b64encode(png).decode('ascii')}


@dataclass(frozen=True, slots=True)
class CapturedSource:
    """Immutable bytes, not a merely write-protected ndarray or nested dict."""
    owner_json: bytes
    asset_header: bytes
    content: bytes = field(repr=False)
    original: bytes = field(repr=False)
    icc: bytes = field(repr=False)
    png: bytes = field(repr=False)
    display_width: int
    display_height: int
    _seal: object = field(repr=False, compare=False)

    @property
    def owner(self):
        return json.loads(self.owner_json)

    @property
    def asset(self):
        return _asset_record(self.asset_header, self.content, self.original, self.icc)

    @property
    def source_image(self):
        return _png_record(self.png, self.display_width, self.display_height)

    @property
    def retained_bytes(self):
        return sum(map(len, (self.owner_json, self.asset_header, self.content, self.original, self.icc, self.png)))


@dataclass(frozen=True, slots=True)
class CapturedDepth:
    wire_json: bytes
    raster_bytes: bytes = field(repr=False)
    session_id: str | None
    _seal: object = field(repr=False, compare=False)

    @property
    def asset(self):
        return json.loads(self.wire_json)

    @property
    def retained_bytes(self):
        return len(self.wire_json) + len(self.raster_bytes)


def _require_source(source):
    if type(source) is not CapturedSource or source._seal is not _SEAL:
        raise ValueError('Source must be captured from the actual immutable creative asset')


def _require_depth(depth, source, session_id=None):
    _require_source(source)
    if type(depth) is not CapturedDepth or depth._seal is not _SEAL:
        raise ValueError('Depth must be captured from actual owned raster bytes')
    asset = depth.asset
    if asset['owner'] != source.owner or (depth.session_id is not None and session_id != depth.session_id):
        raise ValueError('Depth belongs to another document/source or manual-acknowledgement session')
    return asset


def _chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)


def _display_png(content, width, height, poll):
    """Real whole-frame source-centre sample, RGBA PNG, display transfer ONLY.

    No clipping/quantization affects canonical source or output. The separately
    labeled SDR display maps signed/HDR RGB to sRGB8; alpha stays in the PNG.
    """
    import numpy as np
    from .creative_layer_native import display_rgba
    dw, dh = _extent(width, height, MAX_IMAGE_EDGE, MAX_DISPLAY_PIXELS)
    source = np.frombuffer(content, dtype='<f4').reshape(height, width, 4)
    sample = np.empty((dh, dw, 4), dtype=np.float32)
    xs = ((2 * np.arange(dw, dtype=np.int64) + 1) * width // (2 * dw))
    for y in range(dh):
        poll()
        sy = (2 * y + 1) * height // (2 * dh)
        sample[y] = source[sy, xs]
    alpha = sample[:, :, 3].copy()
    np.divide(sample[:, :, :3], alpha[:, :, None], out=sample[:, :, :3], where=alpha[:, :, None] > 0)
    sample[:, :, 3] = 1
    rgb = display_rgba(sample, matte=(0.0, 0.0, 0.0), cancelled=poll)
    rgba = np.empty((dh, dw, 4), dtype=np.uint8)
    rgba[:, :, :3] = rgb
    rgba[:, :, 3] = np.floor(alpha * 255 + .5).astype(np.uint8)
    compressor, pieces, size = zlib.compressobj(level=6), [], 0
    for row in rgba:
        poll()
        piece = compressor.compress(b'\0' + row.tobytes(order='C'))
        size += len(piece)
        if size > MAX_IMAGE_BYTES - 128:
            raise MemoryError('Lens PNG exceeded transport budget; no unrelated image substitute')
        pieces.append(piece)
    tail = compressor.flush()
    payload = b''.join(pieces) + tail
    png = (b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', struct.pack('>IIBBBBB', dw, dh, 8, 6, 0, 0, 0))
           + _chunk(b'sRGB', b'\0') + _chunk(b'IDAT', payload) + _chunk(b'IEND', b''))
    if len(png) > MAX_IMAGE_BYTES:
        raise MemoryError('Lens PNG exceeded transport budget')
    poll()
    return png, dw, dh


def capture_source(asset, owner, *, budget, cancelled=lambda: False):
    """Capture an already genuine, full edited RGBA asset, never decode a proxy.

    The parent's full capture must use a job-local AssetStore. This stage accepts
    no store and cannot intern failed/late outputs into document/history assets.
    It verifies canonical content identity AND its exact UI owner source tuple.
    """
    _owner(owner)
    # Freeze small mutable dictionaries first; payloads must already be bytes.
    owner_json = _json(owner)
    _owner(json.loads(owner_json))
    header, content, original, icc = _asset_parts(asset)
    owned = _asset_record(header, content, original, icc)
    source = json.loads(owner_json)['source']
    if (owned['id'] != 'sha256:' + source['sha256'] or owned['kind'] != 'rgba'
            or (owned['width'], owned['height']) != (source['width'], source['height'])
            or len(content) != source['width'] * source['height'] * 16):
        raise ValueError('Lens owner does not identify these exact full-source RGBA bytes')
    with _job(budget, cancelled) as poll:
        _admit(len(content) + len(original) + len(icc) + DISPLAY_RESERVE, budget)
        from .creative_document_assets import validate_asset
        validate_asset(owned)
        poll()
        png, width, height = _display_png(content, source['width'], source['height'], poll)
        return CapturedSource(owner_json, header, content, original, icc, png, width, height, _SEAL)


def _depth_wire(asset, source, *, manual_plane=False):
    _require_source(source)
    keys = ('version', 'token', 'owner', 'convention', 'mapping', 'orientation', 'raster', 'provenance', 'subject_focus')
    if (not _exact(asset, keys) or type(asset['version']) is not int or asset['version'] != 1
            or not _token(asset['token']) or asset['owner'] != source.owner
            or asset['convention'] != CONVENTION or asset['mapping'] != MAPPING
            or asset['orientation'] != ORIENTATION or asset['subject_focus'] is not None):
        raise ValueError('Depth must be a current owner-bound full-frame raster with no fabricated subject')
    provenance = asset['provenance']
    if type(provenance) is dict and provenance.get('kind') == 'model':
        raise ValueError('Optional AI depth provenance is not admitted; model inference remains unavailable')
    if manual_plane:
        if (not _exact(provenance, ('kind', 'method', 'depth_value', 'acknowledgement_id'))
                or provenance['kind'] != 'manual' or provenance['method'] != 'user_defined_plane'
                or not _number(provenance['depth_value'], 0, 1) or not _token(provenance['acknowledgement_id'])):
            raise ValueError('Manual editing plane requires its explicit acknowledgement')
    elif provenance != {'kind': 'manual', 'method': 'user_supplied_depth'}:
        raise ValueError('An actual supplied manual depth raster is required; no implicit plane or model substitute')
    raster = asset['raster']
    if (not _exact(raster, ('format', 'width', 'height', 'sha256', 'base64')) or raster['format'] != 'u16-le'
            or any(type(raster[k]) is not int or not 2 <= raster[k] <= MAX_DEPTH_EDGE for k in ('width', 'height'))
            or not _whole_frame(raster['width'], raster['height'], source.owner['source']['width'], source.owner['source']['height'])
            or not _sha(raster['sha256'])):
        raise ValueError('Depth raster is not the exact bounded oriented source-frame extent')
    length = raster['width'] * raster['height'] * 2
    encoded = raster['base64']
    if type(encoded) is not str or len(encoded) != ((length + 2) // 3) * 4:
        raise ValueError('Depth raster byte length exceeds the declared extent')
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError('Invalid depth Base64 bytes') from error
    if len(raw) != length or base64.b64encode(raw).decode('ascii') != encoded or _hash(raw) != raster['sha256']:
        raise ValueError('Depth raster canonical bytes/hash mismatch')
    if manual_plane:
        expected = struct.pack('<H', math.floor(provenance['depth_value'] * 65535 + .5))
        if raw != expected * (raster['width'] * raster['height']):
            raise ValueError('Manual plane samples do not equal the explicitly acknowledged constant')
    return raw


def capture_depth(asset, source, *, budget, cancelled=lambda: False):
    """Capture real manual u16-le depth; a model/plane label cannot authorize it."""
    _require_source(source)
    with _job(budget, cancelled) as poll:
        _admit(source.retained_bytes + DISPLAY_RESERVE, budget)
        raw = _depth_wire(asset, source)
        wire = _json(asset)
        # No caller-owned dict/list survives the snapshot boundary.
        frozen = json.loads(wire)
        if _depth_wire(frozen, source) != raw:
            raise ValueError('Depth changed during capture')
        poll()
        return CapturedDepth(wire, raw, None, _SEAL)


def prepare_manual_plane(command, source, *, budget, cancelled=lambda: False):
    """Only this explicit UI action may manufacture a manual editing baseline."""
    _require_source(source)
    required = ('version', 'action', 'request_id', 'session_id', 'owner', 'depth_value', 'acknowledged_manual')
    if (not _exact(command, required) or type(command['version']) is not int or command['version'] != WIRE_PROTOCOL
            or command['action'] != 'prepare_manual_plane' or command['acknowledged_manual'] is not True
            or not _token(command['request_id']) or not _token(command['session_id'])
            or command['owner'] != source.owner or not _number(command['depth_value'], 0, 1)):
        raise ValueError('An exact owner-bound explicit manual-plane acknowledgement is required')
    command = json.loads(_json(command))
    if (not _exact(command, required) or type(command['version']) is not int or command['version'] != WIRE_PROTOCOL
            or command['action'] != 'prepare_manual_plane' or command['acknowledged_manual'] is not True
            or not _token(command['request_id']) or not _token(command['session_id'])
            or command['owner'] != source.owner or not _number(command['depth_value'], 0, 1)):
        raise ValueError('Manual-plane acknowledgement changed during capture')
    with _job(budget, cancelled) as poll:
        _admit(source.retained_bytes + DISPLAY_RESERVE, budget)
        s = source.owner['source']
        width, height = _extent(s['width'], s['height'], MAX_DEPTH_EDGE, MAX_DEPTH_EDGE**2)
        raw = struct.pack('<H', math.floor(command['depth_value'] * 65535 + .5)) * (width * height)
        asset = {'version': 1, 'token': uuid.uuid4().hex, 'owner': source.owner,
                 'convention': CONVENTION, 'mapping': MAPPING, 'orientation': ORIENTATION,
                 'raster': {'format': 'u16-le', 'width': width, 'height': height, 'sha256': _hash(raw),
                            'base64': base64.b64encode(raw).decode('ascii')},
                 'provenance': {'kind': 'manual', 'method': 'user_defined_plane',
                                'depth_value': command['depth_value'], 'acknowledgement_id': command['request_id']},
                 'subject_focus': None}
        _depth_wire(asset, source, manual_plane=True)
        poll()
        return CapturedDepth(_json(asset), raw, command['session_id'], _SEAL)


def context(source, session_id, depth=None):
    """Exact UI LensContext; no automatic model, plane, or document mutation."""
    _require_source(source)
    if not _token(session_id):
        raise ValueError('Lens context needs its session token')
    asset = None if depth is None else _require_depth(depth, source, session_id)
    return {'session_id': session_id, 'owner': source.owner, 'source_image': source.source_image,
            'depth': asset, 'depth_status': 'ready' if asset is not None else 'manual-required',
            'message': ('人工景深输入，不是 AI 分析。' if asset is not None and asset['provenance']['method'] == 'user_supplied_depth'
                        else '人工恒定编辑基准面，不是测量或 AI 景深。' if asset is not None
                        else 'AI 景深来源验证尚未就绪。可显式选择人工散焦编辑；不会自动生成景深。')}


def _point_focus(focus, source, depth, raster_bytes):
    """Validate the UI's actual point sample, not an untrusted point label.

    Four little-endian owned u16 samples, the same source-centre mapping and
    f64 operation order as sampleLensDepth. A legal point interval is a
    symmetric radius around that sample, clipped only at zero/one. Sliders
    intentionally change the UI mode to interval rather than claiming a point.
    """
    point = focus['point']
    sw, sh = source['width'], source['height']
    dw, dh = depth['raster']['width'], depth['raster']['height']
    x = min(dw - 1, max(0., (point['x'] * (sw - 1) + .5) * dw / sw - .5))
    y = min(dh - 1, max(0., (point['y'] * (sh - 1) + .5) * dh / sh - .5))
    x0, y0 = math.floor(x), math.floor(y)
    x1, y1 = min(dw - 1, x0 + 1), min(dh - 1, y0 + 1)
    dx, dy = x - x0, y - y0
    def at(a, b):
        return struct.unpack_from('<H', raster_bytes, (b * dw + a) * 2)[0] / 65535
    sampled = ((at(x0, y0) * (1 - dx) + at(x1, y0) * dx) * (1 - dy)
               + (at(x0, y1) * (1 - dx) + at(x1, y1) * dx) * dy)
    radius = max(sampled - focus['near'], focus['far'] - sampled)
    epsilon = 1e-12  # Binary64 interchange only, far below one u16 depth step.
    if (focus['near'] > sampled + epsilon or focus['far'] < sampled - epsilon
            or radius < -epsilon
            or abs(focus['near'] - max(0., sampled - radius)) > epsilon
            or abs(focus['far'] - min(1., sampled + radius)) > epsilon):
        raise ValueError('Lens point focus interval does not correspond to its actual owned depth sample')


def _recipe(value, source, depth, raster_bytes):
    from .lens_blur_refinement import validate_strokes
    from .lens_aperture_native import normalize_settings
    required = ('version', 'operation_id', 'source', 'depth', 'aperture', 'max_radius_px', 'focus',
                'depth_falloff', 'occlusion_tolerance', 'rotation_radians', 'refinements')
    version = value.get('version') if type(value) is dict else None
    if type(version) is not int or version not in (1, 2):
        raise ValueError('Unknown lens numeric recipe; no automatic migration')
    if version == 2:
        required += ('math_identity',)
        if (value.get('operation_id') != 'lnx.lens_blur.cohort.v2'
                or value.get('math_identity') != 'cohort-fft-f64-v2-00020001'
                or depth['provenance'].get('method') != 'user_defined_plane'):
            raise ValueError('Cohort renderer needs its explicit math identity and acknowledged manual plane')
    elif value.get('operation_id') != OPERATION:
        raise ValueError('Original lens recipe operation changed')
    if not _exact(value, required) or value['source'] != source.owner['source']:
        raise ValueError('Lens recipe does not identify this source/operation')
    expected = {'token': depth['token'], 'sha256': depth['raster']['sha256'], 'provenance': depth['provenance']}
    if value['depth'] != expected:
        raise ValueError('Lens recipe depth differs from the retained actual raster/provenance')
    focus = value['focus']
    if (not _exact(focus, ('mode', 'near', 'far', 'point')) or focus['mode'] not in ('point', 'interval')
            or not _number(focus['near'], 0, 1) or not _number(focus['far'], focus['near'], 1)):
        raise ValueError('Lens focus requires an ordered real interval; measured subject mode is unavailable')
    point = focus['point']
    if focus['mode'] == 'point':
        if not _exact(point, ('x', 'y')) or any(not _number(point[k], 0, 1) for k in ('x', 'y')):
            raise ValueError('Lens point focus needs normalized source-centre coordinates')
        _point_focus(focus, source.owner['source'], depth, raster_bytes)
    elif point is not None:
        raise ValueError('Interval focus cannot retain an unrelated point')
    validate_strokes(value['refinements'])
    settings = normalize_settings({'version': 1, 'aperture': value['aperture'], 'max_radius_px': value['max_radius_px'],
        'focus_near': focus['near'], 'focus_far': focus['far'], 'depth_falloff': value['depth_falloff'],
        'occlusion_tolerance': value['occlusion_tolerance'], 'rotation_radians': value['rotation_radians']})
    if len(_json(value)) > MAX_REQUEST_BYTES:
        raise ValueError('Lens recipe exceeds the complete request budget')
    return settings


def _full_depth(depth, width, height, poll):
    """UI's exact edge/centre bilinear map, no naive u*(depthWidth-1).

    Source centre (x,y) maps to ((x+.5)*dw/W-.5,(y+.5)*dh/H-.5).
    Only actual raster borders clamp. u16 values divide by 65535 in f64 and
    round once to native f32. This never claims new measured detail.
    """
    import numpy as np
    asset = depth.asset
    dw, dh = asset['raster']['width'], asset['raster']['height']
    raster = np.frombuffer(depth.raster_bytes, dtype='<u2').reshape(dh, dw)
    out = np.empty((height, width), dtype=np.float32)
    for y in range(height):
        fy = min(dh - 1, max(0., (y + .5) * dh / height - .5))
        y0 = math.floor(fy)
        y1, dy = min(dh - 1, y0 + 1), fy - y0
        for left in range(0, width, 4096):
            poll()
            right = min(width, left + 4096)
            fx = np.clip((np.arange(left, right, dtype=np.float64) + .5) * dw / width - .5, 0, dw - 1)
            x0 = np.floor(fx).astype(np.int64)
            x1, dx = np.minimum(dw - 1, x0 + 1), fx - x0
            upper = (raster[y0, x0].astype(np.float64) / 65535 * (1 - dx)
                     + raster[y0, x1].astype(np.float64) / 65535 * dx)
            lower = (raster[y1, x0].astype(np.float64) / 65535 * (1 - dx)
                     + raster[y1, x1].astype(np.float64) / 65535 * dx)
            out[y, left:right] = upper * (1 - dy) + lower * dy
    poll()
    return out


@dataclass(frozen=True, slots=True)
class Candidate:
    """Immutable private return; the existing host alone owns atomic publication."""
    review_json: bytes
    asset_header: bytes
    content: bytes = field(repr=False)
    original: bytes = field(repr=False)
    icc: bytes = field(repr=False)
    no_change: bool
    refinement_sha256: str | None
    processing_depth_sha256: str
    _seal: object = field(repr=False, compare=False)

    @property
    def review(self):
        return json.loads(self.review_json)

    @property
    def output_asset(self):
        return _asset_record(self.asset_header, self.content, self.original, self.icc)

    @property
    def token(self):
        return self.review['token']

    @property
    def recipe_sha256(self):
        return self.review['recipe_sha256']

    @property
    def retained_bytes(self):
        return sum(map(len, (self.review_json, self.asset_header, self.content, self.original, self.icc)))

    def validate_apply(self, command):
        """Correlate only, not commit, receipt, current-owner or presentation proof."""
        if self._seal is not _SEAL:
            raise ValueError('Unissued lens candidate')
        required = ('version', 'action', 'request_id', 'session_id', 'owner', 'token', 'recipe_sha256', 'before_sha256', 'after_sha256', 'reviewed', 'return_mode', 'result_source_sha256')
        r = self.review
        if (not _exact(command, required) or type(command['version']) is not int or command['version'] != WIRE_PROTOCOL
                or command['action'] != 'apply' or not _token(command['request_id']) or command['reviewed'] is not True
                or command['return_mode'] != 'new_image' or command['result_source_sha256'] != r['result_source_sha256']
                or command['session_id'] != r['session_id'] or command['owner'] != r['owner'] or command['token'] != r['token']
                or command['recipe_sha256'] != r['recipe_sha256'] or command['before_sha256'] != r['before']['sha256']
                or command['after_sha256'] != r['after']['sha256']):
            raise ValueError('Lens apply does not match the exact immutable reviewed candidate')
        return True


def prepare(command, source, depth, *, budget, cancelled=lambda: False):
    """Real full-source native result + full-frame before/after PNGs, no publish.

    Ownership/cancellation predicate must include the parent's live document and
    session fence. The parent rechecks that fence immediately before its atomic
    existing history transaction. Discarding this return releases all stage data;
    no global cache, AssetStore, document, history or on-disk artifact is changed.
    """
    _require_source(source)
    if (not _exact(command, ('version', 'action', 'request_id', 'session_id', 'owner', 'recipe'))
            or type(command['version']) is not int or command['version'] != WIRE_PROTOCOL or command['action'] != 'preview'
            or not _token(command['request_id']) or not _token(command['session_id']) or command['owner'] != source.owner):
        raise ValueError('Lens preview requires its exact current session/document/source owner')
    depth_asset = _require_depth(depth, source, command['session_id'])
    settings = _recipe(command['recipe'], source, depth_asset, depth.raster_bytes)
    wire = _json(command)
    if len(wire) > MAX_REQUEST_BYTES:
        raise ValueError('Complete lens preview command exceeds 512 KiB; no strokes omitted')
    command = json.loads(wire)
    if (not _exact(command, ('version', 'action', 'request_id', 'session_id', 'owner', 'recipe'))
            or type(command['version']) is not int or command['version'] != WIRE_PROTOCOL or command['action'] != 'preview'
            or not _token(command['request_id']) or not _token(command['session_id']) or command['owner'] != source.owner):
        raise ValueError('Lens preview identity changed during capture')
    depth_asset = _require_depth(depth, source, command['session_id'])
    settings = _recipe(command['recipe'], source, depth_asset, depth.raster_bytes)
    if command['recipe']['version'] == 2:
        from .lens_blur_cohort_stage import prepare_validated
        return prepare_validated(command, source, depth, settings, budget=budget, cancelled=cancelled)
    from . import lens_aperture_native as aperture
    from . import lens_blur_refinement as refinement
    s = source.owner['source']
    width, height = s['width'], s['height']
    work = aperture.work_estimate((height, width), settings)
    brush = refinement.estimate(command['recipe']['refinements'], width, height)
    if type(budget) is not Budget:
        raise TypeError('Lens preview requires Budget')
    if work['candidate_taps'] > budget.max_candidate_taps or brush['pixels_examined'] > budget.max_refinement_pixels:
        raise MemoryError('Lens full-source native/refinement work exceeds its explicit budget')
    # Conservative simultaneous peak: caller source/depth, endian conversion,
    # source/depth/refinement private snapshots, output array+canonical bytes,
    # stroke coverage+immutable mask, native validation/tile scratch, PNGs/JSON.
    needed = source.retained_bytes + depth.retained_bytes + width * height * 128 + DISPLAY_RESERVE + 32 * 1024 * 1024
    with _job(budget, cancelled) as poll:
        _admit(needed, budget)
        # Availability even for neutral intent; never successful identity fallback.
        cap = aperture.capability()
        if not cap['lens_aperture_available'] or settings['aperture'] not in cap['kernels']:
            raise aperture.LensApertureUnavailable(cap['lens_aperture_reason'] or 'Requested aperture is unavailable')
        import numpy as np
        pixels = np.frombuffer(source.content, dtype='<f4').reshape(height, width, 4)
        if not pixels.dtype.isnative:
            pixels = pixels.astype(np.float32)
        relative = _full_depth(depth, width, height, poll)
        correction_bytes = refinement.rasterize(command['recipe']['refinements'], width, height,
            max_bytes=brush['peak_bytes'], max_pixels_examined=budget.max_refinement_pixels, cancelled=poll)
        correction = None if correction_bytes is None else np.frombuffer(correction_bytes, dtype='<f4').reshape(height, width)
        if correction is not None and not correction.dtype.isnative:
            correction = correction.astype(np.float32)
        output = aperture.apply(pixels, relative, settings, refinement=correction,
            max_candidate_taps=budget.max_candidate_taps, cancelled=poll)
        poll()
        depth_hash = hashlib.sha256()
        for row in relative:
            poll()
            depth_hash.update(row.astype('<f4', copy=False).tobytes(order='C'))
        content = output.astype('<f4', copy=False).tobytes(order='C')
        no_change = content == source.content
        from .creative_document_assets import make_asset
        asset = source.asset if no_change else make_asset('rgba', width, height, content, original=source.original, icc=source.icc)
        poll()
        after_png, dw, dh = (source.png, source.display_width, source.display_height) if no_change else _display_png(content, width, height, poll)
        before, after = source.source_image, _png_record(after_png, dw, dh)
        recipe_hash = _hash(b'lrt-lens-recipe-v1\0' + _json(command['recipe']))
        token = _hash(b'lrt-lens-candidate-v1\0' + uuid.uuid4().bytes + _json({
            'session_id': command['session_id'], 'owner': source.owner, 'recipe_sha256': recipe_hash,
            'output_asset_id': asset['id'], 'before_sha256': before['sha256'], 'after_sha256': after['sha256']}))
        review = {'version': WIRE_PROTOCOL, 'request_id': command['request_id'], 'session_id': command['session_id'],
            'token': token, 'owner': source.owner, 'recipe': command['recipe'], 'recipe_sha256': recipe_hash,
            'result_source_sha256': asset['id'][7:],
            'before': before, 'after': after, 'notes': [
                '使用真实完整源图和原生光圈渲染；未修改文档或历史。',
                '对比图为完整画面的 SDR 显示采样；完整输出保留线性浮点、透明度及有符号 HDR，不以显示图替换。',
                '人工恒定编辑基准面，不是测量或 AI 景深。' if depth.session_id is not None else '人工提供的景深栅格，不是 AI 分析。']}
        header, content, original, icc = _asset_parts(asset)
        poll()
        return Candidate(_json(review), header, content, original, icc, no_change,
                         None if correction_bytes is None else _hash(correction_bytes), depth_hash.hexdigest(), _SEAL)
