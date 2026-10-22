"""Bounded Rust field transport. RGB stays in the established Torch renderer."""
import os
import select
import struct
import subprocess
import time
from pathlib import Path
import numpy as np
from . import manual_liquify_state as S


def replay(value, shape, *, cancelled=lambda: False):
    value = S.check(value)
    plan = S.validate_budget(value, shape)
    if not value['strokes']:
        return None
    from .cpu_memory_budget import available_estimate
    if plan['bytes'] + 64*1024*1024 > available_estimate():
        raise ValueError('手动液化重放内存预算不足；不会退回放大的代理位移场')
    path = Path(__file__).resolve().parent/'bin'/'manual-liquify'
    if not path.is_file():
        raise RuntimeError('匹配的 Rust manual-liquify 重放程序未安装')
    h, w = shape
    packet = bytearray(b'LQL1') + struct.pack('<III', w, h, len(value['strokes']))
    for s in value['strokes']:
        packet += struct.pack('<BB8dI', S.MODES.index(s['mode']), int(s['fixed_edges']),
                              s['density'], s['pressure'], s['rate'], s['direction'],
                              *s['axes'][0], *s['axes'][1], len(s['points']))
        for point in s['points']:
            packet += struct.pack('<4d', *point)
    if len(packet) > 1024*1024:
        raise ValueError('液化请求超过 1 MiB 传输预算')
    process = subprocess.Popen([str(path)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    for stream in (process.stdin, process.stdout, process.stderr):
        os.set_blocking(stream.fileno(), False)
    deadline = time.monotonic()+120
    def wait(stream, write=False):
        while True:
            if cancelled():
                raise InterruptedError('手动液化重放已取消')
            left = deadline-time.monotonic()
            if left <= 0:
                raise TimeoutError('手动液化重放超时；未更改照片')
            ready = select.select([] if write else [stream], [stream] if write else [], [], min(.1, left))
            if ready[0] or ready[1]: return
    def read(size):
        result = bytearray()
        while len(result) < size:
            wait(process.stdout)
            try: part = os.read(process.stdout.fileno(), min(65536, size-len(result)))
            except BlockingIOError: continue
            if not part:
                try: detail = os.read(process.stderr.fileno(), 2048).decode(errors='replace')
                except BlockingIOError: detail = ''
                raise ValueError('Rust 液化重放失败或数据截断：'+detail)
            result.extend(part)
        return result
    try:
        data = memoryview(struct.pack('<I', len(packet))+packet)
        while data:
            wait(process.stdin, True)
            try: n = os.write(process.stdin.fileno(), data[:65536])
            except BlockingIOError: continue
            if n < 1: raise ValueError('液化工作程序关闭了输入')
            data = data[n:]
        process.stdin.close()
        header = read(12)
        if header[:4] != b'LQF1' or struct.unpack_from('<Q', header, 4)[0] != h*w*12:
            raise ValueError('Rust 液化位移场协议或尺寸不兼容')
        out = np.empty((h, w, 3), np.float32)
        rows = max(1, 1048576//(w*12))
        for y in range(0, h, rows):
            count = min(rows, h-y)
            out[y:y+count] = np.frombuffer(read(count*w*12), '<f4').reshape(count, w, 3)
        while process.poll() is None:
            if cancelled(): raise InterruptedError('手动液化重放已取消')
            if time.monotonic() >= deadline: raise TimeoutError('液化工作程序未正常结束')
            time.sleep(.01)
        if process.returncode or os.read(process.stdout.fileno(), 1):
            raise ValueError('液化重放工作程序返回无效结束状态或多余数据')
        if not np.isfinite(out).all() or np.any(np.abs(out[..., :2]) > 65536) or np.any((out[..., 2] < 0) | (out[..., 2] > 1)):
            raise ValueError('液化重放场含无效数据')
        return out
    finally:
        if process.poll() is None:
            process.kill(); process.wait()
        for stream in (process.stdin, process.stdout, process.stderr):
            if not stream.closed: stream.close()
