"""P0 首版项①：16-bit TIFF 导入不能静默降为 8-bit，且高位深导出链路要真走得通。

缺陷（当前代码）：
- load_full(want_bits=16) 对所有非 RAW 一律抛，16-bit TIFF 根本进不了 16-bit 导出通路；
- 预览/满幅的 Pillow 支把 16bpc 源直接 np.asarray(dtype=uint8) —— 静默砍掉高 8 位。

修法（本层 CPU 可自证，Pillow/numpy 不碰 GPU）：
- baseline 无压缩 16bpc RGB TIFF 走 _load_16bit_tiff_full 读真实 uint16 像素（复用成对自证过的
  export.read_tiff16），喂给 export_master_16bit 无损往返；
- 读不出真 16-bit 的（8-bit/压缩/非 TIFF）明确拒，而不是退回归 8-bit；
- 预览把高位深源降到 8-bit 显示时，src_bits + notes 显式标注，不再是静默降位。

这里全 CPU：write_tiff16 / read_tiff16 / load_full / export_master_16bit 都是纯 numpy+Pillow，
不起 EngineProcess、不碰 torch。端到端“编辑算子在 16-bit 上真算”属全链路后续、需 GPU 窗口。
"""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from lumaretouch_engine import decode as D
from lumaretouch_engine.export import write_tiff16, export_master_16bit


def _rich16(h=40, w=48):
    """造一张每通道都有高 8 位 + 低 8 位变化的 uint16 图（防左移补零冒充）。"""
    v = (np.arange(h * w * 3, dtype=np.uint32) * 257 + 3) % 65536
    return v.astype(np.uint16).reshape(h, w, 3)


def test_load_full_16bit_returns_true_uint16_without_leftshift(tmp_path):
    p = str(tmp_path / "in16.tif")
    arr = _rich16()
    write_tiff16(arr, p, output_profile="none")

    d = D.load_full(p, want_bits=16)
    assert d.rgb.dtype == np.uint16, "16-bit 导入解出来不是 uint16：被降位了"
    assert np.array_equal(d.rgb, arr), "读回的像素与写入的不是逐字节一致"
    # 关键反假 16-bit 判据：低 8 位不是全 0（8-bit 左移 8 位补零会得到低字节全 0）
    assert int(np.count_nonzero(d.rgb & 0xFF)) > 0, "低位全 0：这是 8-bit 左移补零的假 16-bit"
    assert d.src_bits == 16
    assert (d.raw or {}).get("source") == "tiff16"
    assert any("未降位" in n for n in d.notes)


def test_export_master_16bit_roundtrips_tiff_losslessly(tmp_path):
    """16-bit TIFF 现在能喂进 16-bit 母档导出并逐字节往返自证（旧代码这里直接抛）。"""
    src = str(tmp_path / "in16.tif")
    out = str(tmp_path / "master.tif")
    arr = _rich16()
    write_tiff16(arr, src, output_profile="none")

    info = export_master_16bit(src, out, output_profile="none")
    assert info["bits"] == 16
    assert info["source"] == "tiff16"
    assert info["readback_max_diff"] == 0, "16-bit 往返不是无损"
    assert info["low8_nonzero_px"] > 0, "往返产物低位全 0：中途被降成 8-bit"
    # 每通道取值档数应远超 256（真 16-bit 内容，不是 8-bit 撑的位数）
    assert all(int(x) > 256 for x in info["levels_per_channel"]), info["levels_per_channel"]


def test_preview_16bit_source_is_not_silently_downconverted(tmp_path):
    """预览代理仍按架构是 8-bit，但必须把“16-bit 源被降到 8-bit 显示”显式报出来。"""
    p = str(tmp_path / "in16.tif")
    write_tiff16(_rich16(h=120, w=160), p, output_profile="none")

    d = D.load_rgb(p)                      # 预览路径
    assert d.rgb.dtype == np.uint8         # 8-bit 代理本身没错
    assert d.src_bits == 16, "源位深没报出来：仍是静默降位（P0 项①）"
    assert d.meta()["src_bits"] == 16
    assert any("非静默降位" in n for n in d.notes), d.notes


def test_load_full_16bit_refuses_8bit_tiff(tmp_path):
    """8-bit TIFF 不能被悄悄当 16-bit：要么读真 16-bit，要么明确拒，绝不左移补零。"""
    p = str(tmp_path / "in8.tif")
    Image.fromarray((np.arange(24 * 32 * 3).reshape(24, 32, 3) % 256).astype(np.uint8),
                    "RGB").save(p, format="TIFF")
    with pytest.raises(ValueError) as e:
        D.load_full(p, want_bits=16)
    assert "16-bit" in str(e.value)


def test_load_full_16bit_refuses_jpeg_and_png(tmp_path):
    for name in ("a.jpg", "a.png"):
        p = str(tmp_path / name)
        Image.fromarray(np.zeros((8, 8, 3), np.uint8), "RGB").save(p)
        with pytest.raises(ValueError):
            D.load_full(p, want_bits=16)


def test_src_bits_default_8_for_plain_jpeg(tmp_path):
    p = str(tmp_path / "plain.jpg")
    Image.fromarray((np.full((16, 16, 3), 128, np.uint8)), "RGB").save(p)
    assert D.load_rgb(p).src_bits == 8


@pytest.mark.parametrize("orientation", range(1, 9))
def test_full16_normalizes_orientation_without_quantizing(tmp_path, orientation):
    """Use independent Pillow transpose semantics to check all TIFF orientations."""
    import struct
    p = tmp_path / "oriented.tif"
    arr = _rich16(h=4, w=7)
    write_tiff16(arr, str(p), output_profile="none")
    data = bytearray(p.read_bytes())
    old_ifd = struct.unpack_from("<I", data, 4)[0]
    count = struct.unpack_from("<H", data, old_ifd)[0]
    entries = [bytes(data[old_ifd+2+i*12:old_ifd+14+i*12]) for i in range(count)]
    entries.append(struct.pack("<HHIHH", 274, 3, 1, orientation, 0))
    entries.sort(key=lambda e: struct.unpack_from("<H", e)[0])
    new_ifd = len(data)
    data.extend(struct.pack("<H", len(entries)) + b"".join(entries) + b"\0"*4)
    struct.pack_into("<I", data, 4, new_ifd)
    p.write_bytes(data)
    transpose = {2: Image.Transpose.FLIP_LEFT_RIGHT, 3: Image.Transpose.ROTATE_180,
                 4: Image.Transpose.FLIP_TOP_BOTTOM, 5: Image.Transpose.TRANSPOSE,
                 6: Image.Transpose.ROTATE_270, 7: Image.Transpose.TRANSVERSE,
                 8: Image.Transpose.ROTATE_90}
    planes = [Image.fromarray(arr[:, :, c]) for c in range(3)]
    expected = np.stack([np.asarray(im.transpose(transpose[orientation])
                       if orientation != 1 else im) for im in planes], axis=-1)
    got = D.load_full(str(p), want_bits=16)
    assert got.rgb.dtype == np.uint16
    assert np.array_equal(got.rgb, expected)
    assert (got.src_w, got.src_h) == (expected.shape[1], expected.shape[0])


def test_full16_keeps_embedded_source_profile(tmp_path):
    from PIL import ImageCms
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    path = str(tmp_path / "profile16.tif")
    write_tiff16(_rich16(), path, output_profile="source", source_icc=profile)
    assert D.load_full(path, want_bits=16).source_icc == profile
