#!/usr/bin/env bash
# 安装前置检查：确认这台机器的 GPU 栈真的能跑，而不是"装了个跑不动的包"。
#
# 这是 RapidRetouch 那类包最容易糊弄过去的地方——安装成功 ≠ 加速可用。
# 判定权交给 probe.py 的实测结果，本脚本只做编排与话术，不猜版本号。
#
#   用法: packaging/preflight.sh [python]
#         LRT_ENGINE_PY=... packaging/preflight.sh
#   退出码: 0 可用 / 1 依赖缺失 / 2 设备不可用 / 3 判定未通过
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
py="${1:-${LRT_ENGINE_PY:-python3}}"

echo "前置检查 · 解释器: $py"
if ! "$py" -c 'import torch' 2>/dev/null; then
  cat <<'EOF'
✗ 该解释器里没有 torch。
  AMD（ROCm）: pip install torch==2.10.0+rocm7.0 --index-url https://download.pytorch.org/whl/rocm7.0
  NVIDIA(CUDA): pip install torch --index-url https://download.pytorch.org/whl/cu126
EOF
  exit 1
fi

"$py" - <<'PY'
import torch
flavor = "ROCm" if getattr(torch.version, "hip", None) else ("CUDA" if getattr(torch.version, "cuda", None) else "CPU-only")
print(f"  torch {torch.__version__} / 构建变体 {flavor}"
      f" / cuda_available={torch.cuda.is_available()}")
if flavor == "CPU-only":
    raise SystemExit(2)
PY
rc=$?
if [ $rc -ne 0 ]; then
  echo "✗ torch 构建变体不带 GPU 后端，加速不可用"
  exit 2
fi

echo "· 跑设备打靶 probe.py（真算子、真数据，不看版本号）"
log=$(mktemp)
if ! "$py" "$here/../probe/probe.py" | tee "$log"; then
  echo "✗ probe 运行失败"
  exit 2
fi
if grep -q '^VERDICT=PASS$' "$log"; then
  echo "✓ GPU 加速可用，可以装 LumaRetouch 并启用加速"
  exit 0
fi
echo "✗ probe 判定不是 PASS，加速路径存在缺陷，先别装"
exit 3
