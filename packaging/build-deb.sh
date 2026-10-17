#!/usr/bin/env bash
# M0 打包入口：产出 .deb。
# 注意：引擎（Python + torch 变体）与 AI 权重不进 .deb——体积与许可证都不合适，
# 走首启按显卡探测下载（见 docs 决策 10）。这里只保证 UI 壳与 probe 可安装。
#
# M5-c 起这里多几道自己的活：
#   ① 出包前先过发布静态门禁（版本号一致、元数据不陈旧、随包文件齐、许可未放行的
#      清单不混进来）。让"打出来的包自己会说谎"这件事停在出包这一步，而不是停在
#      装机后的真窗口那一轮——后者要重打一遍包才发现，一轮就是二十分钟。
#   ② 把包里不对的两项就地改掉：重复的 Depends 项、缺执行位的随包脚本。
#   ③/④ 打完立刻把 control 与包内容读回来对一遍：deb 的 Version 来自 tauri.conf.json，
#      而它是 release-version.py 写进去的；对不上说明同步链路在这一头断了。
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
cd "$here/.."

bash packaging/check-release.sh

cd ui
npm ci --no-audit --no-fund
npm run build            # 内含 tsc --noEmit
npm run tauri build -- --bundles deb

cd "$here/.."
ver=$(cat packaging/VERSION)
# 按版本号拿那一件：bundle/deb/ 目录里上一轮的旧包不会被 tauri 清掉，而
# `find | head -1` 也不排序——取到哪一个全看目录项顺序。真窗口那一轮量的可能就是那个旧壳。
out=$(find ui/src-tauri/target/release/bundle/deb -name "*_${ver}_amd64.deb" | head -1)
[ -n "$out" ] || { echo "× 没产出版本 $ver 的 .deb（bundle/deb 里只有旧件）"; exit 1; }
stale=$(find ui/src-tauri/target/release/bundle/deb -name '*.deb' ! -name "*_${ver}_amd64.deb" | head -3)
if [ -n "$stale" ]; then
  echo "  注意：目录里还有旧版本包（$(echo "$stale" | xargs -n1 basename | tr '\n' ' ')），"
  echo "        install-deb.sh 会按 packaging/VERSION 取件，不会拿错"
fi
echo "产物: $out"
dpkg-deb -f "$out" Package Version Depends

# ② 依赖去重 + 随包脚本补执行位：这两件事都不是“美化”，是包里真的不对。
#   · Tauri 把它自己的默认依赖追加在我们写的清单后面，于是 libwebkit2gtk-4.1-0
#     出现两次（本机实测）——重复项不会让 apt 失败，但发布校验里“依赖表不自洽”
#     那条判据必须能绿；
#   · resources 里的文件如果不带执行位，装机后的 setup-runtime.sh 就是个 644 的
#     文本——“开箱即用”那条路在包里就断了。
norm=$(mktemp -d)
dpkg-deb -R "$out" "$norm/pkg"
python3 - "$norm/pkg/DEBIAN/control" <<'PY'
import io, sys
p = sys.argv[1]
text = io.open(p, encoding="utf-8").read()
lines = text.split("\n")
for i, ln in enumerate(lines):
    if not ln.startswith("Depends:"):
        continue
    items = [x.strip() for x in ln[len("Depends:"):].split(",") if x.strip()]
    seen, keep = set(), []
    for it in items:
        name = it.split(" ")[0]
        if name in seen:
            continue
        seen.add(name)
        keep.append(it)
    lines[i] = "Depends: " + ", ".join(keep)
    print("依赖去重：%d → %d 项" % (len(items), len(keep)))
    break
io.open(p, "w", encoding="utf-8").write("\n".join(lines))
PY
stage_script=$(find "$norm/pkg" -name 'setup-runtime.sh' -type f | head -1)
if [ -n "$stage_script" ]; then
  chmod +x "$stage_script"
  echo "  已为包内 $(basename "$stage_script") 上执行位"
else
  echo "  提示：包里没有 setup-runtime.sh（后面那一项检查会拦下）"
fi
dpkg-deb --root-owner-group -b "$norm/pkg" "$out.norm" >/dev/null
mv "$out.norm" "$out"
rm -rf "$norm"
dpkg-deb -f "$out" Depends

# ③ 版本回读：文件名与 control 里的 Version 都必须是 packaging/VERSION
pkg_ver=$(dpkg-deb -f "$out" Version)
if [ "$pkg_ver" != "$ver" ]; then
  echo "× 包里的 Version 是 $pkg_ver，仓库的 packaging/VERSION 是 $ver——不要发布这个包"
  exit 1
fi
if [ ! -f "$out" ] || ! echo "$(basename "$out")" | grep -q "$ver"; then
  echo "× 包文件名没带上版本号（$(basename "$out")）：上一轮的旧包还在目录里，装机时会拿错"
  exit 1
fi
echo "✓ 包版本与 packaging/VERSION 同源：$ver"

# ④ 随包的运行时引导必须**可执行**——装机后用户要直接跑它，一个 644 的引导脚本
#    等于"开箱即用"的那条路在包里就断了。这里只报账，真补执行位在 stage/打包里做。
tmp=$(mktemp -d)
dpkg-deb -x "$out" "$tmp"
script=$(find "$tmp" -name 'setup-runtime.sh' | head -1)
if [ -z "$script" ]; then
  echo "× 包里没有 setup-runtime.sh：装机后没有运行时引导这条路"
  exit 1
fi
if [ -x "$script" ]; then
  echo "✓ 包内 setup-runtime.sh 带执行位"
else
  echo "× 包内 setup-runtime.sh 没有执行位（$(stat -c '%a' "$script")）——装机后跑不起来"
  exit 1
fi
if find "$tmp" -name '__pycache__' -o -name '*.pyc' | grep -q .; then
  echo "× 包里混进了字节码（发布物里不该有开发树的 .pyc）"
  exit 1
fi
echo "✓ 包里零字节码"
