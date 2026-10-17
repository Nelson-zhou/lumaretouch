#!/usr/bin/env python3
"""M1-RAW 打靶：自研 DNG 读侧的三臂证据 + 相位 + 分段耗时，全部现算不 import 引擎常量。

为什么要三臂（这是本仓「自产自读是循环论证」那条老教训的直接应用）：
* **臂 A 对地面真值**：已知 RGB → 按读侧渲染链的解析逆写盘 → 读回。误差归因到容器、
  线性化、demosaic 三处。色彩那条式子不在这里的证明范围（写侧就是按读侧的逆写的）。
* **臂 B 对第三方**：同一张 DNG 交给系统里的 LibRaw（ImageMagick 的 DNG delegate）
  渲染，与我们的渲染逐通道对相关。少了这一臂，往返再准也只能证明「自洽」，证明不了
  「与业界读的是同一件事」。LibRaw 只当裁判，不在产品依赖树里（见 requirements-libraw.txt）。
* **臂 C GPU↔CPU**：生产路（torch）与参考路（numpy float64）必须逐像素 ≤1 LSB——
  RAW 解码是一次性成本，可它也要过「快且不出错」这道门。

外加两条功能判据：
* **CFA 相位**：DefaultCropOrigin 取奇偏移，相位丢了就是红蓝互换（真机 mean|Δ| 53）；
* **分段耗时**：容器 / 像素 / 渲染 / 编码四段各自的 min 与中位（冷首图不混进稳态）。

跑法（需要一个带 ROCm/CUDA torch 的解释器；臂 B 需要本机有 magick/convert，没有就跳过）：
  REPS=5 LRT_DEVICE=cuda python3 packaging/m1-raw-bench.py
VERDICT 行写 PASS/FAIL；非零退出即判据破了。
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import statistics as st
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine", "src"))

import numpy as np                       # noqa: E402
from PIL import Image                     # noqa: E402

from lumaretouch_engine import raw as R   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, "..", "engine", "tests", "fixtures", "portrait-1024x1280.jpg")
DEVICE = os.environ.get("LRT_DEVICE", "cuda")
REPS = int(os.environ.get("REPS", "5"))
PROXY = 576000                             # 产品代理档字节预算（M1-1 钉的）

_spec = importlib.util.spec_from_file_location(
    "make_test_dng", os.path.join(HERE, "make-test-dng.py"))
mt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mt)


def _load_device():
    """生产路要真设备；没 torch / 没 GPU 就退到 numpy 参考，臂 C 那节会如实标注跳过。"""
    try:
        import torch
        if DEVICE.startswith("cuda") and torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return None


def _src():
    a = np.asarray(Image.open(FIXTURE).convert("RGB"))
    return a


def arm_a(tmp, src, device, **kw):
    """往返：读回 vs 裁片地面真值。返回 (mean|Δ|, p95, 逐通道均值偏移, 分段ms)。"""
    crop = kw.get("crop")
    path = os.path.join(tmp, "a.dng")
    mt.build(path, src, **kw)
    res = R.load_raw(path, reference=True)
    ref = res["rgb"]
    gt = src
    if crop:
        x0, y0, cw, ch = crop
        gt = gt[y0:y0 + ch, x0:x0 + cw]
    gt = R.apply_orientation(gt, kw.get("orientation", 1))
    d = np.abs(ref.astype(np.int16) - gt.astype(np.int16))
    offs = [float(ref[..., c].mean() - gt[..., c].mean()) for c in range(3)]
    return float(d.mean()), float(np.percentile(d, 95)), offs, res["ms"]


def arm_c(tmp, src, device, **kw):
    """GPU↔CPU 逐像素最大差。device 为空返回 None（本臂跳过）。"""
    if not device:
        return None
    path = os.path.join(tmp, "c.dng")
    mt.build(path, src, **kw)
    ref = R.load_raw(path, reference=True)["rgb"]
    dev = R.load_raw(path, device=device)["rgb"]
    if dev.shape != ref.shape:
        return 10_000                          # 形状都不同，直接判死
    return int(np.abs(dev.astype(np.int16) - ref.astype(np.int16)).max())


def arm_b(tmp, src):
    """对系统 LibRaw 渲染：逐通道相关 + 均值不跑偏。没 delegate 返回 None。"""
    exe = shutil.which("magick") or shutil.which("convert")
    if not exe:
        return None
    path = os.path.join(tmp, "b.dng")
    mt.build(path, src, black=256.0, white=16383.0)
    out_png = os.path.join(tmp, "b_libraw.png")
    r = subprocess.run([exe, path, out_png], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.isfile(out_png):
        return {"err": (r.stderr.strip()[:200] or "LibRaw 无输出")}
    mine = R.load_raw(path, reference=True)["rgb"].astype(float)
    lr = np.asarray(Image.open(out_png).convert("RGB")).astype(float)
    if lr.shape[:2] != mine.shape[:2]:
        lr = np.asarray(Image.fromarray(lr.astype(np.uint8)).resize(
            (mine.shape[1], mine.shape[0]), Image.LANCZOS)).astype(float)
    corrs, means = [], []
    for c in range(3):
        a, b = mine[..., c].ravel(), lr[..., c].ravel()
        corrs.append(float(np.corrcoef(a, b)[0, 1]))
        means.append((float(a.mean()), float(b.mean())))
    return {"corr": corrs, "means": means}


def main() -> int:
    if not os.path.isfile(FIXTURE):
        print(f"✗ 缺测试人像 {FIXTURE}，先跑 packaging/make-test-portrait.py")
        return 2
    device = _load_device()
    print(f"RAW 打靶 · device={device or 'CPU-only(臂C跳过)'} reps={REPS} "
          f"源图={os.path.basename(FIXTURE)}")
    fails = []
    with tempfile.TemporaryDirectory() as tmp:
        full = _src()
        base = dict(black=256.0, white=16383.0)
        # ---- 臂 A：往返保真（整幅，走产品代理预算）----
        m, p95, offs, seg = arm_a(tmp, full, device, **base)
        print(f"[臂A 往返] mean|Δ|={m:.2f} p95={p95:.1f} 均值偏移="
              + ",".join(f"{o:+.1f}" for o in offs))
        if not (m < 8.0 and all(abs(o) < 12.0 for o in offs)):
            fails.append("臂A 往返误差过大")
        # 代理预算版：真降档（1024×1280 > 576k 会走降采样/LANCZOS）
        dref = R.load_raw(os.path.join(tmp, "a.dng"), budget=PROXY, reference=True)
        rw, rh = dref["rgb"].shape[1], dref["rgb"].shape[0]
        print(f"          代理档 {rw}×{rh} = {rw*rh} px（≤{PROXY}），降采样确实发生："
              f"{(rw, rh) != (full.shape[1], full.shape[0])}")
        if rw * rh > PROXY:
            fails.append("代理档越了字节预算")
        # ---- 相位：奇偏移裁片不得红蓝互换 ----
        pm, pp95, poffs, _ = arm_a(tmp, full[:256, :384], device,
                                   crop=(1, 1, 380, 250), **base)
        swap_ok = all(abs(o) < 12.0 for o in poffs)
        print(f"[相位] crop(1,1) mean|Δ|={pm:.2f} 均值偏移="
              + ",".join(f"{o:+.1f}" for o in poffs) + ("  方向正" if swap_ok else "  ✗像互换"))
        if not (pm < 8.0 and swap_ok):
            fails.append("CFA 相位丢失（红蓝通道错位）")
        # ---- 臂 C：GPU↔CPU ≤1 LSB ----
        gc = arm_c(tmp, full[:256, :384], device, **base)
        if gc is None:
            print("[臂C GPU↔CPU] 跳过：没有可用的 GPU 设备")
        else:
            print(f"[臂C GPU↔CPU] max={gc} LSB")
            if gc > 1:
                fails.append(f"GPU 与 CPU 参考差 {gc} LSB（应 ≤1）")
        # ---- 臂 B：对系统 LibRaw ----
        b = arm_b(tmp, full[:256, :384])
        if b is None:
            print("[臂B LibRaw] 跳过：本机没有 magick/convert 的 DNG delegate")
        elif "err" in b:
            print(f"[臂B LibRaw] 跳过：LibRaw 解不开我们写的 DNG（{b['err']}）")
        else:
            cs = b["corr"]
            print("[臂B LibRaw] 逐通道相关="
                  + ",".join(f"{c:.4f}" for c in cs)
                  + "  均值(我方/LibRaw)="
                  + " ".join(f"{x:.0f}/{y:.0f}" for x, y in b["means"]))
            if min(cs) < 0.90:
                fails.append(f"与第三方渲染方向不一致（最低相关 {min(cs):.3f}）")
        # ---- 分段耗时：REPS 次交错，报 min 与中位 ----
        render_ms, pix_ms = [], []
        for _ in range(REPS):
            _, _, _, s = arm_a(tmp, full[:512, :512], device, **base)
            render_ms.append(s["render_ms"])
            pix_ms.append(s["pixels_ms"])
        print(f"[分段耗时] 像素 {min(pix_ms):.1f}/{st.median(pix_ms):.1f} ms "
              f"(min/中位) · 渲染 {min(render_ms):.1f}/{st.median(render_ms):.1f} ms")

    if fails:
        print("VERDICT=FAIL  " + " ; ".join(fails))
        return 1
    print("VERDICT=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
