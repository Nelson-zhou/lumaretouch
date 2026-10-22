# PC-32476 换天空：实现与验收边界

状态：显式标记版本的代码与共享调用点已接通；未运行、未构建、未验收。自动天空/水面语义提议仍是明确的实现缺口，不把手动标记宣称为自动检测。本文不能作为通过证据。

## 来源与许可证

- 需求基线：《Linux 开源人像修图产品指导手册》“换天空”与 AI 开发资料包 PC-32476 的 20 个控件/分组条目。
- 原始官方地址：<https://www.pixcakeai.com/guide/32476>。2026-10-22 的网页读取不可用，不能把不可读页面当新证据。
- 当前官方“背景”指南：<https://www.pixcakeai.com/guide/177625>，确认自定义素材、天空位置与透明度、人景氛围、-100 还原以及有水面才反射。
- 官方换天空指南：<https://wiki.pixcakeai.com/guide/9817.html>，确认色温/色调/饱和/亮度/虚化、不透明度、人物/景物分离、水面与恢复笔。
- 成熟算子：OpenCV 4.x `remap` / `GaussianBlur` / `distanceTransform` 的官方文档：
  <https://docs.opencv.org/4.x/da/d54/group__imgproc__transform.html>、
  <https://docs.opencv.org/4.x/d4/d86/group__imgproc__filter.html>、
  <https://docs.opencv.org/4.x/d7/d1b/group__imgproc__misc.html>。
- OpenCV 自 4.5.0 为 Apache-2.0：<https://opencv.org/license/>。复用项目现有 NumPy、Pillow、PyTorch、LittleCMS 和 Rust LMR2。没有引入新的模型、模型下载器、网络执行或素材包。
- 没有许可证已确认的官方商业素材授权，因此只接受用户自有/有权使用的本地图片。路径是定位方式，SHA-256 才是内容身份。项目不假定可重新分发素材。

自动语义识别缺口明确保留：当前没有可信、已验收的自动天空/水面检测。UI 明示手动标记，人物蒙版的反选从不被叫作天空。现有 SAM2 是提示式选区，不是天空/水面语义分类器；本提交不下载或运行它，也不宣称自动检测质量。

## 控件到实现

全部 UI 控件有 `data-control-id`，分组保留原始 ID。只有原文明确的 -100 与默认 0 被视为已知语义；其余范围是本项目自己的可见、可持久化尺度，不冒称官方未公开的数值。

| PC-32476-C 后缀 | 控件 | 实现 |
| --- | --- | --- |
| 1f5b94eaeb | 天空调整 | 本地素材绑定与独立参数组 |
| 6b87bf7388 / 679dae32e6 | 垂直 / 水平位置 | 全幅归一偏移，瓦片不重置坐标 |
| 62a11b207d / 48ec19a95a | 水平翻转 / 角度 | 反向仿射采样，另提供素材大小避免露空 |
| 703d8271d5 / 999e4bf2f2 | 边缘 / 渐变 | Rust 区域栅格后，全幅有符号距离边缘移动及 Gaussian 软过渡 |
| 106048a96f / dcca1d21c9 | 色温 / 色调 | 线性 RGB 通道增益，明确是强度尺度而非伪 Kelvin |
| 482ce42caa / 329a11842f | 饱和 / 亮度 | 线性亮度分离饱和及 ±2 EV 映射 |
| 4a4a602101 / d57398ba6c | 虚化 / 不透明度 | 素材空间 Gaussian；线性光 alpha |
| 2db62a27f5 | 人景调整 | 明确人物标记或“照片中无人”后启用 |
| aef60501f4 / 0b58cf183b | 景物 / 人物色彩 | 取新天空全局色相环境，保留局部线性亮度的独立色调映射。-100 为 0 映射，0 为基础映射，正向增强 |
| 47bf45fbb5 | 水面调整 | 明确水面标记及地平线，未标记时控件不可用 |
| 98eade3987 / 3da6103009 | 景物反射 / 水效虚化 | 关于明确地平线镜像新天空，只作用标记水面，独立各向异性 Gaussian |
| c68a287a5a | 恢复笔 | 独立笔迹只衰减天空替换、天空人景映射和反射；不恢复整张原图 |

## 坐标、颜色与层顺序

1. 左侧定位是生产者持有的原始源照片、完整未裁剪/未旋转/未自动变形画布。PNG 仅显示，绑定原文件 SHA、完整源尺寸、文档 ID、配方修订和当前像素对象。完成显示确认后才接收区域笔迹。客户端不从效果图反推源图坐标。
2. 右侧是同一生产管线真实输出，含既有修补、影棚清理、自动美型、调色、天空、最终手动液化和几何。右侧不是用 CSS 混色伪造的效果。
3. 手动源归一笔迹由现有 Rust LMR2 在实际分辨率栅格化。消费天空效果时将区域、天空/反射采样、显式地平线下水面与素材覆盖有效性打包，通过 `align_source_grade_mask` 一次对齐真实自动形变；最终手动液化和构图仍在其后。不会只移动蒙版而让反射内容停在另一坐标。
4. 层顺序：源修补/光影/磨皮/衣物/影棚清理 → 自动形变及人物增强 → 调色及独立局部调色 → 换天空 → 旧式整体换背景 → 手动液化 → 全局镜头/透视 → 现有裁剪/旋转构图。
5. 允许影棚地面清理与天空共存：前者改变天空前的场景输入，天空恢复笔恢复到这个输入，不撤回影棚效果。若用户把同一区域明确标成天空，其上游清理会被天空替换，这是图层顺序，不是静默忽略。
6. 旧式整体换背景和天空替换互斥，双向启用检查和导出检查必须可见阻止，防止后面的整体背景无声覆盖天空。
7. 素材解码保留真实 RGB8/RGB16，嵌入 ICC 通过现有输入转换和 LittleCMS 转到 encoded sRGB。素材变换、Gaussian 和融合以浮点完成。RGB16 图像不进入 RGB8 预览再导出。
8. 高位深 PNG 的现有解码链不能保证真实 RGB16，所以显式要求转成 RGB16 TIFF，而不是把 Pillow RGB8 当作高精度。普通 PNG、JPEG、BMP、RGB TIFF 支持。
9. 水面必须真实标记且位于用户设定地平线下；不默认下半幅为水，不从人像背景推断水。水面采样、天空仿射都使用全图坐标，导出瓦片原点不能改变效果。

## 事务、失败与取消

- 用户在会话中可连续画笔与拖参数；仅一个异步准备任务加一个可替换最新草稿。被取消的准备不发布。主序列渲染，最终准确显示的候选才可提交。
- 区域/参数变化都是草稿，草稿独立撤销/重做。点击“应用”一次仅生成一条全局历史，不在拖动中写上百次历史。
- 本地宿主同时绑定 engine epoch、文档、session、preview，校验真实图像与配方修订，要求显示确认后才能单次兑换。发送失败/超时只查询原 request ID，不重发。
- 关闭、Esc、切图、重开、外部编辑和释放执行器会取消未应用内容。已经发送的请求保持结果未确认状态并提供原操作查询，不伪报取消成功。
- 原图/素材变更、素材缺失、全图/空天空、空人物、错误水面与地平线、素材露空、超内存预算、缺依赖都可见失败。无任何全图蒙版兜底、反选人像兜底、黑色填充天空兜底或低精度导出兜底。
- 无效草稿仍提供原照片定位，以便修正；右侧明确标“天空效果暂停，显示其他效果”。它不可提交，也不会成为导出结果。禁用坏链接效果时仍保留其原始意图；重新选择同一路径可明确重新绑定新内容。
- 每区域 64 对象，总计 128 笔/8192 路径点，既有 Rust 工作预算；素材 64 MiB/3200 万像素，OpenCV 源边长 <32767；预览图边长 ≤800、总结果 6 MiB，完整请求 256 KiB。超限停止，不静默截断。

## 已接通的共享调用点（仅源码状态，不代表运行通过）

本轮在镜头/透视 v9 基础上接通以下路径，项目版本提升为 v10，保留 v7 手动液化、v8 影棚和 v9 镜头/透视的严格版本验证：

- `vram.py`：构造/load/reset 时初始化 `SkyReplacementStage` 和 `_sky_replacement_key=None`；在 local-grade 后调用 `out=self.sky_replacement.apply(out,self.align_source_grade_mask)`，背景/手动液化之前；`doc_state` 包含常驻字节报告；旧背景启用入口反向拒绝 sky enabled。
- `server.py`：初始化 `_sky_replacement=S.empty()`；capture/restore/reset/snapshot 中保留该字段（快照键 `sky_replacement`）；`doc_state` 调 `R.report`；渲染前 `R.sync`；`_sky_replacement_owner` 和 preview owner 的 prepare/apply/finish，idle tick，取消/关闭。接受 `sky_replacement_preview` 不记历史，`sky_replacement apply` 由现有历史事务包裹；caps `sky_replacement_protocol:1`。
- 现有 document-version/capture invalidation：sky apply 是实质编辑，必须 bump revision、取消其他旧坐标捕获；preview 只是只读，不 bump。切图、撤销、重做、源变更和退出取消 preview。
- 导出快照与全尺寸解码：`R.verify_snapshot` / `R.check_export_decode`；`export_recipe` 早于 generic-return 调 `configure_export`；`ExportSpec` 增加 `sky_replacement`、`sky_replacement_path/stamp`、`sky_replacement_prepared` 并严格 `check`；开始准备 `export_prepare`，每带 halo 瓦片 `attach_tile`，结束 `finish_export`。天空边缘和素材模糊预先在完整网格计算，因此不需要新增瓦片 halo。仍需已有自动变形与最终液化 halo。
- `inspection_worker`：同样 snapshot/source 验证，不可忽略启用天空；full-quality 共用导出管线。
- 项目模式：v10 保存、严格读取 `check_saved_record`（包括 nested history/doc versions），仅旧 schema 迁移添空记录，不能 overwrite 现有恢复组/液化。`source` 保留原图 SHA，素材保留 path/SHA/ICC，缺文件是可恢复悬挂，不删除配方。
- `ui/src-tauri`：注册新 api/host 模块，AppState `sky_replacement:Mutex<SkyReplacementHost>`、`sky_preview:Mutex<SkyReplacementPreviewHost>`；dispatch/enqueue 和 preview/result event 接收；engine-ready/reset/ended/capture invalidation；tauri handler 注册四个 api。
- React：`native.ts` doc/caps type；`useRetouchCaptureWorkflows` 或 App 所有者挂 `useSkyReplacementWorkflow`，传相同 doc+revision/context fence 和关闭冲突工具；图像美化/背景区挂 `SkyReplacementPanel`，无能力时显式禁用。
- 预设/批量：注册 `lnx.sky_replacement.v1`，`sky_replacement_scope` 与 presets 适配器只携素材与参数。逐图保留自己的天空/人物/水面/地平线/恢复，不搬源照片坐标。目标缺标记或反射缺水面则逐图报 blocker，不把预设当自动检测。预设应用、批量预检、冻结提交和批量撤销均验证目标原件与素材，使用有界验证网格准备候选；实际生产渲染与全尺寸导出继续独立严格验证，纳入既有原子历史/批量回执；全局“仅参数”范围不能意外携带 source masks。

### 暂停恢复与资源准入

- 已保存天空缺文件、身份改变或资源不足时，原配方和区域不删。仅普通代理显示允许暂时展示其他已保存效果，帧携带 `sky_replacement_suspended`、`suspended_effects` 和 `display_quality:proxy-incomplete`；界面持续显示醒目标记。该帧没有天空 preview/apply 证明，不能用于全质量检查或导出。重新选择素材或关闭该效果仍可进入。
- 真正的天空 stage 继续抛出错误，检查/导出/预设或批量应用不使用代理省略路径。专用天空草稿只有其精确、已确认显示、无错误的真实结果才可提交。
- 素材准备、区域栅格、源域采样、12 通道真实形变和融合有独立 CPU/GPU 预算；最终镜头/透视需要的 RGB8 浮点拼接缓冲也计入天空导出预算。不降低出片位深。

## 留给本地验证的明确验收项

没有执行测试、构建、typecheck、模型、软件安装或图片运算。本清单是应验证事项，不是新编造的“已通过用例”。

- 20 个官方控件/分组逐项可操作，真实图像变化和默认/边界/恢复语义正确。
- 天空/人物/水面、树枝/发丝边界、无天空/无水/多人物、露空、黑天空、透明素材、多页 TIFF、嵌入 ICC 与 RGB16 素材。
- RGB16 暗部/渐变低 8 位不是补零；完整效果与 RGB8 路径共享浮点链；原分辨率与不同 tile size 的坐标、反射、边界没有接缝。
- 两张不同裁剪/旋转/美型/最终液化照片切换；定位始终源域，恢复只擦回 sky contribution。影棚地面清理与天空可共存，整体背景替换冲突双向阻止。
- 快拖滑块/画笔中途取消、pointercancel/lostcapture、延迟结果、超时、重复点击应用、切图/撤销/重做/重开与素材文件改变。
- 项目保存/重开/旧模式迁移与 source-mismatch，预设与批量逐图可用性、坏资产报错、不覆盖既有独立蒙版组和恢复笔迹。

结论：显式标记版已完成源码整合，自动语义提议仍未提供；本地实机、数值、交互和构建验收均未运行，不能标记 PC-32476 已通过或自动换天空已交付。
