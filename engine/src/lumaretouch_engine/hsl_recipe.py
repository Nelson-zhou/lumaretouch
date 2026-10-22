"""Versioned transfer contract for the existing HSV-based eight-color operator.

This envelope does not change pixel math or migrate document state. Future true
HSL/other algorithms must use a different algorithm identifier, never reinterpret
these 24 legacy values. Project state continues to own just the `_hsl` tuple.
"""
from .ops.hsl import check_hsl

ALGORITHM = "legacy-hsv8-smoothstep-v1"
NEUTRAL = (0.0,) * 24


def default_recipe() -> dict:
    return {"version": 1, "algorithm": ALGORITHM, "bands": list(NEUTRAL)}


def check_recipe(recipe) -> dict:
    if recipe is None:
        return default_recipe()
    if not isinstance(recipe, dict) or set(recipe) != {"version", "algorithm", "bands"}:
        raise ValueError("HSL recipe requires exactly version, algorithm and bands")
    if type(recipe["version"]) is not int or recipe["version"] != 1:
        raise ValueError("Unsupported HSL recipe version")
    if recipe["algorithm"] != ALGORITHM:
        raise ValueError("Unsupported HSL recipe algorithm")
    bands = recipe["bands"]
    if not isinstance(bands, (list, tuple)) or len(bands) != 24:
        raise ValueError("HSL recipe requires exactly 24 band values")
    if any(type(v) not in (int, float) for v in bands):
        raise ValueError("HSL band values must be numbers, not strings or booleans")
    try:
        clean = check_hsl(bands)
    except OverflowError as error:
        raise ValueError("HSL band values exceed finite numeric range") from error
    return {"version": 1, "algorithm": ALGORITHM, "bands": list(clean)}


def normalize_state(bands) -> tuple:
    """Keep legacy padding/coercion, but reject invalid values before live writes."""
    try:
        return check_hsl((tuple(float(v) for v in bands) + NEUTRAL)[:24])
    except (TypeError, OverflowError) as error:
        raise ValueError("Invalid legacy HSL state") from error


def from_state(bands) -> dict:
    return {"version": 1, "algorithm": ALGORITHM, "bands": list(normalize_state(bands))}
