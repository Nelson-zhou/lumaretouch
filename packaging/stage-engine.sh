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
echo "引擎已暂存: $stage"
find "$stage" -name '*.py' | sed 's|^|  · |'
