// SPDX-License-Identifier: GPL-3.0-or-later
//! Environment-only diagnostic settings, extracted without changing any key.
use serde_json::{json, Value};

/// M0 自动跑靶配置：环境变量传进来，让整条通路可以被脚本驱起来跑。
#[tauri::command]
pub(crate) fn m0_env() -> Value {
    json!({
        "auto_bench": std::env::var("LRT_AUTO_BENCH").unwrap_or_default(),
        "engine_py": std::env::var("LRT_ENGINE_PY").unwrap_or_default(),
        "engine_src": std::env::var("LRT_ENGINE_SRC").unwrap_or_default(),
        // 没设 LRT_DEVICE 时报 "auto"（引擎会把它落实成 cuda/cpu）：这里写死 cpu 就会
        // 让跑靶报表上的设备栏与真用的那个不一致
        "device": std::env::var("LRT_DEVICE").unwrap_or_else(|_| "auto".into()),
        "skip_draw": std::env::var("LRT_SKIP_DRAW").unwrap_or_default(),
        "skip_pixels": std::env::var("LRT_SKIP_PIXELS").unwrap_or_default(),
        "upload": std::env::var("LRT_UPLOAD").unwrap_or_else(|_| "raw".into()),
        "chunks": std::env::var("LRT_CHUNKS").ok()
            .and_then(|v| v.parse::<u32>().ok())
            .filter(|v| (1..=64).contains(v))
            .unwrap_or(1),
        "no_ctx": std::env::var("LRT_NO_CTX").unwrap_or_default(),
        "no_mirror": std::env::var("LRT_NO_MIRROR").unwrap_or_default(),
        "gl_visible": std::env::var("LRT_GL_VISIBLE").unwrap_or_default(),
        // 视口自证探针（M9）：静态图静置后读回画布缓冲并量布局矩形。历轮跑靶的证据取的是
        // shm 那一帧，即“引擎→宿主”那一段；“宿主→屏幕”那一段从没测过，而 WebKitGTK 的
        // GL 表面截图只会抓到纯黑客户区——黑屏与布局撑爆正是从这条缝里漏出去的。
        "viewport_probe": std::env::var("LRT_VIEWPORT_PROBE").unwrap_or_default(),
        "dirty_frac": crate::tiers().dirty_frac,
        "load_image": std::env::var("LRT_LOAD_IMAGE").unwrap_or_default(),
        "max_px": std::env::var("LRT_MAX_PX").ok().and_then(|v| v.parse::<u64>().ok()),
        "precompute": std::env::var("LRT_PRECOMPUTE").unwrap_or_default(),
        "precompute_channel": std::env::var("LRT_PRECOMPUTE_CHANNEL").unwrap_or_default(),
        // 消除笔自动通道："fx:fy:r,…"（坐标按代理帧归一化），跑的是与真人点击同一条链
        "auto_inpaint": std::env::var("LRT_AUTO_INPAINT").unwrap_or_default(),
        // M2-a 三条带增益的自动通道：“mid:broad:detail”。xdotool 的合成点击进不了 WebKit，
        // 所以“滑块能不能过 Rust”这件事只能靠 env 钩子在真窗口里验：命令签名改了而 TS 侧
        // 名字对不上时，Tauri 会静默丢掉那个参数，屏上不动而一个错也不报。
        "auto_skin": std::env::var("LRT_AUTO_SKIN").unwrap_or_default(),
        // M2-a2 修容自动通道：“fx:fy:r:sign,…”（坐标按代理帧归一化，sign 取 +1/-1），
        // 跟自动消除笔同一条链：只有真窗口能证明“TS → Rust → 引擎”这条命令签名对得上。
        "auto_light": std::env::var("LRT_AUTO_LIGHT").unwrap_or_default(),
        "auto_deform": std::env::var("LRT_AUTO_DEFORM").unwrap_or_default(),
        // M3-a2 调色自动通道："amount@<路径>"。与上面几条同一条理由：只有真窗口
        // 能证明 runLut → Rust lut → 引擎 lut_done 这条命令签名对得上。
        "auto_lut": std::env::var("LRT_AUTO_LUT").unwrap_or_default(),
        // M3-b 肤色定向自动通道："dh:ds:dv:amount"。与上面几条同一条理由：只有真窗口
        // 能证明 runGrade → Rust grade → 引擎 grade_done 这条命令签名对得上。
        "auto_grade": std::env::var("LRT_AUTO_GRADE").unwrap_or_default(),
        // 局部调色（COLOR-004）："fx:fy:r:dh:ds:dv"。区域外逐字节不动这一条只能在真窗口量，
        // 所以它与上面几条同一个身份：签名递得到 + 画面真的按作用域在动。
        "auto_local_color": std::env::var("LRT_AUTO_LOCAL_COLOR").unwrap_or_default(),
        // 眼牙增强（LNX-PORTRAIT-009）："sclera:iris:teeth"。与上面几条同一个身份：
        // 只有真窗口能证明 runEnhance → Rust enhance → 引擎 enhance_done 这条签名对得上。
        "auto_enhance": std::env::var("LRT_AUTO_ENHANCE").unwrap_or_default(),
        "auto_face": std::env::var("LRT_AUTO_FACE").unwrap_or_default(),
        // 人工纠正优先（LNX-PORTRAIT-006）那一臂。上一轮 auto_pick 就是漏在这一行没写：
        // 脚本传了 env、App.tsx 有臂，而桥不转发，于是那条臂**从没跑过**而外面只知道
        // "等满了超时"。桥层漏一个键 = 一条臂静静消失，所以这一格必须与 App.tsx 的臂同名
        "auto_manual": std::env::var("LRT_AUTO_MANUAL").unwrap_or_default(),
        // 1.12 规格工作台那一臂（$LRT_AUTO_SPEC=<JSON>）：100% 视口 + 曝光/影调 +
        // 八色 HSL + 磨皮 + 瘦脸 + 裁剪旋转走用户那条链。这一格与 App.tsx 的臂同名，
        // 漏一行就是“脚本传了 env、臂从没跑过、外面只等到超时”。
        "auto_spec": std::env::var("LRT_AUTO_SPEC").unwrap_or_default(),
        // 取证臂：跑完自动序列后不退出，留给截图/人工核对（默认不设=照旧退出）。
        "keep_open": std::env::var("LRT_KEEP_OPEN").unwrap_or_default(),
        "auto_drop": std::env::var("LRT_AUTO_DROP").unwrap_or_default(),
        "auto_empty": std::env::var("LRT_AUTO_EMPTY").unwrap_or_default(),
        // M4 导出自动通道："<目录>@<格式>@<tile>"（tile 与格式可省）。真窗口跑这一条
        // 才能证明 runExport → Rust export → 引擎 export_done 对得上，而且落盘文件
        // 的尺寸是“满幅不是代理档”的唯一直接证据
        "auto_export": std::env::var("LRT_AUTO_EXPORT").unwrap_or_default(),
        // 底片条自动通道："<目录>[@<选中第几张>[@<edge>]]"，给真窗口确认轮用
        "auto_filmstrip": std::env::var("LRT_AUTO_FILMSTRIP").unwrap_or_default(),
        // 撤销/重做自动通道：<强度值>，给真窗口确认轮用。它验的不是引擎（引擎有
        // 协议用例逐字节对拍），而是 runHistory → Rust history → 引擎 history_state
        // 这条命令签名在真窗口里对不对得上——Tauri 参数名不匹配时是静默丢参数。
        // 换底自检（M6）：非空则前端自动走一次色键换底（“rrggbb:tol:softness”）
        "auto_background": std::env::var("LRT_AUTO_BG").unwrap_or_default(),
        "auto_history": std::env::var("LRT_AUTO_HISTORY").unwrap_or_default(),
        // 发布自检（M5-c）：非空则让前端报一条 M0_RELEASE（解释器来历 + 版本 + 能力）
        "auto_release": std::env::var("LRT_AUTO_RELEASE").unwrap_or_default(),
        // 挑图建议（LNX-PICK-001）自动通道："<重复>/<清晰>/<曝光>/<眼睛>"。
        // 这一格上一轮漏过一次：前端 M0Env 声明了 auto_pick，而宿主少返回一个键，
        // TS 编译期看不出来（引擎交回来的是无类型 JSON），表现是「引擎算得对而屏幕上
        // 一次都没点火」。键名单的双向守卫在 engine/tests/test_pick.py 里钉着。
        "auto_pick": std::env::var("LRT_AUTO_PICK").unwrap_or_default(),
    })
}
