"""Editable source-domain local masks; Python validates/transports, Rust rasterizes.

RGB must be the immutable, encoded working-sRGB source, never retouched/deformed
pixels. Missing semantic operands suspend the *whole* composition, even subtract.
The returned raster is disposable: persist objects, not these proxy pixels.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import re
import select
import struct
import subprocess
import time

import numpy as np

VERSION = 1
DOMAIN = 'source-normalized'
MAX_OBJECTS = 64
MAX_POINTS = 1024
MAX_TOTAL_POINTS = 8192
MAX_PIXELS = 64_000_000
MAX_WORK = 512_000_000
MAX_TILE_PIXELS = 2_000_000
MAX_PACKET_BYTES = 128 * 1024 * 1024
TILE = 512
TIMEOUT = 60.0
KINDS = ('full', 'brush', 'linear', 'radial', 'color_range', 'luminance_range', 'semantic')
OPERATIONS = ('add', 'subtract', 'intersect')
COMMON = {'id', 'name', 'enabled', 'operation', 'kind', 'opacity', 'feather'}
EXTRA = {'full': set(), 'brush': {'points', 'axes'},
         'linear': {'start', 'end', 'cross'}, 'radial': {'center', 'axes'},
         'color_range': {'color', 'tolerance'}, 'luminance_range': {'low', 'high'},
         'semantic': {'channel'}}


class MaskUnavailable(ValueError):
    """Required source/semantic data is absent; caller must suspend this consumer."""


def number(value, low=None, high=None):
    if type(value) not in (int, float):
        raise ValueError('Local mask parameters must be finite numbers')
    try:
        value = float(value)
    except (ValueError, OverflowError) as error:
        raise ValueError('Local mask parameters must be finite numbers') from error
    if not math.isfinite(value) or (low is not None and value < low) or (high is not None and value > high):
        raise ValueError('Local mask parameter is outside its finite range')
    return value


def pair(value, *, point=False):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError('Local mask coordinates require pairs')
    return [number(v, 0 if point else -4, 1 if point else 4) for v in value]


def _basis(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError('Local mask requires two independent axes')
    axes = [pair(v) for v in value]
    if abs(axes[0][0]*axes[1][1]-axes[0][1]*axes[1][0]) < 1e-12:
        raise ValueError('Local mask axes are degenerate')
    return axes


def check_object(raw):
    if type(raw) is not dict or raw.get('kind') not in KINDS:
        raise ValueError('Unsupported local mask object')
    kind = raw['kind']
    if set(raw) != COMMON | EXTRA[kind]:
        raise ValueError('Invalid local mask object fields')
    ident, name = raw['id'], raw['name']
    if type(ident) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', ident):
        raise ValueError('Invalid local mask object id')
    if type(name) is not str or not name.strip() or len(name) > 80 or any(ord(c) < 32 for c in name):
        raise ValueError('Local mask name must contain 1–80 printable characters')
    if type(raw['enabled']) is not bool or raw['operation'] not in OPERATIONS:
        raise ValueError('Invalid local mask visibility or operation')
    out = dict(id=ident, name=name, enabled=raw['enabled'], operation=raw['operation'],
               kind=kind, opacity=number(raw['opacity'], 0, 1), feather=number(raw['feather'], 0, 100))
    if kind == 'full':
        if not out['enabled'] or out['operation'] != 'add' or out['opacity'] != 1 or out['feather'] != 0:
            raise ValueError('The full-image mask cannot be hidden or edited')
    elif kind == 'brush':
        if not isinstance(raw['points'], (list, tuple)) or not 1 <= len(raw['points']) <= MAX_POINTS:
            raise ValueError('A local-mask brush requires 1–1024 points')
        out.update(points=[pair(p, point=True) for p in raw['points']], axes=_basis(raw['axes']))
    elif kind == 'linear':
        start, end, cross = pair(raw['start'], point=True), pair(raw['end'], point=True), pair(raw['cross'])
        _basis([[end[i]-start[i] for i in (0, 1)], cross])
        out.update(start=start, end=end, cross=cross)
    elif kind == 'radial':
        out.update(center=pair(raw['center'], point=True), axes=_basis(raw['axes']))
    elif kind == 'color_range':
        if not isinstance(raw['color'], (list, tuple)) or len(raw['color']) != 3:
            raise ValueError('Colour range requires encoded-sRGB colour')
        out.update(color=[number(v, 0, 1) for v in raw['color']], tolerance=number(raw['tolerance'], 0, 1))
    elif kind == 'luminance_range':
        low, high = number(raw['low'], 0, 1), number(raw['high'], 0, 1)
        if low > high:
            raise ValueError('Luminance range minimum exceeds maximum')
        out.update(low=low, high=high)
    elif kind == 'semantic':
        channel = raw['channel']
        if type(channel) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', channel):
            raise ValueError('Invalid local mask semantic channel')
        out['channel'] = channel
    return out


def check_stack(raw):
    if (type(raw) is not dict or set(raw) != {'version', 'domain', 'objects'}
            or type(raw['version']) is not int or raw['version'] != VERSION or raw['domain'] != DOMAIN
            or not isinstance(raw['objects'], list) or len(raw['objects']) > MAX_OBJECTS):
        raise ValueError('Unsupported or oversized local mask stack')
    objects = [check_object(o) for o in raw['objects']]
    if len({o['id'] for o in objects}) != len(objects):
        raise ValueError('Duplicate local mask object ids')
    if sum(o['kind'] == 'full' for o in objects) > 1:
        raise ValueError('Only one protected full-image mask is allowed')
    if sum(len(o.get('points', [])) for o in objects) > MAX_TOTAL_POINTS:
        raise ValueError('Local mask stack exceeds the total brush-point budget')
    return dict(version=VERSION, domain=DOMAIN, objects=objects)


def check_transition(previous, proposed):
    """Protect full-image identity/fields; deleting other objects may shift it.

    The controller rejects an explicit move of the full object. Index equality
    here would wrongly reject deleting an ordinary preceding object or clearing
    all editable objects while preserving full.
    """
    before, after = check_stack(previous), check_stack(proposed)
    by_id = {obj['id']: obj for obj in after['objects']}
    for obj in before['objects']:
        if obj['kind'] == 'full' and by_id.get(obj['id']) != obj:
            raise ValueError('The full-image mask cannot be hidden, edited, or deleted')
    return after


def dependencies(stack):
    objects = [o for o in check_stack(stack)['objects'] if o['enabled']]
    return (any(o['kind'] in ('color_range', 'luminance_range') for o in objects),
            tuple(sorted({o['channel'] for o in objects if o['kind'] == 'semantic'})))


def _shape(shape):
    if (not isinstance(shape, (list, tuple)) or len(shape) != 2
            or any(type(n) is not int or n < 1 or n > 65536 for n in shape)
            or shape[0]*shape[1] > MAX_PIXELS):
        raise ValueError('Local mask image exceeds the 64-megapixel raster budget')
    return shape[0], shape[1]


def _radius(obj, shape):
    # Integer sample support of a source-normalized spatial feather, not UI px.
    return int(math.ceil(obj['feather'] * .0005 * min(shape)))


def _tiles(shape, radius):
    h, w = shape
    for y in range(0, h, TILE):
        for x in range(0, w, TILE):
            cw, ch = min(TILE, w-x), min(TILE, h-y)
            x0, y0 = max(0, x-radius), max(0, y-radius)
            x1, y1 = min(w, x+cw+radius), min(h, y+ch+radius)
            yield x0, y0, x1-x0, y1-y0, x-x0, y-y0, cw, ch


def _brush_work(obj, tile, shape):
    h, w = shape
    x, y, tw, th = tile[:4]
    axes = obj['axes']
    ex = math.hypot(axes[0][0], axes[1][0])*w
    ey = math.hypot(axes[0][1], axes[1][1])*h
    points = [(p[0]*w-.5, p[1]*h-.5) for p in obj['points']]
    segments = zip(points, points[1:]) if len(points) > 1 else [(points[0], points[0])]
    work = 0
    for a, b in segments:
        xa = max(x, math.floor(min(a[0], b[0])-ex))
        xb = min(x+tw, math.ceil(max(a[0], b[0])+ex)+1)
        ya = max(y, math.floor(min(a[1], b[1])-ey))
        yb = min(y+th, math.ceil(max(a[1], b[1])+ey)+1)
        work += max(0, xb-xa)*max(0, yb-ya)
    return work


def validate_budget(stack, shape):
    stack = check_stack(stack)
    shape = _shape(shape)
    active = [o for o in stack['objects'] if o['enabled']]
    needs_rgb, channels = dependencies(stack)
    if len(channels) > 16:
        raise ValueError('Local mask stack exceeds the semantic channel budget')
    overhead = 56+len(_objects_packet(active, shape, channels))
    radius = max((_radius(o, shape) for o in active), default=0)
    work = 0
    for tile in _tiles(shape, radius):
        area = tile[2]*tile[3]
        if area > MAX_TILE_PIXELS:
            raise ValueError('Local mask feather exceeds the bounded tile budget')
        if overhead+area*(12*int(needs_rgb)+4*len(channels)) > MAX_PACKET_BYTES:
            raise ValueError('Local mask transport exceeds the bounded tile budget')
        for obj in active:
            work += (_brush_work(obj, tile, shape) if obj['kind'] == 'brush' else area)
            r = _radius(obj, shape)
            work += area*2+r*(tile[2]+tile[3]) if r else 0
            work += tile[6]*tile[7]
            if work > MAX_WORK:
                raise ValueError('Local mask stack exceeds the raster work budget; simplify objects or feather')
    return dict(pixels=shape[0]*shape[1], work=work, radius=radius)


def _f64(values):
    return struct.pack('<'+'d'*len(values), *values)


def _objects_packet(objects, shape, channels):
    packet = bytearray()
    for obj in objects:
        packet += struct.pack('<BBdI', KINDS.index(obj['kind']), OPERATIONS.index(obj['operation']),
                              obj['opacity'], _radius(obj, shape))
        kind = obj['kind']
        if kind == 'brush':
            packet += struct.pack('<I', len(obj['points']))
            packet += _f64([v for p in obj['points'] for v in p]+[v for a in obj['axes'] for v in a])
        elif kind == 'linear':
            packet += _f64(obj['start']+obj['end']+obj['cross'])
        elif kind == 'radial':
            packet += _f64(obj['center']+[v for a in obj['axes'] for v in a])
        elif kind == 'color_range':
            packet += _f64(obj['color']+[obj['tolerance']])
        elif kind == 'luminance_range':
            packet += _f64([obj['low'], obj['high']])
        elif kind == 'semantic':
            packet += struct.pack('<I', channels.index(obj['channel']))
    return packet


class _Worker:
    """One worker per raster, framed bounded tiles, deadline on every pipe IO."""
    def __init__(self):
        path = Path(__file__).resolve().parent/'bin'/'local-masks'
        if not path.is_file():
            raise RuntimeError('Matching Rust local-masks worker is not installed')
        self.deadline = time.monotonic()+TIMEOUT
        self.process = subprocess.Popen([str(path)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        os.set_blocking(self.process.stdin.fileno(), False)
        os.set_blocking(self.process.stdout.fileno(), False)
        os.set_blocking(self.process.stderr.fileno(), False)

    def _failure(self):
        try:
            detail = os.read(self.process.stderr.fileno(), 512).decode(errors='replace').strip()
        except BlockingIOError:
            detail = ''
        return RuntimeError('Local mask worker failed'+(': '+detail if detail else ' or returned truncated output'))

    def _wait(self, stream, write=False):
        remaining = self.deadline-time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Local mask raster exceeded its execution deadline')
        ready = select.select([] if write else [stream], [stream] if write else [], [], remaining)
        if not ready[0] and not ready[1]:
            raise TimeoutError('Local mask raster exceeded its execution deadline')

    def transact(self, packet, count):
        stream = self.process.stdin
        for block in (struct.pack('<I', len(packet)), packet):
            data = memoryview(block)
            while data:
                self._wait(stream, write=True)
                try:
                    n = os.write(stream.fileno(), data[:65536])
                except BlockingIOError:
                    continue
                except BrokenPipeError as error:
                    raise self._failure() from error
                if n == 0:
                    raise RuntimeError('Local mask worker closed its input')
                data = data[n:]
        result = bytearray()
        while len(result) < count+4:
            self._wait(self.process.stdout)
            try:
                block = os.read(self.process.stdout.fileno(), min(65536, count+4-len(result)))
            except BlockingIOError:
                continue
            if not block:
                raise self._failure()
            result.extend(block)
        if struct.unpack_from('<I', result)[0] != count:
            raise ValueError('Local mask worker response contract mismatch')
        return memoryview(result)[4:]

    def close(self, success=False):
        if success:
            self.process.stdin.close()
            try:
                code = self.process.wait(timeout=max(.01, self.deadline-time.monotonic()))
                if code:
                    raise self._failure()
                if os.read(self.process.stdout.fileno(), 1):
                    raise ValueError('Local mask worker returned trailing output')
            finally:
                if self.process.poll() is None:
                    self.process.kill()
                    self.process.wait()
                self.process.stdout.close()
                self.process.stderr.close()
        else:
            self.process.kill()
            self.process.wait()
            self.process.stdin.close()
            self.process.stdout.close()
            self.process.stderr.close()


def _field(value, shape, channels, label):
    # Do not coerce an entire GPU tensor or float64 image into a transport copy.
    expected = (*shape, channels) if channels != 1 else tuple(shape)
    if not isinstance(value, np.ndarray) or value.shape != expected:
        raise MaskUnavailable(f'{label} is unavailable in the immutable source domain')
    if value.dtype.kind != 'f' and not (channels == 3 and value.dtype in (np.dtype('uint8'), np.dtype('uint16'))):
        raise ValueError(f'{label} requires floating-point source values')
    return value


def raster(stack, shape, rgb=None, semantic=None):
    """Render retained objects at exactly shape=(height,width), via tiled Rust.

    RGB is H×W×3 float encoded-sRGB or unsigned 8/16-bit encoded-sRGB; integer
    normalization copies only one bounded tile. Semantic is {channel: H×W float
    [0,1]}. Disabled operands need no data. Missing active dependencies raise
    MaskUnavailable before raster allocation. No fallback can broaden a mask.
    """
    stack, shape = check_stack(stack), _shape(shape)
    plan = validate_budget(stack, shape)
    needs_rgb, channels = dependencies(stack)
    if len(channels) > 16:
        raise ValueError('Local mask stack exceeds the semantic channel budget')
    if needs_rgb:
        rgb = _field(rgb, shape, 3, 'Immutable source RGB')
    fields = []
    for channel in channels:
        value = semantic.get(channel) if isinstance(semantic, dict) else None
        fields.append(_field(value, shape, 1, f'Semantic channel {channel}'))
    objects = [o for o in stack['objects'] if o['enabled']]
    output = np.zeros(shape, np.uint8)
    if not objects:
        return output
    body = _objects_packet(objects, shape, channels)
    worker = _Worker()
    success = False
    try:
        for tile in _tiles(shape, plan['radius']):
            x, y, w, h, cx, cy, cw, ch = tile
            packet = bytearray(b'LMR1')
            packet += struct.pack('<13I', shape[1], shape[0], *tile, len(objects), int(needs_rgb), len(channels))
            packet += body
            if needs_rgb:
                samples = np.asarray(rgb[y:y+h, x:x+w], dtype='<f4')
                if rgb.dtype.kind == 'u':
                    samples = samples / float(np.iinfo(rgb.dtype).max)
                packet += samples.tobytes(order='C')
            for field in fields:
                packet += np.asarray(field[y:y+h, x:x+w], dtype='<f4').tobytes(order='C')
            if len(packet) > MAX_PACKET_BYTES:
                raise ValueError('Local mask transport exceeds the bounded tile budget')
            data = worker.transact(packet, cw*ch)
            output[y+cy:y+cy+ch, x+cx:x+cx+cw] = np.frombuffer(data, np.uint8).reshape(ch, cw)
        success = True
    finally:
        worker.close(success)
    return output
