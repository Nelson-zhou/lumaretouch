#!/usr/bin/env bash
# M0 跑靶：tier 阶梯 + 两档尺寸 + GPU 管线，逐级把帧成本归因清楚。
#
#   tier0  像素不跨进程   → 只剩 rAF + IPC 往返，是「测量框架自身的地板」
#   tier1  像素跨进程、不上传不绘制 → 地板 + 每帧 4~10 MB 传输
#   tier2  完整通路       → 再加 texSubImage2D + drawArrays
#
# 没有 tier0/tier1，tier2 的数字没法判读：上一轮 pull_to_ack p50 17.8 ms 看着像
# 「上传要 18 ms」，实际是当时那个「下一拍才 ack」的设计把整整一个帧周期算了进去。
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)   # 先定住绝对路径：脚本会 cd 到 ui/，相对 dirname 会失效
cd "$here/../ui"
export LRT_ENGINE_PY="${LRT_ENGINE_PY:-python3}"
export LRT_ENGINE_SRC="${LRT_ENGINE_SRC:-$PWD/../engine/src}"

out="${1:-/tmp/m0-results.jsonl}"
logdir=/tmp/m0-logs
mkdir -p "$logdir"
: > "$out"
: > /tmp/m0-engine.jsonl

# 起窗口的方式：默认 `npm run tauri dev`（dev profile）；
# M0_BIN=<已安装二进制> 则直接跑安装包——dev 的 opt-level=1 会把帧率拖低三四个点，
# 判结论必须看 release（本机实测：dev 56.5 fps/6% 丢帧，release 59.6 fps/0.8%）。
if [ -n "${M0_BIN:-}" ]; then CMD=("$M0_BIN"); else CMD=(npm run tauri dev); fi

run() { # <名称> <spec> <device> <skip_draw> <skip_pixels>
  local name="$1" spec="$2" dev="$3" sd="$4" sp="$5"
  local log="$logdir/$name.log"
  printf '\n▶ %s  spec=%s device=%s skip_draw=%s skip_pixels=%s\n' "$name" "$spec" "$dev" "$sd" "$sp"
  LRT_AUTO_BENCH="$spec" LRT_DEVICE="$dev" LRT_SKIP_DRAW="$sd" LRT_SKIP_PIXELS="$sp" \
    timeout 420 "${CMD[@]}" > "$log" 2>&1
  local line
  line=$(grep -aoE 'M0_STATS \{.*\}' "$log" | tail -1 | sed 's/^M0_STATS //')
  grep -aoE 'M0_ENGINE \{.*bench_done.*\}' "$log" | sed 's/^M0_ENGINE //' \
    | python3 -c 'import sys,json
for l in sys.stdin:
    l = l.strip()
    if l:
        d = json.loads(l); d["_run"] = sys.argv[1]; print(json.dumps(d))' "$name" >> /tmp/m0-engine.jsonl
  if [ -z "$line" ]; then
    printf '  ✗ 无结果，日志: %s\n' "$log"
    grep -aoE 'M0_ERROR.*' "$log" | tail -3
    echo "$name" >> /tmp/m0-failed.txt
    return 1
  fi
  printf '%s\n' "$line" | python3 -c 'import sys,json;d=json.load(sys.stdin);d["_run"]=sys.argv[1];print(json.dumps(d,ensure_ascii=False))' "$name" >> "$out"
  python3 "$here/m0-report.py" --one "$line"
}

: > /tmp/m0-failed.txt
run "t0-1280-copy"   "1280x800:600:16.7:copy"     cpu  1 1
run "t1-1280-copy"   "1280x800:600:16.7:copy"     cpu  1 0
run "t2-1280-copy"   "1280x800:600:16.7:copy"     cpu  0 0
run "t2-2048-copy"   "2048x1280:600:16.7:copy"    cpu  0 0
run "t2-640-copy"    "640x400:600:16.7:copy"      cpu  0 0
run "t2-1280-pipe"   "1280x800:600:16.7:pipeline" cuda 0 0

echo
echo "汇总: $out   引擎分段: /tmp/m0-engine.jsonl   失败: $(tr '\n' ' ' < /tmp/m0-failed.txt)"
python3 "$here/m0-report.py" "$out" /tmp/m0-engine.jsonl
