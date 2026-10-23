# 扩展影调 v1：隔离源码交付，不是运行验收

状态：SOURCE_CONNECTED_UNRUN / SOURCE_ONLY / ALL_RUNTIME_CASES_UNRUN。共享接入基线：96483d3fd5cf6b21fdf6e919b5673ea0bd749a40。
已修改共享入口并做静态源码检查；未编译 Rust，未导入产品模块，未运行测试、类型检查、程序、模型或图片渲染。不能将本文或源码存在当作 UI 可用、导出一致、视觉通过或 handbook 功能完成。

## 逐项依据

基线：`baseline_probe/AI开发资料包/功能需求验收映射.json`，7341–7464 行；`baseline_probe/manual-text.txt` 色彩调节节。
官网核对时间 2026-10-23：[PixCake 色彩调节](https://www.pixcakeai.com/guide/32455)，页面列明中间调亮度、白色、黑色、纹理、清晰度、祛雾、鲜艳度；黑白配置禁鲜艳度。未披露这些滑杆的精确范围及算法，故全部采用标明的原创 [-100,100]、默认 0；不是冒充官网数值或复刻私有算法。

| 独立控制 | LNX-REF-PC-32455-C- 后缀 | 原创数学路径 |
|---|---|---|
| 亮度 brightness | 935d133b92 | 显示亮度 0–1 内的光滑中间调 bump，黑白端点不动；不是 EV |
| 白色 whites | ef0ecc2e31 | 从 Y=.6 起平滑选择白场，高于 1 保留连续偏移，不裁 HDR |
| 黑色 blacks | b6a3a387f1 | Y=0–.35 平滑选择黑场；负值延伸连续，不偷换 shadows |
| 纹理 texture | df1b3249dd | log1p 亮度的边缘感知 1px 与 3px 带通，噪声阈门；没有全局高斯模糊替代 |
| 清晰度 clarity | 9dc1af72b2 | 独立 3px 与 12px 边缘感知亮度频带；和纹理不是同一滑杆 |
| 祛雾 dehaze | 0b1f30c7f5 | 在线性 sRGB 中估计局部暗通道与全帧中性大气光，用有下限的透射率反演/合成雾 |
| 鲜艳度 vibrance | e25d667189 | 色差相对亮度放大，饱和越高增益越弱；灰阶维持中性，不是 saturation 别名 |

所有空间半径为原图像素单位，代理明确传入 scale；细节采用分数半径插值，小于 1px 时在原信号与 1px 邻域间插值，避免缩小代理上纹理两个频带完全合并；去雾暗通道最小半径 1px。灰阶中性指不制造色偏，并非所有调节都保持灰阶亮度。纹理/清晰度在平坦画面无作用，避免额外全局对比度。数学设计保证的是有限支持，不保证未经视觉测试的完全无光晕。全零或全零蒙版精确保留原位深、负值、HDR 和 signed zero。蒙版作为最后混合权重，邻域仍从整张未遮罩源图取样，避免蒙版边缘被当作图像边界。

## 成熟方案调研与原创实现边界

- [darktable local contrast](https://docs.darktable.org/usermanual/development/en/module-reference/processing-modules/local-contrast/)：官方文档区分局部反差和全局反差，介绍局部 Laplacian/双边方案及尺度。采用这个功能设计原则，自行实现有限半径可分离双边带通；不是复制其代码或声称同质量。
- [darktable haze removal](https://docs.darktable.org/usermanual/development/en/module-reference/processing-modules/haze-removal/)：官方解释局部雾估计、漫射光去除及负向加雾，并提醒无雾画面可能出现不自然效果。本实现也单列该风险。
- [RawTherapee Vibrance](https://rawpedia.rawtherapee.com/Vibrance)：搜索索引可读，直接页面抓取返回 404。仅确认其 intelligent saturation 的设计类别，未依据不可读取的细节复制算法。

本实现不带自动肤色识别，不承诺修复失焦、真实深度估计或任何 AI 能力。雾使用中性标量大气光以避免灰阶染色；带色雾去除质量属于待验差距，不伪称恢复真实场景颜色。所有常数和区间是本产品原创选择。

## 可接入文件及交付边界

- `core/extended_tone/extended_tone.rs`：无第三方依赖 Rust 数值核心/ABI2/原生测试。
- `extended_tone_state.py`：独立 version/algorithm recipe、七参数强校验、黑白条件有效值与范围。
- `extended_tone_native.py`：固定已安装 .so/ABI；缺失立即报错，不编译、不回退 NumPy 算法。
- `extended_tone_stage.py`：RGB8/RGB16/float32，明确 CPU bridge 的 Torch float32 NCHW 路径；不默降 float64/half。
- `extended_tone_controller.py`：document fence、请求指纹/去重、可查询回执，提交及历史之后才成功。
- `extended_tone_host.py`：真实 Engine 方法适配，检查历史字段接入，失败恢复 recipe/frame/history ledger/dirty；不 monkeypatch。
- `extended_tone_project.py`：工程/历史字段捕获恢复校验、预设和批量 replace 纯准备、全帧导出；批量提交仍由现有 host 组事务负责。
- `ui/src/extendedTone`：七控件、数值输入、单项归零、启用、应用/丢弃/整组重置、黑白禁鲜艳、失联查询、不自动重发、sessionStorage 保存未决请求。

UI 草稿为显式“应用”，不伪称实时 GPU 预览。未决请求跨面板重挂/刷新保留身份；引擎重启导致回执 unknown 时锁住，不自动重发，界面提供“读取当前状态以核对”，展示当前 document、七参数及黑白值；只有当前状态仍与回读一致且用户明确确认，才放弃旧回执并解锁，不自动重发。只在同一可验证 request/document/recipe 的终态回执后宣布成功。不同照片回执不覆盖当前照片草稿。

## 已接入的共享边界（运行验收待做）

详见 `integration-map.json`。已授权并接入 Engine/Tauri/UI、历史、工程 v16、预设/批量、导出与包装；这只是源码连接事实。

- 预览在 exposure 后、曲线色阶/后续风格前插入此阶段，导出必须采用同样顺序。
- 局部细节和去雾不在每个 export tile 独立计算；本阶段只接受组装后的完整上游浮点 RGB。现通过只到 exposure-output 的全帧浮点预通路，统一运行 Rust，再把结果带完整 halo 注入正式 downstream tile 通路；并未移到 reference_stage 之后。原图上游为保证不改变现有算子而重跑两遍，耗时必须实测。
- 全帧 RGB8 导出也必须把 intermediate floating 标志置真；最后才量化。RGB16 输入在 math 边界按 65535 解码/编码；float32 不按最大像素或整图归一化、不截断 HDR。
- 全图配方可预设/批量 replace，不复制去雾估计，每张图现场重算。蒙版数学接口已支持，不表示局部选区 UI/蒙版资产保存已经接通；不得把全图 recipe 当局部工作流交付。
- 仓库没有已接入的 XMP/profile owner，本次未假造它。提供明确标为“原创模式，不是 XMP 配置文件”的 monochrome 配方字段，UI、导出快照及 Rust 最终灰阶输出共同消费该字段；鲜艳度仅禁用不清除。完整配置文件/XMP工作流仍是另一项欠账。

## 尚未验收的性能及体验风险

原生核心是安全边界清楚的 CPU 数值版本，局部滤波耗时 O(N*r)，不是实时 GPU 实现。100MP 是尺寸拒绝上限，不是已验证可承载容量；多张 f64 全帧缓存可能需要数 GB。已加可用内存一半且最高 8GiB 的保守工作集预算（256 bytes/pixel + 32MiB）、原生取消回调及导出进度轮询；预算不足明确拒绝而不降精度。仍需要真实 24MP/100MP 测量及进一步缓存/分块优化，预算上限不证明这些尺寸可用。分块优化必须复用全帧雾统计与足量 halo 后再做一致性测试。当前没有假报性能、跨缩放一致或视觉合格。


## 共享接入和并发协议

- Engine `_extended_tone` 为独立 DOC_FIELDS 字段，初始化/捕获/恢复/换图/换设备/历史/项目均保留；`lnx.extended_tone.v1` 走原有预设与批量事务，不绕开 CUBE portable 48MiB 或 compact batch 2MiB 预算。
- 工程提升 v16；所有 v15 CUBE 与 v14 hair 的前驱允许集继续保留。v15及之前不允许夹带 extended-tone 字段后默默当成受支持。
- request 必须包含 document_id、revision、唯一 request_id、完整 spec；服务按真实当前文档版本拒绝陈旧请求。reader-side 64 个有界挂起事件实现取消和最新意图取代；共享帧 publication fence 防止已取消结果发布。
- 原生 ABI2 在空间滤波行/列和像素批次检查取消，Python 将回调异常捕获再安全抛出。取消不转为部分输出成功。历史失败恢复配方、帧、undo/redo/dirty；回滚失败标记 outcome_unknown/requires_reload。
- Tauri 回执绑定 engine epoch 并保留终态；重启返回 unknown，不重发。只读 readback 回执消费后释放，修改身份保留至应用退出，4096 上限明确拒绝。
- 内建/自定义 LUT 的 `_lut`、字节资源、强度、运算位置、颜色合同完全不改。所有现有其他效果继续参与上下游链。原创黑白输出在所有颜色效果之后，由 Rust 单独灰阶化，与完整 profile/XMP 功能区分。

验收必须包含：组合 LUT/曲线/局部调色/换天/几何的预览和 RGB16 导出逐项比对、每块接缝、旧 v15 含 CUBE/旧 v14 hair 工程、批量撤销与取消/重启/UI反复操作。尚无任一运行或视觉合格证据。
