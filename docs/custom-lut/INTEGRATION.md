# Integrated source candidate, 2026-10-23

Baseline `67d319b3d22240b909ed2424ddb34e1ce6208b43`. Requirement `LNX-REF-PC-32455-C-f8f5161c78` (滤镜/我的/CUBE导入), related builtin library/strength controls preserved. Status: SOURCE_CONNECTED_UNRUN. This is source-route evidence, not runtime, visual, performance or release acceptance.

## Actual route

`RetouchPanel` now mounts `ConnectedCustomLutPanel` under PC-32455, replacing the disabled import experience with native import/list/select/strength/name/hide/restore/recover controls. Native `custom_lut_choose` returns only a local .cube path. `customLut/nativePort` sends unique request identities and polls the bounded, engine-epoch-specific native mailbox. It never treats enqueue as success or replays a timed-out mutation. Backend `custom_lut_service` owns reader-registered cancellation events and explicit post-operation committed receipts. Source mutation/navigation cancels pending work; ordinary polling does not. Publication is fenced under the same cancellation lock. Cancellation after publication is reported as an already committed result, not fictional rollback.

Applying a custom LUT invokes existing `cmd_lut`, takes existing history snapshots and advances the document mutation fence. Existing render failure rollback remains in use. `CustomCube` occupies `_lut`, so no duplicate active effect or parallel stage is introduced. Builtin LUT algorithms remain unchanged. Existing generic LUT amount controls now call amount, rather than accidentally trying to set an undefined preset; zero remains zero.

`vram.set_lut/has_lut/apply_lut` dispatch CustomCube through the original Rust CPU parser/interpolator at the existing LUT stage, after HSL and before grade. Preview and full-quality export use the same Vram pipeline. Float32/64 editing tensors keep their dtype; only <=262144 pixels per tile cross CPU and use temporary float64 numerical buffers. No full-frame float64 inflation, downsample or uint8 round-trip. There is one same-dtype output tensor, plus bounded scratch and parsed table. CPU↔GPU transfers and per-row dispatch may be expensive; no GPU-speed or tested latency claim.

## Persistence and portability

- Immutable SHA-addressed SQLite blobs survive source file rename/move. Library removal is reversible hiding; referenced content is not physically deleted. All hidden bytes count toward 512-item/256-MiB quota; there is no GC UI.
- Project v15 explicitly serializes CustomCube as a content-addressed asset. v1–v14 remain recognized; v14 hair/body invariants are retained. Missing/corrupt custom bytes raise instead of using generic dropped-asset recovery. Existing whole-project 256 MB cap remains enforced. Old applications reject new v15 projects rather than silently losing custom LUTs.
- Preset save expands the local reference into embedded verified bytes. The preset file cap is 48 MiB to accommodate a 32-MiB text asset plus base64 overhead. Read-only UI receipts omit embedded bytes and identify this explicitly; application always loads the authoritative saved preset, never the summary.
- Batch frozen parameters use compact SHA/name references. The immutable bytes are registered locally before preflight and never physically removed; applying targets resolves/verifies bytes. Existing batch metadata and aggregate budgets are unchanged. A portable preset can seed a new machine; project decoding embeds the actual bytes.
- `render_snapshot` counts immutable CUBE content against its asset budget. `inspection_bundle` has a dedicated bounded tag backed by the existing array spool, not a huge JSON or pickle object. Full-quality inspection reconstructs and hash-validates CustomCube in the worker.
- Asset recovery picker accepts only exact original hash. A different file does not alter the old effect or enter the library. Malformed embedded project data blocks open; this does not claim an in-place project-file repair editor.

## Native/package and bounds

`packaging/stage-engine.sh` compiles/packages the original core and includes its source/license. No runtime build, dependency installation, model or LUT download. Missing native binary or ABI mismatch is explicit and cannot silently fall back to builtin parsing.

CUBE: 32 MiB; 250-byte lines; 1D 2–65536; 3D 2–65; strict finite decimal/row/header validation. Parser cancellation is before/after a bounded parse, not inside parsing. Interpolation observes cancellation between bounded tiles. Native mailbox: 64 outstanding, 65536 lifetime request IDs, 512 KiB compact result each. Library import reads one regular-file snapshot and forbids symlinks/FIFO/device inputs. Host permission policy remains unchanged.

Lookup coordinates clamp to DOMAIN endpoints; table values are never clipped. Strength blends 0–1. This is encoded-sRGB creative processing, not automatic ICC/RAW/log conversion. Negative/HDR values may be clamped by LUT domain and later by the existing export target. Float precision is retained up to the existing final RGB16 conversion.

## Verification status

Only static Python AST parsing, source inspection and SHA256 generation were performed. Rust compilation, native loading, TypeScript typecheck, UI, numerical fixtures, project/preset/batch/export/inspection execution, visual parity and performance remain UNRUN. New authored fixtures include core Rust cases and engine/tests/custom_lut_contract_test.py. Exact files/hashes are in manifest.json. Local verification must especially cover cancellation/publication races, unrelated edits while panel remains open, history failure after publication, portable clean-library restore, full-size CUBE memory, and source snapshot/inspection spool parity.
