"""P2-8：工程重开时真正比对源文件指纹（过去只查在不在，从不核字节）。

缺陷现场：`verify_fingerprint` 在 server.py 里从没被调用过——只活在单测里。cmd_project
("open") 只算 `missing = PJ.missing_sources(...)` 看文件在不在，而保存那一步明明给每张存了
full 指纹（`PJ.fingerprint(..., full=True)`）。于是"保存后原图被别的程序改了 / 被同步工具换
了一版"这一整类内容漂移静默通过：用户拿旧几何的配方编辑一张已经不是当初那张的图，导出也不自知。

这里全 CPU：不 import torch/vram，用 Engine.__new__(Engine) 直接驱动抽出来的
_source_fingerprint_drift（与 test_project.py 同一层判据口径）。
"""
from __future__ import annotations

import os

import numpy as np

from lumaretouch_engine import project as PJ
from lumaretouch_engine.server import Engine


def _png(path, val=0):
    from PIL import Image
    a = np.full((32, 24, 3), val, np.uint8)
    Image.fromarray(a, "RGB").save(path)
    return str(path)


def _prj(*docs):
    """docs: [(path, fp_or_None), ...]，够 _source_fingerprint_drift 读的窄形状。"""
    return {"docs": [{"path": p, "fingerprint": fp} for (p, fp) in docs]}


def _eng() -> Engine:
    return Engine.__new__(Engine)          # 只用 PJ 与入参，不碰 __init__ 的重依赖


def test_no_drift_when_untouched(tmp_path):
    src = _png(tmp_path / "a.png")
    fp = PJ.fingerprint(src, full=True)
    assert _eng()._source_fingerprint_drift(_prj((src, fp))) == []


def test_content_edit_is_reported_as_drift(tmp_path):
    """原始缺陷的形状：文件还在、可字节变了——过去无人报警，现在必须进 changed。"""
    src = _png(tmp_path / "a.png", val=10)
    fp = PJ.fingerprint(src, full=True)
    _png(src, val=20)                       # 同路径覆盖成不同内容
    changed = _eng()._source_fingerprint_drift(_prj((src, fp)))
    assert len(changed) == 1 and changed[0]["path"] == src
    assert changed[0]["head_match"] is False or changed[0]["full_match"] is False


def test_deep_byte_flip_caught_by_full_level(tmp_path):
    """头部没动、长度没动、只有 4KB 之后一字节变了：head/bytes 都对得上，
    靠存储那一等是 full 才能逮住——证明 full_match 这一支不是摆设。"""
    big = tmp_path / "deep.bin"
    data = bytearray(9000)
    big.write_bytes(bytes(data))
    fp = PJ.fingerprint(str(big), full=True)      # hash_level=full
    data[8000] = 0x5A                             # 只改 4096 之后、长度不变
    big.write_bytes(bytes(data))
    changed = _eng()._source_fingerprint_drift(_prj((str(big), fp)))
    assert len(changed) == 1, changed
    assert changed[0]["head_match"] is True and changed[0]["full_match"] is False


def test_missing_file_not_double_counted_as_drift(tmp_path):
    """缺文件归 missing，不进 changed：这里不许把它又报成"内容漂移"。"""
    gone = str(tmp_path / "nope.png")
    fp = {"path": os.path.abspath(gone), "bytes": 100, "sha256": "x",
          "head_sha256": "y", "hash_level": "full", "mtime_ns": 0, "readonly": False}
    assert _eng()._source_fingerprint_drift(_prj((gone, fp))) == []


def test_mtime_only_touch_is_not_drift(tmp_path):
    """只改 mtime、字节没动（拷贝/同步工具改时间戳）：不该报成"照片坏了"。"""
    src = _png(tmp_path / "a.png")
    fp = PJ.fingerprint(src, full=True)
    os.utime(src, ns=(1_000_000_000, 1_000_000_000))
    assert _eng()._source_fingerprint_drift(_prj((src, fp))) == []


def test_fingerprint_absent_or_none_level_is_skipped(tmp_path):
    """没指纹或 hash_level=none 的降级行：跳过而不是崩（旧版从没算过的格子）。"""
    src = _png(tmp_path / "a.png")
    out = _eng()._source_fingerprint_drift(
        _prj((src, None),
             (src, {"hash_level": "none", "path": src}),
             (src, {})))
    assert out == []
