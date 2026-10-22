"""Bounded small-region ABI to Rust; never transmit a whole image or cache samples."""
from dataclasses import dataclass
import json
import subprocess
from . import white_balance_math as M

POLICY = 'proxy-linear-neutral-v1'
MAX_SAMPLES = 121


@dataclass(frozen=True)
class Pick:
    mean_linear: tuple[float, float, float]
    gains: tuple[float, float, float]
    samples: int
    policy: str = POLICY


def calculate(rows, manual):
    if not isinstance(rows, (list, tuple)) or not 1 <= len(rows) <= MAX_SAMPLES:
        raise ValueError('WB picker requires 1–121 samples')
    manual = M._vector(manual)
    clean = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != 5:
            raise ValueError('WB sample requires linear RGB, coverage and source risk')
        clean.extend(M._number(value) for value in row)
    payload = 'white-balance-pick-v1 ' + POLICY + ' ' + ' '.join(map(repr, manual))
    payload += ' ' + str(len(rows)) + ' ' + ' '.join(map(repr, clean))
    if len(payload.encode('ascii')) > 16384:
        raise ValueError('WB sample request exceeds 16 KiB')
    helper = M._helper_path()
    if not helper.is_file():
        raise RuntimeError('Matching Rust picker helper missing; rebuild/install the engine package')
    result = subprocess.run([str(helper)], input=payload, text=True, capture_output=True, timeout=3, check=False)
    if result.returncode:
        raise ValueError('Rust WB picker rejected sample: ' + result.stderr[:512])
    if len(result.stdout) > 1024:
        raise ValueError('Oversized Rust picker reply')
    try:
        data = json.loads(result.stdout)
    except (ValueError, TypeError) as error:
        raise ValueError('Invalid Rust picker reply') from error
    if (type(data) is not dict or set(data) != {'version','policy','samples','mean_linear','gains'}
            or type(data['version']) is not int or data['version'] != 1 or data['policy'] != POLICY
            or type(data['samples']) is not int or data['samples'] != len(rows)):
        raise ValueError('Unsupported Rust picker reply')
    mean, gains = M._vector(data['mean_linear']), M._vector(data['gains'])
    if any(value > 1 for value in mean):
        raise ValueError('Invalid Rust picker mean')
    return Pick(mean, gains, data['samples'])
