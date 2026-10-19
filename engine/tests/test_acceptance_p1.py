"""《开发验收用例》P1 中**本版本真做了的那几条**的端到端用例（DoD §4 要求跑通 P0/P1）。

先写清这一份**不包含**什么，免得它被读成"P1 全过了"：

· PORTRAIT-003/004/005/006（多人物分层、覆盖与继承、跨图同一人确认、人工纠正优先）
  需要一套"人物身份模型"，本版本没有；
· PORTRAIT-008/010/011/012（全身、妆容头发、手脚、表情）本版本一行实现都没有；
· PICK-001（AI 挑图）要做它就得引入一个我们并没有的分类器——**拿启发式规则冒充 AI
  正是 DoD 明令禁止的那件事**；
· COLOR-004（局部调色）与 BACKGROUND-001 的"目标区域保护"只有已经存在的那几层可测。

这几条在这里**没有测试**，`tools/run-acceptance.py` 因此把它们如实写成 `uncovered`
——不是 `passed`，也不是 skip。少写一份测试是一回事，把没做的东西签成做了是另一回事。

这一份覆盖的五条都有真实现可验，判据逐条取自冻结件的 `then` 原文：

· MANUAL-001 "缩放、旋转、裁剪、重开项目 → 笔划保持正确原图位置和半径语义；显示缩放
  不改变结果"
· MANUAL-002 "重放液化后撤销再重做 → 位移连续、结果稳定；边界无拼缝；可完整撤销"
· MANUAL-003 "改变缩放和重开后重放 → 源点/目标点映射稳定；修复范围可见可撤销"
· RAW-001  "支持项完成明确的显影链；不支持项准确提示；嵌入 JPEG 预览不冒充 RAW 显影"
· PORTRAIT-007 "目标变化可控、连续；不扭曲邻近人脸；背景异常纳入人工审核"（前两句
  客观可测，"背景异常"那一半是**人工**，本文件不代签，见 case-map 的 manual 标记）

跑法同 test_acceptance_p0：必须在运行时 venv（有 torch）里跑；没 torch 整片 skip，
而执行器把 P1 的 skip 记成 `unverified` 而不是绿。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

from lumaretouch_engine.ops.light import DEFAULT_DB_RADIUS
from lumaretouch_engine.shm import FrameShm

from test_protocol import (FIXTURE, _create_and_save, _expect_error, _frame_of,
                           _load_mtd, _need_export_env, _needs_torch, _read_frame,
                           _sha_of, _wait_frame_mode, engine, extra_engine)   # noqa: F401
from test_acceptance_p0 import (DUAL, REPO, _collect_done, _dual_or_explain, _drain,
                                _live_state, _open)   # noqa: F401  (DUAL 由 _dual_or_explain 用)

# 修容带限半径：默认值取自 ops/light 那一份唯一出处（不在这里重述），
# 只有“要改变的那一档”才是测试自己的决定。
RADIUS_WIDE = 60
STROKE = (120, 80, 40, 40)      # (y0, x0, h, w)：代理帧坐标下的一块实心方块
EPS = 2                         # 判定"这一格被动过"的最小 LSB 差
TEAR_SLACK_LSB = 40             # 连续网格重采样不该造出比原图更陡的边缘，余量给插值


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
