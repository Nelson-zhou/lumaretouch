#!/usr/bin/env bash
# 发布静态门禁：出包之前先把"发布物自己会不会骗人"这几件事查掉。不需要 GPU、不需要 root，
# 所以 CI 的 packaging job 能直接跑。
#
# 每一条都对应一次真实的事故或一个真实的分叉点，不是装饰性检查：
#   ① 版本号八处一致——deb 说 0.9.0 而引擎报 0.0.1，装机后就没人能说出"跑的是哪一份"；
#   ② 包描述不许停留在旧里程碑——dpkg 列表里那行字是用户判断"这装的是什么"的唯一入口，
#      写"M0 骨架"的包被装到修图师机器上，就是产品意义上的假指标；
#   ③ 运行时候选表两边字面一致——setup-runtime.sh 把 venv 装到哪，Rust 就得按同一张表
#      去找；两边分叉的报错长得和"没装"一模一样，最难查；
#   ④ 暂存目录卫生——开发树的 __pycache__/*.pyc 第一次出包就被打进过发行物；
#   ⑤ 许可没放行的清单不许随包走（mediapipe），否则发行物里就有一条"看着像受支持的
#      安装路径"。
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/.." && pwd)
cd "$repo"

fail=0
say() { echo "$1 — $2"; }
bad() { say "×" "$1"; fail=$((fail + 1)); }
good() { say "✓" "$1"; }

# ① 版本号一致
if python3 packaging/release-version.py check >/tmp/check-release-version.log 2>&1; then
  good "版本号一致：$(cat packaging/VERSION) 与八处落点全部对上"
else
  bad "版本号漂移（详见 /tmp/check-release-version.log）："
  sed 's/^/     /' /tmp/check-release-version.log | tail -6
fi
ver=$(cat packaging/VERSION)

# ② 包描述不许陈旧
if grep -q "M0 骨架" ui/src-tauri/tauri.conf.json ui/src-tauri/Cargo.toml; then
  bad "打包元数据里还写着「M0 骨架」——dpkg 的那行描述是用户认识这个包的唯一入口"
else
  good "打包元数据已按发布版描述（无 M0 骨架字样）"
fi
if ! grep -q '"version": "'"$ver"'"' ui/src-tauri/tauri.conf.json; then
  bad "tauri.conf.json 的 version 与 VERSION 不同源（应由 release-version.py sync 写）"
fi

# ③ 运行时候选表：脚本的默认安装位置必须出现在 Rust 的候选表里
rust=ui/src-tauri/src/main.rs
sh=packaging/setup-runtime.sh
for needle in "LumaRetouch/engine/venv/bin/python" "/usr/lib/LumaRetouch/engine/venv"; do
  if grep -q "$needle" "$rust" && grep -q "$needle" "$sh"; then
    good "运行时候选路径两边一致：$needle"
  else
    bad "运行时候选路径只在一边出现：$needle（脚本装到哪 ↔ 宿主找到哪，分叉即“装好了却说没装”）"
  fi
done
# 用户级那一档由 XDG_DATA_HOME 拼出来，两边都得写 LumaRetouch/engine/venv 这一段
if ! grep -q 'LumaRetouch/engine/venv' "$sh"; then
  bad "$sh 里没有用户级运行时的默认位置"
fi

# ④ 暂存目录卫生（跑过 stage-engine.sh 之后才查得到东西；没跑过就先生成一次）
stage=ui/src-tauri/gen/engine-stage
[ -d "$stage/lumaretouch_engine" ] || bash packaging/stage-engine.sh >/dev/null
junk=$(find "$stage" \( -name '__pycache__' -o -name '*.pyc' -o -name '*.pyo' \) | head -3)
if [ -n "$junk" ]; then
  bad "暂存目录里有字节码残留：$(echo "$junk" | tr '\n' ' ')"
else
  good "暂存目录零字节码（发布物里不该有别人机器上的 .pyc）"
fi
# requirements-cpu.txt 是手册 P0 首版②那条无 GPU 显式安装路径（--variant cpu）的清单：装机后
# runtime 目录里必须有它，否则 --variant cpu 报“清单不存在”——这条路径就在真无 GPU 机器上
# 断掉。与 rocm/cuda 同档，纳入必在硬门禁（反向：谁把 stage-engine.sh 里的 cp 删了这里就红）。
for f in setup-runtime.sh runtime/requirements-rocm.txt runtime/requirements-cuda.txt runtime/requirements-cpu.txt runtime/VERSION; do
  if [ -f "$stage/$f" ]; then
    good "随包文件在位：$f"
  else
    bad "随包文件缺失：$stage/$f（装机后就没有运行时引导这条路了）"
  fi
done
if [ "$(cat "$stage/runtime/VERSION" 2>/dev/null)" != "$ver" ]; then
  bad "暂存的 runtime/VERSION 与 packaging/VERSION 不同：出包前重跑 stage-engine.sh"
fi

# ⑤ 发布物里的依赖清单：该在的必须在，不该在的必须不在。两个方向都要查——只查
#    一个方向的话，“门禁因为代码改并而关上了”和“因为根本没人装而开着”长得一模一样。
#    requirements-mediapipe.txt 从 ADR-0002 起是**必须在**：没它装机后面部重塑永远装不上，
#    而它自己带了逐包许可审计；THIRD_PARTY_NOTICES 同必须在，因为它补的就是
#    matplotlib（不可从 mediapipe 剔除）与 libportaudio 的声明义务。
#    libraw 可选插件通道仍未逐包审计，继续禁止混进发布物。
for need in requirements-mediapipe.txt THIRD_PARTY_NOTICES; do
  if find "$stage" -name "$need" | grep -q .; then
    good "$need 已随包（清单与声明文件在位；内容适用性另审）"
  else
    bad "$need 没进发布物——没有它，装机后面部重塑无路可装或声明义务没人担"
  fi
done
for unfree in requirements-libraw.txt; do
  if find "$stage" -name "$unfree" | grep -q .; then
    bad "$unfree 混进了发布物——那棵依赖树的许可审计还没放行"
  else
    good "$unfree 未随包走（依赖树许可门禁保持生效）"
  fi
done

# ⑥ 模型台账与发布物对账（ADR-0001）。两边都管：
#    a) 台账里标 bundled 的条目必须真填完了：sha256 非空 + 证据一手。没填完就标
#       bundled，等于在发行声明里写了一个自己都不知道的数；
#    b) 暂存目录里真出现了权重文件时，它必须在台账里有条目、条目必须是 bundled，
#       而且文件实际哈希要跟台账一致——防“进了包但没人核过”。
if [ -f docs/model-licenses/models.json ]; then
  python3 packaging/check-model-artifacts.py "$stage" || exit 1
else
  bad "缺 docs/model-licenses/models.json——许可台账是发布契约的一部分"
fi

# ⑦ P0 注册表的面板覆盖：冻结的 36 条必须逐条有格子，接不通的必须带原因。
#    这一条查的是"发行物自己会不会骗人"里最贵的一形：界面上根本没有那个参数。
if python3 tools/check-p0-coverage.py >/tmp/check-release-p0.log 2>&1; then
  good "P0 注册表面板覆盖：$(grep -c '^✓' /tmp/check-release-p0.log) 项全过（36 格逐条落位，禁用格都带原因）"
else
  bad "P0 注册表面板覆盖不过："
  sed 's/^/     /' /tmp/check-release-p0.log
fi

# ⑧ 开发机的绝对路径不许出现在将要打包的文本资产里
if grep -rlI "$HOME" "$stage" 2>/dev/null | grep -q .; then
  bad "暂存目录里写死了当前用户的主目录路径"
else
  good "暂存目录零本机路径"
fi

echo
if [ "$fail" -ne 0 ]; then
  echo "× 发布静态门禁：$fail 条不过——不要出包"
  exit 1
fi
echo "✓ 发布静态门禁全过（版本 $ver）"
