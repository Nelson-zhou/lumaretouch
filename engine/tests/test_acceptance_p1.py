"""《开发验收用例》P1 中**本版本真做了的那几条**的端到端用例（DoD §4 要求跑通 P0/P1）。

先写清这一份**不包含**什么，免得它被读成"P1 全过了"：

· PORTRAIT-005（跨图同一人确认）与 006（人工纠正优先）需要一套**跨图人物身份模型**，
  本版本没有——所以它们在这里没有测试；同图分人编辑（003）与层级覆盖继承（004）有，
  判据逐条取自冻结件原文（见下面两个 `test_` 函数）。003/004 都不越界成"跨图认人"：
  覆盖挂在**这一轮分析出来的脸盒**上，换一张图就重新按脸盒认，不假装认得"同一个人";
· PORTRAIT-008/010/011（全身、妆容头发、手脚）本版本一行实现都没有——它们要的
  是姿态/发丝/手部那一层感知，没有那一层就没有可验的判据，所以这里不写测试也不签成做了；
· PORTRAIT-012（表情）这一版本只做**嘴角上扬**那一格（露齿笑/抿嘴笑/闭合嘴巴/换表情
  要重建唇齿内容 = 生成式 = 冻结件 2310 行的 P2 实验档），所以下面那条测的是这一格，
  不支持的那四样以「整条拒 + 报得出可用名单」的形式测；
  （012 表情要新的形变目标与唇齿连续性判据，见 ADR-0009 §4 的档位；011 手脚要手部关键点，
  我们只带 FaceMesh；008 全身要身体姿态，同理）；
·（PICK-001 原来在这段里：做它要一个我们没有的分类器，而拿启发式规则冒充 AI 正是 DoD
  明令禁止的那件事。现在它按**本地确定性度量**交付——dHash/高频能量/luma 裁切/FaceMesh
  眼睑几何，每条都带 method、数值与阈值可复算，所以它移到下面"已覆盖"那一段。）
· COLOR-004（局部调色）的"目标区域保护"只有已经存在的那几层可测。

这几条在这里**没有测试**，`tools/run-acceptance.py` 因此把它们如实写成 `uncovered`
——不是 `passed`，也不是 skip。少写一份测试是一回事，把没做的东西签成做了是另一回事。

这一份覆盖的七条都有真实现可验，判据逐条取自冻结件的 `then` 原文：

· MANUAL-001 "缩放、旋转、裁剪、重开项目 → 笔划保持正确原图位置和半径语义；显示缩放
  不改变结果"
· MANUAL-002 "重放液化后撤销再重做 → 位移连续、结果稳定；边界无拼缝；可完整撤销"
· MANUAL-003 "改变缩放和重开后重放 → 源点/目标点映射稳定；修复范围可见可撤销"
· RAW-001  "支持项完成明确的显影链；不支持项准确提示；嵌入 JPEG 预览不冒充 RAW 显影"
· PORTRAIT-007 "目标变化可控、连续；不扭曲邻近人脸；背景异常纳入人工审核"（前两句
  客观可测，"背景异常"那一半是**人工**，本文件不代签，见 case-map 的 manual 标记）
· PORTRAIT-003 "第二人的有效配方不变；图像影响在定义的第一人蒙版边缘内"
· PICK-001   "建议必须可覆盖，不会自动永久删除照片；近似分组与判定原因可见"
· PORTRAIT-012 "中性值可恢复"＋在出片上重测关键点判身份与唇齿连续（阈值取实测）
· PORTRAIT-004 "覆盖项继续生效；未覆盖项跟随；恢复继承后全部按层级合成"
· BACKGROUND-001 "人像边界与目标区域保护通过；不支持场景明确失败并可恢复"
  （换底与色键早就在装机件里，缺的是这两句 then 的证据：真值取自测试自己画的几何已知
  场景，一类像素属于前景/背景/过渡带是**算出来的**，不是看出来的）

跑法同 test_acceptance_p0：必须在运行时 venv（有 torch）里跑；没 torch 整片 skip，
而执行器把 P1 的 skip 记成 `unverified` 而不是绿。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
from lumaretouch_engine.ops.deform import KINDS
import pytest

from lumaretouch_engine.ops.light import DEFAULT_DB_RADIUS
from lumaretouch_engine.shm import FrameShm

from test_protocol import (FIXTURE, _collect, _create_and_save, _expect_error, _frame_of,
                           _load_mtd, _need_export_env, _needs_torch, _read_frame,
                           _sha_of, _wait_frame_mode, engine, extra_engine)   # noqa: F401
from test_acceptance_p0 import (DUAL, REPO, _cmd_frame, _collect_done, _dual_or_explain, _drain,
                                _live_state, _open)   # noqa: F401  (DUAL 由 _dual_or_explain 用)

# 修容带限半径：默认值取自 ops/light 那一份唯一出处（不在这里重述），
# 只有“要改变的那一档”才是测试自己的决定。
RADIUS_WIDE = 60
STROKE = (120, 80, 40, 40)      # (y0, x0, h, w)：代理帧坐标下的一块实心方块
EPS = 2                         # 判定"这一格被动过"的最小 LSB 差
TEAR_SLACK_LSB = 40             # 连续网格重采样不该造出比原图更陡的边缘，余量给插值


def _amounts(**kw):
    """一份"这一格是 0，其余按 kw 给"的形变账，**键集合取自引擎的 KINDS**。

    测试里以前写死三元组，引擎加第四格（smile）时红的是测试而不是产品——那是好事，
    但修的方式不能是再补一个字面量：补完就有第二份名单了。这里让期望值跟着引擎走。
    """
    from lumaretouch_engine.ops.deform import KINDS
    return {k: float(kw.get(k, 0.0)) for k in KINDS}



def _bbox(diff: np.ndarray, thr: int = EPS):
    """差值图里超过阈值的像素包围盒 (y0, x0, y1, x1)（闭区间）；没有命中返 None。"""
    hit = np.abs(diff).max(axis=2) > thr
    ys, xs = np.nonzero(hit)
    if ys.size == 0:
        return None
    return int(ys.min()), int(xs.min()), int(ys.max()), int(xs.max())


def _rle(y0: int, x0: int, h: int, w: int, value: int = 255) -> list:
    """一行一段的游程：[[y, x, len, value255], …]，引擎就是按这个形状收笔迹的。"""
    return [[y0 + r, x0, w, value] for r in range(h)]


def _max_step(img: np.ndarray) -> int:
    """四邻域最大绝对差。撕裂在这里的形状就是它：一处孤立的陡峭边。"""
    a = img.astype(np.int16)
    down = int(np.abs(np.diff(a, axis=0)).max()) if a.shape[0] > 1 else 0
    right = int(np.abs(np.diff(a, axis=1)).max()) if a.shape[1] > 1 else 0
    return max(down, right)


def _corner_bands(h: int, w: int) -> np.ndarray:
    """四角的背景带：离主体最远、最不该被局部层动到的像素。"""
    m = np.zeros((h, w), dtype=bool)
    ch, cw = max(2, h // 12), max(2, w // 6)
    m[:ch, :cw] = m[:ch, -cw:] = m[-ch:, :cw] = m[-ch:, -cw:] = True
    return m


def _face_box(h: int, w: int) -> np.ndarray:
    """面部区（程序化正脸的落点，见 packaging/make-test-portrait.py）。"""
    m = np.zeros((h, w), dtype=bool)
    m[int(h * 0.18):int(h * 0.70), int(w * 0.25):int(w * 0.75)] = True
    return m


def _undo_redo_pair(engine, peer, h, w, *, cmd: str, event: str):
    """对同一层做一次 undo→redo，返回（没有它的那一帧，有它的那一帧）。

    为什么用这一对而不是拿"导入那一帧"当基准：裁剪/旋转之后整幅画面都变了，与导入帧
    的差会盖过这一层本身，包围盒就量不出这一层了。同一裁剪态下的这两帧之差才只属于
    这一层。顺带这条路径本身就在判 MANUAL-002 的"可完整撤销 / 结果稳定"。
    """
    _drain(engine)
    engine.send(cmd=cmd, action="undo")
    engine.wait_for(event, timeout=120)
    off = _read_frame(engine, peer, h, w)
    _drain(engine)
    engine.send(cmd=cmd, action="redo")
    engine.wait_for(event, timeout=120)
    on = _read_frame(engine, peer, h, w)
    return off, on


def _deform_shot(engine, peer, h: int, w: int, amount: float):
    """发一条 deform，同时拿下【账单事件与那一帧】。

    不能直接用 `_wait_frame_mode`：它只认目标事件，`deform_done` 排在帧前面会被它
    一并吃掉——而紧支撑半径、作用面占比全部只在 `deform_done` 里。判据要用的数
    必须来自引擎报的那一份，不能在测试里自己算一个圆去猜。
    """
    import time as _t

    from test_protocol import _next_event
    _drain(engine)
    engine.send(cmd="deform", action="set", amounts={"slim_face": amount})
    done, deadline = None, _t.monotonic() + 120.0
    while _t.monotonic() < deadline:
        e = _next_event(engine, skip=("session_state", "engine_warn"),
                        timeout=min(10.0, max(0.1, deadline - _t.monotonic())))
        if e["event"] == "deform_done":
            done = e
        elif e["event"] == "frame" and e.get("mode") == "deform":
            assert done is not None, "帧先于账单到了：事件顺序与 cmd_deform 里写的不一样"
            return done, _frame_of(e, peer, h, w)
        elif e["event"] == "error":
            raise AssertionError(f"引擎拒绝 deform：{e.get('error')}")
    raise AssertionError("120s 内没等到 deform 那一帧")


# ---------------------------------------------------------------- MANUAL-001
@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像")
def test_brush_strokes_replay_through_zoom_rotate_crop_and_reopen(engine, extra_engine,
                                                                  tmp_path):
    """MANUAL-001：笔划在缩放/旋转/裁剪/重开后保持原图位置与半径语义。

    ① **半径语义是真的**：笔迹一个字节不改、只改 `radius`，作用范围必须跟着扩散。
       这是假滑块的照妖镜——把 radius 只当成一个显示数字的实现会在这一条上响；
    ② **显示缩放不改变结果**：视口变换不进引擎（协议命令面里根本没有它），笔迹按
       **代理帧尺寸**存进工程文件；
    ③ **裁剪后笔划跟着画面走**：裁左上 1/4 放大填回画布 → 笔迹包围盒同步放大 2 倍；
       按屏幕坐标成立的实现会保持原尺寸不动；
    ④ **重开项目**：换一个引擎进程打开工程，笔迹计数、参数与画面逐字节回来。
    """
    _needs_torch()
    meta = _open(engine, max_px=207360)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    base = _read_frame(engine, peer, h, w)      # load 那一帧：还没有任何笔迹

    y0, x0, sh, sw = STROKE
    _drain(engine)
    engine.send(cmd="light", action="add", rle=_rle(*STROKE), feather=0, sign=1)
    done = engine.wait_for("light_done", timeout=60)
    assert done["params"]["radius"] == DEFAULT_DB_RADIUS, done["params"]
    near = _read_frame(engine, peer, h, w)
    box_near = _bbox(near - base)
    assert box_near is not None, "修容笔落下去画面一动不动：假滑块"
    # 核心区必须被覆盖（扣掉带限半径还剩实心块），外扩不得超过半径 + 插值余量
    assert box_near[0] <= y0 + 4 and box_near[1] <= x0 + 4, \
        f"笔迹自身没被覆盖：包围盒 {box_near}，笔迹起点 {(y0, x0)}"
    assert box_near[2] >= y0 + sh - 5 and box_near[3] >= x0 + sw - 5, \
        f"笔迹右下沿没被覆盖：包围盒 {box_near}，笔迹 {(y0, x0, sh, sw)}"
    spread0 = max(y0 - box_near[0], x0 - box_near[1])
    assert spread0 <= DEFAULT_DB_RADIUS + 8, \
        f"半径 {DEFAULT_DB_RADIUS} 却外扩了 {spread0}px：作用域不受半径约束"

    _drain(engine)
    engine.send(cmd="light", action="params", radius=RADIUS_WIDE)
    engine.wait_for("light_done", timeout=60)
    wide = _read_frame(engine, peer, h, w)
    box_wide = _bbox(wide - base)
    step = RADIUS_WIDE - DEFAULT_DB_RADIUS
    grew = [box_near[0] - box_wide[0], box_near[1] - box_wide[1],
            box_wide[2] - box_near[2], box_wide[3] - box_near[3]]
    assert min(grew) >= step // 3, \
        f"radius {DEFAULT_DB_RADIUS}→{RADIUS_WIDE} 各边只扩了 {grew}px（应约 {step}px）：" \
        "半径没参与空间扩散，那是个假滑块"
    assert _live_state(engine)["light"]["radius"] == RADIUS_WIDE, "半径没落进 doc_state"

    # ③ 裁剪：笔迹跟着内容放大 2 倍（同一裁剪态下 undo/redo 两帧之差才只属于这一层）
    _drain(engine)
    engine.send(cmd="crop", rect=[0.0, 0.0, 0.5, 0.5])
    _wait_frame_mode(engine, "crop")
    off, on = _undo_redo_pair(engine, peer, h, w, cmd="light", event="light_done")
    box_crop = _bbox(on - off)
    assert box_crop is not None, "裁剪后笔迹消失了：笔迹没跟着画面走，或被整层丢了"
    assert _live_state(engine)["counts"]["light"] == 1, \
        "裁剪把笔迹层丢了：裁剪不是 PROXY_BOUND 的触发者，尺寸没变就该留着"
    # 基准必须是**同一半径**下那一次（box_wide）：带限半径是在几何层之前作用的，
    # 拿 radius=24 的包围盒去比 radius=60 的裁剪态会得到 3.15× 这种假错读数
    # （本轮就是这么错一次）。
    grow_w = (box_crop[3] - box_crop[1]) / max(box_wide[3] - box_wide[1], 1)
    grow_h = (box_crop[2] - box_crop[0]) / max(box_wide[2] - box_wide[0], 1)
    assert 1.5 <= grow_w <= 2.6 and 1.5 <= grow_h <= 2.6, \
        f"裁剪后笔迹尺度 {grow_w:.2f}×/{grow_h:.2f}×（期望约 2×）：笔迹按屏幕坐标成立了"

    # ④ 存盘 → 换一个引擎进程重开
    src_sha = _sha_of(FIXTURE)
    _created, saved = _create_and_save(engine, tmp_path, name="笔划重放")
    pfile = saved["path"]
    # 读回文件反查：笔迹资产是按**代理帧尺寸**存的（这就是"显示缩放不改变结果"的落点：
    # 视口变换既不在协议命令面里，也不参与这一层的坐标）
    raw = json.loads(Path(pfile).read_text(encoding="utf-8"))
    sizes = [a.get("shape") for a in (raw.get("assets") or {}).values()]
    assert [h, w] in sizes, f"笔迹掩膜不是按代理帧 {h}×{w} 存的：{sizes}"

    eng2 = extra_engine("brush-reopen")
    eng2.send(cmd="hello")
    eng2.wait_for("ready", timeout=90)
    eng2.send(cmd="set_device", device="cpu")
    eng2.wait_for("device_set", timeout=120)
    eng2.send(cmd="project", action="open", path=pfile)
    op = eng2.wait_for("project_opened", timeout=120)
    assert op["docs"] == 1 and op["missing_count"] == 0, op
    shm2 = eng2.wait_for("shm_ready", timeout=240)
    ready2 = eng2.wait_for("image_ready", timeout=240)
    assert (shm2["h"], shm2["w"]) == (h, w), f"重开换了代理档：{(shm2['h'], shm2['w'])}"
    ds2 = ready2["doc_state"]
    assert ds2["counts"]["light"] == 1, f"重开后笔迹层没了：{ds2['counts']}"
    assert ds2["light"]["radius"] == RADIUS_WIDE, f"重开后半径语义变了：{ds2['light']}"
    assert [round(v, 6) for v in ds2["crop"]["rect"]] == [0.0, 0.0, 0.5, 0.5], ds2["crop"]
    peer2 = FrameShm(shm2["name"])
    got = _frame_of(eng2.wait_for("frame", timeout=60), peer2, shm2["h"], shm2["w"])
    assert int(np.abs(got - on).max()) == 0, \
        f"重开后的画面与保存前差 {int(np.abs(got - on).max())} LSB：笔迹重放不是同一幅"
    assert _sha_of(FIXTURE) == src_sha, "打开/保存工程动了原片"


# ---------------------------------------------------------------- MANUAL-003
@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像")
def test_repair_target_mapping_survives_scale_and_reopen(engine, extra_engine, tmp_path):
    """MANUAL-003：修复的源点/目标点映射在改变缩放与重开后稳定；范围可见、可撤销。

    本实现里"目标点"就是那片掩膜，"源点"是它周围的取样上下文——判据落在三件可查的事：
    落点与掩膜同位（映射稳定）、undo 逐字节回到未修那一幅（可撤销、范围可见）、
    redo 与重开后逐字节回来（结果稳定）。"接近"在这条里不算证据。
    """
    _needs_torch()
    meta = _open(engine, max_px=207360)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    base = _read_frame(engine, peer, h, w)

    rect = (140, 300, 40, 40)
    _drain(engine)
    engine.send(cmd="inpaint", action="add", rle=_rle(*rect), feather=0, backend="builtin",
                smooth_iters=1, refine_iters=8)
    done = engine.wait_for("inpaint_done", timeout=240)
    assert done["action"] == "add" and done["backend"] == "builtin", done
    after = _read_frame(engine, peer, h, w)
    box = _bbox(after - base)
    y0, x0, rh, rw = rect
    assert box is not None, "消除笔落下后画面没变：修复范围不可见"
    assert abs(box[0] - y0) <= 8 and abs(box[1] - x0) <= 8, \
        f"修复落点偏了：包围盒 {box} vs 掩膜起点 {(y0, x0)}（源/目标映射不稳）"

    _drain(engine)
    engine.send(cmd="inpaint", action="undo")
    engine.wait_for("inpaint_done", timeout=120)
    back = _read_frame(engine, peer, h, w)
    assert int(np.abs(back - base).max()) == 0, \
        f"撤销消除笔后仍差 {int(np.abs(back - base).max())} LSB：撤销没真的还原"
    assert _live_state(engine)["counts"]["repair"] == 0, "计数没跟着撤销走"

    _drain(engine)
    engine.send(cmd="inpaint", action="redo")
    engine.wait_for("inpaint_done", timeout=240)
    redone = _read_frame(engine, peer, h, w)
    assert int(np.abs(redone - after).max()) == 0, "重做回来的修复与当初不是同一幅"

    # "改变缩放"：裁剪重采样之后仍然落在同一块内容上，然后存盘换进程重开
    _drain(engine)
    engine.send(cmd="crop", rect=[0.0, 0.0, 0.8, 0.8])
    crop_ev = _wait_frame_mode(engine, "crop")
    cropped = _frame_of(crop_ev, peer, h, w)
    off, on = _undo_redo_pair(engine, peer, h, w, cmd="inpaint", event="inpaint_done")
    box_crop = _bbox(on - off)
    assert box_crop is not None, "裁剪后修复层消失了：映射没跟着画面走"
    assert int(np.abs(on - cropped).max()) == 0, "redo 回来的那一帧与裁剪态当前画面不同"

    _created, saved = _create_and_save(engine, tmp_path, name="修复重放")
    eng2 = extra_engine("repair-reopen")
    eng2.send(cmd="hello")
    eng2.wait_for("ready", timeout=90)
    eng2.send(cmd="set_device", device="cpu")
    eng2.wait_for("device_set", timeout=120)
    eng2.send(cmd="project", action="open", path=saved["path"])
    eng2.wait_for("project_opened", timeout=120)
    shm2 = eng2.wait_for("shm_ready", timeout=240)
    ready2 = eng2.wait_for("image_ready", timeout=240)
    assert ready2["doc_state"]["counts"]["repair"] == 1, ready2["doc_state"]["counts"]
    peer2 = FrameShm(shm2["name"])
    got = _frame_of(eng2.wait_for("frame", timeout=60), peer2, shm2["h"], shm2["w"])
    assert int(np.abs(got - on).max()) == 0, \
        "重开后的画面（含裁剪与修复层）与保存前不同：源/目标映射在重开时漂了"


# ---------------------------------------------------------------- MANUAL-002
@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像")
def test_liquify_replay_undo_redo_is_continuous_and_fully_reversible(engine):
    """MANUAL-002：液化重放 → 撤销 → 重做，位移连续、结果稳定、可完整撤销、边界无拼缝。

    四条各自成立：撤销后**逐字节**回到无形变那一幅；重做那一帧与当初那一帧逐字节相同；
    邻域最大跳变不超过原图同一量 + 插值余量（撕裂的形状）；角上背景带一个字节都不动
    （"边界无拼缝"最外层、最不该被动到的像素）。
    """
    _needs_torch()
    meta = _open(engine, max_px=207360)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    # base 必须在 precompute 之前取：`wait_for("precompute_ready")` 会把队列里
    # 那一帧一并吃掉（它只等目标事件），之后再“等一条帧”必然超时——本轮真这么碎过。
    base = _read_frame(engine, peer, h, w)
    engine.send(cmd="precompute", backend="mediapipe")
    pc = engine.wait_for("precompute_ready", timeout=180)
    assert pc["backend"] == "mediapipe" and int(pc.get("num_faces", 0)) == 1, pc

    _drain(engine)
    engine.send(cmd="deform", action="set", amounts={"slim_face": 0.5, "big_eye": 0.3})
    warped = _frame_of(_wait_frame_mode(engine, "deform"), peer, h, w)
    d = warped - base
    assert int(np.abs(d).max()) > 0, "形变滑块推下去画面不动：假形变"
    assert _live_state(engine)["deform"]["built"] is True

    corners = _corner_bands(h, w)
    assert int(np.abs(d)[corners].max()) == 0, \
        f"角上背景被形变动了 {int(np.abs(d)[corners].max())} LSB：边界拼缝/越界"
    ref, got = _max_step(base), _max_step(warped)
    assert got <= ref + TEAR_SLACK_LSB, \
        f"形变后邻域最大跳变 {got} LSB 超过未形变 {ref} + 余量 {TEAR_SLACK_LSB}：出现撕裂"

    _drain(engine)
    engine.send(cmd="history", action="undo")
    undone = _frame_of(_wait_frame_mode(engine, "history_undo"), peer, h, w)
    assert int(np.abs(undone - base).max()) == 0, \
        f"撤销液化后差 {int(np.abs(undone - base).max())} LSB：不可完整撤销"
    _drain(engine)
    engine.send(cmd="history", action="redo")
    redone = _frame_of(_wait_frame_mode(engine, "history_redo"), peer, h, w)
    assert int(np.abs(redone - warped).max()) == 0, "重做的液化与当初不是同一幅：结果不稳定"


# ---------------------------------------------------------------- RAW-001
@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像")
def test_raw_whitelist_develops_for_real_and_never_passes_preview_as_raw(engine, tmp_path):
    """RAW-001：支持项完成明确的显影链；不支持项准确提示；内嵌预览不冒充 RAW 显影。

    ① 支持的 DNG 走真解码，`raw` 那一格要把显影链的关键事实报全（位深、CFA 排阵、
       黑/白点、解它的后端名字），并且 `used_preview is False` 而 `source` 有名字——
       "文件里有没有预览"与"这一帧是不是预览"**必须是两个字段**，合成一个就是冒充；
    ② 导出去反查文件：写出来的尺寸是源图那一个，原片哈希不变；
    ③ 后缀在名单里而内容不是 RAW（拿 JPEG 改名 .cr3）必须**明拒**，而且拒了就不许
       再发一帧——"报错归报错、画面照样给"等于静默换了一条渲染路径。
    """
    _need_export_env()
    mt = _load_mtd()
    from PIL import Image
    src = np.asarray(Image.open(FIXTURE).convert("RGB"))[128:1128, 256:928]
    dng = str(tmp_path / "acceptance.dng")
    mt.build(dng, src, black=256.0, white=16383.0)
    src_sha = _sha_of(dng)

    meta = _open(engine, path=dng, max_px=207360)
    raw = meta.get("raw") or {}
    assert raw, f"image_ready 没带 raw 段，显影链事实无处可查：{sorted(meta)}"
    assert raw["source"] in ("self_dng", "libraw"), \
        f"报不出是谁解的（source={raw.get('source')!r}）：'没有名字'与'不是预览'看着一样"
    assert raw["used_preview"] is False, "编辑会话这一帧来自相机内嵌预览：RAW 显影被预览冒充"
    assert int(raw["bits"]) >= 10 and list(raw["pattern"]), f"显影链缺位深/排阵：{raw}"
    assert float(raw["white"]) > float(raw["black"]), f"黑白点不成立：{raw}"

    out = tmp_path / "out"
    _drain(engine)
    engine.send(cmd="export", out_dir=str(out), format="png", tile=256, quality=90,
                images=[dng])
    done, _ = _collect_done(engine)
    assert done["failed"] == 0 and done["total"] == 1, done
    written = done["images"][0]["out"]
    assert Path(written).is_file(), f"报成功而文件不在：{written}"
    with Image.open(written) as im:
        assert im.size == (src.shape[1], src.shape[0]), \
            f"导出尺寸不是源图那一个：{im.size} vs {(src.shape[1], src.shape[0])}"
    assert _sha_of(dng) == src_sha, "导出改了 RAW 原片"

    fake = tmp_path / "not-really.cr3"
    fake.write_bytes(Path(FIXTURE).read_bytes())
    _drain(engine)
    engine.send(cmd="load_image", path=str(fake), strength=0.0)
    err = _expect_error(engine, "导入失败")
    assert "error" in err, err
    assert _quiet_after_error(engine, timeout=2.0), \
        "坏 RAW 容器被拒之后还发来一帧：静默退成了别的渲染路径"


def _quiet_after_error(engine, *, timeout: float = 2.0) -> bool:
    """error 之后这段时间里确实没有 frame/shm_ready/image_ready（拒了就是没出帧）。"""
    import time as _t
    end = _t.monotonic() + timeout
    while _t.monotonic() < end:
        try:
            e = engine.next_event(timeout=0.5)
        except Exception:
            continue
        if e.get("event") in ("frame", "shm_ready", "image_ready"):
            return False
    return True


# ---------------------------------------------------------------- PORTRAIT-007
@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像")
def test_face_reshaping_is_controlled_continuous_and_protects_neighbouring_faces(engine):
    """PORTRAIT-007：目标变化可控且连续；不扭曲邻近人脸；"背景异常"那一半交人工。

    "可控"判三件事：slim_face 0.2→0.5→0.8 的作用强度与影响面**都单调增大**（不是
    每次随机），且最大那一级也不铺满画幅（≤60%）、**紧支撑圆外逐字节不动**（半径由
    引擎的 build 账单报，不是测试里猜的）；"连续"判邻域跳变余量；
    "不扭曲邻近人脸"由两条一起成立：单人图上远离面部的位置逐字节不动，多人图上这一条
    **整点不着**（SCOPE-001 的保护就是"绝不替你选一张脸"，因此第二张脸不可能被推）。
    用例原文最后那句"背景异常纳入人工审核"不在这里签：`case-map.json` 把本条标了
    manual，验收报告里它是 `manual_pending`，不是通过。
    """
    _needs_torch()
    meta = _open(engine, max_px=207360)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    base = _read_frame(engine, peer, h, w)      # 同 MANUAL-002：precompute 会吃掉这一帧
    engine.send(cmd="precompute", backend="mediapipe")
    pc = engine.wait_for("precompute_ready", timeout=180)
    assert int(pc.get("num_faces", 0)) == 1, pc

    corners, face = _corner_bands(h, w), _face_box(h, w)
    energy, areas = [], []
    support = None
    for amount in (0.2, 0.5, 0.8):
        done, f = _deform_shot(engine, peer, h, w, amount)
        if support is None:
            # 紧支撑半径由引擎报（不是测试里猜的一个数）：判据只能建在
            # 实现自己承诺的那条不变量上
            win = done["build"]["kinds"]["slim_face"]["window"]
            cx, cy, _R, _r0, r1 = [float(v) for v in win]
            yy, xx = np.mgrid[0:h, 0:w]
            support = np.hypot(xx - cx, yy - cy) > r1 * 1.02   # 留一点插值余量
            assert support.mean() > 0.05, \
                f"支撑圆盖住了整幅（窗={win}，画幅 {h}×{w}）：这条用例没有可判的\"背景\""
        d = np.abs(f - base)
        energy.append(float(d[face].mean()))
        assert int(d[corners].max()) == 0, \
            f"slim_face={amount} 时角上背景动了 {int(d[corners].max())} LSB：不是局部作用"
        # 紧支撑窗的那一条不变量：支撑圆之外必须逐字节不动。
        # （支撑圆**以内**会带动背景，那是局部性半径的物理，不是缺陷：上一版这里拿
        # “图像外沿 4px 必须为 0”当判据，而本图左边缘正好落在 1.48R（r1=1.60R）的
        # 过渡带里，量到 0.01→1 LSB / 0.8→26 LSB 且**随形变量线性增长**。把过渡带
        # 压窄能把外沿压成 0，代价是一圈更陡的环——ADR-0009 把那笔账记在那儿。）
        assert int(d[support].max()) == 0, \
            f"slim_face={amount} 时紧支撑圆外动了 {int(d[support].max())} LSB：\"背景不动\"是谎"
        changed = int((d.max(axis=2) > EPS).sum())
        areas.append(changed)
        assert changed <= int(h * w * 0.6), \
            f"slim_face={amount} 推了 {changed}/{h * w} 格（超过 60% 画幅）：整幅被推走"
        assert _max_step(f) <= _max_step(base) + TEAR_SLACK_LSB, \
            f"amount={amount} 出现撕裂（邻域跳变 {_max_step(f)}）"
    assert energy[0] < energy[1] < energy[2], f"形变量不可控（作用强度非单调）：{energy}"
    assert areas[0] < areas[1] < areas[2], f"作用面积不随形变量单调（控制不住）：{areas}"

    dual = _dual_or_explain()
    _drain(engine)
    engine.send(cmd="load_image", path=dual, strength=0.0, max_px=207360)
    engine.wait_for("shm_ready", timeout=240)
    engine.wait_for("image_ready", timeout=240)
    engine.send(cmd="precompute", backend="mediapipe")
    pc2 = engine.wait_for("precompute_ready", timeout=240)
    assert int(pc2.get("num_faces", 0)) >= 2, pc2
    _drain(engine)
    engine.send(cmd="deform", action="set", amounts={"slim_face": 0.5})
    err = _expect_error(engine, "多人")
    assert "error" in err, err
    st = _live_state(engine)
    assert st["deform"]["built"] is False and \
        all(abs(float(v)) == 0.0 for v in st["deform"]["amounts"].values()), \
        f"多人图被拒却留了半截形变状态：{st['deform']}"


# ---------------------------------------------------------------- COLOR-004
@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像")
def test_local_color_adjustment_stays_inside_the_painted_region(engine, extra_engine, tmp_path):
    """COLOR-004 局部调色：只对所选区域调色，蒙版外逐字节不动，撤销逐字节恢复，出片同口径。

    冻结件 `then` 的三句各对上一段判据，另外四条是这一仓自己加的硬规矩：

    ① "蒙版外变化在定义边缘范围内" → 差场必须整片落在笔迹框 + 羽化支撑之内，而四角
       背景带逐字节为 0（"局部"的反面就是它偷偷全图动了，而画面真的在变、看不出来）；
    ② "撤销恢复" → 走**全局 history**（不是参数回滚）：撤销那一帧与点火前那一帧逐字节
       相同，重做再逐字节回来。这条路同时判 DOC_FIELDS 快照与会话重挂（d3b 那一族）；
    ③ "无明显色边" → 差场的邻域最大跳变必须**严格小于**差场峰值：硬阶跃会把整段变化
       压在一格里（跳变==峰值），羽化把它摊开（跳变<峰值），振铃则会超过峰值；
    ④ 不许静默降级：没 precompute 时的 skin、一笔没画时的 brush，都必须明拒；
    ⑤ 落笔即生效：mask 那条命令自己把作用域切到 brush，并把 scope 随事件报回来；
    ⑥ 出片同口径：带区域导出与关掉整层再导相比，区域内有变化、区域外逐字节相同；
    ⑦ 重开工程：换进程打开工程文件，作用域与区域格数回来且画面逐字节相同。
    """
    _needs_torch()
    from PIL import Image

    meta = _open(engine, max_px=207360)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    base = _read_frame(engine, peer, h, w)
    y0, x0, sh, sw = STROKE
    feather = 2

    # ④ 两条"不许静默降级"：底衬还没有时整条拒，而且不许留下半截作用域
    _drain(engine)
    engine.send(cmd="grade", action="scope", scope="skin")
    err = _expect_error(engine, "precompute")
    assert "skin" in err["error"], err
    _drain(engine)
    engine.send(cmd="grade", action="scope", scope="brush")
    _expect_error(engine, "一笔")
    st = _live_state(engine)["grade"]
    assert st["scope"] == "all" and st["mask_px"] == 0 and st["lit"] is False, \
        f"被拒的两条留下了半截状态：{st}"

    # ⑤ 落笔：区域挂上并把作用域切到 brush，可这一层还没点火，所以画面一分不动
    _drain(engine)
    engine.send(cmd="grade", action="mask", rle=_rle(*STROKE), feather=feather, mode="replace")
    done = engine.wait_for("grade_done", timeout=60)
    assert done["grade_scope"] == "brush" and done["grade_lit"] is False, done
    assert done["mask_px"] > sh * sw, f"区域格数比笔迹还小：{done['mask_px']} < {sh * sw}"
    stroke_frame = _read_frame(engine, peer, h, w)
    assert int(np.abs(stroke_frame - base).max()) == 0, "层没点火却动了画面"

    # 点火：只该作用在区域内
    _drain(engine)
    engine.send(cmd="grade", action="set", dh=0.006, ds=-0.14, dv=0.05)
    done = engine.wait_for("grade_done", timeout=60)
    assert done["grade_lit"] is True and done["grade_scope"] == "brush", done
    assert done["bytes_grade"] > 0, f"brush 作用域没常驻掩膜权重，账单却报 0：{done}"
    graded = _read_frame(engine, peer, h, w)
    d = np.abs(graded - base).max(axis=2)
    peak = int(d.max())
    assert peak > EPS, f"区域内一点没动（峰值 {peak} LSB）：局部调色是假的"

    # ① 判据一：差场整片落在笔迹框外扩（羽化支撑 + 插值余量）之内
    inside = np.zeros((h, w), dtype=bool)
    inside[y0:y0 + sh, x0:x0 + sw] = True
    assert int(d[inside].mean()) > 0, "笔迹实心区没被覆盖"
    slack = feather + 2
    allowed = np.zeros((h, w), dtype=bool)
    allowed[max(y0 - slack, 0):min(y0 + sh + slack, h),
            max(x0 - slack, 0):min(x0 + sw + slack, w)] = True
    outside_lsb = int(d[~allowed].max())
    assert outside_lsb == 0, f"笔迹框外扩 {slack} 格之外仍变了 {outside_lsb} LSB：不是局部调色"
    corners = _corner_bands(h, w)
    assert int(d[corners].max()) == 0, "四角背景被局部调色带动"

    # ③ 判据三：羽化必须把台阶摊开（跳变 < 峰值），且不许过冲（跳变 ≤ 峰值）
    step = int(np.abs(np.diff(d.astype(np.int16), axis=1)).max())
    assert step <= peak, f"边界振铃：跳变 {step} 超过整片变化峰值 {peak}"
    assert step < peak, f"羽化没摊开台阶：跳变 {step} == 峰值 {peak}（那是硬边）"

    # ② 判据二：全局撤销/重做逐字节回得来、去得回
    _drain(engine)
    engine.send(cmd="history", action="undo")
    hs = engine.wait_for("history_state", timeout=60)
    undid = _read_frame(engine, peer, h, w)
    assert hs["doc_state"]["grade"]["lit"] is False, hs["doc_state"]["grade"]
    assert hs["doc_state"]["grade"]["scope"] == "brush", \
        f"撤销该退参数而不是退区域：{hs['doc_state']['grade']}"
    assert int(np.abs(undid - stroke_frame).max()) == 0, \
        f"撤销后与点火前差 {int(np.abs(undid - stroke_frame).max())} LSB：撤销没逐字节恢复"
    _drain(engine)
    engine.send(cmd="history", action="redo")
    engine.wait_for("history_state", timeout=60)
    redid = _read_frame(engine, peer, h, w)
    assert int(np.abs(redid - graded).max()) == 0, "重做没回到同一幅：重放不是确定性的"

    # ⑥ 出片同口径：带着区域导一次，关掉整层再导一次
    src_shape = (int(meta["src_h"]), int(meta["src_w"]))
    out_a, out_b = tmp_path / "local-on", tmp_path / "local-off"
    out_a.mkdir(); out_b.mkdir()
    _drain(engine)
    engine.send(cmd="export", out_dir=str(out_a), format="png", tile=256, quality=90,
                images=[FIXTURE])
    da, _ = _collect_done(engine)
    assert da["failed"] == 0, da
    skipped_a = da["images"][0].get("skipped") or []
    assert not any("grade" in str(s) for s in skipped_a), \
        f"带区域的局部调色在导出里被整层放下了：{skipped_a}"
    with Image.open(da["images"][0]["out"]) as im:
        arr_a = np.asarray(im.convert("RGB"), dtype=np.uint8)
    assert arr_a.shape[:2] == src_shape, f"导出尺寸不是源图那一幅：{arr_a.shape[:2]}"

    _drain(engine)
    engine.send(cmd="grade", action="clear")
    engine.wait_for("grade_done", timeout=60)
    engine.send(cmd="export", out_dir=str(out_b), format="png", tile=256, quality=90,
                images=[FIXTURE])
    db, _ = _collect_done(engine)
    with Image.open(db["images"][0]["out"]) as im:
        arr_b = np.asarray(im.convert("RGB"), dtype=np.uint8)
    de = np.abs(arr_a.astype(np.int16) - arr_b.astype(np.int16)).max(axis=2)
    sy, sx = src_shape[0] / h, src_shape[1] / w
    full = np.zeros(arr_a.shape[:2], dtype=bool)
    full[int(y0 * sy):int((y0 + sh) * sy), int(x0 * sx):int((x0 + sw) * sx)] = True
    assert int(de[full].mean()) > 0, \
        "导出里区域内没有变化：屏幕上的局部调色没跟到文件（所见非所出）"
    band = np.zeros(arr_a.shape[:2], dtype=bool)
    band[max(int(y0 * sy) - 8, 0):min(int((y0 + sh) * sy) + 8, arr_a.shape[0]),
         max(int(x0 * sx) - 8, 0):min(int((x0 + sw) * sx) + 8, arr_a.shape[1])] = True
    edge_out = int(de[~band].max())
    assert edge_out == 0, f"导出把局部调色漏到了区域外（{edge_out} LSB）：文件里它是全图的"

    # 重新点火 → 存工程 → 换进程重开（⑦）
    _drain(engine)
    engine.send(cmd="grade", action="set", dh=0.006, ds=-0.14, dv=0.05)
    engine.wait_for("grade_done", timeout=60)
    lit_frame = _read_frame(engine, peer, h, w)
    src_sha = _sha_of(FIXTURE)
    _created, saved = _create_and_save(engine, tmp_path, name="局部调色")
    raw = json.loads(Path(saved["path"]).read_text(encoding="utf-8"))
    sizes = [a.get("shape") for a in (raw.get("assets") or {}).values()]
    assert [h, w] in sizes, f"调色区域不是按代理帧 {h}×{w} 存的：{sizes}"

    eng2 = extra_engine("color004-reopen")
    eng2.send(cmd="hello")
    eng2.wait_for("ready", timeout=90)
    eng2.send(cmd="set_device", device="cpu")
    eng2.wait_for("device_set", timeout=120)
    eng2.send(cmd="project", action="open", path=saved["path"])
    eng2.wait_for("project_opened", timeout=120)
    shm2 = eng2.wait_for("shm_ready", timeout=240)
    ready2 = eng2.wait_for("image_ready", timeout=240)
    g2 = ready2["doc_state"]["grade"]
    assert g2["scope"] == "brush" and g2["mask_px"] > 0 and g2["lit"] is True, g2
    peer2 = FrameShm(shm2["name"])
    got = _frame_of(eng2.wait_for("frame", timeout=60), peer2, shm2["h"], shm2["w"])
    assert int(np.abs(got - lit_frame).max()) == 0, \
        f"重开工程后画面与保存前差 {int(np.abs(got - lit_frame).max())} LSB：区域重放不是同一幅"
    assert _sha_of(FIXTURE) == src_sha, "打开/保存工程动了原片"


# ------------------------------------------------------------------ PORTRAIT-003
def _face_region(h: int, w: int, box, shrink: float = 0.0) -> np.ndarray:
    """把归一化脸盒换算成代理帧上的布尔区；shrink 是把盒子往中心缩的比例。

    "另一个人没被动"这种判据要用**缩过的内芯**：两张脸之间的空隙未必大于形变支撑窗，
    拿整盒去要求逐字节为 0 会把"局部性半径"这条物理事实当成 bug 来响（ADR-0009 量过
    支撑窗是 1.6×脸半对角）。内芯之外我们改用"差场包围盒不许与另一张脸的整盒相交"来判。
    """
    x0, y0, x1, y1 = [float(v) for v in box]
    if shrink:
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        x0, x1 = cx - (cx - x0) * (1 - shrink), cx + (x1 - cx) * (1 - shrink)
        y0, y1 = cy - (cy - y0) * (1 - shrink), cy + (y1 - cy) * (1 - shrink)
    m = np.zeros((h, w), dtype=bool)
    m[max(int(y0 * h), 0):min(int(y1 * h), h), max(int(x0 * w), 0):min(int(x1 * w), w)] = True
    return m


def _current(engine, peer, h, w) -> np.ndarray:
    """把"现在这一帧"要出来：发一次中性曝光（ev=0.0 不改配方、签名与之前一致所以不进
    历史、不脏工程），但它一定走一遍 render→shm→frame。

    为什么不用 `_read_frame` 直等：被拒的命令与"只选型没点火"那两条根本不出帧
    （预计算完不重发帧是 cmd_precompute 里写明的口径），拿 wait_for("frame") 等它
    只会 30 s 超时——那是测试的错，不是引擎的错。而"此刻画面是什么"恰恰是这些
    不许改画面的判据要问的东西，所以由测试主动要一帧。
    """
    return _cmd_frame(engine, peer, h, w, cmd="exposure", ev=0.0)


@pytest.mark.skipif(not os.path.isfile(DUAL), reason="缺多人测试图（生成见 packaging/make-test-dual-portrait.py）")
def test_editing_one_person_leaves_the_other_untouched(engine, extra_engine, tmp_path):
    """PORTRAIT-003 多人照片仅编辑指定人物：改谁由用户显式选定，另一个人不动。

    冻结件的 `then` 两句各对一段判据，另外五条是这一仓的硬规矩：

    ① "第二人有效配方不变" → 推 A 时 B 的脸盒内芯**逐字节 0 LSB**，而差场包围盒与 B 的
       整盒不相交（B 被推过又说成"没动"是最难复查的谎）；
    ② "影响在第一人蒙版边缘内" → 同一份差场必须落在 A 的脸盒外扩（支撑窗余量）之内；
    ③ 没选定之前整条拒（SCOPE-001 不许静默选型），错误里要写清怎么放行；
    ④ 越界 index 明拒且不改状态（静默钳到 0 就是拿"你选了 7"去服务 0 号）；
    ⑤ 选型本身不是编辑：没点火时换人，画面一分不许动；
    ⑥ 换人时形变层跟着搬走：推完 A 再选 B，A 的内芯必须回到出厂字节——效果不许留在
       别人脸上（那正是"第二个人被悄悄改了"的形状）；
    ⑦ 全局撤销/重做把选型也带回去，且画面逐字节对得上；
    ⑧ 出片同口径：带 B 的选型导出，文件里 A 的内芯与不导形变时逐字节相同；
    ⑨ 重开工程：换进程打开，选型（index/脸盒/显式位）回来且画面逐字节相同，原片哈希不动。
    """
    _needs_torch()
    import importlib.util
    from PIL import Image

    if importlib.util.find_spec("mediapipe") is None:
        pytest.fail("运行时没装 mediapipe：分人编辑的核心就是「探到每一张脸」，这条不许"
                    "退成 skip（skip 不是通过），装它见 engine/requirements-mediapipe.txt")
    path = _dual_or_explain()
    meta = _open(engine, path=path)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    engine.send(cmd="precompute", backend="mediapipe")
    pc = engine.wait_for("precompute_ready", timeout=180)
    assert int(pc.get("num_faces", 0)) == 2, f"多人输入没被真检测器报成 2 张脸：{pc.get('num_faces')}"
    faces = sorted(pc.get("faces") or [], key=lambda f: f["index"])
    assert len(faces) == 2, f"名单里只有 {len(faces)} 个人：另一个人没有可编辑的几何"
    assert pc.get("scope_block") == "multi_face", "选型把多人事实抹掉了（SCOPE-001 的 P0 判据会失去意义）"
    # 左右各一位（按脸盒中心排），后面所有"谁被动/谁没动"都按这两个格子算
    left, right = sorted(faces, key=lambda f: f["box"][0] + f["box"][2])
    a, b = right["index"], left["index"]           # 先推右边那位，判据里叫 A
    box_a, box_b = right["box"], left["box"]
    core_a = _face_region(h, w, box_a, shrink=0.25)
    core_b = _face_region(h, w, box_b, shrink=0.25)
    st = _live_state(engine)["face"]
    assert st["blocked"] is True and st["explicit"] is False, st

    base = _current(engine, peer, h, w)

    # ③ 没选定 → 整条拒，且错误里带着放行那条路；状态不许留半截
    _drain(engine)
    engine.send(cmd="deform", action="set", amounts={"slim_face": 0.6})
    err = _expect_error(engine, "SCOPE-001")
    assert "张脸" in err["error"] and "face select" in err["error"], err
    d0 = _live_state(engine)
    assert d0["deform"]["built"] is False and d0["face"]["explicit"] is False, d0
    assert int(np.abs(_current(engine, peer, h, w) - base).max()) == 0, "被拒的形变偷偷上了画面"

    # ④ 越界与坏类型都明拒（静默钳到 0 会得到"选了 7 而动的是 0 号"）
    for bad in (7, -1, 2 if faces[-1]["index"] == 1 else 3):
        _drain(engine)
        engine.send(cmd="face", action="select", index=bad)
        e = _expect_error(engine, "不在名单里")
        assert "2 张脸" in e["error"], e
    _drain(engine)
    engine.send(cmd="face", action="select", index="abc")
    _expect_error(engine, "face index")
    st = _live_state(engine)["face"]
    assert st["index"] == 0 and st["explicit"] is False and st["blocked"] is True, st

    # ⑤ 选定 A：这一步只是"接下来改谁"，画面一分不许动
    _drain(engine)
    engine.send(cmd="face", action="list")
    lst = engine.wait_for("face_list", timeout=60)
    assert len(lst["faces"]) == 2 and lst["blocked"] is True, lst
    engine.send(cmd="face", action="select", index=a)
    ev = engine.wait_for("face_selected", timeout=60)
    assert ev["index"] == a and ev["explicit"] is True and ev["blocked"] is False, ev
    assert [round(v, 3) for v in ev["box"]] == [round(v, 3) for v in box_a], \
        f"报回来的脸盒不是 A 的那一张：{ev['box']} vs {box_a}"
    # 宿主那一个槽位（status.face）是多源汇入的，它靠事件里 `face` 这一格认出对象。
    # 装机真窗口第一轮就撞在这里：事件只平铺、不嵌套，宿主读出 None，于是"点了人而面板
    # 一动不动"——裸引擎的用例全绿，因为没人读那一格。这条把两种形状钉在一起。
    assert isinstance(ev.get("face"), dict) and ev["face"]["index"] == ev["index"] \
        and ev["face"]["blocked"] is False, f"face_selected 没带嵌套那一份：{sorted(ev)}"
    assert int(np.abs(_current(engine, peer, h, w) - base).max()) == 0, "选个人就把画面改了"

    # ①② 推 A：A 的内芯真动了，B 的内芯逐字节不动，且差场不与 B 的整盒相交
    _drain(engine)
    engine.send(cmd="deform", action="set", amounts={"slim_face": 0.9, "big_eye": 0.6})
    done = engine.wait_for("deform_done", timeout=90)
    assert done["built"] is True and done["lit"] is True, done
    assert done["landmark_backend"] == "mediapipe", done
    pushed = _current(engine, peer, h, w)
    d = np.abs(pushed - base).max(axis=2)
    assert int(d[core_a].max()) > EPS, "选了 A 并推了滑块，A 的内芯却一点没动：假控件"
    left_b = int(d[core_b].max())
    assert left_b == 0, f"推 A 时 B 的脸盒内芯动了 {left_b} LSB：改一个人动了另一个人"
    # ② "图像影响在定义的第一人蒙版边缘内"：形变用的是**紧支撑圆盘**（ADR-0009：支撑半径
    # 1.6×脸半对角），不是脸盒外扩——第一版判据拿"脸盒 + 0.65R 的矩形"去要求逐字节 0，
    # 实测响在 24 LSB 上；探针量到的是：最远一位变化格在 1.58R，>1.6R 的格子数 0。
    # 也就是说窗是真的紧，而我把允许区写小了——修的是判据，不是把响当噪声压掉。
    ax0, ay0, ax1, ay1 = [v * [w, h, w, h][i] for i, v in enumerate(box_a)]
    R = 0.5 * float(np.hypot(ax1 - ax0, ay1 - ay0))
    yy, xx = np.mgrid[0:h, 0:w]
    outside = np.hypot(xx - (ax0 + ax1) / 2.0, yy - (ay0 + ay1) / 2.0) > 1.6 * R
    out_a = int(d[outside].max())
    assert out_a == 0, (f"以脸心为心、1.6×半对角（{int(1.6 * R)} px）的支撑窗之外仍变了 "
                        f"{out_a} LSB：作用面超出那一个人")

    # ⑥ 换成 B：效果必须整个搬走——A 的内芯回到出厂字节
    _drain(engine)
    engine.send(cmd="face", action="select", index=b)
    ev2 = engine.wait_for("face_selected", timeout=60)
    assert ev2["index"] == b and ev2["box"] is not None, ev2
    pushed_b = _current(engine, peer, h, w)
    d2 = np.abs(pushed_b - base).max(axis=2)
    back_a = int(d2[core_a].max())
    assert back_a == 0, f"换成 B 后 A 的内芯还留着 {back_a} LSB：形变层没跟着换人"
    assert int(d2[core_b].max()) > EPS, "选了 B 而 B 没被动：换人不生效"

    # ⑦ 全局撤销：退掉这次选型，回到 A（画面逐字节等于推 A 那一幅）
    _drain(engine)
    engine.send(cmd="history", action="undo")
    hs = engine.wait_for("history_state", timeout=60)
    assert hs["doc_state"]["face"]["index"] == a, hs["doc_state"]["face"]
    undid = _current(engine, peer, h, w)
    assert int(np.abs(undid - pushed).max()) == 0, \
        f"撤销选型后与推 A 那一幅差 {int(np.abs(undid - pushed).max())} LSB：选型没进历史"
    _drain(engine)
    engine.send(cmd="history", action="redo")
    engine.wait_for("history_state", timeout=60)
    redid = _current(engine, peer, h, w)
    assert int(np.abs(redid - pushed_b).max()) == 0, "重做没回到 B 那一幅：重放不是确定性的"

    # ⑧ 出片同口径：带着 B 的选型导一次，再关掉形变导一次
    src_shape = (int(meta["src_h"]), int(meta["src_w"]))
    out_on, out_off = tmp_path / "person-on", tmp_path / "person-off"
    out_on.mkdir(); out_off.mkdir()
    _drain(engine)
    engine.send(cmd="export", out_dir=str(out_on), format="png", tile=256, quality=90,
                images=[path])
    da, _ = _collect_done(engine)
    assert da["failed"] == 0, da
    skipped = da["images"][0].get("skipped") or []
    assert not any("deform" in str(s) for s in skipped), \
        f"分人形变在导出里被整层放下了：{skipped}"
    with Image.open(da["images"][0]["out"]) as im:
        arr_on = np.asarray(im.convert("RGB"), dtype=np.uint8)
    assert arr_on.shape[:2] == src_shape, f"导出尺寸不是源图那一幅：{arr_on.shape[:2]}"
    _drain(engine)
    engine.send(cmd="deform", action="clear")
    engine.wait_for("deform_done", timeout=60)
    engine.send(cmd="export", out_dir=str(out_off), format="png", tile=256, quality=90,
                images=[path])
    db, _ = _collect_done(engine)
    with Image.open(db["images"][0]["out"]) as im:
        arr_off = np.asarray(im.convert("RGB"), dtype=np.uint8)
    de = np.abs(arr_on.astype(np.int16) - arr_off.astype(np.int16)).max(axis=2)
    # 满幅那一侧的内芯：脸盒是归一化的，同一个 `_face_region` 换成源图尺寸再算一遍
    # （第二版这里手写了一遍缩放，把归一化坐标乘上了"代理→满幅的比例"而不是源图尺寸，
    # 于是掩膜整片空掉，`mean()` 得到一个 NaN——空掩膜上的任何断言都是空断言，
    # 所以下面先钉 `.size`，再谈大小。）
    core_b_full = _face_region(src_shape[0], src_shape[1], box_b, shrink=0.25)
    core_a_full = _face_region(src_shape[0], src_shape[1], box_a, shrink=0.25)
    assert core_b_full.sum() > 100 and core_a_full.sum() > 100, \
        f"满幅侧的内芯掩膜是空的（{int(core_b_full.sum())}/{int(core_a_full.sum())} 格）：断言没在量任何东西"
    assert int(de[core_b_full].mean()) > 0, "文件里 B 没被推：屏幕上的分人形变没跟到出片"
    leak = int(de[core_a_full].max())
    assert leak == 0, f"出片里 A 的内芯动了 {leak} LSB：导出把形变发给了另一个人"

    # ⑨ 重新点火 → 存工程 → 换进程重开
    _drain(engine)
    engine.send(cmd="face", action="select", index=a)
    engine.wait_for("face_selected", timeout=60)
    engine.send(cmd="deform", action="set", amounts={"slim_face": 0.9, "big_eye": 0.6})
    engine.wait_for("deform_done", timeout=90)
    lit_frame = _current(engine, peer, h, w)
    src_sha = _sha_of(path)
    _created, saved = _create_and_save(engine, tmp_path, name="分人编辑")
    raw = json.loads(Path(saved["path"]).read_text(encoding="utf-8"))
    rows = [d for d in raw["docs"] if d["path"] == os.path.abspath(path)]
    assert rows, f"工程里没有这张多人图：{[d['path'] for d in raw['docs']]}"
    # 配方里那一格直接读回：选型是文档状态，它必须在工程文件里（不在就是"重开少一半"）
    ver = rows[0]["versions"][0]
    assert ver.get("recipe") is not None, "这一版没有配方：存工程存了个空壳"

    eng2 = extra_engine("portrait003-reopen")
    eng2.send(cmd="hello")
    eng2.wait_for("ready", timeout=90)
    eng2.send(cmd="set_device", device="cpu")
    eng2.wait_for("device_set", timeout=120)
    eng2.send(cmd="project", action="open", path=saved["path"])
    eng2.wait_for("project_opened", timeout=120)
    # 按事件流的本来的顺序收：wait_for 会把别的类型丢掉，而重开这一路会连着发
    # shm_ready / (自动的 precompute_ready) / vram_ready / image_ready——先等 precompute
    # 再把 image_ready 丢了，就会得到一个"引擎没报 image_ready"的假失败（上一版就是这么响的）。
    got_ev = _collect(eng2, "image_ready", timeout=240)
    shm2 = got_ev["shm_ready"][-1]
    # 重开那一条路必须自己把分析补回来（CORE-001“配方完整恢复”）：关键点不随工程文件走，
    # 而形变层靠它。上一版这里靠测试手动发一条 precompute，才暂时遮住了“重开后形变层被
    # 归零”这个真缺口。`_collect` 在 image_ready 那一条就返回，而自动补的分析发在它后面
    # （load_image 内部：先出帧、再按配方补 precompute），所以这里单独等一条。
    pc2 = eng2.wait_for("precompute_ready", timeout=240)
    assert int(pc2.get("num_faces", 0)) == 2, pc2
    # 分析那一条也得带嵌套的 face：重开时 image_ready 先出（那时还没关键点），面板要
    # 靠这条把名单与选型认回来，而不是等一次没人发的 face list
    assert isinstance(pc2.get("face"), dict) and pc2["face"]["blocked"] is False, \
        f"precompute_ready 没把选型报回宿主：{sorted(pc2)}"
    st2 = _live_state(eng2)["face"]
    assert st2["index"] == a and st2["explicit"] is True and st2["blocked"] is False, \
        f"重开工程后选型没回来：{st2}"
    peer2 = FrameShm(shm2["name"])
    got = _current(eng2, peer2, shm2["h"], shm2["w"])
    dd = np.abs(got.astype(np.int16) - lit_frame.astype(np.int16)).max(axis=2)
    df2 = _live_state(eng2)["deform"]
    assert df2["built"] is True and df2["defer"] is False, (
        f"重开后形变层没回到常驻：{df2}（配方里那一层必须完整恢复，CORE-001）")
    assert int(dd.max()) == 0, \
        f"重开后画面与保存前差 {int(dd.max())} LSB：换人重放不是同一幅"
    assert _sha_of(path) == src_sha, "打开/保存工程动了原片"


# ---------------------------------------------------------------- PORTRAIT-004
def _layer_shot(engine, peer, h, w, **payload):
    """发一条形变命令（可带 scope），把【账单事件 + 这一笔的帧】一起拿回来。

    不能只等帧：`default / overrides / overridden_kinds / inherited / scope` 全在
    `deform_done` 里，而事件次序是"先账单后帧"（cmd_deform 里钉着的次序）。判据要用
    的数一律取自引擎报的那一份，不在测试里自己合成第二份出处。
    """
    import time as _t

    from test_protocol import _next_event
    _drain(engine)
    engine.send(cmd="deform", **payload)
    done, deadline = None, _t.monotonic() + 180.0
    while _t.monotonic() < deadline:
        e = _next_event(engine, skip=("session_state", "engine_warn"),
                        timeout=min(10.0, max(0.1, deadline - _t.monotonic())))
        if e["event"] == "deform_done":
            done = e
        elif e["event"] == "frame" and e.get("mode") == "deform":
            assert done is not None, "帧先于账单到了：事件次序与 cmd_deform 里写的不一样"
            return done, _frame_of(e, peer, h, w)
        elif e["event"] == "error":
            raise AssertionError(f"引擎拒绝 deform（{payload}）：{e.get('error')}")
    raise AssertionError(f"180s 内没等到这一笔形变的帧：{payload}")


def _lsb(a: np.ndarray, b: np.ndarray) -> int:
    """两帧的最大逐格差（先升 int16：uint8 相减会在负差上回绕，246 不是 10）。"""
    return int(np.abs(a.astype(np.int16) - b.astype(np.int16)).max())


@pytest.mark.skipif(not os.path.isfile(DUAL), reason="缺多人测试图（生成见 packaging/make-test-dual-portrait.py）")
def test_person_override_follows_and_inherits_the_all_person_default(engine, extra_engine,
                                                                    tmp_path):
    """LNX-PORTRAIT-004 覆盖与继承：默认打底、逐张覆盖、恢复继承后全部按层级合成。

    冻结件 `then` 的三句各对一段**逐字节**判据（都在同一张多人图、同一条命令通路、
    真 mediapipe 关键点上量，不拿单元测试的合成状态冒充端到端）：

    ① "覆盖项继续生效" → 给 A 挂上 big_eye 覆盖后改默认（slim 0.5→0.2），A 的
       big_eye 一个 LSB 也不许跟着默认走，而 slim 必须跟着走；
    ② "未覆盖项跟随" → 从没被单独改过的那个人（B）在每一次默认变更后，有效值恰好
       等于默认那一组数（每格一个），且 `inherited` 为真、`overridden_kinds` 为空；
    ③ "恢复继承后全部按层级合成" → 走两条不同路径（0.9→inherit 与 0.4→inherit）
       回到同一个层级状态，两幅画面**逐字节相同**；同值重写也逐字节相同（合成只有
       `_effective_deform_amounts()` 一个出处，这两条就是它的对拍）；

    另外五条是本仓的硬规矩：
    ④ 多人未选定时 `scope=person` 与 `inherit` 整条拒（SCOPE-001 不许静默指派谁）；
    ⑤ 非法 scope / 非法 action / 多余参数当场拒，且层级一份不留、画面不动；
    ⑥ 覆盖按**脸盒**认人而不是按名单序号：换进程重开工程后 A 的覆盖回到 A 身上，
       选到 B 时读到的是默认（把覆盖记成 index 就会在这里响）；
    ⑦ 层级进撤销栈：undo 把"这一张被单独改过"整格退掉、画面回到纯默认那一幅，
       redo 再带回来；
    ⑧ 出片同口径：带着 A 的覆盖导出，文件里 A 的内芯变了而 B 的内芯逐字节不动。

    诚实边界（ADR-0011 §2.7）：一层形变服务一张脸。单位场只从被选中那一张脸的轮廓
    解控制点，所以"同时给两个人挂不同的效果"这一版做不到，也不许说成做到了；这里验
    的是"同一时刻生效的那一张，按默认 + 它自己的覆盖合成"。
    """
    _needs_torch()
    import importlib.util

    from PIL import Image

    if importlib.util.find_spec("mediapipe") is None:
        pytest.fail("运行时没装 mediapipe：这一条要真检测器给出两张脸的位置与脸盒，"
                    "不许退成 skip（skip 不是通过），装它见 engine/requirements-mediapipe.txt")
    path = _dual_or_explain()
    meta = _open(engine, path=path)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    engine.send(cmd="precompute", backend="mediapipe")
    pc = engine.wait_for("precompute_ready", timeout=180)
    assert int(pc.get("num_faces", 0)) == 2, f"多人输入没被真检测器报成 2 张脸：{pc.get('num_faces')}"
    faces = sorted(pc.get("faces") or [], key=lambda f: f["index"])
    left, right = sorted(faces, key=lambda f: f["box"][0] + f["box"][2])
    a, b = right["index"], left["index"]           # 与 PORTRAIT-003 同一套称呼：先推右边那位
    box_a, box_b = right["box"], left["box"]
    core_a = _face_region(h, w, box_a, shrink=0.25)
    core_b = _face_region(h, w, box_b, shrink=0.25)
    ZERO = _amounts()
    base = _current(engine, peer, h, w)

    def layered():
        return _live_state(engine)["deform"]

    def sel(idx):
        _drain(engine)
        engine.send(cmd="face", action="select", index=idx)
        engine.wait_for("face_selected", timeout=60)

    # ---- ⑤④ 五条不该收下的命令：先拒，再确认层级与画面都没被写过
    _drain(engine)
    engine.send(cmd="deform", action="set", scope="person", amounts={"big_eye": 0.9})
    err = _expect_error(engine, "SCOPE-001")
    assert "face select" in err["error"], f"多人未选定的覆盖被拒却没给出放行那条路：{err}"
    _drain(engine)
    engine.send(cmd="deform", action="inherit")
    _expect_error(engine, "SCOPE-001")
    for bad, sub in (({"action": "set", "scope": "everyone", "amounts": {"slim_face": 0.5}},
                      "未知 deform scope"),
                     ({"action": "melt", "amounts": {"slim_face": 0.5}}, "未知 deform action"),
                     ({"action": "set", "scope": "all", "amounts": {"slim_face": 0.5},
                       "person_index": 0}, "不认识的参数")):
        _drain(engine)
        engine.send(cmd="deform", **bad)
        _expect_error(engine, sub)
    st = layered()
    assert st["default"] == ZERO and st["overrides"] == [] and st["amounts"] == ZERO, \
        f"被拒的层级命令留下了半截：{st}"
    assert _lsb(_current(engine, peer, h, w), base) == 0, "被拒的形变动了画面"

    # ---- ② 全人物默认：选定 A 之后改这一层，A 被推而 B 的内芯逐字节不动
    sel(a)
    done, f_slim = _layer_shot(engine, peer, h, w, action="set", scope="all",
                               amounts={"slim_face": 0.5})
    assert done["scope"] == "all" and done["built"] is True and done["lit"] is True, done
    assert done["default"]["slim_face"] == 0.5 and done["inherited"] is True, done
    assert done["amounts"] == _amounts(slim_face=0.5, big_eye=0.0, small_chin=0.0), done
    d = np.abs(f_slim.astype(np.int16) - base.astype(np.int16)).max(axis=2)
    assert int(d[core_a].max()) > EPS, "改了全人物默认而选中那张没动：假控件"
    assert int(d[core_b].max()) == 0, "改默认时把没选中的那个人也推了"
    # 同一层的第二格：部分提交不许把上一格默认抹掉（写默认 ≠ 写合成结果）
    done2, _ = _layer_shot(engine, peer, h, w, action="set", scope="all",
                           amounts={"big_eye": 0.3})
    assert done2["default"] == _amounts(slim_face=0.5, big_eye=0.3, small_chin=0.0), done2

    # 换到 B：完全没有覆盖的人，有效值就是默认那一组数（②"未覆盖项跟随"）
    sel(b)
    st_b = layered()
    assert st_b["amounts"] == _amounts(slim_face=0.5, big_eye=0.3, small_chin=0.0), st_b
    assert st_b["inherited"] is True and st_b["overridden_kinds"] == [], st_b
    f_b_default = _current(engine, peer, h, w)
    db0 = np.abs(f_b_default.astype(np.int16) - base.astype(np.int16)).max(axis=2)
    assert int(db0[core_b].max()) > EPS and int(db0[core_a].max()) == 0, \
        "换人后形变层没跟着搬走（B 没动 / A 还留着）"

    # ---- ① 给 A 挂覆盖，然后改默认：覆盖那格不动，没被覆盖的那格跟着默认走
    sel(a)
    done3, f_ov = _layer_shot(engine, peer, h, w, action="set", scope="person",
                              amounts={"big_eye": 0.9})
    assert done3["scope"] == "person" and done3["inherited"] is False, done3
    assert done3["overridden_kinds"] == ["big_eye"], done3
    assert len(done3["overrides"]) == 1 and done3["overrides"][0]["amounts"] == {"big_eye": 0.9}, \
        done3
    assert [round(v, 3) for v in done3["overrides"][0]["box"]] == [round(v, 3) for v in box_a], \
        f"覆盖没挂在 A 的脸盒上：{done3['overrides'][0]['box']} vs {box_a}"
    assert done3["amounts"] == _amounts(slim_face=0.5, big_eye=0.9, small_chin=0.0), done3
    done4, f_ov2 = _layer_shot(engine, peer, h, w, action="set", scope="all",
                               amounts={"slim_face": 0.2})
    assert done4["default"] == _amounts(slim_face=0.2, big_eye=0.3, small_chin=0.0), done4
    assert done4["amounts"] == _amounts(slim_face=0.2, big_eye=0.9, small_chin=0.0), \
        f"改默认把 A 的覆盖也一起改了（覆盖项必须继续生效）：{done4['amounts']}"
    d4 = np.abs(f_ov2.astype(np.int16) - f_ov.astype(np.int16)).max(axis=2)
    assert int(d4[core_a].max()) > 0, "slim 从 0.5 改到 0.2 而 A 的画面没跟着走：未覆盖项没跟随默认"
    # 这时换到 B：她看到的就是新默认，A 那一格覆盖不许漏给她
    sel(b)
    st_b2 = layered()
    assert st_b2["amounts"] == _amounts(slim_face=0.2, big_eye=0.3, small_chin=0.0), st_b2
    assert st_b2["inherited"] is True and len(st_b2["overrides"]) == 1, \
        f"A 的覆盖必须还在名单里（不许抹），而 B 自己全程全继承：{st_b2}"

    # ---- ③ 恢复继承：两条路径回到同一个层级状态，画面逐字节相同
    sel(a)
    # 先把默认回到 slim 0.5（覆盖还在），这一幅就是"这一张带着覆盖"的样子
    _layer_shot(engine, peer, h, w, action="set", scope="all", amounts={"slim_face": 0.5})
    ref_ov, f_with_ov = _layer_shot(engine, peer, h, w, action="set", scope="person",
                                    amounts={"big_eye": 0.9})     # 同值重写
    assert ref_ov["amounts"] == _amounts(slim_face=0.5, big_eye=0.9, small_chin=0.0), ref_ov
    # 路径一：0.9 → inherit
    inh1, f_inherit_1 = _layer_shot(engine, peer, h, w, action="inherit")
    assert inh1["action"] == "inherit" and inh1["inherited"] is True, inh1
    assert inh1["overrides"] == [] and inh1["overridden_kinds"] == [], inh1
    assert inh1["amounts"] == _amounts(slim_face=0.5, big_eye=0.3, small_chin=0.0), \
        f"恢复继承后没有全按层级合成：{inh1['amounts']}"
    assert int(np.abs(f_inherit_1.astype(np.int16)
                      - f_with_ov.astype(np.int16)).max(axis=2)[core_a].max()) > 0, \
        "inherit 之后画面与带覆盖那一幅一模一样：恢复继承没落地"
    # 路径二：先覆盖成别的值（0.4）再 inherit —— 同一个层级状态必须给出同一幅像素
    _layer_shot(engine, peer, h, w, action="set", scope="person", amounts={"big_eye": 0.4})
    inh2, f_inherit_2 = _layer_shot(engine, peer, h, w, action="inherit")
    assert _lsb(f_inherit_1, f_inherit_2) == 0, \
        f"两条路径回到同一个层级状态而画面差 {_lsb(f_inherit_1, f_inherit_2)} LSB：合成不是一个出处"
    # 同值重写那一幅也要与"直接按默认"逐字节相同（幂等：层级相同 ⇒ 像素相同）
    _, f_default_only = _layer_shot(engine, peer, h, w, action="set", scope="all",
                                    amounts={"slim_face": 0.5, "big_eye": 0.3})
    assert _lsb(f_default_only, f_inherit_1) == 0, \
        f"只改默认与恢复继承走到同一组有效值而画面不同：{_lsb(f_default_only, f_inherit_1)} LSB"

    # ---- ⑦ 层级进撤销栈：undo 退掉"这一张被单独改过"，redo 再带回来
    _layer_shot(engine, peer, h, w, action="set", scope="person", amounts={"big_eye": 0.8})
    assert layered()["overridden_kinds"] == ["big_eye"], layered()
    _drain(engine)
    engine.send(cmd="history", action="undo")
    hs = engine.wait_for("history_state", timeout=60)
    ds = hs["doc_state"]["deform"]
    assert ds["overrides"] == [] and ds["inherited"] is True, f"undo 只退了合成结果没退层级：{ds}"
    assert _lsb(_current(engine, peer, h, w), f_inherit_1) == 0, \
        "undo 后画面没回到纯默认那一幅：层级重放与常驻层不是同一个出处"
    _drain(engine)
    engine.send(cmd="history", action="redo")
    engine.wait_for("history_state", timeout=60)
    rs = layered()
    assert rs["overridden_kinds"] == ["big_eye"] and rs["amounts"]["big_eye"] == 0.8, rs

    # ---- ⑧ 出片同口径：带着 A 的覆盖导一次，再把整层放下导一次
    src_shape = (int(meta["src_h"]), int(meta["src_w"]))
    out_on, out_off = tmp_path / "layer-on", tmp_path / "layer-off"
    out_on.mkdir(); out_off.mkdir()
    _drain(engine)
    engine.send(cmd="export", out_dir=str(out_on), format="png", tile=256, quality=90,
                images=[path])
    da, _ = _collect_done(engine)
    assert da["failed"] == 0, da
    assert not any("deform" in str(x) for x in (da["images"][0].get("skipped") or [])), \
        f"层级形变在导出里被整层放下了：{da['images'][0].get('skipped')}"
    with Image.open(da["images"][0]["out"]) as im:
        arr_on = np.asarray(im.convert("RGB"), dtype=np.uint8)
    _drain(engine)
    engine.send(cmd="deform", action="clear", scope="all")
    engine.wait_for("deform_done", timeout=60)
    engine.send(cmd="export", out_dir=str(out_off), format="png", tile=256, quality=90,
                images=[path])
    dbe, _ = _collect_done(engine)
    with Image.open(dbe["images"][0]["out"]) as im:
        arr_off = np.asarray(im.convert("RGB"), dtype=np.uint8)
    de = np.abs(arr_on.astype(np.int16) - arr_off.astype(np.int16)).max(axis=2)
    core_a_full = _face_region(src_shape[0], src_shape[1], box_a, shrink=0.25)
    core_b_full = _face_region(src_shape[0], src_shape[1], box_b, shrink=0.25)
    assert core_a_full.sum() > 100 and core_b_full.sum() > 100, \
        "满幅侧内芯掩膜是空的（空掩膜上的断言就是空断言）"
    assert int(de[core_a_full].mean()) > 0, "文件里 A 没被推：屏幕上的层级形变没跟到出片"
    assert int(de[core_b_full].max()) == 0, \
        f"出片里另一个人也动了 {int(de[core_b_full].max())} LSB：导出把形变发给了没选中的那张脸"

    # ---- ⑥ 换进程重开：覆盖按脸盒回到 A 身上，选到 B 读到的是默认
    src_sha = _sha_of(path)
    _layer_shot(engine, peer, h, w, action="set", scope="all",
                amounts={"slim_face": 0.5, "big_eye": 0.3})
    _layer_shot(engine, peer, h, w, action="set", scope="person", amounts={"big_eye": 0.9})
    lit_frame = _current(engine, peer, h, w)
    _created, saved = _create_and_save(engine, tmp_path, name="覆盖与继承")
    raw = json.loads(Path(saved["path"]).read_text(encoding="utf-8"))
    rows = [d for d in raw["docs"] if d["path"] == os.path.abspath(path)]
    assert rows, f"工程里没有这张多人图：{[d['path'] for d in raw['docs']]}"
    rec = rows[0]["versions"][0]["recipe"]
    assert (rec.get("_deform_default") or {}).get("slim_face") == 0.5, rec.get("_deform_default")
    assert len(rec.get("_deform_overrides") or []) == 1, \
        f"逐张覆盖没进工程文件（重开就会丢单独改过的那几张）：{rec.get('_deform_overrides')}"

    eng2 = extra_engine("portrait004-reopen")
    eng2.send(cmd="hello")
    eng2.wait_for("ready", timeout=90)
    eng2.send(cmd="set_device", device="cpu")
    eng2.wait_for("device_set", timeout=120)
    eng2.send(cmd="project", action="open", path=saved["path"])
    eng2.wait_for("project_opened", timeout=120)
    got_ev = _collect(eng2, "image_ready", timeout=240)
    shm2 = got_ev["shm_ready"][-1]
    pc2 = eng2.wait_for("precompute_ready", timeout=240)
    assert int(pc2.get("num_faces", 0)) == 2, pc2
    st2 = _live_state(eng2)["deform"]
    assert st2["built"] is True, f"重开后形变层没回到常驻（CORE-001）：{st2}"
    assert st2["overridden_kinds"] == ["big_eye"] and st2["amounts"]["big_eye"] == 0.9, \
        f"重开后 A 的覆盖没跟着回来：{st2}"
    peer2 = FrameShm(shm2["name"])
    assert _lsb(_current(eng2, peer2, shm2["h"], shm2["w"]), lit_frame) == 0, \
        "重开后画面与保存前不同：换进程重放不是同一幅"
    eng2.send(cmd="face", action="select", index=b)
    eng2.wait_for("face_selected", timeout=60)
    st3 = _live_state(eng2)["deform"]
    assert st3["inherited"] is True and st3["amounts"] == _amounts(slim_face=0.5, big_eye=0.3), \
        f"覆盖被记成了名单序号而不是脸盒：选到 B 却读到 {st3['amounts']}"
    assert _sha_of(path) == src_sha, "打开/保存工程动了原片"


# ------------------------------------------------------------------ PICK-001
@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像")
def test_pick_suggestions_are_explainable_overridable_and_never_touch_the_source(
        engine, tmp_path):
    """LNX-PICK-001 挑图建议：判据可复算、建议可覆盖、**没有任何一条路径动原片**。

    先把「AI」这两个字处理干净。冻结件与手册里这条叫「AI 挑图」，官网那套确实是训练出来的
    分类器；本仓没有那种权重，而 DoD §2 明令「严禁假滑块、假滤镜或伪装 AI」。所以这里交付的
    是**本地确定性度量**：dHash 汉明距离分近似组、拉普拉斯能量与相对自身对比度判糊、luma
    两端的裁切占比判欠/过曝、FaceMesh 478 点量眼睑睁开比。每一条都带 method 名、数值与
    阈值，任何人都能按名字复算——这一条把「功能名」让给了「能不能被复核」。

    冻结件 `then` 的两句各对一段端到端判据（真引擎子进程、真 mediapipe、真磁盘）：
    ① 「建议必须可覆盖，不会自动永久删除照片」→ 每一条建议 `overridable=True`、
       `auto_deleted/auto_trashed=False`，加上人工标签后重算报 `overridden_by_user=True`
       而读数一个不少；跑完前后**逐个文件 sha256 相同、目录条目一字不差**；
    ② 「近似分组与判定原因可见」→ `pick_done.groups` 给出成员与组内最优那一张，
       每条 reason 都有 method/value/threshold 与一句带着数值的中文说明。

    另外三条是本仓的硬规矩：
    ③ 未知 action / 未知档位 / 多余参数当场拒（拒绝文案里那条「名单在 ready 里」必须真在）；
    ④ 挑图不进撤销栈也不打工程脏标记：它是读出来的旁注，不是一次编辑（前后 history 账单相同）；
    ⑤ 没量到的那一格只说「没量到」：眼睑不可用时既不写「睁眼」也不写「闭眼」。
    """
    _needs_torch()
    import importlib.util
    import json as _json
    import time as _time

    from PIL import Image, ImageFilter

    from lumaretouch_engine import face as face_mod
    from lumaretouch_engine import picks as PK

    if importlib.util.find_spec("mediapipe") is None:
        pytest.fail("运行时没装 mediapipe：眼睑那一档要真 FaceMesh 的 478 点几何，"
                    "不许退成 skip（skip 不是通过），装它见 engine/requirements-mediapipe.txt")

    d = tmp_path / "set"
    d.mkdir()
    base = np.asarray(Image.open(FIXTURE).convert("RGB"), dtype=np.uint8)
    files: dict = {}

    def put(name: str, arr, *, jpeg: int = 0) -> str:
        p = str(d / (name + (".jpg" if jpeg else ".png")))
        if jpeg:
            Image.fromarray(arr).save(p, quality=jpeg)
        else:
            Image.fromarray(arr).save(p)
        files[name] = p
        return p

    put("base", base)
    put("near", np.clip(base.astype(np.int16) + 2, 0, 255).astype(np.uint8))
    put("soft", np.asarray(Image.fromarray(base).filter(
        ImageFilter.GaussianBlur(6.0)), dtype=np.uint8), jpeg=90)
    put("blown", np.clip(base.astype(np.float32) * 2.6 + 12, 0, 255).astype(np.uint8), jpeg=90)

    # 闭眼替身：把两只眼的眼裂按眼下肤色带涂平。对照必须**重新检测一次**再确认——
    # 拿原图的关键点去量涂平后的图是恒等的，那等于没做这个对照（标定台上就是这里先错过一次）
    h0, w0 = base.shape[:2]
    pts = np.asarray((face_mod.build("mediapipe")(base).all_landmarks
                      or [None])[0], dtype=np.float32)
    eyes = base.copy()
    for e in (PK.EYE_LEFT, PK.EYE_RIGHT):
        sub = pts[[e["outer"], e["inner"], e["upper"], e["lower"]], :2] * [w0, h0]
        x0, y0 = np.floor(sub.min(axis=0)).astype(int)
        x1, y1 = np.ceil(sub.max(axis=0)).astype(int)
        band = eyes[min(y1 + 6, h0 - 1):min(y1 + 12, h0), max(x0, 0):max(x1, 1)]
        tone = band.reshape(-1, 3).mean(axis=0).astype(np.uint8)
        eyes[max(y0, 0):min(y1, h0), max(x0, 0):min(x1, w0)] = tone
    put("closed", eyes)
    flat_lm = (face_mod.build("mediapipe")(eyes).all_landmarks or [None])[0]
    flat_read = PK.eye_openness(flat_lm, image_size=(w0, h0))
    open_read = PK.eye_openness(pts, image_size=(w0, h0))
    assert flat_read is not None and open_read is not None, "闭眼替身没量出可比读数"
    assert flat_read < PK.EYE_SENSITIVITY["strong"] < open_read, \
        f"闭眼替身不成立（睁开 {open_read:.4f} / 涂平后 {flat_read:.4f} / 强档 " \
        f"{PK.EYE_SENSITIVITY['strong']}）：这一条测的就不是「眼睑塌了」"

    before = {p: _sha_of(p) for p in files.values()}
    listing = sorted(os.listdir(d))

    engine.send(cmd="hello")
    ready = engine.wait_for("ready", timeout=90)
    assert "analyze" in (ready.get("pick_actions") or []), ready.get("pick_actions")
    assert ready.get("pick_fingerprint") == PK.fingerprint(), "ready 报的判据指纹与引擎不同版"
    assert set(ready.get("pick_sensitivities", {}).get("eyes", [])) == \
        set(PK.EYE_SENSITIVITY), "档位名单双出处（ready 与 picks 层必须同一份）"
    engine.send(cmd="session", action="add", paths=list(files.values()))
    ev_add = engine.wait_for("session_add", timeout=60)
    assert ev_add["added"] == len(files), ev_add

    # ---- ③ 三件不该收下的：先拒，再看它们有没有偷偷留下半截状态
    for bad, sub in (({"action": "delete"}, "未知 pick action"),
                     ({"action": "analyze", "blur": "ultra"}, "不在名单里"),
                     ({"action": "analyze", "auto_trash": True}, "不认识的参数")):
        _drain(engine)
        engine.send(cmd="pick", **bad)
        got = _expect_error(engine, sub)
        if sub == "未知 pick action":
            assert "analyze/stop/state" in got["error"], f"拒绝文案没给出那条路：{got}"
    engine.send(cmd="session", action="state")
    st0 = engine.wait_for("session_state", timeout=30)
    assert all(row.get("pick") is None for row in st0["docs"]), "被拒的挑图写脏了格子"

    def _run(**kw):
        # 两遍之间先等上一遍真落地：`pick_done` 之后线程还要补一条 session_state，
        # 那时再开一遍会被"已在跑"拒掉。这条拒绝是故意的（两条后台任务同时读几百张盘
        # 会互相把耗时算脏），而 `picks_running` 就是它唯一可见的凭据——顺手也测了它。
        for _ in range(60):
            engine.send(cmd="session", action="state")
            ss = engine.wait_for("session_state", timeout=30)
            if not ss.get("picks_running"):
                break
            _time.sleep(0.5)
        else:
            pytest.fail("等不到挑图线程落地：session_state 里 picks_running 一直是真")
        _drain(engine)
        engine.send(cmd="pick", action="analyze", **kw)
        start = engine.wait_for("pick_start", timeout=60)
        items: dict = {}
        prog: list = []
        done = None
        deadline = _time.time() + 300
        while _time.time() < deadline:
            ev = engine.next_event(timeout=2.0)
            if ev is None:
                continue
            name = ev.get("event")
            if name == "pick_item":
                items[os.path.basename(ev["path"])] = ev
            elif name == "pick_progress":
                prog.append(ev)
            elif name == "pick_done":
                done = ev
                break
            elif name == "error":
                pytest.fail(f"挑图进行中报了错：{ev}")
        assert done is not None, "等不到 pick_done"
        return start, items, prog, done

    engine.send(cmd="history", action="state")
    hist0 = engine.wait_for("history_state", timeout=30)
    start, items, prog, done = _run(eyes="strong")
    engine.send(cmd="history", action="state")
    hist1 = engine.wait_for("history_state", timeout=30)

    def _acct(ev):
        return _json.dumps({k: v for k, v in ev.items()
                            if k not in ("event", "action", "doc_state", "history_ms")},
                           sort_keys=True)

    # ---- ④ 挑图不是编辑动作：撤销栈与工程脏标记一个字节都不该动
    assert _acct(hist0) == _acct(hist1), \
        f"挑图进了撤销栈/改了工程状态：{_acct(hist0)} → {_acct(hist1)}"
    assert done["measured"] == len(files) and done["failed"] == 0 and done["stopped"] is False
    assert done["fingerprint"] == ready["pick_fingerprint"] == PK.fingerprint()
    assert done["eyes_backend"] == "mediapipe", f"眼睑那一档必须真是 FaceMesh 量的：{done}"
    assert len(prog) == len(files) and start["targets"] == len(files)
    assert done["thresholds"]["eyes"] == dict(PK.EYE_SENSITIVITY)

    by = {k: v for k, v in items.items()}
    assert set(by) == {os.path.basename(p) for p in files.values()}, sorted(by)
    # ---- ① 建议永远是可覆盖的旁注，而且这一层根本没有删除能力
    for name, it in by.items():
        assert it["overridable"] is True and it["auto_deleted"] is False \
            and it["auto_trashed"] is False, name
        assert it["schema"] == PK.SCHEMA and it["measures"]["algo"] == PK.ALGO_VERSION
        assert it["measures"]["decoded_from"] == "pixels", \
            f"这批都是位图，来源必须写 pixels（写错就是台账在撒谎）：{name}"
        for r in it["reasons"]:
            assert r.get("method") and "value" in r and "threshold" in r, (name, r)
            assert (r.get("text") or "").strip(), (name, r)
    # ---- ② 近似分组与原因可见
    gkey = {os.path.basename(files["base"]), os.path.basename(files["near"])}
    grp = [g for g in done["groups"] if set(os.path.basename(m) for m in g["members"]) >= gkey]
    assert grp, f"同一构图加 2 偏置的两张没进同一组：{done['groups']}"
    assert grp[0]["size"] >= 2 and grp[0]["leader"]
    sim = [r for it in by.values() for r in it["reasons"] if r["kind"] == "similar_group"]
    assert sim, f"进了组却没有「为什么像」的读数：{by.keys()}"
    assert all(r["method"] == "dhash64-hamming" and r["value"] <= r["threshold"] for r in sim)
    assert not any("删" in r["text"] for r in sim), "分组话越过了「像」这条线"
    for it in by.values():
        if os.path.basename(it["path"]) in gkey:
            assert "similar" in it["labels"], it["labels"]
    # 三件已知方向的变体各自被标出来（数值与阈值一起报，用户看得见按哪条线判的）
    soft_kinds = {r["kind"] for r in by["soft.jpg"]["reasons"]}
    assert soft_kinds & {"blur", "soft_vs_batch"}, \
        f"高斯糊 6.0 的那一张没被任何一条清晰度判据标出：{by['soft.jpg']['reasons']}"
    assert "overexposed" in by["blown.jpg"]["labels"], by["blown.jpg"]["labels"]
    blown = next(r for r in by["blown.jpg"]["reasons"] if r["kind"] == "overexposed")
    assert blown["value"] > blown["threshold"] and "死白" in blown["text"]
    closed = next((r for r in by["closed.png"]["reasons"] if r["kind"] == "eyes_closed"), None)
    assert closed is not None, f"涂平眼裂的那张在强档下没被标出：{by['closed.png']['reasons']}"
    assert closed["method"] == "facemesh-eye-aperture" and closed["value"] < closed["threshold"]
    assert "不是分类器" in closed["text"], closed["text"]
    # 睁开比在读数上必须**同方向**，但不许要求逐字节相等：引擎在 512 档上检测，测试在
    # 满幅上检测，同一张图这两个尺度量出来差约 4%（实测 0.21883 与 0.22795）。这件事
    # 正是"阈值只能当『要不要复核』的标记"的由来，写进 picks.EYE_SENSITIVITY 的注释。
    eng_eye = by["closed.png"]["measures"]["eye_open"]
    _t = PK.EYE_SENSITIVITY["strong"]
    assert eng_eye is not None and eng_eye < _t and flat_read < _t, \
        f"两个尺度必须落在阈值同侧：{eng_eye} vs {flat_read}（线 {_t}）"
    assert abs(eng_eye - flat_read) / flat_read < 0.10, f"同一几何不该差出一个量级：{eng_eye}"
    # 可复算性真正的那一半：**同一个输入两次跑，读数逐字节相同**（度量没有随机性）
    _, again1, _, _ = _run(eyes="strong", force=True, paths=[files["closed"]])
    _, again2, _, _ = _run(eyes="strong", force=True, paths=[files["closed"]])
    def _readings(it):
        """读数本体，去掉逐段耗时：那三格每次跑都不同，不属于"可复算"那句话。"""
        mm = dict(it["measures"])
        mm.pop("ms", None)
        return _json.dumps(mm, sort_keys=True)

    assert _readings(again1["closed.png"]) == _readings(again2["closed.png"]), \
        "度量不可复算：同一张图两次跑给出不同读数"
    assert any("不写「睁眼」" in (r.get("text") or "") for r in by["base.png"]["reasons"]) \
        or "eyes_unknown" not in {r["kind"] for r in by["base.png"]["reasons"]}
    # 眼睛本来睁着的那一张：不许有「闭眼」标签，也不许出现「没量到」的退路
    base_kinds = {r["kind"] for r in by["base.png"]["reasons"]}
    assert "eyes_closed" not in by["base.png"]["labels"] and "eyes_unknown" not in base_kinds,         by["base.png"]["reasons"]
    # ---- ①后半：人工标记优先，重算之后建议变成被压过的旁注
    engine.send(cmd="project", action="create", name="挑图工程", directory=str(tmp_path))
    engine.wait_for("project_created", timeout=60)
    idx_blown = next(i for i, row in enumerate(_rows(engine))
                     if os.path.basename(row["path"]) == "blown.jpg")
    engine.send(cmd="project", action="tag", index=idx_blown, tags=["客户已看"], label="keep")
    engine.wait_for("project_edited", timeout=30)
    _, items2, _, done2 = _run(eyes="strong", force=True, paths=[files["blown"]])
    assert _readings(items2["blown.jpg"]) == _readings(by["blown.jpg"]), \
        "重算把读数算变了：同一条判据应当给出同一个数"
    again = items2["blown.jpg"]
    assert again["overridden_by_user"] is True and again["overridable"] is True
    assert _readings(again) == _readings(by["blown.jpg"]), \
        "被人工标记压过之后读数应当原样还在（压过≠抹掉）"
    assert done2["count"] == 1
    # ---- 底片条那一格确实带着徽章要读的字段（UI 不许自己再算一份）
    # 先等这一遍真落地：跑着的时候 `picks_running` 就必须是真（上面那圈等待就在读它），
    # 落地之后才是假——两头的值都测到了才说明那一格不是恒假的装饰
    running_seen = False
    for _ in range(60):
        engine.send(cmd="session", action="state")
        st1 = engine.wait_for("session_state", timeout=30)
        if st1.get("picks_running"):
            running_seen = True
            _time.sleep(0.5)
            continue
        break
    else:
        pytest.fail("挑图线程没落地")
    assert st1.get("picks_running") is False
    for row in st1["docs"]:
        name = os.path.basename(row["path"])
        assert row.get("pick"), f"底片条那一格没带挑图建议，UI 只能自己猜：{name}"
        assert row["pick"]["labels"] == by[name]["labels"], name
    # ---- ①的磁盘那一半：一个字节没动，一条也没少，也没多出任何东西
    assert sorted(os.listdir(d)) == listing, "挑图动过那个目录里的文件名单"
    for p, sha in before.items():
        assert os.path.isfile(p), f"原片不见了：{p}"
        assert _sha_of(p) == sha, f"原片被改写了：{p}"


def _rows(engine) -> list:
    """从引擎取一次底片条（要 index 与 path 的对应关系时只能问引擎，不能自己数）。"""
    engine.send(cmd="session", action="state")
    return engine.wait_for("session_state", timeout=30)["docs"]
# ── BACKGROUND-001（背景/衣物边界，P1）────────────────────────────────────────
# 冻结件：given 发丝、透明边缘、多人和复杂衣物的样本；when 使用支持的背景或衣物模块；
# then 人像边界与目标区域保护通过；不支持场景明确失败并可恢复。
#
# 这一条不需要新能力——换底（ops/matting.py 的线性光合成 + 色键遮罩）已经在装机件里，
# 缺的是**那两句 then 的证据**。为了让"边界保护"有可核对的真值，这里不用影楼渐变夹具
# （背景在哪要猜），而是自己画一张几何已知的场景：纯灰底铺满四边、两块不相连的主体
# （第二块就当"另一个人/一件衣物"）、边缘做一次高斯羽化（就是"发丝/透明边缘"那一档）。
# 于是每一格像素属于哪一类（前景 / 背景 / 过渡带）是**算出来的**，不是看出来的。
BG_GRAY = 200          # 背景：铺满四边的纯色（色键的 _edge_median 就该报这个数）
BG_REF = [BG_GRAY, BG_GRAY, BG_GRAY]
FG_DARK = 60           # 主体：与背景差得足够远，d 归一化后远超 tol+softness
NEW_BG = [220, 30, 40]   # 换上去的底：红，便于按通道核对"没越界"
TOL = 0.12             # 色键默认档
# softness 两档取的是引擎**自己声明的域**（bg 校验：softness∈[0.001,1]，给 0 会被整条拒）。
# 实测（这套几何 + 300×220 代理帧）：0.001 档中间值 0 格、0.02 档 0 格（8-bit 量化下那一圈
# d∈(0.12,0.14) 里一格都没有）、0.12 档 160 格。断言按这些数钉，不按我对"羽化该有多少格"
# 的想象钉（ADR-0009 那条纪律：实测才能定档）。
SOFT_HARD = 0.001      # 域下界：这一档就是硬切
SOFT_WIDE = 0.12       # 宽羽化档
LSB = 1                # 量化余量：线性光合成来回取整最多差一格


def _bg_scene(tmp_path) -> str:
    """画那张几何已知的场景，存成 PNG（无损：真值必须是精确的，不能带 JPEG 噪声）。"""
    from PIL import Image, ImageDraw, ImageFilter
    w, h = 300, 220
    img = Image.new("RGB", (w, h), tuple(BG_REF))
    dr = ImageDraw.ImageDraw(img)
    dr.ellipse([70, 40, 190, 170], fill=(FG_DARK, FG_DARK, FG_DARK))       # 主体（"人像"）
    dr.rectangle([12, 150, 60, 205], fill=(FG_DARK, FG_DARK, FG_DARK))     # 第二块（"另一个人/衣物"）
    img = img.filter(ImageFilter.GaussianBlur(1.2))   # 边缘羽化：这一圈就是发丝/透明边缘那一档
    path = str(tmp_path / "bg-scene.png")
    img.save(path)
    return path


def _bg_truth(base: np.ndarray):
    """从**已加载的那一帧**上把三类像素算出来（不靠文件坐标：代理帧可能缩过放）。

    前景/背景用与色键同一个距离口径（到边框中位数色 BG_REF 的欧氏距离，归一化），
    所以这三类与引擎实际会算出的 alpha 是同一件事的两遍计算——一致才有资格当判据。
    """
    d = np.sqrt(((base.astype(np.float64) / 255.0
                  - np.asarray(BG_REF, dtype=np.float64)[None, None, :] / 255.0) ** 2).sum(axis=2))
    hi = TOL + SOFT_WIDE                              # 取最宽那一档的软硬边界
    core = d >= hi + 0.05                             # 稳稳的前景（alpha 必为 1）
    back = d <= TOL - 0.05                            # 稳稳的背景（alpha 必为 0）
    band = ~(core | back)                             # 过渡带
    return core, back, band


def _bg_load(engine, tmp_path):
    """hello → cpu → 载入那张场景（走引擎自己的解码，不塞数组），返回 (meta, peer, 帧)。"""
    _needs_torch()
    path = _bg_scene(tmp_path)
    engine.send(cmd="hello")
    engine.wait_for("ready")
    engine.send(cmd="set_device", device="cpu")
    engine.wait_for("device_set")
    engine.send(cmd="load_image", path=path, strength=0.0, max_px=300 * 220)
    meta = engine.wait_for("shm_ready", timeout=60)
    engine.wait_for("vram_ready", timeout=60)
    engine.wait_for("image_ready", timeout=60)
    peer = FrameShm(meta["name"])
    return meta, peer, _read_frame(engine, peer, meta["h"], meta["w"])



def _assert_no_new_frame(engine, peer, meta, ev: dict, expect: np.ndarray, what: str,
                         *, window: float = 1.5):
    """这一段时间里引擎**没出一帧**，并且上一帧那一格仍逐字节等于 expect。

    用在"被拒的命令不许动画面"这一类判据上。`_read_frame` 在这里是错的：它先等一条
    frame 事件，而"没有新帧"恰恰是要证的事——等不到就成了超时假失败，而不是判据本身。
    `ev` 是调用方一路记着的**最近那条 frame 事件**（不能用 engine.last_frame：wait_for
    命中目标事件时是**先返回**的，那一格根本没被记下来，读它会拿到 None）。
    """
    import time

    t_end = time.monotonic() + window
    while time.monotonic() < t_end:
        try:
            e = engine.next_event(timeout=min(0.3, max(0.01, t_end - time.monotonic())))
        except TimeoutError:
            continue
        if e.get("event") == "frame":
            raise AssertionError(f"{what}：被拒之后还出了一帧（画面被动过）")
        if e.get("event") == "bg_done":
            raise AssertionError(f"{what}：报 error 的同时还发了 bg_done（半截状态）")
    got = _frame_of(ev["frame"], peer, meta["h"], meta["w"])
    assert np.array_equal(got, expect), f"{what}：上一帧那一格与底片不一致"

def test_background_swap_protects_subject_edges_and_refuses_what_it_cannot_do(engine, tmp_path):
    """BACKGROUND-001：人像边界与目标区域保护 + 不支持场景明确失败并可恢复。

    五句判据，逐句对着冻结件的 then 来：
    ① 目标区域真的被换掉：alpha=0 那一片逐格等于要换上去的红底（±LSB）；
    ② 人像主体一格没动：alpha=1 那一片与换底前**逐字节相同**——换底污染到主体身上，
       用户在屏幕上看见的就是"人脸上蒙了一层红"；
    ③ 过渡带不越界：每一格每一通道都落在 [min(前景,新底), max(前景,新底)] ±LSB 内。
       这一句管的是发丝/透明边缘：正确的 over 合成只会在两个端点之间插值，任何比两端
       都亮或都暗的像素都是光晕（而 sRGB 域直接加权就会造出这种暗边——见 ops/matting.py
       顶部那段"为什么在线性光下做"）；
    ④ 羽化是 softness 给的、不是蒙出来的：域下界那一档（0.001）**一格中间值都不许有**
       （alpha 只取 0/1 的直接后果），宽档 0.12 必须长出中间值、且不超过我算出的过渡带；
       而 ② 的核心保护在两档下都仍然逐字节成立——"羽化"不许以吃掉主体边缘为代价；
    ⑤ 做不了的事要说出来、并且留得下后门：birefnet 无权重整条拒（不静默退成色键）、
       未知后端拒、衣物那类不存在的参数拒；三次拒绝画面都**一格没变**，且随后
       action=clear 逐字节回到换底前。
    """
    meta, peer, base = _bg_load(engine, tmp_path)
    core, back, band = _bg_truth(base)
    assert core.sum() > 2000 and back.sum() > 20000 and band.sum() > 200, (
        f"这一格的三类像素太少（core={core.sum()} back={back.sum()} band={band.sum()}）："
        "判据会是空的，测了等于没测")

    ev: dict = {}

    def swap(softness: float) -> np.ndarray:
        engine.send(cmd="background", action="set", backend="color_key",
                    bg=NEW_BG, tol=TOL, softness=softness)
        engine.wait_for("bg_done", timeout=30)
        ev["frame"] = engine.wait_for("frame", timeout=30)
        return _frame_of(ev["frame"], peer, meta["h"], meta["w"])

    hard = swap(SOFT_HARD)
    soft = swap(SOFT_WIDE)

    # ① 目标区域
    want = np.asarray(NEW_BG, dtype=np.int16)
    assert np.abs(hard[back].astype(np.int16) - want).max() <= LSB, \
        "背景那一片没换成指定底色：色键遮罩与合成对不上"
    # ② 人像主体一格没动（两档都是）
    for name, got in (("softness=0", hard), ("softness=0.12", soft)):
        assert np.array_equal(got[core], base[core]), (
            f"{name} 那档下主体核心区被换底动过（{int((np.abs(got[core] - base[core]).max(axis=1) > 0).sum())} 格）："
            "alpha=1 必须原样等于前景，这是合成层的逐字节不变式")
    # 第二块（"另一个人 / 一件衣物"）也在核心区里，② 已经把它一起保住了；这里再单独
    # 点一次名：两块互不相连的主体都要有像素落在 core 里，否则 ② 可能只保住了一大块
    ys, xs = np.nonzero(core)
    assert xs.min() < 65 and xs.max() > 90, "左边那块（第二个人/衣物）不在核心保护区里"

    # ③ 过渡带不越界：逐通道夹在两个端点之间
    f = base.astype(np.int16)
    b = np.broadcast_to(want, base.shape).astype(np.int16)
    lo = np.minimum(f, b) - LSB
    hi = np.maximum(f, b) + LSB
    g = soft.astype(np.int16)
    out_of_range = int(((g < lo) | (g > hi)).sum())
    assert out_of_range == 0, f"{out_of_range} 个通道越出两端点之间：换底造出了光晕/暗边"

    # ④ 羽化带随 softness 变宽，且不是靠啃主体边缘换来的
    def mid_count(img: np.ndarray) -> int:
        gg = img.astype(np.int16)
        is_back = np.abs(gg - b).max(axis=2) <= LSB
        is_front = np.abs(gg - f).max(axis=2) <= LSB
        return int((~(is_back | is_front)).sum())

    n_hard, n_soft = mid_count(hard), mid_count(soft)
    assert n_hard == 0, (
        f"域下界那一档（softness={SOFT_HARD}）本来就该是硬切（alpha 只取 0/1），"
        f"却出现 {n_hard} 格中间值：要么遮罩偷偷羽化了，要么合成端点不是我说的那两个数")
    assert 0 < n_soft <= int(band.sum()), (
        f"宽档中间值 {n_soft} 格（实测 160），它必须 >0 且不超过过渡带 {int(band.sum())} 格："
        "超出带界就是羽化在往主体/背景里啃")

    # ⑤ 不支持的三格：说得出理由、画面不动、还能整层撤掉
    engine.send(cmd="background", action="clear")
    engine.wait_for("bg_done", timeout=30)
    ev["frame"] = engine.wait_for("frame", timeout=30)
    cleared = _frame_of(ev["frame"], peer, meta["h"], meta["w"])
    assert np.array_equal(cleared, base), "clear 后没逐字节回到换底前（'可恢复'这半句就是假的）"

    for bad, why in (
        (dict(backend="birefnet", bg=NEW_BG), "神经网络抠图没权重就整条拒，不许静默退成色键"),
        (dict(backend="unet", bg=NEW_BG), "未知后端要说得出可用名单"),
        (dict(backend="color_key", bg=NEW_BG, garment="衬衫"), "衣物模块不存在：不认的参数要拒，不能吞掉"),
        (dict(backend="color_key", bg=NEW_BG, tol=TOL, softness=0.0),
         "softness 在声明域 [0.001,1] 之外要拒，并且要把域说出口"),
    ):
        engine.send(cmd="background", action="set", **bad)
        err = engine.wait_for("error", timeout=30)
        assert err, f"这一格没报错（{bad}）：{why}"
        if bad.get("softness") == 0.0:
            assert "0.001" in err["error"], (
                f"拒的时候没说清可用域，用户无从改起：{err['error']}")
        # 被拒 = 一格都不许动。这里不用 _read_frame（它会等一条 frame 事件，而**没有**
        # 新帧正是这条判据的内容）：先确认 1.5 s 内没有新帧，再按上一帧那条事件自带的
        # 槽号读回像素，与底片逐字节比。两次都要，缺一就漏判——只等事件会把"根本没渲染"
        # 当成通过，只读 shm 会把"渲染了但没发事件"漏掉。
        _assert_no_new_frame(engine, peer, meta, ev, base, f"被拒的 {bad}")

    # 拒完引擎照常活着，并且支持的这一档还能用（"明确失败"不许把会话一起打死）
    again = swap(0.06)
    assert not np.array_equal(again, base), "三次拒绝后色键换底应仍然可用"
    engine.send(cmd="background", action="clear")
    engine.wait_for("bg_done", timeout=30)
# ── PORTRAIT-012（表情调整：本版本做的那一格是「微笑嘴角」）────────────────────
def _detect_on(path):
    """在**出片**上再跑一次 MediaPipe，返回该图像素坐标下的 478 点。

    为什么自己跑而不问引擎：引擎报的是"我按哪份几何搬的控制点"，这里要问的是
    "搬完之后这张脸还认不认得出是同一个人"。缺后端就直接抛，不许退成模板几何——
    模板点是自己摆的，拿它当"检测结果"就是自证。
    """
    import importlib.util

    from PIL import Image

    from lumaretouch_engine import face as face_mod

    if importlib.util.find_spec("mediapipe") is None:
        pytest.fail("运行时没装 mediapipe：表情这一条要在出片上重测关键点，"
                    "不许退成模板几何（装法见 engine/requirements-mediapipe.txt）")
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)
    pc = face_mod.build("mediapipe")(rgb)
    assert pc.num_faces == 1, f"出片上认出 {pc.num_faces} 张脸，这条判据失去对象"
    return np.asarray(pc.landmarks, dtype=np.float64)[:, :2] * [rgb.shape[1], rgb.shape[0]]


def _smile_shot(engine, peer, h, w, amount):
    """发一条 smile，同时拿下账单与那一帧（次序与 cmd_deform 一致：先账单后帧）。"""
    from test_protocol import _next_event

    _drain(engine)
    engine.send(cmd="deform", action="set", amounts={"smile": amount})
    done = None
    while True:
        e = _next_event(engine, skip=("session_state", "engine_warn"), timeout=120.0)
        if e["event"] == "deform_done":
            done = e
        elif e["event"] == "frame" and e.get("mode") == "deform":
            assert done is not None, "帧先于账单到了：与 cmd_deform 里写的次序不一样"
            return done, _frame_of(e, peer, h, w), e
        elif e["event"] == "error":
            raise AssertionError(f"引擎拒绝了 smile：{e.get('error')}")


def _export_one(engine, out_dir):
    _drain(engine)
    engine.send(cmd="export", out_dir=str(out_dir), format="png", tile=256, quality=90,
                images=[FIXTURE])
    done, _seen = _collect_done(engine)
    assert int(done["failed"]) == 0, done
    rep = done["images"][0]
    assert not any("deform" in str(s) for s in (rep.get("skipped") or [])), \
        f"形变层在导出里被放下了：{rep.get('skipped')}"
    return str(rep["out"])


def test_smile_raises_the_corners_keeps_the_person_and_restores_neutrally(engine, tmp_path):
    """LNX-PORTRAIT-012（表情）本版本那一格：嘴角上扬可控、身份与唇齿连续、中性可回。

    冻结件的 `then` 是三句："保留身份和唇齿连续性；无纹理破裂；中性值可恢复"。
    逐句落成可跑的判据（阈值是**实测**数加余量，不是先拍的）：

    ① 中性可恢复 —— smile=0 那一帧与出厂帧**逐字节相同**，推到 0.8 再回 0 也逐字节
       相同。不许用"差别很小"糊过去：中性不干净，用户每拖一次都在慢慢改变一张图。
    ② 可控 —— 在出片上重测关键点：嘴角上抬实测 23.1/24.6 px（按 SMILE_LIFT_OF_MOUTH_W
       请求 20.9 px），判 0.5–2.0 倍之间；左右差 ≤ 25%（不对称的笑就是脸歪）。
    ③ 身份保持 —— 虹膜中心移动 ≤ max(3 px, 25% 嘴角量)（实测 0.66/1.40 px），
       瞳距相对变化 ≤ 2%（实测 −0.90%）。嘴角动了而眼睛也跟着走 = 换人不是表情。
       这一条是加了身份锚之后才立得住的：没锚时同一档把瞳距改到 −3.9%。
    ④ 唇齿连续 / 无纹理破裂 —— 内唇上下中点在检测里的移动 ≤ 60% 嘴角量（实测 36%）；
       嘴周带的边缘能量 99.9 分位不许比同一管线的中性出片高一档（实测反而更低：
       109.3 → 70.2，重采样把边缘磨软了，没有造出新的硬边）。det J > 0 那条不折叠
       的判据在 test_deform 算子层钉着，这里补的是过完整链之后的读数。
    ⑤ 局部性 —— 底部 12% 那一横条逐字节不动（实测作用面 bbox 到 426 行、画幅 504 行）。
       **不**要求"画面外沿一圈不动"：这张夹具的脸填满画幅，1.6R 的紧支撑窗把整幅都
       盖住了（ADR-0009 量过），所以那里给的是"最多 25 LSB"的余量而不是 0（实测 18）。
    ⑥ 做不到的那几样（露齿笑 / 抿嘴笑 / 闭合嘴巴 / 换表情 = 要重建唇齿内容，属冻结件
       2310 行的 P2 实验档）整条拒，且拒的时候说得出可用名单；拒完画面一格没动。
    """
    _needs_torch()
    src_sha = _sha_of(FIXTURE)
    meta = _open(engine, max_px=207360)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    base = _current(engine, peer, h, w)
    engine.send(cmd="precompute", backend="mediapipe")
    pc = engine.wait_for("precompute_ready", timeout=180)
    assert pc["backend"] == "mediapipe" and int(pc["num_faces"]) == 1, pc
    base = _current(engine, peer, h, w)

    # ── ① 中性：一格都不动
    done0, f0, _ev0 = _smile_shot(engine, peer, h, w, 0.0)
    assert done0["amounts"]["smile"] == 0.0, done0["amounts"]
    assert np.array_equal(f0, base), (
        f"smile=0 动了 {int((np.abs(f0 - base).max(axis=2) > 0).sum())} 格：中性不干净")
    # 全零时引擎不建层（built=False 是如实报账，面板那句"已生效"必须跟着它，
    # 而不是跟着"我发过一条命令"）
    assert done0["built"] is False and done0["lit"] is False, done0

    # ── ②⑤ 推到 0.8：画面按方向在动，而作用面有边界
    done8, f8, _ev8 = _smile_shot(engine, peer, h, w, 0.8)
    assert done8["built"] is True and done8["lit"] is True, done8
    diff = f8.astype(np.int16) - base.astype(np.int16)
    moved = int((np.abs(diff).max(axis=2) > 0).sum())
    assert moved > 1000, f"smile=0.8 只动了 {moved} 格（这才是假滑块该有的样子）"
    assert 0.0 < float(done8["support_share"]) < 1.0, done8["support_share"]
    bottom = np.zeros((h, w), dtype=bool)
    bottom[int(h * 0.88):, :] = True
    assert int(np.abs(diff[bottom]).max()) == 0, (
        f"底部 12% 被 smile 动了 {int(np.abs(diff[bottom]).max())} LSB：这一格的作用面"
        "越过了它自己报的那只窗")
    m = max(2, int(0.06 * min(h, w)))
    ring = np.ones((h, w), dtype=bool)
    ring[m:h - m, m:w - m] = False
    assert int(np.abs(diff[ring]).max()) <= 25, (
        f"最外 6% 那一圈被推到 {int(np.abs(diff[ring]).max())} LSB：窗没收住（实测 18）")

    # ── ① 回到中性：逐字节回来
    _done_back, fb, _evb = _smile_shot(engine, peer, h, w, 0.0)
    assert np.array_equal(fb, base), "推到 0.8 再回 0 没逐字节回到出厂帧"

    # ── 负档是反向等幅（下拉），不是"另一种表情"
    _dneg, fneg, _evn = _smile_shot(engine, peer, h, w, -0.8)
    moved_neg = int((np.abs(fneg - base).max(axis=2) > 0).sum())
    assert moved_neg > 1000, f"负档只动了 {moved_neg} 格：下拉这一半是没接通的"

    # ── ②③④ 出片上的读数：带着 smile 导一次，同一管线中性导一次
    _smile_shot(engine, peer, h, w, 0.8)
    smiled = _export_one(engine, tmp_path / "smiled")
    _smile_shot(engine, peer, h, w, 0.0)
    plain = _export_one(engine, tmp_path / "plain")
    lm_s, lm_p = _detect_on(smiled), _detect_on(plain)

    from lumaretouch_engine.ops.deform import (IRIS_LEFT, IRIS_RIGHT, LIP_INNER_BOTTOM,
                                               LIP_INNER_TOP, MOUTH_CORNER_LEFT,
                                               MOUTH_CORNER_RIGHT, SMILE_LIFT_OF_MOUTH_W)

    corners = (MOUTH_CORNER_LEFT, MOUTH_CORNER_RIGHT)
    mouth_w = float(np.hypot(*(lm_p[corners[1]] - lm_p[corners[0]])))
    want = SMILE_LIFT_OF_MOUTH_W * 0.8 * mouth_w
    lift = np.array([lm_p[c][1] - lm_s[c][1] for c in corners])      # y 向下：正=上抬
    assert (lift > 0).all(), f"两个嘴角都该往上走，实测 {lift}：这一格是哭不是笑"
    assert 0.5 * want <= lift.min() <= 2.0 * want, (
        f"嘴角抬了 {lift} px，按 SMILE_LIFT_OF_MOUTH_W 请求的是 {want:.1f} px：不是可控幅度")
    assert abs(lift[0] - lift[1]) <= 0.25 * abs(lift).max() + 1.0, f"左右不对称：{lift}"

    iris = [IRIS_LEFT, IRIS_RIGHT]        # 列表而不是元组：元组会被当成多轴下标
    iris_move = float(np.abs(lm_s[iris] - lm_p[iris]).max())
    assert iris_move <= max(3.0, 0.25 * float(lift.min())), (
        f"虹膜跟着走了 {iris_move:.2f} px（嘴角才 {lift.min():.1f} px）：改的不是表情，是脸")
    ipd_p = float(np.hypot(*(lm_p[iris[0]] - lm_p[iris[1]])))
    ipd_s = float(np.hypot(*(lm_s[iris[0]] - lm_s[iris[1]])))
    assert abs(ipd_s - ipd_p) / ipd_p <= 0.02, (
        f"瞳距变了 {abs(ipd_s - ipd_p) / ipd_p:.2%}（实测 −0.90%）：身份骨架被拖着走")

    lip = float(np.abs(lm_s[[LIP_INNER_TOP, LIP_INNER_BOTTOM]]
                       - lm_p[[LIP_INNER_TOP, LIP_INNER_BOTTOM]]).max())
    assert lip <= 0.6 * float(lift.min()) + 1.0, (
        f"内唇中点被拖走 {lip:.1f} px（嘴角才 {lift.min():.1f}）：唇中线没锚住，"
        "唇齿连续性就只是句口号")

    def _band_energy(lm, img):
        l, r = lm[MOUTH_CORNER_LEFT], lm[MOUTH_CORNER_RIGHT]
        cx, cy = (l + r) / 2.0
        rad = float(np.hypot(*(r - l)) / 2.0) * 1.6
        yy, xx = np.mgrid[0:img.shape[0], 0:img.shape[1]]
        mask = (xx - cx) ** 2 + (yy - cy) ** 2 <= rad ** 2
        g = img.astype(np.float64).mean(axis=2)
        gx = np.abs(np.diff(g, axis=1, prepend=g[:, :1]))
        gy = np.abs(np.diff(g, axis=0, prepend=g[:1, :]))
        v = (gx + gy)[mask]
        return float(np.percentile(v, 99.9)) if v.size else 0.0

    from PIL import Image

    img_p = np.asarray(Image.open(plain).convert("RGB"))
    img_s = np.asarray(Image.open(smiled).convert("RGB"))
    e_p, e_s = _band_energy(lm_p, img_p), _band_energy(lm_s, img_s)
    assert e_s <= 1.1 * e_p + 1.0, (
        f"嘴周边缘能量 99.9 分位从 {e_p:.1f} 涨到 {e_s:.1f}：出片上长出了原图没有的硬边"
        "（撕裂/内翻的形状）")

    # ── ⑥ 不支持的表情：整条拒、说得出可用名单、画面一格没动
    _done_ref, ref_frame, frame_ev = _smile_shot(engine, peer, h, w, 0.8)
    ev = {"frame": frame_ev}
    for bad in ("teeth_show", "pout", "mouth_close", "expression_transfer"):
        _drain(engine)
        engine.send(cmd="deform", action="set", amounts={bad: 0.5})
        err = engine.wait_for("error", timeout=30)
        assert bad in err["error"] and "smile" in err["error"], (
            f"拒 {bad} 时没说清能做的是哪几格：{err['error']}")
        _assert_no_new_frame(engine, peer, meta, ev, ref_frame, f"请求 {bad} 被拒之后")

    assert _sha_of(FIXTURE) == src_sha, "表情这一条改了原片"


# ------------------------------------------------------------------ PORTRAIT-009
# 眼牙局部增强的端到端臂（LNX-PORTRAIT-009）。库层那 41 条（test_enhance.py）判的是
# 算子性质；这两条判的是**过完整产品链**之后那三句 then 还立不立得住：屏幕上的帧、
# 撤销账、工程重开、导出文件、以及"做不到 Must 拒且说得出原因"。
FIX_SMILE_P09 = str(REPO / "engine" / "tests" / "fixtures" / "portrait-smile-1024x1280.jpg")
FIX_GLASS_P09 = str(REPO / "engine" / "tests" / "fixtures" / "portrait-glasses-smile-1024x1280.jpg")
FIX_DEEP_P09 = str(REPO / "engine" / "tests" / "fixtures" / "portrait-deep-skin-smile-1024x1280.jpg")
P09_SIZE = (1280, 1024)        # 夹具的真实像素尺寸；判据按它写死行/列，所以先要住尺寸
GLASS_BAR_ROWS = (512, 528)    # 生成器里横梁那一个矩形（压在两只眼的虹膜盘上）


def _enh_shot(engine, peer, h, w, **payload):
    """发一条 enhance，同时拿下账单与那一帧（次序与 cmd_deform 一致：先账单后帧）。"""
    from test_protocol import _next_event

    _drain(engine)
    engine.send(cmd="enhance", **payload)
    done = None
    while True:
        e = _next_event(engine, skip=("session_state", "engine_warn"), timeout=120.0)
        if e["event"] == "enhance_done":
            done = e
        elif e["event"] == "frame" and e.get("mode") == "enhance":
            assert done is not None, "帧先于账单到了：与 cmd_enhance 里写的次序不一样"
            return done, _frame_of(e, peer, h, w), e
        elif e["event"] == "error":
            raise AssertionError(f"引擎拒绝了 enhance：{e.get('error')}")


def _p09_regions(path):
    """从**出片同款**的检测结果里取出四个带：虹膜盘、眼裂、内唇开口、上唇面。

    不写死坐标：这些带是判据的接地对象，写死了就会跟着关键点模型或夹具的一次改动
    指着一个对的东西报错（test_enhance 里那条牙齿带已经付过一次这个学费）。
    """
    from lumaretouch_engine.ops.deform import (IRIS_LEFT, IRIS_RIM_LEFT, IRIS_RIM_RIGHT,
                                               IRIS_RIGHT, LIP_INNER_BOTTOM, LIP_INNER_TOP,
                                               MOUTH_CORNER_LEFT, MOUTH_CORNER_RIGHT)
    from PIL import Image

    with Image.open(path) as im:
        im = im.convert("RGB")
        h, w = im.height, im.width
    lm = _detect_on(path)
    out: dict = {}
    for side, iris, rim in (("l", IRIS_LEFT, IRIS_RIM_LEFT), ("r", IRIS_RIGHT, IRIS_RIM_RIGHT)):
        cx, cy = float(lm[iris][0]), float(lm[iris][1])
        rad = float(np.hypot(lm[list(rim), 0] - cx, lm[list(rim), 1] - cy).mean())
        out[f"iris_{side}"] = (cx, cy, rad)
        out[f"eye_{side}"] = (int(max(0, cy - 1.5 * rad)), int(min(h, cy + 1.5 * rad)),
                              int(max(0, cx - 2.2 * rad)), int(min(w, cx + 2.2 * rad)))
    y13, y14 = float(lm[LIP_INNER_TOP][1]), float(lm[LIP_INNER_BOTTOM][1])
    xl, xr = float(lm[MOUTH_CORNER_LEFT][0]), float(lm[MOUTH_CORNER_RIGHT][0])
    out["mouth"] = (int(min(y13, y14)), int(max(y13, y14)), int(xl), int(xr))
    out["lip_strip"] = (int(min(y13, y14)) - 18, int(min(y13, y14)) - 4, int(xl), int(xr))
    return out


def _p09_reload(engine, path, peer, h, w):
    """同一会话里换一张图，**不**重等 shm_ready。

    代理尺寸没变时引擎不重建那块共享缓冲（宿主还映射着它，重建反而要把视口拆一次），
    所以只发 vram_ready + image_ready。`_open()` 那一份每次都等 shm_ready，在这儿
    会空等 240 s 报一条假超时——那不是产品没就绪，是助手把"没重建"读成了"没就绪"。
    """
    _drain(engine)
    engine.send(cmd="load_image", path=path, strength=0.0, max_px=2_000_000)
    got = _collect(engine, "image_ready", timeout=240)
    ir = got["image_ready"][-1]
    assert [ir["h"], ir["w"]] == [h, w], (
        f"换图换了代理档：{(ir['h'], ir['w'])}≠{(h, w)}，那块 shm 缓冲就不是同一块，行判据会指错位")
    return ir


def _p09_band(shape, box):
    """(y0,y1,x0,x1) → 布尔带；顺手夹进画幅。"""
    h, w = shape
    m = np.zeros((h, w), dtype=bool)
    y0, y1, x0, x1 = box
    m[max(0, y0):min(h, y1), max(0, x0):min(w, x1)] = True
    return m


def _p09_disc(shape, cx, cy, rad, k=0.6):
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    return (xx - cx) ** 2 + (yy - cy) ** 2 <= (k * rad) ** 2


def _p09_export(engine, out_dir, images):
    _drain(engine)
    engine.send(cmd="export", out_dir=str(out_dir), format="png", tile=256, quality=90,
                images=list(images))
    done, _seen = _collect_done(engine)
    assert int(done["failed"]) == 0, done
    rep = done["images"][0]
    skipped = [str(s) for s in (rep.get("skipped") or [])]
    assert not any("enhance" in s for s in skipped), \
        f"眼牙层在导出里被放下了（屏幕上看到的没跟到文件）：{skipped}"
    return str(rep["out"])


@pytest.mark.skipif(not os.path.isfile(FIX_SMILE_P09),
                    reason="缺露齿夹具：先跑 packaging/make-test-portrait.py --variant smile")
def test_eye_teeth_enhance_is_local_independent_and_reversible(engine, tmp_path):
    """LNX-PORTRAIT-009（眼牙增强）主臂：虹膜不意外改色、牙齿不过曝不越界、三格独立启停。

    冻结件的 then 三句全落成帧上的判据（阈值取自库层那 41 条的同一次实测，余量另给）：

    ① **中性干净** —— 三个数都给 0 那一帧与出厂帧逐字节相同，`built=false`。面板那句
       "已生效"跟着 lit/built 走，不跟着"我发过一条命令"走。
    ② **不越界** —— 掩膜只在自己报的那只窗里动：窗外**逐字节**相同；上唇面那一条带
       （牙带之外 4–18 px）也必须一格不动——牙齿那一格最容易犯的错就是把红唇涂白。
    ③ **不过曝** —— 全帧 v（=RGB 最大通道）不降、不超过 max(原值, 0.965×255)、255 的
       像素数不增。这是那条乘性上界的直接读法，不是"看看图爽不爽"。
    ④ **不是假滑块** —— 露齿带上 0.8 档实测抬升 ≥ 8 LSB（低光臂在库层 ≥ 20）。
    ⑤ **独立启停** —— 只开牙齿时两眼区域逐字节不动；只开眼白时虹膜盘中心逐字节不动
       （两道掩膜按构造互斥）；只开虹膜时牙齿带逐字节不动。
    ⑥ **撤销/重做** —— history undo 回到改动前那一帧（逐字节），redo 再回来。
    ⑦ **所见即所出** —— 带层导出与中性导出相比：窗内牙齿带确实抬了，窗外**逐字节相同**。
    ⑧ **冻结件的 given 不止一张图** —— 眼镜横梁那一臂与深肤色那一臂都要过完整链：
       前者要证“中性遮挡物不被当成眼睛”（实测横梁行带逐字节不动），后者要证内容门
       是相对的而不是抄绝对阈值（深肤色上牙齿同样抬 ≥ 8 LSB）。
    """
    _needs_torch()
    from lumaretouch_engine.ops import enhance as ENH
    from PIL import Image

    assert os.path.isfile(FIX_GLASS_P09) and os.path.isfile(FIX_DEEP_P09), \
        "眼镜/深肤色两臂是同一次生成出来的，缺一张就是夹具没重跑"
    src_sha = {p: _sha_of(p) for p in (FIX_SMILE_P09, FIX_GLASS_P09, FIX_DEEP_P09)}
    meta = _open(engine, FIX_SMILE_P09, max_px=2_000_000)
    h, w = meta["h"], meta["w"]
    assert (h, w) == P09_SIZE, f"代理尺寸不是夹具原尺寸：{(h, w)}≠{P09_SIZE}，行判据会指错位置"
    peer = FrameShm(meta["name"])
    engine.send(cmd="precompute", backend="mediapipe")
    pc = engine.wait_for("precompute_ready", timeout=180)
    assert pc["backend"] == "mediapipe" and int(pc["num_faces"]) == 1, pc
    base = _current(engine, peer, h, w)
    reg = _p09_regions(FIX_SMILE_P09)
    mouth = _p09_band((h, w), reg["mouth"])
    lip = _p09_band((h, w), reg["lip_strip"])
    eyes = _p09_band((h, w), reg["eye_l"]) | _p09_band((h, w), reg["eye_r"])
    discs = (_p09_disc((h, w), *reg["iris_l"]) | _p09_disc((h, w), *reg["iris_r"]))
    vbase = base.max(axis=2).astype(np.int16)

    # ── ① 中性：一格都不动，而且引擎不建层
    done0, f0, _ev0 = _enh_shot(engine, peer, h, w, action="set", sclera=0.0, iris=0.0, teeth=0.0)
    assert done0["built"] is False and done0["lit"] is False, done0
    assert np.array_equal(f0, base), (
        f"三个 0 却动了 {int((np.abs(f0 - base).max(axis=2) > 0).sum())} 格：中性不干净")

    # ── ②③④ 全开 0.8
    d8, f8, _e8 = _enh_shot(engine, peer, h, w, action="set", sclera=0.8, iris=0.8, teeth=0.8)
    assert d8["lit"] is True and d8["built"] is True, d8
    win = d8["enhance_window"]
    assert win, d8
    outside = np.ones((h, w), dtype=bool)
    y0, x0, fh, fw = (int(v) for v in win)
    outside[y0:min(h, y0 + fh), x0:min(w, x0 + fw)] = False
    diff = f8.astype(np.int16) - base.astype(np.int16)
    adiff = np.abs(diff).max(axis=2)
    assert int(adiff[outside].max()) == 0, (
        f"窗外被动了 {int(adiff[outside].max())} LSB：这一层越过了它自己报的那只窗")
    assert int(adiff[lip].max()) == 0, f"上唇面被牙齿那一格涂白了 {int(adiff[lip].max())} LSB"
    gate = d8["enhance_gated_px"]
    assert all(int(gate[k]) >= 12 for k in ("sclera", "iris", "teeth")), gate
    vout = f8.max(axis=2).astype(np.int16)
    assert int((vout < vbase - 1).sum()) == 0, "有像素被这一层推暗了：乘性抬升不该降 v"
    ceil = np.maximum(vbase, int(round(ENH.V_CEIL * 255.0)))
    assert int((vout > ceil).sum()) == 0, (
        f"有 {int((vout > ceil).sum())} 格越过了天花板 {int(ENH.V_CEIL * 255)}：这就是过曝")
    assert int((vout >= 255).sum()) <= int((vbase >= 255).sum()), "255 的像素数增加了"
    lift_teeth = float(adiff[mouth].mean())
    assert lift_teeth >= 8.0, f"露齿带上 0.8 档只抬了 {lift_teeth:.2f} LSB：假滑块"
    assert float(adiff[eyes].mean()) >= 2.0, f"眼部只动了 {float(adiff[eyes].mean()):.2f} LSB"

    # ── ⑤' 计账次序：这一层的 ms 说的是"刚出那一帧的代价"，不是渲染前的 0
    #      （1.8.0 定版时 m5 第 8 臂读到的就是这个 0：账取在 `_write_current_frame`
    #      之前，第一条命令永远报"这层不要钱"。恒 0 的计时比没有计时更坏——它把
    #      "没量到"报成"量到了 0"。）
    ms = float(d8.get("enhance_ms") or 0.0)
    assert ms > 0.0, (f"点火那一格的 enhance_ms 报 0：账又取在渲染之前了"
                      f"（built={d8.get('built')} lit={d8.get('lit')}）")

    # ── ⑤ 独立启停：只开一格时，另两格的重地必须逐字节不动
    for only, keep, where in (("teeth", eyes, "两眼"),
                              ("iris", mouth, "露齿带"),
                              ("sclera", discs, "虹膜盘中心")):
        _dc, fc, _ec = _enh_shot(engine, peer, h, w, action="clear")
        assert np.array_equal(fc, base), "clear 之后没回到出厂帧"
        _dn, fn, _en = _enh_shot(engine, peer, h, w, action="set", **{only: 0.8})
        a = np.abs(fn.astype(np.int16) - base.astype(np.int16)).max(axis=2)
        assert int(a[keep].max()) == 0, (
            f"只开 {only} 时{where}被动了 {int(a[keep].max())} LSB：独立启停不成立")
        moved = int((a > 0).sum())
        assert moved > 200, f"只开 {only} 全图只动了 {moved} 格：这一格没接通"

    # ── ⑥ 撤销 / 重做：账本与画面必须是一对
    _enh_shot(engine, peer, h, w, action="clear")
    _d7, f7, _e7 = _enh_shot(engine, peer, h, w, action="set", sclera=0.7, iris=0.7, teeth=0.7)
    assert np.array_equal(_current(engine, peer, h, w), f7), "取回的最新帧与那一笔的帧不一致"
    _drain(engine)
    engine.send(cmd="history", action="undo")
    undone = _frame_of(_wait_frame_mode(engine, "history_undo"), peer, h, w)
    assert np.array_equal(undone, base), (
        f"撤销后没回到出厂帧（差 {int(np.abs(undone - base).max())} LSB）：这一层的"
        "快照没进撤销账，或进了但重放时没放下")
    _drain(engine)
    engine.send(cmd="history", action="redo")
    redone = _frame_of(_wait_frame_mode(engine, "history_redo"), peer, h, w)
    assert np.array_equal(redone, f7), "redo 回来的那一帧与撤销前那一帧不同：账本说谎"

    # ── ⑦ 所见即所出
    _enh_shot(engine, peer, h, w, action="set", sclera=0.8, iris=0.8, teeth=0.8)
    out_on = _p09_export(engine, tmp_path / "enh-on", [FIX_SMILE_P09])
    _enh_shot(engine, peer, h, w, action="clear")
    out_off = _p09_export(engine, tmp_path / "enh-off", [FIX_SMILE_P09])
    with Image.open(out_on) as im:
        arr_on = np.asarray(im.convert("RGB"), dtype=np.uint8)
    with Image.open(out_off) as im:
        arr_off = np.asarray(im.convert("RGB"), dtype=np.uint8)
    assert arr_on.shape[:2] == arr_off.shape[:2] == (h, w), (arr_on.shape, arr_off.shape)
    de = np.abs(arr_on.astype(np.int16) - arr_off.astype(np.int16)).max(axis=2)
    assert int(de[mouth].mean()) > 0, "导出里牙齿带上没有变化：屏幕上的美白没跟到文件"
    assert int(de[outside].max()) == 0, (
        f"导出窗外差了 {int(de[outside].max())} LSB：分块挂场没按窗口求交")

    # ── ⑧ 冻结件的 given 点名了眼镜与深肤色：这两臂得过完整链，不只过算子层
    for path, extra in ((FIX_GLASS_P09, "glass"), (FIX_DEEP_P09, "deep")):
        m = _p09_reload(engine, path, peer, h, w)
        hh, ww = m["h"], m["w"]
        pr = peer                        # 同一块缓冲：代理档没变，宿主映射也没换
        engine.send(cmd="precompute", backend="mediapipe")
        q = engine.wait_for("precompute_ready", timeout=180)
        assert int(q["num_faces"]) == 1, q
        b = _current(engine, pr, hh, ww)
        rg = _p09_regions(path)
        d_, f_, _e_ = _enh_shot(engine, pr, hh, ww, action="set", sclera=0.8, iris=0.8, teeth=0.8)
        a_ = np.abs(f_.astype(np.int16) - b.astype(np.int16)).max(axis=2)
        assert d_["lit"] is True, (extra, d_)
        lift = float(a_[_p09_band((hh, ww), rg["mouth"])].mean())
        assert lift >= 8.0, f"{extra}：牙齿那一格只抬了 {lift:.2f} LSB（相对内容门没跟上）"
        if extra == "glass":
            # 横梁把整条行带盖成了中性中灰（实测 s≤0.06）：两道眼部门都要把它整块掉出去
            cx_l = int(rg["iris_l"][0])
            cx_r = int(rg["iris_r"][0])
            bar = np.zeros((hh, ww), dtype=bool)
            bar[GLASS_BAR_ROWS[0] + 2:GLASS_BAR_ROWS[1] - 2, cx_l:cx_r + 1] = True
            assert int(a_[bar].max()) == 0, (
                f"眼镜横梁被眼部门动了 {int(a_[bar].max())} LSB：中性灰不该被当成眼睛")
            assert float(a_[_p09_disc((hh, ww), *rg["iris_l"], k=0.45)].mean()) < 3.0, (
                "横梁压在虹膜盘上而那里动得比护栏宽")

    for p09, sha0 in src_sha.items():
        assert _sha_of(p09) == sha0, f"眼牙这一条动了原片：{p09}"


@pytest.mark.skipif(not os.path.isfile(FIX_SMILE_P09), reason="缺露齿夹具")
def test_eye_teeth_enhance_refuses_what_it_cannot_do_and_says_why(engine, extra_engine, tmp_path):
    """LNX-PORTRAIT-009 的"做不到"那一半：闭嘴 / 无关键点 / synthetic / 多人 / 非法参数。

    冻结件的 given 点名了"眼镜/遮挡/低光/深肤色和露齿样本"，而 then 要的是**不出事故**。
    事故不止是"画坏了"，还包括"没画却报告说画了"与"替用户选了一张脸"。这几臂的共同
    判据是：拒的那一条必须说得出原因，而且**画面一格不许动**。
    """
    _needs_torch()

    # ① 闭嘴样本：牙齿那一格不硬画——整格不点火，且 reason 说得出"闭嘴"
    meta = _open(engine, FIXTURE, max_px=2_000_000)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    engine.send(cmd="precompute", backend="mediapipe")
    engine.wait_for("precompute_ready", timeout=180)
    base = _current(engine, peer, h, w)
    d1, f1, _ev = _enh_shot(engine, peer, h, w, action="set", sclera=0.8, iris=0.8, teeth=0.8)
    assert d1["lit"] is True, "眼白/虹膜在闭嘴样本上也该点火；lit=false 就是整层没接上"
    assert int(d1["enhance_gated_px"]["teeth"]) == 0, d1["enhance_gated_px"]
    reason = (d1["enhance_reason"] or {}).get("teeth") or ""
    assert "闭嘴" in reason or "开口度" in reason, f"牙齿那一格没点火却没说原因：{reason!r}"
    assert int((np.abs(f1 - base).max(axis=2) > 0).sum()) > 0, "眼睛那一格也没动：整层是空的"

    # ② 没关键点：defer 存住参数、不动画面；一次 precompute 自动接回（这条打的就是
    #    _rehang_precompute 里那份 pc NameError——接线时只测了直调路径）
    e2 = extra_engine("portrait009-defer")
    meta2 = _open(e2, FIX_SMILE_P09, max_px=2_000_000)
    h2, w2 = meta2["h"], meta2["w"]
    peer2 = FrameShm(meta2["name"])
    base2 = _current(e2, peer2, h2, w2)
    _drain(e2)
    e2.send(cmd="enhance", action="set", iris=0.6)
    dd = e2.wait_for("enhance_done", timeout=30)
    assert dd["action"] == "defer" and dd["defer"] is True and dd["built"] is False, dd
    assert dd["amounts"]["iris"] == 0.6, dd
    got = _current(e2, peer2, h2, w2)
    assert np.array_equal(got, base2), "defer 不该动画面：参数存住≠已经生效"
    e2.send(cmd="precompute", backend="mediapipe")
    pc2 = e2.wait_for("precompute_ready", timeout=180)
    assert int(pc2["num_faces"]) == 1, pc2
    rb = None
    for _ in range(60):
        e = e2.next_event(timeout=10.0)
        if e["event"] == "enhance_done":
            rb = e
            break
    assert rb is not None and rb["action"] == "rebuild", f"precompute 后没把这一层接回来：{rb}"
    assert rb["lit"] is True and rb["built"] is True, rb
    after = _current(e2, peer2, h2, w2)
    assert not np.array_equal(after, got), "接回来之后画面必须真的变了（defer 不是空转）"

    # ②b 存工程 → 换进程重开：三个数与掩膜都要回来，画面逐字节相同。
    #     这一条不是"顺手测一下"：工程里只存参数、不存关键点（关键点随模型版本走），
    #     所以重开必须**自动补一次分析**再把这一层挂回去——CORE-001 那一次丢形变层的
    #     教训就是这条链没接上（口径见 ADR-0008 的 defer）。
    e6 = extra_engine("portrait009-save")
    m6 = _open(e6, FIX_SMILE_P09, max_px=2_000_000)
    h6, w6 = m6["h"], m6["w"]
    pr6 = FrameShm(m6["name"])
    e6.send(cmd="precompute", backend="mediapipe")
    e6.wait_for("precompute_ready", timeout=180)
    _enh_shot(e6, pr6, h6, w6, action="set", sclera=0.5, iris=0.7, teeth=0.9)
    lit6 = _current(e6, pr6, h6, w6)
    sha_smile = _sha_of(FIX_SMILE_P09)
    _c6, saved6 = _create_and_save(e6, tmp_path, name="眼牙增强")
    e7 = extra_engine("portrait009-reopen")
    e7.send(cmd="hello")
    e7.wait_for("ready", timeout=90)
    e7.send(cmd="set_device", device="cpu")
    e7.wait_for("device_set", timeout=120)
    e7.send(cmd="project", action="open", path=saved6["path"])
    e7.wait_for("project_opened", timeout=120)
    got_ev = _collect(e7, "image_ready", timeout=240)
    shm7 = got_ev["shm_ready"][-1]
    en7 = (got_ev["image_ready"][-1].get("doc_state") or {}).get("enhance") or {}
    assert en7.get("amounts"), f"重开后工程里没有这一层的账：{en7}"
    for k, want in (("sclera", 0.5), ("iris", 0.7), ("teeth", 0.9)):
        assert abs(float(en7["amounts"].get(k, 0.0)) - want) < 1e-9, (k, en7["amounts"])
    # 自动补的那次分析排在 image_ready **之后**（PORTRAIT-003 那一臂同一次序）：
    # 在 image_ready 那一格里 lit=false 是对的——关键点还没回来，场确实还没重画。
    assert en7.get("lit") is False, f"关键点还没重算就报 lit：{en7}"
    pc7 = e7.wait_for("precompute_ready", timeout=240)
    assert pc7["backend"] == "mediapipe", pc7
    rb7 = None
    for _ in range(120):
        e = e7.next_event(timeout=20.0)
        if e["event"] == "enhance_done":
            rb7 = e
            break
        if e["event"] == "error":
            raise AssertionError(f"重开自动补分析这路报错了：{e.get('error')}")
    assert rb7 is not None and rb7["action"] == "rebuild", f"重开后这一层没被接回来：{rb7}"
    assert rb7["lit"] is True and rb7["built"] is True, rb7
    assert sum(int(v) for v in (rb7.get("gated_px") or {}).values()) > 0, rb7
    peer7 = FrameShm(shm7["name"])
    assert (shm7["h"], shm7["w"]) == (h6, w6), (shm7["h"], shm7["w"])
    back7 = _current(e7, peer7, shm7["h"], shm7["w"])
    assert int(np.abs(back7.astype(np.int16) - lit6.astype(np.int16)).max()) == 0, (
        f"重开工程后画面与保存前差 {int(np.abs(back7 - lit6).max())} LSB："
        "掩膜重画不是同一幅（换人选/认脸盒那条臂就断在这里）")
    assert _sha_of(FIX_SMILE_P09) == sha_smile, "存/开工程动了原片"

    # ③ synthetic 后端：占位几何画不出可信位置 → 整条拒 + 画面不动
    #    这张露齿图与 ① 那张同代理档，所以走 reload（引擎不重建 shm，等 shm_ready
    #    就是一条 240 s 的假超时——同一个助手口径，理由写在 _p09_reload 的注释里）
    e3_engine = engine
    meta3 = _p09_reload(e3_engine, FIX_SMILE_P09, peer, h, w)
    h3, w3 = meta3["h"], meta3["w"]
    peer3 = peer
    e3_engine.send(cmd="precompute", backend="synthetic")
    e3_engine.wait_for("precompute_ready", timeout=60)
    base3 = _current(e3_engine, peer3, h3, w3)
    _drain(e3_engine)
    e3_engine.send(cmd="enhance", action="set", teeth=0.8)
    err = e3_engine.wait_for("error", timeout=30)
    assert "synthetic" in err["error"], err
    assert np.array_equal(_current(e3_engine, peer3, h3, w3), base3), "被拒之后画面动了"

    # ④ 非法参数：整条不生效，参数与画面都没被改动过
    for bad, want in (({"action": "set", "iris": 2.0}, "2.0"),
                      ({"action": "set", "eyebrow": 0.5}, "eyebrow"),
                      ({"action": "boost", "iris": 0.5}, "boost")):
        _drain(e3_engine)
        e3_engine.send(cmd="enhance", **bad)
        err = e3_engine.wait_for("error", timeout=30)
        assert want.split()[0] in err["error"], (bad, err["error"])
        assert np.array_equal(_current(e3_engine, peer3, h3, w3), base3), (
            f"非法参数 {bad} 之后画面动了：被拒不许留半截状态")
        st = _live_state(e3_engine)
        amounts = ((st.get("enhance") or {}).get("amounts")) or {}
        assert all(abs(float(v)) < 1e-12 for v in amounts.values()), (
            f"被拒之后 doc_state 里还留着非零值：{amounts}")

    # ⑤ 多人图：不替用户选哪一张脸（SCOPE-001），显式选定后才干活，换人时静默放下要说清
    dual = _dual_or_explain()
    sha_dual = _sha_of(dual)
    meta4 = _open(e3_engine, dual, max_px=2_000_000)
    h4, w4 = meta4["h"], meta4["w"]
    peer4 = FrameShm(meta4["name"])
    e3_engine.send(cmd="precompute", backend="mediapipe")
    pc4 = e3_engine.wait_for("precompute_ready", timeout=180)
    assert int(pc4["num_faces"]) >= 2, pc4
    base4 = _current(e3_engine, peer4, h4, w4)
    _drain(e3_engine)
    e3_engine.send(cmd="enhance", action="set", iris=0.6)
    err = e3_engine.wait_for("error", timeout=30)
    assert "SCOPE-001" in err["error"] and "face" in err["error"], err["error"]
    assert np.array_equal(_current(e3_engine, peer4, h4, w4), base4), "多人图被拒之后画面动了"
    _drain(e3_engine)
    e3_engine.send(cmd="face", action="select", index=0)
    # 按事件流本来的顺序收（`wait_for` 会把命中之前的别的类型**丢掉**，而换人这一路
    # 后面正要读那条被丢掉的 enhance_done——PORTRAIT-003 那一臂已经为这个形状写过警告）
    got0 = _collect(e3_engine, "face_selected", timeout=60)
    sel = got0["face_selected"][-1]
    assert sel.get("explicit") is True or sel.get("selected_index") == 0, sel
    d5, _f5, _e5 = _enh_shot(e3_engine, peer4, h4, w4, action="set", iris=0.6)
    assert d5["lit"] is True and d5["person_box"], "选定一张脸之后这一层该点火并报出挂在谁身上"
    box_a = list(d5["person_box"])
    _drain(e3_engine)
    e3_engine.send(cmd="face", action="select", index=1)
    got5 = _collect(e3_engine, "face_selected", timeout=60)
    invs = got5.get("enhance_done") or []
    assert invs, ("换人后连一条 enhance_done 都没有：那一层是静默消失的",
                  [e.get("event") for e in got5.values()])
    inv = invs[-1]
    assert inv["action"] == "invalidate", f"换人后这一层没被放下：{inv}"
    assert inv["person_box"] != box_a or inv["person_box"] is None, inv
    assert "另一张脸" in (inv.get("reason") or ""), inv
    assert (inv.get("dropped_amounts") or {}).get("iris") == 0.6, (
        f"放下时要把用户的参数如实报回去：{inv.get('dropped_amounts')}")
    assert _sha_of(dual) == sha_dual, "多人这一条动了原片"


# ------------------------------------------------------------------ 人工纠正优先（LNX-PORTRAIT-006）
# 库层那 20 条（test_face_manual.py）判的是映射数学与账的语义；这两条判的是**产品事实**：
# 用户关掉的那一只在重检测、换模型、重开工程之后仍是关着的那一只，而用户框出来补上的
# 那一位，画面里真的是他。
def test_manual_face_corrections_survive_redetection_model_switch_and_reopen(
        engine, extra_engine, tmp_path):
    """LNX-PORTRAIT-006（人工纠正优先）主臂：禁用那一只跨重检测、换模型、重开工程都保留。

    冻结件 given「用户手动添加/禁用的人脸」× when「后台重检测或更换检测模型」× then
    「人工纠正保留，变化可预览；不静默恢复已禁用误检」逐句对判据：

    ① 关掉当前选定的那一只：那一个人的两层生效值当场放下，另一个人的活儿逐字节不动；
    ② 禁用之后 `face select` 那一只必须明拒——引擎不服务人说过"这不是脸"的那一张；
    ③ 全局撤销/重做把这次禁用连同画面一起带回与再放下，逐字节对得上（这条账是真状态，
       不是宿主侧的一份旁注）；
    ④ 后台重检测（同模型）：账保留、名单上那一只仍 disabled、被禁那一位在新一帧上的内芯
       **逐字节 0 LSB**（"不得重新出现"就是这一句），而 `scope_block` 仍是 multi_face
       （人工账不许把原始分析事实抹掉，SCOPE-001 的 P0 判据读的是它）；
    ⑤ 更换检测模型（mediapipe → template）：认得回就照账禁用，认不回也要留账并明说 stale；
       两条路都不许把它当"没被禁过"（逐位相等在这里就不够，所以按 IoU 认人）；
    ⑥ 存工程 → 换进程重开：账随配方走，重开自动补的那次分析把禁用重新叠上，被禁那一位的
       内芯仍是出厂字节；
    ⑦ 原片哈希不动。
    """
    _needs_torch()
    import importlib.util
    from PIL import Image                      # noqa: F401  （与 PORTRAIT-003 同一臂依赖面）

    if importlib.util.find_spec("mediapipe") is None:
        pytest.fail("运行时没装 mediapipe：人工纠正判的是「名单里那一个人」，这条不许退成"
                    "skip（skip 不是通过），装它见 engine/requirements-mediapipe.txt")
    path = _dual_or_explain()
    meta = _open(engine, path=path)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    engine.send(cmd="precompute", backend="mediapipe")
    pc = engine.wait_for("precompute_ready", timeout=180)
    assert int(pc.get("num_faces", 0)) == 2, pc.get("num_faces")
    faces = sorted(pc.get("faces") or [], key=lambda f: f["index"])
    left, right = sorted(faces, key=lambda f: f["box"][0] + f["box"][2])
    a, b = right["index"], left["index"]           # A = 要留的那一位，B = 被当成误检的那一位
    box_a, box_b = right["box"], left["box"]
    core_a = _face_region(h, w, box_a, shrink=0.25)
    core_b = _face_region(h, w, box_b, shrink=0.25)
    sha0 = _sha_of(path)

    base = _current(engine, peer, h, w)
    _drain(engine)
    engine.send(cmd="face", action="select", index=a)
    engine.wait_for("face_selected", timeout=60)
    engine.send(cmd="deform", action="set", amounts={"slim_face": 0.9, "big_eye": 0.6})
    done = engine.wait_for("deform_done", timeout=90)
    assert done["built"] is True and done["lit"] is True, done
    pushed = _current(engine, peer, h, w)
    d = np.abs(pushed.astype(np.int16) - base.astype(np.int16)).max(axis=2)
    assert int(d[core_a].max()) > EPS, "推 A 而 A 的内芯没动：假控件"
    assert int(d[core_b].max()) == 0, "推 A 时 B 动了：改一个人动了另一个人"

    # ① 用户判断：B 是误检，关掉它
    _drain(engine)
    engine.send(cmd="face", action="disable", index=b)
    ev = engine.wait_for("face_manual", timeout=60)
    assert ev["action"] == "disable" and len(ev["manual"]["disabled"]) == 1, ev
    flags = {f["index"]: f["disabled"] for f in ev["faces"]}
    assert flags[b] is True and flags[a] is False, flags
    assert ev["enabled"] == [a] and ev["blocked"] is False, ev
    assert ev["scope_block"] == "multi_face", "人工账把「这一轮探到两张」抹掉了"
    assert ev["explicit"] is True and ev["index"] == a, \
        f"只剩一个可编辑的人时应指过去并明说：{ev['index']}/{ev['explicit']}"
    off = _current(engine, peer, h, w)
    doff = np.abs(off.astype(np.int16) - base.astype(np.int16)).max(axis=2)
    assert int(doff[core_b].max()) == 0, "关掉的那一只在画面上还挂着东西"
    assert int(np.abs(off.astype(np.int16) - pushed.astype(np.int16)).max(axis=2)[core_a].max()) == 0, \
        "关掉 B 把 A 的活儿也一起烧了：一次排除不该推翻另一次编辑"

    # ② 禁用之后不许再把服务给他
    _drain(engine)
    engine.send(cmd="face", action="select", index=b)
    err = _expect_error(engine, "已被人工禁用")
    assert "face enable" in err["error"], err

    # ③ 撤销这次禁用：账与画面必须同时回去（这份账进文档状态、进撤销栈，不是宿主旁注）
    _drain(engine)
    engine.send(cmd="history", action="undo")
    engine.wait_for("history_state", timeout=60)
    st = _live_state(engine)["face"]
    assert st["manual"]["disabled"] == [], f"撤销没把账退回去：{st['manual']}"
    undone = _current(engine, peer, h, w)
    assert int(np.abs(undone.astype(np.int16) - pushed.astype(np.int16)).max()) == 0, \
        "撤销后画面没回到禁用前那一幅"
    _drain(engine)
    engine.send(cmd="history", action="redo")
    engine.wait_for("history_state", timeout=60)
    st = _live_state(engine)["face"]
    assert len(st["manual"]["disabled"]) == 1, st["manual"]
    redone = _current(engine, peer, h, w)
    assert int(np.abs(redone.astype(np.int16) - off.astype(np.int16)).max()) == 0, \
        "重做后画面没回到禁用那一幅"

    # ④ 后台重检测（同一个模型再来一次）：不静默恢复，且被禁那一位不许在帧上重新出现
    _drain(engine)
    engine.send(cmd="precompute", backend="mediapipe")
    pc2 = engine.wait_for("precompute_ready", timeout=180)
    st2 = pc2["face"]
    assert len(st2["manual"]["disabled"]) == 1, f"重检测把人工账洗掉了：{st2['manual']}"
    assert st2["manual"]["stale"] == [], f"同模型重检测却认不回：{st2['manual']}"
    flags2 = {f["index"]: f["disabled"] for f in st2["faces"]}
    assert flags2[b] is True and flags2[a] is False, flags2
    assert st2["enabled"] == [a] and st2["blocked"] is False and st2["explicit"] is True, st2
    assert st2["scope_block"] == "multi_face", st2
    assert "保留 1 处禁用" in st2["manual"]["preview"], st2["manual"]["preview"]
    again = _current(engine, peer, h, w)
    d2 = np.abs(again.astype(np.int16) - base.astype(np.int16)).max(axis=2)
    assert int(d2[core_b].max()) == 0, \
        f"重检测后被禁那一只的内芯动了 {int(d2[core_b].max())} LSB：静默恢复"
    assert int(np.abs(again.astype(np.int16) - off.astype(np.int16)).max()) == 0, \
        "同图同模型重算，A 那一侧的帧变了：重算不是重新发明"

    # ⑤ 更换检测模型（冻结件 when 的另一半）：认得回照账禁用，认不回留账并明说
    _drain(engine)
    engine.send(cmd="precompute", backend="template")
    pc3 = engine.wait_for("precompute_ready", timeout=120)
    st3 = pc3["face"]
    assert len(st3["manual"]["disabled"]) == 1, f"换模型把人工账洗掉了：{st3['manual']}"
    attached = [f["index"] for f in st3["faces"] if f["disabled"]]
    assert bool(attached) == (st3["manual"]["stale"] == []), \
        f"认没认上与实际标记不一致：attached={attached} stale={st3['manual']['stale']}"
    assert not (set(attached) & set(st3["enabled"])), "被禁那一位同时出现在可编辑名单里"
    for i in attached:
        _drain(engine)
        engine.send(cmd="face", action="select", index=i)
        _expect_error(engine, "已被人工禁用")
    _drain(engine)
    engine.send(cmd="precompute", backend="mediapipe")
    pc4 = engine.wait_for("precompute_ready", timeout=180)
    assert len(pc4["face"]["manual"]["disabled"]) == 1 and pc4["face"]["enabled"] == [a], pc4["face"]

    # ⑥ 存工程 → 换进程重开：账随配方走，重开补的那次分析把它叠回名单
    _created, saved = _create_and_save(engine, tmp_path, name="人工纠正")
    raw = json.loads(Path(saved["path"]).read_text(encoding="utf-8"))
    rows = [d for d in raw["docs"] if d["path"] == os.path.abspath(path)]
    assert rows, f"工程里没有这张多人图：{[d['path'] for d in raw['docs']]}"
    recipe = json.dumps(rows[0]["versions"][0].get("recipe") or {})
    assert "disabled" in recipe, "人工账没进工程文件：重开之后关掉的误检会自己活回来"

    eng2 = extra_engine("portrait006-reopen")
    eng2.send(cmd="hello")
    eng2.wait_for("ready", timeout=90)
    eng2.send(cmd="set_device", device="cpu")
    eng2.wait_for("device_set", timeout=120)
    eng2.send(cmd="project", action="open", path=saved["path"])
    eng2.wait_for("project_opened", timeout=120)
    got_ev = _collect(eng2, "image_ready", timeout=240)
    shm2 = got_ev["shm_ready"][-1]
    pc5 = eng2.wait_for("precompute_ready", timeout=240)
    st5 = pc5["face"]
    assert len(st5["manual"]["disabled"]) == 1, f"重开后账没了：{st5['manual']}"
    assert st5["enabled"] == [a] and st5["explicit"] is True and st5["index"] == a, st5
    got = _current(eng2, FrameShm(shm2["name"]), shm2["h"], shm2["w"])
    d3 = np.abs(got.astype(np.int16) - base.astype(np.int16)).max(axis=2)
    core_b2 = _face_region(shm2["h"], shm2["w"], box_b, shrink=0.25)
    assert int(d3[core_b2].max()) == 0, \
        f"重开工程后被禁那一只的内芯动了 {int(d3[core_b2].max())} LSB：静默恢复"

    # ⑦ 原片只读
    assert _sha_of(path) == sha0, "动过原片：这一条在任何一臂里都是死刑"


def test_a_manually_framed_missed_face_becomes_editable_geometry(engine, tmp_path):
    """LNX-PORTRAIT-006 的另一半 given：用户**手动添加**的那一张。引擎只探 2 张，
    三格图上必然有一位不在名单里——把他框出来，他要拿到**区域真检测**的 478 点，
    而且改他不动另外两人。

    ① 名单确实漏了第三位（按生成器的几何反算，不靠"我记得长这样"）；
    ② `face add` 之后那一位的 box 与反算位置对得上，且点位出自区域检测（事件里报后端）；
    ③ 选定他并推滑块：他的内芯动了，另两位的内芯逐字节 0 LSB——人工补的脸不是新造的
       一整层，而是与检测脸同一条服务路径；
    ④ 补错能收回（`face remove` 只允许撤人工的那一张，撤检测脸要明拒）；
    ⑤ 框在背景上必须**明拒**且名单原样（DoD §2：不许按框拟合一套占位点位冒充 AI）；
    ⑥ 重复框同一位要明拒（"已经有脸了"），不给他两份几何。
    """
    _needs_torch()
    import importlib.util

    if importlib.util.find_spec("mediapipe") is None:
        pytest.fail("运行时没装 mediapipe：这一条要的是「区域里真的再检测一次」")
    spec = importlib.util.spec_from_file_location(
        "make_test_dual", str(REPO / "packaging" / "make-test-dual-portrait.py"))
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    src_png = str(REPO / "engine" / "tests" / "fixtures" / "portrait-1024x1280.png")
    img = gen.build(src_png, cells=3)
    triple = tmp_path / "portrait-triple.jpg"
    img.save(str(triple), quality=95, subsampling=2)

    meta = _open(engine, path=str(triple))
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    engine.send(cmd="precompute", backend="mediapipe")
    pc = engine.wait_for("precompute_ready", timeout=180)
    faces = sorted(pc.get("faces") or [], key=lambda f: f["index"])
    assert len(faces) == 2 and int(pc.get("num_faces", 0)) == 2, \
        f"三格图本该撞到探脸上限（名单漏一位），实际名单 {len(faces)} 张：输入或上限变了"
    # 第三格的位置由生成器的常量反算（CELL_W/CELL_H/GAP/THIRD_SCALE 是同一份出处）
    CW, CH, GAP, TS = gen.CELL_W, gen.CELL_H, gen.GAP, gen.THIRD_SCALE
    total_w = CW * 3 + GAP * 2
    start_x, start_y = 2 * (CW + GAP), int(CH * (1 - TS))
    # 名单顺序是检测器的返回顺序，不是从左到右（本仓在 `_face_box` 那条注释里写过这件事），
    # 所以要按**几何**挑出第一格那一位：第三格贴的是同一张未镜像的源图，镜像那位不能当参照
    ref_face = min(faces, key=lambda f: f["box"][0] + f["box"][2])
    ref = ref_face["box"]
    assert ref[0] * total_w < CW and ref[2] * total_w > CW * 0.4, \
        f"参照那位不在第一格里（{ref}），反算的前提不成立：这一条判据会量错位置"
    u0, u1 = ref[0] * total_w / CW, ref[2] * total_w / CW
    rect = ((start_x + u0 * CW * TS) / total_w, start_y / CH + ref[1] * TS,
            (start_x + u1 * CW * TS) / total_w, start_y / CH + ref[3] * TS)
    from lumaretouch_engine.face import box_iou
    for f in faces:
        assert box_iou(f["box"], rect) < 0.2, f"这一框与名单里第 {f['index']} 张对得上：输入没漏人"

    _drain(engine)
    engine.send(cmd="face", action="add", rect=list(rect))
    ev = engine.wait_for("face_manual", timeout=120)
    assert ev["action"] == "add" and len(ev["faces"]) == 3, ev
    newf = [f for f in ev["faces"] if f.get("manual")]
    assert len(newf) == 1, f"人工来源没标出来：{ev['faces']}"
    assert ev["region"]["backend"] == "mediapipe", ev["region"]
    assert box_iou(newf[0]["box"], rect) >= 0.2, f"补回来的不是这一框：{newf[0]['box']} vs {rect}"
    assert len(ev["manual"]["added"]) == 1, ev["manual"]
    # 框住他就是要改他：这一步指过去不是"引擎替人选"，那次框选本身就是选择
    assert ev["index"] == newf[0]["index"] and ev["explicit"] is True, ev
    assert ev["enabled"] == [f["index"] for f in sorted(ev["faces"], key=lambda x: x["index"])]

    # ③ 改他不动别人：人工补的脸走的是与检测脸同一条服务路径，不是新造的一整层
    idx = newf[0]["index"]
    base = _current(engine, peer, h, w)
    _drain(engine)
    engine.send(cmd="deform", action="set", amounts={"slim_face": 0.9})
    done = engine.wait_for("deform_done", timeout=90)
    assert done["built"] is True and done["lit"] is True, done
    assert done["landmark_backend"] == "mediapipe", done
    pushed = _current(engine, peer, h, w)
    d = np.abs(pushed.astype(np.int16) - base.astype(np.int16)).max(axis=2)
    mine = _face_region(h, w, newf[0]["box"], shrink=0.25)
    assert int(d[mine].max()) > EPS, "人工补的那一位推了滑块而画面没动：假控件"
    for f in faces:
        other = _face_region(h, w, f["box"], shrink=0.25)
        assert int(d[other].max()) == 0, \
            f"改人工补的那一位时动了名单里第 {f['index']} 位（{int(d[other].max())} LSB）"

    # ⑤ 框在**第三格上方那块纯背景**上：明拒，名单原样。补过上下文之后窗里可能带进
    #    那一位的头顶，两种失败（没脸 / 对不上框）都走同一条外报文案，所以判据不猜原因
    rect_bg = [(start_x + 20) / total_w, 0.02, (start_x + CW * TS - 20) / total_w, (start_y - 8) / CH]
    _drain(engine)
    engine.send(cmd="face", action="add", rect=list(rect_bg))
    err = _expect_error(engine, "这一框里")
    assert "名单原样未动" in err["error"], err
    st = _live_state(engine)["face"]
    assert len(st["faces"]) == 3, f"被拒的人工框动了名单：{len(st['faces'])} 张"

    # ⑥ 重复框同一位
    _drain(engine)
    engine.send(cmd="face", action="add", rect=list(rect))
    _expect_error(engine, "已经有脸了")

    # ④ 收回：人工那张可以撤，检测那两张只能禁用
    _drain(engine)
    engine.send(cmd="face", action="remove", index=0)
    _expect_error(engine, "不能撤")
    _drain(engine)
    engine.send(cmd="face", action="remove", index=idx)
    ev2 = engine.wait_for("face_manual", timeout=60)
    assert len(ev2["faces"]) == 2 and not [f for f in ev2["faces"] if f.get("manual")], ev2["faces"]
    assert ev2["manual"]["added"] == [], ev2["manual"]
