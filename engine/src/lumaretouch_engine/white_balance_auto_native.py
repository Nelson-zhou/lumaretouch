"""Independent fixed-size Rust statistical ABI. No Python estimator/fallback."""
from functools import lru_cache
import json
from pathlib import Path
import struct
import subprocess
from .white_balance_math import _number, _vector

POLICY = 'stratified-trimmed-log-gray-world-v1'
SAMPLES = 1024
BYTES = 40 + SAMPLES * 40


def helper_path():
    return Path(__file__).resolve().parent / 'bin' / 'white-balance-auto'


@lru_cache(maxsize=1)
def available():
    helper = helper_path()
    if not helper.is_file():
        return False
    try:
        result = subprocess.run([str(helper), '--protocol'], capture_output=True, timeout=2, check=False)
        return result.returncode == 0 and result.stdout == f'white-balance-auto-v1:{POLICY}\n'.encode('ascii')
    except (OSError, subprocess.SubprocessError):
        return False


def calculate(rows, manual):
    if not available():
        raise ValueError('自动白平衡 Rust 核心未安装或版本不匹配；不会用吸管或旧算法冒充自动估计')
    if not isinstance(rows, (list, tuple)) or len(rows) != SAMPLES:
        raise ValueError('Auto WB requires the fixed 32×32 stratified grid')
    manual = _vector(manual)
    payload = bytearray(struct.pack('<8sII3d', b'LRTAWB01', SAMPLES, 0, *manual))
    for row in rows:
        if not isinstance(row, (tuple, list)) or len(row) != 5:
            raise ValueError('Auto WB sample must have linear RGB, coverage and risk')
        payload.extend(struct.pack('<5d', *(_number(value) for value in row)))
    if len(payload) != BYTES:
        raise ValueError('Invalid bounded auto WB payload')
    result = subprocess.run([str(helper_path())], input=payload, capture_output=True, timeout=3, check=False)
    if result.returncode:
        raise ValueError('自动白平衡未提交：有效取样不足、空间统计不稳定或增益超限；' + result.stderr[:512].decode('utf-8', 'replace'))
    if len(result.stdout) > 2048:
        raise ValueError('Oversized auto WB reply')
    try:
        data = json.loads(result.stdout)
    except (ValueError, TypeError) as error:
        raise ValueError('Invalid auto WB reply') from error
    if (type(data) is not dict or set(data) != {'version', 'policy', 'samples', 'accepted', 'stable_tiles', 'spread', 'illuminant', 'gains'}
            or type(data['version']) is not int or data['version'] != 1 or data['policy'] != POLICY
            or type(data['samples']) is not int or data['samples'] != SAMPLES
            or type(data['accepted']) is not int or not 512 <= data['accepted'] <= SAMPLES
            or type(data['stable_tiles']) is not int or not 12 <= data['stable_tiles'] <= 16):
        raise ValueError('Unsupported auto WB reply')
    gains, illuminant = _vector(data['gains']), _vector(data['illuminant'])
    spread = _number(data['spread'])
    if not 0 <= spread <= 0.60 or any(not 0.25 <= gains[i] <= 4 or not 0.25 <= gains[i]*manual[i] <= 4 for i in range(3)):
        raise ValueError('Auto WB reply exceeds gain/stability policy')
    return {'gains': list(gains), 'diagnostic': {
        'origin': 'classic-statistical-estimate', 'policy': POLICY, 'domain': 'pre-wb-linear-working-srgb',
        'samples': SAMPLES, 'accepted': data['accepted'], 'stable_tiles': data['stable_tiles'],
        'spread': spread, 'illuminant': list(illuminant), 'quality': 'current-proxy-stratified',
    }}
