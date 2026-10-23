//! 引擎子进程：spawn + JSON lines 事件回读。

use std::io::{self, BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{mpsc, Arc, Mutex};
use std::thread;

use serde_json::{json, Value};

use crate::shm::ShmReader;
use crate::AppState;

/// The normal dispatcher and cancellation control lane share exactly one writer.
/// Each complete JSON line holds this mutex until every byte has been written.
#[derive(Clone)]
struct EngineInput(Arc<Mutex<Option<ChildStdin>>>);
impl EngineInput {
    fn with_writer<T>(&self, write: impl FnOnce(&mut ChildStdin) -> io::Result<T>) -> io::Result<T> {
        let mut guard = self.0.lock().map_err(|_| io::Error::new(io::ErrorKind::Other, "engine stdin lock poisoned"))?;
        let writer = guard.as_mut().ok_or_else(|| io::Error::new(io::ErrorKind::BrokenPipe, "engine stdin closed"))?;
        write(writer)
    }
    fn close(&self) {
        // Recover the writer even after poisoning: all clones must observe EOF.
        let mut guard = self.0.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
        drop(guard.take());
    }
}
impl Write for EngineInput {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> { self.with_writer(|writer| writer.write(bytes)) }
    fn write_all(&mut self, bytes: &[u8]) -> io::Result<()> { self.with_writer(|writer| writer.write_all(bytes)) }
    fn flush(&mut self) -> io::Result<()> { self.with_writer(|writer| writer.flush()) }
}

pub struct EngineHandle {
    epoch:[u8;16],
    dispatcher: Arc<crate::dispatch::Dispatcher>,
    input: EngineInput,
    child: Arc<Mutex<Child>>,
    alive: Arc<AtomicBool>,
    inspection_root: Arc<crate::inspection_io::Root>,
}

impl EngineHandle {
    pub fn epoch(&self)->[u8;16]{self.epoch}
    pub fn send(&self, cmd: Value) -> Result<(), String> {
        if cmd["cmd"] == "virtual_copy" && matches!(cmd["action"].as_str(), Some("state" | "query")) {
            return self.dispatcher.enqueue(None, cmd);
        }
        // Some reviewed native APIs send directly, outside AppState dispatch.
        // Fence them too, including shutdown; library reads are explicitly exempt.
        if cmd["cmd"] != "preset_organisation" && crate::sample_library_api::invalidates_capture(&cmd) && !crate::semantic_colour_api::read_only(&cmd) && !crate::shoulder_shape_api::read_only(&cmd) && !crate::leg_shape_api::read_only(&cmd) && !crate::waist_shape_api::read_only(&cmd) && !crate::leg_length_api::read_only(&cmd) && !crate::neck_shape_api::read_only(&cmd) && !crate::arm_shape_api::read_only(&cmd) {
            crate::sample_library_api::invalidate_captures(self)?;
        }
        if cmd["cmd"] != "preset_organisation" && crate::semantic_colour_api::invalidates_capture(&cmd) && !crate::shoulder_shape_api::read_only(&cmd) && !crate::leg_shape_api::read_only(&cmd) && !crate::waist_shape_api::read_only(&cmd) && !crate::leg_length_api::read_only(&cmd) && !crate::neck_shape_api::read_only(&cmd) && !crate::arm_shape_api::read_only(&cmd) { crate::semantic_colour_api::invalidate_captures(self)?; }
        self.dispatcher.enqueue(None, cmd)
    }

    /// Cancellation is the only out-of-band command. It must reach the Python
    /// reader while the acknowledged command is still rendering/importing.
    pub(crate) fn cancel_sample_library(&self,request_id:&str)->Result<(),String>{self.cancel_owned_request("sample_library_cancel",request_id)}
    pub(crate) fn cancel_semantic_colour(&self,request_id:&str)->Result<(),String>{self.cancel_owned_request("semantic_colour_cancel",request_id)}
    fn cancel_owned_request(&self, command:&str, request_id: &str) -> Result<(), String> {
        if !self.is_alive() { return Err("引擎已结束；取消结果未确认".into()); }
        let mut line = serde_json::to_vec(&json!({"cmd":command, "request_id":request_id}))
            .map_err(|error| error.to_string())?;
        line.push(b'\n');
        if let Err(error) = self.input.with_writer(|writer| writer.write_all(&line).and_then(|_| writer.flush())) {
            self.dispatcher.close();
            self.input.close();
            return Err(format!("取消请求写入失败，未重试：{error}"));
        }
        Ok(())
    }

    pub fn send_interactive(&self, key: String, cmd: Value) -> Result<(), String> {
        if cmd["cmd"] != "preset_organisation" && crate::sample_library_api::invalidates_capture(&cmd) && !crate::semantic_colour_api::read_only(&cmd) && !crate::shoulder_shape_api::read_only(&cmd) && !crate::leg_shape_api::read_only(&cmd) && !crate::waist_shape_api::read_only(&cmd) && !crate::leg_length_api::read_only(&cmd) && !crate::neck_shape_api::read_only(&cmd) && !crate::arm_shape_api::read_only(&cmd) {
            crate::sample_library_api::invalidate_captures(self)?;
        }
        if cmd["cmd"] != "preset_organisation" && crate::semantic_colour_api::invalidates_capture(&cmd) && !crate::shoulder_shape_api::read_only(&cmd) && !crate::leg_shape_api::read_only(&cmd) && !crate::waist_shape_api::read_only(&cmd) && !crate::leg_length_api::read_only(&cmd) && !crate::neck_shape_api::read_only(&cmd) && !crate::arm_shape_api::read_only(&cmd) { crate::semantic_colour_api::invalidate_captures(self)?; }
        self.dispatcher.enqueue(Some(key), cmd)
    }

    pub fn queue_stats(&self) -> Value { self.dispatcher.stats() }

    pub fn pid(&self) -> u32 {
        self.child.lock().map(|c| c.id()).unwrap_or(0)
    }

    pub fn is_alive(&self) -> bool {
        self.alive.load(Ordering::Relaxed)
    }

    pub fn shutdown(&self) {
        let _ = self.send(serde_json::json!({"cmd": "shutdown"}));
        if let Ok(mut c) = self.child.lock() {
            if c.wait().is_ok(){
                self.alive.store(false,Ordering::Relaxed);
                let _=self.inspection_root.cleanup();
            }
        }
    }
}

/// 启动引擎并开两个读线程（stdout 事件 / stderr 日志）。
pub fn spawn(py: &str, engine_src: &str, session: &str, state: Arc<AppState>,
             inspection_epoch:[u8;16],inspection_root:Arc<crate::inspection_io::Root>) -> EngineHandle {
    let mut child = Command::new(py)
        .arg("-m")
        .arg("lumaretouch_engine.server")
        .arg("--session")
        .arg(session)
        .env("PYTHONPATH", engine_src)
        .env("PYTHONUNBUFFERED", "1")
        // 不往只读的资源目录里写 __pycache__
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("LRT_PARENT_PID",std::process::id().to_string())
        .env("LRT_INSPECTION_ROOT",&inspection_root.path)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap_or_else(|e| panic!("启动引擎失败 ({py}): {e}"));

    let input = EngineInput(Arc::new(Mutex::new(Some(child.stdin.take().expect("拿不到引擎 stdin")))));
    let dispatcher = crate::dispatch::Dispatcher::new();
    {
        let d=dispatcher.clone(); let st=state.clone(); let stdin=input.clone();
        thread::spawn(move || {
            if let Err(error) = d.run(stdin.clone()) { d.close(); st.push_log(error); }
            // The handle retains a control-lane clone; explicitly close every
            // clone after dispatch ends so write failures cannot suppress EOF.
            stdin.close();
        });
    }
    let stdout = child.stdout.take().expect("拿不到引擎 stdout");
    let stderr = child.stderr.take().expect("拿不到引擎 stderr");
    let child=Arc::new(Mutex::new(child));
    let alive = Arc::new(AtomicBool::new(true));

    let (tx, rx) = mpsc::channel::<String>();
    {
        let alive = alive.clone();
        let d = dispatcher.clone();
        let process=child.clone();let st=state.clone();let root=inspection_root.clone();
        thread::spawn(move || {
            for line in BufReader::new(stdout).lines() {
                match line {
                    Ok(l) => {
                        if tx.send(l).is_err() { break; }
                    }
                    Err(_) => break,
                }
            }
            drop(tx); // Let the consumer drain receipts without waiting for process cleanup.
            alive.store(false, Ordering::Relaxed);
            d.close();
            let exited=process.lock().map(|mut c|c.wait().is_ok()).unwrap_or(false);
            st.on_inspection_engine_end(inspection_epoch);
            st.color_capture.lock().unwrap().engine_ended(inspection_epoch);
            st.source_patch_capture.lock().unwrap().engine_ended(inspection_epoch);
            st.white_balance_capture.lock().unwrap().engine_ended(inspection_epoch);
            st.color_picker_capture.lock().unwrap().engine_ended(inspection_epoch);
            if exited{if let Err(e)=root.cleanup(){st.push_log(format!("inspection cleanup: {e}"));}}
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
        let d = dispatcher.clone();
        thread::spawn(move || {
            while let Ok(line) = rx.recv() {
                if let Ok(v)=serde_json::from_str::<Value>(&line) {
                    if v["event"]=="ready" && v["command_ack"].as_u64()!=Some(1) {
                        let why="宿主与引擎不匹配：引擎缺少命令完成回执，请使用同一版本的配套引擎";
                        *st.last_error.lock().unwrap()=Some(why.into());
                        st.push_log(why.into());
                        d.close();
                    }
                    if v["event"]=="command_done" {
                        if let Some(id)=v["request_id"].as_u64() {d.acknowledge(id);}
                        continue;
                    }
                }
                handle_event(&st, &line,inspection_epoch);
            }
            // Drain every accepted stdout event before synthesizing unknown outcomes.
            crate::shoulder_shape_api::ended(inspection_epoch);
            crate::leg_shape_api::ended(inspection_epoch);
            crate::waist_shape_api::ended(inspection_epoch);
            crate::leg_length_api::ended(inspection_epoch);
            crate::neck_shape_api::ended(inspection_epoch);
            crate::arm_shape_api::ended(inspection_epoch);
            crate::people_api::ended(inspection_epoch);
            crate::hair_colour_api::ended(inspection_epoch);
            crate::sample_library_api::ended(inspection_epoch);
            crate::preset_organisation_api::ended(inspection_epoch);
            crate::semantic_colour_api::ended(inspection_epoch);
            st.batch_results.lock().unwrap().ended(inspection_epoch);
            st.preset_results.lock().unwrap().ended(inspection_epoch);
            st.white_balance_results.lock().unwrap().ended(inspection_epoch);
            st.color_picker_results.lock().unwrap().ended(inspection_epoch);
            st.color_picker_probes.lock().unwrap().ended(inspection_epoch);
            st.source_patch.lock().unwrap().ended(inspection_epoch);
            st.local_masks.lock().unwrap().ended(inspection_epoch);
            st.sky_replacement.lock().unwrap().ended(inspection_epoch);
            st.sky_preview.lock().unwrap().ended(inspection_epoch);
            st.sky_semantic.lock().unwrap().ended(inspection_epoch);
            st.optics.lock().unwrap().ended(inspection_epoch);
            st.optics_preview.lock().unwrap().ended(inspection_epoch);
            st.studio_background.lock().unwrap().ended(inspection_epoch);
            st.studio_background_preview.lock().unwrap().ended(inspection_epoch);
            st.manual_liquify.lock().unwrap().ended(inspection_epoch);
            st.liquify_preview.lock().unwrap().ended(inspection_epoch);
            st.effect_recovery.lock().unwrap().ended(inspection_epoch);
            st.recovery_preview.lock().unwrap().ended(inspection_epoch);
            st.local_grade_live.lock().unwrap().ended(inspection_epoch);
            st.prompted_masks.lock().unwrap().ended(inspection_epoch);
        });
    }

    EngineHandle {
        epoch:inspection_epoch,
        dispatcher,
        input,
        child,
        alive,
        inspection_root,
    }
}

fn handle_event(state: &Arc<AppState>, line: &str,inspection_epoch:[u8;16]) {
    if state.inspection.lock().unwrap().epoch!=inspection_epoch{return;}
    let v: Value = match serde_json::from_str(line) {
        Ok(v) => v,
        Err(_) => {
            state.push_log(format!("引擎非 JSON 输出: {line}"));
            return;
        }
    };
    match v.get("event").and_then(|e| e.as_str()).unwrap_or("") {
        "inspection_snapshot"=>state.on_inspection_event(inspection_epoch,&v),
        "shoulder_shape_result" => { crate::shoulder_shape_api::receive(inspection_epoch, &v); if v.get("doc_state").is_some() { state.on_layer_frame(&v); } },
        "leg_shape_result" => { crate::leg_shape_api::receive(inspection_epoch, &v); if v.get("doc_state").is_some_and(|doc| doc.is_object()) { state.on_layer_frame(&v); } },
        "waist_shape_result" => { crate::waist_shape_api::receive(inspection_epoch, &v); if v.get("doc_state").is_some_and(|doc| doc.is_object()) { state.on_layer_frame(&v); } },
        "leg_length_result" => { crate::leg_length_api::receive(inspection_epoch, &v); if v.get("doc_state").is_some_and(|doc| doc.is_object()) { state.on_layer_frame(&v); } },
        "neck_shape_result" => { crate::neck_shape_api::receive(inspection_epoch, &v); if v.get("doc_state").is_some_and(|doc| doc.is_object()) { state.on_layer_frame(&v); } },
        "arm_shape_result" => { if crate::arm_shape_api::receive(inspection_epoch, &v) && v["action"] == "execute" && v.get("doc_state").is_some_and(|doc| doc.is_object()) { state.on_layer_frame(&v); } },
        "semantic_colour_result" => crate::semantic_colour_api::receive(inspection_epoch, &v),
        "semantic_colour_progress" => crate::semantic_colour_api::progress(inspection_epoch, &v),
        "hair_colour_result" => { crate::hair_colour_api::receive(inspection_epoch, &v); if v.get("doc_state").is_some_and(|doc| doc.is_object()) { state.on_layer_frame(&v); } },
        "photo_grain_result" | "photo_grain_preview" | "photo_grain_readback" => { crate::photo_grain_api::receive(inspection_epoch, &v); if v.get("doc_state").is_some_and(|d|d.is_object()) { state.on_layer_frame(&v); } if v.get("frame").is_some_and(|f|f.is_object()) { state.on_frame_event(); } },
        "colour_grading_result" | "colour_grading_preview" | "colour_grading_readback" => { crate::colour_grading_api::receive(inspection_epoch, &v); if v.get("doc_state").is_some_and(|d|d.is_object()) { state.on_layer_frame(&v); } if v.get("frame").is_some_and(|f|f.is_object()) { state.on_frame_event(); } },
        "selective_colour_result" | "selective_colour_preview" | "selective_colour_readback" => { crate::selective_colour_api::receive(inspection_epoch, &v); if v.get("doc_state").is_some_and(|d|d.is_object()) { state.on_layer_frame(&v); } if v.get("frame").is_some_and(|f|f.is_object()) { state.on_frame_event(); } },
        "colour_editor_result" | "colour_editor_preview" | "colour_editor_readback" | "colour_editor_sample" => { crate::colour_editor_api::receive(inspection_epoch, &v); if v.get("doc_state").is_some_and(|d|d.is_object()) { state.on_layer_frame(&v); } if v.get("frame").is_some_and(|f|f.is_object()) { state.on_frame_event(); } },
        "primary_calibration_result" | "primary_calibration_preview" | "primary_calibration_readback" => { crate::primary_calibration_api::receive(inspection_epoch, &v); if v.get("doc_state").is_some_and(|d|d.is_object()) { state.on_layer_frame(&v); } if v.get("frame").is_some_and(|f|f.is_object()) { state.on_frame_event(); } },
        "photo_detail_result" | "photo_detail_readback" => { crate::photo_detail_api::receive(inspection_epoch, &v); if v.get("doc_state").is_some_and(|d|d.is_object()) { state.on_layer_frame(&v); } },
        "extended_tone_result" | "extended_tone_readback" => { crate::extended_tone_api::receive(inspection_epoch, &v); if v.get("doc_state").is_some_and(|d|d.is_object()) { state.on_layer_frame(&v); } },
        "custom_lut_result" => { crate::custom_lut_api::receive(inspection_epoch, &v); if v.get("doc_state").is_some_and(|d|d.is_object()) { state.on_layer_frame(&v); } },
        "export_destination_result" => crate::export_destination_port::receive(inspection_epoch, &v),
        "virtual_copy_result" => crate::virtual_copy_api::receive(inspection_epoch, &v),
        "project_package_result" => crate::project_package_api::receive(inspection_epoch, &v),
        "source_relocation_result" => crate::source_relocation_api::receive(inspection_epoch, &v),
        "preset_organisation_result" => crate::preset_organisation_api::receive(inspection_epoch, &v),
        "sample_library_result" => crate::sample_library_api::receive(inspection_epoch, &v),
        "sample_library_cancel_ack" => (),
        "batch_result"=>state.batch_results.lock().unwrap().receive(inspection_epoch,&v),
        "people_result" => {
            crate::people_api::receive(inspection_epoch, &v);
            if v.get("doc_state").is_some() { state.on_layer_frame(&v); }
        },
        "brow_shape_result"=>{crate::brow_shape_api::receive(inspection_epoch,&v);if v.get("doc_state").is_some(){state.on_layer_frame(&v);}},
        "nose_shape_result"=>{crate::nose_shape_api::receive(inspection_epoch,&v);if v.get("doc_state").is_some(){state.on_layer_frame(&v);}},
        "eye_shape_result"=>{crate::eye_shape_api::receive(inspection_epoch,&v);if v.get("doc_state").is_some(){state.on_layer_frame(&v);}},
        "mouth_shape_result"=>{crate::mouth_shape_api::receive(inspection_epoch,&v);if v.get("doc_state").is_some(){state.on_layer_frame(&v);}},
        "preset_result"=>state.preset_results.lock().unwrap().receive(inspection_epoch,&v),
        "white_balance_result"=>state.white_balance_results.lock().unwrap().receive(inspection_epoch,&v),
        "color_picker_result"=>state.color_picker_results.lock().unwrap().receive(inspection_epoch,&v),
        "color_picker_probe_result"=>state.color_picker_probes.lock().unwrap().receive(inspection_epoch,&v),
        "prompted_masks"=>state.prompted_masks.lock().unwrap().receive(inspection_epoch,&v),
        "local_masks_result"=>state.local_masks.lock().unwrap().receive(inspection_epoch,&v),
        "optics_result"=>state.optics.lock().unwrap().receive(inspection_epoch,&v),
        "optics_preview"=>state.optics_preview.lock().unwrap().receive(inspection_epoch,&v),
        "sky_replacement_result"=>state.sky_replacement.lock().unwrap().receive(inspection_epoch,&v),
        "sky_replacement_preview"=>state.sky_preview.lock().unwrap().receive(inspection_epoch,&v),
        "sky_semantic_result"|"sky_semantic_proposal"=>state.sky_semantic.lock().unwrap().receive(inspection_epoch,&v),
        "id_background_result"=>crate::id_background_api::receive(inspection_epoch,&v),
        "studio_background_result"=>state.studio_background.lock().unwrap().receive(inspection_epoch,&v),
        "studio_background_preview"=>state.studio_background_preview.lock().unwrap().receive(inspection_epoch,&v),
        "manual_liquify_result"=>state.manual_liquify.lock().unwrap().receive(inspection_epoch,&v),
        "manual_liquify_preview"=>state.liquify_preview.lock().unwrap().receive(inspection_epoch,&v),
        "effect_recovery_result"=>state.effect_recovery.lock().unwrap().receive(inspection_epoch,&v),
        "effect_recovery_preview"=>state.recovery_preview.lock().unwrap().receive(inspection_epoch,&v),
        "local_grade_live_result"=>state.local_grade_live.lock().unwrap().receive(inspection_epoch,&v),
        "source_patch_result"=>state.source_patch.lock().unwrap().receive(inspection_epoch,&v),
        "shm_ready" => {
            let name = v["name"].as_str().unwrap_or("").to_string();
            match ShmReader::open(&name) {
                Ok(reader) => {
                    if v.get("frame_identity_version").is_some() || v.get("shm_instance").is_some() {
                        let actual=reader.instance_id().map(crate::frame_identity::hex);
                        if v["frame_identity_version"].as_u64()!=Some(1) ||
                            actual.as_deref()!=v["shm_instance"].as_str() || actual.is_none() {
                            state.push_log("共享帧实例身份不匹配，拒绝绑定".into());return;
                        }
                    }
                    state.attach_shm(reader, name);
                },
                Err(e) => state.push_log(format!("打开共享内存失败: {e}")),
            }
        }
        "curves_result" => {
            let mut receipt=v.clone();
            receipt["host_doc_rev"]=json!(*state.doc_rev.lock().unwrap());
            *state.curve_result.lock().unwrap() = Some(receipt);
        }
        "color_capture" => {
            let revision=*state.doc_rev.lock().unwrap();
            state.color_capture.lock().unwrap().armed_event(inspection_epoch,&v,revision);
        }
        "color_capture_sample" => state.color_capture.lock().unwrap().sample_event(inspection_epoch,&v),
        "source_patch_capture" => {
            let revision=*state.doc_rev.lock().unwrap();
            state.source_patch_capture.lock().unwrap().armed_event(inspection_epoch,&v,revision);
        }
        "color_picker_capture" => {
            let revision=*state.doc_rev.lock().unwrap();
            state.color_picker_capture.lock().unwrap().armed_event(inspection_epoch,&v,revision);
        }
        "white_balance_capture" => {
            let revision=*state.doc_rev.lock().unwrap();
            state.white_balance_capture.lock().unwrap().armed_event(inspection_epoch,&v,revision);
        }
        "color_scopes" => {
            let revision=*state.doc_rev.lock().unwrap();
            state.color_scopes.lock().unwrap().complete(&v,revision);
        }
        "levels_result" => {
            let mut receipt=v.clone();
            receipt["host_doc_rev"]=json!(*state.doc_rev.lock().unwrap());
            *state.levels_result.lock().unwrap() = Some(receipt);
        }
        "frame" => {
            if v.get("mode").and_then(|x| x.as_str()) == Some("compare") {
                *state.compare_frame.lock().unwrap() = Some(v.clone());
            }
            state.on_frame_event();
            // 裁剪/曝光那两条一次性 frame 带着 doc_state（面板重摆滑块的唯一依据）；
            // 拖拽帧没有这一格，一条也不进 note_doc
            if v.get("doc_state").is_some() {
                state.on_layer_frame(&v);
            }
        }
        "ready" => {
            let mut inspection=state.inspection.lock().unwrap();
            if inspection.epoch!=inspection_epoch{return;}
            inspection.ready(inspection_epoch,v["inspection_protocol"].as_u64()==Some(1));
            crate::shoulder_shape_api::ready(inspection_epoch, v["shoulder_shape_protocol"].as_u64() == Some(1));
            crate::leg_shape_api::ready(inspection_epoch, v["leg_shape_protocol"].as_u64() == Some(1));
            crate::waist_shape_api::ready(inspection_epoch, v["waist_shape_protocol"].as_u64() == Some(1));
            crate::leg_length_api::ready(inspection_epoch, v["leg_length_protocol"].as_u64() == Some(1));
            crate::neck_shape_api::ready(inspection_epoch, v["neck_shape_protocol"].as_u64() == Some(1));
            crate::arm_shape_api::ready(inspection_epoch, v["arm_shape_protocol"].as_u64() == Some(1));
            crate::preset_organisation_api::ready(inspection_epoch, v["preset_organisation_protocol"].as_u64() == Some(1));
            crate::sample_library_api::ready(inspection_epoch, v["sample_library_protocol"].as_u64() == Some(1));
            crate::semantic_colour_api::ready(inspection_epoch,v["semantic_colour_protocol"].as_u64()==Some(1),v["semantic_colour_workflow_protocol"].as_u64()==Some(1));
            state.batch_results.lock().unwrap().ready(inspection_epoch,v["batch_preflight_protocol"].as_u64()==Some(1));
            state.preset_results.lock().unwrap().ready(inspection_epoch,v["preset_result_protocol"].as_u64()==Some(1));
            state.white_balance_results.lock().unwrap().ready(inspection_epoch,v["white_balance_result_protocol"].as_u64()==Some(1));
            state.source_patch.lock().unwrap().ready(inspection_epoch,v["source_patch_result_protocol"].as_u64()==Some(1));
            state.local_masks.lock().unwrap().ready(inspection_epoch,v["local_masks_result_protocol"].as_u64()==Some(1));
            state.optics.lock().unwrap().ready(inspection_epoch,v["optics_protocol"].as_u64()==Some(1));
            state.studio_background.lock().unwrap().ready(inspection_epoch,v["studio_background_protocol"].as_u64()==Some(1));
            state.manual_liquify.lock().unwrap().ready(inspection_epoch,v["manual_liquify_protocol"].as_u64()==Some(1));
            state.effect_recovery.lock().unwrap().ready(inspection_epoch,v["effect_recovery_protocol"].as_u64()==Some(1));
            state.local_grade_live.lock().unwrap().ready(inspection_epoch,v["local_grade_live_protocol"].as_u64()==Some(1));
            state.source_patch_capture.lock().unwrap().ready(inspection_epoch,v["source_patch_capture_protocol"].as_u64()==Some(1));
            state.white_balance_capture.lock().unwrap().ready(inspection_epoch,v["white_balance_capture_protocol"].as_u64()==Some(1));
            state.color_picker_capture.lock().unwrap().ready(inspection_epoch,v["color_picker_capture_protocol"].as_u64()==Some(1));
            state.color_picker_results.lock().unwrap().ready(inspection_epoch,v["color_picker_result_protocol"].as_u64()==Some(1));
            state.color_picker_probes.lock().unwrap().ready(inspection_epoch,v["color_picker_result_protocol"].as_u64()==Some(1));
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
        "face_selected" | "face_list" | "face_manual" => {
            // 多人图选人（PORTRAIT-003）：一次点击一条。它与 precompute_ready 汇进同一个
            // 槽位——面板要的是「引擎现在说有几张脸、在改哪一张」，不关心是哪条事件说的。
            // face_manual（PORTRAIT-006）必须一起接：上一版只列了前两个，于是点了 ✕
            // 之后引擎那句「已关掉第 1 只」落在事件里而**没人往槽位搬**——面板读的是槽位，
            // 账记上了而屏幕不认（要等下一次 precompute 才刷新）。装机真窗口第 9 臂
            // 就是这么抓出来的：库里 20 条与端到端 2 条全部连的是裸引擎，看不见这一格。
            let name = v["event"].as_str().unwrap_or("").to_string();
            state.on_face(&v, &name);
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
        "enhance_done" => {
            // PORTRAIT-009 眼牙局部增强：与定向分开存。它报的是掩膜盖了多少格、
            // 每一格没接通的原因与那只窗口的常驻字节——这些数定向层没有，合成一份
            // 就会让面板"牙齿那一格是灰的"这句话找不到出处。
            state.on_enhance_ready(&v);
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
        "project_created" | "project_opened" | "project_saved" | "project_edited"
        | "project_state" => {
            // 项目面：五个名字进同一格（最后一条就是当前事实）。载荷只有名字与计数，
            // 整条回显：装机自证要拿它比“重开后 dirty 说的是不是真话”
            state.on_project(&v);
            println!("M0_PROJECT {line}");
        }
        "task_state" | "task_list" | "task_deleted" => {
            // 批量台账：逐条目一条，所以只印摘要不印整份（一批两百张就是两百行 payload，
            // 而计数与状态就是跑靶要的那两个字）。整份进 state，UI 轮询读
            state.on_task(&v);
            let c = &v["counts"];
            println!("M0_TASK id={} state={} ok={}/{} failed={} skipped={}",
                v["task_id"].as_str().unwrap_or("?"),
                v["state"].as_str().unwrap_or("?"),
                c["succeeded"].as_i64().unwrap_or(-1), c["total"].as_i64().unwrap_or(-1),
                c["failed"].as_i64().unwrap_or(-1), c["skipped"].as_i64().unwrap_or(-1));
        }
        "pick_start" | "pick_done" | "pick_state" => {
            // 挑图的账单（跑了多少张、按哪三档、判据指纹）只有这一份能进跑靶日志；
            // 逐格的那两条不印，500 张就是 500 行 payload
            state.on_pick(&v);
            println!("M0_PICK {line}");
        }
        "pick_item" => {
            state.on_pick(&v);
        }
        "pick_progress" => {
            state.on_pick(&v);
        }
        "pick_failed" => {
            state.on_pick(&v);
            state.push_log(format!("挑图量不开: {}", v["path"].as_str().unwrap_or("?")));
            println!("M0_PICK_FAILED {line}");
        }
        "thumb_failed" => {
            state.on_thumb(&v);
            state.push_log(format!("缩略图解不开: {}", v["path"].as_str().unwrap_or("?")));
            println!("M0_THUMB_FAILED {line}");
        }
        "error" => {
            *state.last_error.lock().unwrap() =
                Some(v["error"].as_str().unwrap_or("?").to_string());
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
