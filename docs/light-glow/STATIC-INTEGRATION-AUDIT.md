# Light glow static integration audit

Status: **AUTHORED / UNRUN**, 2026-10-25. This pass read the scoped source only.
No product module was imported or executed, and no tests, type checks, builds,
native calls, image downloads, inference, installations or Git commands ran.
This is not runtime approval or a photographic-quality certificate.

## Concrete findings and dispositions

1. The original `nativePort.ts` called `validGlowReview` with its retained small
   `SourceProof`, while the validator required a complete `GlowContext`. That
   structural TypeScript incompatibility was reported and corrected in
   `model.ts`: the validator now accepts precisely the owner, evidence and before
   hash fields it reads. Native transport additionally compares before dimensions.
2. Current-source acquisition needed to settle pending local curve edits, not
   only check the engine queue or preflight preview/apply. The completed
   `useGlowWorkspaceBinding.ts` now waits for `settleCurveEdit` before acquisition
   and checks the committed live scope/generation again. This was reviewed as
   source, not exercised in React.
3. Existing host fixtures did not exercise the actual canonical publication
   boundary. `engine/tests/test_light_glow_publication_unrun.py` now authors that
   path with a real Engine, real native glow and canonical conversion, serialized
   handlers, actual history and `CreativeHost.commit_return`. It is still UNRUN.

No additional definite cross-layer protocol mismatch was identified in this
bounded source pass. Absence of another finding is not a build/runtime pass.

## Boundaries traced

- `core/light_glow/light_glow.h` and `lib.rs` agree with
  `light_glow_native.py`: ABI 1, math identity 65537, field order and scalar
  widths, element-counted RGBA/coverage buffers, synchronous cancel callback,
  56-byte settings, 32-byte geometry and 72-byte plan declarations. The Python
  tile adapter consumes the native source-region plan and never feeds a rendered
  tile back as another tile's input.
- Capability requires the installed core's ABI, math, struct-size and symbol
  checks plus the canonical creative renderer. `server.py` publishes protocol 1
  separately from capture evidence version 3. Native `ready` validates the
  complete capability, and App validates it again before acquisition.
- `light_glow_source.py` requests complete current edited capture, not the proxy
  framebuffer, and binds the actual file, document, load, people graph and
  ordered repair evidence. Unsupported transparency/HDR return is rejected.
- `light_glow_stage.py` retains full canonical float32 pixels. Before/after PNGs
  are display-only and share the complete-frame projection. Green alpha comes
  from actual native maximum RGB delta; its full-grid digest and PNG digest are
  separately bound into apply. Native validates PNG bytes/CRCs/hashes; UI also
  verifies bytes and requires decoded dimensions plus explicit review.
- `light_glow_host.py` calls only the canonical `new_image` return path. It marks
  an entered write uncertain before publication, reads the actual new row back,
  requires a distinct document identity, and preserves exact original receipts.
  No direct original-file overwrite or second history controller is introduced.
- `command_registry.py`, `server.py`, `creative_capture_routes.py`,
  `read_job_ingress.py` and `project_recovery_runtime.py` connect dispatch,
  rejection, read-only classification, unknown-write guards and cancellation.
- Tauri `main.rs`, `engine.rs`, `native_dispatch.rs` and `capture_lifecycle.rs`
  connect command registration, engine epochs, raw-line admission before generic
  settlement, one-use dispatch, dedicated out-of-band read cancellation and
  terminal engine lifecycle. Private native epoch metadata is removed before
  Python ingress. No lens command or lens-render alias substitutes for glow.
- `App.tsx` mounts `useGlowWorkspaceBinding` and the host above the transient
  panel, uses real source/load/engine/revision identities and connects catalogue
  entry 211524. `guardCreativeWork.ts` includes the glow host while retaining the
  prior tool selectors. Queue activity is admission-only, not external busy state
  that would automatically invalidate the operation that caused it.
- `packaging/stage-engine.sh` invokes the new explicit build helper at the exact
  filename consumed by Python. Neither application startup nor capability
  discovery compiles, downloads or installs the module.

## Authored real-publication fixture

The new fixture creates a tiny local synthetic PNG, records two real exposure
edit groups and undoes one so the original has nonempty undo and redo stacks.
It then traverses full current capture, real native preview, exact apply and the
real canonical copy transaction. Assertions cover original bytes, state,
history, people graph and document revision; independent copy identity,
canonical content/document validity and fresh history; zero/nonzero strength;
exact receipt replay without duplicate copies; and a deliberately lost return
acknowledgement after real publication, reconciled by canonical readback without
a second commit. A face-backend sentinel prevents inference. Missing required
packaged binaries/dependencies are explicit skips, never substitute successes.

The test does not run a Tauri window or the stdin reader thread, and does not
prove UI presentation, cancellation latency, transactional rollback after an
internal mutation failure, or deployed packaging. Those are separate cases.

## Unresolved execution and product limits

- Compilation/type checking, Python imports and execution, all authored tests,
  native ABI loading, package assembly and runtime smoke acceptance are UNRUN.
- The required glow and creative shared-library files were not present at the
  checked source-tree `bin/` paths during this pass. Source hooks and build
  helpers therefore do not establish an installed or usable feature here.
- Cancellation/unmount/repeated-click/navigation behavior was source-reviewed
  only; actual browser decode, screen review and native event ordering remain
  unverified. Memory/RSS, timing, seams and photographic comparisons are UNRUN.
- The exposed workflow is one current opaque SDR photograph and an independent
  new image. Batch, original replacement, transparent/HDR return and AI
  lit-surface analysis are not supplied by this integration.
- The module boundaries are replaceable built-ins, not dynamic third-party
  plug-in loading or hot-swapping. Official reference text does not establish
  vendor-equivalent numeric ranges, presets or image quality.
