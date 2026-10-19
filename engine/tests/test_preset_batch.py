"""预设与批量同步的端到端验收（PRESET-001、PRESET-002、BATCH-004）。

为什么必须端到端而不是单测 `scope.py`：这三条用例判的都是"**盖下去了没有、盖错了没有**"。
纯函数测得再干净，也证不了 `cmd_preset` 真的走 `_replay_state` 把参数装进了会话、
真的出了一帧、真的能在一次 Ctrl+Z 里退回去；也证不了批量写进底片条那一格的快照在
**切回那张图时**还在。本仓的老规矩：不跑的代码等于没写，不切回来看一眼的写入等于没写。

预设目录固定到一个 /tmp 下的独立目录（模块级设置，见下面的注释）：引擎是**子进程**，
测试里再 monkeypatch 环境已经晚了 —— 进程早就起来了。所以必须在任何 engine fixture
实例化之前就把 `LRT_PRESET_DIR` 放进 os.environ。
"""
from __future__ import annotations

import os
import shutil
import json
from pathlib import Path

import pytest

from lumaretouch_engine import scope as SC
from lumaretouch_engine.shm import FrameShm

from test_protocol import (FIXTURE, _expect_error, _needs_torch, _sha_of, _wait_frame_mode)
# `engine` 这一行不是多余导入：fixture 靠“被导入进本模块”才能被 pytest 认到
#（test_acceptance_p0 也是这么接的）。少了它会得到四条 `fixture 'engine' not found`。
from test_acceptance_p0 import _cmd_frame, _drain, _live_state, _open, engine   # noqa: F401

PRESET_TMP = Path(os.environ.get("TMPDIR", "/tmp")) / f"lrt-preset-tests-{os.getpid()}"
shutil.rmtree(PRESET_TMP, ignore_errors=True)
PRESET_TMP.mkdir(parents=True, exist_ok=True)
os.environ["LRT_PRESET_DIR"] = str(PRESET_TMP)

EXPO_OPS = [SC.OP_EXPOSURE, SC.OP_WHITE_BALANCE]


def _events_until(engine, want: str, timeout: float = 120.0) -> dict:
    return engine.wait_for(want, timeout=timeout)


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像")
def test_module_presets_only_touch_their_own_scope_and_same_module_overrides(engine):
    """PRESET-001：先套人像预设、再套色彩预设 → 各自只改范围内那一组，同模块后应用覆盖。

    四件事一起判：
    ① 人像预设只动磨皮强度，色彩/裁剪一个键都不变（越界作用 = 用户以为只调了肤，
       结果整张色偏了）；
    ② 色彩预设同理不动人像；
    ③ **同模块后应用覆盖**：手工把 EV 推到 2.0 后再套一次色彩预设，EV 必须等于预设里
       那一个值，既不是叠加（2.3）也不是保留旧值（2.0）；
    ④ 一次预设 = 一步撤销（走 EDIT_CMDS 与 `_replay_state`，不是逐条命令各入一步）。
    """
    _needs_torch()
    meta = _open(engine, max_px=207360)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    engine.send(cmd="precompute", backend="mediapipe")
    pc = engine.wait_for("precompute_ready", timeout=180)
    assert int(pc.get("num_faces")) == 1, pc

    # 一份"已有色彩 + 已有编辑"的文档（用例的 given）
    engine.send(cmd="exposure", ev=1.0, temperature_shift=400.0, tint_shift=0.1)
    _wait_frame_mode(engine, "exposure")
    engine.send(cmd="crop", rect=[0.1, 0.1, 0.9, 0.9], rotation_degrees=5.0)
    _wait_frame_mode(engine, "crop")
    engine.send(cmd="set_strength", value=0.8)
    _wait_frame_mode(engine, "drag")

    engine.send(cmd="preset", action="list")
    pl = _events_until(engine, "preset_list")
    ids = {p["id"] for p in pl["list"]}
    assert {"portrait-soft", "color-warm"} <= ids, f"随包的模块预设没报出来：{ids}"
    assert pl["list"][0]["builtin"] is True, "内置标记没随事件出来：UI 分不出能不能删"

    # ① 先套人像预设
    engine.send(cmd="preset", action="apply", id="portrait-soft")
    ev1 = _events_until(engine, "preset_applied")
    _drain(engine)
    assert ev1["modules"] == [SC.OP_SKIN, SC.OP_BLEMISH] or set(ev1["modules"]) == {
        SC.OP_SKIN, SC.OP_BLEMISH}, ev1["modules"]
    st = _live_state(engine)
    assert st["strength"] == pytest.approx(0.45), f"人像预设没把人像参数盖下去：{st['strength']}"
    assert st["exposure"]["ev"] == pytest.approx(1.0), f"人像预设越界改了曝光：{st['exposure']}"
    assert st["exposure"]["temperature_shift"] == pytest.approx(400.0), st["exposure"]
    assert [round(v, 4) for v in st["crop"]["rect"]] == [0.1, 0.1, 0.9, 0.9], st["crop"]
    assert st["crop"]["rotation_degrees"] == pytest.approx(5.0), st["crop"]

    # ② 再套色彩预设
    engine.send(cmd="preset", action="apply", id="color-warm")
    ev2 = _events_until(engine, "preset_applied")
    _drain(engine)
    assert ev2["before"][SC.OP_EXPOSURE] == {"ev": pytest.approx(1.0)}, ev2["before"]
    st2 = _live_state(engine)
    assert st2["exposure"]["ev"] == pytest.approx(0.30), st2["exposure"]
    assert st2["exposure"]["temperature_shift"] == pytest.approx(250.0), st2["exposure"]
    assert st2["exposure"]["tint_shift"] == pytest.approx(0.05), st2["exposure"]
    assert st2["strength"] == pytest.approx(0.45), f"色彩预设动了人像：{st2['strength']}"
    assert [round(v, 4) for v in st2["crop"]["rect"]] == [0.1, 0.1, 0.9, 0.9], st2["crop"]

    # ③ 同模块后应用覆盖：手工推到 2.0，再套同一条色彩预设 → 必须是预设值，不是叠加
    engine.send(cmd="exposure", ev=2.0)
    _wait_frame_mode(engine, "exposure")
    engine.send(cmd="preset", action="apply", id="color-warm")
    _events_until(engine, "preset_applied")
    _drain(engine)
    st3 = _live_state(engine)["exposure"]
    assert st3["ev"] == pytest.approx(0.30), f"后应用的同模块没有覆盖而是留旧值/叠加：{st3}"

    # ④ 一次撤销退掉整条预设
    engine.send(cmd="history", action="undo")
    hs = engine.wait_for("history_state", timeout=60)
    _drain(engine)
    assert hs["action"] == "undo"
    st4 = _live_state(engine)
    assert st4["exposure"]["ev"] == pytest.approx(2.0), \
        f"一次撤销没退掉整条预设（现在 EV={st4['exposure']['ev']}）：预设被拆成了多步"

    # 画面必须真的动了（假预设在判据上与 P0-*-NEUTRAL 同一族）
    a = _cmd_frame(engine, peer, h, w, cmd="set_strength", value=0.8)
    b = _cmd_frame(engine, peer, h, w, cmd="set_strength", value=0.0)
    assert (a != b).any(), "强度动了而画面一模一样：那是假滑块"


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像")
def test_hostile_presets_are_refused_and_a_valid_one_still_imports(engine, tmp_path):
    """PRESET-002：路径穿越 / 过大资产 / 未知 schema / 脚本内容 → 安全拒绝。

    判的不是"报错就行"，而是三件后果：① 每一条都有明确拒绝理由；② 预设目录外面
    没有多出任何文件（路径穿越真的没落盘）；③ 引擎从没执行过文件内容（脚本里那一句
    要写的标记文件不存在）；④ 合法预设仍然导入得进来、用得上、删得掉。
    """
    _needs_torch()
    engine.send(cmd="hello")
    engine.wait_for("ready", timeout=90)
    outside = tmp_path / "pwned.txt"
    evil_outside = tmp_path.parent / "evil-slip.json"

    cases = [
        ("路径穿越 id", {"schema": SC.PRESET_SCHEMA, "id": "../../evil-slip",
                       "modules": {SC.OP_EXPOSURE: {"ev": 0.2}}}),
        ("未知 schema", {"schema": "lrt.preset.v9", "id": "ok-1",
                       "modules": {SC.OP_EXPOSURE: {"ev": 0.2}}}),
        ("未知模块", {"schema": SC.PRESET_SCHEMA, "id": "ok-1",
                    "modules": {"lnx.nope.v1": {"x": 1}}}),
        ("越界参数", {"schema": SC.PRESET_SCHEMA, "id": "ok-1",
                    "modules": {SC.OP_EXPOSURE: {"ev": 1e9}}}),
        ("非有限参数", {"schema": SC.PRESET_SCHEMA, "id": "ok-1",
                    "modules": {SC.OP_WHITE_BALANCE: {"tint_shift": float("inf")}}}),
        ("空模块", {"schema": SC.PRESET_SCHEMA, "id": "ok-1", "modules": {}}),
        ("自报内置", {"schema": SC.PRESET_SCHEMA, "id": "ok-1", "builtin": True,
                    "modules": {SC.OP_EXPOSURE: {"ev": 0.2}}}),
        ("未建模参数", {"schema": SC.PRESET_SCHEMA, "id": "ok-1",
                     "modules": {SC.OP_BLEMISH: {"protect_identity_marks": True}}}),
        ("顶层多余键", {"schema": SC.PRESET_SCHEMA, "id": "ok-1", "modules": {SC.OP_EXPOSURE: {"ev": 0.2}},
                    "extra_hook": 1}),
    ]
    for label, doc in cases:
        f = tmp_path / f"hostile-{abs(hash(label)) % 10**6}.json"
        f.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        engine.send(cmd="preset", action="import", path=str(f))
        ev = _expect_error(engine, "被拒", timeout=30)
        assert "preset import" in ev["error"], (label, ev)
    assert not evil_outside.exists(), "路径穿越的预设落到了目录外面"

    # 过大资产：不解析内容就该拒（读进来再说等于把内存交给一个文件名）
    huge = tmp_path / "huge.json"
    huge.write_text(json.dumps({"schema": SC.PRESET_SCHEMA, "id": "ok-1",
                               "modules": {SC.OP_EXPOSURE: {"ev": 0.2}},
                               "note": "x" * (SC.PRESET_MAX_BYTES + 10)}), encoding="utf-8")
    engine.send(cmd="preset", action="import", path=str(huge))
    assert "过大" in _expect_error(engine, "过大", timeout=30)["error"]

    # 脚本内容：写一句"能跑就跑"的 shell，跑完看那个标记文件在不在
    script = tmp_path / "evil.sh"
    marker = tmp_path / "RAN-FROM-PRESET"
    script.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    engine.send(cmd="preset", action="import", path=str(script))
    _expect_error(engine, "被拒", timeout=30)
    assert not marker.exists(), "预设文件被执行了：这是最不该发生的事"
    non_json = tmp_path / "broken.json"
    non_json.write_text("{ 这不是 JSON", encoding="utf-8")
    engine.send(cmd="preset", action="import", path=str(non_json))
    _expect_error(engine, "被拒", timeout=30)

    engine.send(cmd="preset", action="list")
    before = {p["id"] for p in _events_until(engine, "preset_list")["list"]}
    assert not (before - {"portrait-soft", "color-warm"}), f"恶意预设挤进了列表：{before}"

    # 合法预设：导入 → 用得上 → 删得掉
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"schema": SC.PRESET_SCHEMA, "id": "test-cool",
                               "name": "冷调（测试）", "kind": "color",
                               "modules": {SC.OP_EXPOSURE: {"ev": -0.4},
                                           SC.OP_WHITE_BALANCE: {"temperature_shift": -300.0}}},
                              ensure_ascii=False), encoding="utf-8")
    engine.send(cmd="preset", action="import", path=str(good))
    imp = _events_until(engine, "preset_imported")
    assert Path(imp["path"]).parent == PRESET_TMP, f"预设落到了用户目录外面：{imp['path']}"
    assert Path(imp["path"]).read_text(encoding="utf-8")     # 真在盘上，不是自报

    _open(engine, max_px=207360)
    engine.send(cmd="preset", action="apply", id="test-cool")
    _events_until(engine, "preset_applied")
    _drain(engine)
    st = _live_state(engine)["exposure"]
    assert st["ev"] == pytest.approx(-0.4) and st["temperature_shift"] == pytest.approx(-300.0), st

    engine.send(cmd="preset", action="delete", id="test-cool")
    _events_until(engine, "preset_deleted")
    assert not Path(imp["path"]).exists(), "事件说删了而文件还在（信自报不信盘的下场）"
    engine.send(cmd="preset", action="delete", id="portrait-soft")
    _expect_error(engine, "内置", timeout=30)
    engine.send(cmd="preset", action="import", path=str(tmp_path / "does-not-exist.json"))
    _expect_error(engine, "被拒", timeout=30)


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像")
def test_batch_sync_undo_restores_untouched_and_reports_conflict(engine, tmp_path):
    """BATCH-004：同步后部分目标又被修改 → 撤销时未动的还原、动过的报冲突不抹。

    原子性与"不抹后续修改"是同一件事的两面：撤销一批同步不该把用户在这批之后做的
    工作一起撤掉。判据只看一个事实：**这一格上那几个模块现在的参数，还是不是我当初
    写进去的那一组**。
    """
    _needs_torch()
    paths = []
    for i in range(3):
        p = tmp_path / f"shot-{i}.jpg"
        shutil.copyfile(FIXTURE, p)
        paths.append(str(p))
    sha = {p: _sha_of(p) for p in paths}

    engine.send(cmd="hello")
    engine.wait_for("ready", timeout=90)
    engine.send(cmd="set_device", device="cpu")
    engine.wait_for("device_set", timeout=120)
    engine.send(cmd="session", action="add", paths=paths, thumbs=False)
    engine.wait_for("session_add", timeout=120)
    _open(engine, path=paths[0])

    engine.send(cmd="exposure", ev=1.2, temperature_shift=300.0, tint_shift=0.2)
    _wait_frame_mode(engine, "exposure")
    engine.send(cmd="batch", action="preflight", docs=[1, 2], module_scope=EXPO_OPS)
    pf = _events_until(engine, "batch_preflight")
    assert pf["ok"] == 2 and pf["blocked"] == 0, pf
    assert pf["applies"][SC.OP_EXPOSURE]["ev"] == pytest.approx(1.2), pf["applies"]

    engine.send(cmd="batch", action="commit", docs=[1, 2], module_scope=EXPO_OPS)
    bc = _events_until(engine, "batch_committed")
    bid = bc["batch_id"]
    assert bc["targets"] == [1, 2] and bc["skipped"] == [], bc

    # 切回来看一眼：写进那一格的快照在切回时必须还在（不切回来看=没验）
    engine.send(cmd="session", action="select", index=1)
    engine.wait_for("image_ready", timeout=240)
    _drain(engine)
    st1 = _live_state(engine)["exposure"]
    assert st1["ev"] == pytest.approx(1.2) and st1["temperature_shift"] == pytest.approx(300.0), st1

    # 目标 1 在同步之后又被编辑；目标 2 没人碰
    engine.send(cmd="exposure", ev=2.5)
    _wait_frame_mode(engine, "exposure")

    engine.send(cmd="batch", action="undo", batch_id=bid)
    bu = _events_until(engine, "batch_undone")
    assert 2 in bu["restored"], bu
    conflict_paths = {c["path"] for c in bu["conflicts"]}
    assert conflict_paths == {paths[1]}, bu
    assert bu["conflicts"][0]["now"][SC.OP_EXPOSURE]["ev"] == pytest.approx(2.5), bu["conflicts"][0]

    # 目标 1 现在就是活动那一格：再 select 一次会走 noop 分支（不开新会话、不发
    # image_ready），拿它当“切回来看一眼”会等到超时。直接读 live 状态就是最真的读数。
    _drain(engine)
    assert _live_state(engine)["exposure"]["ev"] == pytest.approx(2.5), \
        "撤销批量把后续修改一起抹了：这正是 BATCH-004 要防的"
    engine.send(cmd="session", action="select", index=2)
    engine.wait_for("image_ready", timeout=240)
    _drain(engine)
    st2 = _live_state(engine)["exposure"]
    assert st2["ev"] == pytest.approx(0.0) and st2["tint_shift"] == pytest.approx(0.0), st2

    # 同一批不能撤两次
    engine.send(cmd="batch", action="undo", batch_id=bid)
    _expect_error(engine, "撤销过", timeout=30)

    for p in paths:
        assert _sha_of(p) == sha[p], f"批量同步改了原片：{p}"


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像")
def test_batch_scope_and_policy_guards(engine, tmp_path):
    """作用域与策略的守卫：空集中性不通过、没有 overwrite、未知模块、人脸范围未知不默认放行。"""
    _needs_torch()
    p = tmp_path / "one.jpg"
    shutil.copyfile(FIXTURE, str(p))
    other = tmp_path / "two.jpg"
    shutil.copyfile(FIXTURE, str(other))
    _open(engine, path=str(p))
    engine.send(cmd="session", action="add", paths=[str(other)], thumbs=False)
    engine.wait_for("session_add", timeout=120)

    engine.send(cmd="batch", action="preflight", docs=[1], module_scope=[])
    assert "空" in _expect_error(engine, "module_scope", timeout=30)["error"]
    engine.send(cmd="batch", action="preflight", docs=[1], module_scope=["lnx.nope.v1"])
    _expect_error(engine, "未知模块", timeout=30)
    engine.send(cmd="batch", action="preflight", docs=[1], module_scope=[SC.OP_MASK])
    assert "未接通" in _expect_error(engine, "不可作用", timeout=30)["error"]
    engine.send(cmd="batch", action="preflight", docs=[1], module_scope=EXPO_OPS,
                conflict_policy="overwrite")
    assert "overwrite" in _expect_error(engine, "conflict_policy", timeout=30)["error"]
    engine.send(cmd="batch", action="preflight", docs=[99], module_scope=EXPO_OPS)
    _expect_error(engine, "没有可用目标", timeout=30)

    # 人像作用域：目标那一格从没做过预计算 → 未知就不默认放行
    engine.send(cmd="batch", action="preflight", docs=[1], module_scope=[SC.OP_SKIN])
    pf = _events_until(engine, "batch_preflight")
    assert pf["blocked"] == 1 and pf["ok"] == 0, pf
    assert "预计算" in pf["targets"][0]["blocked"], pf["targets"][0]
    engine.send(cmd="batch", action="commit", docs=[1], module_scope=[SC.OP_SKIN],
                conflict_policy="recheck")
    err = _expect_error(engine, "整条不提交", timeout=30)
    assert "recheck" in err["error"], err
    assert _live_state(engine)["strength"] == pytest.approx(0.0), "被拒的批量留了半截状态"
