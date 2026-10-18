#!/usr/bin/env python3
"""把《P0参数注册表.json》里 19 条「待决策」定案，生成冻结版注册表。

为什么是生成器而不是手写一份 JSON：注册表的身份规则写着 `operation_id + parameter_key`
唯一、稳定 ID 不得按展示文本改名。手抄 36 条一定会在某个下划线或某条 v1 后缀上出错，
而那种错在 UI 上表现为「这条参数看起来接了但其实接错键"，测试也不会响。生成器只做一件事：
从原件读出 36 条骨架，按本文件里的决策表填掉 null，其余字段原样带过去。

原件在本仓库之外（总工给的资料包）。这里把它当**输入**而不是当**权威拷贝**：输出里记下
原件的 sha256 与来源路径，这样日后原件变了、冻结版没跟着重生成，对账能发现。

决策本身记在 DECISIONS 里，每条带一句理由；理由不在这里长篇大论，长篇在
docs/adr/0003-p0-parameter-decisions-frozen.md。

用法：
    python3 tools/freeze-p0-registry.py [--source <P0参数注册表.json>]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------- 决策表
# 键 = (operation_id, parameter_key)。只覆盖原件里 range_status/neutral_status 未定的项。
# 每条都必须带 reason：没有理由的数值就是拍脑袋，后面没人敢改也没人记得能不能改。
DECISIONS: dict[tuple[str, str], dict] = {
    ("lnx.exposure.v1", "ev"): dict(
        range={"min": -5.0, "max": 5.0, "step": 0.01}, neutral=0.0,
        reason="±5 EV、步进 0.01。暗房主流上限（Lightroom 是 ±5，Capture One 同量级）；"
               "0.01 是因为导出比对要能分辨 1/100 EV，而更细的步进在 16-bit 上跨不过一个可辨台阶。"),
    ("lnx.white_balance.v1", "temperature_shift"): dict(
        range={"min": -2000.0, "max": 2000.0, "step": 25.0}, neutral=0.0, unit="kelvin_offset",
        reason="开尔文**偏移**而不是绝对值：绝对值要拿源 as-shot 色温做基准，RAW 里没有 as-shot "
               "时（合成/无 EXIF）绝对值语义直接塌掉；偏移对任何源都成立。2000 K 上限覆盖白炽灯到"
               "阴影的全行程，25 K 步进是工程上不会误读的粒度。"),
    ("lnx.white_balance.v1", "tint_shift"): dict(
        range={"min": -1.0, "max": 1.0, "step": 0.01}, neutral=0.0, unit="normalized",
        reason="绿–洋红是色温之外的正交轴，没有物理单位；用归一 [-1,1] 而不是编一个 'tint 单位'。"
               "引擎侧它本来就落到对 G 通道的乘性增益，归一化与实现之间没有换算层就没有谎。"),
    ("lnx.crop.v1", "rect_normalized"): dict(
        range={"per_coordinate_min": 0.0, "per_coordinate_max": 1.0,
               "constraints": "x0<x1;y0<y1"}, neutral=[0.0, 0.0, 1.0, 1.0],
        reason="原件已给出逐坐标 [0,1] 与 x0<x1;y0<y1，中性 [0,0,1,1] 就是全画幅——这条不是"
               "重新决策，是把原件的空值语义坐实：中性=不裁剪=逐字节等同原图（除方向规范化）。"),
    ("lnx.crop.v1", "rotation_degrees"): dict(
        range={"min": -180.0, "max": 180.0, "step": 0.1}, neutral=0.0, unit="degree",
        reason="±180 是单值覆盖全圆的唯一自然区间（±90 表达不了倒置，0..360 让 0 与 360 两个值"
               "表示同一件事、破坏中性唯一性）。0.1° 与主流修图工具的微调粒度一致。"),
    ("lnx.mask.v1", "analysis_enabled"): dict(neutral=False,
        reason="默认关：自动分析是一条会改变画面的推理路径，开箱默认关才不会让"
               "「我什么都没调但图变了」发生。"),
    ("lnx.mask.v1", "overlay_visible"): dict(neutral=False,
        reason="蒙版叠加是诊断视图，默认关。"),
    ("lnx.mask.v1", "feather"): dict(
        range={"min": 0.0, "max": 256.0, "step": 1.0}, neutral=0.0, unit="source_pixels",
        reason="单位定成**源像素**而不是归一比例：256 在 443 px 的代理帧上会溢出，而像素值"
               "在代理/全分辨率之间是有明确换算的（按长边比例），归一比例反而让「同一条目在两种"
               "分辨率下羽化宽度不同」这种错无法被发现。上限 256 覆盖半张代理脸的过渡带。"
               "中性 0 = 硬边，必须是可复现的硬边，否则羽化开关的对拍就没有 0 位可退。"),
    ("lnx.blemish.v1", "enabled"): dict(neutral=False, reason="同上：不改画面的默认。"),
    ("lnx.blemish.v1", "strength"): dict(
        range={"min": 0.0, "max": 1.0, "step": 0.01}, neutral=0.0, unit="normalized",
        reason="归一 [0,1]。祛瑕强度是「这个算法走多远」，不是任何物理量；0 必须是精确恒等，"
               "这条是 P0-BLEMISH-NEUTRAL 用例的判据本身。"),
    ("lnx.blemish.v1", "protect_identity_marks"): dict(neutral=True,
        reason="**默认开**。痣、疤、纹身是身份特征；祛瑕算法默认把它们当瑕疵抹掉是产品级事故，"
               "而且用户通常看不出来（少了一颗痣不会有人报警）。保守一侧的默认值在这里比"
               "「效果更强」重要。"),
    ("lnx.skin.v1", "enabled"): dict(neutral=False, reason="同 enabled 一族：默认不改画面。"),
    ("lnx.skin.v1", "strength"): dict(
        range={"min": 0.0, "max": 1.0, "step": 0.01}, neutral=0.0, unit="normalized",
        reason="与 blemish.strength 同口径，两个「强度」必须同一个含义，否则批量套用时会出一个"
               "0.5 是半力、另一个 0.5 是别的什么。"),
    ("lnx.export.v1", "format"): dict(
        enum=["jpeg", "tiff"], neutral="jpeg",
        reason="枚举是原件给的（jpeg/tiff），本条只定中性：jpeg 是「拖进来就能分享」的默认出口。"
               "16-bit 直通只在 tiff 下承诺，jpeg 8-bit 是格式本身的性质，不是降级。"),
    ("lnx.export.v1", "jpeg_quality"): dict(
        range={"min": 1, "max": 100, "step": 1}, neutral=92, unit="percent",
        reason="92：libjpeg 惯例的「视觉无损」档，也是主流导出对话框的默认。定这个数是为了"
               "P0 用例有可复现基准，不是为了最优压缩。"),
    ("lnx.export.v1", "tiff_compression"): dict(
        enum=["none", "deflate", "lzw"], neutral="deflate",
        reason="全部无损候选（TIFF 里没有有损的合理位置）。默认 deflate：Pillow 与主流读取端"
               "都支持、压缩率优于 none。lzw 保留是因为 TIFF 6.0 里它是原生公民，某些管线只认它。"),
    ("lnx.export.v1", "output_profile"): dict(
        enum=["source", "srgb", "adobergb", "display_p3"], neutral="srgb",
        reason="默认 srgb：接收方最广、且嵌入 ICC 后不会让浏览器把它读成「过饱和」。"
               "source 表示不转换只透传源描述文件——这一档必须存在，否则高位深工作流"
               "被迫过一次色域转换。"),
    ("lnx.export.v1", "metadata_include_gps"): dict(neutral=False,
        reason="原件已给 False，坐实它：色彩/隐私用例 COLOR-003 的判据就是默认不外泄位置。"),
    ("lnx.batch.v1", "module_scope"): dict(neutral=[],
        range={"min_items": 1, "constraints": "非空才能 preflight 通过"},
        reason="中性是空集，且**空集不允许通过 preflight**。原件写 neutral=[]，但如果把空集"
               "解释成「全部模块」，就等于批量默认套用所有操作——那正是手册警告的越界。"
               "所以空集只能是不完整配置。"),
    ("lnx.batch.v1", "conflict_policy"): dict(
        enum=["skip_and_report", "recheck"], neutral="skip_and_report",
        reason="枚举里两个都是**不覆盖**：没有 overwrite 选项不是遗漏，是 EXPORT-001 的"
               "「无无提示覆盖」要求的直接体现。默认 skip_and_report——跳过并报告比"
               "回头再查一遍更容易在批量跑完后被读到。"),
}

# D-P0-02：人像类操作的启用范围（enable_condition 里那条「单脸及 D-P0-02 支持范围"）。
SCOPE_SINGLE_FACE = {
    "decision": "D-P0-02",
    "rule": "target_scope=single_face 的操作，仅在恰好检测到 1 张可用人脸时启用；"
            "检测到 0 张或多于一张时，控件必须显式禁用并说明「需要且仅需要一张可用人脸」。",
    "reason": "多人照片上「对这张脸做的改动 applied 到全部脸」是手册 SCOPE-001 定义的超范围"
              "行为。宁可少给一次自动效果，也不能替别人改脸。",
    "usable_face_criteria": "backend ∈ {mediapipe} 且 landmarks 形状 (478,3) 且 "
                            "face.geometry_warning(box) 为 False——synthetic 的网格占位几何"
                            "不算可用人脸（它按脸形语义取点会搬到无关位置且画面看不出错）。",
}

# 质量阈值（quality_threshold_policy 要求「未冻结阈值前不得宣称通过"）。
QUALITY_THRESHOLDS = {
    "frozen_at": "由本生成器随版本冻结；改动必须走 ADR",
    "identity": {
        "definition": "中性值下输出必须与参考渲染逐字节相同（16-bit 主链，逐通道 uint16 比较）",
        "tolerance": 0,
        "note": "0 容差不适用于含色彩管理的链路：那条走下面 color_management 的色差判据。",
    },
    "illegal_input": {
        "definition": "越界/NaN/Inf/类型错误一律拒绝并回明确原因，不夹取、不静默改值",
        "must_not": ["clamp silently", "coerce to 0", "execute external code"],
    },
    "out_of_scope_change": {
        "definition": "蒙版/目标外的变化不得超过批准边缘",
        "edge_pixels_max": 2,
        "channel_delta_beyond_edge": 1,   # 16-bit 下 1 LSB；比这大就是漏出界
        "reason": "2 px 是肤色定向层羽化（[1,2,1]/4，支撑半径 2 px）的既有事实，"
                  "把它写成阈值而不是假装它是 0。",
    },
    "color_management": {
        "definition": "参考色块在输出上的 ΔE00 误差",
        "delta_e00_max": 2.0,
        "bit_depth_guard": "16-bit 主链不得静默降 8-bit：导出侧必须自报位深读数并与请求一致",
    },
    "source_readonly": {
        "definition": "全部源文件 sha256 与字节数在处理前后一致；导出目标路径等于输入路径即拒绝",
    },
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=os.path.expanduser(
        "~/文档/岫图软件/AI开发资料包/P0参数注册表.json"))
    ap.add_argument("--out", default=os.path.join(REPO, "docs", "p0", "p0-registry-frozen.json"))
    ap.add_argument("--ui-copy", default=os.path.join(REPO, "ui", "src", "p0-registry.json"))
    a = ap.parse_args()

    if not os.path.isfile(a.source):
        print(f"× 找不到原件：{a.source}", file=sys.stderr)
        return 1
    raw = open(a.source, "rb").read()
    src = json.loads(raw)
    src_sha = hashlib.sha256(raw).hexdigest()

    entries = []
    for e in src["entries"]:
        key = (e["operation_id"], e["parameter_key"])
        dec = DECISIONS.get(key, {})
        out = {
            "requirement_id": e["requirement_id"],
            "operation_id": e["operation_id"],
            "parameter_key": e["parameter_key"],
            "type": e["type"],
            "unit": dec.get("unit", e["unit"]),
            "neutral": dec.get("neutral", e["neutral"]),
            "range": dec.get("range", e["range"]),
            "enum": dec.get("enum", e["enum"]),
            "target_scope": e["target_scope"],
            "enable_condition": e["enable_condition"],
            "source_category": e["source_category"],
            "official_source_urls": e["official_source_urls"],
            "reason": dec.get("reason"),
        }
        # 冻结版不许留该类型本该有的东西：但**按类型要求**，而不是一律要求非空。
        # boolean 的 range 为 null 是合法的（布尔没有量程），把它当“未定案”拦下是
        # 判据太粗；反过来 enum 必须有枚举、number 必须有量程，那才是真不变量。
        t = out["type"]
        if t != "action":
            missing = []
            if out["neutral"] is None:
                missing.append("neutral")
            if t == "number" and out["range"] is None and out["enum"] is None:
                missing.append("range")
            if t == "enum" and not out["enum"]:
                missing.append("enum")
            if missing:
                print(f"× {key} 的 {missing} 仍未定案（type={t}）——生成器拒绝产出假冻结",
                      file=sys.stderr)
                return 1
        if out["reason"] is None and t != "action":
            print(f"× {key} 缺理由", file=sys.stderr)
            return 1
        entries.append(out)

    frozen = {
        "schema_version": src["schema_version"],
        "derived_from": "P0参数注册表.json",
        "source_sha256": src_sha,
        "null_semantics": src["null_semantics"],
        "identity_rule": src["identity_rule"],
        "frozen_by": "tools/freeze-p0-registry.py",
        "decisions_rationale_doc": "docs/adr/0003-p0-parameter-decisions-frozen.md",
        "scope_single_face": SCOPE_SINGLE_FACE,
        "quality_thresholds": QUALITY_THRESHOLDS,
        "entries": entries,
    }

    for path in (a.out, a.ui_copy):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(frozen, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"✓ {path}  ({len(entries)} 条，源 sha256 {src_sha[:16]}…)")

    # 两份必须逐字节相同，否则 UI 读的与审计读的会分家。
    h1 = hashlib.sha256(open(a.out, "rb").read()).hexdigest()
    h2 = hashlib.sha256(open(a.ui_copy, "rb").read()).hexdigest()
    if h1 != h2:
        print("× 冻结版与 UI 副本不一致", file=sys.stderr)
        return 1
    print("✓ 两份逐字节一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
