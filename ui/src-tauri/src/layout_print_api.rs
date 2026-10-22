//! Explicit GTK print dialog for an actual completed layout, never silent printing.
use std::{cell::RefCell, path::{Path, PathBuf}, rc::Rc, sync::{Arc, atomic::{AtomicBool, Ordering}}};
use serde_json::{json, Value};
use tauri::State;
use crate::AppState;
static PRINT_OPEN: AtomicBool = AtomicBool::new(false);
struct PrintGuard;
impl Drop for PrintGuard { fn drop(&mut self) { PRINT_OPEN.store(false, Ordering::Release); } }

#[tauri::command]
pub(crate) async fn print_layout(app: tauri::AppHandle, window: tauri::WebviewWindow,
    state: State<'_, Arc<AppState>>, manifest: String) -> Result<Value, String> {
    let layout = state.export.lock().map_err(|_| "export state unavailable")?
        .as_ref().and_then(|v| v.get("layout_result")).cloned().ok_or("no completed layout")?;
    if layout["manifest"].as_str() != Some(manifest.as_str()) || layout.get("error").is_some() {
        return Err("layout is stale or incomplete; export again".into());
    }
    if PRINT_OPEN.swap(true, Ordering::AcqRel) { return Err("print dialog already open".into()); }
    let guard = PrintGuard;
    let (send, receive) = std::sync::mpsc::channel();
    app.run_on_main_thread(move || {
        let _guard = guard;
        let result = show_dialog(window, layout);
        let _ = send.send(result);
    }).map_err(|e| e.to_string())?;
    tauri::async_runtime::spawn_blocking(move || receive.recv()
        .map_err(|_| "print dialog outcome unavailable".to_string())?)
        .await.map_err(|e| e.to_string())?
}

#[cfg(target_os = "linux")]
fn show_dialog(window: tauri::WebviewWindow, layout: Value) -> Result<Value, String> {
    use gtk::{prelude::*, gdk::prelude::*};
    use std::io::Read;
    let dimension = |key: &str| -> Result<f64, String> {
        layout[key].as_f64().filter(|x| x.is_finite() && *x >= 25. && *x <= 1000.)
            .ok_or_else(|| format!("invalid layout {key}"))
    };
    let width = dimension("width_mm")?;
    let height = dimension("height_mm")?;
    let root = Path::new(layout["directory"].as_str().ok_or("layout directory missing")?)
        .canonicalize().map_err(|e| e.to_string())?;
    let entries = layout["pages"].as_array().ok_or("layout pages missing")?;
    if entries.is_empty() || entries.len() > 200 || layout["page_count"].as_u64() != Some(entries.len() as u64) {
        return Err("invalid layout page count".into());
    }
    let expected_w = layout["width_px"].as_u64().ok_or("page width missing")?;
    let expected_h = layout["height_px"].as_u64().ok_or("page height missing")?;
    if expected_w == 0 || expected_h == 0 || expected_w.saturating_mul(expected_h) > 60_000_000 {
        return Err("layout page exceeds pixel limit".into());
    }
    let mut pages: Vec<PathBuf> = Vec::new();
    for entry in entries {
        let path = Path::new(entry.as_str().ok_or("page path missing")?).canonicalize().map_err(|e| e.to_string())?;
        if path.parent() != Some(root.as_path()) { return Err("page outside layout directory".into()); }
        let mut file = std::fs::File::open(&path).map_err(|e| e.to_string())?;
        let mut head = [0_u8; 24];
        file.read_exact(&mut head).map_err(|e| e.to_string())?;
        if &head[..8] != b"\x89PNG\r\n\x1a\n" || &head[12..16] != b"IHDR"
            || u32::from_be_bytes(head[16..20].try_into().unwrap()) as u64 != expected_w
            || u32::from_be_bytes(head[20..24].try_into().unwrap()) as u64 != expected_h {
            return Err("page PNG dimensions changed; export again".into());
        }
        pages.push(path);
    }
    let parent = window.gtk_window().map_err(|e| e.to_string())?;
    let operation = gtk::PrintOperation::new();
    let setup = gtk::PageSetup::new();
    let paper = gtk::PaperSize::new_custom("lrt-layout", "LumaRetouch layout", width, height, gtk::Unit::Mm);
    setup.set_paper_size(&paper);
    setup.set_top_margin(0., gtk::Unit::Mm); setup.set_bottom_margin(0., gtk::Unit::Mm);
    setup.set_left_margin(0., gtk::Unit::Mm); setup.set_right_margin(0., gtk::Unit::Mm);
    operation.set_default_page_setup(Some(&setup));
    operation.set_unit(gtk::Unit::Mm);
    operation.set_use_full_page(true);
    operation.set_n_pages(pages.len() as i32);
    operation.set_job_name("LumaRetouch photo layout");
    operation.set_allow_async(false);
    let error = Rc::new(RefCell::new(None::<String>));
    let settings_error = error.clone();
    operation.connect_begin_print(move |op, _| {
        if let Some(settings) = op.print_settings() {
            if (settings.scale() - 100.).abs() > 0.01 || settings.number_up() != 1 {
                *settings_error.borrow_mut() = Some("请选 100% 缩放且每纸一页，以保持照片物理尺寸".into());
                op.cancel();
            }
        }
    });
    let draw_error = error.clone();
    operation.connect_draw_page(move |op, context, index| {
        let drawn = (|| -> Result<(), String> {
            // Never shrink ID photos to printer margins or a changed paper size.
            if (context.width() - width).abs() > 0.5 || (context.height() - height).abs() > 0.5 {
                return Err("打印纸张尺寸与排版不一致，请选匹配纸张后重试；不会自动缩放证件照".into());
            }
            let path = pages.get(index as usize).ok_or("invalid print page")?;
            let pixbuf = gtk::gdk_pixbuf::Pixbuf::from_file(path).map_err(|e| e.to_string())?;
            if pixbuf.width() as u64 != expected_w || pixbuf.height() as u64 != expected_h {
                return Err("page dimensions changed during printing".into());
            }
            let cr = context.cairo_context().ok_or("printer has no drawing context")?;
            cr.save().map_err(|e| e.to_string())?;
            cr.scale(width / expected_w as f64, height / expected_h as f64);
            cr.set_source_pixbuf(&pixbuf, 0., 0.);
            let result = cr.paint().map_err(|e| e.to_string());
            cr.restore().map_err(|e| e.to_string())?;
            result
        })();
        if let Err(message) = drawn { *draw_error.borrow_mut() = Some(message); op.cancel(); }
    });
    let result = operation.run(gtk::PrintOperationAction::PrintDialog, Some(&parent)).map_err(|e| e.to_string())?;
    if let Some(message) = error.borrow().as_ref() { return Err(message.clone()); }
    // Apply means accepted by the print backend, not physical paper delivery.
    Ok(json!({"outcome": match result {
        gtk::PrintOperationResult::Apply => "submitted", gtk::PrintOperationResult::Cancel => "cancelled",
        _ => "unknown"}, "physical_output_verified": false}))
}
#[cfg(not(target_os = "linux"))]
fn show_dialog(_: tauri::WebviewWindow, _: Value) -> Result<Value, String> {
    Err("This build provides native printing on Linux only; use the exported PDF in your system viewer".into())
}

#[tauri::command]
pub(crate) async fn open_layout_pdf(state: State<'_, Arc<AppState>>, manifest: String) -> Result<Value, String> {
    let layout = state.export.lock().map_err(|_| "export state unavailable")?
        .as_ref().and_then(|v| v.get("layout_result")).cloned().ok_or("no completed layout")?;
    if layout["manifest"].as_str() != Some(manifest.as_str()) || layout.get("error").is_some() {
        return Err("layout is stale or incomplete".into());
    }
    let path = Path::new(layout["pdf"].as_str().ok_or("PDF missing")?)
        .canonicalize().map_err(|e| e.to_string())?;
    let directory = Path::new(layout["directory"].as_str().ok_or("layout directory missing")?)
        .canonicalize().map_err(|e| e.to_string())?;
    if path.parent() != Some(directory.as_path()) || path.file_name().and_then(|x|x.to_str()) != Some("layout.pdf") {
        return Err("invalid layout PDF path".into());
    }
    let status = tauri::async_runtime::spawn_blocking(move || std::process::Command::new("xdg-open").arg(path).status())
        .await.map_err(|e| e.to_string())?.map_err(|e| e.to_string())?;
    if !status.success() { return Err(format!("system PDF viewer failed: {status}")); }
    Ok(json!({"outcome":"opened"}))
}
