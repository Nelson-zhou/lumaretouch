# 发色统一：独立审核 UI

状态：AUTHORED / UNRUN。仅源码编写及人工静态阅读；没有执行产品、模块导入、测试、类型检查、构建、模型推理、安装或下载。本文不宣称功能或画质已经验收。

## 范围和语义

- 独立需求 `LNX-REF-PC-32472-C-fb2fe59a22`，独立操作 `lnx.hair_unification.v1`。
- 配方严格为 `{version: 1, amount: -1..1}`。负值参考本人发尾，正值参考本人发根，0 为中性。显示为 −100% 至 +100%；这是本实现量程，不是公开的商业算法参数。
- 仅当前照片、当前所选人物的独立覆盖。没有关联、分组、批量、预设或通用标量激活入口。
- 源图手绘根部/尾部采样，用户明确确认样本可见、无遮挡且属于本人。非所用方向样本可为空。
- 已审核的 `hairColour` 范围和冻结实测头发证据由引擎复用；UI 不创建第二份头发支持、不使用脸框、上下半图或最近人脸猜测头发归属。
- 参考样本不改变；同一人物已审核头发中其余像素是颜色匹配目标。不是自动解剖分区，也不是自动根部检测。
- 仅颜色匹配，保留当前亮度与纹理；纯亮度差异、裁黑、过曝、缺失细节不会被重建。没有新增学习模型或生成式发丝承诺。

## 文件与职责

- `ui/src/hairUnification/model.ts`：独立 DTO、样本/配方严格校验、当前照片人物绑定、候选/回执/ACK 核对、PNG 字节 SHA-256。
- `nativePort.ts`：应用生命周期的草稿和原请求所有者；有界发送、原编号查询、明确未发出与结果未知区分、完整审核到提交状态机。此处不拥有人物图、银行或历史。
- `useHairUnificationPort.ts`：App 一次挂载，不随面板关闭销毁。
- `HairSampleEditor.tsx`：完整不可变源图上的独立样本画笔，源图归一化向量、缩放、减去、逐笔撤回、清空草稿。
- `ReviewImages.tsx`：真实干净 before/after 与范围图；解码尺寸、PNG 字节摘要和整图可见性检查。
- `HairUnificationPanel.tsx`、`hairUnification.css`：带焦点约束的审核工作区、独立中性恢复、显式本人确认与精确图片确认。
- `HairRecovery.tsx`：父级接入的明确引擎重启与已保存工程重新打开入口，仍须核对原生恢复标记，不能自行把未知当成功。
- `index.ts`：小型公开接入面。已有 `hairColour` 文件不改动。

## 父级接入

从 `./hairUnification` 导入 `useHairUnificationPort`、`HairUnificationPanel`。

`useHairUnificationPort(enabled, refresh, people)` 返回 `{port, state, check}`。其中 `people` 是当前权威 `PeopleView | null`，`refresh` 只在确认提交/中性恢复后刷新照片。

`HairUnificationPanel` 接收 `{port, busy?, available?, engineAlive, onStartEngine}`，其中 `engineAlive: boolean` 与 `onStartEngine: () => Promise<void>` 由父级提供。`available` 默认 false；父级必须以 `ready_caps.hair_unification_protocol === 1` 显式启用。该协议门槛不同于来源回执中的 `native_available` 数值核心能力：核心缺失禁用非零预览；请求中性恢复不需要本项新数值核心或重新测量根尾样本，但原始来源、人物及其他已保留效果所需分析仍由引擎核对，缺失时必须明确拒绝。

父级 enabled/busy 输入只包含外部占用，不包含本模块自己的 pending，以免原请求自行死锁。其他工具和照片历史需在 `state.open || state.pending || state.checking || state.preparing || state.refreshing` 期间受保护；许可点击区域是 `[data-hair-unification-workflow]`，父级活动栏的原请求查询也应保留可用。关闭窗口后仍保留草稿、原编号和 pending。

父级及引擎规范人物图是唯一历史所有者。UI 不调用通用 people patch，不维护影子人物图，不重建历史，不复制支持/样本到其他照片。

## 原生边界

发送：`invoke('hair_unification', {request})`。

请求精确字段：`{cmd:'hair_unification', protocol:1, operation_id:'lnx.hair_unification.v1', request_id, action, people_context, payload}`。

- `context`：`{}`。
- `preview`：`{recipe, root_sample, tip_sample, ownership_confirmed:true}`。
- `presented`：`{preview_id, review_token, before_sha256, after_sha256, support_sha256}`。
- `commit`：`{preview_id, review_token, confirmed:true}`。
- `clear`：`{}`，只将本项 amount 设为 0，旧不可变样本由规范历史继续保留。

查询：`invoke('hair_unification_status', {request_id: original})`，不向引擎重发原修改。原生邮箱返回 `{request_id, phase:'pending'|'done'|'unavailable', result?, error?}`。

入队只有两类明确响应：`{requested:true, request_id}`，或确认从未入队的 `{requested:false, not_sent:true, request_id, error}`。异常不当成未发送。未发出也保留草稿；入队之后不确定只能查询同一编号。

终态完整关联字段：`event:'hair_unification_result'`、protocol、operation_id、request_id、action、document_id、原 people_context、原 request_payload。UI 对这些身份和 payload 做精确比较；不同方向、不同样本、不同人物或照片的结果不能解除保护。

### 图片与 ACK

- context 提供真实完整源图 PNG、规范 source、源图尺寸及单独的 `source_preview_width/height`。UI 在真实图片完成解码且尺寸匹配之前禁用采样。
- preview 提供独立的 `before_png/after_png/support_png`、每张的 width/height 和 SHA-256、source、face_ref、原 recipe/root_sample/tip_sample、sample_counts、reference_side、preview_id、review_token、preview_sha256、sample_asset_sha256。
- 所有显示图片每边不超过 1024 像素，PNG data URL 有界；成片 before/after 必须同尺寸。它们是完整成片缩小审核，不是假色范围图，不是实际原尺寸质量验收。
- `context.support_sha256` 是已审核头发范围内容身份；`preview.support_sha256` 是审核范围 PNG 字节身份，两者用途不同，不混淆。
- 三张图都需完成解码、自然尺寸匹配、实际 PNG 二进制字节 SHA-256 匹配，并完整进入前台视图。隐藏图片、裁切局部、未加载占位图或仅范围图不构成 ACK。
- 用户先勾选本份整图与本人样本确认，再点击“核对本份图片的显示确认”。引擎须返回 `kind:'presented', presented:true` 及完全相同的 preview/token/三图摘要。
- 只有这份 ACK 和仍然当前、完整可见的候选允许 commit。样本、程度、来源、人物、状态版本或显示变化会撤销本地确认。
- commit 回执中的 `asset_sha256` 是样本资产内容摘要，必须匹配 preview.sample_asset_sha256，不是源照片 SHA。

## 中断与预算

- 每个样本最多 64 个 brush/radial 对象；本 UI 只创建 brush。每笔最多 1024 点，每样本最多 8192 点。请求体最多 512 KiB。
- 坐标是整个源图画布边界的 [0,1] 向量。笔刷半径从源图短边计算双轴，不写屏幕像素蒙版，也不反算后期变形画布。
- 手势离开边界、源图布局/缩放变化、失去指针捕获、窗口失焦或路径超限会取消未完成一笔；已有草稿保留。
- 拖动、切换方向、勾选样本归属、生成候选、显示 ACK 都不直接写规范照片历史。
- 待确认时禁用新请求、中性恢复、草稿丢弃和再次应用。查询失败、错误回执、结果未知、引擎缺失都保留原请求与样本。
- 来源变化时保留但冻结旧草稿，不借给新照片/人物。只有原请求结束后才允许明确丢弃旧草稿并载入当前人物。
- 关闭面板保留草稿，不承诺跨应用重启恢复。确认成功后刷新失败不重发提交。

### 已保存工程重新打开后的显式退役

这不是超时后解锁，也不是把未知当成功。只有原生回执账本在当前引擎收到真实 `project_opened`、有效数值 docs 和精确引擎 epoch 后，才能为原操作提供 `workspace_reopened:true, success:false, outcome_unknown:true`。原生拒绝任何由引擎结果冒充的该标记；普通导航、照片/人物/context 改变、引擎断开和 UI 自己刷新均不能生成标记。

UI 的 `readWorkspaceReopened` 对原 event/protocol/operation/request/action/document/people_context/request_payload 全部精确核对。接到有效标记后，`state.workspaceReopened` 为 true，但 `pending`、`uncertain` 和原请求/草稿继续保留。普通 `readResult` 明确拒绝该标记，不把它作为成功或已知拒绝处理。

父级可提供明确的保存工程恢复入口和另一个“结束旧工程会话保护”的确认按钮。`port.canDismissReopened()` 返回是否已有精确原生证据且没有进行中的查询/准备/刷新；只有用户明确触发 `port.dismissReopened()` 才移出活动请求。该动作不调用引擎、不重复发送、不回滚、不刷新为成功，并使旧候选失效，要求重新载入并审核当前工程。

`state.retired_request`、`state.retired_receipt` 保留最近退役的原请求和仍未知的回执；`state.retired_operations` 追加保存每次原请求、回执、原来源绑定和根尾样本草稿（不存 PNG、不建影子历史）。之后载入、关闭或丢弃新草稿不清空该存档。进程内预算为最多 32 项 / 16 MiB；达到预算时拒绝退役并保留当前锁，绝不丢弃旧未知记录。此存档仍不承诺跨应用重启持久保存。

## 必须在后续授权本地验收中运行的检查（全部 UNRUN）

1. 默认中性、signed 参数端点、错误数值/版本/未知字段拒绝；负值确实参考尾部，正值确实参考根部。
2. 缺少协议、数值核心、已审核 hairColour 支持、冻结语义证据、本人确认或实际样本时不允许激活；禁用人物可在有效当前所有权下请求中性恢复；本项不要求新数值核心或重测样本，但原有来源/人物/其他效果的必要分析仍须可核对，缺失时明确拒绝。
3. 长发、卷发、倒置头部、相邻人物、交叉发丝、帽子/遮挡、只检出一张脸等情况下不产生自动归属假设。
4. crop/rotation/shape edit 后的源图采样域正确；按下后改变布局、拖出边界、取消指针、失焦、超预算不会留半笔或错位样本。
5. 前后整图实际来自完整渲染；裁切、缩放、横纵比例、支持图不同构图均不偷换。PNG byte hash/尺寸/token/样本资产有一处不同即不能 ACK 或提交。
6. 未加载、图片错误、后台窗口、未完整可见、关闭/重开、人物/照片/版本改变、快速编辑和迟到响应不会借旧图授权新效果。
7. 双击应用只发一个请求；丢失入队回复、明确 not_sent、pending 超时、unknown、unavailable、错误身份、引擎退出均按各自原请求规则处理，原样本不丢失。
8. commit 拒绝保留可编辑草稿；成功后只增加规范历史，刷新失败不重复提交；undo/redo、项目重开和原尺寸 RGB8/RGB16 导出由父级/引擎单独验收。
9. 关联/分组/批量/预设不能绕过本项全图审核；其他照片不能获得此照片的根尾样本或支持。
10. 键盘焦点、Esc、Tab、局部撤笔快捷键、中性按钮、滚动和平移、窄窗口和触屏可用；照片全局历史不会在此模态草稿后方运行。
11. 普通 unknown、超时、context/epoch 改变、引擎伪造恢复标记、错原编号/配方/来源、success=true 的标记均不允许退役；真实原生 reopen 标记也不自动解锁。明确退役后不重发、不算成功，旧请求/未知回执/样本存档在新载入后仍保留；重复退役和存档满额不能丢失原记录。
