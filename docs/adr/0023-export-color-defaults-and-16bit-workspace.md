# ADR-0023：导出色彩转换默认口径与 16-bit 工作空间（首版默认，已授权定档）

- 状态：已定档（2026-10-20，用户授权"按某默认方案推进"）
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

1. **工作空间恒为 sRGB（显示参考、8-bit）**。非 RAW 解码走 `im.convert("RGB")`（即 sRGB），
   RAW/编辑链最终也归到 sRGB 像素。因此导出到任何**非 sRGB** 目标档时，一律把最终（已调色）像素
   做 `sRGB → 目标档` 转换后再嵌档；目标为 sRGB 或 `none` 时恒等不转（默认路径逐字节不变）。
2. **`output_profile=source`** 透传源档、不额外转色（源像素与源假设一致）；无源档则明确拒，不静默不嵌。
3. **渲染意图缺省 = `relative_colorimetric` + 黑点补偿**（与 Photoshop 转配置默认一致，适合保色度的
   人像出片）。要整体改口径只改 `RENDERING_INTENT_DEFAULT` 一处；转换机制本身与意图选择无关。
   首版**不**在 UI 暴露意图选择控件（手册 P0 未要求，避免堆控件）；如后续产品要给用户选，再加注册表格。

## 决策二：16-bit 工作空间（首版模型）

首版维持**两条清晰分路**，不擅自把 float32 全链纳入首版（依据总目标"不把所有未来能力纳入首版、
不做无关重构"与用户"最小方案立即执行"偏好）：

- **交互编辑/预览/常规导出**：8-bit sRGB 工作空间（现有 shm 双缓冲 + 常驻会话架构）。
- **16-bit 位忠直通**：16-bit TIFF / RAW 母档走 `load_full(want_bits=16)` → `export_master_16bit`，
  全程真实 `uint16`，不左移补零、不静默降位（P0①，`test_decode_16bit_tiff.py` 已验往返无损与低 8 位非零）。
- **像素级编辑在 16-bit 母档上被拦截**（P1-5），而不是悄悄在 8-bit 上算完再冒充 16-bit。
  即：16-bit 直通与像素编辑首版互斥，界面对此显式禁用并说明原因，绝不留哑按钮。

统一 float32（或 16-bit）处理管线是手册建议的**后续里程碑**，属架构级改动、需按手册做误差验证，
且要 GPU 端到端取证——**不在本次默认方案范围内**。

## 后果 / 退出条件

- P1-3 与 P0① 的产品决策维度由本 ADR 定档，不再是"待拍板"；两者仍未完成的只有**端到端人眼色准 /
  全尺寸 16-bit 处理**这类需 GPU 窗口的验收，不因此 ADR 被当作"通过"。
- 若未来产品要暴露渲染意图控件或引入 float32 主链，本 ADR 被 supersede，按新判据建用例；
  不允许拿"近似能力"或"代码存在"冒名顶替验收。
- 按"验收决策状态判定规则"：本 ADR 记录的 `deferred`（float32 全链）仅对**无测试引用**的用例生效；
  已有测试引用的（16-bit 直通往返、意图恒等/转换）以自动化读数为准，本 ADR 不覆盖其结论。
