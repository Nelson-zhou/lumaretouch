"""PORTRAIT-002 的自动化那半（纹理保留 / 肤色漂移 / 边界污染）+ ΔE00 实现校验。

用例原文（冻结件）："不同肤色和光照的固定授权样本 → 应用基础肤质修饰 → 不出现蜡像感、
明显肤色漂移或边界污染；按冻结盲评规则通过"，`test_method = human_and_image_regression`。

这条文件只做 **image_regression** 那一半，而且把另一半写明：
人眼盲评（"看起来自不自然"）不是机器能签字的，本仓不拿指标冒充它。
`docs/acceptance/case-map.json` 里 PORTRAIT-002 标了 `manual: true`，验收报告把它显示成
"待人工"，而不是跟着这里绿。

三个判据的数值不是拍的：ADR-0008 记着本轮实测表（同一份代码、同一台机器量出来的），
阈值定在实测与"坏味道"之间。ΔE00 的**测量本身**先要被验：`color_metric.delta_e00`
逐条对 Sharma 等人的官方校验数据（34 行全对），否则上面那些数字都是自报。

样本从哪来：确定性算法臂用本仓自有程序化正脸夹具（`packaging/make-test-portrait.py`，许可干净、无真人），
"不同肤色与光照"由引擎自己的白平衡/曝光命令造出来（±800 K、色调 +0.6、±1.0 EV）——
用产品命令造样本，不引入第二份色彩路径。真实模型臂另用有来源记录的NASA公共领域照片；色温变化不冒充不同真实肤色人群。
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import numpy as np
import pytest

from lumaretouch_engine import color_metric as CM
from lumaretouch_engine.shm import FrameShm

from test_protocol import FIXTURE, _needs_torch, _read_frame, _wait_frame_mode
from test_acceptance_p0 import REPO, _cmd_frame, _drain, _open, engine   # noqa: F401
# （`engine` 必须被导入进本模块才能当 fixture 用：不导入会得到 fixture not found。）

TESTDATA = REPO / "engine" / "tests" / "data" / "ciede2000testdata.txt"
TESTDATA_SHA256 = "44aebb39107128328add54fbef5ac8ee89909e50508f448a1580adea2058a4b8"

# 阈值出处见 ADR-0008（本轮实测：高频比 0.994–1.004；ΔE00 mean 0.674–0.923、p95 1.82–2.40；
# 掩膜那一条角背景逐字节 0 LSB）。
TEXTURE_RATIO_MIN = 0.50
TEXTURE_RATIO_MAX = 1.15
DRIFT_DE00_MEAN_MAX = 1.00
DRIFT_DE00_P95_MAX = 3.00
MASKED_OUTSIDE_MAX_LSB = 0

# (名字, temperature_shift, tint_shift, ev)：不同肤色/光照的近似组
SAMPLES = [("中性", 0.0, 0.0, 0.0),
           ("偏冷", -800.0, 0.0, 0.0),
           ("偏暖", 800.0, 0.0, 0.0),
           ("绿向", 0.0, 0.6, 0.0),
           ("暗光", 0.0, 0.0, -1.0),
           ("亮光", 0.0, 0.0, 1.0)]
STRENGTH = 0.6
REAL_PHOTO = REPO / "engine/tests/fixtures/nasa-astronaut-face-crop.png"


def _face_box(h: int, w: int) -> np.ndarray:
    """面部区：中心 40% 宽 × 20%–65% 高（程序化正脸的落点，见 make-test-portrait.py）。"""
    m = np.zeros((h, w), dtype=bool)
    m[int(h * 0.20):int(h * 0.65), int(w * 0.30):int(w * 0.70)] = True
    return m


def _corner_background(h: int, w: int) -> np.ndarray:
    """两块角上的背景带：离主体远，判"边界污染"用最外层、最不该被动到的像素。"""
    m = np.zeros((h, w), dtype=bool)
    ch, cw = max(2, h // 12), max(2, w // 6)
    m[:ch, :cw] = True
    m[:ch, -cw:] = True
    return m


def test_delta_e00_matches_the_published_reference_vectors():
    """ΔE00 的实现必须逐条过官方校验数据（Sharma 等人 34 行，kL=kC=kH=1）。

    先验测量工具，再用它验产品：这条不过，下面那些 ΔE00 判据全是自报。
    """
    assert TESTDATA.is_file(), f"缺官方校验数据 {TESTDATA}（来源见同目录 README）"
    digest = hashlib.sha256(TESTDATA.read_bytes()).hexdigest()
    assert digest == TESTDATA_SHA256, f"校验数据文件被改过：{digest[:12]}… ≠ 记录的那一份"
    bad = []
    rows = 0
    for line in TESTDATA.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 7:
            continue
        rows += 1
        lab1 = np.array([float(x) for x in parts[0:3]])
        lab2 = np.array([float(x) for x in parts[3:6]])
        want = float(parts[6])
        got = float(CM.delta_e00(lab1, lab2))
        if abs(got - want) > 5e-4:
            bad.append(f"{parts[0:6]} 期望 {want} 实得 {got:.5f}")
    assert rows == 34, f"官方表应有 34 行，读到 {rows} 行：数据文件或解析漂了"
    assert not bad, "CIEDE2000 实现与公开校验数据不一致：\n" + "\n".join(bad[:8])


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像")
@pytest.mark.parametrize("backend,path", [("synthetic", FIXTURE), ("mediapipe", str(REAL_PHOTO))])
def test_skin_retouch_keeps_texture_and_does_not_drift_color_or_bleed(engine, backend, path):
    """PORTRAIT-002（自动化那半）：基础肤质修饰不产生蜡像感、不明显肤色漂移、不越界污染。

    每组样本各判三件事（strength=0 与 0.6 两帧对比，全部走真命令通路）：
    ① 高频能量保留比落在 [0.50, 1.15]：低于下限就是"橡皮"（局部对比被抹平），
       高于上限说明这一层在加锐/加噪而不是磨皮；
    ② 面部区 ΔE00：mean ≤ 1.00、p95 ≤ 3.00（均值会摊薄，p95 才看得见少数像素）；
    ③ 掩膜作用域外（角上的背景带）**逐字节不动**（≤ 0 LSB）：这就是"边界污染"。
       这条必须用 `channel="skin"` 那一次来判——全局磨皮本来就该动背景，
       拿全局那一帧判越界会把正确实现判成错。
    """
    _needs_torch()
    meta = _open(engine, path=path, max_px=207360)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    box = _face_box(h, w)
    corners = _corner_background(h, w)
    measured = []

    def shot(value: float, channel) -> np.ndarray:
        # 按 seq 认帧（_cmd_frame）而不是 drain + 取下一帧：drain 赌的是"事件间隔
        # 不超过 0.1 s"，全量跑时 GPU 争用能把两条命令的帧隔开几百毫秒，于是拿回来
        # 的是上一条命令那一帧——本轮 P0 中性那条判据就是这么假红的。
        return _cmd_frame(engine, peer, h, w, cmd="set_strength",
                          value=value, channel=channel)

    for name, temp, tint, ev in SAMPLES:
        _drain(engine)
        engine.send(cmd="exposure", ev=ev, temperature_shift=temp, tint_shift=tint)
        _wait_frame_mode(engine, "exposure")
        base = shot(0.0, None)
        on = shot(STRENGTH, None)
        ratio = float(CM.high_pass_energy(on)[box].mean()
                      / max(float(CM.high_pass_energy(base)[box].mean()), 1e-9))
        drift = CM.de00_stats(base, on, mask=box)
        assert TEXTURE_RATIO_MIN <= ratio <= TEXTURE_RATIO_MAX, \
            f"{name}：高频保留比 {ratio:.3f} 出了 [{TEXTURE_RATIO_MIN}, {TEXTURE_RATIO_MAX}]" \
            f"（低=蜡像/橡皮，高=在加噪）"
        assert drift["mean"] <= DRIFT_DE00_MEAN_MAX, \
            f"{name}：磨皮让肤色漂移 mean ΔE00={drift['mean']} > {DRIFT_DE00_MEAN_MAX}"
        assert drift["p95"] <= DRIFT_DE00_P95_MAX, \
            f"{name}：少数像素色偏明显 p95 ΔE00={drift['p95']} > {DRIFT_DE00_P95_MAX}"
        measured.append((name, round(ratio, 3), drift["mean"], drift["p95"], drift["max"]))
        assert (base != on).any(), f"{name}：strength={STRENGTH} 画面一动不动：假磨皮"

    # ③ 边界污染：只有掩膜那一次能判
    engine.send(cmd="precompute", backend=backend)
    pc = engine.wait_for("precompute_ready", timeout=180)
    assert pc.get("backend") == backend, pc
    _drain(engine)
    engine.send(cmd="exposure", action="clear")
    _wait_frame_mode(engine, "exposure")
    base = shot(0.0, None)
    masked = shot(STRENGTH, "skin")
    outside = int(np.abs(masked - base)[corners].max())
    assert outside <= MASKED_OUTSIDE_MAX_LSB, \
        f"掩膜外的背景带了 {outside} LSB 的变化（边界污染）：磨皮越过了作用域"
    inside = int(np.abs(masked - base).max())
    assert inside > 0, "掩膜内也没动：这一层根本没生效，'没污染'是因为'没干活'"
    print("\nPORTRAIT-002 自动化读数（名字, 高频比, ΔE00 mean, p95, max）：", measured)


def test_real_photo_fixture_matches_documented_bytes():
    import json
    manifest = json.loads((REAL_PHOTO.parent / "nasa-astronaut-provenance.json").read_text())
    assert hashlib.sha256(REAL_PHOTO.read_bytes()).hexdigest() == manifest["sha256"]
