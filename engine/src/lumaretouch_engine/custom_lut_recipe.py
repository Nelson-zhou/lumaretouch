"""Single portable recipe for history, project, preset, batch and export snapshots."""
from __future__ import annotations
import math
from .custom_lut_library import digest_id


def validate(value):
    if value is None: return None
    if not isinstance(value, dict) or set(value) != {"schema", "asset_id", "amount", "space", "interpolation", "out_of_domain"}:
        raise ValueError("自定义 LUT 配方字段无效")
    if type(value["schema"]) is not int or value["schema"] != 1 or value["space"] != "srgb-encoded" or value["interpolation"] != "linear" or value["out_of_domain"] != "clamp-coordinate":
        raise ValueError("不支持的自定义 LUT 配方语义")
    a = value["amount"]
    if isinstance(a, bool) or not isinstance(a, (int, float)) or not math.isfinite(a) or not 0 <= a <= 1:
        raise ValueError("LUT 强度必须为 0–1")
    return dict(value, asset_id=digest_id(value["asset_id"]), amount=float(a))


def make(ident, amount=1.):
    return validate(dict(schema=1, asset_id=ident, amount=amount, space="srgb-encoded", interpolation="linear", out_of_domain="clamp-coordinate"))


def pack(recipe, library):
    recipe = validate(recipe)
    return {"recipe": recipe, "asset": library.portable(recipe["asset_id"]) if recipe else None}


def unpack(payload, library, cancelled=lambda: False):
    if not isinstance(payload, dict) or set(payload) != {"recipe", "asset"}: raise ValueError("自定义 LUT 包字段无效")
    recipe = validate(payload["recipe"])
    if recipe is None:
        if payload["asset"] is not None: raise ValueError("未使用的 LUT 资源")
        return None
    asset = payload["asset"]
    if not isinstance(asset, dict) or asset.get("sha256") != recipe["asset_id"]: raise ValueError("LUT 配方与资源不匹配")
    library.restore(asset, cancelled)
    return recipe
