#!/usr/bin/env bash
# M0 打包入口：产出 .deb。
# 注意：引擎（Python + torch 变体）与 AI 权重不进 .deb——体积与许可证都不合适，
# 走首启按显卡探测下载（见 docs 决策 10）。这里只保证 UI 壳与 probe 可安装。
set -euo pipefail
cd "$(dirname "$0")/../ui"

npm ci --no-audit --no-fund
npm run build            # 内含 tsc --noEmit
npm run tauri build -- --bundles deb

out=$(find src-tauri/target/release/bundle/deb -name '*.deb' | head -1)
echo "产物: $out"
dpkg-deb -f "$out" Package Version Depends
