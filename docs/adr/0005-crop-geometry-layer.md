# ADR-0005：裁剪 / 旋转（lnx.crop.v1）——唯一尺寸出处、链尾位置与"预览是缩放视图"

日期：2026-10-18
状态：已采纳
相关：ADR-0003（D-P0 冻结：`LNX-P0-CROP` 的 rect/rotation 量程与中性值）、
ADR-0004（导出侧 P0 口径）、《开发验收用例.json》P0-CROP-NEUTRAL / P0-CROP-BOUNDARY /
RENDER-002（预览导出一致）

## 背景

注册表 `lnx.crop.v1` 两个参数：`rect_normalized`（中性 `[0,0,1,1]`）与
`rotation_degrees`（中性 `0`，冻结量程 `[-180, 180]`）。引擎原先没有任何几何层：
命令面收不到、链上没有、导出与 16-bit 母档都不认。

这一层比像素层危险的地方在于：**它同时决定"看到什么"和"文件是多大"**。预览与导出
一旦各算各的尺寸，用户就会在文件上看到与预览不同的一行像素；而代理画布尺寸是固定的
（shm 双缓冲 + 显存常驻帧），不能为一次拖滑块重分配。下面四条就是为这两件事定的。

## 决策

### 1. 尺寸只有一个出处：`ops/geometry.py::_cut`

`out_size()` 与两条臂（`crop_rotate_np` / `crop_rotate_t`）的切片都必须经过同一个
`_cut(n, a, b) = round(n*b) - round(n*a)`。

这条不是洁癖，是量出来的：写第一版时 `out_size` 用的是 `round(n*(b-a))`，与切片的
`round(n*b) - round(n*a)` 在 `n=1024, a=0.05, b=0.75` 这类取值上**差 1 像素**。差的
表现正是 RENDER-002 要防的"预览与导出不一致"，而且只在那一行像素上、肉眼看不出来。
用例 `test_crop_neutral_is_byte_identical_and_crop_actually_crops` 里把这两个式子
都按测试自己的算法重算一遍当对照：拿引擎函数验引擎函数只是把同一个函数调两次。

### 2. 链序：几何在所有像素层之后（最外尾）

`deform → exposure → lut → grade → background → geometry`。

反过来"先剪再算"会让同一支消除笔在剪后的图上落在别处——那不是"批量应用设置"，
那是另一张图。导出路径同样在 `export_image()` 之后再 `crop_rotate_np()`，两边同序。

### 3. 预览是缩放视图，不是另一种构图

`apply_geometry()` 在代理尺寸上剪转后，用 `interpolate` 缩回代理画布——因为显存常驻帧
与 shm 双缓冲的尺寸固定。于是事件必须把两个数一起报出去：

* `crop_out`：代理档上剪转后的尺寸（预览那一层的真实像素数）；
* `out_full`：导出会写的满幅尺寸，取自底片条那一行记的 `src_w/src_h`。

只报一个，UI 就会把"预览里那一小块"讲成"文件的尺寸"。可验版本是
`test_crop_reports_the_size_the_exporter_will_actually_write`：拿**文件里的像素尺寸**
反查 `out_full`，因为文件来自全幅解码后另做一次裁剪的完全不同路径。

### 4. 中性逐字节恒等由短路给出；旋转符号是顺时针

`is_identity(rect, rotation)` 为真时两臂直接把原数组递回去（连复制都不做）。90° 整数倍
走 `rot90` 转置（无损、不重采样），任意角走逆仿射 + 双线性、画布取外接框。

正角定义为**顺时针**（Lightroom / Capture One 的右转习惯）；两臂与导出共用一个式子，
改符号要一起改，server 侧不另立一套。

### 5. 裁剪只删除区域，不改动留存像素（P0-CROP-BOUNDARY 的 then）

`test_crop_only_deletes_pixels_and_leaves_the_kept_region_untouched` 用 PIL 自己裁出
留存区，与导出文件逐字节比：容差 0。这条把"剪完顺手重采样一遍"这种实现永远关在门外
——它在预览里几乎看不出来，却会改掉用户没有要求改动的每一个像素。

### 6. 16-bit 母档直通点名拒绝裁剪

母档直通的语义是"解出来什么样就写什么样"。剪过就不是那张图了，16-bit 那条路
（`_master16_blockers`）在开跑前按名字拒绝，而不是悄悄插一次重采样。UI 要裁剪 +
16-bit，走 8-bit 全链导出。

### 7. 生命周期：crop 是文档状态，也是可撤销编辑

`_crop_rect / _crop_rotation` 进了 `DOC_FIELDS`，所以三处（`_capture_state` /
`_fresh_doc_state` / 名单守卫）必须同时改——本轮 `KeyError: '_exposure'` 那个事故
就是只改了两处。重挂走 `_attach_pipeline`（与 lut/grade/曝光同一条担心："会话迁了、
图层没迁"），判据用 live 字段是否为中性值。

顺带修掉一条同类缺陷：曝光层的重挂判据原来只看 `(ev, temperature_shift, tint_shift)`
三元组，而 `cmd_exposure` 允许**只给 `reference_k`**（EV/偏移全 0）——那时三元组是中
性的，整段重挂被跳过，新会话的参考光源退回默认 6500，而 `doc_state` 报的仍然是来片
那个 K：上报与实际双向错配。判据补成"三元组非中性**或** reference_k 非空"。

### 8. `doc_state` 里 crop 是一层，不是 exposure 的一个键

第一版把 `crop` 嵌进了 `exposure` 那个字典字面里（缩进也一样），宿主按
`doc_state["crop"] 取永远拿到 `None`，而这份错在 JSON 里看起来完全自洽——正是本仓反复出事的
那一类"错得看不出来"。现在 `crop` 是顶层键，量程取自 `ops.geometry.MAX_ANGLE` 这一份
出处（`doc_state` 里那份 `[-180, 180]` 字面量一并删掉：UI 自己抄的数与引擎实际拒的数
迟早分叉）。用例：`test_doc_state_reports_crop_as_its_own_layer`。

### 9. 命令面沿用"整组校验后一次提交"那套铁律

`cmd_crop` 与 `cmd_exposure` 同形：跑靶互斥、rect 与 rotation 整组校过才提交、被拒
一个字段都不留、出帧失败回滚并补帧、事件只有一个组装点。另外立了一条：

* `crop set` 什么也没给（既无 rect 又无 rotation）→ 拒，并提示走 `clear`。
  静默按当前值"重提交一次"会发一帧而什么都不改，报表上就是一次没发生的编辑。

`EDIT_CMDS` 加了 `crop`，所以 Ctrl+Z 必须逐字节回到剪之前
（`test_crop_is_undoable_step_by_step`）。分发表也不再手抄第二份：`Engine.HANDLED`
是唯一名单，`_dispatch_table()` 按它取 `cmd_*`，双向守卫（名单里有而没有方法、
有方法而没进名单）都在开工第一帧响。

## 后果与证据

* `ops/geometry.py`（两臂 + `_cut` + `out_size`）；`test_geometry.py` 13 条；
  `test_protocol.py` 裁剪组 9 条端到端（中性逐字节、真剪改变画面、尺寸与文件对账、
  非法 rect 被拒且**连一帧都不补发**、撤销/重做逐字节、留存区零改动、
  doc_state 分层、跨设备重挂、16-bit 点名拒绝）。
* 取证过程中暴露的测试写法错误（都是本轮真踩的，已写进 helper 的 docstring）：
  ① 命令出的那帧就是最后一帧，再 `_read_frame` 等第二帧只会空等 10 s；
  ② 拿"下一个非静默事件"当本命令的帧会把 load_image 补发帧当成 crop 帧（KeyError）；
     判据必须落在事件自己的 `mode` 字段上（`_wait_frame_mode`）；
  ③ `_collect_until` 把"两帧之间静默 10 s"当成失败——真机上 RAW 解码 + 第一次全幅
     渲染确实会静默十几秒，只在最慢机器上响的失败不是证据；
  ④ `_nudge_frame` 发的是 `strength=` 而 `cmd_set_strength` 只认 `value=`：写错的键被
     静默忽略，帧照出、基线照拿，用例仍然"通过"。已改成 `value=` 并把这条写进注释。
* 三套证据：运行时 venv（有 torch、GPU 可见）**682 passed / 2 skipped**；开发 venv
  384 passed / 261 skipped；`check-release.sh` 与 `check-tests-runtime.sh` 全过。
