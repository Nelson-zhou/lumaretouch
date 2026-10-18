"""M5-a 底片条的库层口径：扫描名单、缩略图上限、通道行宽。

这一层不起引擎也不碰 GPU，跑在 CI 的 CPU job 上。判据全部是"产品事实"那类：
底片条少一张图、缩略图撑爆一行 JSON、格子被竖图撑破行高——用户在用，而日志里看不出来。
所以每一条断言都对着一个具体的错法写。
"""

from __future__ import annotations

import base64
import io
import os

import numpy as np
import pytest
from PIL import Image

from lumaretouch_engine import session as S

FIXTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "tests", "fixtures", "portrait-1024x1280.jpg")


def write_jpg(path: str, *, w: int = 120, h: int = 90, seed: int = 0) -> str:
    """一张真 JPEG（不是同名占位）：内容有低频结构，编码后大小接近真实照片。"""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    a = (np.clip(0.5 + 0.3 * np.sin(xx / 7.0 + seed) + 0.2 * np.cos(yy / 5.0), 0, 1) * 255)
    a = a[..., None].astype(np.uint8)
    a = np.repeat(a, 3, axis=-1)
    a[:, :, 2] = np.clip(a[:, :, 2].astype(np.int16) + rng.integers(-12, 12, (h, w)), 0, 255)
    Image.fromarray(np.ascontiguousarray(a), "RGB").save(path, "JPEG", quality=92)
    return path


def noise_jpg(path: str, edge: int) -> str:
    """一张最坏情况：全画幅随机噪声。JPEG 对它的编码量是照片的十几倍。"""
    rng = np.random.default_rng(7)
    a = rng.integers(0, 256, (edge, edge, 3), dtype=np.uint8)
    Image.fromarray(a, "RGB").save(path, "JPEG", quality=95)
    return path


# ------------------------------------------------------------------------ 扫描
def test_scan_dir_sorts_and_admits_the_whitelist(tmp_path):
    """扫描的名单与 decode 的 RAW 名单同进退：收进来的格子不能少。

    .CR3 从「不收」变成「收」是 M9-c 的口径变更：厂商容器现在由系统 LibRaw 接，把
    它挡在名单外只会让用户以为拍丢了。今天手上还没有真机样本，所以这条只锁
    「名单形状」；能不能真解开由 test_raw 那一节与能力上报说。
    """
    write_jpg(str(tmp_path / "b.jpg"))
    write_jpg(str(tmp_path / "A.jpeg"), seed=1)
    (tmp_path / "note.txt").write_text("不是图")
    (tmp_path / "raw.CR3").write_bytes(b"\x00" * 16)
    (tmp_path / "shot.NEF").write_bytes(b"\x00" * 16)
    (tmp_path / "sub").mkdir()
    got = S.scan_dir(str(tmp_path))
    names = [os.path.basename(x) for x in got["files"]]
    assert names == ["A.jpeg", "b.jpg", "raw.CR3", "shot.NEF"], \
        f"排序不是不区分大小写的稳定序，或 RAW 后缀没进名单：{names}"
    why = {s["name"]: s["why"] for s in got["skipped"]}
    assert "note.txt" in why and "扩展名" in why["note.txt"]
    assert "sub" in why and "目录" in why["sub"]
    assert got["truncated"] is False
    assert got["scan_ms"] >= 0.0


def test_scan_dir_honours_limit_and_reports_truncation(tmp_path):
    for i in range(7):
        write_jpg(str(tmp_path / f"p{i:02d}.jpg"), seed=i)
    got = S.scan_dir(str(tmp_path), limit=4)
    assert len(got["files"]) == 4
    assert got["truncated"] is True, "超限必须说：静默少三张就是底片条少三张"


def test_scan_dir_rejects_non_directory(tmp_path):
    p = write_jpg(str(tmp_path / "x.jpg"))
    with pytest.raises(NotADirectoryError):
        S.scan_dir(p)                              # 是文件不是目录
    with pytest.raises(NotADirectoryError):
        S.scan_dir(str(tmp_path / "没有这个目录"))
    with pytest.raises(ValueError):
        S.scan_dir("")


def test_scan_dir_deduples_by_absolute_path(tmp_path):
    """同一目录里不能有同格重复：重复的一格会把缩略图与状态都指向两份。"""
    p = write_jpg(str(tmp_path / "same.jpg"))
    got = S.scan_dir(str(tmp_path))
    assert len(set(got["files"])) == len(got["files"])
    assert got["files"] == [os.path.join(str(tmp_path), "same.jpg")]
    assert os.path.isabs(p)


# -------------------------------------------------------------------- 缩略图
def test_thumb_long_edge_is_boxed_and_bytes_within_channel_bound():
    info = S.make_thumb(FIXTURE)
    assert max(info["w"], info["h"]) <= S.EDGE, "底片条的格子被一张竖图撑破了"
    assert S.thumb_stores_bytes_ok(info), f"缩略图撑爆控制通道一行：{info['bytes']} B"
    assert info["src_w"] == 1024 and info["src_h"] == 1280, "报出去的源尺寸必须是真的"
    assert info["total_ms"] >= info["decode_ms"] >= 0.0


def test_thumb_base64_round_trips_into_the_reported_picture():
    info = S.make_thumb(FIXTURE, edge=96)
    raw = base64.b64decode(info["jpeg_b64"])
    assert raw[:2] == b"\xff\xd8" and raw[-2:] == b"\xff\xd9", "不是完整的 JPEG"
    with Image.open(io.BytesIO(raw)) as im:
        assert im.size == (info["w"], info["h"]), "报的尺寸与发出去的像素不是一回事"
        assert im.convert("RGB").size == (info["w"], info["h"])


def test_worst_case_noise_thumb_still_fits_the_channel_bound(tmp_path):
    """最坏情况必须真的守住上限，而不是"降质到下限就带着超限字节数发出去"。

    这是随机噪声图：JPEG 编它要几百 KB，质量降到 MIN_THUMB_QUALITY 也还是超。
    实现里那一轮缩尺寸就是为这一条存在的——把 fallback 摘掉，这条立刻红。
    """
    p = noise_jpg(str(tmp_path / "noise.jpg"), 512)
    info = S.make_thumb(p, edge=512)
    assert info["bytes"] <= S.THUMB_MAX_BYTES, f"上限没守住：{info['bytes']} B"
    assert S.thumb_stores_bytes_ok(info)
    assert info["reencoded"] > 0, "质量一档没降过，说明这个靶根本没打到降质那条路"
    assert info["resized"] > 0, "没走缩尺寸那条 fallback：上限是靠运气守住的"
    assert max(info["w"], info["h"]) <= 512


def test_thumb_handles_grey_and_alpha_sources(tmp_path):
    """灰度与带 alpha 的源都得落到 RGB JPEG（格子不能因为 mode 不同而空着）。"""
    a = np.tile(np.linspace(0, 255, 80, dtype=np.uint8), (60, 1))
    Image.fromarray(a, "L").save(tmp_path / "grey.png")
    rgba = np.dstack([np.full((60, 80), 120, np.uint8)] * 3 + [np.full((60, 80), 255, np.uint8)])
    Image.fromarray(rgba, "RGBA").save(tmp_path / "alpha.png")
    for name in ("grey.png", "alpha.png"):
        info = S.make_thumb(str(tmp_path / name), edge=64)
        with Image.open(io.BytesIO(base64.b64decode(info["jpeg_b64"]))) as im:
            assert im.mode == "RGB"
            assert max(im.size) <= 64


def test_thumb_reports_the_deception_case_specifically(tmp_path):
    """把文本改名成 .jpg：报错要说清是"解不开"，不能只丢一句"解码失败"。"""
    p = tmp_path / "fake.jpg"
    p.write_bytes(b"%PDF-1.4 this-is-not-a-bitmap" * 40)
    with pytest.raises(ValueError) as e:
        S.make_thumb(str(p))
    assert "解不开" in str(e.value)


def test_thumb_rejects_missing_file_and_out_of_range_edge(tmp_path):
    with pytest.raises(FileNotFoundError):
        S.make_thumb(str(tmp_path / "没有这个文件.jpg"))
    for bad in (16, 4, 1024, 0):
        with pytest.raises(ValueError):
            S.make_thumb(FIXTURE, edge=bad)
    assert S.valid_edge(S.MIN_EDGE) == S.MIN_EDGE
    assert S.valid_edge(S.MAX_EDGE) == S.MAX_EDGE


@pytest.mark.parametrize("quality,worse", [(100, False), (S.MIN_THUMB_QUALITY, True)])
def test_quality_floor_is_respected_and_reported(quality, worse):
    """报出去的 quality 必须是真用了的那一档：宿主拿它决定要不要提示"图已降质"。"""
    info = S.make_thumb(FIXTURE, edge=S.EDGE, quality=quality)
    assert S.MIN_THUMB_QUALITY <= info["quality"] <= quality
    if not worse:
        assert info["bytes"] <= S.THUMB_MAX_BYTES


def test_doc_meta_is_cheap_and_names_the_file():
    m = S.doc_meta(FIXTURE)
    assert m["name"] == "portrait-1024x1280.jpg"
    assert m["bytes_on_disk"] == os.path.getsize(FIXTURE)
    assert m["bytes_on_disk"] > 0
