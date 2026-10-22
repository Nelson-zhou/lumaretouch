"""Bounded scalar ABI to the packaged Rust helper; never sends image tensors.

Call when installing parameters, not from a render loop. Cache entries are
immutable tuples. Missing/mismatched helpers fail closed, with no Python fallback.
"""
from functools import lru_cache
import json
import math
from pathlib import Path
import subprocess


def _number(value):
    if type(value) not in (int, float):
        raise ValueError("WB scalar must be a finite number")
    try:
        value = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError("WB scalar must be finite") from exc
    if not math.isfinite(value):
        raise ValueError("WB scalar must be finite")
    return value


def _vector(value):
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        raise ValueError("WB vector must contain exactly three gains")
    result = tuple(_number(x) for x in value)
    if any(x <= 0 for x in result):
        raise ValueError("WB vector must be positive")
    return result


def _helper_path():
    return Path(__file__).resolve().parent / "bin" / "curve-compiler"


@lru_cache(maxsize=256)
def _request(action, values):
    helper = _helper_path()
    if not helper.is_file():
        raise RuntimeError("Matching Rust math helper missing; rebuild/install the engine package")
    payload = "white-balance-v1 " + action + " " + " ".join(repr(x) for x in values)
    result = subprocess.run([str(helper)], input=payload, text=True, capture_output=True,
                            timeout=3, check=False)
    if result.returncode:
        raise ValueError("Rust WB calculation failed: " + result.stderr[:512])
    if len(result.stdout) > 512:
        raise ValueError("Oversized Rust WB reply")
    try:
        data = json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid Rust WB reply") from exc
    if (not isinstance(data, dict) or set(data) != {"version", "action", "gains"}
            or data["action"] != action
            or type(data["version"]) is not int or data["version"] != 1):
        raise ValueError("Unsupported Rust WB reply")
    return _vector(data["gains"])


def manual_gains(reference, shift, tint):
    values = tuple(_number(x) for x in (reference, shift, tint))
    reference, shift, tint = values
    if not (4000 <= reference <= 25000 and 4000 <= reference + shift <= 25000):
        raise ValueError("Corrected WB requires daylight whites in 4000–25000 K")
    if abs(shift) > 2000 or abs(tint) > 1:
        raise ValueError("WB shift outside range")
    return _request("manual", values)


def neutral_gains(mean_linear, manual):
    return _request("neutral", _vector(mean_linear) + _vector(manual))
