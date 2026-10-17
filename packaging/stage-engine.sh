#!/usr/bin/env bash
# 打包前把引擎源码暂存进 src-tauri/gen/engine-stage，供 tauri 的 resources 收进 .deb。
#
# 为什么不直接把 ../engine/src 指给 resources：那样会把开发树的 __pycache__/*.pyc
# 一起打进发行包（第一次出包就中招了）。发布物只该有源码，不该有别人机器上的字节码。
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
stage="$here/../ui/src-tauri/gen/engine-stage"
mkdir -p "$stage"
( cd "$here/../engine/src" && tar cf - --exclude='__pycache__' --exclude='*.pyc' . ) \
  | ( cd "$stage" && tar xf - )

# 运行时引导那两件（M5-c）也随包走：torch 不进 .deb（体积与许可），但
# “按显卡装对应清单”这件事得有可执行的东西留在装机件里，而且它得在**没有仓库
# 的机器上**能跑——所以 GPU 清单本身也要进包，不能只留在 engine/ 目录里。
rt="$stage/runtime"
# 先清再生成：gen/ 是上一轮的目录，留着旧文件就会把“本轮不该随包走”的那几条
# 继续打进 .deb（上面那条 mediapipe 的规矩只能靠不残留来保证）。
[ -d "$rt" ] && find "$rt" -type f -delete
mkdir -p "$rt"
cp "$here/../packaging/setup-runtime.sh" "$stage/setup-runtime.sh"
chmod +x "$stage/setup-runtime.sh"
cp "$here/../engine/requirements-rocm.txt" "$here/../engine/requirements-cuda.txt" "$rt/"
# 故意**不**随包走 requirements-mediapipe.txt：那棵依赖树的许可审计还没放行（文件自己写着
# “未放行前不许安装”）。把清单放进装机件里，等于在发行物里留一条“看着像受支持的
# 安装路径”——而跑它的人拿不到任何审批背书。
cp "$here/../packaging/VERSION" "$rt/VERSION"   # 发布校验拿它对账，运行时里那份必须与包同源

echo "引擎已暂存: $stage"
find "$stage" -name '*.py' | sed 's|^|  · |'
echo "  · setup-runtime.sh + $(ls "$rt" | tr '\n' ' ')"
