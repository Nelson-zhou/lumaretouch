"""系统文件拖入（DoD §5「任意拖入真机人像或 DNG 照片」）的形状守卫。

为什么这几条写在 pytest 里而不是只写在真窗口那一臂：装机壳里的 OS 拖拽需要一个人
坐在机器前拖一次，那进不了发布门禁。能静态判的就静态判死——**挂错事件源**（HTML5
dataTransfer 在 Tauri 壳里拿不到路径）、**名单刻在两份上**（引擎加了 RAW 后缀而前端
不跟着变）、**环境变量没透传**（上一轮 auto_pick 就是漏在桥那一格）这三类错，每条
都曾经靠肉眼发现。
"""
from __future__ import annotations

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
    assert 'className="openPhoto"' in top, "顶栏最左侧没有常驻的「打开照片」"
    assert "openAndImport()" in top, "顶栏按钮没接上同一条入口"


def test_empty_state_copy_is_defined_in_both_languages():
    for k in ("empty.open", "empty.openBtn", "empty.hint"):
        assert f'"{k}"' in ZH and f'"{k}"' in EN, f"缺文案键 {k}"
    assert "点击打开照片，或将照片拖入此处" in ZH, "空状态卡片的原话丢了"
    used = set(re.findall(r't\("(empty\.[a-zA-Z]+)"', APP))
    assert used <= {"empty.open", "empty.openBtn", "empty.hint"}, sorted(used)


def test_auto_empty_env_reaches_the_ui_through_the_host():
    """$LRT_AUTO_EMPTY 要走完 main.rs → m0_env → M0Env 这三格（少一格就是一条静默）。"""
    assert "LRT_AUTO_EMPTY" in MAIN and '"auto_empty"' in MAIN
    assert "auto_empty: string;" in NATIVE
    assert re.search(r"env\?\.auto_empty", APP), "前端没读这一格：第 11 臂永远不会答话"
