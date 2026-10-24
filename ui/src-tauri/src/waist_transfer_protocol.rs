//! Waist scalar review uses its own operation and receipt field. Only proof shape,
//! bounded PNG validation and scalar validation are shared with torso.
use serde_json::Value;
pub(crate) use crate::torso_transfer_protocol::{MAX_TARGETS, acknowledgments, hex, parameters, revision, source_proof, transfer};
pub(crate) const WAIST_OP: &str = "lnx.waist_length.v1";
pub(crate) fn command(value: &Value) -> Result<(), String> {
    crate::torso_transfer_protocol::scalar_command(value, WAIST_OP, "waist_review_ack")
}
#[cfg(test)]
#[path = "waist_transfer_protocol_tests.rs"]
mod tests;
