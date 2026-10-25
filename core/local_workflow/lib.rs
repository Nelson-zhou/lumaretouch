// SPDX-License-Identifier: GPL-3.0-or-later
//! Local workflow core only. Native/engine/UI adapters are separate owners.
//! No import, preset, renderer, inference, timer thread or implicit retry lives
//! here. An issued mutation is exposed only after its intent is durable.
//! Authored fixtures and all runtime/build verification are UNRUN.

pub mod schema;
pub mod ports;
pub mod scheduler;
pub mod ledger;
pub mod poll;

pub use ledger::DurableRunner;
pub use ports::{Command, CommandKind, Receipt, ReceiptResult};
pub use schema::{Graph, ValidatedGraph, WorkflowError};
pub use scheduler::{Event, RunStatus, Scheduler};

#[cfg(test)]
mod tests;
