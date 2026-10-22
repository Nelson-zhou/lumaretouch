"""Physical print layout contract. Values in the request's explicit display unit."""
from __future__ import annotations
import math

LAYOUT_ITEM = "layout://pages"
UNITS = {"mm": 1.0, "cm": 10.0, "in": 25.4}
FIELDS = {"enabled", "mode", "unit", "paperWidth", "paperHeight", "orientation", "dpi",
          "rows", "columns", "marginTop", "marginBottom", "marginLeft", "marginRight",
          "gapX", "gapY", "photoWidth", "photoHeight", "copies", "fit"}


def normalize(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - FIELDS:
        raise ValueError("排版参数有未知字段或不是对象")
    if not isinstance(value.get("enabled"), bool):
        raise ValueError("排版 enabled 必须为布尔值")
    if not value["enabled"]:
        return None
    result = dict(value)
    for key, options in (("mode", ("ordinary", "id")), ("unit", UNITS),
                         ("orientation", ("portrait", "landscape")), ("fit", ("contain", "cover"))):
        if result.get(key) not in options:
            raise ValueError(f"排版 {key} 非法")
    for key in ("paperWidth", "paperHeight", "marginTop", "marginBottom", "marginLeft",
                "marginRight", "gapX", "gapY", "photoWidth", "photoHeight"):
        v = result.get(key)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
            raise ValueError(f"排版 {key} 必须是非负有限数")
    for key, maximum in (("rows", 40), ("columns", 40), ("copies", 100), ("dpi", 1200)):
        v = result.get(key)
        if type(v) is not int or not 1 <= v <= maximum:
            raise ValueError(f"排版 {key} 必须为 1–{maximum} 的整数")
    if result["dpi"] < 72:
        raise ValueError("排版分辨率不能低于 72 DPI")
    geometry(result)
    return result


def geometry(spec):
    mm = UNITS[spec["unit"]]
    short, long = sorted((spec["paperWidth"] * mm, spec["paperHeight"] * mm))
    w, h = (short, long) if spec["orientation"] == "portrait" else (long, short)
    if short < 25 or long > 1000:
        raise ValueError("纸张边长必须在 25–1000 mm 之间")
    left, right, top, bottom = [spec[k] * mm for k in ("marginLeft", "marginRight", "marginTop", "marginBottom")]
    gx, gy = spec["gapX"] * mm, spec["gapY"] * mm
    rows, cols = spec["rows"], spec["columns"]
    cw = (w - left - right - gx * (cols - 1)) / cols
    ch = (h - top - bottom - gy * (rows - 1)) / rows
    if spec["mode"] == "id":
        pw, ph = spec["photoWidth"] * mm, spec["photoHeight"] * mm
        if pw <= 0 or ph <= 0 or pw > cw or ph > ch:
            raise ValueError("证件照尺寸/行列/间隔超出纸张可用区域，请调整排版")
        cw, ch = pw, ph
    if min(cw, ch) < 1:
        raise ValueError("边距/间隔/行列使照片单元小于 1 mm")
    px = lambda x: round(x * spec["dpi"] / 25.4)
    width, height = px(w), px(h)
    if width * height > 60_000_000:
        raise ValueError("单页超过 6000 万像素，请降低 DPI 或纸张尺寸")
    cells = []
    for row in range(rows):
        for col in range(cols):
            x, y = left + col * (cw + gx), top + row * (ch + gy)
            cells.append((px(x), px(y), px(x + cw), px(y + ch)))
    return {"width_mm": w, "height_mm": h, "width_px": width, "height_px": height,
            "dpi": spec["dpi"], "cells": cells}
