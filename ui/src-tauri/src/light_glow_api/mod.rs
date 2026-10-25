// SPDX-License-Identifier: GPL-3.0-or-later
//! Replaceable built-in creative:211524 transport, NOT a dynamic plug-in loader.
//! AUTHORED / UNRUN. Engine owns capture v3, rendering and canonical publication.
mod json;
mod imagery;
mod wire;
mod mailbox;
mod transport;

use std::sync::Arc;
use serde_json::Value;
use tauri::State;
use crate::{engine::EngineHandle, AppState};

pub(crate) fn reset(epoch: [u8;16]) { transport::reset(epoch); }
pub(crate) fn ready(epoch: [u8;16], capability: &Value) { transport::ready(epoch, capability); }
pub(crate) fn ended(epoch: [u8;16]) { transport::ended(epoch); }
pub(crate) fn observe_line(epoch: [u8;16], line: &str) -> Option<Value> { transport::observe_line(epoch, line) }
pub(crate) fn guards_result(epoch: [u8;16], id: &str) -> bool { transport::guards_result(epoch, id) }
pub(crate) fn read_only(command: &Value) -> bool { transport::read_only(command) }
pub(crate) fn blocks_mutation(epoch: [u8;16], command: &Value) -> Result<(),String> { transport::blocks_mutation(epoch, command) }
pub(crate) fn enqueue(handle: &EngineHandle, command: Value) -> Result<(),String> { transport::enqueue(handle, command) }

#[tauri::command]
pub(crate) fn light_glow_capability(state: State<'_, Arc<AppState>>) -> Result<Value,String> { transport::capability(state.inner()) }
#[tauri::command]
pub(crate) fn light_glow_request(state: State<'_, Arc<AppState>>, request: Value) -> Result<Value,String> { transport::request(state.inner(), request) }
#[tauri::command]
pub(crate) fn light_glow_status(_state: State<'_, Arc<AppState>>, request_id: String) -> Result<Value,String> { transport::status(request_id) }
#[tauri::command]
pub(crate) fn light_glow_cancel(state: State<'_, Arc<AppState>>, request_id: String) -> Result<Value,String> { transport::cancel(state.inner(), request_id) }
