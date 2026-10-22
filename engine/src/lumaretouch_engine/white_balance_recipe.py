"""Versioned WB options and recipe-time gain compilation, without live state ownership."""
from . import white_balance_math as math_bridge

LEGACY = "legacy-xyz-ratio-v1"
CORRECTED = "linear-srgb-d-white-ratio-v1"


def default_options(algorithm=LEGACY):
    return check_options({"version": 1, "algorithm": algorithm, "picked_gains": [1.0, 1.0, 1.0]})


def check_options(value):
    if not isinstance(value, dict) or set(value) != {"version", "algorithm", "picked_gains"}:
        raise ValueError("WB options require exactly version, algorithm and picked_gains")
    if type(value["version"]) is not int or value["version"] != 1:
        raise ValueError("Unsupported WB options version")
    if not isinstance(value["algorithm"], str) or value["algorithm"] not in (LEGACY, CORRECTED):
        raise ValueError("Unsupported WB algorithm")
    return {"version": 1, "algorithm": value["algorithm"],
            "picked_gains": list(math_bridge._vector(value["picked_gains"]))}


def compile_gains(options, reference, shift, tint):
    """Compile before installing state. Legacy calculations keep their original implementation."""
    checked = check_options(options)
    reference, shift, tint = (math_bridge._number(x) for x in (reference, shift, tint))
    if checked["algorithm"] == LEGACY:
        from .ops.exposure import wb_gains
        manual = wb_gains(shift, tint, reference)
    else:
        manual = math_bridge.manual_gains(reference, shift, tint)
    return math_bridge._vector(tuple(float(manual[i]) * checked["picked_gains"][i] for i in range(3)))
