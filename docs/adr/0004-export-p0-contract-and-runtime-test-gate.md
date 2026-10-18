# ADR-0004：导出侧 P0 口径（ICC / 元数据 / 冲突 / 原子提交）与"运行时形状"门禁

日期：2026-10-18
状态：已采纳
相关：ADR-0002（mediapipe 随包运行时）、ADR-0003（D-P0 冻结与质量阈值）、
《P0参数注册表.json》`lnx.export.v1`、《开发验收用例.json》COLOR-001/002/003、EXPORT-001

## 背景

`write_file` 原先只做一件事：把数组存成文件。它既不嵌 ICC，也不带任何源元数据，
落盘是裸 `img.save(path)`。COLOR-001/002/003 与 EXPORT-001 四条 P0 用例都要求
**从文件读回来反查**，而"没做"与"做了但只有 8-bit 那条路做了"在报表上长得一样。

本轮把四个口径落进两条通路（8-bit 常规、16-bit 母档直通），并把参数一路接到
`cmd_export` 的事件面上。过程中出了三个必须记下来的发现。

## 决策

### 1. ICC：只给拿得到真档的选项，嵌进去的字节用 sha256 自证

- `output_profile` 按冻结注册表是 `source|srgb|adobergb|display_p3`（中性 srgb）。
  本层内置只有 littleCMS 的 sRGB（实测 588 B）；`adobergb`/`display_p3` **没有真档就明确拒**，
  并提示调用方可以递一个真实 `.icc` 路径。不烘一份"名字对、内容错"的 profile：
  读方会拿它去转色，结果是颜色真的变了而文件里写着另一个名字（COLOR-002 的口径）。
- **littleCMS 的 `createProfile("sRGB")` 跨进程字节不稳定**：同一台机器两个子进程都出 588 B，
  sha256 分别是 `c827bf…` 与 `a82481…`（进程内稳定）。于是"拿本地再生成的一份去比文件里那份"
  这个断言本身不成立。改成两条能成立的：
  ① `write_file` 回报 `icc_bytes` + `icc_sha256`，读方拿**文件里那份**算哈希与事件对账；
  ② 语义侧用 `ImageCms.getProfileDescription()` 验它真是 sRGB（"sRGB built-in"）。
- 16-bit 母档走自写 TIFF：ICC 落在 tag **34675（0x8773）**。这里我一度写成 `0x8711`
  （=34577，不是 ICCProfile）——自写自读那份发现不了，是"Pillow 也把标签原样收下但不认、
  `info` 里没有 icc_profile"暴露的。跨实现读方不是锦上添花，它就是这类错唯一的照妖镜。

### 2. 元数据：默认删 GPS、永远删 Orientation、损坏即报错

源文件的 ICC/EXIF 现在在解码层就被带走（`Decoded.source_icc/source_exif`，两条 Pillow 通路），
理由与边界都写进 notes：

- **判有无 GPS 只看键在不在，不调 `get_ifd(0x8825)`**：Pillow 的 `get_ifd` 会把子 IFD 缓存进
  私有的 `_ifds`，而 `tobytes()` 会遍历 `_ifds` 把"不在 items 里"的子 IFD 重新写回去。
  实测三种写法都得出了"GPS 没写出"，但那取决于缓存时序；不调它就不会有缓存。
- **Orientation(0x0112) 无条件删**：像素在解码层已经 `exif_transpose` 摆正，再把 274 透传出去
  等于让读方再转一次——COLOR-003 里"输出无二次方向错误"点名的就是这个。端到端用例现在钉死
  "源 48×64 + orientation=6 ⇒ 产物 64×48"。
- **损坏的 EXIF 报 `ExportError`**，不默默当"没有元数据"（COLOR-002 的"展示…错误"）。
- **RAW 两条解码臂不提取源元数据**：这一条通道没读，不是文件里没有。`Decoded.notes` 里明写，
  而 `output_profile=source` 对 RAW 直接拒并给出这句原因。UI 侧必须据此把控件置灰——
  DoD-3 禁的就是"按下去不响的开关"。

### 3. TIFF 压缩的中性位按通路选

注册表 `tiff_compression = none|deflate|lzw`，中性 deflate，这条对常规导出成立
（真图实测 1.31 MP：none 3.93 MB/31.3 ms，deflate 1.55 MB/132.1 ms，lzw 1.96 MB/51.9 ms，
三者读回逐字节一致）。但 16-bit 母档**只写无压缩**：实测不加 Predictor 的 16-bit 交织数据
deflate 是负收益（噪声样本 18,600 B > 无压缩 18,578 B），而加 Predictor=2 就不再是
"母档解出来什么样就写什么样"的直通。两条合起来的默认值是：8-bit → deflate，16-bit → none；
显式给 16-bit 要 deflate/lzw 一律开跑前拒。
（本轮第一次实现时把"deflate"同时当两条路的默认值，于是 16-bit 直通开箱必失败——
`test_export_bit_depth_16_reports_its_fidelity_numbers` 就是这么红的。）

### 4. 冲突策略的校验与"文件是否存在"无关

`resolve_target` 原先只在目标已存在时才看策略名，于是拼错的 `conflict_policy` 在导出一批
全新文件时被静默当成 `skip_and_report` 通过。校验抽成 `_check_policy` 并前置：
认不出就拒，`overwrite` 不在枚举里是**有意的**（EXPORT-001"无无提示覆盖"）。
两个结局都不许盖已有文件：`skip_and_report` 不写并回报原因；`recheck` 用 `-0001` 唯一名继续写
并在账单里记 `renamed_from`。落盘统一"内存编码 + 同目录 tmp + fsync + os.replace"，
失败分支删 tmp，不留半成品。批量事件里逐张带 `out_skipped/skip_reason/renamed_from`，
只在批级别说一句"有跳过"是没法复查的。

### 5. 发布门禁新增一条：必须在运行时 venv 里跑过测试

本轮最贵的一条。`d3b` 把 `_exposure` 加进了 `DOC_FIELDS` 与 `_capture_state`，
唯独没加进 `_fresh_doc_state`。开发 venv 里报的是 **384 passed / 247 skipped 全绿**，
而装机的运行时第一次 `load_image` 就 `KeyError: '_exposure'`——那 247 条 skip 里正是
全部需要 torch 的协议用例。两条修复：

- **结构上**：`_fresh_doc_state()` 现在自带名单守卫（与 `_capture_state` 守同一批字段），
  缺一个键当场响。反向门禁实测：注入一个假字段，`AssertionError: 起始状态名单与 DOC_FIELDS
  漂移了（新图层没给默认值）`。
- **流程上**：新增 `packaging/check-tests-runtime.sh`，并被 `build-deb.sh` 在
  `check-release.sh` 之前调用。它要求运行时 venv 在场、torch 可 import、
  **skip 条数不超过上限（默认 24）**、零失败。判缺了就是不过，没有"读不到就跳过"这一支。

顺带被这条门禁照出来的另两条红（都在 HEAD 上就已存在，只是从没在带 torch 的环境里跑过）：

- `test_grade` 的"w=0 像元一动不动"：实现没错，是判据取了**羽化前**的权重且拿未 clip 的 x 比。
  算子过 `feather_np`（[1,2,1]/4）并先 clip 到 [0,1]，所以断言改成按羽化后权重取像元、
  与 clip 后的 f32 比，并加 `assert zero.sum() > 0` 防它空转。
- `test_explicit_missing_backend…` 用 `backend="mediapipe"` 当"缺席的后端"：mediapipe 自
  ADR-0002 起是随包运行时，装上之后这条请求会成功。改成点名一个根本不会存在的后端名，
  并新增一条正面对拍（点名 mediapipe 时要么 `backend` 真是 mediapipe、要么明确报错，
  绝不允许"请求 mediapipe、回报 synthetic、还发 precompute_ready"）。

## 影响面

- `engine/src/lumaretouch_engine/decode.py`：`Decoded` 多两个字段；两条 RAW 臂各加一条 note。
- `engine/src/lumaretouch_engine/export.py`：`_icc_facts/_profile_bytes/_filter_exif/
  _check_policy/_tiff_compression/resolve_target/_atomic_write/read_tiff16_icc`；
  `write_file`、`write_tiff16`、`export_master_16bit` 的新参数与可验回执。
- `engine/src/lumaretouch_engine/server.py`：`EXPORT_KEYS` + 四格、`cmd_export` 校验顺序、
  `_export_args` 末位 opts、逐张与批级事件回显、`_fresh_doc_state` 缺键修复 + 守卫。
- `engine/tests/test_export_profile.py`（24 条，全部读回文件反查）、`test_protocol.py`
  （新增 5 条端到端 + 2 处过期前提修正）、`test_grade.py`（1 处判据修正）、`test_export.py`
  （两条头部布局断言改为按字段算，不再钉魔术数）。
- `packaging/check-tests-runtime.sh`（新）与 `packaging/build-deb.sh`（接进流程）。
