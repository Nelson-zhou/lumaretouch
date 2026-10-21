"""《开发验收用例》P0 缺口的逐项端到端用例（DoD §4）。

这一份里每条测试都在文档串或函数体里**写出它验的是哪条用例 ID**，`tools/run-acceptance.py`
按这个引用生成"用例 → 测试节点"的映射。为什么要单独一份而不是散进各模块：散着写的时候，
覆盖这件事只能靠人脑记账——八百条测试与 80 条用例之间没有一条可复查的连线，"跑通了"就
退化成一句信念。

两条纪律：
① **判据一律取自冻结件**（`docs/p0/p0-registry-frozen.json` 的量程与中性值、ADR-0003 的
   质量阈值），测试里不刻第二份数——量程被改而测试还按旧数判，红线会静默挪位置；
② 每条测试都对着用例的 `then` 那句写，不对着"代码碰巧做了什么"写。

跑法同 test_protocol：必须在运行时 venv（有 torch）里跑；没 torch 时这一批整片 skip，
而 `run-acceptance.py` 把 P0 的 skip 记成 `unverified` 并报红——skip 不是通过。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

import numpy as np
import pytest

from lumaretouch_engine.shm import FrameShm

from test_protocol import (FIXTURE, _create_and_save, _expect_error, _frame_of, _load,
                           _need_export_env, _needs_torch, _read_frame, _sha_of,
                           _wait_frame_mode, engine, extra_engine)   # noqa: F401

# 仓库根在 tests 的上两级（engine/tests/…）：test_protocol 里的 HERE 指的是 engine 目录，
# 而这里的 REPO 要指仓库根（docs/ 在那儿）。两个名字分开写，不让人去猜哪一个。
REPO = Path(__file__).resolve().parents[2]
REG = json.loads((REPO / "docs" / "p0" / "p0-registry-frozen.json").read_text(encoding="utf-8"))

# 判「强度不是假滑块」用的磨皮配置。三个增益都落在协议校验的量程 [0, 2] 内
# （`cmd_set_strength` 那道校验是量程的唯一出处），而这一组在库层 cpu/cuda 两臂各实测
# 强度 0↔1 差 134 LSB。出厂那一组（broad 0 / mid 0 / detail 1）不够用：同一份真图两臂只
# 有 1 LSB——那是"保留全部肌理"的语义，红线贴着 1 LSB 等于没有红线。
SMOOTH_CONFIG = {"radius": 12, "eps": 0.0006, "texture_radius": 4,
                 "broad_gain": 0.55, "mid_gain": 0.35, "detail_gain": 0.25}
# 红线取 16 LSB（满幅的 6%）：实测 134，留一个"假滑块无论怎么摆都过不了"的下界，
# 而不是贴着读数取个 1——那种红线一遇抗锯齿就红。
NOT_A_FAKE_SLIDER_MIN_LSB = 16


def entry(op_id: str, key: str) -> dict:
    """按 (operation_id, parameter_key) 取冻结件那一条。取不到就响：
    冻结件改了键名而测试还按旧名找，"覆盖"会静默变成一个空表。"""
    for e in REG["entries"]:
        if e["operation_id"] == op_id and e["parameter_key"] == key:
            return e
    raise AssertionError(f"冻结注册表里没有 {op_id}.{key}：这一条判据失去了唯一出处")


def limits(op_id: str, key: str) -> tuple[float, float]:
    r = entry(op_id, key).get("range")
    assert isinstance(r, dict) and "min" in r and "max" in r, \
        f"{op_id}.{key} 的 range 不是 {{min,max}} 形状：{r}"
    return float(r["min"]), float(r["max"])


def neutral(op_id: str, key: str):
    n = entry(op_id, key).get("neutral")
    assert n is not None, f"{op_id}.{key} 没冻结中性值"
    return n


def _drain(engine, quiet: float = 0.4) -> int:
    """把队列里**已经发过而没人读**的事件排空。

    每条命令都会发一帧；上一条命令的帧没被读走时，`wait_for("frame")` 拿到的是
    那一帧旧画面，判据就成了"比较两次历史读数"。本轮的"强度 1.0 画面没变"就是
    这样假红的。排空之后再发命令，读到的那一帧才属于这一笔。
    """
    n = 0
    deadline = time.monotonic() + quiet
    while time.monotonic() < deadline:
        try:
            engine.next_event(timeout=0.1)
            n += 1
            deadline = time.monotonic() + quiet
        except (TimeoutError, Exception):
            break
    return n


def _open(engine, path: str = FIXTURE, **kw) -> dict:
    """开一张图并把 **shm_ready 与 image_ready 合成一份**返回。

    为什么要合：`name` 只在 shm_ready 里（那是缓冲的形状回执），而 `device`、
    `src_w/src_h`、`doc_state` 只在 image_ready 里。test_protocol 的 `_load` 返回
    前者，直接拿它读 device 会 KeyError——那不是产品缺字段，是回执分两条。
    等设备固定 cpu：这一批判"对不对"，两臂的字节差（≤1 LSB）由别的用例判。
    """
    engine.send(cmd="hello")
    engine.wait_for("ready", timeout=90)
    engine.send(cmd="set_device", device="cpu")
    engine.wait_for("device_set", timeout=120)
    payload = {"cmd": "load_image", "path": path, "strength": 0.0}
    payload.update(kw)
    engine.send(**payload)
    shm = engine.wait_for("shm_ready", timeout=240)
    img = engine.wait_for("image_ready", timeout=240)
    return {**shm, **img}


# 每条命令「自己那一帧」怎么认：回执名（等到它，前面别人的帧就都消费掉了）或帧里的 mode。
# 名单不全就当场响——退回去"拿下一帧"就是本轮那一记红色的来源。
_FRAME_ACK = {"set_strength": "params_set", "inpaint": "inpaint_done",
              "light": "light_done", "deform": "deform_done", "lut": "lut_done",
              "grade": "grade_done", "background": "bg_done",
              # 眼牙层（PORTRAIT-009）也是"命令自己那一帧"：cmd_enhance 先 emit
              # enhance_done 再 emit frame，与 deform/grade 同一条次序约定。
              "enhance": "enhance_done"}
_FRAME_MODE = {"crop": "crop", "exposure": "exposure"}


def _cmd_frame(engine, peer, h, w, *, cmd: str, **payload) -> np.ndarray:
    """发一条会出帧的命令，返回**这一笔**写出的那一帧像素（按回执/ mode 认，不按时间猜）。

    为什么不能"排空队列再取下一帧"（drain + wait_for("frame")）：drain 的内层是
    `next_event(timeout=0.1)` 且一遇空就 break，它赌的是"事件间隔不超过 0.1 s"；负载高时
    上一条命令的帧还压在队列里，于是拿回旧帧。
    也不能"发命令前取 peer.freshest() 的 seq，之后第一帧 seq 更大者算数"：前面几条命令
    如果没等回执，它们的帧会在取样之后才提交进 shm，seq 照样更大——探针实测到
    「请求 value=1.0 而拿回的那一帧事件自己写着 strength=0.0」，于是"强度 1.0 必须与 0.0
    不同"被报成假滑块。事件流里的位置才是身份：引擎单线程，回执之后第一条 frame
    必是本命令写的。
    """
    ack = _FRAME_ACK.get(cmd)
    mode = _FRAME_MODE.get(cmd)
    if ack is None and mode is None:
        raise AssertionError(f"不知道 {cmd} 的帧怎么认：补进 _FRAME_ACK 或 _FRAME_MODE，"
                             "不许退回去拿'下一帧'")
    engine.send(cmd=cmd, **payload)
    acked = ack is None
    want_strength = payload.get("value")
    deadline = time.monotonic() + 90.0
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            raise AssertionError(f"90 s 内没等到 cmd={cmd} 自己那一帧"
                                 f"（ack={ack} mode={mode}）")
        try:
            e = engine.next_event(timeout=min(10.0, left))
        except TimeoutError:
            continue
        if e.get("event") == "error":
            raise AssertionError(f"引擎报错: {e.get('error')}（cmd={cmd}）")
        if not acked:
            if e.get("event") == ack:
                acked = True
            continue
        if e.get("event") != "frame":
            continue
        if mode is not None and e.get("mode") != mode:
            continue
        if want_strength is not None and e.get("strength") is not None \
                and abs(float(want_strength) - float(e["strength"])) > 1e-6:
            # 帧自己报了强度而对不上：这不是本命令那一帧，跳过并继续等（认错了就是伪证）
            continue
        return _frame_of(e, peer, h, w)


def test_cmd_frame_picks_the_frame_committed_after_its_own_command():
    """执行器自己的判据（不连引擎）：只认「本命令之后提交的那一帧」。

    形状取自本轮全量回归那一记假红：队列里压着上一条命令的帧事件，旧写法
    （排空 + 取下一帧）会把旧帧当本帧返回，于是「强度 1.0 必须与 0.0 不同」变成
    「比较两次历史读数」。shm 的提交语义保证旧事件的 seq 不大于发命令前 shm 里的
    最大 seq，本命令那一帧一定更大——按 seq 认帧是确定性的，按安静窗口认是碰运气。
    """
    hh, ww = 2, 2
    old_px = bytes([7] * (hh * ww * 4))
    new_px = bytes([9] * (hh * ww * 4))

    class FakePeer:
        def freshest(self):
            return (5, 0, ww, hh, 0, 0)          # 发命令前已提交到 seq=5

        def read_pixels(self, slot):
            return old_px if slot == 0 else new_px

    class FakeEngine:
        def __init__(self, events):
            self._events = list(events)
            self.sent = []

        def send(self, **payload):
            self.sent.append(payload)

        def next_event(self, timeout=None):
            if not self._events:
                raise TimeoutError("没有更多事件")
            return self._events.pop(0)

    # 上一版红的形状：请求 value=1.0，而队列里先躺着一帧 strength=0.0 的（属于上一条
    # 命令）。只按"seq 更大"认，就会把那一帧当证据——实测到的正是这个。
    eng = FakeEngine([{"event": "frame", "seq": 5, "slot": 0, "mode": "drag", "strength": 0.0},
                      {"event": "params_set", "strength": 1.0},
                      {"event": "frame", "seq": 6, "slot": 1, "mode": "drag", "strength": 1.0}])
    got = _cmd_frame(eng, FakePeer(), hh, ww, cmd="set_strength", value=1.0)
    assert eng.sent == [{"cmd": "set_strength", "value": 1.0}], eng.sent
    assert got[..., 0].tolist() == [[9, 9], [9, 9]], \
        "拿回的是队列里那条旧事件的帧：判据变成比历史读数，P0 中性那条会假红"
    # 没有回执的命令按 mode 认（crop 只出带 mode 的帧）
    eng2 = FakeEngine([{"event": "frame", "seq": 7, "slot": 0, "mode": "drag", "strength": 1.0},
                      {"event": "frame", "seq": 8, "slot": 1, "mode": "crop"}])
    got2 = _cmd_frame(eng2, FakePeer(), hh, ww, cmd="crop", action="clear")
    assert got2[..., 0].tolist() == [[9, 9], [9, 9]], got2


def _live_state(engine) -> dict:
    """当前文档的 live 状态（session_state 里那份，不是格子里的快照）。"""
    engine.send(cmd="session", action="state")
    ev = engine.wait_for("session_state", timeout=30)
    return ev.get("doc_state") or {}


def _recipe(state: dict) -> dict:
    """状态里"配方"那一部分（去掉历史账）。

    doc_state 里带着 `history`（can_undo/undo_steps 那一堆）：它随每一步变，与
    "配方恢复得对不对"是两件事。整份比就会把"撤销确实生效了"误判成"配方没恢复"——
    这里要判的是参数，不是账。
    """
    return {k: v for k, v in (state or {}).items() if k != "history"}


# ------------------------------------------------------------------ P0-*-BOUNDARY
@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像")
def test_boundary_and_illegal_params_are_refused_without_half_state(engine):
    """P0-EXPOSURE-BOUNDARY / P0-WHITE_BALANCE-BOUNDARY / P0-CROP-BOUNDARY /
    P0-MASK-BOUNDARY / P0-BLEMISH-BOUNDARY。

    三件事一起判，缺一件就不叫"边界无崩溃、非法输入拒绝"：
    ① 越界与畸形输入必须**明确拒绝**（ADR-0003：拒绝而不是夹取——夹取会让坏配方看起来
       正常，而画面不是用户要的那张）；
    ② 被拒之后 live 状态必须与拒之前**逐键相同**（半截状态最难复查：参数改了一半、层建了
       一半，画面看着还挺正常）；
    ③ 量程**端点本身合法**（端点被拒是另一类错：滑块推到最大就报错，用户只会认为产品坏了）。

    蒙版与祛瑕这两组的作用面就在 `set_strength(channel=…)` 与画笔的 `rle` 上：本版本没有
    独立的 overlay/feather 通路（UI 里那两格显式禁用并写了原因），所以这里判的是它们
    **真正能被递到的那两条入口**，不给不存在的入口编判据。
    """
    _needs_torch()
    lo_ev, hi_ev = limits("lnx.exposure.v1", "ev")
    lo_k, hi_k = limits("lnx.white_balance.v1", "temperature_shift")
    lo_t, hi_t = limits("lnx.white_balance.v1", "tint_shift")
    lo_r, hi_r = limits("lnx.crop.v1", "rotation_degrees")
    meta = _load(engine, max_px=207360, strength=0.0)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    base = _read_frame(engine, peer, h, w)

    cases = [
        ("exposure", {"ev": 1e9}, "越界"),
        ("exposure", {"ev": float("nan")}, "NaN/Inf"),
        ("exposure", {"ev": "一度"}, "非法"),
        ("exposure", {"temperature_shift": hi_k + 1}, "越界"),
        ("exposure", {"temperature_shift": lo_k - 1}, "越界"),
        ("exposure", {"tint_shift": hi_t + 0.5}, "越界"),
        ("exposure", {"tint_shift": lo_t - 0.5}, "越界"),
        ("exposure", {"action": "翻一下"}, "action"),
        ("crop", {"rect": [0.9, 0.1, 0.1, 0.9]}, "x0"),
        ("crop", {"rect": [0.0, 0.0, 1.0, 2.0]}, "越界"),
        ("crop", {"rect": [0.0, 0.0, 0.5]}, "4 个数"),
        ("crop", {"rotation_degrees": hi_r + 1}, "越界"),
        ("crop", {"rotation_degrees": float("inf")}, "NaN/Inf"),
        ("crop", {"action": "bogus"}, "action"),
        # 蒙版这一族的真实入口：通道名认不出来就拒（不静默退回全图）
        ("set_strength", {"channel": "不存在的通道"}, "通道"),
        # 画笔（祛瑕/修容）的行程编码：非法形状整条拒，不截断也不"忽略这一笔"
        ("inpaint", {"action": "bogus"}, "action"),
        ("inpaint", {"action": "add", "rle": [[-1, 0, 5, 255]], "radius": 4,
                     "feather": 0}, "rle"),
        ("inpaint", {"action": "add", "rle": "not-a-list"}, "rle"),
        ("inpaint", {"action": "add", "rle": [[0, 0, 10 ** 9, 255]], "radius": 4,
                     "feather": 0}, "rle"),
        ("light", {"action": "add", "rle": [[0, 0, 10 ** 9, 128]], "radius": 4,
                   "feather": 0}, "rle"),
    ]
    for cmd, payload, word in cases:
        before = _live_state(engine)
        engine.send(cmd=cmd, **payload)
        ev = _expect_error(engine, word, timeout=30)
        after = _live_state(engine)
        assert before == after, (
            f"{cmd} {payload} 被拒（{ev['error']}）却改了状态：留下半截状态比报错更坏")
    # 端点合法：只有上面那些而没有这一段，会得到一个"什么都不敢收"的产品
    engine.send(cmd="exposure", ev=hi_ev, temperature_shift=hi_k, tint_shift=hi_t)
    _wait_frame_mode(engine, "exposure")
    st = _live_state(engine)["exposure"]
    assert st["ev"] == pytest.approx(hi_ev) and st["temperature_shift"] == pytest.approx(hi_k) \
        and st["tint_shift"] == pytest.approx(hi_t), st
    engine.send(cmd="exposure", ev=lo_ev, temperature_shift=lo_k, tint_shift=lo_t)
    _wait_frame_mode(engine, "exposure")
    engine.send(cmd="crop", rect=list(neutral("lnx.crop.v1", "rect_normalized")),
                rotation_degrees=lo_r)
    _wait_frame_mode(engine, "crop")
    engine.send(cmd="exposure", action="clear")
    _wait_frame_mode(engine, "exposure")
    back = _cmd_frame(engine, peer, h, w, cmd="crop", action="clear")
    assert int(np.abs(back - base).max()) == 0, "清完两层后画面没回到未点火那一幅"


# ------------------------------------------------------------------ P0-*-NEUTRAL
@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像")
def test_neutral_params_are_byte_identity_and_survive_save_reopen(engine, extra_engine,
                                                                 tmp_path):
    """P0-EXPOSURE-NEUTRAL / P0-WHITE_BALANCE-NEUTRAL / P0-CROP-NEUTRAL /
    P0-MASK-NEUTRAL / P0-BLEMISH-NEUTRAL。

    ADR-0003 把中性定死为**逐字节恒等**（16-bit 主链，容差 0）：中性位不该是"算出来恰好
    一样"，而是那一层根本没点火。保存重开那一半判的是"参数、坐标、依赖版本"三件事都活得
    下来——依赖版本这一格就是工程文件里的 `writer` 戳，重开时引擎比一次并把结果报出来
    （`writer_match`）。
    """
    _needs_torch()
    meta = _open(engine, max_px=207360)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    # base 也必须由"这一次 set_strength"产出：load 那一条的帧已经在队列里，
    # 排空它再等下一条不会来的帧，只会得到一片超时
    base = _cmd_frame(engine, peer, h, w, cmd="set_strength", value=0.0)
    src_sha = _sha_of(FIXTURE)
    engine.send(cmd="exposure", ev=neutral("lnx.exposure.v1", "ev"),
                temperature_shift=neutral("lnx.white_balance.v1", "temperature_shift"),
                tint_shift=neutral("lnx.white_balance.v1", "tint_shift"))
    _wait_frame_mode(engine, "exposure")
    rect_n = list(neutral("lnx.crop.v1", "rect_normalized"))
    engine.send(cmd="crop", rect=rect_n,
                rotation_degrees=neutral("lnx.crop.v1", "rotation_degrees"))
    _wait_frame_mode(engine, "crop")
    engine.send(cmd="inpaint", action="clear")        # 祛瑕中性=没有笔迹
    engine.send(cmd="light", action="clear")
    # 蒙版中性=强度 0 且不作用掩膜；这一笔会出帧，按帧自己读
    hot = _cmd_frame(engine, peer, h, w, cmd="set_strength", value=1.0, **SMOOTH_CONFIG)
    d_hot = int(np.abs(hot - base).max())
    assert d_hot >= NOT_A_FAKE_SLIDER_MIN_LSB, (
        f"真要磨皮的配置下强度 1.0 只动了 {d_hot} LSB（红线 {NOT_A_FAKE_SLIDER_MIN_LSB}）："
        "那是假滑块")
    # 中性位那条判据一个字不放松：strength=0 时混合式是 `(1-0)*底图 + 0*磨皮结果`，
    # 配置再怎么磨都不许漏进画面——这一条比"出厂配置下不动"强得多（0 × 任何东西恒为 0）。
    cold = _cmd_frame(engine, peer, h, w, cmd="set_strength", value=0.0,
                      channel=None, **SMOOTH_CONFIG)
    d = int(np.abs(cold - base).max())
    assert d == 0, f"全部回写中性位后画面差 {d} LSB：冻结口径是逐字节恒等"

    _created, saved = _create_and_save(engine, tmp_path, name="中性回归")
    pfile = saved["path"]
    raw = json.loads(Path(pfile).read_text(encoding="utf-8"))
    w_stamp = raw.get("writer") or {}
    assert w_stamp.get("engine") and w_stamp.get("python") and "numpy" in w_stamp, \
        f"工程文件没记写手环境（依赖版本这一格缺了）：{w_stamp}"

    eng2 = extra_engine("neutral-reopen")
    eng2.send(cmd="hello")
    eng2.wait_for("ready", timeout=90)
    eng2.send(cmd="set_device", device="cpu")
    eng2.wait_for("device_set", timeout=120)
    eng2.send(cmd="project", action="open", path=pfile)
    op = eng2.wait_for("project_opened", timeout=120)
    assert op["writer_match"] is True, f"同一台机器重开却报环境不一致：{op.get('writer')}"
    shm2 = eng2.wait_for("shm_ready", timeout=240)
    ready2 = eng2.wait_for("image_ready", timeout=240)
    ds = ready2["doc_state"]
    assert ds["exposure"]["ev"] == pytest.approx(0.0) and \
        ds["exposure"]["temperature_shift"] == pytest.approx(0.0) and \
        ds["exposure"]["tint_shift"] == pytest.approx(0.0), ds["exposure"]
    assert [round(v, 6) for v in ds["crop"]["rect"]] == [round(v, 6) for v in rect_n], ds["crop"]
    assert ds["crop"]["lit"] is False, "中性裁剪被当成已点火：那一层应当没点火"
    peer2 = FrameShm(shm2["name"])
    got2 = _frame_of(eng2.wait_for("frame", timeout=60), peer2, shm2["h"], shm2["w"])
    assert int(np.abs(got2 - base).max()) == 0, "重开后的画面与保存前不是同一幅"
    assert _sha_of(FIXTURE) == src_sha, "打开/保存工程动了原片"


# ------------------------------------------------------------------ CORE-003
def test_orientation_is_normalized_exactly_once(engine, tmp_path):
    """CORE-003 方向规范化：EXIF orientation 只生效一次，裁剪坐标与之同口径。

    手机竖拍常常是「横着存 + orientation=6」。两个失败方向都要堵住：不转（横着上屏）与
    转两次（倒过来）。这里与"独立摆正的参照图"逐像素对拍，而不是只看宽高——宽高对了而
    像素转糊了，是真实存在过的一类错。
    """
    from PIL import Image

    _need_export_env()
    src = Image.open(FIXTURE).convert("RGB")
    # orientation=6 的语义：存储态需要顺时针转 90° 才是正视图 → 存图前先逆时针转 90°
    stored = src.transpose(Image.Transpose.ROTATE_90)
    ex = Image.Exif()
    ex[274] = 6                                     # 0x0112 = Orientation
    up = tmp_path / "oriented.jpg"
    stored.save(up, format="JPEG", exif=ex.tobytes())

    meta = _open(engine, str(up), max_px=207360)
    assert (meta["src_w"], meta["src_h"]) == src.size, \
        f"报出去的源尺寸没按 EXIF 摆正：{(meta['src_w'], meta['src_h'])} vs {src.size}"
    def ref_for(img) -> np.ndarray:
        return np.asarray(img.resize((meta["w"], meta["h"]), Image.LANCZOS), dtype=np.int16)

    peer = FrameShm(meta["name"])
    frame = _read_frame(engine, peer, meta["h"], meta["w"])
    # 三方对比：摆正的、顺时针转错的、逆时针转错的。绝对容差在这里不可信——引擎会走
    # libjpeg 的 draft 缩放（1/2、1/4 档），与这里 LANCZOS 直接缩到同一尺寸的边界行为
    # 就是不一样（实测 30 LSB 量级）；而"转错方向"的差是几百 LSB 量级，两者分得开。
    up_ref = ref_for(src)
    cw = ref_for(src.transpose(Image.Transpose.ROTATE_270))
    ccw = ref_for(src.transpose(Image.Transpose.ROTATE_90))
    d_up = int(np.abs(frame - up_ref).mean())
    d_bad = min(int(np.abs(frame - cw).mean()), int(np.abs(frame - ccw).mean()))
    assert d_up < d_bad, f"画面更像转错方向那一幅（摆正均值差 {d_up} vs 错向 {d_bad}）"
    assert d_up <= 40, f"与摆正参照差 {d_up}：方向处理不只是转的问题"
    # 裁剪落点必须按摆正后的画面算：裁中间一半，导出尺寸应当正好是摆正尺寸的一半
    engine.send(cmd="crop", rect=[0.25, 0.25, 0.75, 0.75], rotation_degrees=0.0)
    _wait_frame_mode(engine, "crop")
    out = tmp_path / "out"
    engine.send(cmd="export", out_dir=str(out), format="png", tile=256, quality=90,
                images=[str(up)])
    done, _ = _collect_done(engine)
    assert done["failed"] == 0, done
    with Image.open(done["images"][0]["out"]) as im:
        assert im.size == (src.size[0] // 2, src.size[1] // 2), \
            f"裁剪按存储态方向算了：{im.size} vs 期望 {(src.size[0] // 2, src.size[1] // 2)}"


def _collect_done(engine, timeout=240.0):
    from test_protocol import _collect_until
    return _collect_until(engine, "export_done", timeout=timeout)


# ------------------------------------------------------------------ CORE-004
def test_sources_are_read_only_and_export_cannot_target_them(engine, tmp_path):
    """CORE-004 原图只读：全部源文件哈希与字节数不变；导出不能指向输入文件。

    后半条是**开跑前**判的，不是写到那一张时才判：批量清单里只要有一张与输入同名同目录，
    默认的 skip_and_report 会让整批"完成而一个新文件都没写"，事件里只写着跳过——用户
    看到的是"导出了"而盘上没有。而这条不变量也不该依赖"今天没有 overwrite 策略"。
    """
    _need_export_env()
    import shutil
    dir_in = tmp_path / "originals"
    dir_in.mkdir()
    files = []
    for i in range(2):
        dst = dir_in / f"src-{i}.jpg"
        shutil.copyfile(FIXTURE, dst)
        files.append(dst)
    before = {str(f): (_sha_of(str(f)), f.stat().st_size) for f in files}

    _load(engine, max_px=207360, strength=0.5)
    engine.send(cmd="exposure", ev=0.5)
    _wait_frame_mode(engine, "exposure")
    out = tmp_path / "out"
    engine.send(cmd="export", out_dir=str(out), format="jpg", quality=90, tile=256,
                images=[str(f) for f in files])
    done, _ = _collect_done(engine)
    assert done["failed"] == 0 and done["total"] == 2, done
    assert len(list(out.iterdir())) == 2, "导出没落到 out_dir"

    n_before = sorted(os.listdir(dir_in))
    engine.send(cmd="export", out_dir=str(dir_in), format="jpg", quality=90, tile=256,
                images=[str(f) for f in files])
    ev = _expect_error(engine, "原片只读")
    assert "输入文件本身" in ev["error"], ev["error"]
    assert sorted(os.listdir(dir_in)) == n_before, "被拒的导出仍然动了输入目录"
    for f in files:
        assert (_sha_of(str(f)), f.stat().st_size) == before[str(f)], \
            f"{f} 被这个会话改过：原片只读破了"


# ------------------------------------------------------------------ CORE-006
def test_undo_redo_restores_recipe_and_named_versions_survive(engine, extra_engine, tmp_path):
    """CORE-006 历史撤销重做：配方正确恢复；命名版本不被撤销删掉；分支策略明确。

    本版本写死的分支策略：**撤销后再做一个新操作就丢弃 redo 栈**（线性历史，不保留分支）。
    这是绘图软件里唯一能被用户预测的行为；而工程里的命名版本属于"账"不属于"历史"，
    撤销不许把它一起抹掉。
    """
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.4)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    base = _read_frame(engine, peer, h, w)
    at_load = _live_state(engine)       # 刚导入那一份配方：退到底应当回到这里
    engine.send(cmd="exposure", ev=1.0)
    lit = _wait_frame_mode(engine, "exposure")
    lit_px = _frame_of(lit, peer, h, w)
    assert int(np.abs(lit_px - base).max()) > 0, "曝光没作画"
    engine.send(cmd="crop", rect=[0.1, 0.1, 0.9, 0.9], rotation_degrees=3.0)
    _wait_frame_mode(engine, "crop")
    engine.send(cmd="history", action="state")
    st = engine.wait_for("history_state", timeout=30)
    steps = int(st["undo_steps"])
    # 步数由引擎报，不在这刻第二份数：分组（同一支滑块的连续拖动算一步）是它的口径
    assert st["can_undo"] is True and steps >= 1, st

    engine.send(cmd="project", action="create", name="历史工程", directory=str(tmp_path))
    engine.wait_for("project_created", timeout=30)
    engine.send(cmd="project", action="save")
    saved = engine.wait_for("project_saved", timeout=90)
    pfile = saved["path"]

    # 一路退到底：undo_steps 步之后配方必须回到"刚导入"那一份，画面也是同一幅
    for _ in range(steps):
        engine.send(cmd="history", action="undo")
        _wait_frame_mode(engine, "history_undo")
    assert _recipe(_live_state(engine)) == _recipe(at_load), \
        "撤销到底之后配方不是刚导入那一份"
    check = _cmd_frame(engine, peer, h, w, cmd="set_strength", value=0.4)
    assert int(np.abs(check - base).max()) == 0, "撤销到底后画面没回到刚导入那一幅"
    engine.send(cmd="history", action="redo")
    _wait_frame_mode(engine, "history_redo")
    redone_state = _live_state(engine)     # 帧事件不带 doc_state，配方要从状态里读
    engine.send(cmd="history", action="state")
    st_mid = engine.wait_for("history_state", timeout=30)
    assert st_mid["can_redo"] is (int(st_mid["redo_steps"]) > 0), st_mid
    assert _recipe(redone_state) != _recipe(at_load), \
        "重做拿回来的还是刚导入那一份：那一步没回来"
    # 分支策略：撤销一格后接一个新操作，redo 栈必须清空
    engine.send(cmd="history", action="undo")
    engine.send(cmd="exposure", ev=0.25)
    _wait_frame_mode(engine, "exposure")
    engine.send(cmd="history", action="state")
    st2 = engine.wait_for("history_state", timeout=30)
    assert st2["can_redo"] is False, f"新操作之后还能 redo：分支没有被明确处理（{st2}）"

    eng2 = extra_engine("reopen-history")
    eng2.send(cmd="hello")
    eng2.wait_for("ready", timeout=90)
    eng2.send(cmd="set_device", device="cpu")
    eng2.wait_for("device_set", timeout=120)
    eng2.send(cmd="project", action="open", path=pfile)
    op = eng2.wait_for("project_opened", timeout=120)
    assert op["docs"] == 1, op
    raw = json.loads(Path(pfile).read_text(encoding="utf-8"))
    ver = raw["docs"][0]["versions"]
    assert ver and ver[0]["name"], f"工程里没有命名版本：{ver}"
    ds = eng2.wait_for("image_ready", timeout=240)["doc_state"]
    assert ds["exposure"]["ev"] == pytest.approx(1.0), \
        f"重开后的配方不是保存时那一份：{ds['exposure']}"


# ------------------------------------------------------------------ CORE-009
def test_hostile_or_incompatible_project_is_inert(engine, tmp_path):
    """CORE-009 参数校验：不兼容项明确拒绝；不执行外部代码；不静默改变数值。

    工程文件是**用户能编辑的输入**，也是本产品唯一会被"从磁盘递进来"的结构化数据。
    它只被当 JSON 读（没有 pickle、没有 eval、没有按内容 import），因此判据是：
    ① schema 不认 → 拒开并说清认哪个；② 恶意字段（可执行表达式、路径穿越、伪资产引用）
    既不执行也不越界写；③ 合法数值原样回来（"顺手换算一下"要能被抓住）。
    """
    _needs_torch()
    _load(engine, max_px=207360, strength=0.3)
    _created, saved = _create_and_save(engine, tmp_path, name="恶意输入")
    pfile = saved["path"]
    doc = json.loads(Path(pfile).read_text(encoding="utf-8"))
    assert doc["schema_version"] == "lrt.project.v1", doc["schema_version"]
    marker = "/tmp/lrt-pwned"
    recipe = doc["docs"][0]["versions"][0]["recipe"]
    recipe["__exec__"] = "__import__('os').open(r'%s','w').write('x')" % marker
    recipe["asset_ref"] = {"__asset__": "sha256:" + "0" * 64, "at": "nowhere"}
    recipe["path_escape"] = "../../../../etc/lurma"
    recipe["strength"] = 12.0                       # 越界：不夹取，不"顺手归一"
    doc["schema_version"] = "lrt.project.v99"
    hostile = tmp_path / "hostile-copy.lrproject.json"
    hostile.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    pfile = str(hostile)
    assert not os.path.exists(marker), "测试自身不该有副作用"

    engine.send(cmd="project", action="open", path=pfile)
    ev = _expect_error(engine, "schema")
    assert "lrt.project.v99" in ev["error"], ev["error"]
    assert not os.path.exists(marker), "读工程文件时执行了里面的东西"
    assert not os.path.exists("/etc/lurma"), "路径穿越被当成了要写的地方"
    # 拒开之后引擎还活着，而且没把那份工程装进会话
    st = _live_state(engine)
    engine.send(cmd="session", action="state")
    ss = engine.wait_for("session_state", timeout=30)
    assert ss["project"]["path"] != pfile, f"被拒的工程仍然成了当前工程：{ss['project']}"
    assert st.get("strength") is not None, "拒开之后连当前文档状态都没了"

    # 数值不被静默改变：合法范围内的小数存进去再拿回来，必须逐位相同
    engine.send(cmd="exposure", ev=0.30000000000000004)
    _wait_frame_mode(engine, "exposure")
    _c2, saved2 = _create_and_save(engine, tmp_path, name="数值原样")
    doc2 = json.loads(Path(saved2["path"]).read_text(encoding="utf-8"))
    got = doc2["docs"][0]["versions"][0]["recipe"]["_exposure"][0]
    assert repr(got) == repr(0.30000000000000004), f"保存时把这个数改了：{got!r}"


# ------------------------------------------------------------------ RENDER-006
def test_cpu_path_completes_without_silent_quality_or_size_drop(engine, tmp_path):
    """RENDER-006 CPU 路径：功能可完成；没有质量/分辨率静默降低；资源限制清楚显示。

    "CPU 也能跑"不是把 GPU 那一套偷偷换成另一套算法：代理档尺寸、满幅导出尺寸、常驻
    字节账都必须原样报出来。设备这一格只信引擎自报（`image_ready.device`），不信调用方
    请求过什么——请求 cuda 而没 GPU 时真正落下来的是 cpu，那件事必须看得见。
    """
    _need_export_env()
    meta = _open(engine, max_px=207360)
    assert meta["device"] == "cpu", meta["device"]
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    # CPU 不是“能开而不能编辑”的展示模式：拖一下滑块必须真出一帧，而且两帧不一样
    soft = _cmd_frame(engine, peer, h, w, cmd="set_strength", value=0.6)
    hard = _cmd_frame(engine, peer, h, w, cmd="set_strength", value=1.0)
    assert int(np.abs(hard - soft).max()) > 0, "CPU 上拖强度画面不动：那是假控件"
    engine.send(cmd="exposure", ev=0.4)
    _wait_frame_mode(engine, "exposure")
    out = tmp_path / "cpu"
    engine.send(cmd="export", out_dir=str(out), format="png", tile=256, quality=90,
                images=[FIXTURE])
    done, _ = _collect_done(engine)
    assert done["failed"] == 0, done
    from PIL import Image
    with Image.open(done["images"][0]["out"]) as im:
        assert im.size == (meta["src_w"], meta["src_h"]), \
            f"CPU 路径悄悄换了输出尺寸：{im.size} vs {(meta['src_w'], meta['src_h'])}"
    # 常驻账在 CPU 上也要报得出（"资源限制清楚显示"指的是用户能看见自己付了多少）
    for k in ("bytes_filter", "bytes_bands", "bytes_light", "bytes_deform"):
        assert isinstance(meta.get(k), int), f"{k} 没随 image_ready 报出来：{meta.get(k)}"


# ------------------------------------------------------------------ RENDER-008
def test_clearing_caches_keeps_source_recipe_and_versions(engine, tmp_path):
    """RENDER-008 清理缓存安全：原图、配方、版本不丢；预览可重建。

    本版本能被用户清掉的"缓存"只有两处：撤销/重做栈（history clear）与常驻张量
    （换设备会整条重建会话）。清完必须还能画出同一幅画面——重建路径若算出另一张图，
    "缓存只是可丢弃的加速件"这句话就是假的。
    """
    _needs_torch()
    meta = _open(engine, max_px=207360)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    _cmd_frame(engine, peer, h, w, cmd="set_strength", value=0.7)
    engine.send(cmd="exposure", ev=0.6, temperature_shift=200.0)
    lit = _wait_frame_mode(engine, "exposure")
    keep = _frame_of(lit, peer, h, w)
    src_sha = _sha_of(FIXTURE)
    _created, saved = _create_and_save(engine, tmp_path, name="清缓存")
    pfile = saved["path"]

    engine.send(cmd="history", action="clear")
    st = engine.wait_for("history_state", timeout=30)
    assert st["undo_steps"] == 0 and st["can_undo"] is False, st
    # 换设备 = 会话整条重建（新张量 + 按存下的参数重放）：这就是"清掉所有缓存"的最强形式
    other = "cuda" if meta["device"] == "cpu" else "cpu"
    _drain(engine)
    engine.send(cmd="set_device", device=other)
    engine.wait_for("device_set", timeout=240)
    _drain(engine)
    engine.send(cmd="set_strength", value=0.7)     # 重建后重新出一帧（同参数同画面）
    rebuilt = _read_frame(engine, peer, h, w)
    d = int(np.abs(rebuilt - keep).max())
    assert d <= 1, f"清栈+重建会话后画面差 {d} LSB：可重建这件事没做到"
    ds = _live_state(engine)
    assert ds["exposure"]["ev"] == pytest.approx(0.6), f"配方被清掉了：{ds.get('exposure')}"
    assert _sha_of(FIXTURE) == src_sha, "清缓存动了原片"
    raw = json.loads(Path(pfile).read_text(encoding="utf-8"))
    assert raw["docs"][0]["versions"], "工程里的命名版本被清没了"


# ------------------------------------------------------------------ EXPORT-003
def test_export_refuses_invalid_combinations_instead_of_losing_data(engine, tmp_path):
    """EXPORT-003 格式组合校验：阻止无效组合或要求明确转换，不静默丢弃信息。

    每条被拒的组合都是一类**能被解释**的错（不是随手加的闸）：
    · 16-bit 母档只走 TIFF——JPEG/WebP 有损，PNG 那条写手不接三通道 uint16，选它等于交一张
      假母档或偷偷降到 8-bit；
    · 位深、冲突策略、输出 ICC、TIFF 压缩都只认冻结枚举里的值；不在枚举里的（例如
      overwrite）一律拒——EXPORT-001 要的"无无提示覆盖"就是从这儿来的；
    · 只对某一种格式有意义的参数，递到别的格式上不当"忽略"处理（忽略等于静默丢信息）。
    """
    _need_export_env()
    _load(engine, max_px=207360, strength=0.0)
    out = tmp_path / "out"
    for payload, word in (
        ({"bit_depth": 16, "format": "png"}, "TIFF"),
        ({"bit_depth": 16, "format": "tif", "tiff_compression": "jpeg"}, "tiff_compression"),
        ({"bit_depth": 8, "format": "heic"}, "格式"),
        ({"bit_depth": 7}, "bit_depth"),
        ({"bit_depth": "16位"}, "bit_depth"),
        ({"conflict_policy": "overwrite"}, "conflict_policy"),
        ({"output_profile": "adobergb"}, "output_profile"),
        ({"tiff_compression": "packbits"}, "tiff_compression"),
        ({"quality": 0}, "quality"),
        ({"tile": 128}, "tile"),
        ({"metadata_include_gps": "yes"}, "metadata_include_gps"),
    ):
        cmd = {"cmd": "export", "out_dir": str(out), "images": [FIXTURE]}
        cmd.update(payload)
        engine.send(**cmd)
        _expect_error(engine, word, timeout=30)
    assert not out.exists() or not list(out.iterdir()), \
        "被拒的导出还是把目录建出来/写出了文件"


# ------------------------------------------------------------------ FORMAT-001
def test_quality_mapping_version_and_encoder_value_are_recorded(engine, tmp_path):
    """FORMAT-001 JPEG 量表映射版本化：记录编码器值与 mapping_version，
    不得宣称与竞品 0—14 等价。

    这条用例的本体是"可回溯"：一年后有人问"这批片子按什么质量出的"，导出清单必须自己
    带着答案。`encoder_quality` 记的是**真正递给编码器的那个数**（无损格式为 None，不是 0），
    `quality_mapping_version` 是本厂量表的版本号——它的值刻意不含任何外部量表的名字。
    """
    _need_export_env()
    _load(engine, max_px=207360, strength=0.0)
    out = tmp_path / "q"
    seen = {}
    for fmt, q in (("jpg", 92), ("png", 95), ("tif", 88)):
        engine.send(cmd="export", out_dir=str(out), format=fmt, quality=q, tile=256,
                    images=[FIXTURE])
        done, _ = _collect_done(engine)
        assert done["failed"] == 0, done
        img = done["images"][0]
        seen[fmt] = img
        assert img["quality_mapping_version"] == "lrt.quality.v1", img
        assert done["quality"] == q, f"批级质量账与请求不一致：{done.get('quality')}"
        if fmt == "jpg":
            assert img["encoder_quality"] == q, f"JPEG 递给编码器的值与请求不一致：{img}"
        else:
            assert img["encoder_quality"] is None, \
                f"{fmt} 是无损的，encoder_quality 该是 None 而不是编出来的数：{img}"
        if fmt == "png":
            assert 0 <= int(img["compress_level"]) <= 6, f"PNG 压缩档越出实测曲线：{img}"
        blob = json.dumps(img, ensure_ascii=False)
        assert not re.search(r"(?i)(equivalent|equivalence|等价)", blob), blob
    # 版本串在同一批里必须一致：它若随每张图变，"这批是按哪版量表出的"就无从回答
    assert len({v["quality_mapping_version"] for v in seen.values()}) == 1, seen


# ------------------------------------------------------------------ FORMAT-002
def test_multipage_container_is_refused_not_silently_first_page(engine, tmp_path):
    """FORMAT-002 格式边界：明确多页不支持，不静默丢页。

    "只解第一页"是最坏的一种失败：文件写出来了、名字对、尺寸对，而它是那一叠里的第一页，
    用户直到打印才发现少了后面几页。这一版没有多页编辑也没有多页落盘（注册表里没有这一格），
    所以把不支持说清楚，而不是假装支持（与 RAW 那条"宁缺不假"同一条纪律）。
    """
    from PIL import Image

    _need_export_env()
    src = Image.open(FIXTURE).convert("RGB").resize((160, 120), Image.LANCZOS)
    pages = tmp_path / "pages.tif"
    src.save(pages, format="TIFF", save_all=True, append_images=[src, src])
    with Image.open(pages) as probe:
        assert getattr(probe, "n_frames", 1) > 1, "夹具本身没造出多页，这条用例就没意义"
    _load(engine, max_px=207360, strength=0.0)          # 先 handshake，让 error 落在同一条流上
    engine.send(cmd="load_image", path=str(pages), max_px=207360, strength=0.0)
    ev = _expect_error(engine, "页")
    assert "单页" in ev["error"], ev["error"]
    # 单页 TIFF 必须照常能开：拒多页不等于拒 TIFF
    single = tmp_path / "single.tif"
    src.save(single, format="TIFF")
    engine.send(cmd="load_image", path=str(single), max_px=207360, strength=0.0)
    meta = engine.wait_for("image_ready", timeout=120)
    assert (meta["src_w"], meta["src_h"]) == (160, 120), meta


# ------------------------------------------------------------------ SEC-001
def test_no_egress_or_telemetry_anywhere_in_the_shipped_code():
    """SEC-001 不收集隐私遥测：默认不发送图像、人脸向量、EXIF 或文件路径。

    静态可判的部分就静态判（比"跑一次看有没有网络流量"更能覆盖分支）：整个交付物里
    不许出现任何出网调用面。这不是"暂时没接上"，而是产品定义本身——离线普惠、本地优先，
    代码里若出现一个 http 客户端，评审时它必须是个事故而不是一行普通代码。
    真正的"这台机器没出过网"由 packaging/preflight.sh 与装机自证那一段负责（LINUX-001）。
    """
    roots = ["engine/src/lumaretouch_engine", "ui/src", "ui/src-tauri/src", "packaging",
             "tools"]
    # 每条都带括号或点号，避免把文档里"不联网"这类散文误判成调用
    patterns = [
        r"\bsocket\.socket\s*\(", r"\burllib\.request\b", r"\bhttp\.client\b",
        r"\brequests\.(get|post|put)\s*\(", r"\bfetch\s*\(", r"\bXMLHttpRequest\b",
        r"\bWebSocket\b", r"\bcurl\b", r"\bwget\b", r"\bnslookup\b",
        r"pycurl\b", r"\bgql\b.*execute", r"\btelemetry\b", r"\btrack[_i]?(ng|er)\b",
        r"\bAnalytics\b", r"\bSentryClient\b", r"\.upload_to\b",
    ]
    hits = []
    for r in roots:
        base = REPO / r
        assert base.is_dir(), f"扫描根目录不存在：{r}（扫描范围缩水就等于门禁失效）"
        for f in sorted(base.rglob("*")):
            if not f.is_file() or f.suffix not in (".py", ".ts", ".tsx", ".rs", ".sh",
                                                   ".json", ".html"):
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
            for pat in patterns:
                if pat in (r"\bfetch\s*\(",) and f.suffix == ".rs":
                    continue            # Rust 侧没有浏览器的 fetch；这里只判前端与脚本
                for m in re.finditer(pat, text):
                    line = text[:m.start()].count("\n") + 1
                    hits.append(f"{f.relative_to(REPO)}:{line}: {pat}")
    assert not hits, "发现出网/遥测的调用面：\n" + "\n".join(hits[:12])


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像")
def test_events_never_carry_absolute_paths_off_the_machine(engine):
    """SEC-001 的另一半：错误报告可预览并脱敏。

    本产品**没有**"把日志发出去"这条通路（上一条测试已经把调用面扫干净了），所以这里的
    判据是"就算用户自己复制事件流去求助，那份东西也不能泄露他家目录结构"：会话事件里
    出现的绝对路径必须是他自己给进来的图片路径（他要指认那张图），而诊断类文本里不许
    混进 /home/<用户名> 这种环境指纹。
    """
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.0)
    engine.send(cmd="session", action="state")
    ss = engine.wait_for("session_state", timeout=30)
    blob = json.dumps({"image_ready_keys": sorted(k for k in meta if k != "doc_state"),
                       "session": {k: ss[k] for k in ("index", "count", "project")}},
                      ensure_ascii=False)
    home = os.path.expanduser("~")
    assert home not in blob, f"事件里带着家目录指纹：{home}"
    assert "/home/" not in blob, blob


# ------------------------------------------------------------------ RENDER-003
@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像")
def test_frame_sequence_is_monotonic_and_slot_never_lies(engine, tmp_path):
    """RENDER-003 迟到结果淘汰：画布最终只显示后请求的那一版，前结果不能覆盖。

    本产品的渲染是**单写者**（引擎主循环按命令顺序写 shm），所以"迟到结果盖掉新结果"
    在这里不是一个竞态窗口，而是一条必须成立的结构性事实：
    ① `frame.seq` 严格递增（读端按它淘汰旧帧）；
    ② 同一个 seq 只落在一个 slot 上（双缓冲的槽号是回执的一部分，槽号若能为同一个 seq
       变两次，读端按事件取到的像素就不是它说的那一帧）；
    ③ 中途换文档、切设备这些"会重开缓冲"的动作也不许把 seq 发回过去——宿主的重置规则
       以"每条 shm_ready 都是新缓冲"为准，seq 从 1 重计只允许发生在**换档那一刻**。
    """
    _needs_torch()
    meta = _open(engine, max_px=207360)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    seen: list[tuple[int, int]] = []        # (seq, slot)
    for i in range(12):
        _drain(engine)
        engine.send(cmd="set_strength", value=0.2 + 0.05 * i)
        e = engine.wait_for("frame", timeout=30)
        seen.append((int(e["seq"]), int(e["slot"])))
    seqs = [a for a, _ in seen]
    assert seqs == sorted(set(seqs)) and len(set(seqs)) == len(seqs), \
        f"seq 不是严格递增（读端无法判断谁更新）：{seqs}"
    by_seq: dict[int, set[int]] = {}
    for a, b in seen:
        by_seq.setdefault(a, set()).add(b)
    assert all(len(v) == 1 for v in by_seq.values()), \
        f"同一个 seq 落在两个槽上：按事件取像素会取到别的帧 {by_seq}"
    # 换文档（同尺寸的另一张图）：缓冲那一块是**复用**的，引擎不再发 shm_ready（那条只在
    # 真的换档时发，见 Rust 侧 attach_shm 的注释）。这里要判的是"同一块缓冲上的 seq 仍然
    # 单调"，比"再来一条 shm_ready"更接近宿主真正会遇到的情形。
    import shutil
    other = tmp_path / "other.jpg"
    shutil.copyfile(FIXTURE, other)
    _drain(engine)
    engine.send(cmd="load_image", path=str(other), max_px=207360, strength=0.3)
    engine.wait_for("image_ready", timeout=180)
    _drain(engine)
    engine.send(cmd="set_strength", value=0.55)
    e2 = engine.wait_for("frame", timeout=30)
    assert int(e2["seq"]) > max(seqs), \
        f"换文档后 seq 回到旧值（{e2['seq']} ≤ {max(seqs)}）：读端会把新帧当旧帧丢掉"
    # 反向对照：请求顺序就是显示顺序——最后请求的那一笔必须是最后到达的那一帧
    px = _frame_of(e2, peer, h, w)
    _drain(engine)
    engine.send(cmd="set_strength", value=0.0)
    e3 = engine.wait_for("frame", timeout=30)
    px0 = _frame_of(e3, peer, h, w)
    assert int(e3["seq"]) > int(e2["seq"]), "后请求的帧 seq 反而更小：读端无从淘汰"
    assert int(np.abs(px - px0).max()) > 0, "强度从 0.55 改到 0 画面没动：那一帧不是新结果"


# ------------------------------------------------------------------ LINUX-002
def test_every_bundled_weight_has_a_filled_license_ledger_entry():
    """LINUX-002 依赖许可门槛：每项版本/哈希/许可/分发约束有记录；未知或不允许分发项被排除。

    这条是**发行物的门禁**而不是文档检查：台账说某个权重进 deb，就要能当场反查
    那个文件真的在包里、字节数与 sha256 真的对得上、许可与证据等级真的填完。
    只对不上一条就红——"sha256=null 而档写 bundled"正是这套政策自己定的红线
    （`policy.gate`），而反向也要判：包里不许出现台账不认的权重（那叫无标签字节）。
    """
    led = json.loads((REPO / "docs" / "model-licenses" / "models.json").read_text(encoding="utf-8"))
    data = REPO / "engine" / "src" / "lumaretouch_engine" / "data"
    artifacts = {f.name for f in data.iterdir() if f.is_file()}
    gate = led["policy"]["gate"]
    assert "bundled" in gate, "政策里那条硬门禁本身要能被读到"
    listed: set[str] = set()
    problems = []
    for m in led["models"]:
        art = m.get("artifact")
        tier = m.get("tier")
        if art:
            listed.add(art)
        if tier != "bundled":
            continue
        f = data / art
        if not f.is_file():
            problems.append(f"{m['id']}: 标了 bundled 而包里没有 {art}")
            continue
        digest = hashlib.sha256(f.read_bytes()).hexdigest()
        # 台账里哈希有两个键名（早期条目写 sha256，权重束写 artifact_sha256）：
        # 这里两边都认，但**只有一个非空时才拿它当判据**，两边都有而互相不同时也要响
        declared = [v for v in (m.get("sha256"), m.get("artifact_sha256")) if v]
        if not declared:
            problems.append(f"{m['id']}: bundled 却没记 sha256（policy.gate 的第一条）")
        elif digest not in declared:
            problems.append(f"{m['id']}: 台账 sha256 与实际文件不符"
                            f"（台账 {str(declared[0])[:12]}… vs 实测 {digest[:12]}…）")
        if m.get("size_bytes") != f.stat().st_size:
            problems.append(f"{m['id']}: 台账体积 {m.get('size_bytes')} ≠ 实际 {f.stat().st_size}")
        lic = m.get("weights_license") or m.get("license")
        if not lic or str(lic).lower() in ("unknown", "none") or "未" in str(lic):
            problems.append(f"{m['id']}: bundled 却没填权重许可名（读到 {lic!r}）")
        if m.get("evidence") != "一手":
            problems.append(f"{m['id']}: 证据等级是 {m.get('evidence')!r}，按 policy.gate 不得 bundled")
    unlabeled = sorted(a for a in artifacts if a.endswith((".task", ".tflite", ".onnx"))
                       and a not in listed)
    if unlabeled:
        problems.append(f"包里有台账不认的权重（无标签字节）：{unlabeled}")
    assert not problems, "\n".join(["依赖许可台账不过：", *problems])


# ------------------------------------------------------------------ SCOPE-001
DUAL = str(REPO / "engine" / "tests" / "fixtures" / "portrait-dual-1570x950.jpg")
DUAL_NOTE = str(REPO / "engine" / "tests" / "fixtures" / "portrait-dual.sha256.txt")


def _dual_or_explain() -> str:
    """多人图必须存在且指纹对得上台账。这里**不用 skip**：缺输入就是验收缺证据，
    skip 会把它写成"本轮没跑到"而不是"跑不了"，而 P0 不允许前者蒙混过关。"""
    if not os.path.isfile(DUAL):
        pytest.fail("缺多人测试图 portrait-dual-1570x950.jpg：先跑 "
                    "packaging/make-test-dual-portrait.py（SCOPE-001 没有输入就没有判据）")
    want = Path(DUAL_NOTE).read_text(encoding="utf-8").splitlines()[1].split()[0]
    got = hashlib.sha256(open(DUAL, "rb").read()).hexdigest()
    assert got == want, f"多人测试图与指纹台账不符（台账 {want[:12]}… vs 实测 {got[:12]}…）"
    return DUAL


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像")
def test_multi_face_photo_blocks_reshaping_but_keeps_global_edits(engine):
    """SCOPE-001（多人超范围保护）：两张脸的照片里**不许静默选一张**。

    判据分三段，缺一都不是这条用例：
    ① 真检测器（mediapipe，不是测试里塞的假后端）在同一帧上报 num_faces=2，且
       `precompute_ready` 自己带着 scope_block/max_faces_probed——超范围这件事要写在
       事件自己身上，不能只存在于"UI 记得要禁用"；
    ② `deform` 被明拒且**不留半截状态**（amounts 全零、built 仍 False：静默建了单
       而滑块全零，是最难复查的那种"看起来没事"）；
    ③ 全图那几条入口在同一份文档上仍然可用（曝光/白平衡、裁剪）——作用面不是
       "某个人"的操作不该被一起禁掉。禁错范围与不禁一样是产品缺陷。

    不许"退成选最大的那张脸"：冻结件（ADR-0003 / D-P0-02）点名 target_scope=
    single_face 的操作在多人图上要阻止并说明范围，因为画面被推的那一张用户无从看出。
    """
    import importlib.util

    _needs_torch()
    if importlib.util.find_spec("mediapipe") is None:
        pytest.fail("运行时没装 mediapipe 插件：面部重塑的核心就是它，这条用例不许"
                    "退成 skip（skip 不是通过），装它见 engine/requirements-mediapipe.txt")
    path = _dual_or_explain()
    # 不传 max_px：走引擎产品档（decode.PROXY_PIXELS = 4K 预算）。这组夹具 1570×950
    # 本来就在预算内，解出来就是原幅；换成测试夹具的小档会改变检测条件，判据就不是那条了
    meta = _open(engine, path=path)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])

    engine.send(cmd="precompute", backend="mediapipe")
    pc = engine.wait_for("precompute_ready", timeout=180)
    assert pc.get("backend") == "mediapipe", f"报的不是真后端：{pc.get('backend')}"
    assert int(pc.get("num_faces", 0)) == 2, \
        f"多人输入没被真检测器报成 2 张脸（得到 {pc.get('num_faces')}）：这张用例失去意义"
    assert pc.get("scope_block") == "multi_face", pc
    assert int(pc.get("max_faces_probed")) >= 2, pc
    assert any("张脸" in n for n in pc.get("notes") or []), \
        f"超范围没写进 notes：{pc.get('notes')}"

    before = _live_state(engine)
    engine.send(cmd="deform", action="set", amounts={"slim_face": 0.6})
    ev = _expect_error(engine, "SCOPE-001", timeout=30)
    assert "张脸" in ev["error"], ev
    after = _live_state(engine)
    assert _recipe(after) == _recipe(before), \
        "deform 被拒却改了配方（半截状态）：拒之前 + " + json.dumps(
            _recipe(before).get("deform"), ensure_ascii=False) + " 拒之后 " + json.dumps(
            _recipe(after).get("deform"), ensure_ascii=False)
    d = after["deform"]
    assert d["built"] is False and all(abs(float(v)) == 0.0 for v in d["amounts"].values()), d

    # 全图那几条入口不该被连带禁掉（同一份多人文档上仍然可用）
    hot = _cmd_frame(engine, peer, h, w, cmd="exposure", ev=1.0)
    base = _cmd_frame(engine, peer, h, w, cmd="exposure", action="clear")
    assert int(np.abs(hot - base).max()) > 0, "多人图上全图曝光成了假滑块：禁错范围了"
    st = _live_state(engine)
    assert st["exposure"]["ev"] == pytest.approx(0.0), st["exposure"]
    cropped = _cmd_frame(engine, peer, h, w, cmd="crop", rect=[0.1, 0.1, 0.9, 0.9],
                         rotation_degrees=0.0)
    assert int(np.abs(cropped - base).max()) > 0, "多人图上全图裁剪成了假控件"
    engine.send(cmd="crop", action="clear")
    _wait_frame_mode(engine, "crop")
    assert _live_state(engine)["deform"]["built"] is False, "全图操作把形变层顺手建起来了"
