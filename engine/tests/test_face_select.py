"""分人编辑的库层判据：`FacePrecompute` 的"这一轮探到的每一张脸"契约（PORTRAIT-003）。

命令层那条端到端（`test_acceptance_p1.py` 里引用 PORTRAIT-003 的那条）跑的是真检测器
+ 真会话，慢且要 torch；这一份守的是它够不着的那一层——**选型语义本身**：

· 只留第 0 张脸就是"引擎替你选了一张"的硬件前提：没有其余那些点，UI 上那颗
  "人物 2" 的 chip 只能是个假控件；
· 换视图不许换掩膜：selfie 分割给的是"人"这一整块，与选哪张脸无关，复制一份
  就是多一处会漂的像素；
· 越界的 index 必须响：静默钳到 0 会得到"状态说选了 5、画面动了 0 号"，而两张脸
  在多人照片上看着都像被推过；
· `scope_block` 不随选型翻牌（那是 SCOPE-001 的 P0 判据要的"这一轮分析是多人图"这个
  事实本身）；放行与否是文档状态，由 server 那一层的 `blocked` 说。

不装 mediapipe 也能跑：这里要验的是产物契约，占位后端与手搓点位就够——真检测的
那一段在端到端与 SCOPE-001 里验。
"""
from __future__ import annotations

import numpy as np
import pytest

from lumaretouch_engine.face import (NUM_LANDMARKS, FacePrecompute, SyntheticFace,
                                     TemplateFace)


def _face_points(cx: float, cy: float, half: float = 0.08) -> np.ndarray:
    """一张"像脸的"点位集：478×3，归一化落在以 (cx,cy) 为中心的小盒里。

    不是模板也不是真检测——这一层要验的是 list/视图的语义（谁被选中、谁被留着），
    与点位从哪来无关；用真点集会把它不该管的东西（精度）混进判据里。
    """
    rng = np.random.default_rng(7)
    xy = rng.uniform(-half, half, size=(NUM_LANDMARKS, 2)) + np.array([cx, cy])
    xy = np.clip(xy, 0.0, 1.0)
    z = rng.uniform(-0.05, 0.05, size=(NUM_LANDMARKS, 1))
    return np.ascontiguousarray(np.hstack([xy, z]), dtype=np.float32)


def _two_face_precompute() -> FacePrecompute:
    """一份"探到两张脸"的产物：左侧那位是默认视图，右侧那位是备选。"""
    a, b = _face_points(0.28, 0.42), _face_points(0.74, 0.46)
    return FacePrecompute(landmarks=a, all_landmarks=[a, b], face_index=0,
                          masks={"skin": np.zeros((24, 32), dtype=np.float32)},
                          backend="mediapipe", t_detect_ms=1.0, t_masks_ms=1.0,
                          face_box=(0.2, 0.34, 0.36, 0.5), num_faces=2)


def test_faces_lists_every_detected_person():
    """PORTRAIT-003 的前提：名单里得有每一个人，且顺序稳定、盒与面积算得出。

    顺序按 `all_landmarks` 的索引（检测器返回的顺序），不面积排序——一排序就和
    `select_face(index)` 的 index 分家，两个"第几张"会指到不同的人。
    """
    pc = _two_face_precompute()
    faces = pc.faces()
    assert len(faces) == 2, f"只报出 {len(faces)} 个人：另一个人没有可编辑的几何"
    assert [f["index"] for f in faces] == [0, 1]
    assert faces[0]["box"][0] < faces[1]["box"][0], "名单被重排了：index 与选中的不是同一张"
    for f in faces:
        assert len(f["box"]) == 4 and f["box"][0] <= f["box"][2]
        assert f["box"][1] <= f["box"][3]
        assert 0.0 < f["area"] < 1.0
    # 空名单不许出现：`all_landmarks` 缺省（旧产物）时按当前那份点算一个
    old = FacePrecompute(landmarks=_face_points(0.5, 0.5), masks={"skin": np.zeros((8, 8), np.float32)},
                         backend="template", t_detect_ms=0.0, t_masks_ms=0.0)
    assert [f["index"] for f in old.faces()] == [0]


def test_select_face_moves_the_view_without_touching_the_masks():
    """换人选只换关键点那份视图：掩膜必须是同一个对象。

    masks 复制一份看着无害，实际是把"skin 通道"变成两份会各自漂的东西——
    肤色定向与换底读的都是它，下一笔改遮罩只会改到其中一份。
    """
    pc = _two_face_precompute()
    view = pc.select_face(1)
    assert view.landmarks is pc.all_landmarks[1], "选中的不是那一张的点位（拷了？换了？）"
    assert view.masks is pc.masks, "掩膜被复制了：同一张 skin 现在有两份"
    assert view.all_landmarks is pc.all_landmarks, "名单被丢了：换回去要重新检测才是假能力"
    assert view.face_index == 1
    assert view.face_box[0] > pc.face_box[0], "脸盒没跟着换：报的还是上一张的位置"
    assert view.num_faces == 2 and view.backend == "mediapipe"
    # 视图上还能再选回去（同一份名单，不用重新分析）
    back = view.select_face(0)
    assert back.landmarks is pc.all_landmarks[0] and back.face_index == 0
    # 原件不许被改动：选型是产生视图，不是就地改状态
    assert pc.landmarks is pc.all_landmarks[0] and pc.face_index == 0


def test_out_of_range_index_is_rejected_not_clamped():
    """越界与坏类型都整条拒。静默钳到 0 会得到"选了 5 而动了 0 号"那种查不清的错。"""
    pc = _two_face_precompute()
    for bad in (2, 7, -1, True, "1", 0.0, None):
        with pytest.raises(ValueError):
            pc.select_face(bad)


def test_select_face_refuses_a_broken_landmark_set():
    """名单里混进一份坏点集（不是 478×3）时必须拒，而不是让下游去撞形状。

    deform 的 `controls()` 按点号取部位，477 点会取到错位的部位而"画面真的动了"——
    那正是契约破坏最安静的形状。
    """
    good = _face_points(0.3, 0.4)
    broken = good[:-1]                      # 少一个点，形状 (477,3)
    pc = FacePrecompute(landmarks=good, all_landmarks=[good, broken], num_faces=2,
                        masks={"skin": np.zeros((8, 8), np.float32)}, backend="mediapipe",
                        t_detect_ms=0.0, t_masks_ms=0.0)
    with pytest.raises(ValueError, match="契约"):
        pc.select_face(1)


def test_meta_reports_the_selection_and_keeps_the_scope_flag():
    """上报那一格：名单、当前第几张都在，而 scope_block 不随选型翻牌。

    后者是有意的：SCOPE-001（P0）要的是"这一轮分析看到了几张脸"这个事实，
    它不因为用户选了其中一张而变成单人图；能不能放行由 server 的 `blocked` 说。
    """
    pc = _two_face_precompute()
    meta = pc.meta(24, 32)
    assert meta["face_index"] == 0 and len(meta["faces"]) == 2
    assert meta["num_faces"] == 2 and meta["scope_block"] == "multi_face"
    v = pc.select_face(1).meta(24, 32)
    assert v["face_index"] == 1 and v["num_faces"] == 2
    assert v["scope_block"] == "multi_face", "选型把多人事实抹掉了：SCOPE-001 的 P0 判据会失去意义"
    # 单人那一轮：既没有 block 也只有一个候选
    one = _two_face_precompute().select_face(0)
    one = FacePrecompute(landmarks=one.landmarks, all_landmarks=[one.landmarks], num_faces=1,
                         masks=one.masks, backend="mediapipe", t_detect_ms=0.0, t_masks_ms=0.0)
    m = one.meta(24, 32)
    assert m["scope_block"] is None and len(m["faces"]) == 1 and m["face_index"] == 0


def test_single_face_backends_still_fill_the_list():
    """synthetic / template 也要给名单（只有一张）：缺这一格，命令层就得替它们猜。

    两个后端都是"按定义一张"的占位几何；把它们写进同一形状，UI 与 server 就只需
    处理一种数据结构，不用"mediapipe 才有的字段"那种分支（那会漂）。
    """
    rgb = np.zeros((48, 40, 3), dtype=np.uint8)
    rgb[:, :, :] = (200, 160, 140)          # 一块"像皮肤"的暖色
    for cls in (SyntheticFace, TemplateFace):
        pc = cls()(rgb)
        assert pc.num_faces == 1, pc.num_faces
        assert len(pc.all_landmarks) == 1, f"{cls.__name__} 没填名单：命令层要替它猜第 0 张"
        assert pc.all_landmarks[0] is pc.landmarks
        assert pc.select_face(0).landmarks is pc.landmarks
        with pytest.raises(ValueError):
            pc.select_face(1)
