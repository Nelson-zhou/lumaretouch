# ADR-0003：冻结 P0 参数注册表的 19 条待决项与质量阈值

状态：已采纳（2026-10-18）。依据总工的全权自主裁决授权；原件 `P0参数注册表.json`
（sha256 b8726308161da098…）里 19 条 `range_status/neutral_status` 未定，13 个 operation
的 UI 与《开发验收用例》的 P0-* 用例都卡在这上面——没有确定量程就没有滑块，没有冻结阈值
就不许宣称任何用例通过（原件的 quality_threshold_policy 自己写的）。

## 冻结方式

`tools/freeze-p0-registry.py` 从原件读 36 条骨架、按决策表填 null，产出
`docs/p0/p0-registry-frozen.json` 与逐字节相同的 `ui/src/p0-registry.json`。
不手抄的理由：身份规则是 `operation_id+parameter_key` 唯一，手抄错位会表现为
「参数看着接了其实接错键」，测试不会响。生成器带三条硬校验（缺 neutral / 缺该类型
该有的 range|enum / 缺 reason 就拒绝产出），拒绝产出「假冻结」。

## 关键决策与理由（数值全在冻结版里，这里只记非显然的几条）

- **白平衡用 kelvin_offset 而不是绝对色温**：绝对值要拿源 as-shot 色温做基准，而无 EXIF 的
  源（合成、部分 DNG）根本没有 as-shot，绝对语义当场塌掉。偏移对任何源成立。
  tint 是色温之外的正交轴、无物理单位，用归一 [-1,1]，不编造 "tint 单位"。
- **feather 单位 = 源像素**，不是归一比例：归一比例会让「同一条目在代理帧与全分辨率下
  羽化宽度不同」这类错无法被发现；像素值在两种分辨率之间有明确的长边比例换算。
- **rotation ±180**：±90 表达不了倒置；0..360 让 0 与 360 表示同一件事，破坏中性唯一性。
- **protect_identity_marks 默认 True**：痣/疤/纹身是身份特征，祛瑕默认把它们当瑕疵抹掉是
  产品级事故，而且用户看不出来。宁可效果弱一点。
- **batch.module_scope 的空集不允许通过 preflight**：原件 neutral=[]，若解释成「全部模块」
  就等于批量默认套用所有操作——正是手册警告的越界。
- **conflict_policy 枚举里没有 overwrite 不是遗漏**：EXPORT-001 要求「无无提示覆盖」，
  两个候选（skip_and_report / recheck）都是不覆盖，默认 skip_and_report。
- **D-P0-02 单脸范围**：target_scope=single_face 的操作仅在恰好 1 张可用人脸时启用；
  0 张或多张一律显式禁用并说明原因。「可用人脸」要求 backend=mediapipe 且 (478,3) 且
  geometry_warning False——synthetic 的网格占位几何按脸形取点会搬到无关位置且画面看不出错。

## 质量阈值（用例的前置）

中性=**逐字节恒等**（16-bit 主链，容差 0）；非法输入必须拒绝、不得夹取或改值；
蒙版/目标外变化 ≤ 2 px 且界外 Δ ≤ 1（16-bit LSB）——2 px 不是保守数字，是肤色定向层
羽化 [1,2,1]/4 支撑半径的既有事实，把它写成阈值而不是假装它是 0；色彩管理链走
ΔE00 ≤ 2.0 并自报位深读数，不许静默降 8-bit。

## 被否掉的方案

- 沿用官网数值：`official_parameter_value` 19 条全为 None，官网根本没给。
- 留 null 让 UI 自己决定默认：那会把「引擎口径」散落成十几个前端字面量。
- 手改一份 JSON 当冻结版：见上，错位不可测。
