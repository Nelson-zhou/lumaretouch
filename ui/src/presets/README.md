# Module presets

Entry: RetouchPanel → presets group → PC-32452. Existing LUT cards stay separate.
App always mounts usePresetWorkflow, so changing tool panels does not abandon an
accepted mutation. This implementation still requires execution/physical checks.

- presetWorkflow.ts: pure injectable transport state machine; capture request,
  document, preset ID and exact scope; acceptance is not completion. Timeout,
  lost transport, missing receipt or malformed evidence means uncertain, never
  automatic mutation resubmission. Recovery reads the same request ID only.
- presetModel.ts: name revision and stable-ID form reducer; explicit module
  selection; stale capability selections are visible and never broaden to all.
- usePresetWorkflow.ts: native bridge, application-lifetime ownership, dialogs
  and fresh authoritative state requests. Failed refresh cannot undo a confirmed
  save. No historical receipt.doc_state is installed into current controls.
- PresetPanel.tsx: reachable save name/scope controls, stored scope preview,
  default-no-overwrite import and explicit copy, builtin protection, precise
  delete confirmation, uncertain-outcome recovery. Name edits during saving survive.
- Native receipt_host.rs shares only mailbox mechanics with batch; preset_host.rs
  validates preset evidence. Neither query endpoint executes another mutation.

npm test includes workflow/model regressions and the global statusFence tests.
CI also executes preset_host::tests and existing batch_host::tests. The real
engine protocol test covers legacy/correlated saves, SHM pixels, one-step undo,
project reopen, stale identity rejection and no-mutation cached replay. Record
actual pass/skip evidence in docs/development/preset-workflow.md before acceptance.
