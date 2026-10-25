# Explicit renderer choice and wire v3 — AUTHORED / UNRUN

This slice changes the lens UI family only. It is an authored integration contract, not evidence that a native binary, photographic result, 24 MP workload, or performance target has passed. Static TypeScript/TSX syntax parsing and source/hash inspection are separate from tests, typechecking, builds and runtime review. The older `README.md` and `HOST-PORT.md` describe the previous wire-v2/capability-v1 stage; the version statements below supersede those statements, not their ownership, source, cancellation or receipt rules.

## Independent version axes

- Wire protocol is **3** for preview, manual-plane preparation, Apply, Cancel, reviews and receipts. Their existing exact field sets and new-image return mode are otherwise unchanged. Wire 1/2 packets are rejected, not upgraded in the browser.
- Capability is **2** with exactly `version`, `operation_id`, `status`, `kernels`, `renderers`, `reason`. The capability operation remains `lnx.lens_blur.v1`, identifying the lens module family rather than the selected recipe.
- Depth assets remain **1**, with the exact existing owner, mapping, orientation, raster and provenance contract.
- Recipe **1** and recipe **2** are a discriminated union. Neither the wire number nor availability of a new renderer changes an existing recipe.

An available capability contains nonempty unique lists of supported kernels and renderers. An unavailable capability has both lists empty. Unknown/duplicate renderers, missing/extra keys, old capability versions and an unavailable capability retaining either list fail validation. The existing five aperture IDs are unchanged. Renderer IDs are exactly `direct-v1` and `cohort-fft-v2`; either or both may be advertised.

## Exact recipe identity

Both recipe versions have the unchanged common fields `source`, `depth`, `aperture`, `max_radius_px`, `focus`, `depth_falloff`, `occlusion_tolerance`, `rotation_radians`, and `refinements`.

Recipe v1 has exactly the previous keys: the common fields plus `version: 1` and `operation_id: 'lnx.lens_blur.v1'`. It has no renderer or math-identity field. Appending `math_identity` to an otherwise v1 recipe is rejected. Its scalar ranges, source-pixel geometry, focus and ordered stroke semantics are unchanged.

Recipe v2 has the common fields plus `version: 2`, `operation_id: 'lnx.lens_blur.cohort.v2'` and required `math_identity: 'cohort-fft-f64-v2-00020001'`. A mismatched or absent identity, a future version or any extra key is rejected. This corresponds to the separately owned native ABI 2/math `0x00020001`; it does not replace the v1 native core.

V2 accepts only exact `manual` / `user_defined_plane` provenance, including its explicit depth value and acknowledgement ID. It does not accept `user_supplied_depth` or `model` provenance, even when all other fields appear valid. Matching against the current depth asset still requires exact source, token, raster digest and provenance. The native host separately enforces opaque SDR source pixels, constant-plane correctness and resource admission. Browser validation is not proof of native execution or pixel suitability.

## Choice, initialization and acknowledgement

The renderer selector precedes the effect controls and preview action. V1 is the default for a new session when advertised, irrespective of renderer array ordering. If only cohort v2 is available and the depth is an explicit manual plane, a new v2 candidate recipe is initialized but preview remains blocked until the user explicitly checks the new-math acknowledgement. Merely advertising v2 never supplies that acknowledgement. For incompatible supplied/model depth, no v2 recipe is synthesized or provenance relabeled: the existing v1-shaped initial settings remain unavailable for rendering until a compatible path is chosen.

The manual-plane action continues to send the exact explicit `acknowledged_manual: true` command and value 0.5. Its UI explains which renderer will initialize, distinguishes a constant editing baseline from real depth, and says that preparing the baseline does not accept v2 math. No renderer, math or extra acknowledgement key is smuggled into the manual-plane wire command.

`selectRenderer` is the only workflow action that changes a recipe's version. The conversion helper reconstructs the exact destination shape while cloning all common fields, including unchanged source/depth ownership, numeric controls and ordered brush points. Converting back to v1 removes the v2-only identity rather than retaining an invalid extra key. Normal `edit`, focus and brush actions cannot change the version. Upstream stored recipes are not migrated or rewritten by this UI.

Each explicit renderer change discards the old candidate, before/after presentation proofs and final-review acknowledgement. V2 also requires a fresh math opt-in. The UI explains that v2 is a different mathematical renderer, not pixel-equivalent v1 acceleration; the before/after section and final checkbox identify the actual candidate recipe version and, for v2, its math identity. The separate final image-review acknowledgement is still required before saving a new copy.

Capability changes invalidate review and v2 math acknowledgement but preserve the exact current recipe. A missing selected renderer or kernel produces an explanation and blocks preview/Apply. It does not pick another renderer, alter the aperture, discard strokes, or reinterpret an old recipe. Reinstating the same renderer requires review again. Selecting an available alternative is a separate user action. These checks are UI admission only; native validation remains independently strict.

## Honest workload and image boundaries

The v2 disclosure states that:

- Only explicitly selected manual constant-plane editing on opaque SDR inputs is in scope.
- Feathering, low flow and overlapping strokes may create many intermediate radii. Those residual calculations have bounded work/memory budgets even when the grouped FFT component is admissible.
- A rejected residual budget is not permission to remove feathering, truncate strokes, use a different renderer, drop resolution or produce a neutral stand-in. The existing controls remain functional rather than becoming disabled/no-op placeholders. The user may deliberately reduce radius or dense refinements and request another preview.
- The full-source import, canonical-base and non-neutral full-resolution rendering paths retain their host-specific restrictions. This is not universal 24 MP support. RAW/TIFF, dense feathering and real-depth workflows remain limited. No throughput, latency, benchmark or photographic-quality claim is made.

The UI shows the host's capability reason even for available capabilities and preserves the exact error returned when preview admission or rendering fails. It does not estimate hidden native budgets from brush counts, claim every remaining brush configuration will work, or bypass a source-size/native gate.

## Ownership and interruption invariants

The per-source typed owner/source format is unchanged. `imagery.ts`, `useLensBlur.ts`, source acquisition, read ledgers, cancellation acceptance versus terminal outcomes, timeout behavior, exact original-write retention, receipt polling and new-copy editor refresh are not redesigned by this slice. `nativePort.ts` changes only the unavailable-capability shape; its calls inherit wire 3 through `LENS_PROTOCOL`.

An unresolved Apply or Cancel still blocks renderer changes and new writes. Capability changes may invalidate presentation consent but cannot replace its retained command. Read-only reconciliation of that original wire-3 request can finish even if its renderer is subsequently unavailable. Switching renderers does not submit, cancel, replay or infer the outcome of a native write. No second transaction path is introduced.

## Authored acceptance fixtures, not executed

`model.unrun.test.ts` adds exact capability-v2 validation, deterministic new-session renderer preference, v1 key preservation and v1↔v2 round-trip settings, wrong-math/extra-key rejection, v2 provenance rejection, and wire-2 review/write/receipt rejection.

`workflow.unrun.test.ts` adds explicit selection and independent math opt-in, common-control/stroke preservation, blocking version changes through ordinary edits, candidate/ACK invalidation, cohort-only initialization without implicit consent, capability loss/reinstatement without fallback or migration, supplied-depth refusal, and unresolved v2 write identity preservation. Existing real-image-presentation, pending/unknown write, cancellation, source invalidation and terminal-refresh cases remain authored.

Still required before any integrated/completed claim: actual native registration and capability selection, native v1/v2 rejection/dispatch correspondence, opaque-SDR/source-format gates, real manual-plane provenance, candidate math/digest correlation, full-resolution canonical output, every interruption path, bounded residual failures, returned independent-copy identity, export/save/reopen, browser accessibility and real-photo visual review. No product module or fixture was imported/executed, and no test, typecheck, compiler/build, inference, installation/download, native call, benchmark or Git operation was run for this UI slice.
