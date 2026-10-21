"""系统文件拖入（DoD §5「任意拖入真机人像或 DNG 照片」）的形状守卫。

为什么这几条写在 pytest 里而不是只写在真窗口那一臂：装机壳里的 OS 拖拽需要一个人
坐在机器前拖一次，那进不了发布门禁。能静态判的就静态判死——**挂错事件源**（HTML5
dataTransfer 在 Tauri 壳里拿不到路径）、**名单刻在两份上**（引擎加了 RAW 后缀而前端
不跟着变）、**环境变量没透传**（上一轮 auto_pick 就是漏在桥那一格）这三类错，每条
都曾经靠肉眼发现。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP = (REPO / "ui/src/App.tsx").read_text(encoding="utf-8")
NATIVE = (REPO / "ui/src/native.ts").read_text(encoding="utf-8")
MAIN = (REPO / "ui/src-tauri/src/main.rs").read_text(encoding="utf-8")
ZH = (REPO / "ui/src/locales/zh.ts").read_text(encoding="utf-8")
EN = (REPO / "ui/src/locales/en.ts").read_text(encoding="utf-8")


def _keys(text: str) -> set[str]:
    return set(re.findall(r'"(retouch\.drop\.[a-zA-Z]+)"', text))


def test_drop_uses_the_tauri_event_not_html5_datatransfer():
    """装机壳里 HTML5 的 dataTransfer 拿不到文件路径，只有 Tauri 的 drop 事件有。"""
    assert "onDragDropEvent" in APP, "App.tsx 没挂 Tauri 的 drag-drop 监听：拖进来不会有任何事"
    # 判的是代码而不是注释：从 dataTransfer 取文件在装机壳里永远拿不到路径
    assert not re.search(r"\.dataTransfer\.(files|getData)", APP), \
        "拖入路径改从 dataTransfer 取就等于在装机壳里作废它"


def test_droppable_filter_reads_the_engine_list_and_has_no_local_copy():
    """能不能开只由引擎 ready 报的 image_exts 定；前端不许再刻一份后缀名单。"""
    assert "splitDroppable" in APP
    body = APP[APP.index("export function splitDroppable"):APP.index("const SIZES")]
    assert "exts.includes" in body and "IMAGE_EXT" not in body
    # 拖入那条路上取的是宿主状态里的引擎名单，不是本地常量
    assert re.search(r"splitDroppable\(raw, exts\)", APP), "拖入没把引擎名单交给那份判断"
    assert re.search(r"\?\.image_exts", APP), "可开后缀没从 ready/status 里读"
    # 前端不该有一份 RAW 名单（.cr2/.nef 这类只在引擎那份里数得全）
    for lit in ('".cr2"', '".nef"', '".arw"'):
        assert lit not in body, f"判断里混进了本地 RAW 名单：{lit}"


def test_drop_paths_land_on_the_same_import_as_the_dialog():
    """拖进来与点进来必须汇进同一条 importPath（两份导入就会有一份不报错）。"""
    assert re.search(r"async function onImport\(\) \{ await importPath\(imgPath\); \}", APP)
    assert "await importPath(first)" in APP


def test_auto_drop_env_reaches_the_ui_through_the_host():
    """$LRT_AUTO_DROP 要走完 main.rs → m0_env → M0Env 这三格（少一格就是一条静默）。"""
    assert "LRT_AUTO_DROP" in MAIN and '"auto_drop"' in MAIN
    assert "auto_drop: string;" in NATIVE
    assert re.search(r"auto_drop", APP)


def test_drop_locale_keys_exist_in_both_languages():
    zhk, enk = _keys(ZH), _keys(EN)
    assert {"retouch.drop.tip", "retouch.drop.active", "retouch.drop.scanned",
            "retouch.drop.onlyFirst", "retouch.drop.unsupported"} <= zhk, sorted(zhk)
    assert zhk == enk, f"中英名单不一致：zh-en={sorted(zhk - enk)} en-zh={sorted(enk - zhk)}"
    # 用到的键必须都在（写错一个 key 就是屏幕上露出一串裸 id）
    used = set(re.findall(r't\("(retouch\.drop\.[a-zA-Z]+)"', APP))
    assert used <= zhk, f"用了没定义的文案键：{sorted(used - zhk)}"


def test_empty_state_and_topbar_share_one_click_open():
    """空状态卡片与顶栏「打开照片」必须是同一条一次点击的入口（1.10.0 收官）。

    这一条判三件事，每件都是"控件看着在、其实没接通"的形状：
    ① 卡片只在没有图时出现（有图了还盖着 = 挡住精修）；
    ② 点卡片真的开选择框并**立刻导入**（选完还要再按一下导入，用户会以为按钮坏了）；
    ③ 顶栏那颗按钮与之同源（两份入口就会有一份将来忘记改）。
    """
    # ① 只在 !hasImage 时渲染，且是视口覆盖层上的角色按钮
    assert re.search(r"\{!hasImage && \(\s*<div className=\"emptyStage\"", APP), \
        "空状态卡片不是挂在 !hasImage 上的覆盖层"
    assert 'role="button"' in APP and 'tabIndex={0}' in APP, "卡片不可键盘触发"

    # ② 点它走 openAndImport，而那条路自己开框并立刻导入
    i = APP.index("async function openAndImport()")
    body = APP[i:APP.index("\n  }\n", i)]
    assert "openDialog(" in body, "一键打开没有真开选择框"
    assert "await importPath(sel)" in body, "一键打开选完不导入：还差第二次点击"
    assert re.search(r"onClick=\{\(\) => void openAndImport\(\)\}", APP), \
        "卡片或顶栏按钮没有接到 openAndImport"

    # ③ 顶栏那颗按钮同源
    top = APP[APP.index('<header className="topbar">'):APP.index('</header>')]
    assert "openPhoto" in top, "顶栏没有常驻的「打开照片」"
    assert "openAndImport()" in top, "顶栏按钮没接上同一条入口"


def test_empty_state_copy_is_defined_in_both_languages():
    for k in ("empty.open", "empty.openBtn", "empty.hint"):
        assert f'"{k}"' in ZH and f'"{k}"' in EN, f"缺文案键 {k}"
    assert "点击打开照片，或将照片拖入此处" in ZH, "空状态卡片的原话丢了"
    used = set(re.findall(r't\("(empty\.[a-zA-Z]+)"', APP))
    assert used <= {"empty.open", "empty.openBtn", "empty.hint"}, sorted(used)



def test_host_bridge_uses_the_real_tauri_parameter_names():
    """Tauri 的 JS 参数名是 camelCase。上一版 exposure/crop/preset/batch/export 里
    混着 snake_case：Tauri 把不认识的键当“没给”，于是色温/色调/参考白/四项影调、
    旋转、预设作用域、批量策略、16-bit 与 ICC 全是“界面上选了而引擎没收到”，
    回执一切正常。这条守卫只管名字这一层（值时行为由 M0_SPEC 真窗口臂量）。"""
    native = (REPO / "ui/src/native.ts").read_text(encoding="utf-8")
    main = (REPO / "ui/src-tauri/src/main.rs").read_text(encoding="utf-8")
    for good in ("temperatureShift:", "tintShift:", "referenceK:", "rotationDegrees,",
                 "moduleScope: opts.moduleScope", "conflictPolicy: opts.conflictPolicy",
                 "batchId: opts.batchId", "bitDepth:", "outputProfile:",
                 "tiffCompression:", "metadataIncludeGps:"):
        assert good in native, f"宿主桥没把 {good} 递出去（Tauri 会静默丢这个参数）"
    for bad in ("temperature_shift: v.", "rotation_degrees: rotationDegrees",
                "module_scope: opts.moduleScope", "conflict_policy: opts.conflictPolicy",
                "batch_id: opts.batchId", "bit_depth: opts?.bitDepth",
                "output_profile: opts?.outputProfile", "tiff_compression: opts?.tiffCompression",
                "metadata_include_gps: opts?.metadataIncludeGps"):
        assert bad not in native, f"snake_case 键 {bad} 会被 Tauri 静默丢掉"
    # 八色 HSL 那条命令与它的真窗口臂：桥里少一条就是“滑块拖了而引擎没这条命令”
    assert "fn hsl(" in main, "宿主没有 hsl 命令"
    # Registration order is not a contract: new commands may sit between old ones.
    # Inspect actual handler identifiers, not an adjacent three-name substring.
    import re
    handler = main.split("tauri::generate_handler![", 1)[1].split("])", 1)[0]
    handler = re.sub(r"//[^\n]*", "", handler)
    registered = {name.strip() for name in handler.split(",") if name.strip()}
    for command in ("exposure", "hsl", "crop", "curves", "curve_preview"):
        assert command in registered, f"{command} 没注册进 invoke_handler"
    assert "gestureId,interactive,requestId" in native, "曲线请求标识未以 camelCase 传递"
    assert '"auto_spec"' in main and '"keep_open"' in main, "M0_SPEC 的桥缺一格"
    app = APP
    assert "runHsl(" in app and "LRT_AUTO_SPEC" in app, "M0_SPEC 臂或 runHsl 没接上"
    assert 'data-fit-scale' in VIEWER and 'data-frame' in VIEWER, \
        "视口没把 fitScale/帧尺寸画到 DOM 上：100% 探针读不到真倍率"

def test_auto_empty_env_reaches_the_ui_through_the_host():
    """$LRT_AUTO_EMPTY 要走完 main.rs → m0_env → M0Env 这三格（少一格就是一条静默）。"""
    assert "LRT_AUTO_EMPTY" in MAIN and '"auto_empty"' in MAIN
    assert "auto_empty: string;" in NATIVE
    assert re.search(r"env\?\.auto_empty", APP), "前端没读这一格：第 11 臂永远不会答话"


PANEL = (REPO / "ui/src/components/RetouchPanel.tsx").read_text(encoding="utf-8")
VIEWER = (REPO / "ui/src/components/Viewer.tsx").read_text(encoding="utf-8")
SPEC_DIR = REPO / "ui/src/spec"


def _spec(name: str) -> dict:
    return json.loads((SPEC_DIR / name).read_text(encoding="utf-8"))


def test_spec_copies_are_byte_identical_and_complete():
    """规格数据驱动的前提：项目内那四份 JSON 必须与资料包逐字节一致。
    资料包不在本机时退回 manifest 自证（sha256 与条数）；在就必须真比。"""
    man = _spec("manifest.json")
    pairs = [("refine.json", "精修功能规格.json"), ("workflows.json", "工作流规格.json"),
             ("creative.json", "创意工具规格.json"), ("p0.json", "P0参数注册表.json")]
    for dst, src in pairs:
        raw = (SPEC_DIR / dst).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == man["files"][dst]["sha256"], \
            f"{dst} 与 manifest 记的 sha256 不一致（副本被改过）"
        assert len(raw) == man["files"][dst]["bytes"], f"{dst} 字节数漂了"
    ref = _spec("refine.json")
    feats = ref["features"]
    assert len(feats) == 39, f"精修功能规格不是 39 族：{len(feats)}"
    assert sum(len(f.get("subcontrols") or []) for f in feats) == 805, "子控件总数不是 805"
    assert len(_spec("workflows.json")["workflows"]) == 34
    assert len(_spec("creative.json")["tools"]) == 32
    assert len(_spec("p0.json")["entries"]) == 36
    assert man["counts"] == {"features": 39, "subcontrols": 805, "workflows": 34,
                             "tools": 32, "p0_entries": 36}
    # 资料包在场时再逐字节比一次（这才是“前端读的是资料包那一份”的直接证据）
    src_dir = Path(man["source_dir"])
    if src_dir.is_dir():
        for dst, src in pairs:
            raw = (src_dir / src).read_bytes()
            assert raw == (SPEC_DIR / dst).read_bytes(), f"{dst} 与资料包原件不一致"


def test_product_ui_is_spec_driven_and_de_engineered():
    """红线：39 族仍由 SPEC 数据生成；未开放的控件静默置灰。
    产品界面不准出现规格编号、阶段标签、项数徽章或后端实现细节。"""
    assert 'className="hud"' not in APP, "调试 HUD 又回到视口里了"
    assert 'className="bar"' not in APP, "底片条工具条又回来了"
    # 规格树是唯一的功能清单：面板里不许再有手写的分类墙
    assert "buildTree" in PANEL and "SpecNodes" in PANEL, "右栏没有从规格 JSON 生成树"
    assert "<Group title=" not in PANEL, "面板又回到手写分类了"
    assert 'data-spec-total={SPEC_COUNTS.features}' in PANEL
    assert 'data-spec-controls={SPEC_COUNTS.subcontrols}' in PANEL
    assert 'f.id !== "PC-47211"' in PANEL, "人物属性栏没有按 PC-47211 单列"
    # 未开放：保留控件位置、静默置灰；界面上没有 P1 标签
    assert "DisabledRow" in PANEL
    assert "P1 规划中" not in PANEL, "P1 黄色标签又回到界面"
    assert "specId={f.id}" not in PANEL, "规格 ID 又被传进可见控件"
    for bad in ('className="sfamId"', 'className="pgCount"', 'className="specStat"',
                'className="specFoot"', 'className="specP1"', "已接通 ${wiredCount}",
                "39 族", "805 项", "规格 ID", "页面概述"):
        assert bad not in PANEL, f"产品面板里混进了研发元数据：{bad}"
    # 数值输入框与单位是这一轮的质感要求，不能只剩一根滑杆
    assert 'className="pfield"' in PANEL and 'className="pnum"' in PANEL
    assert 'unit="EV"' in PANEL and 'unit="K"' in PANEL
    # 创意 / 导出工作区也不许再贴阶段标签或工具/分类数量
    for bad in ("P1 规划中", "个工具 ·", "个分类", "引擎已接通", "工作流 32483"):
        assert bad not in APP, f"顶部工作区里混进了研发元数据：{bad}"
    assert "disabled" in PANEL
    # 已接通的那 15 项真的挂在命令上（抽样，防“全表被清空还能过”）
    for fn in ("setStrength", "runDeform", "runEnhance", "runExposure", "runLut",
               "runGrade", "runCrop", "runBackground", "runHistory"):
        assert fn in PANEL, f"已接通的命令被摘掉了：{fn}"
    assert "所有人" in PANEL and "FaceAvatar" in PANEL, "人物属性栏缺失"
    for bad in ("LNX-", "名单上", "p95"):
        assert bad not in PANEL, f"产品面板里混进了开发话术：{bad}"
    # 1:1 与 Fit 必须靠平滑重采样，不许用 pixelated 冒充清晰
    assert "imageRendering" not in VIEWER and "pixelated" not in VIEWER, \
        "视口又用像素化硬采样冒充 1:1 了"
    # 产品档代理是 4K 档，不是跑靶预算
    assert "useState(8_294_400)" in APP and "useState(576000)" not in APP


def test_viewport_never_shows_zero_percent_and_uses_floating_capsules():
    """视口顶栏出现过「0%」按钮的低级错误：没有图或 fitScale 还没量到时
    必须隐藏缩放读数或用 100% 占位。对比模式与裁剪收进悬浮胶囊。"""
    assert 'className="stageTools"' not in APP, "旧的顶栏工具条又回来了"
    assert 'className="viewBar"' in APP and 'className="zoomBar"' in APP
    assert 'className={"zoomRead"' in APP and 'srOnly' in APP
    assert 'const zoomPct = !status?.image ? ""' in APP
    assert 'fitScale > 0' in APP and ': "100%"' in APP, \
        "fitScale 未就绪时没有 100% 占位，仍可能显示 0%"
    assert 'className="zoomtag"' not in VIEWER, "视口里还挂着旧的缩放徽标"


def test_one_to_one_zoom_is_recomputed_when_the_window_resizes():
    """4K 验收量到过的一次漂移：100% 是 zoom=1/(dpr*fitScale)，窗口一拉大
    fitScale 就变；只算一次的话徽标会写成 119%，用户看到的已经不是 1:1。
    这一条钉住那个重算 effect，以及「100%」按钮不再拿 !fit 冒充选中态。"""
    assert "const [oneToOne, setOneToOne] = useState(false)" in APP
    assert "if (!oneToOne) return;" in APP, "100% 没有随 fitScale 重算的路径"
    assert "zoom: 1 / Math.max(1e-6, dpr * fitScale)" in APP
    assert 'className={oneToOne ? "on" : ""} onClick={zoomOne}' in APP, \
        "100% 按钮的选中态还挂在 !view.fit 上（自由缩放也会亮）"
    assert "if (v.fit || v.zoom !== view.zoom) setOneToOne(false)" in APP, \
        "滚轮放大后没退出 1:1 档，徽标会继续自称 100%"


def test_doc_report_is_refreshed_by_revision_not_by_source():
    """4K 全幅那一轮的真事故：刷新文档状态时只等 `source == history_state`，
    而宿主一直留着上一笔答复——于是第二次刷新当场读到裁剪前的状态，报告写
    “历史 5 步、crop 还是恒等”。必须等宿主的 doc_rev 真的往前走。
    同一条臂还把引擎的 last_error 带进报告：crop 被整条拒时命令不会抛。"""
    assert "st?.doc_rev ?? 0) > before" in APP, "刷新只认 source，会读到上一笔"
    assert "got.cropErr" in APP, "crop 失败没把引擎原话带进报告"
