"""P2-6：check-tests-runtime.sh 解析 "N skipped" 必须取完整数字，不能只取末位。

缺陷现场：旧写法 `sed -n 's/.*\\([0-9]\\+\\) skipped.*/\\1/p'` 里 `.*` 是贪婪的，会先把
多位数几乎吃光、只留最后一位给捕获组——"384 passed, 247 skipped" 被解析成 "7"。而这个数
正是要和 max_skips 比大小来拦"没 GPU 的那份绿"（skip 太多=大量用例没跑）：247 被读成 7，
阈值判据直接失效，装机件第一次 load_image 就 KeyError 那种事故又能在一片绿勾里溜过去。

纯 CPU、无副作用：行为层跑真实的提取管道，静态层钉住脚本用的是对的写法。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "packaging" / "check-tests-runtime.sh"

NEW_PIPELINE = "printf '%s' \"$1\" | grep -oE '[0-9]+ skipped' | head -1 | grep -oE '[0-9]+'"
OLD_SED = "printf '%s' \"$1\" | sed -n 's/.*\\([0-9]\\+\\) skipped.*/\\1/p'"


def _extract(cmd: str, summary: str) -> str:
    # 用位置参数把 summary 传进 $1，避免引号嵌套
    r = subprocess.run(["bash", "-c", cmd, "bash", summary], capture_output=True, text=True)
    return r.stdout.strip()


def test_new_pipeline_grabs_full_multidigit():
    """247 / 1000 这类多位数必须整串取到。"""
    assert _extract(NEW_PIPELINE, "384 passed, 247 skipped in 5.2s") == "247"
    assert _extract(NEW_PIPELINE, "1000 passed, 8 skipped") == "8"
    assert _extract(NEW_PIPELINE, "2 failed, 964 passed, 8 skipped") == "8"


def test_old_sed_takes_only_last_digit():
    """反向对照：旧写法确实只取末位——这条钉住"我们修的是真 bug"，不是恒绿空断言。"""
    assert _extract(OLD_SED, "384 passed, 247 skipped in 5.2s") == "7"


def test_script_uses_correct_extraction():
    """静态门：脚本里取 skips 的那行不许再用贪婪 `.*\\([0-9]\\+\\) skipped`，得用整串提取。"""
    s = SCRIPT.read_text(encoding="utf-8")
    # 取 skips 的那一行
    line = next((ln for ln in s.splitlines() if ln.lstrip().startswith("skips=")), "")
    assert line, "脚本里找不到 skips= 提取行"
    assert "grep -oE '[0-9]+ skipped'" in line, f"skips 提取没改成整串写法：{line!r}"
    assert ".*\\([0-9]\\+\\) skipped" not in line, f"仍留着会取末位的贪婪 sed：{line!r}"
