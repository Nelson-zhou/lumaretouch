# Shared source integration — authored, UNRUN

Base: 30494a6e (includes waist tranche). Shared ownership grant received and all
routes below authored. This records source reachability, not compiled/runtime
success. Qoder/local tests and photographic acceptance remain unrun.

1. Canonical policy: `body_pose_operations.policies` registers
   `lnx.leg_length.v1`; same single body bank, source-owned support and BodyRef.
2. Canonical ordering: `body_pose_geometry.LEG_LENGTH_BODY_ORDER` is v5,
   appending length after v4. `effective_order` selects it only for active length.
   Neutral length retains exact prior v1–v4 order. Length project delegates this
   authority; no independent order selector remains.
3. Render/export: `body_pose_render.prepare` adds length fields to existing
   width+waist fields before arm/common preparation. Existing face/hair/mask and
   recovery inputs remain intact. No new RGB raster sampling pass. Generic
   frozen export snapshots resolve canonical v5 through arm/common project ports.
   Original RGB16/HDR source routes are unchanged; explicit export helper accepts
   finite uint8, uint16 and float32 without intermediate quantization.
4. Host: `body_pose_families`, `body_pose_host` and `body_pose_commands` register
   length presenter, independent receipt ledger and `cmd_leg_length` with the
   canonical document edit lock/publication/history. Terminal ledger is immutable;
   unknown outcomes are queried, never replayed. `arm_shape_registered_host`
   classifies length reads without cancelling unrelated pending acquisition.
5. Engine: `server.HANDLED`, dispatch shortcut and readiness register length.
   Capability is 1 only if packaged `bin/liblrt_leg_length.so` exists. Missing or
   invalid ABI remains a clear preparation refusal, never runtime compilation.
6. Native: `ui/src-tauri/src/leg_length_api.rs` validates precise recipe/support,
   pose anchors, source/document epoch, monotonic mailbox and canonical exact
   request replay signatures. `main.rs`, `native_dispatch.rs`, `engine.rs` and
   `capture_lifecycle.rs` register dispatch, ready/ended/reset/receive and read-only
   capture exemptions. Existing source, pixel and permission boundaries preserved.
7. UI bridge: `native.ts` exposes exact DocState/capability/mailbox types and
   `runLegLength`; operation/error receipts remain separate from width. Workflow
   checks event identity and retains original request identity through timeout.
8. UI host: `App.tsx` mounts the length workflow; `BodyShapeTools` exposes three
   baseline anchors and a distinct workspace/support picker. Shared activity,
   busy/uncertain locks, main canvas refresh, existing real body-analysis opener
   and source preview mapping are connected. `toolRouting/coverage.ts` only
   de-duplicates these exact three entries, not the remaining body family.
9. Project14/history: existing recursive bank validation gains canonical length
   policy; immutable support assets, reviews and v5 order persist in live,
   undo/redo and export trees. Gesture coalescing includes length. Length project
   exposes graph-fenced parameter-only transfer; destination review and explicit
   person confirmation required, and caller must prepare before publication.
   No automatic batch propagation of source measurements or anatomy is added.
10. Distribution: `stage-engine.sh` invokes explicit `build-leg-length.sh` and
    includes original Rust source, GPL license, documentation and body licenses.
    No packaging command was executed here.

`manifest.json` freezes all owned isolated and granted shared files, excluding
itself to avoid self-hashing and excluding unrelated blush/eye_light work.
Static Python AST/JSON/hash checks only. No tests, compiler, typecheck, product
imports/execution, inference, install, downloads or Git writes/push.

Remaining verification: native/UI compilation, runtime end-to-end receipts,
project14 replay, original-resolution RGB16/HDR export, combined geometry
photographic naturalness and performance. These are actual acceptance gaps,
not reported as passes. Conservative posture/support/128-pixel displacement
limitations are disclosed in README; no height/waist-length/torso-length/AI claim.
