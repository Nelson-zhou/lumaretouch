#!/usr/bin/env python3
"""性能分位数收档（DoD §4「记录真实性能分位数」的那把尺）。

版本号只从 packaging/VERSION 读一处：上一轮把 "1.7.0" 写死在脚本里，定版时要顺手
改两个地方，漏一个就收出一份"版本对不上"的台账。落盘文件名跟着版本号走
（docs/acceptance/性能分位数-<版本>.json），档与档不可比这件事就写在文件名上。

RAW 那一臂的输入必须与本轮同源：先重建 DNG 夹具再收数，而且**按尺寸硬挡**——
1.7.0 第一次收数就撞上过 384×256 的小夹具，那份数与上一轮放在同一个目录里看着能比，
其实不能比。

用法（运行时 venv 才有 torch/mediapipe）：
  PYTHONPATH=engine/src ~/.local/share/LumaRetouch/engine/venv/bin/python tools/collect-perf.py
"""
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RT = os.environ.get("LRT_RT") or os.path.expanduser(
    "~/.local/share/LumaRetouch/engine/venv/bin/python")
VERSION = open(os.path.join(REPO, "packaging", "VERSION")).read().strip()
OUT = os.path.join(REPO, "docs", "acceptance", f"性能分位数-{VERSION}.json")
DNG = "/tmp/lrt-perf-dng.dng"
SRC = "/tmp/lrt-perf-src-3750.png"

env = dict(os.environ, PYTHONPATH=os.path.join(REPO, "engine", "src"),
           LRT_PERF_OUT=OUT, LRT_PERF_DNG=DNG)

# 1) DNG 夹具重新生成。源图用「已提交夹具 Lanczos 放大到 3750×4688」：上一轮 RAW 那一臂
#    是 3000×2000 源幅，同档才可比。放大不改变这一档要量的事（解码与下采样随像素标度）。
if not os.path.isfile(SRC):
    subprocess.run([RT, "-c",
                    "from PIL import Image;"
                    "im=Image.open('%s').convert('RGB');"
                    "im.resize((3750,4688), Image.LANCZOS).save('%s')"
                    % (os.path.join(REPO, "engine/tests/fixtures/portrait-1024x1280.jpg"), SRC)],
                   check=True, capture_output=True)
subprocess.run([RT, os.path.join(REPO, "packaging", "make-test-dng.py"),
                "--from", SRC, "--out", DNG, "--edge", "3000"],
               check=True, capture_output=True)
size = os.path.getsize(DNG)
print("DNG 重建：", DNG, size, "字节")
if size < 8_000_000:
    sys.exit(f"DNG 只有 {size} 字节，与既有台账不同档（要 --edge 3000）——这一轮不收数")

# 2) 收数那一档（只有 test_perf_report，别的用例不掺进来抢 CPU/GPU）
r = subprocess.run([RT, "-m", "pytest", "engine/tests/test_perf_report.py", "-q",
                    "--tb=short", "-p", "no:cacheprovider"],
                   cwd=REPO, env=env, capture_output=True, text=True)
tail = [l for l in r.stdout.splitlines() if "passed" in l or "failed" in l or "skipped" in l]
print("pytest:", tail[-1] if tail else r.stdout[-300:], "rc=", r.returncode)
if r.returncode != 0:
    print(r.stdout[-2000:], r.stderr[-1500:])
    sys.exit(1)

d = json.load(open(OUT, encoding="utf-8"))
# 版本对不上就是收数过程中版本漂了（定版链没跑完就收档）：宁可停，不留一份假台账
if d["env"]["engine_version"] != VERSION:
    sys.exit(f"台账里的 engine_version={d['env']['engine_version']!r} 与 packaging/VERSION"
             f"={VERSION!r} 不同：先跑 release-version.py sync 再收数")
print("engine_version =", d["env"]["engine_version"], " device =", d["env"]["device"])
for k in ("drag_render_ms", "deform_apply_ms", "deform_build_ms", "thumbnail_ms",
          "import_jpg", "import_dng", "export_per_image_ms"):
    print(" ", k, "=", json.dumps(d["metrics"].get(k), ensure_ascii=False))
print("  notes =", json.dumps(d.get("notes"), ensure_ascii=False))
print("→ 落盘：", OUT)
