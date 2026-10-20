"""P1-1：批量导出按每张照片的独立编辑状态处理（不再串当前照片配方）。

原始缺陷：cmd_export 只在命令线程拍了**一份** snap（当前那张的磨皮/调色/裁剪/图层），
_export_loop 整批每张都套这同一份，只靠 for_document=(path==doc) 区分是不是当前那张。
于是同一批里非当前、且各自在底片条里独立编辑过的照片，被套上了当前那张的磨皮强度/
色阶/LUT/裁剪——"串配方"。它们自己的状态本就存在 _docs[i]["state"]，导出没用上。

这里只测**命令线程预解析**的纯逻辑（_state_to_export_snap / _export_snap_by_path）：
用 Engine.__new__ 造假实例，绕开 torch/vram/shm——libraw/torch 缺席的 CI 也能跑。
端到端"不同配方→不同像素"（load_full→export_image→torch）需 GPU 窗口，不在本用例内。
"""
from __future__ import annotations

import os

from lumaretouch_engine.server import Engine


def _mk_session(docs: list) -> Engine:
    """只带 _export_snap_by_path / _state_to_export_snap 所需字段的假 Engine。

    _docs[i]["path"] 必须是绝对路径（_index_of 按 abspath 匹配）；_params/_light 是
    _state_to_export_snap 缺键兜底会读到的 live 字段，给中性值。
    """
    e = Engine.__new__(Engine)
    e._docs = docs
    e._params = {"radius": 12, "eps": 8.0, "texture_radius": 3,
                 "broad_gain": 0.0, "mid_gain": 0.0, "detail_gain": 0.0}
    e._light = {"exposure": 0.0, "radius": 30}
    return e


def _batch_snap() -> dict:
    """一份批级导出选项齐备的当前档 snap（cmd_export 手拼的那种形状）。"""
    return dict(strength=0.9, params=dict(radius=12, eps=8.0, texture_radius=3,
                                          broad_gain=0.0, mid_gain=0.0, detail_gain=0.0),
                grade=(0.5, 0.0, 0.0, 1.0), grade_scope="all", grade_mask=None,
                exposure=(1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0), exposure_ref_k=None,
                hsl=(0.0,) * 24, crop_rect=(0.1, 0.1, 0.9, 0.9), crop_rotation=15.0,
                lut=None, lut_amount=0.0, light={"exposure": 0.0, "radius": 30},
                light_ops=[], repair_ops=[], deform={"amounts": {}, "built": False},
                deform_defer=False, enhance={"amounts": {}, "built": False},
                enhance_defer=False, channel=None, _bg={}, precompute=None,
                device="cuda:0", scale=2, upscale_backend="lanczos3", sharpen=0.3)


def _state(strength: float, grade: tuple, crop: tuple) -> dict:
    """一格底片条的已存 state（_capture_state 的下划线键，只填本项关心的几笔）。"""
    return {"_strength": strength, "_grade": grade, "_grade_scope": "all",
            "_crop_rect": crop, "_crop_rotation": 0.0,
            "_exposure": (0.0,) * 7, "_hsl": (0.0,) * 24, "_lut": None,
            "_lut_amount": 0.0, "_params": None, "_light": None,
            "_light_ops": [], "_repair_ops": [], "deform": None,
            "_deform": {"amounts": {}, "built": False}, "_deform_defer": False,
            "_enhance": {"amounts": {}, "built": False}, "_enhance_defer": False,
            "_channel": None, "_bg": {}, "_precompute": None,
            "_exposure_ref_k": None, "_grade_mask": None}


def test_state_to_export_snap_maps_per_image_recipe():
    """一张独立 state 的下划线键要翻成非下划线导出快照，逐字段各归各。"""
    e = _mk_session([])
    st = _state(0.4, (0.0, 0.2, 0.0, 1.0), (0.2, 0.2, 0.8, 0.8))
    snap = e._state_to_export_snap(st, device="cpu", scale=1,
                                   upscale_backend="lanczos3", sharpen=0.0)
    assert snap["strength"] == 0.4
    assert snap["grade"] == (0.0, 0.2, 0.0, 1.0)
    assert snap["crop_rect"] == (0.2, 0.2, 0.8, 0.8)
    assert snap["crop_rotation"] == 0.0
    # 批级导出选项由调用方统一带，不属于某张照片
    assert snap["device"] == "cpu" and snap["scale"] == 1
    assert snap["upscale_backend"] == "lanczos3" and snap["sharpen"] == 0.0


def test_state_to_export_snap_missing_keys_neutral_not_none():
    """缺键按出厂中性兜：不能拿 None 去比名单，也不能静默丢层。"""
    e = _mk_session([])
    snap = e._state_to_export_snap({}, device="cpu", scale=1,
                                   upscale_backend="lanczos3", sharpen=0.0)
    assert snap["strength"] == 0.0
    assert snap["grade"] == (0.0, 0.0, 0.0, 1.0)
    assert snap["exposure"] == (0.0,) * 7
    assert snap["hsl"] == (0.0,) * 24
    assert snap["crop_rect"] == (0.0, 0.0, 1.0, 1.0)


def test_export_snap_by_path_uses_own_recipe_per_document():
    """BATCH-003 核心：同批两张各自编辑过的照片，返回各自配方，不是当前档那一份。"""
    a = os.path.abspath("/imgs/a.jpg")   # 当前文档
    b = os.path.abspath("/imgs/b.jpg")   # 会话里另一格，磨皮 0.4 / 不同裁剪
    docs = [{"path": a, "state": _state(0.9, (0.5, 0.0, 0.0, 1.0), (0.1, 0.1, 0.9, 0.9))},
            {"path": b, "state": _state(0.4, (0.0, 0.2, 0.0, 1.0), (0.2, 0.2, 0.8, 0.8))}]
    e = _mk_session(docs)
    snap = _batch_snap()
    by = e._export_snap_by_path([a, b], a, snap)

    snap_a, fd_a = by[a]
    snap_b, fd_b = by[b]
    # 当前档 → 直接用现拍的 snap（恒等，带它专属图层）
    assert snap_a is snap and fd_a is True
    # 另一格 → 用它自己的 state：磨皮/调色/裁剪各归各，不是套当前档
    assert fd_b is True
    assert snap_b["strength"] == 0.4, "串了当前档的磨皮强度（原缺陷）"
    assert snap_b["grade"] == (0.0, 0.2, 0.0, 1.0)
    assert snap_b["crop_rect"] == (0.2, 0.2, 0.8, 0.8)
    # 批级选项仍从当前档 snap 统一带
    assert snap_b["scale"] == snap["scale"] == 2
    # 两张必须不同——同即是"串配方"
    assert snap_b["strength"] != snap_a["strength"]


def test_export_snap_by_path_bare_file_no_fabricated_recipe():
    """BATCH-003：不在会话里的裸文件无独立状态可用，退回共享参数且 for_document=False，
    让 _export_snapshot 逐图 skip 掉文档专属层（绝对坐标笔迹/裁剪不盲目搬）——绝不假装搬了配方。"""
    a = os.path.abspath("/imgs/a.jpg")
    z = os.path.abspath("/imgs/not-in-session.jpg")
    docs = [{"path": a, "state": _state(0.9, (0.5, 0.0, 0.0, 1.0), (0.1, 0.1, 0.9, 0.9))}]
    e = _mk_session(docs)
    snap = _batch_snap()
    by = e._export_snap_by_path([a, z], a, snap)
    assert by[z] == (snap, False)


def test_export_snap_by_path_current_doc_wins_even_if_in_docs():
    """当前那张即使在 _docs 里（它本就是某一格），也用现拍 snap 而不是它存的旧 state：
    现拍 snap 带着此刻 live 的图层，比格子里那份可能过期的 state 新。"""
    a = os.path.abspath("/imgs/a.jpg")
    docs = [{"path": a, "state": _state(0.1, (0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 1.0, 1.0))}]
    e = _mk_session(docs)
    snap = _batch_snap()
    by = e._export_snap_by_path([a], a, snap)
    assert by[a] == (snap, True)
