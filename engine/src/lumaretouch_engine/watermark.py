"""Frozen, orientation-specific delivery marks. Photo pixels never enter Pillow.

Pillow rasterizes only the mark; compositing uses linear-light float32 in its ROI.
Source: frozen workflow 32483 / handbook section 导出与水印. Asset bytes belong to
submission snapshots, so editing/removing a logo cannot change a running batch.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import io
import math
from pathlib import Path

import numpy as np

ORIENTATIONS = ("landscape", "portrait", "square")
POSITIONS = ("top-left", "top-center", "top-right", "middle-left", "middle-center",
             "middle-right", "bottom-left", "bottom-center", "bottom-right")
MAX_ASSET_BYTES = 8 * 1024 * 1024
MAX_MARK_PIXELS = 16_000_000


def _number(p, key, default, lo, hi):
    value = p.get(key, default)
    if isinstance(value, bool):
        raise ValueError(f"水印 {key} 必须是数字")
    value = float(value)
    if not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError(f"水印 {key} 必须在 {lo}–{hi} 之间")
    return value


def _asset(path, limit=MAX_ASSET_BYTES):
    with open(path, "rb") as stream:
        data = stream.read(limit + 1)
    if not data or len(data) > limit:
        raise ValueError("水印资源为空或超过大小限制（图片 8 MiB，字体 32 MiB）")
    return base64.b64encode(data).decode("ascii")


def _font_path(text):
    candidates = ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                  "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    for path in candidates:
        if Path(path).is_file() and (not any(ord(c) > 255 for c in text) or "CJK" in path):
            return path
    raise ValueError("没有可用的水印字体；请选择支持水印文字的 TTF/OTF/TTC 字体文件")


def freeze_settings(raw):
    """Validate untrusted UI settings and own assets before queue submission."""
    if raw is None:
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("enabled", False), bool):
        raise ValueError("水印设置格式错误")
    if not raw.get("enabled"):
        return None
    if not isinstance(raw.get("alsoClean", False), bool):
        raise ValueError("无水印副本开关必须为布尔值")
    profiles = raw.get("profiles")
    if not isinstance(profiles, dict) or any(key not in profiles for key in ORIENTATIONS):
        raise ValueError("请分别配置横图、竖图、方图水印")
    frozen = {"enabled": True, "alsoClean": raw.get("alsoClean", False), "profiles": {}}
    for name in ORIENTATIONS:
        p = profiles[name]
        if not isinstance(p, dict):
            raise ValueError("水印方向配置格式错误")
        kind, position = p.get("kind", "text"), p.get("position", "bottom-right")
        if kind not in ("text", "image") or position not in POSITIONS:
            raise ValueError("未知水印类型或九宫格位置")
        q = {"kind": kind, "position": position,
             "opacity": _number(p, "opacity", .65, 0, 1),
             "size": _number(p, "size", .25, .01, 1),
             "margin": _number(p, "margin", .03, 0, .45),
             "offsetX": _number(p, "offsetX", 0, -.5, .5),
             "offsetY": _number(p, "offsetY", 0, -.5, .5),
             "rotation": _number(p, "rotation", 0, -180, 180),
             "fit": p.get("fit", True)}
        if not isinstance(q["fit"], bool):
            raise ValueError("水印适合画幅开关必须为布尔值")
        if kind == "text":
            text = p.get("text", "")
            if not isinstance(text, str) or not text.strip() or len(text) > 300:
                raise ValueError("水印文字需要 1–300 个字符")
            color = p.get("color", "#ffffff")
            if not isinstance(color, str) or len(color) != 7 or not color.startswith("#"):
                raise ValueError("水印颜色需要 #RRGGBB")
            try:
                int(color[1:], 16)
            except ValueError:
                raise ValueError("水印颜色需要 #RRGGBB") from None
            font_path = p.get("fontPath") or _font_path(text)
            q.update(text=text, color=color, fontPath=str(font_path), fontData=_asset(font_path, 32 * 1024 * 1024))
            from PIL import ImageFont
            ImageFont.truetype(io.BytesIO(base64.b64decode(q["fontData"])), 32)
        else:
            path = p.get("imagePath", "")
            if not isinstance(path, str) or not path:
                raise ValueError("请选择水印图片")
            data = _asset(path)
            from PIL import Image
            with Image.open(io.BytesIO(base64.b64decode(data))) as image:
                if image.width * image.height > MAX_MARK_PIXELS:
                    raise ValueError("水印图片超过 1600 万像素")
                image.load()
            q.update(imagePath=path, imageData=data)
        asset = q.get("imageData", q.get("fontData"))
        q["assetSha256"] = hashlib.sha256(base64.b64decode(asset)).hexdigest()
        frozen["profiles"][name] = q
    return frozen


def public_settings(frozen):
    """Task/event metadata omits embedded asset payloads; retry retains the original."""
    if frozen is None:
        return None
    out = copy.deepcopy(frozen)
    for p in out["profiles"].values():
        p.pop("imageData", None)
        p.pop("fontData", None)
    return out


def _mark(p, width, canvas):
    from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageCms
    if p["kind"] == "image":
        with Image.open(io.BytesIO(base64.b64decode(p["imageData"]))) as source:
            mark = ImageOps.exif_transpose(source).convert("RGBA")
            icc = source.info.get("icc_profile")
            if icc:
                alpha = mark.getchannel("A")
                rgb = ImageCms.profileToProfile(mark.convert("RGB"),
                    ImageCms.ImageCmsProfile(io.BytesIO(icc)), ImageCms.createProfile("sRGB"), outputMode="RGB")
                mark = rgb.convert("RGBA")
                mark.putalpha(alpha)
    else:
        font = ImageFont.truetype(io.BytesIO(base64.b64decode(p["fontData"])), 128)
        box = ImageDraw.Draw(Image.new("L", (1, 1))).multiline_textbbox((0, 0), p["text"], font=font)
        size = (max(1, box[2] - box[0] + 8), max(1, box[3] - box[1] + 8))
        if size[0] * size[1] > MAX_MARK_PIXELS:
            raise ValueError("文字水印栅格过大；请缩短文字或减少换行")
        mark = Image.new("RGBA", size)
        ImageDraw.Draw(mark).multiline_text((4-box[0], 4-box[1]), p["text"], font=font, fill=p["color"])
    height = max(1, round(mark.height * width / mark.width))
    angle = math.radians(p["rotation"])
    rotated_w = abs(math.cos(angle))*width + abs(math.sin(angle))*height
    rotated_h = abs(math.sin(angle))*width + abs(math.cos(angle))*height
    if p["fit"]:
        fit = min(1.0, max(1, canvas[0]*(1-2*p["margin"]))/max(1,rotated_w),
                  max(1, canvas[1]*(1-2*p["margin"]))/max(1,rotated_h))
        width, height = max(1, int(width*fit)), max(1, int(height*fit))
        rotated_w, rotated_h = rotated_w*fit, rotated_h*fit
    if max(width * height, rotated_w * rotated_h) > MAX_MARK_PIXELS:
        raise ValueError("水印栅格超过 1600 万像素；请减小水印尺寸或更换宽高比")
    mark = mark.resize((width, height), Image.Resampling.LANCZOS)
    return mark.rotate(-p["rotation"], resample=Image.Resampling.BICUBIC, expand=True)


def composite(rgb, frozen):
    """Return marked copy and audit facts; preserve integer depth and outside ROI."""
    if not frozen:
        return rgb, {"enabled": False}
    if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype not in (np.uint8, np.uint16, np.float32, np.float64):
        raise ValueError("水印需要 RGB8/RGB16 或 [0,1] 浮点 RGB")
    h, w = rgb.shape[:2]
    orientation = "square" if w == h else "landscape" if w > h else "portrait"
    p = frozen["profiles"][orientation]
    mark = _mark(p, max(1, round(w * p["size"])), (w, h))
    mx, my = round(w * p["margin"]), round(h * p["margin"])
    if p["fit"]:
        from PIL import Image
        mark.thumbnail((max(1, w - 2*mx), max(1, h - 2*my)), Image.Resampling.LANCZOS)
    vertical, horizontal = p["position"].split("-")
    x = {"left": mx, "center": (w-mark.width)//2, "right": w-mx-mark.width}[horizontal]
    y = {"top": my, "middle": (h-mark.height)//2, "bottom": h-my-mark.height}[vertical]
    x += round(w * p["offsetX"])
    y += round(h * p["offsetY"])
    x0, y0, x1, y1 = max(0,x), max(0,y), min(w,x+mark.width), min(h,y+mark.height)
    facts = {"enabled": True, "orientation": orientation, "kind": p["kind"],
             "asset_sha256": p["assetSha256"], "opacity": p["opacity"],
             "bounds": [x, y, mark.width, mark.height], "compositing": "linear_srgb_float32"}
    if x0 >= x1 or y0 >= y1:
        raise ValueError("水印完全在画幅外；请调整位置偏移")
    out = rgb.copy()
    rgba = np.asarray(mark.crop((x0-x, y0-y, x1-x, y1-y)), dtype=np.float32) / 255
    a = rgba[...,3:4] * p["opacity"]
    maximum = 65535 if rgb.dtype == np.uint16 else 255 if rgb.dtype == np.uint8 else 1
    photo = rgb[y0:y1,x0:x1].astype(np.float32) / maximum
    def linear(v):
        return np.where(v <= .04045, v/12.92, ((v+.055)/1.055)**2.4)
    mixed = linear(photo) * (1-a) + linear(rgba[...,:3]) * a
    encoded = np.where(mixed <= .0031308, 12.92*mixed, 1.055*np.maximum(mixed,0)**(1/2.4)-.055)
    pixels = np.clip(encoded,0,1) * maximum
    if maximum != 1:
        pixels = np.rint(pixels)
    # Zero alpha is a strict identity, including RGB16 least-significant bits.
    out[y0:y1,x0:x1] = np.where(a > 0, pixels.astype(rgb.dtype), rgb[y0:y1,x0:x1])
    return out, facts
