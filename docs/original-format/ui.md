# Original format — UI and native intent boundary

Status: **source-authored; executable fixtures UNRUN**. No app launch, TypeScript
check, Rust build, UI test, encoder exercise, or runtime capability claim was made
in this slice. The existing application/export destination/task owners remain in
place; this adds neither a renderer nor a queue.

## Intent and receipt contract

- `original` is a policy choice displayed separately from `ready.export_formats`
  (the existing codec list). The option requires
  `export_original_format_protocol == 1` and
  `export_original_format_available == true`; the engine's reason is shown if
  capability disappears while Original is selected. There is no JPEG fallback.
- Selecting Original leaves the explicit-format `exportBits16` preference
  untouched, disables the bit-depth control, and omits both `bit_depth` (preview)
  and `bitDepth` (Tauri start). Returning to an explicit format restores the
  remembered control. The host rejects a manually supplied depth for Original.
- GPS remains an explicit intent for Original, even with a remembered manual
  16-bit preference. The engine rejects an Original batch containing a 16-bit
  decision and requested GPS; the UI does not silently clear the preference.
- An untouched TIFF preference is omitted for Original, so the engine retains
  its per-entry defaults (8-bit Deflate, 16-bit no compression). An explicitly
  chosen compression applies only to TIFF decisions. The quality control
  is labeled for applicable JPEG/WebP/PNG8 entries, not original compression or
  RGB16 encoder quality. Original does not mean a byte-identical copy or metadata
  preservation, and never rewrites RAW.
- Enabled target-size intent is retained across format switches. For Original,
  the UI validates the numeric policy without inventing source codec or depth;
  engine admission must prove **all** selected entries are JPEG8. Incompatible
  explicit formats produce an error instead of dropping the enabled policy.
- Native start requires nonempty distinct `document_ids`, destination policy,
  intent revision and frozen destination plan ID. Native preview supplies the
  same document identities to the existing `cmd_export_destination` owner.
  These checks are structural, not source or codec authentication.
- Destination v1's top-level schema remains unchanged. UI reads the engine's
  `settings_json.format_plan` (`lrt.export-format-plan.v1`) and per-entry
  `lrt.export-format-decision.v1` for display. It checks required receipt shapes,
  canonical codec/extensions, 8/16 precision, decision/fact digests, coverage of
  primary/clean entries and missing decisions. It does **not** generate, hash,
  resolve or send source facts or format decisions as input authority. Admission
  still recomputes and authenticates the plan in the engine.
- Preview shows per-entry actual codec/precision and decision identity. Clean
  variants display their primary decision but retain separate reserved paths.
  Layout PNG/PDF remains independently 8-bit; layout manifest remains JSON.
- Export queue reads per-image and per-variant actual format, bits, decision ID
  and fact ID. Pending Original is shown as unresolved, not fake TIFF16 or JPG8.
  A mixed Original batch's null depth never supplies an actual per-image depth.
  Existing partial output receipts, error messages and retry controls remain.

## Changed source manifest (UI slice)

- `ui/src/exportModel.ts`
- `ui/src/exportModel.test.ts` — authored executable fixtures, UNRUN
- `ui/src/App.tsx`
- `ui/src/native.ts`
- `ui/src/components/ExportMetadataOptions.tsx`
- `ui/src/components/ExportQueuePanel.tsx`
- `ui/src/exportDestination/model.ts`
- `ui/src/exportDestination/nativePort.ts`
- `ui/src/exportDestination/ExportDestinationPanel.tsx`
- `ui/src/exportTargetSize/model.ts`
- `ui/src/exportTargetSize/TargetSizeControls.tsx`
- `ui/src-tauri/src/export_destination_port.rs`
- `ui/src-tauri/src/main.rs`
- `docs/original-format/ui.md`

No automatic workflow profile or immutable profile hash is changed. The manual
successful-group delivery route still delegates to the same canonical preview
and start owner and forwards only the user's export intent.

## Authored UNRUN coverage and local acceptance matrix

`ui/src/exportModel.test.ts` retains explicit PNG16/TIFF tests and adds Original
precision/GPS memory, target-size retention, mixed decisions, clean/layout
mapping, malformed or absent decisions, intent-only transport and capability/
structural host guards. Qoder should execute the existing UI test command only
at the separately authorized local-testing stage.

| Scenario | Expected observation | Status |
| --- | --- | --- |
| Explicit PNG16 → Original → PNG | Original sends no depth; explicit16 preference survives | UNRUN |
| Original with JPEG8 + PNG16 + TIFF16 + WebP8 | Preview and actual image receipts retain each codec/precision | UNRUN |
| Original after capability missing/ABI mismatch | Option/start blocked with engine reason; no codec fallback | UNRUN |
| Original untouched / explicit TIFF compression | Untouched omitted; engine preserves 8-bit Deflate / 16-bit none; explicit choice applies only to TIFF | UNRUN |
| Original GPS requested + any native16 | Entire intent refused before task/directory admission; GPS stays checked | UNRUN |
| Original target-size with all JPEG8 | Intent reaches engine; existing bounded JPEG search owns output | UNRUN |
| Original target-size with one non-JPEG8 | Entire intent refused; target-size is not discarded | UNRUN |
| Native Original call with explicit 8 or 16 | Rejected as conflicting explicit depth | UNRUN |
| Original legacy images/out_dir only | Rejected: authoritative documents and frozen preview required | UNRUN |
| Watermark + clean with mixed Original | Separate planned paths, matching per-image codec/precision and decision IDs | UNRUN |
| Edit/select/change options during preview | Existing generation fence discards stale response | UNRUN |
| Repeated start / engine restart / source changed after preview | Existing owner fences reject/reconcile; no newly resolved retry | UNRUN |
| Failure after a variant committed | Queue retains committed output receipt and failure rather than hiding output | UNRUN |
| Same-session retry | Existing task identity and frozen plan/paths/decisions retained | UNRUN |
| Restored task without original in-session snapshot | Explicit refusal; no current-state reconstruction | UNRUN |
| Original layout | Photo decisions separate from layout's PNG/PDF8 contract | UNRUN |
