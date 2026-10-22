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


def neutral_transfer_options():
    return {**default_options(), "reference_k": 6500.0}


def check_transfer_params(params):
    """Omission remains omission; an explicit neutral object is a different recipe."""
    if not isinstance(params, dict) or set(params) - {"temperature_shift", "tint_shift", "options"}:
        raise ValueError("Invalid WB transfer parameters")
    shift = math_bridge._number(params.get("temperature_shift", 0.0))
    tint = math_bridge._number(params.get("tint_shift", 0.0))
    if abs(shift) > 2000 or abs(tint) > 1:
        raise ValueError("WB transfer shifts outside range")
    out = {"temperature_shift": shift, "tint_shift": tint}
    if "options" in params:
        raw = params["options"]
        if not isinstance(raw, dict) or set(raw) != {"version", "algorithm", "picked_gains", "reference_k"}:
            raise ValueError("Complete WB transfer options required")
        options = check_options({k: v for k, v in raw.items() if k != "reference_k"})
        reference = math_bridge._number(raw["reference_k"])
        check_reference(options, reference, shift)
        out["options"] = {**options, "reference_k": reference}
    return out


def check_reference(options, reference, shift):
    if not 1000 <= reference <= 40000:
        raise ValueError("WB reference outside 1000–40000 K")
    if options["algorithm"] == CORRECTED and not (4000 <= reference <= 25000 and 4000 <= reference + shift <= 25000):
        raise ValueError("Corrected WB whites outside 4000–25000 K")


def normalize_state(state, *, required=False):
    """Pure validation/copy before persistence or workspace changes; never invokes Rust."""
    if not isinstance(state, dict):
        raise ValueError("WB document state must be an object")
    if required and "_wb_options" not in state:
        raise ValueError("Versioned project recipe is missing WB options")
    options = check_options(state["_wb_options"]) if "_wb_options" in state else default_options()
    exposure = state.get("_exposure", (0.0,) * 7)
    if not isinstance(exposure, (list, tuple)) or len(exposure) not in (3, 7):
        raise ValueError("Exposure recipe requires three legacy or seven current scalars")
    values = tuple(math_bridge._number(x) for x in exposure)
    if abs(values[1]) > 2000 or abs(values[2]) > 1:
        raise ValueError("WB document shifts outside range")
    raw_reference = state.get("_exposure_ref_k")
    reference = 6500.0 if raw_reference is None else math_bridge._number(raw_reference)
    check_reference(options, reference, values[1])
    return {**state, "_wb_options": options}


def transfer_from_state(state):
    state = normalize_state(state)
    exposure = state.get("_exposure", (0.0,) * 7)
    reference = state.get("_exposure_ref_k")
    return {"temperature_shift": float(exposure[1]), "tint_shift": float(exposure[2]),
            "options": {**state["_wb_options"], "reference_k": 6500.0 if reference is None else float(reference)}}


def apply_transfer(state, params):
    clean = check_transfer_params(params)
    exposure = list(state["_exposure"])
    exposure += [0.0] * (7 - len(exposure))
    exposure[1:3] = [clean["temperature_shift"], clean["tint_shift"]]
    updates = {"_exposure": tuple(exposure), "_wb_options": default_options()}
    if "options" in clean:
        updates["_wb_options"] = {k: v for k, v in clean["options"].items() if k != "reference_k"}
        updates["_exposure_ref_k"] = clean["options"]["reference_k"]
    # Omitted options deliberately preserve the target's reference, not 6500 K.
    state.update(updates)


def has_picks(options):
    return check_options(options)["picked_gains"] != [1.0, 1.0, 1.0]


def prepare_state(state):
    state = normalize_state(state)
    options = state["_wb_options"]
    values = tuple(state.get("_exposure", (0.0,) * 7))
    # Old neutral documents could carry a reference outside the daylight domain.
    # They never invoked legacy wb_gains; preserve that inactive-path behavior.
    if options["algorithm"] == LEGACY and all(x == 0 for x in values) and not has_picks(options):
        return None
    reference = state.get("_exposure_ref_k")
    gains = compile_gains(options, 6500.0 if reference is None else reference, values[1], values[2])
    from .ops.exposure import ev_gain
    math_bridge._vector(tuple(g * ev_gain(values[0]) for g in gains))
    return gains
