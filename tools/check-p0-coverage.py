#!/usr/bin/env python3
"""P0 注册表面板覆盖门禁：UI 必须把冻结的 36 条**逐条**落到一个格子上。

为什么要单独立一条：手册与 DoD 要求"右侧精修面板严格依照《P0参数注册表.json》
完整实现分栏；未接通功能显式禁用并说明原因，绝不留无响应控件"。这句话光靠注释
保证不了——漏一格的表现是"界面上根本没有这个参数"，比留个哑按钮更难发现。
这里查四件事，任一不过就红：

① 注册表里每一格都在 `ui/src/p0.ts` 的 WIRING 里登记（不多不少）；
② 每一格的 section 是面板六个分栏之一（不许出现"登记了但哪一栏都不在"）；
③ `blocked: true` 的格子必须带 `why_not`，且中英两段拼起来够说清一件事（不是"暂无"）；
④ 反向门禁（这一条自己验自己）：拿一份"少登记一格"的 p0.ts 副本来跑，必须响。
   不跑的反向门禁等于没有——本仓的名单漂移事故都是守卫只写在注释里那一形。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REG = REPO / "ui" / "src" / "p0-registry.json"
P0TS = REPO / "ui" / "src" / "p0.ts"
SECTIONS = {"skin", "face", "tone", "local", "crop", "output"}


def bindings(src: str) -> dict[str, str]:
    """从 p0.ts 里把 WIRING 的每一项按大括号配对切出来（不引 JS 解析器：
    这里只查"登记没登记、话说没说全"，不解释语义）。"""
    body = src[src.index("export const WIRING"):]
    out: dict[str, str] = {}
    for m in re.finditer(r'^  "(lnx\.[a-z_]+\.v1\.[a-z_]+)": \{', body, re.M):
        i = m.end() - 1                      # 停在 '{' 上
        depth = 0
        for j in range(i, len(body)):
            if body[j] == "{":
                depth += 1
            elif body[j] == "}":
                depth -= 1
                if depth == 0:
                    out[m.group(1)] = body[i:j + 1]
                    break
        else:
            raise SystemExit(f"× {m.group(1)} 的绑定块没闭合（p0.ts 结构坏了）")
    return out


def audit(reg_text: str, p0_text: str, quiet: bool = False) -> int:
    """返回不通过的项目数。quiet 给反向门禁用：它只关心"响没响"。"""

    def say(msg: str) -> None:
        if not quiet:
            print(msg)

    entries = json.loads(reg_text)["entries"]
    want = {f"{e['operation_id']}.{e['parameter_key']}" for e in entries}
    got = bindings(p0_text)
    fail = 0

    missing = sorted(want - set(got))
    extra = sorted(set(got) - want)
    if missing:
        say(f"× 注册表有 {len(missing)} 格没在面板上登记：{missing}")
        fail += 1
    else:
        say(f"✓ 注册表 {len(want)} 格全部登记在 WIRING 里")
    if extra:
        say(f"× WIRING 里有 {len(extra)} 格不在注册表（注册表是冻结件，不许自己加）：{extra}")
        fail += 1

    blocked = 0
    for key, blk in sorted(got.items()):
        sec = re.search(r'section: "([a-z]+)"', blk)
        if not sec or sec.group(1) not in SECTIONS:
            say(f"× {key} 的 section 不在六个分栏里：{sec.group(1) if sec else '（缺）'}")
            fail += 1
        if "blocked: true" not in blk:
            continue
        blocked += 1
        why = re.search(r"why_not: \[(.*?)\],\n", blk, re.S)
        if not why:
            say(f"× {key} 声明禁用却没写 why_not（DoD 要求禁用必须带原因）")
            fail += 1
            continue
        # 一段中文在源码里是拆成相邻字面量写的，必须拼回一句再看长度：
        # 按片段判会把"说得很长但分了三行"误判成"理由太短"
        parts = re.findall(r'"((?:[^"\\]|\\.)*)"', why.group(1))
        joined = "".join(parts)
        if len(parts) < 2:
            say(f"× {key} 的 why_not 少于中英两段")
            fail += 1
        if len(joined) < 60:
            say(f"× {key} 的 why_not 拼起来只有 {len(joined)} 字，不像能复查的理由")
            fail += 1
    say(f"✓ 显式禁用并带原因的格子：{blocked} 格（其余 {len(got) - blocked} 格接进了命令面）")

    secs = set(re.findall(r'section: "([a-z]+)"', p0_text))
    if secs != SECTIONS:
        say(f"× 面板实际用到的分栏与预期的六个不一致：{sorted(secs)}")
        fail += 1
    else:
        say("✓ 六个分栏都在用上（质感/面部/色调/局部/裁剪/输出）")
    return fail


def main() -> int:
    reg = REG.read_text(encoding="utf-8")
    p0 = P0TS.read_text(encoding="utf-8")
    rc = audit(reg, p0)
    if rc:
        print(f"× P0 面板覆盖不过（{rc} 项）")
        return 1
    # 反向门禁：删掉一格绑定，这条必须响。响不了就是这条门禁在假装工作
    drop = next(iter(bindings(p0)))
    probe = p0.replace(f'  "{drop}": {{', '  "_dropped_probe_": {', 1)
    if probe == p0:
        print("× 反向门禁没能构造出来（WIRING 的写法变了，脚本没跟上）")
        return 1
    if audit(reg, probe, quiet=True) == 0:
        print(f"× 反向门禁没响：删掉 {drop} 的绑定之后仍然全过——这条检查是假的")
        return 1
    print(f"✓ 反向门禁有效：删掉 {drop} 的绑定立刻响")
    return 0


if __name__ == "__main__":
    sys.exit(main())
