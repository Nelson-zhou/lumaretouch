#!/usr/bin/env bash
# 运行时环境测试门禁：出包前，引擎测试必须在**和装机同一形状**的那个 venv 里全跑一遍。
#
# 为什么单独立一条，而不是并进 check-release.sh：
#   check-release.sh 刻意"不需要 GPU、不需要 root"，为的是 CI 的 packaging job 能直接跑。
#   而"不需要 torch"恰恰就是这一条要堵的口子——本轮的真实事故：
#     d3b 把 `_exposure` 加进了 DOC_FIELDS 与 _capture_state，唯独没加进 _fresh_doc_state；
#     开发 venv 里 `pytest engine/tests` 报的是 **384 passed / 247 skipped**，全绿；
#     装上运行时之后第一次 load_image 就 `KeyError: '_exposure'`，产品直接打不开图。
#   那 247 条 skip 里就包括全部需要 torch 的协议用例。skip 掉的测试不是证据。
#
# 判缺了就不过，没有"读不到就跳过"这一支：
#   ① 运行时 venv 不在 → 先跑 packaging/setup-runtime.sh（装机引导本来就要求这一步）；
#   ② 那个 venv 里没有 torch → 上面那条等于没跑，直接红；
#   ③ skip 条数超过上限 → 说明这一遍又退化成"没 GPU 的那份绿"，红；
#   ④ 任何一条用例红 → 红。
set -uo pipefail

here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/.." && pwd)
cd "$repo"

max_skips=${LRT_MAX_SKIPS:-24}          # 运行时 venv 实测只该剩个位数（缺样本图那一类）
py=${LRT_TEST_PYTHON:-}
if [ -z "$py" ]; then
  for cand in "${XDG_DATA_HOME:-$HOME/.local/share}/LumaRetouch/engine/venv/bin/python" \
              /usr/lib/LumaRetouch/engine/venv/bin/python; do
    if [ -x "$cand" ]; then py=$cand; break; fi
  done
fi

if [ -z "$py" ] || [ ! -x "$py" ]; then
  echo "× 找不到运行时 venv（试过 ~/.local/share 与 /usr/lib 两处候选）"
  echo "  → 先跑 packaging/setup-runtime.sh；没有它就没有“装机形状”的测试环境"
  exit 1
fi
echo "· 运行时解释器：$py"

if ! "$py" -c "import torch" >/dev/null 2>&1; then
  echo "× 这个 venv 里没有 torch：跑出来的绿与开发 venv 无异，本门禁要验的正是 GPU 形状"
  echo "  （torch 缺席时那批常驻管线/导出用例全部 skip，而它们才是装机会走的路）"
  exit 1
fi
tv=$("$py" -c "import torch;print(torch.__version__)")
gpu=$("$py" -c "import torch;print('可见 GPU' if torch.cuda.is_available() else 'CPU -only')")
echo "· torch $tv（$gpu）"

log=/tmp/check-tests-runtime.log
PYTHONPATH=engine/src "$py" -m pytest engine/tests -q >"$log" 2>&1
rc=$?
summary=$(grep -E "passed|failed|error" "$log" | tail -1)
echo "· 结果：${summary:-（没拿到汇总行，见 $log）}"

skips=$(printf '%s' "$summary" | sed -n 's/.*\([0-9]\+\) skipped.*/\1/p')
if [ -n "${skips:-}" ] && [ "$skips" -gt "$max_skips" ]; then
  echo "× skip 了 $skips 条（上限 $max_skips）：这一遍又变成了“没 GPU 的那份绿”"
  echo "  真实事故就是这一形：384 passed / 247 skipped 全绿，装机第一次 load_image 就 KeyError"
  exit 1
fi

if [ "$rc" -ne 0 ]; then
  echo "× 运行时环境测试不过——不要出包。尾部摘录："
  tail -25 "$log" | sed 's/^/     /'
  exit 1
fi
echo "✓ 运行时环境测试全过（${summary}）"
