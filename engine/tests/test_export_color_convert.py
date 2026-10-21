"""P1-3（F03）：导出到一个"与 sRGB 不同"的输出档时，必须真的把像素转过去，不是只贴标签。

缺陷：write_file 过去只 kw["icc_profile"]=icc 嵌档、不动像素。工作空间经核实是 sRGB，
于是把 sRGB 数值贴上一个别的档（如 AdobeRGB）名 → 色管读者按错空间解释同一批字节，颜色真的飘。

这里全 CPU（Pillow/littleCMS 是 CPU 绑定，不碰 torch/GPU）。用系统里的一份 AdobeRGB1998.icc
做"真不同档"的转换判据——只在它存在时判像素确实变了；缺它则仍判恒等/身份分支与审计字段成立。
"""
from __future__ import annotations

import os

import numpy as np
import pytest

from lumaretouch_engine.export import (
    RENDERING_INTENT_DEFAULT, _convert_srgb_to_profile, _srgb_bytes, write_file,
)

ADOBE = next((p for p in ("/usr/share/color/icc/colord/AdobeRGB1998.icc",
    "/usr/share/color/icc/compatibleWithAdobeRGB1998.icc") if os.path.isfile(p)), "")
need_adobe = pytest.mark.skipif(not os.path.isfile(ADOBE), reason="系统没有 AdobeRGB1998.icc 样本档")


def _saturated():
    # 一块高饱和红 + 一块纯绿 + 中性灰：sRGB 数值明确、转到 AdobeRGB 应有可见变化
    a = np.zeros((8, 8, 3), np.uint8)
    a[0:4, :, :] = (230, 30, 40)
    a[4:8, :, :] = (40, 200, 60)
    return a


def test_identity_when_target_is_srgb():
    """output_profile=srgb → 恒等：原样返回、不引入一次舍入、意图报 srgb_identity。"""
    from PIL import Image
    img = Image.fromarray(_saturated(), "RGB")
    out, intent = _convert_srgb_to_profile(img, _srgb_bytes())
    assert intent == "srgb_identity"
    assert np.array_equal(np.asarray(out), np.asarray(img))


def test_write_file_srgb_default_marks_not_converted(tmp_path):
    """默认 srgb 导出：color_converted=False，逐字节仍是恒等（改动不伤常见路径）。"""
    p = str(tmp_path / "out.png")
    info = write_file(_saturated(), p, output_profile="srgb")
    assert info["color_converted"] is False
    assert info["color_intent"] == "srgb_identity"
    from PIL import Image
    assert np.array_equal(np.asarray(Image.open(p).convert("RGB")), _saturated())


def test_write_file_no_profile_marks_not_converted(tmp_path):
    p = str(tmp_path / "out2.png")
    info = write_file(_saturated(), p, output_profile="none")
    assert info["color_converted"] is False


@need_adobe
def test_write_file_to_other_gamut_actually_transforms(tmp_path):
    """转到 AdobeRGB：像素必须真的变了（不是把 sRGB 字节贴个 AdobeRGB 名），并如实上报转色。"""
    from PIL import Image
    srgb_png = str(tmp_path / "s.png")
    adobe_png = str(tmp_path / "a.png")
    i_srgb = write_file(_saturated(), srgb_png, output_profile="srgb")
    i_adobe = write_file(_saturated(), adobe_png, output_profile=ADOBE)

    assert i_adobe["color_converted"] is True
    assert i_adobe["color_intent"] == RENDERING_INTENT_DEFAULT
    # 嵌的档确实换成了 AdobeRGB（与内置 sRGB 档不同）
    assert i_adobe["icc_bytes"] != i_srgb["icc_bytes"]

    px_srgb = np.asarray(Image.open(srgb_png).convert("RGB"), dtype=np.int16)
    px_adobe = np.asarray(Image.open(adobe_png).convert("RGB"), dtype=np.int16)
    # 同一块饱和区，转档后字节必须不同（证明真做了 profileToProfile，而不是只改标签）
    assert np.abs(px_srgb - px_adobe).max() > 0, "转到不同档却没有改像素：仍是只贴标签（F03）"

    # 相对色度保中性：一块 r==g==b 的灰经转换仍应 r'≈g'≈b'（不产生假色偏）
    gray = np.full((4, 4, 3), 128, np.uint8)
    gpng = str(tmp_path / "g.png")
    write_file(gray, gpng, output_profile=ADOBE)
    gp = np.asarray(Image.open(gpng).convert("RGB"), dtype=np.int16)
    assert int(np.abs(gp[..., 0] - gp[..., 1]).max()) <= 2
    assert int(np.abs(gp[..., 1] - gp[..., 2]).max()) <= 2


@need_adobe
def test_every_known_intent_is_plumbed_through_littlecms(tmp_path):
    """四种意图都要真的传到 littleCMS 建成变换并返回同尺寸图（不是只存个字符串）。
    同白点的 RGB→RGB 下相对/绝对可能数值相同，那是正确的 littleCMS 行为，
    本例只钉"每条意图分支都跑通、标签如实"。"""
    from PIL import Image
    from lumaretouch_engine.export import _INTENT_CODES
    img = Image.fromarray(_saturated(), "RGB")
    adobe = open(ADOBE, "rb").read()
    for it in _INTENT_CODES:
        out, applied = _convert_srgb_to_profile(img, adobe, intent=it)
        assert applied == it
        assert out.size == img.size and out.mode == "RGB"
        assert np.asarray(out).shape == (8, 8, 3)


def test_unknown_intent_raises():
    from PIL import Image
    img = Image.fromarray(_saturated(), "RGB")
    with pytest.raises(Exception):
        _convert_srgb_to_profile(img, open(ADOBE, "rb").read() if os.path.isfile(ADOBE) else b"\x00" * 132,
                                 intent="banana")


@need_adobe
def test_output_profile_source_converts_working_pixels(tmp_path):
    """Input decoding normalizes to sRGB, so source is an output target too."""
    from PIL import Image
    adobe = open(ADOBE, "rb").read()
    src_png = str(tmp_path / "src.png")
    expected, _ = _convert_srgb_to_profile(Image.fromarray(_saturated()), adobe)
    info = write_file(_saturated(), src_png, output_profile="source", source_icc=adobe)
    assert info["color_converted"] is True
    assert info["color_intent"] == RENDERING_INTENT_DEFAULT
    assert info["icc_bytes"] == len(adobe)
    assert np.array_equal(np.asarray(Image.open(src_png)), np.asarray(expected))


@need_adobe
def test_webp_export_to_other_gamut_also_converts(tmp_path):
    """F03 的转色必须覆盖每一个会嵌档的 RGB 光栅格式。webp 也嵌 icc_profile，
    曾因转换护栏只写 jpg/png/tif 而漏了它——那样 webp 会“只贴标签不转色”（F03 残留）。
    本例钉：转到 AdobeRGB 的 webp 必须 color_converted=True。"""
    p = str(tmp_path / "out.webp")
    info = write_file(_saturated(), p, output_profile=ADOBE)
    assert info["color_converted"] is True
    assert info["color_intent"] == RENDERING_INTENT_DEFAULT
