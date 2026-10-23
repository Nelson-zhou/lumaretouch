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

## XMP adaptation source implementation (AUTHORED / UNRUN)

- Dedicated original-XMP / portable-XMP JSON inspection and copy-import buttons
  require catalog xmp_import_protocol=1. Inspection works without a photo and
  never writes a preset. Ordinary JSON controls remain separate.
- The compatibility dialog starts with no selected groups. It lists every
  reported property, unsupported and invalid values, versions and bounded hashes.
  Import needs explicit group selection and non-Adobe acknowledgment. The mode
  only adapts observed ProcessVersion 11.0 syntax, never Adobe rendering behavior.
- XMP-backed presets always preflight the current document. Both frozen PNGs
  need successful browser decoding, exact dimensions, SHA-256 verification and
  a visual-review checkbox before apply. Review is bound to token, source/report
  hashes, document revision, effective source and people/recipe identities.
- Native xmp_preset_protocol.rs validates public report/summary schemas, native
  EV/explicit four-channel curves, PNG headers/dimensions and acknowledgment
  shapes. WebCrypto performs PNG digest verification; the engine authoritatively
  verifies the frozen token and both PNG hashes again before apply. Original XML
  remains engine-side and is not a public receipt or executable UI asset.
- Regression sources: existing presetWorkflow.test.ts additions, the new
  xmpImport/model.test.ts, and xmp_preset_protocol_tests.rs. The new standalone
  model test is not yet listed in the existing explicit npm test file list.

No build, typecheck, tests, imports, runtime or screenshot checks were executed
for this addition. Expat >= 2.7.2 is an unverified runtime prerequisite. Physical
acceptance still needs real XMP/photo pairs, disabled controls until both images
load, changed files, corrupt images, cancel/Escape/reopen, double clicks, document
switch/edit during review, unknown outcomes, old engines, portable imports,
one-step undo, project reopen and genuine full-resolution output comparison.
