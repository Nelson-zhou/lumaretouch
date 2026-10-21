# ADR-0023：导出色彩转换与高位深工作空间（现状与待实现要求）

- 状态：2026-10-20 修订。色彩转换策略保留；原“首版仅直通、float32延期”的范围裁减不再作为开发/验收依据。按用户最新要求，两份原始手册逐项落实，不为赶工删减功能体验。
- 关联：F03/P1-3（`export._convert_srgb_to_profile`、`RENDERING_INTENT_DEFAULT`）；
  P0 首版项①（16-bit 处理与导出链路）；P1-5（16-bit 母档像素级编辑拦截 `test_master16_blockers`）；
  ADR-0004（导出 P0 契约）；ADR-0022（无 GPU 运行路径）。
- 来源（官方/成熟项目实际做法，非凭记忆）：
  - ICC v4 / littleCMS 渲染意图编码：perceptual=0、relative_colorimetric=1、saturation=2、
    absolute_colorimetric=3；黑点补偿 flag=8192（本机 Pillow 12.3 `ImageCms` 实测一致）。
  - Adobe Photoshop「编辑→转换为配置文件」默认渲染意图为 Relative Colorimetric 且默认开启
    Black Point Compensation；darktable 显示参考默认走 Perceptual。二者都是显示参考照片工作流。
    https://helpx.adobe.com/photoshop/using/converting-to-and-from-color-spaces.html
  - 《Linux 开源人像修图产品指导手册》§7：16-bit TIFF 是交换/交付格式，内部建议 float32 基准，
    GPU fp16 仅在误差验证后开启。

## 决策一：导出的源/已调色策略与渲染意图

1. **工作空间为 sRGB（显示参考）**。非 RAW 解码先按嵌入 ICC 显式转换到 sRGB（`im.convert("RGB")` 本身不是颜色管理），
   RAW/编辑链最终也归到 sRGB 像素。因此导出到任何**非 sRGB** 目标档时，一律把最终（已调色）像素
   做 `sRGB → 目标档` 转换后再嵌档；目标为 sRGB 或 `none` 时恒等不转（默认路径逐字节不变）。
2. **`output_profile=source`** 保留源档作为输出目标，将已归一到工作 sRGB 的最终像素转换回该目标后嵌档；不能仅贴源档。无源档则明确拒，不静默不嵌。输入端纠正及依据见 `docs/development/direct-implementation.md`。
3. **渲染意图缺省 = `relative_colorimetric` + 黑点补偿**（与 Photoshop 转配置默认一致，适合保色度的
   人像出片）。要整体改口径只改 `RENDERING_INTENT_DEFAULT` 一处；转换机制本身与意图选择无关。
   首版**不**在 UI 暴露意图选择控件（手册 P0 未要求，避免堆控件）；如后续产品要给用户选，再加注册表格。

## 决策二：高位深要求保留，当前实现不得冒充完成

《Linux开源人像修图产品指导手册》要求的高位深处理目标保留，内部float32基准、16-bit交换/输出及误差验证仍须实现。此前将主链定为“后续里程碑、默认范围外”的措辞已失效，不能据此跳过、关闭或标记豁免。

当前代码事实（不是最终产品取舍）：

- 交互输入、共享显示帧与常规导出仍含8-bit量化路径；算子内部使用float32不等于端到端保留高位深输入。
- 2026-10-21本地候选新增真实RGB16输入→float32或更高精度编辑→RGB16颜色转换/输出，逐图配方协议已接线；中性图保留精确直通。专项测试通过，完整回归与发布尚待完成。
- RGB8显示代理不得成为RGB16编辑导出的输入。宽色域/HDR、全尺寸内存预算、GPU精度及更广真实照片组合仍未完成，不能据此关闭完整要求。

## 必须达到的退出条件

1. 真正高位深输入贯穿编辑与输出，中间不得经uint8量化；显示代理可以单独量化，但不能反过来作为出片源。
2. 源/工作/输出色彩空间和传递函数显式一致，不能仅贴ICC标签，也不能用8-bit颜色转换绕行后宣称高位深。
3. 编辑、掩膜、形变、修补和调色组合在全尺寸及切块输出上完成误差、接缝和中性恒等验证。
4. CPU路径也必须验证，GPU性能与实机视觉分别取证；“无GPU”不能被用于跳过可在CPU实施的正确性工作。
5. 未达到的条目在追踪表保留为未完成，不因为有直通测试或本ADR而变为通过。

色彩转换默认意图与黑点补偿的决定不受上述范围纠正影响；本ADR描述的当前限制仍应在UI如实告知，直到对应能力通过验收，而非隐藏限制或承诺已支持。
