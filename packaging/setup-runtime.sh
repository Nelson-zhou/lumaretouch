#!/usr/bin/env bash
# 引擎运行时引导：把「deb 里没有 Python 与 torch」这一事实变成一条用户可以执行的命令。
#
# 为什么 deb 不直接捆 torch：单个 ROCm 轮子装完 4 GB 上下，且按显卡厂商分叉
# （决策 10），打进 .deb 会让包体积与许可证审查都变成灾难。所以 deb 只带
# UI 壳 + 引擎源码，运行时装机后由本脚本按显卡装对应清单。
#
# 决策 10 的原文是「首启探测显卡厂商（PCI id 1002→AMD、10de→NVIDIA），装对应
# 依赖清单，失败即明示用户」。这里把那句话落成可执行、可重跑（幂等）、失败会
# 非零退出并说清缺什么的一步——不做「静默回落 CPU」：精修的常驻管线整个建立在
# torch 之上，CPU 回落跑不出可接受的帧率，装作能跑只是把失败挪到用户面前更晚
# 的位置。
#
# 装到哪个路径不是随便定的：UI 壳按同一张候选表找解释器（ui/src-tauri/src/main.rs
# 的 resolve_engine_py）。两边顺序一改，装好的运行时就会被当成"没装"。
#   1) $LRT_ENGINE_PY            开发/调试覆盖，永远优先
#   2) 用户级：~/.local/share/LumaRetouch/engine/venv/bin/python   ← 本脚本默认
#   3) 系统级：/usr/lib/LumaRetouch/engine/venv/bin/python         ← --system
#   4) python3                   兜底，几乎必然缺依赖（壳会明确报出来）
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/.." && pwd)

# 两种布局都要能跑：仓库里（本脚本在 packaging/，清单在 engine/）与装机后
# （本脚本在 /usr/lib/LumaRetouch/engine/，清单在旁边的 runtime/）。只认仓库布局的
# 引导脚本，恰好在它要解决的问题上自身不可用——那台机器上没有仓库。
req_dir=""
for cand in "$repo/engine" "$here/runtime"; do
  # 判“有没有清单文件”而不是“有没有这个目录”：装机布局下 $repo/engine 就是 $here 本身，
  # 目录在而清单不在，拿它当 req_dir 会在下一步撞一个错因不明的“清单不存在”。
  ls "$cand"/requirements-*.txt >/dev/null 2>&1 && { req_dir=$cand; break; }
done
[ -n "$req_dir" ] || { echo "× 找不到 GPU 依赖清单目录（仓库的 engine/ 或装机的 runtime/）"; exit 1; }

variant=auto
prefix=""
engine_src=""
recheck=0
dry=0
force_new=0
# 镜像：直连 download.pytorch.org 在本机实测只有 ~50 KB/s（4.5 GiB 的 ROCm 轮子要下 25 小时），
# 同一件轮子在国内镜像（南京大学）实测 37 MB/s——差了三倍多数量级。首启下载要能在用户
# 家里完成，镜像不是一个可选美化，而是这一条路能走通的本身。
# 用 LRT_WHEEL_INDEX 传；留空则用清单里写死的上游 index。
index=${LRT_WHEEL_INDEX:-}

usage() {
  cat <<'TXT'
用法：packaging/setup-runtime.sh [选项]

  --variant auto|rocm|cuda|cpu  引擎变体（默认 auto：按 PCI 厂商探测装 GPU；cpu 是无 GPU 的显式降级
                              路径，帧率受限，能力/性能边界见 docs/adr/0022，非静默回落）
  --prefix DIR               运行时安装位置（默认 用户级 XDG_DATA_HOME/LumaRetouch/engine/venv）
  --system                   装到系统级 /usr/lib/LumaRetouch/engine/venv（需 root）
  --engine-src DIR           自检时用的引擎源码目录（默认自动找：仓库 engine/src → 装机资源目录）
  --index-url URL            用镜像取 GPU 轮子（也可用 env LRT_WHEEL_INDEX）；留空用清单里的上游 index
  --recheck                  只跑自检，不装任何东西（CI 与装机校验用）
  --force-new                重建 venv（默认复用已有的，幂等重跑只补装与自检）
  --dry-run                  把探测结果与将要执行的命令打出来，不动磁盘
  -h, --help                 本帮助
TXT
}

while [ $# -gt 0 ]; do
  case "$1" in
    --variant) variant=$2; shift 2 ;;
    --prefix) prefix=$2; shift 2 ;;
    --system) prefix=/usr/lib/LumaRetouch/engine/venv; shift ;;
    --engine-src) engine_src=$2; shift 2 ;;
    --index-url) index=$2; shift 2 ;;
    --recheck) recheck=1; shift ;;
    --force-new) force_new=1; shift ;;
    --dry-run) dry=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "× 未知选项：$1"; usage; exit 2 ;;
  esac
done

# ---------------------------------------------------------------- 显卡探测
# 读 sysfs 而不是 lspci：lspci 属 pciutils，是 deb 的 Depends 里没有的可选工具，
# 而 /sys/bus/pci 在任何 Linux 上都在。class 0x03xxxx 才是显示控制器——网卡、
# 桥设备也是 1002/10de 的 vendor，只看 vendor 会把主板芯片组认成显卡。
detect_vendors() {
  local d v c
  for d in /sys/bus/pci/devices/*/; do
    [ -r "$d/class" ] || continue
    c=$(cat "$d/class" 2>/dev/null) || continue
    case "$c" in 0x03*) ;; *) continue ;; esac
    v=$(cat "$d/vendor" 2>/dev/null) || continue
    echo "$v"
  done | sort -u
}

vendors=$(detect_vendors || true)
# 厂商探测只服务 auto；显式 --variant rocm|cuda|cpu 一律绕过探测，按用户点名的变体装。
if [ "$variant" != auto ]; then
  :
elif [ -z "$vendors" ]; then
  echo "× sysfs 里没找到任何显示控制器（class 0x03xxxx），无法判定 GPU 厂商"
  echo "  显式指定变体可绕过探测：--variant rocm / cuda；确需无 GPU 路径用 --variant cpu（性能受限，见 ADR-0022）"
  exit 1
else
  echo "→ 探测到显示控制器厂商：$(echo "$vendors" | tr '\n' ' ')"
  if echo "$vendors" | grep -q '^0x1002$'; then
    variant=rocm
  elif echo "$vendors" | grep -q '^0x10de$'; then
    variant=cuda
  else
    echo "× 既不是 AMD（0x1002）也不是 NVIDIA（0x10de）的显卡；不猜变体"
    echo "  要无 GPU 路径请显式 --variant cpu（本脚本不把没跑过的路径当默认，也不静默回落 CPU）"
    exit 1
  fi
fi
req="$req_dir/requirements-$variant.txt"
[ -f "$req" ] || { echo "× 清单不存在：$req"; exit 1; }
echo "→ 变体 $variant，清单 $req"

# 给了镜像就把清单里那行 --index-url 剔掉：两处各说一个 index 时， uv/pip 以清单里那行为准，
# 拿它当“能覆盖”会静默回落到上游——那正好是今晚这种 25 小时的下法。
eff_req="$req"
if [ -n "$index" ]; then
  eff_req=$(mktemp)
  grep -v '^\s*--index-url' "$req" > "$eff_req"
  echo "→ 轮子镜像：$index（剔掉清单里的上游 index 后另存临时清单）"
fi

# requirements-cuda.txt 的 pin 至今没在 N 卡上验证过（文件头写明由带 NVIDIA runner
# 的 CI 回填）。让它跟 ROCm 一样"直接开装"等于替用户装一套没解析过的依赖图。
if [ "$variant" = cuda ]; then
  echo "  注意：CUDA 变体的精确 pin 尚未在任何 N 卡上实测（见清单头注释）。"
fi

if [ "$variant" = cpu ]; then
  echo "  注意：CPU 是无 GPU 的显式降级路径（手册 P0②）。常驻精修管线在 CPU 上帧率显著低于 GPU，"
  echo "        仅可用、非流畅；能力/性能边界见 docs/adr/0022-…md，精确 pin 待无 GPU 裸机实测回填。"
fi

# ---------------------------------------------------------------- 安装位置
if [ -z "$prefix" ]; then
  data_home=${XDG_DATA_HOME:-$HOME/.local/share}
  prefix="$data_home/LumaRetouch/engine/venv"
fi
pybin="$prefix/bin/python"

if [ "$engine_src" = "" ]; then
  for cand in "$repo/engine/src" "$here/src" /usr/lib/LumaRetouch/engine/src; do
    [ -d "$cand/lumaretouch_engine" ] && { engine_src=$cand; break; }
  done
fi
[ -n "$engine_src" ] || { echo "× 找不到引擎源码目录（--engine-src 显式指定）"; exit 1; }

if [ -x "$prefix/bin/pip" ]; then
  echo "→ 运行时已存在：$prefix（幂等重跑 = 校验 + 补装）"
fi

# ---------------------------------------------------------------- 自检
# 自检跑的是引擎真正的 import 链，不是"torch 能不能 import"：server.py 一路会拉
# vram/ops/guided 等模块，缺哪个包、哪个符号在这里就露出来了。
selfcheck() {
  LRT_VARIANT="$variant" PYTHONPATH="$engine_src" "$pybin" - <<'PY'
import sys, json, os
from lumaretouch_engine.privacy import require_offline_or_exit, policy_status
require_offline_or_exit()
import numpy, PIL, tifffile, imagecodecs
import torch
import lumaretouch_engine.server as _server   # 真正的 import 链
from lumaretouch_engine import __version__
from lumaretouch_engine.color16 import _library as _color_library
_color_library()  # fail clearly if the system RGB16 ICC runtime is absent
info = {
    "python": sys.version.split()[0],
    "privacy": policy_status(),
    "engine_version": __version__,
    "numpy": numpy.__version__,
    "pillow": PIL.__version__,
    "tifffile": tifffile.__version__,
    "imagecodecs": imagecodecs.__version__,
    "icc16_runtime": "LittleCMS 2 (system)",
    "torch": torch.__version__,
    "hip": getattr(torch.version, "hip", None),
    "cuda": getattr(torch.version, "cuda", None),
    "gpu_available": bool(torch.cuda.is_available()),
    "device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
    "device_name": (torch.cuda.get_device_name(0)
                    if torch.cuda.is_available() else None),
}
# 人脸后端可用性单独报：它是“可选但已装”这一档，报成布尔值而不是缺席字段，
# 这样“装失败但自检全绿”这种情态在本机日志里一眼就能看出来。
try:
    import importlib.util as _iu
    from lumaretouch_engine import face as _face
    _have = _iu.find_spec("mediapipe") is not None
    _dirs = _face.model_search_dirs(None)
    _models = {m: next((d for d in _dirs if __import__("os").path.isfile(
                   __import__("os").path.join(d, m))), None) or "MISSING"
               for m in (_face.FACE_LANDMARKER_MODEL, _face.SELFIE_MULTICLASS_MODEL)}
    info["face_mediapipe_import"] = _have
    info["face_model_paths"] = _models
    info["face_backend"] = ("mediapipe" if _have and
                            all(v != "MISSING" for v in _models.values()) else "unavailable")
except Exception as _e:
    info["face_backend"] = f"error: {type(_e).__name__}: {_e}"
print("LRT_RUNTIME_SELFCHK " + json.dumps(info, ensure_ascii=False))
_variant = os.environ.get("LRT_VARIANT", "auto")
if _variant != "cpu" and not info["gpu_available"]:
    print("× torch 报告没有可用 GPU 设备", file=sys.stderr)
    sys.exit(3)
if _variant == "cpu":
    print("  （CPU 变体：按无 GPU 路径自检，gpu_available=False 属预期）", file=sys.stderr)
PY
}

if [ "$recheck" = 1 ]; then
  [ -x "$pybin" ] || { echo "× 运行时不存在：$pybin（先不带 --recheck 跑一次）"; exit 1; }
  echo "→ 自检 $pybin"
  selfcheck
  echo "✓ 运行时自检通过"
  exit 0
fi

if [ "$dry" = 1 ]; then
  cat <<TXT
--dry-run，未动磁盘。将执行：
  1) 建 venv     $(command -v uv >/dev/null && echo "uv venv --seed --python 3.12 $prefix" || echo "python3 -m venv $prefix")
  2) 装 torch 轮子 $(command -v uv >/dev/null && echo "uv pip install --python $pybin ${index:+--index-url $index }-r $eff_req" || echo "$pybin -m pip install -r $eff_req")
  3) 装引擎依赖  $(command -v uv >/dev/null && echo "uv pip install --python $pybin 'numpy>=2.1' 'pillow>=11' 'tifffile==2026.10.15' 'imagecodecs==2026.10.10'" || echo "$pybin -m pip install 'numpy>=2.1' 'pillow>=11' 'tifffile==2026.10.15' 'imagecodecs==2026.10.10'")
  4) 自检        PYTHONPATH=$engine_src $pybin -c 'import lumaretouch_engine.server'
TXT
  exit 0
fi

idx_args=()
if [ -n "$index" ]; then
  # 只给一个 index，不补 PyPI 作 extra：本机实测——补了之后 uv 先在 PyPI 上看到 `torch`，
  # 默认的第一命中 index 策略（防 dependency confusion）就不再去看镜像，于是
  # `torch==2.10.0+rocm7.0` 直接报“unsatisfiable”。上游 download.pytorch.org 那个
  # 单 index 本来就能解出全部 14 个包（镜像同一棵树），不需要拿安全机制换方便。
  idx_args=(--index-url "$index")
fi

mkdir -p "$(dirname "$prefix")"
if [ -x "$pybin" ] && [ "$force_new" = 0 ]; then
  # 幂等重跑不能"先把上一次的成果拆掉"：uv 对已存在的 venv 直接报错退出，而装到一半
  # 断掉的运行时重跑一次就该接着装。要干净重建，显式给 --force-new。
  echo "→ 复用已存在的 venv：$prefix（重建请加 --force-new）"
elif command -v uv >/dev/null 2>&1; then
  echo "→ uv 建 venv：$prefix"
  clear_arg=()
  [ "$force_new" = 1 ] && clear_arg=(--clear)
  uv venv "${clear_arg[@]}" --seed --python 3.12 "$prefix"
else
  echo "→ python3 -m venv：$prefix"
  python3 -m venv "$prefix"
  "$pybin" -m pip install --upgrade pip
fi
if command -v uv >/dev/null 2>&1; then
  echo "→ 装 GPU 变体（uv 的缓存命中走硬链接，第二次装几乎不占新磁盘）"
  uv pip install --python "$pybin" "${idx_args[@]}" -r "$eff_req"
  echo "→ 装引擎运行时依赖"
  uv pip install --python "$pybin" 'numpy>=2.1' 'pillow>=11' 'tifffile==2026.10.15' 'imagecodecs==2026.10.10'
else
  "$pybin" -m pip install "${idx_args[@]}" -r "$eff_req"
  "$pybin" -m pip install 'numpy>=2.1' 'pillow>=11' 'tifffile==2026.10.15' 'imagecodecs==2026.10.10'
fi
[ -n "$index" ] && rm -f "$eff_req"

# 人脸关键点运行时（MediaPipe FaceMesh，Apache-2.0）。
# 单独一步而不并进 GPU 清单：那份带 --index-url 指向 pytorch 专仓，把 PyPI 包写进去
# 会去错仓找包。也是这个原因它必须走默认 index。
#
# 装不上**不让整个运行时报错**：磨皮/调色/导出是 0 权重管线，没 mediapipe 也该照常
# 可用；面部重塑在缺依赖时由引擎抛 MissingBackend 显式说明缺什么，绝不静默退成
# 占位后端。把“能不能脸重塑”写成安装期的硬前提，会顺带把无网机器整个挡在门外。
mp_req="$req_dir/requirements-mediapipe.txt"
if [ -f "$mp_req" ]; then
  echo "→ 装人脸关键点运行时（mediapipe，走 PyPI；失败不阻断，仅面部重塑不可用）"
  if command -v uv >/dev/null 2>&1; then
    uv pip install --python "$pybin" -r "$mp_req" || echo "  ! mediapipe 未装成（下面自检会报）"
  else
    "$pybin" -m pip install -r "$mp_req" || echo "  ! mediapipe 未装成（下面自检会报）"
  fi
else
  echo "→ 跳过人脸关键点运行时（清单不在：$mp_req）"
fi

echo "→ 自检（引擎真实 import 链 + GPU 可用性）"
selfcheck
echo "✓ 运行时就绪：$pybin"
echo "  UI 壳会按候选表自动找到它；无需设置任何环境变量。"
