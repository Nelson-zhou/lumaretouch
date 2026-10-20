"""人工纠正优先的库层判据（LNX-PORTRAIT-006）。

命令层那条端到端（`test_acceptance_p1.py` 里引用 PORTRAIT-006 的那条）跑的是真检测器
+ 真会话 + 真工程文件，慢且要 torch；这一份守的是它够不着、又最容易错的那三层：

· **映射数学**：用户框的是一块窗，而名单活在整幅归一化坐标上。窗→整幅那一步算错，
  产出的是一层"看着能拖、控制点却在别人脸上"的形变——屏幕上看不出来，只有逐点反算能抓；
· **拒绝路径**：框里没有脸 / 框对不上 / 窗太小补不出上下文，三种都必须是**明拒并说清
  为什么**。静默退成"用邻近那一张"或"按框拟合一套占位点位"就是 DoD §2 严禁的假 AI；
· **人工账的叠放语义**：禁用按 IoU 认（`when` 那一栏写的是"重检测**或更换检测模型**"，
  逐位相等等于只在同一次推理内有效），认不回的条目留在账上（丢掉就是一次静默恢复）。

不装 mediapipe 也能跑：这里验的是产物契约与判据语义，占位后端与手搓点位就够——真检测
的那一段在端到端里验（ADR-0009 的"通路证据 ≠ 精度证据"同一口径）。
"""
from __future__ import annotations

import numpy as np
import pytest

from lumaretouch_engine import face as face_mod
from lumaretouch_engine.face import (NUM_LANDMARKS, FacePrecompute, RegionNotFound,
                                     TemplateFace, _norm_box, box_iou, detect_region)
from lumaretouch_engine.server import Engine


def _points(x0, y0, x1, y1) -> np.ndarray:
    """一张"落在给定归一化盒里"的点位集（478×3，xy 线性铺满对角，z 固定）。

    刻意用可反算的解析布局：映射那条判据要的是"每个点都按同一条仿射走过"，
    随机点只能验包围盒，验不出逐点。
    """
    t = np.linspace(0.0, 1.0, NUM_LANDMARKS, dtype=np.float32)
    xy = np.stack([x0 + t * (x1 - x0), y0 + t * (y1 - y0)], axis=1)
    z = np.full((NUM_LANDMARKS, 1), -0.02, dtype=np.float32)
    return np.ascontiguousarray(np.hstack([xy, z]), dtype=np.float32)


def _two_face_pc() -> FacePrecompute:
    a, b = _points(0.20, 0.34, 0.36, 0.50), _points(0.62, 0.38, 0.78, 0.54)
    return FacePrecompute(landmarks=a, all_landmarks=[a, b], face_index=0,
                          masks={"skin": np.zeros((24, 32), dtype=np.float32)},
                          backend="mediapipe", t_detect_ms=1.0, t_masks_ms=1.0,
                          face_box=_norm_box(a), num_faces=2)


# ------------------------------------------------------------------ 名单里的人工来源
def test_with_manual_face_appends_and_records_provenance():
    pc = _two_face_pc()
    lm = _points(0.05, 0.60, 0.18, 0.78)
    out = pc.with_manual_face(lm)
    assert out is not pc, "改成了原地 mutate：同一份产物被两条文档共用是一次静默串档"
    faces = out.faces()
    assert len(faces) == 3 and out.num_faces == 3, f"人工脸没进名单：{len(faces)} 张"
    assert [f["manual"] for f in faces] == [False, False, True], \
        f"来源标错了：{[f['manual'] for f in faces]}（检测那两张不该被说成人工的）"
    assert faces[2]["box"] == [round(v, 5) for v in _norm_box(lm)]
    assert out.manual == (2,), out.manual


def test_with_manual_face_rejects_broken_contract():
    pc = _two_face_pc()
    with pytest.raises(ValueError, match="478"):
        pc.with_manual_face(np.zeros((NUM_LANDMARKS - 5, 3), dtype=np.float32))
    with pytest.raises(ValueError, match="478"):
        pc.with_manual_face(np.zeros((NUM_LANDMARKS, 2), dtype=np.float32))
    assert len(pc.faces()) == 2, "被拒的人工脸留下了半截名单"


def test_select_face_keeps_manual_provenance():
    """换视图不许把「这张脸出自用户框」洗成模型输出：chip 上一秒标人工、下一秒自称
    检测器找到，用户在审计自己作品时就会被告知一条不存在的事实。"""
    out = _two_face_pc().with_manual_face(_points(0.05, 0.60, 0.18, 0.78))
    view = out.select_face(2)
    assert view.manual == (2,) and view.faces()[2]["manual"] is True
    assert view.face_index == 2 and view.landmarks.shape == (NUM_LANDMARKS, 3)


def test_meta_reports_manual_indices_separately_from_num_faces():
    """「这一轮探到几张」与「名单里有几张」是两件事，混成一格就查不出补的那张去了哪。"""
    out = _two_face_pc().with_manual_face(_points(0.05, 0.60, 0.18, 0.78))
    m = out.meta(24, 32)
    assert m["manual_indices"] == [2], m.get("manual_indices")
    assert m["num_faces"] == 3


# ------------------------------------------------------------------ IoU 与窗口
def test_box_iou_edges():
    assert box_iou((0, 0, 1, 1), (0, 0, 1, 1)) == pytest.approx(1.0)
    assert box_iou((0, 0, 0.5, 0.5), (0.5, 0.5, 1, 1)) == 0.0
    assert box_iou((0, 0, 0.5, 1), (0.25, 0, 0.75, 1)) == pytest.approx(1.0 / 3.0)
    # 退化输入必须给 0 而不是 NaN/异常：判据要在这些数字上做比较
    assert box_iou(None, (0, 0, 1, 1)) == 0.0
    assert box_iou((0, 0, 0, 0), (0, 0, 1, 1)) == 0.0
    assert box_iou((0, 0, 1), (0, 0, 1, 1)) == 0.0
    assert box_iou(("a", 0, 1, 1), (0, 0, 1, 1)) == 0.0


def test_grow_window_clamps_at_frame_edges():
    g = face_mod._grow_window
    assert g(30, 40, 200, 35, 48) == (16, 64), "以框中心为锚补齐"
    lo, hi = g(0, 10, 200, 5, 48)
    assert (lo, hi) == (0, 48), f"贴左边界时整窗该往右推：{(lo, hi)}"
    lo, hi = g(190, 200, 200, 195, 48)
    assert (lo, hi) == (152, 200), f"贴右边界时整窗该往左退：{(lo, hi)}"
    assert g(0, 100, 200, 50, 48) == (0, 100), "已经够大就不动"


# ------------------------------------------------------------------ 区域检测
class _StubBackend:
    """按契约行事的假后端：给它的那一窗里放几张脸它就报几张，点位解析可反算。

    真后端（mediapipe）在这一层只贡献"点位从哪来"，而这一条要验的是**映射数学与拒绝
    路径**——用真后端反而验不出逐点（它的点位没人知道该在哪）。
    """

    name = "stub"
    requires_models = False

    def __init__(self, maker, notes=None):
        self.maker = maker
        self.calls = []
        self.notes = notes or ["stub 后端：点位由测试给出"]

    def __call__(self, rgb: np.ndarray) -> FacePrecompute:
        h, w = int(rgb.shape[0]), int(rgb.shape[1])
        self.calls.append((h, w))
        pool = self.maker(h, w)
        if not pool:
            raise RuntimeError("stub 没脸可报")
        return FacePrecompute(landmarks=pool[0], all_landmarks=pool, num_faces=len(pool),
                              masks={"skin": np.zeros((h, w), dtype=np.float32)},
                              backend=self.name, t_detect_ms=0.5, t_masks_ms=0.0,
                              face_box=_norm_box(pool[0]))


def _rect_in_window(win, x0, y0, x1, y1):
    """把「窗内归一化」换算成「整幅归一化」——与 detect_region 该用的那条公式同源，
    这里独立写一遍，是为了让判据不是拿被测代码自己算出来的数自我确认。"""
    wx0, wy0, wx1, wy1 = win
    return (wx0 + x0 * (wx1 - wx0), wy0 + y0 * (wy1 - wy0),
            wx0 + x1 * (wx1 - wx0), wy0 + y1 * (wy1 - wy0))


def test_detect_region_maps_crop_points_back_to_full_frame():
    rgb = np.zeros((400, 600, 3), dtype=np.uint8)
    rect = (0.30, 0.25, 0.45, 0.60)
    stub = _StubBackend(lambda h, w: [_points(0.15, 0.10, 0.85, 0.90)])
    lm, info = detect_region(stub, rgb, rect)
    assert lm.shape == (NUM_LANDMARKS, 3) and lm.dtype == np.float32
    win = info["window"]
    # 窗必须**包住**用户框（补上下文），且补的量随框的大小走而不是拍一个常数
    assert win[0] <= rect[0] and win[1] <= rect[1] and win[2] >= rect[2] and win[3] >= rect[3]
    want = _rect_in_window(win, 0.15, 0.10, 0.85, 0.90)
    got = (float(lm[:, 0].min()), float(lm[:, 1].min()), float(lm[:, 0].max()), float(lm[:, 1].max()))
    assert max(abs(a - b) for a, b in zip(want, got)) < 1e-6, f"映射不是一条仿射：{want} vs {got}"
    assert info["iou"] >= face_mod.REGION_IOU_MIN and info["chosen_index"] == 0
    assert stub.calls and min(stub.calls[0]) >= face_mod.REGION_MIN_SIDE_PX, \
        f"喂给后端的窗比最小边还小：{stub.calls[0]}"


def test_detect_region_picks_the_face_that_matches_the_rect_not_the_biggest():
    """窗里坐着两个人时必须按「与用户框对得上」选，而不是按面积选。

    拿邻座的 478 点当成"你框的那一张"挂进名单，就是拿另一个人的脸形服务一个不该服务
    的人——与 SCOPE-001 拦的是同一件事，只是这次是补过上下文之后自己造出来的重叠。
    """
    rgb = np.zeros((400, 600, 3), dtype=np.uint8)
    rect = (0.30, 0.25, 0.45, 0.60)
    big_off = _points(0.55, 0.05, 0.98, 0.55)          # 又大片又不在框上
    small_on = _points(0.10, 0.20, 0.40, 0.85)         # 小一点，但正落在用户框里
    stub = _StubBackend(lambda h, w: [big_off, small_on])
    lm, info = detect_region(stub, rgb, rect)
    assert info["chosen_index"] == 1, f"选了面积最大的那位：{info}"
    box = (float(lm[:, 0].min()), float(lm[:, 1].min()), float(lm[:, 0].max()), float(lm[:, 1].max()))
    assert box_iou(box, rect) >= face_mod.REGION_IOU_MIN


def test_detect_region_refuses_when_nothing_matches_the_rect():
    rgb = np.zeros((400, 600, 3), dtype=np.uint8)
    stub = _StubBackend(lambda h, w: [_points(0.7, 0.7, 0.95, 0.95)])
    with pytest.raises(RegionNotFound, match="对得上"):
        detect_region(stub, rgb, (0.05, 0.05, 0.18, 0.30))


def test_detect_region_refuses_broken_rects_without_calling_the_backend():
    rgb = np.zeros((400, 600, 3), dtype=np.uint8)
    calls = []

    def maker(h, w):
        calls.append((h, w))
        return [_points(0.2, 0.2, 0.8, 0.8)]

    stub = _StubBackend(maker)
    for bad in ((0.5, 0.2, 0.3, 0.6),        # 反了
                (-0.1, 0.2, 0.5, 0.6),       # 越界
                (0, 0, 1, 1, 0),             # 维度不对
                ("a", 0.2, 0.5, 0.6),        # 类型不对
                (0.3, 0.25, 0.3 + 1e-6, 0.6)):   # 扁得像一次误点
        with pytest.raises(RegionNotFound):
            detect_region(stub, rgb, bad)
    assert not calls, "非法框也去跑了后端：拒绝要在花钱之前发生"


def test_detect_region_wraps_backend_failure_as_an_explicit_refusal():
    """后端报"这张图里没有脸"不能被说成"用户框错了"，也不能退成占位点位。"""
    class _Broken:
        name = "broken"

        def __call__(self, rgb):
            raise RuntimeError("MediaPipe 未在这张图上检测到人脸")

    rgb = np.zeros((400, 600, 3), dtype=np.uint8)
    with pytest.raises(RegionNotFound, match="未在这张图上检测到人脸"):
        detect_region(_Broken(), rgb, (0.3, 0.2, 0.5, 0.6))


def test_detect_region_refuses_window_it_cannot_grow():
    rgb = np.zeros((30, 40, 3), dtype=np.uint8)      # 代理帧比最小窗还小
    stub = _StubBackend(lambda h, w: [_points(0.2, 0.2, 0.8, 0.8)])
    with pytest.raises(RegionNotFound, match="补不出"):
        detect_region(stub, rgb, (0.1, 0.1, 0.6, 0.6))


def test_detect_region_works_on_the_template_backend_without_plugins():
    """通路证据：没装 mediapipe 的机器上这条路径也要能端到端跑（template 满足同一契约）。

    它**不是**精度证据——模板点位是按肤色盒摆的，这一点由后端自己的 notes 说，而
    detect_region 把 backend 原样报出去（面板要显示"这一张的点位出自 template"）。
    """
    rgb = np.zeros((300, 300, 3), dtype=np.uint8)
    rgb[90:220, 90:220] = (200, 150, 130)            # 一块"像皮肤"的方片
    lm, info = detect_region(TemplateFace(), rgb, (0.30, 0.30, 0.72, 0.74))
    assert lm.shape == (NUM_LANDMARKS, 3)
    assert info["backend"] == "template", info
    assert box_iou(info["box"], (0.30, 0.30, 0.72, 0.74)) >= face_mod.REGION_IOU_MIN


# ------------------------------------------------------------------ 人工账语义（命令层判据的无机版）
def _ledger_engine(pc=None, disabled=None, added=None, index=0, box=None, explicit=False):
    """只装人脸子系统要用的那几格状态的 Engine 壳。

    不走真会话是因为这些判据比的是**账的语义**（认不认人、丢不丢条目、放行怎么算），
    与显存/渲染无关；把它们挂在真窗口上，一轮回归要为每条判据付一次 torch 初始化的钱。
    """
    e = object.__new__(Engine)
    e._precompute = pc
    e._face_manual = {"disabled": [list(b) for b in (disabled or [])],
                      "added": [list(b) for b in (added or [])]}
    e._face_index = index
    e._face_box = box
    e._face_explicit = explicit
    e._deform = dict(amounts={k: 0.0 for k in ("slim_face",)}, built=False)
    e._deform_defer = False
    e._deform_default = {}
    e._deform_overrides = []
    e._enhance = dict(amounts={}, built=False, box=None)
    e._enhance_defer = False
    e._vram = None
    e._image_loaded = True
    return e


def test_manual_box_normalizes_and_drops_malformed_entries():
    e = _ledger_engine()
    assert e._manual_box([0.1, 0.2, 0.3, 0.4]) == (0.1, 0.2, 0.3, 0.4)
    assert e._manual_box((0.1, 0.2, "0.3", 0.4)) == (0.1, 0.2, 0.3, 0.4)   # 工程档里的字符串数
    for bad in (None, [0.1, 0.2, 0.3], [0.5, 0.2, 0.3, 0.4], [0.1, 0.2, 0.3, 1.4], "abcd", 7):
        assert e._manual_box(bad) is None, f"这条残框会被留下：{bad!r}"


def test_disabled_ledger_matches_by_iou_across_redetection():
    """同一个人换了模型/换了代理档，盒会漂：按 IoU 认，人工禁用才不会一次重算就失效。"""
    pc = _two_face_pc()
    b = pc.faces()[1]["box"]
    drifted = [max(0.0, v - 0.02) if i % 2 == 0 else v + 0.02 for i, v in enumerate(b)]
    e = _ledger_engine(pc, disabled=[drifted])
    st = e._face_state()
    assert st["faces"][1]["disabled"] is True, "盒漂了 0.02 就不认了：禁用形同一次重算即失效"
    assert st["manual"]["stale"] == [], st["manual"]
    assert st["disabled_count"] == 1 and st["enabled"] == [0], st


def test_unmatched_disabled_entry_stays_on_the_ledger():
    """认不回的条目**留在账上**并标 stale：悄悄丢掉它就是一次静默恢复。"""
    pc = _two_face_pc()
    far = [0.82, 0.80, 0.95, 0.97]           # 名单里没有这个人
    e = _ledger_engine(pc, disabled=[far])
    st = e._face_state()
    assert st["manual"]["disabled"] == [far], "账被偷偷改写了"
    assert st["manual"]["stale"] == [far], st["manual"]
    assert st["disabled_count"] == 0, "认不出却算成已禁用：名单凭空少了一个人"


def test_blocked_counts_editable_people_not_detected_faces():
    """关掉一只误检之后不该还要求用户对着只剩一格的名单再选一次（那也是一种无响应控件），
    而 `scope_block` 仍要说真话：这一轮分析确实探到过不止一张。"""
    pc = _two_face_pc()
    on = _ledger_engine(pc, disabled=[pc.faces()[0]["box"]])
    st = on._face_state()
    assert st["scope_block"] == "multi_face", "人工账把原始分析事实抹掉了（SCOPE-001 的 P0 判据失去意义）"
    assert st["blocked"] is False and st["enabled"] == [1], st
    off = _ledger_engine(pc)
    assert off._face_state()["blocked"] is True, "没禁用时多人图照样要显式选定"


def test_face_state_previews_what_this_round_changed():
    """冻结件 then 那句"变化可预览"的落点：新增谁、认不回谁，一份账说清。"""
    pc = _two_face_pc()
    e = _ledger_engine(pc, disabled=[pc.faces()[1]["box"]],
                       added=[[0.02, 0.62, 0.16, 0.80]], index=1)
    # 第三条禁用对应的这个人这一轮没被探到
    e._face_manual["disabled"].append([0.86, 0.86, 0.98, 0.99])
    st = e._face_state()
    m = st["manual"]
    assert len(m["stale"]) == 1, m
    # 名单里既没被禁用、也不在人工账里的那些 = 本轮新增的候选
    assert m["new_faces"] == [0], m
    assert "保留" in m["preview"] and "认不回" in m["preview"], m["preview"]


def test_face_guard_uses_the_editable_count():
    e = _ledger_engine(_two_face_pc())
    blocked, why = e._face_guard()
    assert blocked is True and "face select" in why and "face disable" in why, why
    e2 = _ledger_engine(_two_face_pc(), disabled=[_two_face_pc().faces()[0]["box"]])
    assert e2._face_guard()[0] is False, "关掉一只误检之后还挡着：用户会看到面板能点而引擎拒"


def test_engine_face_actions_are_the_single_source_for_the_ui():
    """ready 报的 face_actions 必须真等于 cmd_face 认的那些：前端刻一份就是下一轮漏改的那处。"""
    assert set(Engine.FACE_ACTIONS) >= {"list", "select", "disable", "enable", "add", "remove"}
    assert Engine.MANUAL_IOU_MIN > 0.0 and Engine.MANUAL_IOU_MIN < 1.0


def test_manual_done_event_carries_the_face_object_the_host_slot_reads(monkeypatch):
    """`face_manual` 必须自己带着那一份 `face` 对象——宿主桥（note_face）只认这一格。

    这一条是被装机真窗口第 9 臂逼出来的：库里那份账走 `status.face` → `faceStateOf`
    → 面板，事件少带一格，面板就要等下一次 precompute 才刷新——用户点了 ✕，账记上了
    而屏幕不认（DoD §3 禁的正是这一类"看着没反应"的控件）。
    """
    from lumaretouch_engine import server as srv

    pc = _two_face_pc()
    e = _ledger_engine(pc, disabled=[pc.faces()[1]["box"]])
    seen: list[dict] = []
    monkeypatch.setattr(srv, "emit", lambda obj: seen.append(obj))
    e._face_manual_done("disable", note="已关掉第 1 只（误检）")
    ev = [s for s in seen if s.get("event") == "face_manual"]
    assert len(ev) == 1, seen
    st = ev[0].get("face")
    assert isinstance(st, dict) and st, "事件没带 face 对象：桥那一格永远不刷新"
    assert st["manual"]["disabled"] and st["enabled"] == [0], st
    # 平铺与嵌套必须是同一份（历史形状与新形状不许各写一份、各漂移一半）
    assert ev[0]["manual"] == st["manual"] and ev[0]["enabled"] == st["enabled"], ev[0]
    assert ev[0]["note"] == "已关掉第 1 只（误检）"


def test_every_face_bearing_engine_event_is_routed_by_the_host_bridge():
    """双向守卫：引擎带 `face` 的事件名 ⊇/⊆ Rust 桥 `on_face` 那一支列出的名字。

    上一轮 auto_pick 漏桥、这一轮 face_manual 漏桥，形状完全一样：**新增一条事件而
    忘了在路由器里接**，裸引擎用例一个字也看不见（它们连的是引擎，不经过桥）。写成人
    对人的记忆纪律没有用，只有把它变成一条会红的判据才有用。
    """
    import re
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    engine_src = (repo / "engine" / "src" / "lumaretouch_engine" / "server.py").read_text(
        encoding="utf-8")
    bridge = (repo / "ui" / "src-tauri" / "src" / "engine.rs").read_text(encoding="utf-8")

    carrying = set()
    for m in re.finditer(r"emit\(\{(?:.|\n){0,900}?\}\)", engine_src):
        blk = m.group(0)
        if '"face":' in blk:
            ev = re.search(r'"event":\s*"([a-z_]+)"', blk)
            if ev:
                carrying.add(ev.group(1))
    assert {"face_list", "face_selected", "face_manual"} <= carrying, carrying

    arms = re.findall(r'^[ \t]*("face[a-z_]+"(?:\s*\|\s*"face[a-z_]+")*)\s*=>', bridge, re.M)
    routed = set(re.findall(r'"(face[a-z_]+)"', " ".join(arms)))
    assert carrying <= routed, f"引擎带 face 的事件而桥没接：{sorted(carrying - routed)}"
    assert routed <= carrying, f"桥接了引擎不会发的名字（拼错就是一条静默）：{sorted(routed - carrying)}"


def test_every_host_slot_writer_has_a_router_arm():
    """main.rs 里每个 `pub fn on_*`（往状态槽位写东西的那批）必须由路由器调用。

    本轮亲手撞上的那记：给 face 那一臂加名字时，编辑误把 `"enhance_done"` 与
    `"pick_*"` 两整个 match 臂删掉了。tsc 不知道（那是 Rust），裸引擎 930 条也不
    知道（它们连的是引擎，不经过桥），而症状是"两臂静默超时"——只有装机真窗口看得见。
    这条判据把同一件事变成一条会红的判据：**槽位写入者没有调用者 = 那条通道是死的**。
    """
    import re
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    main = (repo / "ui" / "src-tauri" / "src" / "main.rs").read_text(encoding="utf-8")
    router = (repo / "ui" / "src-tauri" / "src" / "engine.rs").read_text(encoding="utf-8")

    writers = sorted(set(re.findall(r"pub fn (on_[a-z_]+)\(", main)))
    called = set(re.findall(r"state\.(on_[a-z_]+)\(", router))
    # 也认 main.rs 内部自己的调用（note_doc → note_face 那一类转发）
    called |= {w for w in writers if re.search(r"\." + w + r"\(", main)}
    dead = [w for w in writers if w not in called]
    assert not dead, f"这些槽位写入者没有任何调用者（事件通道是死的）：{dead}"
    assert len(writers) >= 20, f"槽位写入者数目掉到 {len(writers)}：路由面被整片删过"
