#!/usr/bin/env bash
# M1 通路对比矩阵：按臂重复跑，聚合看中位与最差。
#
# 两条从实测里学到的规矩（都写过错结论，别再踩）：
#   1) 单一采样不能下结论。同一份二进制、同一参数背靠背两轮分别报 54.1 与 57.1 fps、
#      撞帧 4/5 与 2/5 —— 本机噪声底约 ±3 fps。任何小于这个量级的“改善”都不算数。
#   2) 因此默认**交错跑**（INTERLEAVE=1）：每轮把所有臂各跑一次，臂序固定但时间上穿插，
#      这样机器状态漂移会同时作用于所有臂，而不是把“先跑的臂”和“后跑的臂”分成两种条件。
#
# 引擎侧分段（bench_done）一并采集到 <out>.engine.jsonl：E 轮要证的是「内核没变、
# 省的全是搬运」，只看 fps 会被显示通路的字节尾部盖住。
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)   # 用绝对路径定位同目录的 m0-report.py，不依赖调用方的 cwd
out="${1:-/tmp/m1-upload.jsonl}"
eng="${out%.jsonl}.engine.jsonl"
reps="${REPS:-5}"
frames="${FRAMES:-600}"
size="${SIZE:-1280x800}"
bin="${M0_BIN:-/usr/bin/lumaretouch}"
export LRT_ENGINE_PY="${LRT_ENGINE_PY:-python3}"
# 带管线的臂先验一下解释器：系统 python3 往往没 numpy/torch，这种情况跑出来的
# 是一份“引擎起不来”的空白矩阵，要三秒钟就能自己发现，不必等二十分钟。
if [ "${ROUND:-e}" = "e" ] && ! "$LRT_ENGINE_PY" -c 'import numpy, torch' >/dev/null 2>&1; then
  echo "✗ LRT_ENGINE_PY=$LRT_ENGINE_PY 导不了 numpy/torch——管线臂会全部空跑"
  echo "  指向一个 ROCm/CUDA 版 torch 的解释器再跑，例：LRT_ENGINE_PY=/path/.venv/bin/python $0"
  exit 2
fi
: > "$out"
: > "$eng"

run_one() { # <序号> <臂名> <upload> <dirty_frac> <no_ctx> <尺寸> <分块> <模式> <设备>
  local i="$1" name="$2" up="$3" df="$4" nc="$5" sz="$6" ck="$7" md="${8:-copy}" dv="${9:-cpu}" line
  local log="/tmp/m1-$name-$i.log"
  LRT_AUTO_BENCH="$sz:$frames:16.7:$md" LRT_UPLOAD="$up" LRT_DIRTY_FRAC="$df" \
  LRT_NO_CTX="$nc" LRT_CHUNKS="$ck" LRT_DEVICE="$dv" timeout 240 "$bin" > "$log" 2>&1
  grep -aoE 'M0_ENGINE \{.*bench_done.*\}' "$log" | sed 's/^M0_ENGINE //' \
    | python3 -c 'import sys,json
for l in sys.stdin:
    l = l.strip()
    if l:
        d = json.loads(l); d["_run"] = sys.argv[1]; print(json.dumps(d))' "$name#$i" >> "$eng"
  line=$(grep -aoE 'M0_STATS \{.*\}' "$log" | tail -1 | sed 's/^M0_STATS //')
  if [ -z "$line" ]; then
    echo "  ✗ $name #$i 无结果，见 $log"
    grep -aoE 'M0_ERROR.*' "$log" | tail -1
    grep -aoE '引擎错误.*' "$log" | tail -1
    return 1
  fi
  printf '%s\n' "$line" | python3 -c 'import sys,json;d=json.load(sys.stdin);d["_run"]=sys.argv[1];print(json.dumps(d,ensure_ascii=False))' "$name#$i" >> "$out"
}

# 臂定义：<臂名>|<upload>|<dirty_frac>|<no_ctx>|<尺寸>|<分块>|<模式>|<设备>
arms=()
echo "M1 通路矩阵 · frames=$frames reps=$reps bin=$bin round=${ROUND:-e} interleave=${INTERLEAVE:-1}"
case "${ROUND:-e}" in
  # A 轮：上传策略对比（结论：脏矩形>其余；bitmap 延迟多一拍）
  a) arms=("A1-raw|raw|1|1|1280x800|1" "A2-bitmap|bitmap|1|1|1280x800|1"
           "A3-pingpong|pingpong|1|1|1280x800|1" "A4-ctx|raw|1|0|1280x800|1"
           "A5-dirty25|raw|0.25|1|1280x800|1") ;;
  # B 轮：把 ctx 从上传策略里剖出来背靠背（结论：ctx 无可复现收益）
  b) arms=("B1-full-ctx|raw|1|0|1280x800|1" "B2-full-raw|raw|1|1|1280x800|1"
           "B3-dirty-ctx|raw|0.25|0|1280x800|1" "B4-dirty-raw|raw|0.25|1|1280x800|1") ;;
  # C 轮：扫每帧字节找撞帧拐点（结论：3.32 MB 干净、4.10 MB 撞帧）
  c) arms=("C1-640x400|raw|1|1|640x400|1" "C2-960x600|raw|1|1|960x600|1"
           "C3-1152x720|raw|1|1|1152x720|1" "C4-1280x800|raw|1|1|1280x800|1"
           "C5-dirty-1MB|raw|0.25|1|1280x800|1") ;;
  # D 轮：验“4 MiB 命令缓冲”假设（结论：假设不成立，拆调用无效）
  d) arms=("D1-1280-c1|raw|1|1|1280x800|1" "D2-1280-c2|raw|1|1|1280x800|2"
           "D3-1280-c4|raw|1|1|1280x800|4" "D4-2048-c8|raw|1|1|2048x1280|8") ;;
  # E 轮：引擎侧改造的通路总览——空管线 vs 张量常驻 GPU 管线 vs 逐帧搬运管线
  # 每档尺寸都配一个 copy 对照组：1280 的 fps 被 4.1 MB/帧的显示尾部钉住，
  # 960（2.3 MB，尾部干净）才量得见引擎侧改善能不能转化成帧率。
  e) arms=("E1-copy-1280|raw|1|1|1280x800|1|copy|cpu"
           "E2-resident-1280|raw|1|1|1280x800|1|pipeline_resident|cuda"
           "E3-copyin-1280|raw|1|1|1280x800|1|pipeline_copyin|cuda"
           "E4-copy-960|raw|1|1|960x600|1|copy|cpu"
           "E5-resident-960|raw|1|1|960x600|1|pipeline_resident|cuda"
           "E6-copyin-960|raw|1|1|960x600|1|pipeline_copyin|cuda") ;;
esac

if [ "${INTERLEAVE:-1}" = "1" ]; then
  for i in $(seq 1 "$reps"); do
    for a in "${arms[@]}"; do IFS='|' read -r n up df nc sz ck md dv <<< "$a"; run_one "$i" "$n" "$up" "$df" "$nc" "$sz" "$ck" "${md:-copy}" "${dv:-cpu}"; done
    echo "  · 第 $i 轮全部臂完成"
  done
else
  for a in "${arms[@]}"; do
    IFS='|' read -r n up df nc sz ck md dv <<< "$a"
    for i in $(seq 1 "$reps"); do run_one "$i" "$n" "$up" "$df" "$nc" "$sz" "$ck" "${md:-copy}" "${dv:-cpu}"; done
    echo "  · 臂 $n 跑完 $reps 次"
  done
fi

python3 "$here/m0-report.py" "$out" "$eng"
