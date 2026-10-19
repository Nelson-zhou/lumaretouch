# ADR-0008：模块作用域、预设落盘格式与肤质质量阈值

日期：2026-10-18　状态：已采纳
关联：《P0参数注册表》LNX-P0-PRESET / LNX-P0-BATCH / LNX-P0-SKIN；《开发验收用例》
PRESET-001、PRESET-002、BATCH-004、SCOPE-001、PORTRAIT-002；ADR-0003、ADR-0007

## 1. 作用域只有一份出处：`lumaretouch_engine/scope.py`

预设（"把一组模块的参数盖到一张图上"）与批量同步（"把同一组盖到多张图上"）必须是
**同一语义**。分开写两份"哪些参数属于哪个模块"，就会出现"预设里没有的参数被批量
偷偷同步了"——本仓同一形状的坑受过两次（doc_state 里 crop 被塞进 exposure 的字典、
per-image 清单在组装处静默丢键）。

作用域按冻结注册表的 `operation_id` 划分（`lnx.batch.v1.module_scope` 的类型就是
`set[operation_id]`，这不是我起的）。运行时读代码里那份表，判据读 `docs/p0/` 里那份冻结件
（注册表不进 deb，所以运行时不能去读文件），两边由
`engine/tests/test_scope_registry_agreement.py` 双向对拍：名单、中性值、量程、
`conflict_policy` 枚举、`module_scope` 的空集中性，逐条比。

**这条守卫当场抓出两个我写错的字面量**（写在 scope.py 里自以为照抄了注册表）：
`temperature_shift` 我写成 ±100，冻结件是 **±2000 K**；`rect_normalized` 我允许
[-0.5, 1.5]，冻结件是**逐轴 [0,1] 加 x0<x1/y0<y1**。没有双向对拍，这两条会变成
"合法值被拒"和"越界值被接受"两种产品故障，而且只在用户碰到时才发现。

## 2. `enabled` 不是第二个开关

注册表有 `lnx.skin.v1.enabled`（neutral false）与 `strength`（neutral 0.0），而引擎只有
一位强度。再造一个独立 `enabled` 会允许 `enabled=1 且 strength=0` 这种"开着但没作用"
的配方——两份事实说同一件事时必然有一份会说谎。所以 `enabled` 解释成 `strength > 0`
的只读别名；导入时 `enabled=false` 强制把 strength 归 0。

注册表里有、本版本**没建模**的参数（`blemish.protect_identity_marks`、`mask.*`）一律
记在 `MODULES[op]["unmodeled"]` 里并带原因：带原因才会"整条拒 + 说清为什么"，
没记就是"静默丢掉一个参数"（假绿）。守卫要求：注册表里每个键要么被建模、要么有原因。

## 3. 逐点层不进任何作用域

消除笔/修容笔笔迹与掩膜本体在**代理档像素坐标**上成立，形变层要那张图自己的关键点：
搬到另一张图就是错的坐标。所以它们不在任何模块子集里，也不提供任何"看起来能同步"
的选项。可转移的是：曝光、白平衡、裁剪（归一化）、磨皮强度与高低频参数。

## 4. 预设的落盘格式与安全边界（PRESET-002）

格式 `lrt.preset.v1`：`{schema, id, name, kind, modules{operation_id → 参数}}`，
用户预设存 `$XDG_DATA_HOME/LumaRetouch/presets/`（`LRT_PRESET_DIR` 覆盖）。
**跨项目**的用户资产，所以不跟工程文件走（手册：个人预设共用）。

拒的六类（每类都是整条拒，不改任何状态）：未知 schema、路径穿越的 id（slug 白名单
`[a-z0-9._-]{1,64}`，禁 `/`、`\`、`..`、前导 `.`）、过大文件（256 KiB，stat 与实读各判一次）、
脚本/可执行内容（`script/code/exec/eval/command/python` 键名与 `#!`/`<script` 内容）、
未知模块与非法参数（NaN/Inf/越界/类型错）、顶层多余键。
`builtin` **不是文件字段**：它是"从哪个目录读到"的事实，由引擎注入——文件能自报内置
就能遮住真内置预设并绕开"内置不删"。

内置两个预设（人像：磨皮 0.45；色彩：+0.30 EV / +250 K / +0.05 tint）写在代码里而不是
`data/*.json`：deb 的引擎打包只拷 `data/` 里的权重，新增一类数据文件要同步改打包脚本，
漏改的后果是"装机后预设列表是空的"，而这在开发机上永远看不出来。

## 5. 一次预设 = 一步撤销；预设与同步都算"编辑"

`EDIT_CMDS` 加了 `preset` 与 `batch`。逐条命令各自入栈会得到"一次预设 = 四五步撤销"，
而 UI 上没有任何地方解释为什么——这正是 `exposure` 漏在名单外那次的同一类错（CORE-006
把它响出来过）。预设的落状态走 `_replay_state`（`_apply_state` → `_attach_pipeline` →
`_rehang_precompute`），与撤销/换设备/切文档同一条重放路径，不写第二份重放。

"这一张当前等于哪个预设"由引擎判（`presets.last_applied`）：报之前先比一次那几个模块
的参数，套完又被手改过就回 None。UI 的下拉因此不会在用户推过滑块后还赖着"暖调（色彩）"。

## 6. 批量撤销的冲突判据是参数，不是时间戳（BATCH-004）

`undo` 对每一格只问一句：**那几个模块现在的参数，还是不是我当初写进去的那一组**。
相等 → 同步后没人碰，还原；不等 → 用户又编辑过，报冲突并且不动它。

本轮这条判据抓到一个真 bug：撤销路径拿的是底片条格子里的**陈快照**（`row["state"]`
只在切走时才更新），于是"同步后又被编辑"那一格被当成没动过、一起还原了——用户的
后续修改被抹掉。修法是撤销前先 `_remember_current()`，并且比较只看 `row["state"]`。
这条有测试（`test_batch_sync_undo_restores_untouched_and_reports_conflict`）。

`conflict_policy` 只有注册表那两个值（`skip_and_report` / `recheck`），两个都是不覆盖；
**没有 overwrite 是冻结的决定**（EXPORT-001"无提示不覆盖"的同一要求），所以 UI 与
命令行都不提供"强制覆盖"。

## 7. ΔE00 此前是纸面阈值，这一轮才真的能算

ADR-0003 把色彩链质量门禁写成"ΔE00 ≤ 2.0"，而仓库里**没有任何一处实现过 ΔE00**——
阈值存在，测量不存在，等于那条门禁从未被执行过。本轮补 `lumaretouch_engine/color_metric.py`
（sRGB→线性→XYZ/D65→Lab→CIEDE2000），并逐条过 Sharma 等人的官方校验数据
（`engine/tests/data/ciede2000testdata.txt`，34 行，容差 5e-4）。
数据文件按原样 vendored 并在同目录 README 里记来源与许可（只作测试校验，不进 deb）。

sRGB 传输函数那一处也错过一次：写成 `(c + 0.055/12.92) / (1 - 0.055/12.92)`，看着像
"归一化"，实际把整条曲线偏了一个常数——官方向量一对就露馅。

## 8. 肤质修饰的三个阈值与实测（PORTRAIT-002 自动化那半）

判据（6 组样本 × strength 0.6，全部走真命令通路；样本与派生方式见
`docs/acceptance/PORTRAIT-002-盲评规程.md`）：

| 判据 | 阈值 | 本轮实测 |
|---|---|---|
| 面部区高频能量保留比 | [0.50, 1.15] | 0.994 – 1.004 |
| 面部区 ΔE00（磨皮前后同图对比） | mean ≤ 1.00，p95 ≤ 3.00 | mean 0.674 – 0.923，p95 1.823 – 2.397 |
| 掩膜作用域外（角背景） | 0 LSB | 0 LSB |

阈值定在"实测"与"明显坏味道"之间：高频比低于 0.5 就是橡皮（局部对比被抹平），
高于 1.15 说明这一层在加锐/加噪而不是磨皮；ΔE00 的均值上限取 1.0（实测最高 0.923，
留不到一格的余量），p95 取 3.0 是因为磨皮在边缘/五官过渡处必然动到少数像素，
而 ADR-0003 的 ≤2.0 管的是**色彩链**（LUT/定向），不是空间平滑——两个不能混用，
也不许拿一个去冒充另一个。

**人工盲评不在这里签**：`docs/acceptance/case-map.json` 把 PORTRAIT-002 标成
`manual: true`，验收报告的状态是 `manual_pending`（"待人工"），不算通过。
指标能挡住明显的错，挡不住"看着就不像皮肤"。

## 9. 后果

- UI 注册表里 `lnx.preset.v1.save` 与 `lnx.batch.v1.module_scope` 两处从"显式禁用 +
  原因"变成真接通；`lnx.preset.v1.apply` 现在接的是**模块预设**（LUT 面板那一排表预设
  按钮仍读 ready 的 `presets`，是另一件事）。
- 宿主（Rust）新增 `preset` / `batch` 两条命令，只做把手：不判合法性、不记作用域名单。
- 引擎每步 `session_state` 会读一次预设目录（几个小 JSON，几十微秒量级）。真要缓存，
  键必须是目录 mtime + 文件数，不能是"我记得没改过"。
