# AI native-size restoration — authored, all execution UNRUN

The UI exposes only Swin2SR-classical-sr-x2-64 native-size restoration. It does not turn the existing Lanczos export scale into AI, claim model availability from file presence, or report quality/performance acceptance. The engine capability must declare real runtime availability; `acceptance: unrun` remains separate.

The current full edited-source capture, immutable review token, source revision, before/after PNG SHA and dimensions, explicit user acknowledgement, and new-image-only return are checked in TS and native Rust. Display PNGs are never returned as model input. Reads and writes retain identities above modal lifetime. Timeout, hide, source switch, engine replacement, cancel acceptance and unknown write receipts do not authorize retransmission or report success. New copies then use ordinary project save/export; neither is triggered automatically.

Authored fixtures: model.unrun.test.ts and ../../src-tauri/src/upscale_restore_api/tests_unrun.rs. No fixture, typecheck, build, install, inference or application was executed.

Required future acceptance: clean unavailable state and exact blocker; installed genuine model runtime capability; original/edited/derived/RAW/16-bit colour capture; opaque SDR rejection without clipping/flattening; full-image model candidate; mismatched/source-stale/tampered image rejection; image load + explicit human acknowledgement; repeated clicks/hide/reopen/source switch/restart; unknown submission/query original/never reissue; successful independent copy and existing save/export; actual photographs for global-edge behaviour/texture/faces/text/hallucinations; resource, cancellation and latency measurements. No universal hardware claim.

The dedicated `data-upscale-restore-workflow` guard retains access to the owner while other creative editing is blocked; close hides only, and the activity receipt locator remains reachable.

Explicit model setup reuses the single optional-model subprocess owner, extension `upscale-native-v1`; fixed helper `lumaretouch_engine.upscale_v2.setup`. There is no arbitrary module/path input or automatic mount installation. The base torch 2.7.1+cpu and NumPy 2 runtime must already exist. Installer status is not engine capability. A matching protocol (even a cached unavailable status) permits an explicit current-source read: Python rechecks actual runtime readiness before capture. Only the fully validated current-source reply refreshes native capability and session. No automatic restart, forced availability, or edit loss.

Session lease is 900 seconds, matching the engine. UI bounded waits may surface a still-pending/unknown read before the CPU worker finishes; polling preserves the original identity and never resubmits it. CPU performance remains unmeasured.

## Restricted single-frame source profile

Each source side must be 16–1024 pixels, total at most 1,048,576 pixels. Model inference uses one complete full-frame input, not multiple neural tiles. Swin finite attention masks retain global-edge cyclic dependencies; adding a local halo does not establish full-frame equivalence. Larger photographs are explicitly unsupported: no source downsampling, proxy substitution, neural tiling or claimed full-photo restoration. Display-only PNG resizing remains separate from inference input. This intentionally restricted profile is not acceptance for ordinary large wedding photographs.
