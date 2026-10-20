"""P2-5：干净 CI 的 UI job 必须在 cargo check 之前暂存引擎资源。

缺陷现场：tauri.conf.json 的 bundle.resources 指向 gen/engine-stage/*，而
tauri_build::build() 在 `cargo check` 阶段就校验这些源目录存在。历史口径写得很直白——
"Rust 检查在准备 staging 资源后通过"。可 CI 的 ui job 只 `npm ci + tsc` 后直接 cargo check，
从没跑过 stage:engine；beforeBuildCommand（才做暂存）只在 `tauri build` 触发，救不了裸
cargo check。于是干净 checkout 的 CI 要么 cargo check 直接红，要么这一步根本没被真正验证过。

纯静态、无副作用：钉住 ui job 里"暂存引擎"这一步存在且排在 cargo check 之前，并确认 resources
确实指向 engine-stage（前提不成立时这条判据就没意义）。改回去（删步骤或排到后面）就红。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CI = REPO / ".github" / "workflows" / "ci.yml"
TAURI = REPO / "ui" / "src-tauri" / "tauri.conf.json"


def _ui_job_body(text: str) -> str:
    """切出 `  ui:` 到下一个同级 job（两空格缩进的键）之间的片段。"""
    m = re.search(r"^  ui:\n", text, re.MULTILINE)
    assert m, "ci.yml 里找不到 ui job"
    start = m.end()
    nxt = re.search(r"^  [a-z][a-z0-9-]*:\n", text[start:], re.MULTILINE)
    return text[start:start + (nxt.start() if nxt else len(text))]


def test_resources_point_at_engine_stage():
    """前提：bundle.resources 的源确实落在 gen/engine-stage/——否则本条判据没意义。"""
    conf = json.loads(TAURI.read_text(encoding="utf-8"))
    resources = conf["bundle"]["resources"]
    assert resources, "tauri.conf.json 没有 bundle.resources"
    staged = [k for k in resources if str(k).startswith("gen/engine-stage/")]
    assert staged, f"resources 没有一条指向 gen/engine-stage/：{list(resources)}"


def test_ui_job_stages_engine_before_cargo_check():
    body = _ui_job_body(CI.read_text(encoding="utf-8"))
    # 只认步骤的 run 行，别被注释里的散文"cargo check"骗到
    stage = re.search(r"run:\s*npm run stage:engine", body)
    cargo = re.search(r"run:\s*cargo check", body)
    assert stage, "ui job 里没有 `run: npm run stage:engine`：干净 CI 缺资源 staging（P2-5）"
    assert cargo, "ui job 里没有 cargo check 步骤"
    assert stage.start() < cargo.start(), \
        "stage:engine 排在 cargo check 之后：check 阶段资源还不存在，照样红"


def test_ui_job_still_runs_tsc_and_cargo():
    """别把原有的 tsc / cargo 判据挤没了——补暂存是加一步，不是换掉检查。"""
    body = _ui_job_body(CI.read_text(encoding="utf-8"))
    assert "tsc --noEmit" in body
    assert "cargo check" in body
