#!/usr/bin/env bash
# 安装本地 .deb 并**按内容**证明装进去的就是刚打的那个包。
#
# 为什么要有这个脚本：本仓的包版本号固定在 0.0.1（M0 起就没动），而
# `apt install ./LumaRetouch_0.0.1_amd64.deb` 遇到同名同版本会静默跳过安装——
# 退出码 0、正常打印"已完成"，机器上跑的还是上一轮的引擎。M1-3b 实测踩过一次：
# 装机 face.py 仍是旧的 13024 B，而仓库里已经是 13446 B。
# 之后任何一轮跑靶量的都不是被测代码，数据整片作废。
#
# 所以这里做三件事：dpkg -i 强制覆盖 → 逐个文件按内容比对（不比大小/时间戳，
# 只比 sha256）→ 任一条不一致就非零退出。
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
deb=$(find "$here/../ui/src-tauri/target/release/bundle/deb" -name '*.deb' | head -1)
[ -n "$deb" ] || { echo "× 没找到 .deb，先跑 packaging/build-deb.sh"; exit 1; }

stage="$here/../ui/src-tauri/gen/engine-stage/lumaretouch_engine"
echo "→ 安装 $deb"
sudo dpkg -i "$deb"

installed=/usr/lib/LumaRetouch/engine/src/lumaretouch_engine
[ -d "$installed" ] || { echo "× 装机目录不存在：$installed（用 dpkg -L 看真实落点）"; exit 1; }
echo "→ 按内容校验装机文件与暂存目录一致（sha256，不比大小）"
bad=0; n=0
for f in "$stage"/*.py "$stage"/ops/*.py; do
  base=$(basename "$f")
  case "$f" in
    */ops/*) dst=$installed/ops/$base ;;
    *)       dst=$installed/$base ;;
  esac
  [ -f "$dst" ] || { echo "  × 装机缺少 $dst"; bad=$((bad + 1)); continue; }
  a=$(sha256sum "$f" | cut -d' ' -f1)
  b=$(sha256sum "$dst" | cut -d' ' -f1)
  n=$((n + 1))
  if [ "$a" != "$b" ]; then echo "  × 内容不同：$base"; bad=$((bad + 1)); fi
done
if [ "$bad" -ne 0 ]; then
  echo "× 校验失败：$bad 处不一致（共比对 $n 个文件）——不要开始跑靶"
  exit 1
fi
echo "✓ 已装 $n 个引擎文件，全部与暂存内容逐字节一致"
# 再点一条"这一轮的特征"：新代码里独有的字符串，命中为 0 说明装的还是旧逻辑
marker=${1:-refilter_frames}
if grep -rq "$marker" "$installed"; then
  echo "✓ 装机代码含本轮特征标记 '$marker'"
else
  echo "× 装机代码里找不到 '$marker'——装的不是刚打的那份"
  exit 1
fi
