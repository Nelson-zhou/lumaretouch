//! 引擎子进程：spawn + JSON lines 事件回读。

use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{mpsc, Arc, Mutex};
use std::thread;

use serde_json::Value;

use crate::shm::ShmReader;
use crate::AppState;

pub struct EngineHandle {
    stdin: Arc<Mutex<ChildStdin>>,
    child: Arc<Mutex<Child>>,
    alive: Arc<AtomicBool>,
}

impl EngineHandle {
    pub fn send(&self, cmd: Value) -> Result<(), String> {
        let mut stdin = self.stdin.lock().map_err(|_| "stdin 锁中毒".to_string())?;
        let line = serde_json::to_string(&cmd).map_err(|e| e.to_string())?;
        stdin
            .write_all(line.as_bytes())
            .and_then(|_| stdin.write_all(b"\n"))
            .and_then(|_| stdin.flush())
            .map_err(|e| format!("写引擎 stdin 失败: {e}"))
    }

    pub fn pid(&self) -> u32 {
        self.child.lock().map(|c| c.id()).unwrap_or(0)
    }

    pub fn is_alive(&self) -> bool {
        self.alive.load(Ordering::Relaxed)
    }

    pub fn shutdown(&self) {
        let _ = self.send(serde_json::json!({"cmd": "shutdown"}));
        if let Ok(mut c) = self.child.lock() {
            let _ = c.wait();
        }
    }
}

/// 启动引擎并开两个读线程（stdout 事件 / stderr 日志）。
pub fn spawn(py: &str, engine_src: &str, session: &str, state: Arc<AppState>) -> EngineHandle {
    let mut child = Command::new(py)
        .arg("-m")
        .arg("lumaretouch_engine.server")
        .arg("--session")
        .arg(session)
        .env("PYTHONPATH", engine_src)
        .env("PYTHONUNBUFFERED", "1")
        // 不往只读的资源目录里写 __pycache__
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap_or_else(|e| panic!("启动引擎失败 ({py}): {e}"));

    let stdin = Arc::new(Mutex::new(child.stdin.take().expect("拿不到引擎 stdin")));
    let stdout = child.stdout.take().expect("拿不到引擎 stdout");
    let stderr = child.stderr.take().expect("拿不到引擎 stderr");
    let alive = Arc::new(AtomicBool::new(true));

    let (tx, rx) = mpsc::channel::<String>();
    {
        let alive = alive.clone();
        thread::spawn(move || {
            for line in BufReader::new(stdout).lines() {
                match line {
                    Ok(l) => {
                        if tx.send(l).is_err() {
                            return;
                        }
                    }
                    Err(_) => break,
                }
            }
            alive.store(false, Ordering::Relaxed);
        });
    }
    {
        let st = state.clone();
        thread::spawn(move || {
            for line in BufReader::new(stderr).lines() {
                if let Ok(l) = line {
                    st.push_log(l);
                }
            }
        });
    }

    {
        let st = state.clone();
        thread::spawn(move || {
            while let Ok(line) = rx.recv() {
                handle_event(&st, &line);
            }
        });
    }

    EngineHandle {
        stdin,
        child: Arc::new(Mutex::new(child)),
        alive,
    }
}

fn handle_event(state: &Arc<AppState>, line: &str) {
    let v: Value = match serde_json::from_str(line) {
        Ok(v) => v,
        Err(_) => {
            state.push_log(format!("引擎非 JSON 输出: {line}"));
            return;
        }
    };
    match v.get("event").and_then(|e| e.as_str()).unwrap_or("") {
        "shm_ready" => {
            let name = v["name"].as_str().unwrap_or("").to_string();
            match ShmReader::open(&name) {
                Ok(reader) => state.attach_shm(reader, name),
                Err(e) => state.push_log(format!("打开共享内存失败: {e}")),
            }
        }
        "frame" => state.on_frame_event(),
        "ready" => {
            // M3-b：引擎报上来的内置预设清单（按钮文字与提交名都靠它）。
            // 不写这一臂就会落进下面的 other 分支：只进日志，前端永远拿不到。
            state.on_ready(&v);
            println!("M0_ENGINE {line}");
        }
        "image_ready" => {
            // 代理档尺寸与解码耗时是前端开跑靶与报表采集的唯一依据，既存下也回显
            state.on_image_ready(&v);
            println!("M0_ENGINE {line}");
        }
        "precompute_ready" => {
            // 478 点 / 掩膜通道 / 常驻设备：同样是“前端轮询 + 跑靶采集”两份用
            state.on_precompute_ready(&v);
            println!("M0_ENGINE {line}");
        }
        "inpaint_done" => {
            // 消除笔是事件驱动的：一次松手一条，轮询不到就会错过
            state.on_inpaint_ready(&v);
            println!("M0_ENGINE {line}");
        }
        "light_done" => {
            // 修容笔同上：一次事件一条，而且它与消除笔各自一份结果，不能串台
            state.on_light_ready(&v);
            println!("M0_ENGINE {line}");
        }
        "deform_done" => {
            // M2-b 五官微调：三个滑块一条。真窗口跑靶靠它采 deform_ms / bytes_deform
            state.on_deform_ready(&v);
            println!("M0_ENGINE {line}");
        }
        "lut_done" => {
            // M3-a2 影楼色彩：set/amount/clear 一条。与 deform 分开存：它报的是调色段
            // 与表的常驻字节，与形变的账不是一个量（串台就是报表上看不出谁花的钱）
            state.on_lut_ready(&v);
            println!("M0_ENGINE {line}");
        }
        "grade_done" => {
            // M3-b 肤色定向：与 lut 分开存。预设走 lut_done 时也会带一份 grade_state，
            // 但那一层自己的耗时/上限/事件次序只有 grade_done 能说全
            state.on_grade_ready(&v);
            println!("M0_ENGINE {line}");
        }
        "bg_done" => {
            // M6 换底：一次“换底”事件一条（与 inpaint/light/grade 同为事件驱动）。
            // 分开存：它报的是合成耗时与遮罩常驻字节，与其它层的账不是一个量。
            state.on_bg_ready(&v);
            println!("M0_ENGINE {line}");
        }
        "bench_done" => {
            state.on_bench_done();
            println!("M0_ENGINE {line}");
        }
        "export_progress" => {
            // M4 批量出片：逐图一条。它落在 other 分支就会只进日志不进状态，
            // 而 UI 的进度条要的恰好是“第几张 / 共几张”这句话
            state.on_export_progress(&v);
            println!("M0_ENGINE {line}");
        }
        "export_done" => {
            // 终态：每张的尺寸/字节/块数/margin，以及逐图 skipped 与失败原因。
            // 必须回显：跑靶脚本靠它量“导出的是满幅不是代理档”
            state.on_export_ready(&v);
            println!("M0_ENGINE {line}");
        }
        "session_state" => {
            // M5-a 底片条：格子列表 + 当前哪一格。载荷不带像素，可以进轮询；
            // 但这一条也高频（每次开关图与每批缩略图之后各一条），所以只回显摘要，
            // 不把整份 docs 数组刷进 stdout
            state.on_session_state(&v);
            println!("M0_SESSION count={} index={} thumbs_running={}",
                v["count"].as_i64().unwrap_or(-1), v["index"].as_i64().unwrap_or(-1),
                v["thumbs_running"].as_bool().unwrap_or(false));
        }
        "thumb_ready" => {
            // 缩略图：像素按 path 存进宿主，不进 stdout（一张 7 KB，两百张就是 1.4 MB 日志）
            state.on_thumb(&v);
        }
        "history_state" => {
            // M5-b 撤销/重做：整条 payload 回显。跑靶要在真窗口里量 history_ms 与栈深，
            // 而这一份只有数字与图层计数（没有像素），不会把 stdout 撑爆
            state.on_history(&v);
            println!("M0_HISTORY {line}");
        }
        "thumb_failed" => {
            state.on_thumb(&v);
            state.push_log(format!("缩略图解不开: {}", v["path"].as_str().unwrap_or("?")));
            println!("M0_THUMB_FAILED {line}");
        }
        "error" => {
            state.push_log(format!("引擎错误: {}", v["error"].as_str().unwrap_or("?")));
            // 必须回显到标准输出：跑靶脚本只看得见 stdout。不往这里印的话，
            // “某一臂被引擎拒了”在日志里一个字都不留，表现为静默超时。
            println!("M0_ENGINE {line}");
        }
        other => {
            state.push_log(format!("事件 {other}: {v}"));
            // 引擎侧分段耗时（synth/pipe/rgba/shm/notify）是「帧率天花板卡在
            // 哪一段」的唯一直接证据，高频事件不刷，其余回显给跑靶脚本采集。
            if other != "bench_progress" {
                println!("M0_ENGINE {line}");
            }
        }
    }
}
